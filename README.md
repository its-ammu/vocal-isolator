# Vocal Isolator

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)

Split any audio track into **vocals** and **instrumental** stems, via a web UI or a REST API. Two separation engines are supported:

| Engine | Model | Notes |
|---|---|---|
| **Demucs v4** (default) | `htdemucs` | Always available; no extra install |
| **Audio Separator** | MelBand Roformer (`vocals_mel_band_roformer.ckpt`) | Optional extra; often cleaner vocal isolation, GPU recommended |

Pick the engine per request with `engine=demucs` or `engine=audio_separator` — see [Usage](#usage-browser) and [API](#api) below.

## Table of contents

- [Setup](#setup)
- [Run](#run)
- [Usage (browser)](#usage-browser)
- [API authentication (optional)](#api-authentication-optional)
- [S3 output storage (optional)](#s3-output-storage-optional)
- [API documentation (Swagger)](#api-documentation-swagger)
- [API](#api)
- [Requirements](#requirements)
- [Deployment (systemd)](#systemd-linux-server-no-gunicorn)
- [Contributing](#contributing)
- [License](#license)

## Setup

```bash
uv sync
```

This installs **Demucs**, which works out of the box. To also enable the **Audio Separator** (MelBand Roformer) engine, install its extra:

```bash
uv sync --extra audio-separator
```

> **Apple Silicon note:** `audio-separator` currently pins `samplerate==0.1.0`, whose macOS wheel can be x86_64-only.
> If you see `incompatible architecture (have 'x86_64', need 'arm64')`, replace it with an arm64-friendly build:
>
> ```bash
> uv pip uninstall samplerate
> uv pip install "samplerate==0.2.3"
> ```

## Run

```bash
uv run python app.py
```

Or with Flask's dev server:

```bash
uv run flask --app app run --host 0.0.0.0 --port 8001
```

Then open http://localhost:8001 in your browser.

Both entry points run with Flask's debug/reloader off by default. Set `FLASK_DEBUG=1` to enable them for local development (never in production — the debugger allows arbitrary code execution).

## Usage (browser)

1. Upload an audio file (MP3, WAV, FLAC, OGG, M4A, AAC)
2. Pick an engine — **Demucs** or, if installed, **Audio Separator**
3. Wait for separation (often 1–3× track length on CPU)
4. Play or download the **vocals** and **instrumental** WAVs

## API authentication (optional)

If the environment variable **`VOCAL_ISOLATOR_API_KEY`** is set to a non-empty string, every request under **`/api/*`** must include that value in either:

- Header **`X-API-Key: <your-key>`**, or
- Header **`Authorization: Bearer <your-key>`**

If the variable is **unset** or **empty**, no API key is required (typical local development).

**Example**

```bash
export VOCAL_ISOLATOR_API_KEY='your-secret'
curl -sS -H "X-API-Key: $VOCAL_ISOLATOR_API_KEY" http://localhost:8001/api/engines
```

The web UI has an **API key** field (stored in `sessionStorage` for that browser only) so uploads work when the server requires a key.

## S3 output storage (optional)

By default, output WAV files are stored on the server's local disk and served from `/api/download/...`. To instead upload outputs to S3 and return presigned URLs, set:

| Variable | Default | Description |
|---|---|---|
| `VOCAL_ISOLATOR_S3_BUCKET` | *(unset — S3 disabled)* | Bucket name; setting this enables S3 uploads |
| `VOCAL_ISOLATOR_S3_PREFIX` | `vocal-isolator` | Key prefix within the bucket |
| `VOCAL_ISOLATOR_S3_PRESIGN_EXPIRES` | `604800` (7 days) | Presigned URL expiry, in seconds |
| `AWS_REGION` / `AWS_DEFAULT_REGION` | `us-east-1` | Bucket region |

Requires standard AWS credentials (env vars, shared config, or an instance/task role) with `s3:PutObject` and `s3:GetObject` on the bucket.

## API documentation (Swagger)

- **Swagger UI:** `GET /docs` (e.g. [http://localhost:8001/docs](http://localhost:8001/docs)) — **no API key**
- **OpenAPI JSON:** `GET /openapi.json` — **no API key** (legacy `/api/docs` and `/api/openapi.json` redirect here)

### Engine discovery

- `GET /api/engines` — engines you can pass as `engine=` (Audio Separator included only if installed)
- `GET /api/engines/status` — full catalog, import/version info, and torch device

## API

### Synchronous (blocks until done)

`POST /api/separate` — multipart form: `file`, optional `engine` (`demucs` or `audio_separator`, default `demucs`).

Returns JSON with relative paths to `GET /api/download/<job_id>/vocals` and `.../instrumental`.

### Async (create task → poll → fetch files)

1. **Create task** — `POST /api/tasks` (same form as above: `file`, optional `engine`).
   Response **202** with `task_id`, `poll_url`, and `status: "pending"`.

2. **Poll** — `GET /api/tasks/<task_id>` until `status` is `completed` or `failed`.

   - `pending` / `running` — still processing
   - `completed` — includes `vocals_url`, `instrumental_url` (absolute URLs), plus suggested filenames
   - `failed` — includes `error`

3. **Download** — `GET` the URLs from the completed response (same as `/api/download/<job_id>/vocals` and `.../instrumental`).
   Use the returned `job_id` (same as `task_id`) for the path form.

4. **Optional cleanup** — `DELETE /api/tasks/<task_id>` removes the task record and deletes the output WAV files.

**Example (curl)**

```bash
# 1. Create task
RESP=$(curl -sS -X POST -F "file=@track.mp3" -F "engine=demucs" http://localhost:8001/api/tasks)
echo "$RESP"

# 2. Poll (replace TASK_ID)
curl -sS http://localhost:8001/api/tasks/TASK_ID

# 3. When status is completed, download
curl -sS -OJ http://localhost:8001/api/download/TASK_ID/vocals
```

> **Production notes:** Tasks are stored in memory; use one worker process or an external queue (Redis + Celery/RQ) if you scale horizontally. Short `task_id` values are guessable — add authentication and rate limits for a public API.

## Requirements

- Python 3.11+
- **ffmpeg** (for loading MP3, M4A, etc.) — install with `brew install ffmpeg` on macOS
- ~2GB RAM for CPU inference
- GPU (CUDA/MPS) optional for faster processing; recommended for Audio Separator

### Linux / GPU instances: `libsamplerate` (Audio Separator)

The `samplerate` Python package loads the **system** library `libsamplerate`. Minimal AMIs often don't include it, which causes:

`OSError: libsamplerate not found`

Install the OS package, then restart your app:

| Distro | Command |
|--------|---------|
| Amazon Linux 2023 | `sudo dnf install -y libsamplerate` |
| Amazon Linux 2 | `sudo yum install -y libsamplerate` |
| Ubuntu / Debian | `sudo apt-get update && sudo apt-get install -y libsamplerate0` |
| RHEL / Rocky | `sudo dnf install -y libsamplerate` |

Verify: `ldconfig -p | grep libsamplerate` (should list `libsamplerate.so`).

If you only use **Demucs** and not Audio Separator, you can avoid this dependency entirely by not installing the `audio-separator` extra (Demucs does not use `samplerate`).

## systemd (Linux server, no Gunicorn)

A unit file is provided: [`deploy/vocal-isolator.service`](deploy/vocal-isolator.service). Edit `User`, `WorkingDirectory`, and `ExecStart` paths, then:

```bash
sudo cp deploy/vocal-isolator.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vocal-isolator
sudo systemctl status vocal-isolator
```

Listens on **port 8001** (Flask built-in server, `--no-reload`). Adjust the port in `ExecStart` if needed.

### systemd: `FileNotFoundError: 'ffmpeg'`

Interactive shells usually have a full `PATH` (Homebrew, conda, etc.). **systemd** does not, so `ffmpeg` / `ffprobe` may not be found even though `curl` works from your terminal.

1. Install ffmpeg on the host if needed (e.g. `sudo dnf install -y ffmpeg` on Amazon Linux 2023).
2. As the **same user** the service runs as, check:
   `sudo -u ec2-user bash -lc 'command -v ffmpeg; command -v ffprobe'`
3. Put every directory from step 2 into the unit's `Environment=PATH=...` (see `deploy/vocal-isolator.service`; prepend directories separated by `:`).

Then: `sudo systemctl daemon-reload && sudo systemctl restart vocal-isolator`.

**Miniconda / conda:** `ffmpeg` is often under `~/miniconda3/bin`. systemd does **not** expand `~` — use the full path, e.g. prepend `/home/ec2-user/miniconda3/bin` to `PATH` in the unit file (see `deploy/vocal-isolator.service`) or in `.env.local`:

`PATH=/home/ec2-user/miniconda3/bin:/usr/local/bin:/usr/bin:/bin`

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE)
