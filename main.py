import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiohttp import web
from aiogram import types, F

from database import init_db, set_user_group, get_all_users_id
from parser import get_faculties, get_forms, get_courses, get_groups, get_schedule_text, search_group_id
from scheduler import start_scheduler

BOT_TOKEN = "8923062582:AAGcjkBTD714VDE0cSWEs_XYPL2PSIOHegI"
ADMIN_ID = 1686406789
  # O'z profilingiz ID raqamini raqam formatida yozing (masalan: 135792468)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Admin xabar tarqatishi uchun holat
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()

@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Premium stiker (ID ni xohlagan stikeringizga almashtirishingiz mumkin)
    try:
        await message.answer_sticker("CAACAgIAAxkBAAEK1eJlY_6K3F2Gv0yqQj6wA_J5cM9_AAO_AQAC7_L0CwVj5-VlRkY6MzQE")
    except Exception:
        pass # Stiker ID noto'g'ri bo'lsa xato bermaydi
        
    text = (
        f"Assalomu alaykum, {message.from_user.first_name} 🍁🍂 👨‍🎓 👨‍💻!\n\n"
        "🏛 <b>GulDU Dars Jadvali Tizimi</b> ✨\n"
        "<i>Guliston Davlat Universiteti rasmiy dars jadvallarini qulay kuzatib boring.</i>\n\n"
        "Kerakli bo'limni tanlang:\n"
        "• 👨‍🏫 <b>Fakultetlar bo'yicha:</b> Bosqichma-bosqich qidirish\n"
        "• 🎯 <b>Guruhni qidirish:</b> Nom bo'yicha lahzada topish"
    )
    
    builder = InlineKeyboardBuilder()
    builder.button(text="🏛 Fakultetlar bo'yicha", callback_data="menu_faculties")
    builder.button(text="🎯 Guruhni qidirish", callback_data="menu_search")
    builder.button(text="ℹ️ Bot haqida", callback_data="menu_about")
    builder.adjust(2, 1)
    
    await message.answer(text, reply_markup=builder.as_markup(), parse_mode="HTML")

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id != ADMIN_ID:
        return
    
    users = await get_all_users_id()
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📢 Barchaga xabar yuborish", callback_data="admin_broadcast")
    
    await message.answer(
        f"👨‍💻 <b>Boshqaruv Paneli</b>\n\n"
        f"👥 Botdagi jami talabalar: <b>{len(users)} ta</b>", 
        reply_markup=builder.as_markup(), 
        parse_mode="HTML"
    )

@dp.callback_query(F.data == "admin_broadcast")
async def ask_broadcast_msg(call: CallbackQuery, state: FSMContext):
    if call.from_user.id != ADMIN_ID:
        return
    await call.message.edit_text("✍️ Tarqatmoqchi bo'lgan xabaringizni yuboring (Matn, rasm yoki video):")
    await state.set_state(AdminStates.waiting_for_broadcast)

@dp.message(AdminStates.waiting_for_broadcast)
async def send_broadcast(message: Message, state: FSMContext):
    users = await get_all_users_id()
    sent_count = 0
    await message.answer("⏳ Xabar tarqatilmoqda...")
    
    for uid in users:
        try:
            await message.send_copy(chat_id=uid)
            sent_count += 1
            await asyncio.sleep(0.05) # Telegram bloklamasligi uchun
        except Exception:
            pass
            
    await message.answer(f"✅ Xabar <b>{sent_count}</b> ta foydalanuvchiga muvaffaqiyatli yuborildi!", parse_mode="HTML")
    await state.clear()


