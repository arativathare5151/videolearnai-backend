"""
=============================================================
  services/ffmpeg_service.py  –  Extract audio with FFmpeg
=============================================================
WHAT IT DOES
  extract_audio(video_bytes) → WAV bytes (16 kHz mono PCM)

WHY WAV 16 kHz?
  IBM Watson STT works best with:
    • WAV or FLAC container
    • 16 000 Hz sample rate
    • Mono channel
    • 16-bit PCM

DEPENDENCY
  ffmpeg must be installed on the server.
  Railway → add it in Dockerfile or via nixpacks.toml (see deploy notes).
=============================================================
"""

import io
import logging
import subprocess
import tempfile
import os

logger = logging.getLogger(__name__)


def extract_audio(video_bytes: bytes) -> bytes:
    """
    Convert raw video bytes → WAV audio bytes (16 kHz, mono, PCM s16le).

    Steps
    -----
    1. Write video bytes to a temp file  (ffmpeg needs seekable input)
    2. Run ffmpeg to produce WAV in memory via stdout
    3. Return the WAV bytes

    Raises
    ------
    RuntimeError if ffmpeg exits with a non-zero code.
    """
    # Write video to a temporary file
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp_video:
        tmp_video.write(video_bytes)
        tmp_video_path = tmp_video.name

    try:
        cmd = [
            "ffmpeg",
            "-y",                        # overwrite without asking
            "-i", tmp_video_path,        # input file
            "-vn",                       # drop video stream
            "-acodec", "pcm_s16le",      # PCM 16-bit little-endian
            "-ar", "16000",              # 16 kHz sample rate
            "-ac", "1",                  # mono
            "-f", "wav",                 # WAV container
            "pipe:1",                    # output to stdout
        ]

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=300,                 # 5 min max for long videos
        )

        if result.returncode != 0:
            err = result.stderr.decode("utf-8", errors="replace")
            logger.error(f"FFmpeg error:\n{err}")
            raise RuntimeError(f"FFmpeg failed (code {result.returncode}): {err[-500:]}")

        wav_bytes = result.stdout
        logger.info(f"✅ Audio extracted: {len(wav_bytes)//1024} KB WAV")
        return wav_bytes

    finally:
        # Always clean up the temp file
        os.unlink(tmp_video_path)


def get_video_duration_seconds(video_bytes: bytes) -> float:
    """
    Returns the duration of the video in seconds using ffprobe.
    Used to display video length in the UI.
    """
    with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
        tmp.write(video_bytes)
        tmp_path = tmp.name

    try:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            tmp_path,
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        duration_str = result.stdout.decode().strip()
        return float(duration_str) if duration_str else 0.0
    except Exception:
        return 0.0
    finally:
        os.unlink(tmp_path)