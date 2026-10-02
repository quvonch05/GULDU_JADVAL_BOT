import asyncio
import logging
import os
from aiohttp import web
from datetime import datetime, timedelta
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import init_db, set_user_group, get_all_users_id, get_user_group, get_active_groups
from parser import (
    get_faculties, get_forms, get_courses, get_groups, 
    get_schedule_text, search_group_id, search_teacher_schedule, get_rooms_status_by_faculty,
    get_teachers_by_faculty, search_teacher_by_keyword, get_all_teachers_stats
)
from scheduler import start_scheduler
import parser 

# DIQQAT: BotFather'dan olingan YANGI tokenni kiritishni unutmang!
BOT_TOKEN = "8923062582:AAF8Vl3F0wTufeF3uZ8XEFbrpvu21XUbQy4"
ADMIN_IDS = [1686406789] 

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

class QidiruvHolati(StatesGroup):
    guruh_kutilmoqda = State()
    oqituvchi_kutilmoqda = State()

# --- ASOSIY MENYU CHIZUVCHI FUNKSIYA ---
async def send_main_menu(event: Message | CallbackQuery, user_id: int, first_name: str, state: FSMContext):
    await state.clear() 
    saved_group = await get_user_group(user_id)
    
    text = (
        f"Assalomu alaykum, {first_name}!\n\n"
        "🏛 <b>GulDU Dars Jadvali Tizimi</b> ✨\n"
        "<i>Guliston Davlat Universiteti rasmiy dars jadvallarini qulay kuzatib boring.</i>\n\n"
        "Kerakli bo'limni tanlang:\n"
        "• 🏢 <b>Fakultetlar bo'yicha:</b> Bosqichma-bosqich qidirish\n"
        "• 🎯 <b>Guruhni qidirish:</b> Nom bo'yicha lahzada topish\n"
        "• 👨‍🏫 <b>O'qituvchini qidirish:</b> O'qituvchilar dars jadvali"
    )
    
    if saved_group:
        text += (
            f"\n\n🌠 <b>Tanlangan guruh: {saved_group}</b>\n"
            "🔔 <i>Dars boshlanishiga 30 daqiqa qolganda va jadval o'zgarganda avtomatik ogohlantirish faol!</i>"
        )
    
    builder = InlineKeyboardBuilder()
    
    if saved_group:
        builder.button(text=f"🌠 Mening guruhim: {saved_group}", callback_data=f"mygrp_{saved_group}")
        
    builder.button(text="🏛 Fakultetlar bo'yicha", callback_data="menu_faculties")
    builder.button(text="🎯 Guruhni qidirish", callback_data="menu_search")
    builder.button(text="👨‍🏫 O'qituvchini qidirish", callback_data="menu_teacher_search")
    builder.button(text="🚪 Bo'sh auditoriyalar", callback_data="menu_empty_rooms")
    builder.button(text="ℹ️ Bot haqida", callback_data="menu_about")
    
    if saved_group:
        builder.adjust(1, 2, 2, 1)
    else:
        builder.adjust(2, 2, 1)
    
    if isinstance(event, CallbackQuery):
        try:
            await event.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
        except Exception:
            pass
        await event.answer()
    else: 
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    try:
        await message.answer_sticker("CAACAgIAAxkBAAEK1eJlY_6K3F2Gv0yqQj6wA_J5cM9_AAO_AQAC7_L0CwVj5-VlRkY6MzQE")
    except Exception:
        pass 
    await send_main_menu(message, message.from_user.id, message.from_user.first_name, state)

@dp.callback_query(F.data == "ignore")
async def ignore_callback(call: CallbackQuery):
    await call.answer()

# ======================================================================
# --- YANGI O'QITUVCHI QIDIRISH TIZIMI ---
# ======================================================================

