from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def teacher_search_main_menu():
    """O'qituvchini qidirish asosiy menyusi[cite: 4]"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏢 Fakultetlar bo'yicha", callback_data="search_by_fac")],
        [InlineKeyboardButton(text="🔎 Ism-familiya orqali qidirish", callback_data="search_by_name")],
        [InlineKeyboardButton(text="👨‍🏫 Asosiy menyu", callback_data="main_menu")]
    ])

def cancel_search_btn():
    """Qidiruvni bekor qilish tugmasi[cite: 8]"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Qidiruvni bekor qilish", callback_data="cancel_search")]
    ])

def teacher_schedule_filters(teacher_name: str):
    """Jadval ostidagi Bugun, Ertaga, Haftalik tugmalari"""
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📅 Bugun", callback_data=f"t_sch|bugun|{teacher_name}"),
            InlineKeyboardButton(text="⏰ Ertaga", callback_data=f"t_sch|ertaga|{teacher_name}"),
            InlineKeyboardButton(text="🟢 Haftalik", callback_data=f"t_sch|haftalik|{teacher_name}")
        ],
        [
            InlineKeyboardButton(text="🔎 Boshqa domla 👨‍🏫", callback_data="search_by_fac"),
            InlineKeyboardButton(text="👨‍🏫 Asosiy menyu", callback_data="main_menu")
        ]
    ])
