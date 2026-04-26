"""
=============================================================
  routers/quiz.py  –  Quiz endpoints
=============================================================
ENDPOINTS
  GET  /quiz/{quiz_id}        → get quiz with all questions
  POST /quiz/submit           → submit answers, calculate score, update leaderboard
  GET  /quiz/attempts/{user_id} → get user's quiz history
=============================================================
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


# ── Request / Response models ─────────────────────────────
class SubmitQuizRequest(BaseModel):
    quiz_id: str
    user_id: str
    video_id: str
    answers: list[str]      # list of selected option strings, one per question
    time_taken_seconds: int = 0


# ──────────────────────────────────────────────────────────
# 1.  GET QUIZ WITH QUESTIONS
# ──────────────────────────────────────────────────────────
@router.get("/{quiz_id}")
async def get_quiz(quiz_id: str):
    """
    Return the quiz header + all questions.
    Note: correct_answer is included so the frontend can show
    answers after submission. In a production app you would
    serve correct answers only after submission.
    """
    db = get_db()

    # Quiz header
    quiz_result = db.table("quizzes").select("*").eq("id", quiz_id).single().execute()
    if not quiz_result.data:
        raise HTTPException(status_code=404, detail="Quiz not found")

    quiz = quiz_result.data

    # Questions (ordered)
    q_result = db.table("quiz_questions") \
        .select("*") \
        .eq("quiz_id", quiz_id) \
        .order("order_index") \
        .execute()

    quiz["questions"] = q_result.data or []
    return quiz


# ──────────────────────────────────────────────────────────
# 2.  SUBMIT QUIZ
# ──────────────────────────────────────────────────────────
@router.post("/submit")
async def submit_quiz(payload: SubmitQuizRequest):
    """
    Score the quiz and save the attempt.

    Logic:
    ------
    1. Fetch all questions for quiz_id (with correct_answer)
    2. Compare each submitted answer to correct_answer
    3. Calculate percentage score
    4. Save to quiz_attempts table
    5. Update leaderboard (call the Supabase RPC)
    6. Return detailed result (which questions were correct/wrong)
    """
    db = get_db()

    # Fetch questions
    q_result = db.table("quiz_questions") \
        .select("*") \
        .eq("quiz_id", payload.quiz_id) \
        .order("order_index") \
        .execute()

    questions = q_result.data or []
    if not questions:
        raise HTTPException(status_code=404, detail="No questions found for this quiz")

    # Grade answers
    if len(payload.answers) != len(questions):
        raise HTTPException(
            status_code=400,
            detail=f"Expected {len(questions)} answers, got {len(payload.answers)}",
        )

    results = []
    correct_count = 0
    for q, submitted_answer in zip(questions, payload.answers):
        is_correct = submitted_answer.strip() == q["correct_answer"].strip()
        if is_correct:
            correct_count += 1
        results.append({
            "question_id": q["id"],
            "question_text": q["question_text"],
            "submitted_answer": submitted_answer,
            "correct_answer": q["correct_answer"],
            "explanation": q["explanation"],
            "is_correct": is_correct,
        })

    total = len(questions)
    score_percent = round((correct_count / total) * 100)

    # Save to quiz_attempts
    attempt = db.table("quiz_attempts").insert({
        "user_id": payload.user_id,
        "quiz_id": payload.quiz_id,
        "video_id": payload.video_id,
        "score": score_percent,
        "correct_count": correct_count,
        "total_questions": total,
        "time_taken_seconds": payload.time_taken_seconds,
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    attempt_id = attempt.data[0]["id"] if attempt.data else None

    # Update leaderboard via Supabase RPC
    try:
        db.rpc("update_leaderboard", {
            "p_user_id": payload.user_id,
            "p_score": score_percent,
        }).execute()
        logger.info(f"✅ Leaderboard updated for user {payload.user_id}")
    except Exception as e:
        logger.warning(f"Leaderboard update failed (non-critical): {e}")

    logger.info(f"✅ Quiz submitted: {correct_count}/{total} = {score_percent}%")
    return {
        "success": True,
        "attempt_id": attempt_id,
        "score_percent": score_percent,
        "correct_count": correct_count,
        "total_questions": total,
        "results": results,
    }


# ──────────────────────────────────────────────────────────
# 3.  GET USER'S QUIZ ATTEMPTS
# ──────────────────────────────────────────────────────────
@router.get("/attempts/{user_id}")
async def get_user_attempts(user_id: str):
    """Return all quiz attempts for a user (for history / My Videos stats)."""
    db = get_db()
    result = db.table("quiz_attempts") \
        .select("*, quizzes(title), videos(title)") \
        .eq("user_id", user_id) \
        .order("submitted_at", desc=True) \
        .execute()

    return {"attempts": result.data or []}