# --- Asosiy Menyu Tugmalari ---
@dp.callback_query(F.data == "menu_about")
async def menu_about(call: CallbackQuery):
    text = "🤖 <b>GulDU Dars Jadvali Bot</b>\n\nBu bot orqali universitetdagi barcha dars jadvallarini qulay kuzatib borishingiz mumkin. \n\n✨ <i>Qo'shimcha imkoniyatlar:</i> Jadvaldagi o'zgarishlar va dars boshlanishidan 30 daqiqa oldin keladigan avto-eslatmalar."
    await call.message.edit_text(text, parse_mode="HTML")
    
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    await call.message.edit_reply_markup(reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_search")
async def menu_search(call: CallbackQuery):
    text = "🔍 <b>Guruh nomini yozib yuboring</b>\n\n(Masalan: <i>10-26AT</i>, <i>9-24AT</i> yoki <i>1-24F</i>):"
    await call.message.edit_text(text, parse_mode="HTML")
    builder = InlineKeyboardBuilder()
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    await call.message.edit_reply_markup(reply_markup=builder.as_markup())

@dp.callback_query(F.data == "menu_main")
async def back_to_main(call: CallbackQuery):
    await cmd_start(call.message)
    await call.message.delete()

# --- Fakultet -> Shakl -> Kurs -> Guruh ---
@dp.callback_query(F.data == "menu_faculties")
async def show_faculties(call: CallbackQuery):
    await call.message.edit_text("⏳ Fakultetlar ro'yxati yuklanmoqda...")
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
    await call.message.edit_text("⏳ Ta'lim shakllari yuklanmoqda...")
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
    await call.message.edit_text("⏳ Kurslar yuklanmoqda...")
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
    await call.message.edit_text("⏳ Guruhlar yuklanmoqda...")
    groups = await get_groups(fakul_id, t_shakli_id, kursid)
    builder = InlineKeyboardBuilder()
    for gid, name in groups.items():
        builder.button(text=f"👥 {name}", callback_data=f"grp_{gid}_{name}_haftalik")
    builder.button(text="🔙 Kurslar", callback_data=f"form_{fakul_id}_{t_shakli_id}")
    builder.button(text="👨‍🏫 Bosh menyu", callback_data="menu_main")
    builder.adjust(2)
    await call.message.edit_text("👥 Guruhni tanlang:", reply_markup=builder.as_markup())

# --- Dars jadvalini ko'rsatish ---
@dp.callback_query(F.data.startswith("grp_"))
async def show_schedule(call: CallbackQuery):
    data_parts = call.data.split("_")
    group_id = data_parts[1]
    group_name = data_parts[2]
    day_filter = data_parts[3] 
    
    await call.message.edit_text(f"🔍 <b>{group_name}</b> jadvali yuklanmoqda...", parse_mode="HTML")
    schedule_text = await get_schedule_text(group_id, group_name, day_filter)
    
    builder = InlineKeyboardBuilder()
    builder.button(text="📅 Bugun", callback_data=f"grp_{group_id}_{group_name}_bugun")
    builder.button(text="⏰ Ertaga", callback_data=f"grp_{group_id}_{group_name}_ertaga")
    builder.button(text="🟢 Haftalik", callback_data=f"grp_{group_id}_{group_name}_haftalik")
    builder.button(text="📌 Mening guruhim qilib saqlash", callback_data=f"save_{group_name}")
    builder.button(text="🔙 Boshqa guruh", callback_data="menu_faculties")
    builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
    builder.adjust(3, 1, 2)
    
    await call.message.edit_text(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)

@dp.callback_query(F.data.startswith("save_"))
async def save_group(call: CallbackQuery):
    group_name = call.data.split("_")[1]
    await set_user_group(call.from_user.id, group_name)
    await call.answer(f"✅ {group_name} guruhi avto-eslatmalar uchun saqlandi!", show_alert=True)

# --- Matn orqali qidirish ---
@dp.message()
async def process_text_search(message: Message, state: FSMContext):
    # Agar admin xabar yozyotgan bo'lsa, uni guruh deb qidirmaydi
    current_state = await state.get_state()
    if current_state == AdminStates.waiting_for_broadcast:
        return

    group_name = message.text.strip().upper()
    wait_msg = await message.answer("⏳ Guruh bazadan qidirilmoqda, 5-10 soniya kuting...")
    
    group_id = await search_group_id(group_name)
    
    if group_id:
        schedule_text = await get_schedule_text(group_id, group_name, "haftalik")
        
        builder = InlineKeyboardBuilder()
        builder.button(text="📅 Bugun", callback_data=f"grp_{group_id}_{group_name}_bugun")
        builder.button(text="⏰ Ertaga", callback_data=f"grp_{group_id}_{group_name}_ertaga")
        builder.button(text="🟢 Haftalik", callback_data=f"grp_{group_id}_{group_name}_haftalik")
        builder.button(text="📌 Mening guruhim qilib saqlash", callback_data=f"save_{group_name}")
        builder.button(text="👨‍🏫 Asosiy menyu", callback_data="menu_main")
        builder.adjust(3, 1, 1)
        
        await wait_msg.delete()
        await message.answer(schedule_text, reply_markup=builder.as_markup(), parse_mode="HTML", disable_web_page_preview=True)
    else:
        await wait_msg.edit_text("❌ Bunday guruh topilmadi. To'g'ri yozilganiga ishonch hosil qiling (masalan: 10-26AT).")

async def main():
    logging.basicConfig(level=logging.INFO)
    await init_db()
    
    # Orqa fonda 30 daqiqalik eslatmalarni yoqish
    start_scheduler(bot)
    print("Avto-eslatma tizimi yoqildi.")
    import asyncio
import os

# ... bu yerda sizning oldingi kodlaringiz (routerlar, bot va hokazo) ...

# 1. Soxta veb-server uchun oddiy sahifa yaratamiz
async def handle_ping(request):
    return web.Response(text="Bot is running! 24/7")

async def main():
    # 2. Render talab qilgan portni ochamiz
    app = web.Application()
    app.router.add_get('/', handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000)) # Render bergan portni olamiz
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Soxta veb-server {port}-portda ishga tushdi.")

# Sizning guruh qidiruvchi handleringiz (nomi boshqacha bo'lishi mumkin)
@dp.message(F.text)
async def search_group(message: types.Message):
    # 1. Kiritilgan matn guruh formatiga mos kelishini tekshiramiz
    # Odatda guruhlarda "-" belgisi bo'ladi va eng kamida 4 ta belgidan iborat bo'ladi (Masalan: 4-21)
    if "-" not in matn or len(matn) < 4:
        await message.reply("Noma'lum buyruq. Iltimos, menyudan foydalaning yoki guruh nomini to'g'ri formatda yozing (masalan: 10-26AT).")
        return  # Kod shu yerda to'xtaydi va qidiruv tizimiga o'tib ketmaydi
        
    # 2. Sizning qidiruvchi asosiy kodingiz shu yerdan davom etadi...
    # guruh_jadvali = await get_schedule(matn) 
    # agar topilmasa: "Bunday guruh topilmadi..."

    # 3. Botni ishga tushiramiz (o'zingizning botingizni yozasiz)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
