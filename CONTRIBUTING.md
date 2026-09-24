# Contributing

Thanks for considering a contribution to Vocal Isolator!

## Setup

```bash
uv sync
uv run python app.py
```

See the [README](README.md) for the full setup, including the optional Audio Separator engine and environment variables.

## Making changes

1. Fork the repo and create a branch from `main`.
2. Keep changes focused — separate unrelated fixes into separate PRs.
3. Test the change locally (upload a short audio clip through the web UI or `POST /api/separate`) before opening a PR.
4. Open a pull request describing what changed and why.

## Reporting issues

Please include:

- Steps to reproduce
- Expected vs. actual behavior
- Python version, OS, and whether you're using Demucs or Audio Separator
- Relevant logs or stack traces (redact any file paths, API keys, or bucket names)
