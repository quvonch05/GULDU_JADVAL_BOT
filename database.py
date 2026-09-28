from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy import Column, Integer, BigInteger, String
from sqlalchemy import select
import asyncio

# Ma'lumotlar bazasi fayli manzili
DATABASE_URL = "postgresql+asyncpg://postgres.hctthovvcyvmsaosqtpl:Quvonch.0510@aws-0-eu-central-1.pooler.supabase.com:5432/postgres"

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
Base = declarative_base()

# Foydalanuvchilar jadvali
class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False) # Talabaning Telegram ID si
    group_name = Column(String, nullable=True) # Saqlangan guruhi (masalan: 10-26AT)

# Bazani boshlang'ich ishga tushirish (Jadvallarni yaratish)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

# Foydalanuvchini bazaga qo'shish yoki uning guruhini yangilash
async def set_user_group(telegram_id: int, group_name: str):
    async with AsyncSessionLocal() as session:
        # Baza ichidan bu foydalanuvchini qidiramiz
        result = await session.execute(User.__table__.select().where(User.telegram_id == telegram_id))
        user = result.fetchone()
        
        if user:
            # Agar oldin ro'yxatdan o'tgan bo'lsa, guruhini yangilaymiz
            await session.execute(
                User.__table__.update().where(User.telegram_id == telegram_id).values(group_name=group_name)
            )
        else:
            # Yangi foydalanuvchi bo'lsa, bazaga qo'shamiz
            new_user = User(telegram_id=telegram_id, group_name=group_name)
            session.add(new_user)
        
        await session.commit()

# Foydalanuvchining saqlangan guruhini bazadan chaqirib olish
async def get_user_group(telegram_id: int):
    async with AsyncSessionLocal() as session:
        result = await session.execute(User.__table__.select().where(User.telegram_id == telegram_id))
        user = result.fetchone()
        return user.group_name if user else None
    
# Mavjud kodlar tagidan qo'shing...

async def get_all_users_id():
    """Barcha foydalanuvchilarning ID raqamlarini ro'yxat qilib qaytaradi (Admin xabar tarqatishi uchun)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.telegram_id))
        return [row[0] for row in result.fetchall()]

async def get_active_groups():
    """Faqatgina ro'yxatdan o'tgan (kuzatilayotgan) guruhlar nomini qaytaradi (Eslatma uchun)."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.group_name).distinct())
        return [row[0] for row in result.fetchall() if row[0]]

async def get_users_by_group(group_name: str):
    """Bitta guruhga tegishli barcha talabalar ID larini qaytaradi."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(User.telegram_id).where(User.group_name == group_name))
        return [row[0] for row in result.fetchall()]
