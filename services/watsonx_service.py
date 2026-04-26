"""
=============================================================
  services/watsonx_service.py  –  IBM watsonx.ai (Granite)
=============================================================
WHAT IT DOES
  summarize_transcript(transcript) → {"summary": "...", "key_topics": [...]}

MODEL
  ibm/granite-13b-instruct-v2   (best free-tier instruction-following model)

DEPENDENCY
  pip install ibm-watsonx-ai
=============================================================
"""

import json
import logging
import re

from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from ibm_watsonx_ai.metanames import GenTextParamsMetaNames as GenParams

from config import settings

logger = logging.getLogger(__name__)

_model = None


def _get_model() -> ModelInference:
    global _model
    if _model is None:
        credentials = Credentials(
            url=settings.IBM_WATSONX_URL,
            api_key=settings.IBM_WATSONX_API_KEY,
        )
        _model = ModelInference(
            model_id="ibm/granite-13b-instruct-v2",
            credentials=credentials,
            project_id=settings.IBM_WATSONX_PROJECT_ID,
            params={
                GenParams.MAX_NEW_TOKENS: 800,
                GenParams.MIN_NEW_TOKENS: 100,
                GenParams.TEMPERATURE: 0.3,      # lower = more factual
                GenParams.REPETITION_PENALTY: 1.1,
            },
        )
        logger.info("✅ IBM watsonx.ai model initialised")
    return _model


# ── Prompt templates ──────────────────────────────────────
_SUMMARY_PROMPT = """You are an expert educational content summarizer.

Below is a transcript from an educational video. 
Your task:
1. Write a clear, concise SUMMARY (150–250 words) that captures the main ideas.
2. List exactly 5 KEY TOPICS covered in the video (one per line, starting with "- ").

Respond ONLY in this exact JSON format (no extra text):
{{
  "summary": "...",
  "key_topics": ["topic1", "topic2", "topic3", "topic4", "topic5"]
}}

TRANSCRIPT:
{transcript}

JSON RESPONSE:"""


def summarize_transcript(transcript: str) -> dict:
    """
    Call watsonx.ai Granite to summarize the transcript.

    Parameters
    ----------
    transcript : str
        Full text from Watson STT.

    Returns
    -------
    dict with keys: "summary" (str), "key_topics" (list[str])
    """
    # Truncate transcript if very long (Granite has context limits)
    max_chars = 8000
    if len(transcript) > max_chars:
        transcript = transcript[:max_chars] + "… [truncated]"
        logger.warning("Transcript truncated to 8000 chars for watsonx.ai")

    model = _get_model()
    prompt = _SUMMARY_PROMPT.format(transcript=transcript)

    logger.info("📤 Sending transcript to watsonx.ai for summarization …")
    response = model.generate_text(prompt=prompt)
    logger.info("✅ watsonx.ai response received")

    return _parse_json_response(response, fallback_transcript=transcript)


def _parse_json_response(raw: str, fallback_transcript: str) -> dict:
    """
    Try to parse JSON from the model response.
    If it fails, return a best-effort fallback so the pipeline doesn't crash.
    """
    # Strip any markdown fences the model might add
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    # Find the first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            return {
                "summary": data.get("summary", "Summary not available."),
                "key_topics": data.get("key_topics", []),
            }
        except json.JSONDecodeError:
            pass

    logger.warning("Could not parse JSON from watsonx.ai – using fallback")
    # Fallback: return raw text as summary
    return {
        "summary": raw.strip() or "Summary could not be generated.",
        "key_topics": [],
    }