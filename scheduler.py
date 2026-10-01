import asyncio
import re
from datetime import datetime, timedelta
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot

from database import get_active_groups, get_users_by_group, get_all_users_id, get_user_group
from parser import get_schedule_text, search_group_id

# Jadval o'zgarishlarini tekshirish uchun vaqtinchalik xotira
_SCHEDULE_CACHE = {}

async def send_daily_briefing(bot: Bot):
    """Har kuni ertalab soat 07:00 da foydalanuvchilarga bugungi jadvalni yuborish"""
    users = await get_all_users_id()
    
    for user_id in users:
        group_name = await get_user_group(user_id)
        if group_name:
            group_id = await search_group_id(group_name)
            if group_id:
                schedule_text = await get_schedule_text(group_id, group_name, "bugun")
                
                # Agar jadvalda "Dam olish kuni" yoki "dars topilmadi" yozuvi bo'lmasa, xabar yuboramiz
                if "Dam olish kuni" not in schedule_text and "Bunday sanada dars topilmadi" not in schedule_text:
                    msg_text = (
                        f"🌅 <b>Xayrli tong! Bugungi dars jadvalingiz bilan tanishing:</b>\n\n"
                        f"{schedule_text}\n\n"
                        f"<i>🏃‍♂️ Darsga kechikmang, kuningiz unumli o'tsin!</i>"
                    )
                    try:
                        await bot.send_message(chat_id=user_id, text=msg_text, parse_mode="HTML")
                        await asyncio.sleep(0.05) # Spam himoyasi
                    except Exception:
                        pass

async def check_schedules(bot: Bot):
    """Jadval o'zgarishlarini tekshirish va 30 daqiqa oldin eslatma yuborish"""
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
        
        if "Bunday sanada dars topilmadi" in schedule_text or "Dam olish kuni" in schedule_text:
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

        # 2. 30 DAQIQALIK MUKAMMAL ESLATMA
        blocks = schedule_text.split('\n\n')
        
        for block in blocks:
            # Blok ichidan darsning boshlanish vaqtini qidiramiz
            time_match = re.search(r'\[(\d{2}:\d{2})\s*-', block)
            
            if time_match and time_match.group(1) == target_time_str:
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
                
                eslatma_matni = (
                    "⏰ <b>Dars boshlanishiga 30 daqiqa qoldi!</b>\n\n"
                    f"👥 <b>Guruh:</b> {group_name}\n"
                    f"⏱ <b>Vaqt:</b> {juftlik} [{start_time} - {end_time}] • 📗 [{dars_turi}]\n"
                    f"📖 <b>Fan:</b> {fan}\n"
                    f"👨‍🏫 <b>O'qituvchi:</b> {oqituvchi}\n"
                    f"📍 <b>Auditoriya:</b> {auditoriya}\n\n"
                    "<i>Darsga kechikmang! Muvaffaqiyatli dars tilaymiz! ✨</i>"
                )
                
                users = await get_users_by_group(group_name)
                for uid in users:
                    try:
                        await bot.send_message(uid, eslatma_matni, parse_mode="HTML")
                    except Exception:
                        pass
                        
        # Telegram API ni zo'riqtirib qo'ymaslik uchun kichik pauza
        await asyncio.sleep(1)

def start_scheduler(bot: Bot):
    tz = pytz.timezone('Asia/Tashkent')
    scheduler = AsyncIOScheduler(timezone=tz)
    
    # 1. Har kuni ertalab 07:00 da dayjest yuborish
    scheduler.add_job(send_daily_briefing, trigger='cron', hour=7, minute=0, args=[bot])
    
    # 2. Har 1 daqiqada jadval o'zgarishi va darsga 30 daqiqa qolganini tekshirish
    scheduler.add_job(check_schedules, 'interval', minutes=1, args=[bot])
    
    scheduler.start()
