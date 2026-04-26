"""
=============================================================
  services/cos_service.py  –  IBM Cloud Object Storage
=============================================================
WHAT IT DOES
  • upload_video_to_cos()  – streams the file to IBM COS
  • get_presigned_url()    – returns a 1-hour download URL
  • delete_object()        – removes a file (cleanup)

DEPENDENCY
  pip install ibm-cos-sdk
=============================================================
"""

import io
import logging
import uuid
from pathlib import Path

import ibm_boto3
from ibm_botocore.client import Config, ClientError

from config import settings

logger = logging.getLogger(__name__)

# ── Singleton COS client ──────────────────────────────────
_cos_client = None


def _get_cos():
    global _cos_client
    if _cos_client is None:
        _cos_client = ibm_boto3.client(
            "s3",
            ibm_api_key_id=settings.IBM_COS_API_KEY,
            ibm_service_instance_id=settings.IBM_COS_INSTANCE_ID,
            config=Config(signature_version="oauth"),
            endpoint_url=settings.IBM_COS_ENDPOINT,
        )
        logger.info("✅ IBM COS client initialised")
    return _cos_client


# ─────────────────────────────────────────────────────────
def upload_video_to_cos(file_bytes: bytes, original_filename: str) -> str:
    """
    Upload video bytes to IBM COS.

    Returns
    -------
    str
        The COS object key (used to build download URLs later).
    """
    ext = Path(original_filename).suffix  # e.g. ".mp4"
    object_key = f"videos/{uuid.uuid4().hex}{ext}"

    cos = _get_cos()
    cos.put_object(
        Bucket=settings.IBM_COS_BUCKET,
        Key=object_key,
        Body=file_bytes,
        ContentType=_content_type(ext),
    )
    logger.info(f"✅ Uploaded {object_key} to COS ({len(file_bytes)//1024} KB)")
    return object_key


def get_presigned_url(object_key: str, expiry_seconds: int = 3600) -> str:
    """Return a temporary signed URL valid for `expiry_seconds` (default 1 h)."""
    cos = _get_cos()
    url = cos.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.IBM_COS_BUCKET, "Key": object_key},
        ExpiresIn=expiry_seconds,
    )
    return url


def download_from_cos(object_key: str) -> bytes:
    """Download an object and return its raw bytes."""
    cos = _get_cos()
    response = cos.get_object(Bucket=settings.IBM_COS_BUCKET, Key=object_key)
    return response["Body"].read()


def delete_object(object_key: str) -> None:
    """Delete an object from COS (e.g. after processing audio)."""
    cos = _get_cos()
    cos.delete_object(Bucket=settings.IBM_COS_BUCKET, Key=object_key)
    logger.info(f"🗑️  Deleted {object_key} from COS")


# ── helpers ───────────────────────────────────────────────
def _content_type(ext: str) -> str:
    mapping = {
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".avi": "video/x-msvideo",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
    }
    return mapping.get(ext.lower(), "application/octet-stream")