from datetime import datetime
from aiogram import Router, F
from aiogram.filters import CommandStart, Command
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

        # Birinchi topic Nazariy har doim ochiq
        await _unlock_first_topic(session, user.id)
        # Nazariy done bo'lgan topiclar uchun Amaliy ni tekshirib ochamiz
        await _sync_amaliy_unlocks(session, user.id)
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
        # Yangi user — birinchi testni och
        session.add(UserProgress(
            user_id=user_id,
            topic_id=first_topic.id,
            type="nazariy",
            status="open",
        ))
    elif existing.status == "locked":
        # Birinchi test hech qachon locked bo'lmasligi kerak
        existing.status = "open"


async def _sync_amaliy_unlocks(session, user_id: int):
    """Nazariy done bo'lgan har bir topic uchun Amaliy ni ochiq qilib qo'yadi."""
    all_progress = (await session.scalars(
        select(UserProgress).where(UserProgress.user_id == user_id)
    )).all()
    progress_map = {(p.topic_id, p.type): p for p in all_progress}

    topics = (await session.scalars(
        select(Topic).where(Topic.is_active == True)
    )).all()

    for topic in topics:
        naz = progress_map.get((topic.id, "nazariy"))
        aml = progress_map.get((topic.id, "amaliy"))

        if naz and naz.status == "done":
            if not aml:
                session.add(UserProgress(
                    user_id=user_id,
                    topic_id=topic.id,
                    type="amaliy",
                    status="open",
                ))
            elif aml.status == "locked":
                aml.status = "open"


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

        # Amaliy faqat Nazariy done bo'lgandan keyin ochiladi
        if naz_status != "done" and aml_status not in ("done",):
            aml_status = "locked"

        naz_icon = "✅" if naz_status == "done" else "🔓" if naz_status == "open" else "🔒"
        aml_icon = "✅" if aml_status == "done" else "🔓" if aml_status == "open" else "⏳" if aml_status == "waiting" else "🔒"

        def _cb(status, topic_id, test_type):
            if status == "open":
                return f"start_test:{topic_id}:{test_type}"
            if status == "done":
                return "already_done"
            if status == "waiting":
                return "waiting"
            return "locked"

        # Har bir test alohida qatorda — mobilda accidentally bosmaslik uchun
        buttons.append([InlineKeyboardButton(
            text=f"{naz_icon} {topic.title} — Nazariy",
            callback_data=_cb(naz_status, topic.id, "nazariy"),
        )])
        buttons.append([InlineKeyboardButton(
            text=f"{aml_icon} {topic.title} — Amaliy",
            callback_data=_cb(aml_status, topic.id, "amaliy"),
        )])

    await message.answer("📚 Darslar ro'yxati:", reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons))


@router.callback_query(F.data == "locked")
async def locked_topic(callback: CallbackQuery):
    await callback.answer("🔒 Bu test hali qulflangan!", show_alert=True)


@router.callback_query(F.data == "waiting")
async def waiting_topic(callback: CallbackQuery):
    await callback.answer("⏳ Vaqt hali kelmadi. Biroz kuting!", show_alert=True)


@router.callback_query(F.data == "already_done")
async def already_done(callback: CallbackQuery):
    await callback.answer("✅ Bu testni allaqachon o'tdingiz!", show_alert=True)


@router.message(Command("help"))
async def help_command(message: Message):
    await message.answer(
        "📖 <b>Bot qo'llanmasi</b>\n\n"
        "🔸 /start — Botni ishga tushirish\n"
        "🔸 /help — Ushbu yordam xabari\n"
        "🔸 /teacher — O'qituvchi bilan bog'lanish\n\n"
        "<b>Testlar qanday ishlaydi?</b>\n"
        "1️⃣ Har bir dars <b>Nazariy</b> va <b>Amaliy</b> testdan iborat\n"
        "2️⃣ Avval Nazariy testni ishlaysiz\n"
        "3️⃣ <b>80%</b> va undan yuqori ball olsangiz Amaliy ochiladi\n"
        "4️⃣ Amaliy o'tgandan keyin keyingi dars ochiladi\n\n"
        "<b>Ball 80% dan past bo'lsa:</b>\n"
        "❌ Dostup yopiladi\n"
        "👥 5 ta do'stingizni kanalga qo'shib, dostupni qayta ochasiz",
        parse_mode="HTML",
    )


@router.message(Command("teacher"))
async def teacher_command(message: Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="👨‍🏫 Abdurashid Yusupov",
            url="https://t.me/abdurashid_yusufov"
        )
    ]])
    await message.answer(
        "👨‍🏫 <b>O'qituvchi bilan bog'lanish</b>\n\n"
        "Savollaringiz bo'lsa, to'g'ridan-to'g'ri murojaat qilishingiz mumkin:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
