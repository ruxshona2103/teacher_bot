from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
)
from sqlalchemy import select

from db import Session
from models.models import User, Topic, UserProgress
from config import ADMIN_IDS

router = Router()

ADMIN_KB = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="📤 Test yuklash"),    KeyboardButton(text="📋 Testlar ro'yxati")],
    [KeyboardButton(text="📊 Natijalar"),       KeyboardButton(text="📥 Word eksport")],
], resize_keyboard=True)


@router.message(CommandStart())
async def start(message: Message):
    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == message.from_user.id))

        if not user:
            user = User(
                tg_id=message.from_user.id,
                name=message.from_user.full_name,
                username=message.from_user.username,
            )
            session.add(user)
            await session.flush()
            await _unlock_first_topic(session, user.id)
            await session.commit()
        else:
            # Agar progress yo'q bo'lsa (topics keyinroq qo'shilgan bo'lsa) — unlock
            progress_count = await session.scalar(
                select(UserProgress).where(UserProgress.user_id == user.id)
            )
            if not progress_count:
                await _unlock_first_topic(session, user.id)
                await session.commit()

    if message.from_user.id in ADMIN_IDS:
        await message.answer("👨‍💼 Admin panel:", reply_markup=ADMIN_KB)
        return

    await show_topics(message)


async def _unlock_first_topic(session, user_id: int):
    first_topic = await session.scalar(
        select(Topic).where(Topic.is_active == True).order_by(Topic.order_num).limit(1)
    )
    if not first_topic:
        return
    existing = await session.scalar(
        select(UserProgress).where(
            UserProgress.user_id == user_id,
            UserProgress.topic_id == first_topic.id,
            UserProgress.type == "nazariy",
        )
    )
    if not existing:
        session.add(UserProgress(
            user_id=user_id,
            topic_id=first_topic.id,
            type="nazariy",
            status="open",
        ))


@router.message(F.text == "📚 Darslar")
async def show_topics(message: Message):
    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == message.from_user.id))
        topics = (await session.scalars(
            select(Topic).where(Topic.is_active == True).order_by(Topic.order_num)
        )).all()

        if not topics:
            await message.answer("📭 Hozircha darslar yo'q. Admin tez orada qo'shadi!")
            return

        progress_rows = (await session.scalars(
            select(UserProgress).where(UserProgress.user_id == user.id)
        )).all()

    now = datetime.utcnow()
    # (topic_id, type) → progress object
    progress_map = {(p.topic_id, p.type): p for p in progress_rows}

    def _status(topic_id, test_type):
        p = progress_map.get((topic_id, test_type))
        if not p:
            return "locked"
        # 48 soatlik kutish vaqti o'tmagan bo'lsa — hali qulflangan
        if p.status == "open" and p.unlocked_at and p.unlocked_at > now:
            return "waiting"
        return p.status

    buttons = []
    for topic in topics:
        naz_status = _status(topic.id, "nazariy")
        aml_status = _status(topic.id, "amaliy")

        # Amaliy — Nazariy done bo'lmasa hech qachon ochilmaydi
        if naz_status != "done" and aml_status not in ("done",):
            aml_status = "locked"

        naz_icon = "✅" if naz_status == "done" else "🔓" if naz_status == "open" else "🔒"
        aml_icon = "✅" if aml_status == "done" else "🔓" if aml_status == "open" else "⏳" if aml_status == "waiting" else "🔒"

        buttons.append([
            InlineKeyboardButton(
                text=f"{naz_icon} {topic.title} — Nazariy",
                callback_data=f"start_test:{topic.id}:nazariy" if naz_status == "open" else "locked"
            ),
            InlineKeyboardButton(
                text=f"{aml_icon} {topic.title} — Amaliy",
                callback_data=f"start_test:{topic.id}:amaliy" if aml_status == "open" else (
                    "waiting" if aml_status == "waiting" else "locked"
                )
            ),
        ])

    await message.answer("📚 Darslar ro'yxati:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "locked")
async def locked_topic(callback: CallbackQuery):
    await callback.answer("🔒 Bu test hali qulflangan!", show_alert=True)


@router.callback_query(F.data == "waiting")
async def waiting_topic(callback: CallbackQuery):
    await callback.answer("⏳ Vaqt hali kelmadi. Biroz kuting!", show_alert=True)
