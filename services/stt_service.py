"""
=============================================================
  services/stt_service.py  –  IBM Watson Speech-to-Text
=============================================================
WHAT IT DOES
  transcribe_audio(wav_bytes) → full transcript string

IBM Watson STT FREE TIER
  • 500 minutes/month free
  • Model used: en-US_BroadbandModel (best for lectures)

DEPENDENCY
  pip install ibm-watson
=============================================================
"""

import logging
import json

from ibm_watson import SpeechToTextV1
from ibm_cloud_sdk_core.authenticators import IAMAuthenticator

from config import settings

logger = logging.getLogger(__name__)

_stt_client = None


def _get_stt():
    global _stt_client
    if _stt_client is None:
        authenticator = IAMAuthenticator(settings.IBM_WATSON_STT_KEY)
        stt = SpeechToTextV1(authenticator=authenticator)
        stt.set_service_url(settings.IBM_WATSON_STT_URL)
        _stt_client = stt
        logger.info("✅ IBM Watson STT client initialised")
    return _stt_client


def transcribe_audio(wav_bytes: bytes) -> str:
    """
    Send WAV audio bytes to IBM Watson STT and return the full transcript.

    Parameters
    ----------
    wav_bytes : bytes
        16 kHz mono PCM WAV audio (produced by ffmpeg_service).

    Returns
    -------
    str
        Full transcript text.  Empty string if nothing recognised.
    """
    stt = _get_stt()

    logger.info(f"📤 Sending {len(wav_bytes)//1024} KB to Watson STT …")

    response = stt.recognize(
        audio=wav_bytes,
        content_type="audio/wav",
        model="en-US_BroadbandModel",   # best for clear speech / lectures
        smart_formatting=True,           # punctuation, numbers, dates
        timestamps=False,
        word_confidence=False,
        max_alternatives=1,
    ).get_result()

    # Watson returns a list of "results", each with "alternatives"
    # We concatenate all the top-1 transcripts.
    transcript_parts = []
    for result in response.get("results", []):
        alternatives = result.get("alternatives", [])
        if alternatives:
            transcript_parts.append(alternatives[0].get("transcript", ""))

    transcript = " ".join(transcript_parts).strip()
    logger.info(f"✅ Transcript received: {len(transcript)} characters")
    return transcript