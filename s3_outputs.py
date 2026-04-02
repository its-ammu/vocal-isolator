"""Upload separation outputs to S3 and build URLs."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import boto3
from botocore.config import Config as BotoConfig


def _bucket() -> str | None:
    """Default bucket wmg-acestep-batch-input-test; set VOCAL_ISOLATOR_S3_BUCKET= to disable S3."""
    raw = os.environ.get("VOCAL_ISOLATOR_S3_BUCKET")
    if raw is not None:
        b = raw.strip()
        return b or None
    return "wmg-acestep-batch-input-test"


def s3_enabled() -> bool:
    return _bucket() is not None


def _prefix() -> str:
    p = os.environ.get("VOCAL_ISOLATOR_S3_PREFIX", "vocal-isolator").strip().strip("/")
    return p


def _region() -> str:
    return (
        os.environ.get("AWS_REGION")
        or os.environ.get("AWS_DEFAULT_REGION")
        or "us-east-1"
    )


def _expires_seconds() -> int:
    try:
        return int(os.environ.get("VOCAL_ISOLATOR_S3_PRESIGN_EXPIRES", "604800"))
    except ValueError:
        return 604800


def upload_stems(
    job_id: str,
    vocals_path: Path,
    instrumental_path: Path,
) -> dict[str, Any]:
    """
    Upload two WAV files to S3. Returns presigned HTTPS URLs and s3:// URIs.

    Requires IAM permission s3:PutObject on the bucket (and s3:GetObject for presigned get).
    """
    bucket = _bucket()
    if not bucket:
        raise RuntimeError("S3 bucket not configured")

    prefix = _prefix()
    base_key = f"{prefix}/{job_id}" if prefix else job_id
    keys = {
        "vocals": f"{base_key}/vocals.wav",
        "instrumental": f"{base_key}/instrumental.wav",
    }

    region = _region()
    client = boto3.client(
        "s3",
        region_name=region,
        config=BotoConfig(signature_version="s3v4"),
    )

    extra = {"ContentType": "audio/wav"}

    client.upload_file(str(vocals_path), bucket, keys["vocals"], ExtraArgs=extra)
    client.upload_file(str(instrumental_path), bucket, keys["instrumental"], ExtraArgs=extra)

    expires = _expires_seconds()
    out: dict[str, Any] = {
        "bucket": bucket,
        "prefix": base_key,
        "vocals_s3_uri": f"s3://{bucket}/{keys['vocals']}",
        "instrumental_s3_uri": f"s3://{bucket}/{keys['instrumental']}",
    }

    for stem in ("vocals", "instrumental"):
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": keys[stem]},
            ExpiresIn=expires,
        )
        out[f"{stem}_url"] = url

    out["presign_expires_seconds"] = expires
    return out
