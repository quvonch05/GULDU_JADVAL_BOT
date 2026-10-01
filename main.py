import asyncio
import logging
import os
from aiohttp import web
from datetime import datetime
import pytz

from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from database import init_db, set_user_group, get_all_users_id, get_user_group, get_active_groups
from parser import (
    get_faculties, get_forms, get_courses, get_groups, 
    get_schedule_text, search_group_id, search_teacher_schedule, get_rooms_status_by_faculty
)
from scheduler import start_scheduler

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

# --- ASOSIY MENYU CHIZUVCHI FUNKSIYA (TEZLASHTIRILDI) ---
async def send_main_menu(event: Message | CallbackQuery, user_id: int, first_name: str, state: FSMContext):
    await state.clear() 
    saved_group = await get_user_group(user_id)
    
    text = (
        f"Assalomu alaykum, {first_name}!\n\n"
        "🏛 <b>GulDU Dars Jadvali Tizimi</b> ✨\n"
        "<i>Guliston Davlat Universiteti rasmiy dars jadvallarini qulay kuzatib boring.</i>\n\n"
        "Kerakli bo'limni tanlang:\n"
        "• 👨‍🏫 <b>Fakultetlar bo'yicha:</b> Bosqichma-bosqich qidirish\n"
        "• 🎯 <b>Guruhni qidirish:</b> Nom bo'yicha lahzada topish"
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
    builder.button(text="👨‍🏫 O'qituvchi jadvali", callback_data="menu_teacher_search")
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
    else: 
        await event.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    try:
        await message.answer_sticker("CAACAgIAAxkBAAEK1eJlY_6K3F2Gv0yqQj6wA_J5cM9_AAO_AQAC7_L0CwVj5-VlRkY6MzQE")
    except Exception:
        pass 
    await send_main_menu(message, message.from_user.id, message.from_user.first_name, state)

@dp.callback_query(F.data.startswith("mygrp_"))
async def show_my_group(call: CallbackQuery):
    group_name = call.data.split("_")[1]
    wait_msg = await call.message.edit_text(f"⏳ <b>{group_name}</b> jadvali yuklanmoqda...", parse_mode="HTML")
    
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
        await wait_msg.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    else:
        await wait_msg.edit_text("❌ Guruh ma'lumotlari topilmadi.", reply_markup=InlineKeyboardBuilder().button(text="🔙 Orqaga", callback_data="menu_main").as_markup())

@dp.callback_query(F.data == "menu_teacher_search")
async def menu_teacher_search(call: CallbackQuery, state: FSMContext):
    text = "👨‍🏫 <b>O'qituvchi ism-sharifini kiriting</b>\n\n(Masalan: <i>ISMATILLAYEV A.</i> yoki qisman familiyasini):"
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(QidiruvHolati.oqituvchi_kutilmoqda)

@dp.message(QidiruvHolati.oqituvchi_kutilmoqda)
async def process_teacher_search(message: Message, state: FSMContext):
    teacher_name = message.text.strip()
    wait_msg = await message.answer(f"⏳ <b>{teacher_name}</b> ismli o'qituvchi jadvali qidirilmoqda, kuting...", parse_mode="HTML")
    
    schedule_text = await search_teacher_schedule(teacher_name)
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    
    if schedule_text:
        await wait_msg.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML")
        await state.clear()
    else:
        await wait_msg.edit_text(
            f"❌ <b>{teacher_name}</b> ismli o'qituvchi topilmadi yoki jadvali yo'q.\nIltimos, qayta kiriting.", 
            reply_markup=builder.as_markup(), parse_mode="HTML"
        )

# --- BO'SH XONALAR (FAKULTETNI TANLASH - AVTOMATIK) ---
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
        reply_markup=builder.as_markup(), 
        parse_mode="HTML"
    )

