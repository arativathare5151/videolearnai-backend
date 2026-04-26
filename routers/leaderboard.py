"""
=============================================================
  routers/leaderboard.py  –  Leaderboard endpoints
=============================================================
ENDPOINTS
  GET /leaderboard          → top 50 users ranked by score
  GET /leaderboard/{user_id} → rank + stats for a specific user
=============================================================
"""

import logging
from fastapi import APIRouter, HTTPException
from db import get_db

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("")
async def get_leaderboard(limit: int = 50):
    """
    Return top `limit` users sorted by total_score descending.
    Also fetches the user's email from the users table.
    """
    db = get_db()
    result = db.table("leaderboard") \
        .select("*, users(email, full_name)") \
        .order("total_score", desc=True) \
        .limit(limit) \
        .execute()

    rows = result.data or []

    # Add rank number (1-indexed)
    for i, row in enumerate(rows):
        row["rank"] = i + 1

    return {"leaderboard": rows}


@router.get("/{user_id}")
async def get_user_rank(user_id: str):
    """Return the leaderboard row for a specific user."""
    db = get_db()
    result = db.table("leaderboard") \
        .select("*, users(email, full_name)") \
        .eq("user_id", user_id) \
        .single() \
        .execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="User not on leaderboard yet")

    # Calculate rank by counting users with higher scores
    rank_result = db.table("leaderboard") \
        .select("user_id", count="exact") \
        .gt("total_score", result.data["total_score"]) \
        .execute()

    rank = (rank_result.count or 0) + 1
    return {**result.data, "rank": rank}