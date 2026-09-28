import asyncio
import re
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import get_active_groups, get_users_by_group
from parser import get_schedule_text, search_group_id

# Jadval o'zgarishlarini tekshirish uchun vaqtinchalik xotira
_SCHEDULE_CACHE = {}

async def check_schedules(bot):
    tz = pytz.timezone('Asia/Tashkent')
    now = datetime.now(tz)
    
    # Hozirgi vaqtdan roppa-rosa 30 daqiqa keyingi vaqtni olamiz (Masalan, hozir 09:30 bo'lsa, 10:00 ni)
    target_time_str = (now + timedelta(minutes=30)).strftime("%H:%M")
    
    active_groups = await get_active_groups()
    
    for group_name in active_groups:
        group_id = await search_group_id(group_name)
        if not group_id: 
            continue
            
        # Faqat bugungi jadvalni olamiz
        schedule_text = await get_schedule_text(group_id, group_name, "bugun")
        
        if "Bunday sanada dars topilmadi" in schedule_text:
            continue

        # 1. O'ZGARISHLAR MONITORINGI
        old_schedule = _SCHEDULE_CACHE.get(group_name)
        if old_schedule and old_schedule != schedule_text:
            users = await get_users_by_group(group_name)
            for uid in users:
                try:
                    await bot.send_message(uid, f"⚠️ <b>DIQQAT! Jadvalingizda o'zgarish sezildi:</b>\n\n{schedule_text}", parse_mode="HTML")
                except Exception:
                    pass
        _SCHEDULE_CACHE[group_name] = schedule_text

        # 2. 30 DAQIQALIK ESLATMA
        # Matn ichidan vaqtlarni qidiramiz. Masalan: [10:00 - 11:20]
        start_times = re.findall(r'\[(\d{2}:\d{2}) -', schedule_text)
        
        for t in start_times:
            if t == target_time_str:
                users = await get_users_by_group(group_name)
                for uid in users:
                    try:
                        await bot.send_message(
                            uid, 
                            f"🔔 <b>Dars eslatmasi!</b>\n\nTayyorgarlik ko'ring, darsingiz boshlanishiga 30 daqiqa qoldi!\nBoshlanish vaqti: <b>{t}</b>", 
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                        
        # Saytni zo'riqtirib qo'ymaslik uchun har bir guruh orasida 1 soniya pauza
        await asyncio.sleep(1)

def start_scheduler(bot):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Tashkent'))
    # Har 1 daqiqada tekshiruv ishga tushadi
    scheduler.add_job(check_schedules, 'interval', minutes=1, args=[bot])
    scheduler.start()