@dp.callback_query(F.data == "menu_teacher_search")
async def menu_teacher_search(call: CallbackQuery, state: FSMContext):
    await state.clear()
    text = (
        "👨‍🏫 <b>O'qituvchini qidirish</b>\n\n"
        "Qidirish usulini tanlang:\n\n"
        "• 🏢 <b>Fakultetlar bo'yicha:</b> Fakultetni tanlab, o'sha fakultetdagi domlalar ro'yxatini ko'rish\n"
        "• 🔎 <b>Ism-familiya orqali:</b> Domlaning familiyasi yoki ismini yozib topish (Masalan: <code>ABDURAXIMOV D</code>)\n\n"
        "<i>Domlaning dars vaqtlari, xonalari va qaysi guruhlarga dars berishini bilib oling.</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🏢 Fakultetlar bo'yicha", callback_data="tsearch_fac")
    builder.button(text="🔎 Ism-familiya orqali qidirish", callback_data="tsearch_name")
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    builder.adjust(1, 1, 1)
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "tsearch_fac")
async def tsearch_fac_menu(call: CallbackQuery):
    faculties = await get_faculties()
    builder = InlineKeyboardBuilder()
    for fid, name in faculties.items():
        builder.button(text=f"🏢 {name}", callback_data=f"tfac_{fid}_0")
    builder.button(text="🔙 Orqaga", callback_data="menu_teacher_search")
    builder.adjust(1)
    await call.message.edit_text(
        "🏢 <b>Fakultetni tanlang:</b>\n\n<i>Kerakli fakultetdagi o'qituvchilar ro'yxati ko'rsatiladi.</i>", 
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("tfac_"))
async def tsearch_fac_list(call: CallbackQuery):
    if parser._IS_CACHING and not parser._ALL_SCHEDULES_CACHE:
        await call.answer("⏳ Baza endigina ishga tushdi va yuklanmoqda (1-2 daqiqa). Iltimos, biroz kuting!", show_alert=True)
        return

    parts = call.data.split("_")
    fid = parts[1]
    page = int(parts[2])
    
    faculties = await get_faculties()
    fac_name = faculties.get(fid, "")
    teachers = await get_teachers_by_faculty(fac_name)
    
    ITEMS_PER_PAGE = 8
    total_pages = max(1, (len(teachers) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    
    start_idx = page * ITEMS_PER_PAGE
    end_idx = start_idx + ITEMS_PER_PAGE
    current_teachers = teachers[start_idx:end_idx]
    
    text = (
        f"🏢 <b>Fakultet:</b> {fac_name}\n"
        f"👨‍🏫 <b>O'qituvchilar ro'yxati:</b>\n"
        f"Jami: <b>{len(teachers)} nafar</b> o'qituvchi\n"
        f"Sahifa: {page+1}/{total_pages}\n\n"
        f"<i>Dars jadvalini ko'rish uchun o'qituvchini tanlang:</i>"
    )
    
    builder = InlineKeyboardBuilder()
    for t in current_teachers:
        safe_name = t['name'][:25]
        builder.button(text=f"👨‍🏫 {t['name']} ({t['count']} ta dars)", callback_data=f"tsch_{safe_name}_haftalik")
        
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Oldingi", callback_data=f"tfac_{fid}_{page-1}"))
    nav_buttons.append(InlineKeyboardButton(text=f"📄 {page+1}/{total_pages}", callback_data="ignore"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ▶️", callback_data=f"tfac_{fid}_{page+1}"))
    
    builder.adjust(1)
    if len(teachers) > ITEMS_PER_PAGE:
        builder.row(*nav_buttons)
    builder.row(
        InlineKeyboardButton(text="🌎 Fakultetlar ro'yxati", callback_data="tsearch_fac"),
        InlineKeyboardButton(text="🏠 Asosiy menyu", callback_data="menu_main")
    )
    
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "tsearch_name")
async def ask_teacher_name(call: CallbackQuery, state: FSMContext):
    text = (
        "🔎 <b>O'qituvchining ism yoki familiyasini yozing:</b>\n\n"
        "Masalan: <code>ABDURAXIMOV D</code> yoki <code>Tishlikov</code>\n\n"
        "<i>Kerakli domlaning dars jadvali, auditoriyasi va dars vaqtlarini topib beramiz.</i>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Qidiruvni bekor qilish", callback_data="menu_teacher_search")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(QidiruvHolati.oqituvchi_kutilmoqda)
    await call.answer()

@dp.message(QidiruvHolati.oqituvchi_kutilmoqda)
async def process_teacher_name(message: Message, state: FSMContext):
    if parser._IS_CACHING and not parser._ALL_SCHEDULES_CACHE:
        await message.reply("⏳ <i>Ma'lumotlar bazasi hozir yangilanmoqda. Iltimos, birozdan so'ng qayta urining...</i>", parse_mode="HTML")
        return

    keyword = message.text.strip()
    results = await search_teacher_by_keyword(keyword)
    builder = InlineKeyboardBuilder()
    
    if not results:
        builder.button(text="🔎 Qayta qidirish", callback_data="tsearch_name")
        builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
        builder.adjust(2)
        await message.answer(f"❌ <b>{keyword}</b> ismli o'qituvchi topilmadi.\nIltimos, ismning bir qismini to'g'ri yozing.", reply_markup=builder.as_markup(), parse_mode="HTML")
        return
        
    await state.clear()
    for t in results[:15]: 
        fac_short = t['faculty'][:25] + "..." if len(t['faculty']) > 25 else t['faculty']
        safe_name = t['name'][:25]
        btn_text = f"👨‍🏫 {t['name']} ({fac_short})"
        builder.button(text=btn_text, callback_data=f"tsch_{safe_name}_haftalik")
    
    builder.button(text="🔎 Qayta qidirish", callback_data="tsearch_name")
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    builder.adjust(1) 
    
    await message.answer(f"✅ <b>{len(results)} nafar o'qituvchi topildi. Tanlang:</b>", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data.startswith("tsch_"))
async def show_teacher_schedule(call: CallbackQuery):
    data_parts = call.data.split("_", 2)
    teacher_name = data_parts[1]
    day_filter = data_parts[2]
    
    full_schedule_text = await search_teacher_schedule(teacher_name)
    
    if not full_schedule_text:
        builder = InlineKeyboardBuilder()
        builder.button(text="🔙 Orqaga", callback_data="menu_teacher_search")
        await call.message.edit_text("❌ Jadval topilmadi.", reply_markup=builder.as_markup())
        await call.answer()
        return

    schedule_text = full_schedule_text
    if day_filter in ["bugun", "ertaga"]:
        tz = pytz.timezone('Asia/Tashkent')
        target_dt = datetime.now(tz)
        if day_filter == "ertaga":
            target_dt += timedelta(days=1)
        target_date_str = target_dt.strftime("%d.%m.%Y")
        
        blocks = full_schedule_text.split("━━━━━━━━━━━━━━━━━━\n")
        filtered_lines = [blocks[0].split("\n\n")[0] + "\n\n"] 
        
        found = False
        for block in blocks[1:]:
            if target_date_str in block:
                filtered_lines.append(block)
                found = True
                
        if found:
            schedule_text = "━━━━━━━━━━━━━━━━━━\n".join(filtered_lines)
        else:
            prefix = "Bugun" if day_filter == "bugun" else "Ertaga"
            schedule_text = f"👨‍🏫 <b>{teacher_name} ishtirokidagi darslar:</b>\n\n🌴 <i>{prefix} darslar mavjud emas (Dam olish kuni).</i>"

    safe_name = teacher_name[:25]
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Bugun", callback_data=f"tsch_{safe_name}_bugun")
    builder.button(text="⏰ Ertaga", callback_data=f"tsch_{safe_name}_ertaga")
    builder.button(text="🟢 Haftalik", callback_data=f"tsch_{safe_name}_haftalik")
    builder.button(text="🔎 Boshqa domla 👨‍🏫", callback_data="menu_teacher_search")
    builder.button(text="🏠 Asosiy menyu", callback_data="menu_main")
    builder.adjust(3, 2)
    
    await call.message.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

# ======================================================================

@dp.callback_query(F.data.startswith("mygrp_"))
async def show_my_group(call: CallbackQuery):
    group_name = call.data.split("_")[1]
    
    group_id = await search_group_id(group_name)
    if group_id:
        schedule_text = await get_schedule_text(group_id, group_name, "bugun") 
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Bugun", callback_data=f"grp_{group_id}_{group_name}_bugun")
        builder.button(text="⏰ Ertaga", callback_data=f"grp_{group_id}_{group_name}_ertaga")
        builder.button(text="📚 Haftalik", callback_data=f"grp_{group_id}_{group_name}_haftalik")
        builder.button(text="📌 Asosiy guruh qilib saqlash", callback_data=f"save_{group_name}")
        builder.button(text="🔍 Boshqa guruh", callback_data="menu_search")
        builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
        builder.adjust(3, 1, 2)
        await call.message.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    else:
        await call.message.edit_text("❌ Guruh ma'lumotlari topilmadi.", reply_markup=InlineKeyboardBuilder().button(text="🔙 Orqaga", callback_data="menu_main").as_markup())
    
    await call.answer()

@dp.callback_query(F.data == "menu_empty_rooms")
async def show_buildings_menu(call: CallbackQuery):
    faculties = await get_faculties()
    builder = InlineKeyboardBuilder()
    for fid, name in faculties.items():
        builder.button(text=f"🏢 {name}", callback_data=f"efac_{fid}")
    builder.button(text="🔙 Asosiy menyu", callback_data="menu_main")
    builder.adjust(1)
    await call.message.edit_text(
        "🏢 <b>Qaysi fakultetga tegishli dars xonalarini tekshirmoqchisiz?</b>\n\nRo'yxatdan tanlang:", 
        reply_markup=builder.as_markup(), parse_mode="HTML"
    )
    await call.answer()

@dp.callback_query(F.data.startswith("efac_"))
async def process_faculty_rooms(call: CallbackQuery):
    fid = call.data.split("_")[1]
    faculties = await get_faculties()
    faculty_name = faculties.get(fid, "Noma'lum fakultet")
    
    rooms_text = await get_rooms_status_by_faculty(faculty_name)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Yangilash", callback_data=f"efac_{fid}")
    builder.button(text="🔙 Fakultetlar ro'yxati", callback_data="menu_empty_rooms")
    builder.button(text="🏠 Asosiy menyu", callback_data="menu_main")
    builder.adjust(1, 2)
    
    await call.message.edit_text(rooms_text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = (
        "🤖 <b>GulDU Dars Jadvali Bot — Qo'llanma</b>\n\n"
        "Ushbu bot Guliston Davlat Universiteti talabalari va ustozlari uchun dars jadvallarini kuzatishni eng qulay darajaga olib chiqish maqsadida yaratilgan.\n\n"
        "<b>Asosiy imkoniyatlar:</b>\n"
        "🎯 <b>Guruhni qidirish:</b> Eng tezkor usul. Guruh nomini (masalan: <i>9-24AT</i>) yozib yuboring va jadvalni lahzada oling.\n"
        "🏛 <b>Fakultetlar bo'yicha:</b> Agar guruh nomini aniq bilmasangiz, fakultet, kurs va ta'lim shaklini tanlash orqali bosqichma-bosqich qidirishingiz mumkin.\n"
        "👨‍🏫 <b>O'qituvchini qidirish:</b> Ustozingiz qachon, qaysi guruhga va qayerda dars o'tayotganini bilmoqchimisiz? Shunchaki fakulteti bo'yicha yoki ism-sharifini yozib qidiring.\n"
        "🚪 <b>Bo'sh auditoriyalar:</b> Fakultetni tanlang va ayni shu daqiqada qaysi xonalar bo'sh ekanligini, bandlarida esa qaysi guruh o'tirganini avtomatik tahlil orqali bilib oling.\n\n"
        "⭐ <b>Maxsus Imkoniyat (Mening guruhim)</b>\n"
        "O'z guruhingizni topgach, pastdagi <i>«📌 Asosiy guruh qilib saqlash»</i> tugmasini bosing. Shundan so'ng, Asosiy menyuda siz uchun maxsus tezkor tugma paydo bo'ladi. Dars boshlanishiga 30 daqiqa qolganda va jadvalda o'zgarish bo'lsa, bot sizga avtomatik eslatma yuboradi!\n\n"
        "<i>Eslatma: Barcha ma'lumotlar to'g'ridan-to'g'ri GulDU rasmiy bazasidan olinadi.</i>\n\n"
        "👨‍💻 <b>Dasturchi:</b> Quvonchbek Baratov"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyuga qaytish", callback_data="menu_main")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    await call.answer()

@dp.callback_query(F.data == "menu_search")
async def menu_search(call: CallbackQuery, state: FSMContext):
    text = "🔍 <b>Guruh nomini yozib yuboring</b>\n\n(Masalan: <i>10-26AT</i>, <i>9-24AT</i>):"
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(QidiruvHolati.guruh_kutilmoqda)
    await call.answer()

@dp.callback_query(F.data == "menu_main")
async def back_to_main(call: CallbackQuery, state: FSMContext):
    await send_main_menu(call, call.from_user.id, call.from_user.first_name, state)

@dp.callback_query(F.data == "menu_faculties")
async def show_faculties(call: CallbackQuery):
    faculties = await get_faculties()
    builder = InlineKeyboardBuilder()
    for fid, name in faculties.items():
        builder.button(text=f"👨‍🏫 {name}", callback_data=f"fac_{fid}")
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    builder.adjust(1)
    await call.message.edit_text("🏛 Fakultetingizni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("fac_"))
async def show_forms(call: CallbackQuery):
    fakul_id = call.data.split("_")[1]
    forms = await get_forms(fakul_id)
    builder = InlineKeyboardBuilder()
    for tid, name in forms.items():
        builder.button(text=f"🎓 {name}", callback_data=f"form_{fakul_id}_{tid}")
    builder.button(text="🔙 Fakultetlar", callback_data="menu_faculties")
    builder.button(text="👨‍🏫 Bosh menyu", callback_data="menu_main")
    builder.adjust(1, 2)
    await call.message.edit_text("🎓 Ta'lim shaklini tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("form_"))
async def show_courses(call: CallbackQuery):
    _, fakul_id, t_shakli_id = call.data.split("_")
    courses = await get_courses(fakul_id, t_shakli_id)
    builder = InlineKeyboardBuilder()
    for kid, name in courses.items():
        builder.button(text=f"📘 {name}", callback_data=f"crs_{fakul_id}_{t_shakli_id}_{kid}")
    builder.button(text="🔙 Ta'lim shakllari", callback_data=f"fac_{fakul_id}")
    builder.button(text="👨‍🏫 Bosh menyu", callback_data="menu_main")
    builder.adjust(2, 2)
    await call.message.edit_text("📘 Kursni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("crs_"))
async def show_groups(call: CallbackQuery):
    _, fakul_id, t_shakli_id, kursid = call.data.split("_")
    groups = await get_groups(fakul_id, t_shakli_id, kursid)
    builder = InlineKeyboardBuilder()
    for gid, name in groups.items():
        builder.button(text=f"👥 {name}", callback_data=f"grp_{gid}_{name}_haftalik")
    builder.button(text="🔙 Kurslar", callback_data=f"form_{fakul_id}_{t_shakli_id}")
    builder.button(text="👨‍🏫 Bosh menyu", callback_data="menu_main")
    builder.adjust(2)
    await call.message.edit_text("👥 Guruhni tanlang:", reply_markup=builder.as_markup())
    await call.answer()

@dp.callback_query(F.data.startswith("grp_"))
async def show_schedule(call: CallbackQuery):
    data_parts = call.data.split("_")
    group_id = data_parts[1]
    group_name = data_parts[2]
    day_filter = data_parts[3] 
    
    schedule_text = await get_schedule_text(group_id, group_name, day_filter)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Bugun", callback_data=f"grp_{group_id}_{group_name}_bugun")
    builder.button(text="⏰ Ertaga", callback_data=f"grp_{group_id}_{group_name}_ertaga")
    builder.button(text="📚 Haftalik", callback_data=f"grp_{group_id}_{group_name}_haftalik")
    builder.button(text="📌 Asosiy guruh qilib saqlash", callback_data=f"save_{group_name}")
    builder.button(text="🔍 Boshqa guruh", callback_data="menu_search")
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    builder.adjust(3, 1, 2)
    
    await call.message.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    await call.answer()

@dp.callback_query(F.data.startswith("save_"))
async def save_group(call: CallbackQuery, state: FSMContext):
    group_name = call.data.split("_")[1]
    await set_user_group(call.from_user.id, group_name)
    await call.answer(f"✅ {group_name} guruhi avto-eslatmalar uchun saqlandi!", show_alert=True)
    await send_main_menu(call, call.from_user.id, call.from_user.first_name, state)

@dp.message(QidiruvHolati.guruh_kutilmoqda)
async def process_group_search(message: Message, state: FSMContext):
    matn = message.text.strip().upper()
    if "-" not in matn or len(matn) < 4:
        await message.reply("Guruh formatida xatolik bor (masalan: 10-26AT):")
        return

    group_id = await search_group_id(matn)
    
    if group_id:
        schedule_text = await get_schedule_text(group_id, matn, "haftalik")
        builder = InlineKeyboardBuilder()
        builder.button(text="✅ Bugun", callback_data=f"grp_{group_id}_{matn}_bugun")
        builder.button(text="⏰ Ertaga", callback_data=f"grp_{group_id}_{matn}_ertaga")
        builder.button(text="📚 Haftalik", callback_data=f"grp_{group_id}_{matn}_haftalik")
        builder.button(text="📌 Asosiy guruh qilib saqlash", callback_data=f"save_{matn}")
        builder.button(text="🔍 Boshqa guruh", callback_data="menu_search")
        builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
        builder.adjust(3, 1, 2)
        
        await message.answer(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
        await state.clear()
    else:
        await message.answer("❌ Bunday guruh topilmadi.")

# ======================================================================
# --- ADMIN PANEL FUNKSIYALARI ---
# ======================================================================
async def show_admin_menu(message_or_call):
    text = "👨‍💻 <b>Boshqaruv Paneli</b>\n\nTizim to'liq sizning nazoratingizda. Kerakli amalni tanlang:"
    builder = InlineKeyboardBuilder()
    builder.button(text="📊 Statistika", callback_data="admin_stats")
    builder.button(text="📢 Xabar tarqatish", callback_data="admin_broadcast")
    builder.button(text="🔄 Keshni yangilash", callback_data="admin_refresh")
    builder.button(text="❌ Yopish", callback_data="admin_close")
    builder.adjust(2, 1, 1)
    
    if isinstance(message_or_call, Message):
        await message_or_call.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    else:
        await message_or_call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.message(Command("admin"))
async def admin_panel(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return
    await state.clear() 
    await show_admin_menu(message)

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    users = await get_all_users_id()
    active_groups = await get_active_groups()
    
    text = (
        "📊 <b>Tizim Statistikasi</b>\n\n"
        f"👥 Jami ro'yxatdan o'tganlar: <b>{len(users)} ta</b>\n"
        f"📚 Kuzatilayotgan guruhlar: <b>{len(active_groups)} ta</b>"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data="admin_back")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await call.answer()

@dp.callback_query(F.data == "admin_refresh")
async def admin_refresh(call: CallbackQuery):
    if call.from_user.id not in ADMIN_IDS: return
    await call.answer("⏳ Bazadan yangi guruhlar va jadvallar yuklanmoqda...", show_alert=False)
    
    import parser
    parser.clear_all_caches()
    await parser._fetch_all_schedules()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Orqaga", callback_data="admin_back")
    await call.message.edit_text("✅ <b>Ma'lumotlar bazasi to'liq yangilandi!</b>\nYangi qo'shilgan guruhlar, o'qituvchilar va xonalar tizimga kiritildi.", reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast_msg(call: CallbackQuery, state: FSMContext):
    if call.from_user.id not in ADMIN_IDS: return
    builder = InlineKeyboardBuilder()
    builder.button(text="❌ Bekor qilish", callback_data="admin_back")
    await call.message.edit_text("✍ <b>Tarqatmoqchi bo'lgan xabaringizni yuboring:</b>\n\n(Matn, rasm yoki video qabul qilinadi)", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_broadcast)
    await call.answer()

@dp.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS: return
    
    users = await get_all_users_id()
    sent_count = 0
    wait_msg = await message.answer("⏳ Xabar tarqatilmoqda, tizimdan chiqmang...")
    
    for uid in users:
        try:
            await message.send_copy(chat_id=uid)
            sent_count += 1
            await asyncio.sleep(0.05)
        except Exception:
            pass
            
    await state.clear()
    await wait_msg.delete()
    await message.answer(f"✅ Xabar <b>{sent_count} ta</b> foydalanuvchiga muvaffaqiyatli yuborildi!", parse_mode="HTML")
    await show_admin_menu(message)

@dp.callback_query(F.data == "admin_back")
async def admin_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_admin_menu(call)
    await call.answer()

@dp.callback_query(F.data == "admin_close")
async def admin_close(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.delete()

@dp.message()
async def boshqa_xabarlar(message: Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state == AdminStates.waiting_for_broadcast.state:
        return
    await message.reply("🙂 Iltimos, kerakli amallarni bajarish uchun /start buyrug'idan foydalaning yoki tugmalarni bosing.")

# ======================================================================
# --- SOXTA VEB-SERVER VA ISHGA TUSHIRISH ---
# ======================================================================
async def handle_ping(request):
    return web.Response(text="Bot is running! 24/7")

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    start_scheduler(bot)
    
    import parser
    asyncio.create_task(parser._fetch_all_schedules())
    
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port) 
    await site.start()

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
