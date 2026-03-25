"""Vocal isolator web application using Demucs v4 or Audio Separator."""

import os
import shutil
import subprocess
import tempfile
import threading
import time
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import torch
import torchaudio as ta
from flask import Flask, jsonify, request, send_file

import soundfile as sf
from demucs.apply import apply_model
from demucs.audio import AudioFile, convert_audio, prevent_clip
from demucs.pretrained import get_model

from openapi_spec import build_openapi_dict

# All engines we know about (for status); selectable engines omit unavailable optional deps.
ENGINE_CATALOG = {
    "demucs": {
        "label": "Demucs v4 (htdemucs)",
        "model": "htdemucs",
    },
    "audio_separator": {
        "label": "Audio Separator (MelBand Roformer)",
        "model": "vocals_mel_band_roformer.ckpt",
    },
}

ENGINES = {"demucs": ENGINE_CATALOG["demucs"]["label"]}
try:
    import audio_separator  # noqa: F401
    ENGINES["audio_separator"] = ENGINE_CATALOG["audio_separator"]["label"]
except ImportError:
    pass

BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__, static_folder="static", static_url_path="/static")

# API auth: set VOCAL_ISOLATOR_API_KEY to require X-API-Key or Authorization: Bearer on all /api/* routes
API_KEY = os.environ.get("VOCAL_ISOLATOR_API_KEY", "").strip()


def _request_provides_api_key() -> str:
    """Return API key from X-API-Key or Authorization: Bearer."""
    key = (request.headers.get("X-API-Key") or "").strip()
    if key:
        return key
    auth = request.headers.get("Authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return ""


@app.before_request
def _require_api_key():
    if not API_KEY:
        return None
    if request.method == "OPTIONS":
        return None
    path = request.path or ""
    if not path.startswith("/api/"):
        return None
    if _request_provides_api_key() != API_KEY:
        return jsonify({"detail": "Unauthorized"}), 401
    return None


# Auto-detect best device: CUDA > MPS (Apple Silicon) > CPU
DEVICE = (
    "cuda"
    if torch.cuda.is_available()
    else "mps"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available()
    else "cpu"
)

# Create output directory for processed files
OUTPUT_DIR = BASE_DIR / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# Async API: background separation (single worker avoids GPU contention)
_tasks_lock = threading.Lock()
TASKS: dict[str, dict] = {}
_task_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="separate")