# --- TANLANGAN FAKULTET XONALARINI KO'RSATISH ---
@dp.callback_query(F.data.startswith("efac_"))
async def process_faculty_rooms(call: CallbackQuery):
    fid = call.data.split("_")[1]
    faculties = await get_faculties()
    faculty_name = faculties.get(fid, "Noma'lum fakultet")
    
    wait_msg = await call.message.edit_text(f"⏳ <b>{faculty_name}</b> xonalari bazadan izlanib, tahlil qilinmoqda...", parse_mode="HTML")
    
    tz = pytz.timezone('Asia/Tashkent')
    current_time = datetime.now(tz).strftime("%H:%M")
    
    rooms_text = await get_rooms_status_by_faculty(faculty_name, current_time)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🔄 Yangilash", callback_data=f"efac_{fid}")
    builder.button(text="🔙 Fakultetlar ro'yxati", callback_data="menu_empty_rooms")
    builder.button(text="🏠 Asosiy menyu", callback_data="menu_main")
    
    builder.adjust(1, 2)
    
    await wait_msg.edit_text(rooms_text, reply_markup=builder.as_markup(), parse_mode="HTML")

@dp.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = (
        "🤖 <b>GulDU Dars Jadvali Bot — Qo'llanma</b>\n\n"
        "Ushbu bot Guliston Davlat Universiteti talabalari va ustozlari uchun dars jadvallarini kuzatishni eng qulay darajaga olib chiqish maqsadida yaratilgan.\n\n"
        "<b>Asosiy imkoniyatlar:</b>\n"
        "🎯 <b>Guruhni qidirish:</b> Eng tezkor usul. Guruh nomini (masalan: <i>9-24AT</i>) yozib yuboring va jadvalni lahzada oling.\n"
        "🏛 <b>Fakultetlar bo'yicha:</b> Agar guruh nomini aniq bilmasangiz, fakultet, kurs va ta'lim shaklini tanlash orqali bosqichma-bosqich qidirishingiz mumkin.\n"
        "👨‍🏫 <b>O'qituvchi jadvali:</b> Ustozingiz qachon, qaysi guruhga va qayerda dars o'tayotganini bilmoqchimisiz? Shunchaki ism-sharifini yozib qidiring.\n"
        "🚪 <b>Bo'sh auditoriyalar:</b> Fakultetni tanlang va ayni shu daqiqada qaysi xonalar bo'sh ekanligini, bandlarida esa qaysi guruh o'tirganini avtomatik tahlil orqali bilib oling.\n\n"
        "⭐ <b>Maxsus Imkoniyat (Mening guruhim)</b>\n"
        "O'z guruhingizni topgach, pastdagi <i>«📌 Asosiy guruh qilib saqlash»</i> tugmasini bosing. Shundan so'ng, Asosiy menyuda siz uchun maxsus tezkor tugma paydo bo'ladi. Dars boshlanishiga 30 daqiqa qolganda va jadvalda o'zgarish bo'lsa, bot sizga avtomatik eslatma yuboradi!\n\n"
        "<i>Eslatma: Barcha ma'lumotlar to'g'ridan-to'g'ri GulDU rasmiy bazasidan olinadi.</i>\n\n"
        "👨‍💻 <b>Dasturchi:</b> Quvonchbek Baratov"
    )
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyuga qaytish", callback_data="menu_main")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data == "menu_search")
async def menu_search(call: CallbackQuery, state: FSMContext):
    text = "🔍 <b>Guruh nomini yozib yuboring</b>\n\n(Masalan: <i>10-26AT</i>, <i>9-24AT</i>):"
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    await call.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(QidiruvHolati.guruh_kutilmoqda)

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

@dp.callback_query(F.data.startswith("grp_"))
async def show_schedule(call: CallbackQuery):
    data_parts = call.data.split("_")
    group_id = data_parts[1]
    group_name = data_parts[2]
    day_filter = data_parts[3] 
    
    await call.message.edit_text(f"⏳ <b>{group_name}</b> jadvali yuklanmoqda...", parse_mode="HTML")
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

    wait_msg = await message.answer("⏳ Guruh bazadan qidirilmoqda, kuting...")
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
        
        await wait_msg.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
        await state.clear()
    else:
        await wait_msg.edit_text("❌ Bunday guruh topilmadi.")

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
    await call.message.edit_text("✍️ <b>Tarqatmoqchi bo'lgan xabaringizni yuboring:</b>\n\n(Matn, rasm yoki video qabul qilinadi)", reply_markup=builder.as_markup(), parse_mode="HTML")
    await state.set_state(AdminStates.waiting_for_broadcast)

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
    
    from parser import _fetch_all_schedules
    asyncio.create_task(_fetch_all_schedules())
    
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
