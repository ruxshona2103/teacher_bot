from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Question, UserProgress, Topic
from config import PASS_SCORE, UNLOCK_HOURS


def calculate_score(questions: list[Question], answers: dict) -> tuple[float, list[Question]]:
    correct = 0
    wrong = []

    for q in questions:
        if answers.get(str(q.id)) == q.correct:
            correct += 1
        else:
            wrong.append(q)

    score = (correct / len(questions)) * 100 if questions else 0
    return round(score, 1), wrong


async def unlock_next(session: AsyncSession, user_id: int, topic_id: int, test_type: str):
    if test_type == "nazariy":
        await _unlock(session, user_id, topic_id, "amaliy")
    elif test_type == "amaliy":
        await _unlock_next_topic(session, user_id, topic_id)


async def _unlock(session: AsyncSession, user_id: int, topic_id: int, test_type: str):
    existing = await session.scalar(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.topic_id == topic_id,
            UserProgress.type == test_type,
        )
    )
    if existing:
        existing.status = "open"
        existing.unlocked_at = datetime.utcnow()
    else:
        session.add(UserProgress(
            user_id=user_id,
            topic_id=topic_id,
            type=test_type,
            status="open",
            unlocked_at=datetime.utcnow(),
        ))


async def _unlock_next_topic(session: AsyncSession, user_id: int, current_topic_id: int):
    current = await session.get(Topic, current_topic_id)
    next_topic = await session.scalar(
        select(Topic).where(
            Topic.order_num > current.order_num,
            Topic.is_active == True,
        ).order_by(Topic.order_num).limit(1)
    )
    if not next_topic:
        return

    unlock_time = datetime.utcnow() + timedelta(hours=UNLOCK_HOURS)

    existing = await session.scalar(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.topic_id == next_topic.id,
            UserProgress.type == "nazariy",
        )
    )
    if existing:
        existing.status = "open"
        existing.unlocked_at = unlock_time
    else:
        session.add(UserProgress(
            user_id=user_id,
            topic_id=next_topic.id,
            type="nazariy",
            status="open",
            unlocked_at=unlock_time,
        ))
