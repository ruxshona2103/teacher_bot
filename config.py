from dotenv import load_dotenv
import os

load_dotenv()

# --- Telegram ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "").split(",")))

# --- Database ---
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///bot.db")

# --- AI ---
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# --- Kanal (jazo tizimi) ---
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))
CHANNEL_LINK = os.getenv("CHANNEL_LINK", "")

# =============================================
# BARCHA BIZNES QOIDALAR — shu yerdan o'zgartir
# =============================================
PASS_SCORE = 80          # o'tish uchun minimal foiz (%)
REQUIRED_INVITES = 5     # jazo: nechta do'st qo'shish kerak
UNLOCK_HOURS = 48        # nazariydan keyingi amaliy ochilish vaqti (soat)
REMINDER_HOURS = 24      # eslatma qayta yuborish vaqti (soat)

