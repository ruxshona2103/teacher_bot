from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from sqlalchemy import select

from db import Session
from models.models import User, Notification, Invite, UserProgress
from config import CHANNEL_LINK, REMINDER_HOURS, UNLOCK_HOURS, REQUIRED_INVITES

scheduler = AsyncIOScheduler()


def start_scheduler(bot: Bot):
    scheduler.add_job(check_pending_notifications, "interval", minutes=10, args=[bot])
    scheduler.start()


async def schedule_notifications(tg_id: int, passed: bool):
    now = datetime.utcnow()

    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == tg_id))

        if passed:
            # 3 — O'tdi (darhol)
            session.add(Notification(user_id=user.id, type="passed_now", scheduled_at=now))
            # 4 — O'tdi (24 soatdan keyin eslatma)
            session.add(Notification(user_id=user.id, type="passed_reminder", scheduled_at=now + timedelta(hours=REMINDER_HOURS)))
            # 5 — Dostup ochildi (48 soatdan keyin)
            session.add(Notification(user_id=user.id, type="unlocked", scheduled_at=now + timedelta(hours=UNLOCK_HOURS)))
        else:
            # 1 — O'tmadi (darhol)
            session.add(Notification(user_id=user.id, type="failed_now", scheduled_at=now))
            # 2 — O'tmadi (24 soatdan keyin eslatma)
            session.add(Notification(user_id=user.id, type="failed_reminder", scheduled_at=now + timedelta(hours=REMINDER_HOURS)))

        await session.commit()


async def check_pending_notifications(bot: Bot):
    now = datetime.utcnow()

    async with Session() as session:
        pending = (await session.scalars(
            select(Notification).where(
                Notification.sent_at == None,
                Notification.scheduled_at <= now,
            )
        )).all()

        for notif in pending:
            user = await session.get(User, notif.user_id)
            await _send_notification(bot, user, notif, session)
            notif.sent_at = datetime.utcnow()

        await session.commit()


async def _send_notification(bot: Bot, user: User, notif: Notification, session):
    tg_id = user.tg_id

    if notif.type == "failed_now":
        invite_count = await _count_invites(session, user.id)
        remaining = REQUIRED_INVITES - invite_count
        await bot.send_message(
            tg_id,
            f"❌ Siz testdan o'ta olmadingiz.\n\n"
            f"Dostupni qayta ochish uchun {remaining} ta do'stingizni kanalga qo'shing:\n"
            f"{CHANNEL_LINK}"
        )

    elif notif.type == "failed_reminder":
        invite_count = await _count_invites(session, user.id)
        if invite_count >= REQUIRED_INVITES:
            return
        remaining = REQUIRED_INVITES - invite_count
        await bot.send_message(
            tg_id,
            f"⏰ Eslatma! Hali {remaining} ta do'st qo'shishingiz kerak.\n"
            f"Kanal: {CHANNEL_LINK}"
        )

    elif notif.type == "passed_now":
        await bot.send_message(
            tg_id,
            f"🎉 Tabriklaymiz! Testdan o'tdingiz!\n\n"
            f"Keyingi dars {UNLOCK_HOURS} soatdan keyin ochiladi."
        )

    elif notif.type == "passed_reminder":
        await bot.send_message(
            tg_id,
            f"📚 Eslatma! Keyingi darsga {REMINDER_HOURS} soat qoldi.\n"
            f"Tayyorlanib boring!"
        )

    elif notif.type == "unlocked":
        await bot.send_message(
            tg_id,
            f"🔓 Keyingi dars ochildi! Hoziroq ishlashingiz mumkin.\n"
            f"/start buyrug'ini bosing."
        )


async def _count_invites(session, user_id: int) -> int:
    invites = (await session.scalars(
        select(Invite).where(Invite.user_id == user_id)
    )).all()
    return len(invites)


async def check_invite_and_unlock(bot: Bot, user_tg_id: int, invited_tg_id: int):
    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == user_tg_id))
        if not user:
            return

        existing = await session.scalar(
            select(Invite).where(
                Invite.user_id == user.id,
                Invite.invited_tg_id == invited_tg_id,
            )
        )
        if existing:
            return

        session.add(Invite(user_id=user.id, invited_tg_id=invited_tg_id))
        await session.flush()

        invite_count = await _count_invites(session, user.id)
        if invite_count >= REQUIRED_INVITES:
            failed_progress = (await session.scalars(
                select(UserProgress).where(
                    UserProgress.user_id == user.id,
                    UserProgress.status == "failed",
                )
            )).all()

            for p in failed_progress:
                p.status = "open"

            await session.commit()
            await bot.send_message(
                user_tg_id,
                f"✅ {REQUIRED_INVITES} ta do'st qo'shdingiz! Dostup qayta ochildi.\n"
                f"/start buyrug'ini bosing."
            )
        else:
            await session.commit()
