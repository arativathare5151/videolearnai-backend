"""
=============================================================
  services/gemini_service.py  –  Google Gemini Quiz Generator
=============================================================
WHAT IT DOES
  generate_quiz(transcript, summary) →
    {
      "title": "...",
      "questions": [
        {
          "question": "...",
          "options": ["A", "B", "C", "D"],
          "correct_answer": "A",
          "explanation": "..."
        },
        ...
      ]
    }

MODEL
  gemini-1.5-flash  (fast, free tier: 15 req/min, 1M tokens/day)

DEPENDENCY
  pip install google-generativeai
=============================================================
"""

import json
import logging
import re

import google.generativeai as genai

from config import settings

logger = logging.getLogger(__name__)

_genai_configured = False


def _configure():
    global _genai_configured
    if not _genai_configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _genai_configured = True
        logger.info("✅ Google Gemini configured")


# ── Prompt ────────────────────────────────────────────────
_QUIZ_PROMPT = """You are an expert educational quiz creator.

Based on the TRANSCRIPT and SUMMARY below, generate exactly {n} multiple-choice questions.

Rules:
- Each question must test genuine understanding (no trick questions)
- Each question has exactly 4 options (A, B, C, D)
- Only ONE option is correct
- Options must be clearly different from each other
- Include a short explanation (1 sentence) for the correct answer

Return ONLY valid JSON in this exact format (no extra text, no markdown):
{{
  "title": "Quiz: <topic of the video>",
  "questions": [
    {{
      "question": "...",
      "options": ["option A text", "option B text", "option C text", "option D text"],
      "correct_answer": "option A text",
      "explanation": "..."
    }}
  ]
}}

SUMMARY:
{summary}

TRANSCRIPT (first 6000 chars):
{transcript}

JSON:"""


def generate_quiz(transcript: str, summary: str) -> dict:
    """
    Call Gemini to generate a quiz from the video transcript + summary.

    Returns
    -------
    dict with keys: "title" (str), "questions" (list[dict])
    Each question dict has: question, options, correct_answer, explanation
    """
    _configure()

    n = settings.QUIZ_QUESTION_COUNT
    # Truncate transcript to keep prompt within limits
    trunc_transcript = transcript[:6000]

    prompt = _QUIZ_PROMPT.format(
        n=n,
        summary=summary,
        transcript=trunc_transcript,
    )

    model = genai.GenerativeModel("gemini-1.5-flash")

    logger.info(f"📤 Sending to Gemini – generating {n} quiz questions …")
    response = model.generate_content(prompt)
    raw = response.text
    logger.info("✅ Gemini response received")

    return _parse_quiz_json(raw, n)


def _parse_quiz_json(raw: str, expected_count: int) -> dict:
    """Parse and validate the JSON returned by Gemini."""
    # Strip markdown fences
    cleaned = re.sub(r"```(?:json)?", "", raw).strip()

    # Find first {...} block
    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        logger.error("Gemini did not return valid JSON")
        return _fallback_quiz()

    try:
        data = json.loads(match.group())
        questions = data.get("questions", [])

        # Validate each question has required fields
        valid = []
        for q in questions:
            if all(k in q for k in ("question", "options", "correct_answer", "explanation")):
                if len(q["options"]) == 4:
                    valid.append(q)

        if not valid:
            logger.warning("No valid questions parsed from Gemini response")
            return _fallback_quiz()

        return {
            "title": data.get("title", "Video Quiz"),
            "questions": valid,
        }

    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f"JSON parse error: {e}")
        return _fallback_quiz()


def _fallback_quiz() -> dict:
    """Return a placeholder quiz when generation fails."""
    return {
        "title": "Quiz (generation failed – retry)",
        "questions": [],
    }