ALLOWED_EXTENSIONS = {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"}


def allowed_file(filename):
    return Path(filename or "").suffix.lower() in ALLOWED_EXTENSIONS


def _run_separation(engine: str, input_path: Path, vocals_path: Path, instrumental_path: Path) -> None:
    if engine == "demucs":
        _separate_demucs(vocals_path, instrumental_path, input_path)
    else:
        _separate_audio_separator(vocals_path, instrumental_path, input_path)


def _process_task(
    task_id: str,
    engine: str,
    input_path: Path,
    temp_dir: Path,
    base_url: str,
    original_stem: str,
) -> None:
    """Background worker: run separation and update TASKS."""
    vocals_path = OUTPUT_DIR / f"{task_id}_vocals.wav"
    instrumental_path = OUTPUT_DIR / f"{task_id}_instrumental.wav"
    try:
        with _tasks_lock:
            if task_id in TASKS:
                TASKS[task_id]["status"] = "running"
        _run_separation(engine, input_path, vocals_path, instrumental_path)
        base = base_url.rstrip("/")
        with _tasks_lock:
            if task_id in TASKS:
                TASKS[task_id].update(
                    {
                        "status": "completed",
                        "job_id": task_id,
                        "vocals_url": f"{base}/api/download/{task_id}/vocals",
                        "instrumental_url": f"{base}/api/download/{task_id}/instrumental",
                        "vocals_filename": f"{original_stem}_vocals.wav",
                        "instrumental_filename": f"{original_stem}_instrumental.wav",
                    }
                )
    except Exception as e:
        traceback.print_exc()
        with _tasks_lock:
            if task_id in TASKS:
                TASKS[task_id].update({"status": "failed", "error": str(e)})
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.route("/")
def index():
    """Serve the main page."""
    return send_file(BASE_DIR / "static" / "index.html", mimetype="text/html")


@app.route("/api/openapi.json")
def openapi_json():
    """OpenAPI 3 document (machine-readable)."""
    return jsonify(build_openapi_dict())


@app.route("/api/docs")
def swagger_ui():
    """Swagger UI (interactive docs)."""
    return send_file(BASE_DIR / "static" / "swagger.html", mimetype="text/html")


def _separate_demucs(vocals_path: Path, instrumental_path: Path, input_path: Path) -> None:
    """Separate vocals and instrumental (non-vocal mix) using Demucs v4."""
    model = get_model(name="htdemucs")
    model.to(DEVICE)

    try:
        wav = AudioFile(input_path).read(
            streams=0,
            samplerate=model.samplerate,
            channels=model.audio_channels,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        wav, sr = ta.load(str(input_path))
        wav = convert_audio(wav, sr, model.samplerate, model.audio_channels)

    ref = wav.mean(0)
    std = ref.std()
    if std == 0:
        std = 1.0
    wav = (wav - ref.mean()) / std

    sources = apply_model(
        model,
        wav[None],
        device=DEVICE,
        shifts=1,
        split=True,
        overlap=0.25,
        progress=False,
        segment=None,
    )[0]

    sources = sources * std + ref.mean()
    vocals_idx = model.sources.index("vocals")
    vocals = sources[vocals_idx]

    # Instrumental = drums + bass + other (everything except vocals)
    instrumental = torch.zeros_like(vocals)
    for i, name in enumerate(model.sources):
        if name != "vocals":
            instrumental = instrumental + sources[i]

    vocals = prevent_clip(vocals, mode="rescale")
    instrumental = prevent_clip(instrumental, mode="rescale")
    sf.write(str(vocals_path), vocals.cpu().numpy().T, model.samplerate)
    sf.write(str(instrumental_path), instrumental.cpu().numpy().T, model.samplerate)


def _resolve_output_paths(sep_dir: Path, output_files: list[str]) -> list[Path]:
    """Resolve audio-separator return paths (may be relative) to absolute paths."""
    resolved: list[Path] = []
    for f in output_files:
        p = Path(f)
        if p.is_absolute() and p.exists():
            resolved.append(p)
            continue
        for base in (sep_dir, Path.cwd()):
            cand = base / p
            if cand.exists():
                resolved.append(cand)
                break
    return resolved


def _find_audio_separator_stems(sep_dir: Path) -> tuple[Path | None, Path | None]:
    """Pick vocals and Other stems from MelBand Roformer output filenames."""
    vocals_file: Path | None = None
    other_file: Path | None = None
    for wav in sorted(sep_dir.glob("*.wav")):
        lower = wav.name.lower()
        if "(vocals)" in lower:
            vocals_file = wav
        elif "(other)" in lower:
            other_file = wav
    return vocals_file, other_file


def _separate_audio_separator(
    vocals_path: Path, instrumental_path: Path, input_path: Path
) -> None:
    """Vocals + instrumental (Other) using MelBand Roformer via Audio Separator."""
    try:
        from audio_separator.separator import Separator
    except ImportError:
        raise RuntimeError(
            "Audio Separator is not installed. Run: uv sync --extra audio-separator "
            "(requires Python 3.11+)"
        )

    sep_dir = Path(tempfile.mkdtemp())
    try:
        separator = Separator(
            output_dir=str(sep_dir),
            output_format="WAV",
        )
        separator.load_model(model_filename="vocals_mel_band_roformer.ckpt")
        output_files = separator.separate(str(input_path))

        resolved = _resolve_output_paths(sep_dir, output_files or [])
        vocals_file: Path | None = None
        other_file: Path | None = None

        for p in resolved:
            name = p.name.lower()
            if "(vocals)" in name:
                vocals_file = p
            elif "(other)" in name:
                other_file = p

        if vocals_file is None or other_file is None:
            v2, o2 = _find_audio_separator_stems(sep_dir)
            vocals_file = vocals_file or v2
            other_file = other_file or o2

        if vocals_file is None or not vocals_file.exists():
            raise RuntimeError(
                f"Vocals stem not found. Returned: {output_files}, dir={list(sep_dir.glob('*.wav'))}"
            )
        if other_file is None or not other_file.exists():
            raise RuntimeError(
                f"Instrumental (Other) stem not found. Returned: {output_files}, dir={list(sep_dir.glob('*.wav'))}"
            )

        shutil.copy(vocals_file, vocals_path)
        shutil.copy(other_file, instrumental_path)
    finally:
        shutil.rmtree(sep_dir, ignore_errors=True)


@app.route("/api/engines")
def list_engines():
    """Return selectable separation engines (same as UI dropdown)."""
    return jsonify({"engines": ENGINES})


@app.route("/api/engines/status")
def engines_status():
    """
    All engines in the catalog, whether dependencies are importable,
    model id, and runtime (torch device). Weights are loaded per request, not kept in RAM.
    """
    import demucs

    demucs_ver = getattr(demucs, "__version__", "unknown")
    audio_sep_ver: str | None = None
    try:
        import audio_separator

        audio_sep_ver = getattr(audio_separator, "__version__", "unknown")
    except ImportError:
        pass

    engines: dict[str, dict] = {}
    engines["demucs"] = {
        "id": "demucs",
        "label": ENGINE_CATALOG["demucs"]["label"],
        "available": True,
        "importable": True,
        "models_loaded_in_memory": False,
        "model": ENGINE_CATALOG["demucs"]["model"],
        "package_version": demucs_ver,
    }
    sep = ENGINE_CATALOG["audio_separator"]
    engines["audio_separator"] = {
        "id": "audio_separator",
        "label": sep["label"],
        "available": audio_sep_ver is not None,
        "importable": audio_sep_ver is not None,
        "models_loaded_in_memory": False,
        "model": sep["model"],
        "package_version": audio_sep_ver,
    }

    return jsonify(
        {
            "device": str(DEVICE),
            "torch_version": torch.__version__,
            "engines": engines,
        }
    )


@app.route("/api/tasks", methods=["POST"])
def create_task():
    """
    Create an async separation task. Returns 202 with task_id and poll_url.
    Poll GET /api/tasks/<task_id> until status is completed or failed.
    """
    if "file" not in request.files:
        return jsonify({"detail": "No file provided"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"detail": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify(
            {"detail": f"Unsupported format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}
        ), 400

    engine = request.form.get("engine", "demucs")
    if engine not in ENGINES:
        return jsonify({"detail": f"Unknown engine. Choose: {', '.join(ENGINES)}"}), 400

    suffix = Path(file.filename or "audio").suffix.lower()
    task_id = str(uuid.uuid4())[:8]
    original_stem = Path(file.filename or "audio").stem
    temp_dir = Path(tempfile.mkdtemp())
    input_path = temp_dir / f"input{suffix}"
    file.save(str(input_path))

    base_url = request.host_url or request.url_root or "http://localhost:8001/"
    poll_url = f"{base_url.rstrip('/')}/api/tasks/{task_id}"

    with _tasks_lock:
        TASKS[task_id] = {
            "status": "pending",
            "engine": engine,
            "created_at": time.time(),
            "error": None,
        }

    _task_executor.submit(
        _process_task, task_id, engine, input_path, temp_dir, base_url, original_stem
    )

    return (
        jsonify(
            {
                "task_id": task_id,
                "status": "pending",
                "poll_url": poll_url,
                "message": "Poll poll_url until status is completed or failed.",
            }
        ),
        202,
    )


@app.route("/api/tasks/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """Poll task status; when completed, includes vocals_url and instrumental_url."""
    if not task_id.replace("_", "").replace("-", "").isalnum():
        return jsonify({"detail": "Invalid task ID"}), 400

    with _tasks_lock:
        task = TASKS.get(task_id)

    if task is None:
        return jsonify({"detail": "Task not found"}), 404

    out = {"task_id": task_id, **task}
    return jsonify(out)


@app.route("/api/tasks/<task_id>", methods=["DELETE"])
def delete_task(task_id: str):
    """Remove task metadata and output WAV files (optional cleanup)."""
    if not task_id.replace("_", "").replace("-", "").isalnum():
        return jsonify({"detail": "Invalid task ID"}), 400

    with _tasks_lock:
        if task_id not in TASKS:
            return jsonify({"detail": "Task not found"}), 404
        del TASKS[task_id]

    for name in (f"{task_id}_vocals.wav", f"{task_id}_instrumental.wav"):
        p = OUTPUT_DIR / name
        p.unlink(missing_ok=True)

    return "", 204


@app.route("/api/separate", methods=["POST"])
def separate_vocals():
    """
    Upload an audio file and separate vocals.
    Returns the isolated vocals as a downloadable WAV file.
    """
    if "file" not in request.files:
        return jsonify({"detail": "No file provided"}), 400

    file = request.files["file"]
    if not file or file.filename == "":
        return jsonify({"detail": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify(
            {"detail": f"Unsupported format. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"}
        ), 400

    engine = request.form.get("engine", "demucs")
    if engine not in ENGINES:
        return jsonify({"detail": f"Unknown engine. Choose: {', '.join(ENGINES)}"}), 400

    suffix = Path(file.filename or "audio").suffix.lower()
    job_id = str(uuid.uuid4())[:8]
    temp_dir = Path(tempfile.mkdtemp())
    stem = Path(file.filename or "audio").stem
    vocals_path = OUTPUT_DIR / f"{job_id}_vocals.wav"
    instrumental_path = OUTPUT_DIR / f"{job_id}_instrumental.wav"

    try:
        input_path = temp_dir / f"input{suffix}"
        file.save(str(input_path))

        _run_separation(engine, input_path, vocals_path, instrumental_path)

        return jsonify(
            {
                "job_id": job_id,
                "download_url": f"/api/download/{job_id}/vocals",
                "filename": f"{stem}_vocals.wav",
                "instrumental_download_url": f"/api/download/{job_id}/instrumental",
                "instrumental_filename": f"{stem}_instrumental.wav",
            }
        )

    except Exception as e:
        traceback.print_exc()
        return jsonify(
            {"detail": f"Separation failed: {str(e)}"}
        ), 500

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def _download_stem(job_id: str, stem: str):
    if not job_id.replace("_", "").replace("-", "").isalnum():
        return jsonify({"detail": "Invalid job ID"}), 400
    if stem not in ("vocals", "instrumental"):
        return jsonify({"detail": "Invalid stem"}), 400

    name = f"{job_id}_vocals.wav" if stem == "vocals" else f"{job_id}_instrumental.wav"
    file_path = OUTPUT_DIR / name
    if not file_path.exists():
        return jsonify({"detail": "File not found or expired"}), 404

    return send_file(
        file_path,
        mimetype="audio/wav",
        as_attachment=True,
        download_name=name,
    )


@app.route("/api/download/<job_id>/<stem>")
def download_stem(job_id, stem):
    """Download vocals or instrumental WAV."""
    return _download_stem(job_id, stem)


@app.route("/api/download/<job_id>")
def download_vocals_legacy(job_id):
    """Legacy URL: same as vocals stem."""
    return _download_stem(job_id, "vocals")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8001, debug=True)
