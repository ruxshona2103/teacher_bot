import asyncio
import logging

from aiogram import Bot, Dispatcher, F
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ChatMemberUpdated, BotCommand

from config import BOT_TOKEN, CHANNEL_ID
from db import init_db
from handlers import user, admin, test
from services.notif_service import start_scheduler, check_invite_and_unlock

logging.basicConfig(level=logging.INFO)

BOT_COMMANDS = [
    BotCommand(command="start",   description="Botni ishga tushirish"),
    BotCommand(command="help",    description="Yordam va qo'llanma"),
    BotCommand(command="teacher", description="O'qituvchi bilan bog'lanish"),
]


async def main():
    await init_db()

    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())

    await bot.set_my_commands(BOT_COMMANDS)

    @dp.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
    async def on_member_join(event: ChatMemberUpdated):
        if event.chat.id != CHANNEL_ID:
            return
        invited_tg_id = event.new_chat_member.user.id
        if event.invite_link and event.invite_link.creator:
            inviter_tg_id = event.invite_link.creator.id
            await check_invite_and_unlock(bot, inviter_tg_id, invited_tg_id)

    dp.include_router(user.router)
    dp.include_router(admin.router)
    dp.include_router(test.router)

    start_scheduler(bot)

    await dp.start_polling(
        bot,
        allowed_updates=dp.resolve_used_update_types(),
    )


if __name__ == "__main__":
    asyncio.run(main())
