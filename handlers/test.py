from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from sqlalchemy import select

from db import Session
from models.models import User, Question, UserProgress, UserResult
from services.test_service import calculate_score, unlock_next
from services.ai_service import get_ai_advice
from services.notif_service import schedule_notifications
from config import PASS_SCORE

router = Router()


class TestState(StatesGroup):
    in_progress = State()


@router.callback_query(F.data.startswith("start_test:"))
async def start_test(callback: CallbackQuery, state: FSMContext):
    _, topic_id, test_type = callback.data.split(":")
    topic_id = int(topic_id)

    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == callback.from_user.id))
        progress = await session.scalar(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.topic_id == topic_id,
                UserProgress.type == test_type,
            )
        )
        if not progress or progress.status != "open":
            await callback.answer("🔒 Bu test hozir mavjud emas!", show_alert=True)
            return

        questions = (await session.scalars(
            select(Question).where(
                Question.topic_id == topic_id,
                Question.type == test_type,
            )
        )).all()

    if not questions:
        await callback.answer("❌ Savollar topilmadi!", show_alert=True)
        return

    await state.set_state(TestState.in_progress)
    await state.set_data({
        "topic_id": topic_id,
        "test_type": test_type,
        "questions": [q.id for q in questions],
        "answers": {},
        "current": 0,
    })

    await callback.message.delete()
    await send_question(callback.message, state, questions[0], current=0, total=len(questions))


async def send_question(message, state: FSMContext, question: Question, current: int, total: int):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="A", callback_data="answer:A"),
        InlineKeyboardButton(text="B", callback_data="answer:B"),
        InlineKeyboardButton(text="C", callback_data="answer:C"),
        InlineKeyboardButton(text="D", callback_data="answer:D"),
    ]])

    text = (
        f"📝 Savol {current + 1} dan {total} ta\n\n"
        f"{question.text}\n\n"
        f"🅰 {question.option_a}\n"
        f"🅱 {question.option_b}\n"
        f"🅲 {question.option_c}\n"
        f"🅳 {question.option_d}"
    )

    if question.image_file_id:
        await message.answer_photo(question.image_file_id, caption=text, reply_markup=keyboard)
    else:
        await message.answer(text, reply_markup=keyboard)


@router.callback_query(F.data.startswith("answer:"), TestState.in_progress)
async def handle_answer(callback: CallbackQuery, state: FSMContext):
    chosen = callback.data.split(":")[1]
    data = await state.get_data()

    current = data["current"]
    questions_ids = data["questions"]
    answers = data["answers"]
    answers[str(questions_ids[current])] = chosen

    await callback.answer("✅ Javob qabul qilindi")
    await callback.message.delete()

    next_index = current + 1
    if next_index >= len(questions_ids):
        await state.update_data(answers=answers, current=next_index)
        await finish_test(callback, state)
        return

    await state.update_data(answers=answers, current=next_index)

    async with Session() as session:
        next_question = await session.get(Question, questions_ids[next_index])

    await send_question(callback.message, state, next_question, next_index, len(questions_ids))


async def finish_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.clear()

    topic_id = data["topic_id"]
    test_type = data["test_type"]
    question_ids = data["questions"]
    answers = data["answers"]

    async with Session() as session:
        user = await session.scalar(select(User).where(User.tg_id == callback.from_user.id))
        questions = (await session.scalars(
            select(Question).where(Question.id.in_(question_ids))
        )).all()

        score, wrong_questions = calculate_score(questions, answers)
        passed = score >= PASS_SCORE

        result = UserResult(
            user_id=user.id,
            topic_id=topic_id,
            type=test_type,
            score=score,
        )
        session.add(result)

        progress = await session.scalar(
            select(UserProgress).where(
                UserProgress.user_id == user.id,
                UserProgress.topic_id == topic_id,
                UserProgress.type == test_type,
            )
        )
        progress.status = "done" if passed else "failed"

        rank, total_users = await _get_rank(session, user.id, topic_id, test_type, score)
        correct_count = round(score * len(questions) / 100)

        if passed:
            await unlock_next(session, user.id, topic_id, test_type)

        await session.commit()

    status_text = "✅ O'tdingiz!" if passed else "❌ O'tmadingiz"
    result_text = (
        f"📊 Test natijasi\n\n"
        f"To'g'ri javoblar: {correct_count} / {len(questions)}\n"
        f"Ball: {score:.0f}%\n"
        f"Reyting: {rank}-o'rin / {total_users} kishi\n"
        f"Holat: {status_text}"
    )
    await callback.message.answer(result_text)

    ai_text = await get_ai_advice(wrong_questions)
    await callback.message.answer(f"🤖 AI tavsiya:\n\n{ai_text}")

    await schedule_notifications(callback.from_user.id, passed)


async def _get_rank(session, user_id: int, topic_id: int, test_type: str, score: float):
    from sqlalchemy import func
    all_results = (await session.scalars(
        select(UserResult).where(
            UserResult.topic_id == topic_id,
            UserResult.type == test_type,
        ).order_by(UserResult.score.desc())
    )).all()

    unique = {}
    for r in all_results:
        if r.user_id not in unique:
            unique[r.user_id] = r.score

    sorted_scores = sorted(unique.values(), reverse=True)
    rank = sorted_scores.index(score) + 1 if score in sorted_scores else len(sorted_scores)
    return rank, len(sorted_scores)
