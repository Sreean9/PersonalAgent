"""
tools/discovery_tools.py – What's New & Interest Explorer tools.

'What's New' is driven by admin-managed Announcements in the DB.
'Explore Interest' uses the LLM itself (via the caller) to generate
curated content recommendations based on stored user topics.
"""

from __future__ import annotations

from typing import Optional, List

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from models import Announcement, UserInterest


# ─────────────────────────────────────────────────────────────────────────────
#  What's New
# ─────────────────────────────────────────────────────────────────────────────

async def get_whats_new(
    db: AsyncSession,
    category: Optional[str] = None,
    limit: int = 5,
) -> dict:
    """
    Return the latest announcements / what's new items.

    Args:
        category: Optional filter – 'feature', 'offer', or 'general'.
        limit: Maximum number of items to return (default 5).

    Returns:
        A list of announcement dicts.
    """
    stmt = select(Announcement).where(Announcement.is_active == True)  # noqa: E712
    if category:
        stmt = stmt.where(Announcement.category == category.lower())
    stmt = stmt.order_by(Announcement.created_at.desc()).limit(min(limit, 10))

    result = await db.execute(stmt)
    announcements = result.scalars().all()

    return {
        "announcements": [
            {
                "id": a.id,
                "title": a.title,
                "body": a.body,
                "category": a.category,
                "created_at": a.created_at.isoformat(),
            }
            for a in announcements
        ],
        "count": len(announcements),
    }


# ─────────────────────────────────────────────────────────────────────────────
#  User Interests
# ─────────────────────────────────────────────────────────────────────────────

async def get_user_interests(db: AsyncSession, user_id: str) -> dict:
    """
    Fetch the user's saved interest topics.

    Returns:
        A list of interest dicts with 'topic' and 'weight'.
    """
    result = await db.execute(
        select(UserInterest)
        .where(UserInterest.user_id == user_id)
        .order_by(UserInterest.weight.desc())
    )
    interests = result.scalars().all()
    return {
        "interests": [{"id": i.id, "topic": i.topic, "weight": i.weight} for i in interests],
        "count": len(interests),
    }


async def update_user_interests(
    db: AsyncSession,
    user_id: str,
    topics: List[str],
) -> dict:
    """
    Replace the user's interest topics with the provided list.

    Args:
        topics: List of interest topics (e.g. ['cricket', 'cooking', 'finance']).

    Returns:
        The saved interests.
    """
    # Remove existing
    await db.execute(delete(UserInterest).where(UserInterest.user_id == user_id))

    # Insert new
    new_interests = [
        UserInterest(user_id=user_id, topic=t.strip().lower(), weight=1.0)
        for t in topics
        if t.strip()
    ]
    db.add_all(new_interests)
    await db.commit()

    return {
        "success": True,
        "interests": [{"topic": i.topic} for i in new_interests],
        "message": f"Updated {len(new_interests)} interest(s).",
    }


async def explore_interest(
    db: AsyncSession,
    user_id: str,
    topic: Optional[str] = None,
) -> dict:
    """
    Return the user's interest topics so the LLM can generate
    personalised recommendations or exploration content.

    When 'topic' is provided, it narrows the focus; otherwise returns
    all saved interests so the LLM can pick what to explore.

    Args:
        topic: Optional specific topic to explore (e.g. 'cricket').

    Returns:
        A dict with interests and a prompt hint for the LLM.
    """
    result = await db.execute(
        select(UserInterest)
        .where(UserInterest.user_id == user_id)
        .order_by(UserInterest.weight.desc())
        .limit(10)
    )
    interests = result.scalars().all()
    topics = [i.topic for i in interests]

    if topic:
        # Boost weight of the requested topic for future personalisation
        for interest in interests:
            if interest.topic == topic.lower().strip():
                interest.weight = min(interest.weight + 0.5, 10.0)
        await db.commit()

    focus = topic if topic else (topics[0] if topics else "general knowledge")

    return {
        "focus_topic": focus,
        "all_interests": topics,
        "instruction": (
            f"The user wants to explore '{focus}'. "
            f"Their other interests are: {', '.join(topics)}. "
            "Please provide an engaging, informative 3–5 point overview or fun facts "
            "about this topic. Keep it conversational and tailored to their profile."
        ),
    }
