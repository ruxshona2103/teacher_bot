from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from models.models import Base
from config import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False)
Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Yangi ustunlar uchun migration (mavjud DB da bo'lmasa qo'shadi)
        try:
            await conn.execute(text("ALTER TABLE questions ADD COLUMN image_file_id VARCHAR(255)"))
        except Exception:
            pass
