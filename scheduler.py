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
    
    # Hozirgi vaqtdan roppa-rosa 30 daqiqa keyingi vaqtni olamiz
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

        # 2. 30 DAQIQALIK MUKAMMAL ESLATMA (Rasmdagi dizayn asosida)
        # Jadvalni har bir dars bloklariga bo'lamiz
        blocks = schedule_text.split('\n\n')
        
        for block in blocks:
            # Blok ichidan darsning boshlanish vaqtini qidiramiz
            time_match = re.search(r'\[(\d{2}:\d{2})\s*-', block)
            
            if time_match and time_match.group(1) == target_time_str:
                # Agar vaqt mos kelsa, kerakli ma'lumotlarni matndan sug'urib olamiz
                start_time = target_time_str
                
                juftlik_match = re.search(r'(\d+-juftlik)', block)
                juftlik = juftlik_match.group(1) if juftlik_match else ""
                
                end_time_match = re.search(r'-\s*(\d{2}:\d{2})\]', block)
                end_time = end_time_match.group(1) if end_time_match else ""
                
                turi_match = re.search(r'•\s*.\s*\[(.*?)\]', block)
                dars_turi = turi_match.group(1).strip() if turi_match else "Mavjud emas"
                
                fan_match = re.search(r'Fan:\s*(.+)', block, re.IGNORECASE)
                fan = fan_match.group(1).strip() if fan_match else "Mavjud emas"
                
                oqituvchi_match = re.search(r'O[\'‘`’]qituvchi:\s*(.+)', block, re.IGNORECASE)
                oqituvchi = oqituvchi_match.group(1).strip() if oqituvchi_match else "Mavjud emas"
                
                auditoriya_match = re.search(r'Auditoriya:\s*(.+)', block, re.IGNORECASE)
                auditoriya = auditoriya_match.group(1).strip() if auditoriya_match else "Mavjud emas"
                
                # Eslatma dizayni
                eslatma_matni = (
                    "⏰ <b>Dars boshlanishiga 30 daqiqa qoldi!</b>\n\n"
                    f"👥 <b>Guruh:</b> {group_name}\n"
                    f"⏱ <b>Vaqt:</b> {juftlik} [{start_time} - {end_time}] • 📗 [{dars_turi}]\n"
                    f"📖 <b>Fan:</b> {fan}\n"
                    f"👨‍🏫 <b>O'qituvchi:</b> {oqituvchi}\n"
                    f"📍 <b>Auditoriya:</b> {auditoriya}\n\n"
                    "<i>Darsga kechikmang! Muvaffaqiyatli dars tilaymiz! ✨</i>"
                )
                
                # Shu guruhdagi barcha talabalarga jo'natamiz
                users = await get_users_by_group(group_name)
                for uid in users:
                    try:
                        await bot.send_message(uid, eslatma_matni, parse_mode="HTML")
                    except Exception:
                        pass
                        
        # Telegram API ni zo'riqtirib qo'ymaslik uchun kichik pauza
        await asyncio.sleep(1)

def start_scheduler(bot):
    scheduler = AsyncIOScheduler(timezone=pytz.timezone('Asia/Tashkent'))
    # Har 1 daqiqada tekshiruv ishga tushadi
    scheduler.add_job(check_schedules, 'interval', minutes=1, args=[bot])
    scheduler.start()
