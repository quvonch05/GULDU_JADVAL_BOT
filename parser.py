import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import re
import asyncio
import ssl
import json
import os

BASE_URL = "https://data.guldu.uz/dars"
CACHE_FILE = "cache_data.json"

SSL_CONTEXT = ssl.create_default_context()
SSL_CONTEXT.check_hostname = False
SSL_CONTEXT.verify_mode = ssl.CERT_NONE

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}

_CACHED_GROUPS = {}  
_GROUP_FACULTY_MAP = {} 
_ALL_SCHEDULES_CACHE = []
_RAW_SCHEDULES_HTML = {}
_LAST_CACHE_TIME = None
_IS_CACHING = False 
_IS_LOADING_GROUPS = False
_CACHE_STRUCT = {'faculties': None, 'forms': {}, 'courses': {}, 'groups': {}}

def load_local_backup():
    """Agar Renderdan GulDU sayti bloklangan bo'lsa, cache_data.json dan o'qiydi"""
    global _CACHE_STRUCT, _CACHED_GROUPS, _GROUP_FACULTY_MAP, _ALL_SCHEDULES_CACHE, _RAW_SCHEDULES_HTML
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                _CACHE_STRUCT = data.get("cache_struct", _CACHE_STRUCT)
                _CACHED_GROUPS = data.get("cached_groups", {})
                _GROUP_FACULTY_MAP = data.get("group_faculty_map", {})
                _ALL_SCHEDULES_CACHE = data.get("all_schedules_cache", [])
                _RAW_SCHEDULES_HTML = data.get("raw_schedules", {})
                print(f"[BACKUP YUKLANDI] {len(_CACHED_GROUPS)} ta guruh xotiraga olindi!")
        except Exception as e:
            print(f"[BACKUP XATOSI] {e}")

# Bot ishga tushishi bilan zaxira faylni yuklaydi
load_local_backup()

def clear_all_caches():
    global _CACHE_STRUCT, _CACHED_GROUPS, _GROUP_FACULTY_MAP, _ALL_SCHEDULES_CACHE, _LAST_CACHE_TIME
    _CACHE_STRUCT = {'faculties': None, 'forms': {}, 'courses': {}, 'groups': {}}
    _CACHED_GROUPS = {}
    _GROUP_FACULTY_MAP = {}
    _ALL_SCHEDULES_CACHE = []
    _LAST_CACHE_TIME = None
    load_local_backup()

def normalize_room_key(name: str) -> str:
    if not name:
        return ""
    cleaned = " ".join(name.strip().lower().split())
    cleaned = cleaned.replace("auditoriya", "xona")
    return cleaned

async def fetch_html(url: str, data: dict = None) -> str:
    # Agar guruh jadvali so'ralgan bo'lsa va u zaxirada bo'lsa, oldin saytdan, bo'lmasa zaxiradan oladi
    timeout = aiohttp.ClientTimeout(total=6)
    connector = aiohttp.TCPConnector(ssl=SSL_CONTEXT)
    
    # Ixtiyoriy: Agar Render Environment'ga PROXY_URL qo'shsangiz, o'sha orqali ulanadi
    proxy_url = os.environ.get("PROXY_URL", None)
    
    async with aiohttp.ClientSession(headers=HEADERS, timeout=timeout, connector=connector) as session:
        try:
            if data:
                async with session.post(url, data=data, proxy=proxy_url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if text and text.strip():
                            return text
            else:
                async with session.get(url, proxy=proxy_url) as response:
                    if response.status == 200:
                        text = await response.text()
                        if text and text.strip():
                            return text
        except Exception:
            pass
            
    # Sayt javob bermasa (Render bloklangan bo'lsa), zaxiradagi HTML ni qaytaradi
    if data and "datagroupid" in data:
        gid = str(data["datagroupid"])
        if gid in _RAW_SCHEDULES_HTML:
            return _RAW_SCHEDULES_HTML[gid]
            
    return ""

async def get_faculties() -> dict:
    if _CACHE_STRUCT['faculties']:
        return _CACHE_STRUCT['faculties']
        
    html = await fetch_html(f"{BASE_URL}/")
    if not html:
        load_local_backup()
        return _CACHE_STRUCT['faculties'] or {}
        
    soup = BeautifulSoup(html, 'html.parser')
    faculties = {}
    for a in soup.find_all('a'):
        fid = a.get('data-id')
        name = " ".join(a.text.split())
        if fid and name and name.lower() != "bosh sahifa":
            faculties[fid] = name
            
    if faculties:
        _CACHE_STRUCT['faculties'] = faculties
    return faculties

async def get_forms(fakul_id: str) -> dict:
    if _CACHE_STRUCT['forms'].get(fakul_id):
        return _CACHE_STRUCT['forms'][fakul_id]
        
    html = await fetch_html(f"{BASE_URL}/category.php?fakul_id={fakul_id}")
    if not html:
        return _CACHE_STRUCT['forms'].get(fakul_id, {})
        
    soup = BeautifulSoup(html, 'html.parser')
    forms = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 't_shakli_id=' in href:
            tid = href.split('t_shakli_id=')[-1].split('&')[0]
            forms[tid] = " ".join(a.text.split())
            
    if forms:
        _CACHE_STRUCT['forms'][fakul_id] = forms
    return forms

async def get_courses(fakul_id: str, t_shakli_id: str) -> dict:
    cache_key = f"{fakul_id}_{t_shakli_id}"
    if _CACHE_STRUCT['courses'].get(cache_key):
        return _CACHE_STRUCT['courses'][cache_key]
        
    html = await fetch_html(f"{BASE_URL}/kurs.php?fakul_id={fakul_id}&t_shakli_id={t_shakli_id}")
    if not html:
        return _CACHE_STRUCT['courses'].get(cache_key, {})
        
    soup = BeautifulSoup(html, 'html.parser')
    courses = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 'kursid=' in href:
            kid = href.split('kursid=')[-1].split('&')[0]
            courses[kid] = " ".join(a.text.split())
            
    if courses:
        _CACHE_STRUCT['courses'][cache_key] = courses
    return courses

async def get_groups(fakul_id: str, t_shakli_id: str, kursid: str) -> dict:
    cache_key = f"{fakul_id}_{t_shakli_id}_{kursid}"
    if _CACHE_STRUCT['groups'].get(cache_key):
        return _CACHE_STRUCT['groups'][cache_key]
        
    html = await fetch_html(f"{BASE_URL}/group.php?kursid={kursid}&fraculid={fakul_id}&t_shakli_id={t_shakli_id}")
    if not html:
        return _CACHE_STRUCT['groups'].get(cache_key, {})
        
    soup = BeautifulSoup(html, 'html.parser')
    groups = {}
    for btn in soup.find_all('button', class_='btn'):
        gid = btn.get('data-groupid')
        name = " ".join(btn.text.split())
        if gid and name:
            groups[gid] = name
            
    if groups:
        _CACHE_STRUCT['groups'][cache_key] = groups
    return groups

async def _load_all_groups_parallel():
    global _CACHED_GROUPS, _GROUP_FACULTY_MAP, _IS_LOADING_GROUPS
    if _CACHED_GROUPS or _IS_LOADING_GROUPS:
        return
    _IS_LOADING_GROUPS = True
    try:
        facs = await get_faculties()
        if not facs:
            return

        sem = asyncio.Semaphore(8)

        async def load_faculty_tree(fid, fname):
            async with sem:
                forms = await get_forms(fid)
            for tid in forms:
                async with sem:
                    courses = await get_courses(fid, tid)
                for kid in courses:
                    async with sem:
                        groups = await get_groups(fid, tid, kid)
                    for gid, gname in groups.items():
                        g_upper = " ".join(gname.upper().split())
                        _CACHED_GROUPS[g_upper] = gid
                        _GROUP_FACULTY_MAP[g_upper] = fname

        await asyncio.gather(*(load_faculty_tree(fid, fname) for fid, fname in facs.items()), return_exceptions=True)
    finally:
        _IS_LOADING_GROUPS = False

async def search_group_id(target_name: str) -> str:
    if not target_name:
        return None
    target = " ".join(target_name.strip().upper().split())
    if target.startswith("/"):
        return None
    if not _CACHED_GROUPS:
        await _load_all_groups_parallel()
    return _CACHED_GROUPS.get(target)

async def get_schedule_text(group_id: str, group_name: str, day_filter: str = "haftalik") -> str:
    if not group_id:
        return "❌ Guruh ma'lumotlari topilmadi."
        
    url = f"{BASE_URL}/ll.php"
    html = await fetch_html(url, data={"datagroupid": str(group_id)})
    
    if not html.strip() or "dars jadvali" not in html.lower():
        return "Bu guruh uchun hozircha dars jadvali kiritilmagan."

    tz = timezone(timedelta(hours=5))
    today_dt = datetime.now(tz)
    tomorrow_dt = today_dt + timedelta(days=1)
    
    today_str = today_dt.strftime("%d.%m.%Y")
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")

    uz_days = {0: 'Dushanba', 1: 'Seshanba', 2: 'Chorshanba', 3: 'Payshanba', 4: 'Juma', 5: 'Shanba', 6: 'Yakshanba'}

    soup = BeautifulSoup(html, 'html.parser')
    
    if day_filter == "bugun": 
        day_name = uz_days[today_dt.weekday()]
        header_title = f"Bugungi darslar — {today_str} ({day_name})"
    elif day_filter == "ertaga": 
        day_name = uz_days[tomorrow_dt.weekday()]
        header_title = f"Ertangi darslar — {tomorrow_str} ({day_name})"
    else:
        header_title = "To'liq haftalik dars jadvali"
    
    result_text = f"👥 Guruh: <a href='https://data.guldu.uz'><b>{group_name}</b></a>\n📆 {header_title}\n\n"
    found_days = 0
    current_date_text = ""

    cols = soup.find_all('div', class_='col-md-12')
    for col in cols:
        date_p = col.find('p', class_='bg-primary')
        if date_p:
            current_date_text = " ".join(date_p.text.split())
            if day_filter == "bugun" and today_str not in current_date_text: continue
            if day_filter == "ertaga" and tomorrow_str not in current_date_text: continue
            found_days += 1
            result_text += f"━━━━━━━━━━━━━━━━━━━━\n📅 <b>{current_date_text}</b>\n━━━━━━━━━━━━━━━━━━━━\n"

        tables = col.find_all('table')
        for table in tables:
            if current_date_text and (day_filter == "haftalik" or (day_filter == "bugun" and today_str in current_date_text) or (day_filter == "ertaga" and tomorrow_str in current_date_text)):
                time_th = table.find('th')
                time_text = " ".join(time_th.text.split()) if time_th else "Vaqti noma'lum"

                tds = table.find_all('td')
                if len(tds) >= 3:
                    t_parts = list(tds[0].stripped_strings)
                    teacher = t_parts[-1] if len(t_parts) > 1 else "Noma'lum"

                    s_parts = list(tds[1].stripped_strings)
                    s_type = s_parts[0] if len(s_parts) > 1 else ""
                    s_name = " ".join(s_parts[1:]) if len(s_parts) > 1 else ""

                    r_parts = list(tds[2].stripped_strings)
                    room = " ".join(r_parts[1:]) if len(r_parts) > 1 else ""

                    s_type_emoji = "📘" if "ma'ruza" in s_type.lower() else "📗"
                    
                    result_text += f"⏰ {time_text} • {s_type_emoji} [{s_type}]\n"
                    result_text += f"📖 Fan: {s_name}\n"
                    result_text += f"👨‍🏫 O'qituvchi: {teacher}\n"
                    result_text += f"🏫 Auditoriya: {room}\n\n"

    if found_days == 0:
        if day_filter in ["bugun", "ertaga"]:
            prefix = "Bugun" if day_filter == "bugun" else "Ertaga"
            result_text += f"🌴 <i>{prefix} darslar mavjud emas (Dam olish kuni).</i>"
        else:
            result_text += "Bunday sanada dars topilmadi 😴"

    return result_text.strip()

async def _fetch_all_schedules():
    global _ALL_SCHEDULES_CACHE, _LAST_CACHE_TIME, _IS_CACHING
    if _ALL_SCHEDULES_CACHE:
        return _ALL_SCHEDULES_CACHE
    if _IS_CACHING:
        return _ALL_SCHEDULES_CACHE
        
    _IS_CACHING = True
    try:
        temp_cache = []
        if not _CACHED_GROUPS:
            await _load_all_groups_parallel()
            
        sem = asyncio.Semaphore(5) 
        
        async def fetch_group(gname, gid):
            faculty_name = _GROUP_FACULTY_MAP.get(gname.upper(), "Boshqa")
            async with sem:
                html = await fetch_html(f"{BASE_URL}/ll.php", data={"datagroupid": str(gid)})
                if not html or "dars jadvali" not in html.lower():
                    return
                soup = BeautifulSoup(html, 'html.parser')
                current_date_text = "" 
                for col in soup.find_all('div', class_='col-md-12'):
                    date_p = col.find('p', class_='bg-primary')
                    if date_p:
                        current_date_text = " ".join(date_p.text.split())
                    if not current_date_text: 
                        continue
                    for table in col.find_all('table'):
                        time_th = table.find('th')
                        time_text = " ".join(time_th.text.split()) if time_th else ""
                        times = re.findall(r'\d{1,2}:\d{2}', time_text)
                        start_time = f"{int(times[0].split(':')[0]):02d}:{times[0].split(':')[1]}" if len(times) > 0 else "00:00"
                        end_time = f"{int(times[1].split(':')[0]):02d}:{times[1].split(':')[1]}" if len(times) > 1 else "23:59"
                        j_match = re.search(r'(\d+-juftlik)', time_text, re.IGNORECASE)
                        juftlik = j_match.group(1) if j_match else ""
                        tds = table.find_all('td')
                        if len(tds) >= 3:
                            t_strings = list(tds[0].stripped_strings)
                            teacher = t_strings[-1] if len(t_strings) > 1 else ""
                            s_parts = list(tds[1].stripped_strings)
                            dars_turi = s_parts[0] if len(s_parts) > 1 else ""
                            fan = " ".join(s_parts[1:]) if len(s_parts) > 1 else ""
                            r_strings = list(tds[2].stripped_strings)
                            room = " ".join(r_strings[1:]) if len(r_strings) > 1 else ""
                            if room and room.lower() != "noma'lum":
                                temp_cache.append({
                                    "guruh_nomi": gname, "sana": current_date_text, "juftlik": juftlik,
                                    "boshlanish_vaqti": start_time, "tugash_vaqti": end_time,
                                    "oqituvchi": teacher if teacher else "Noma'lum", "fan": fan, 
                                    "dars_turi": dars_turi, "auditoriya": room, "fakultet": faculty_name
                                })

        await asyncio.gather(*(fetch_group(gname, gid) for gname, gid in _CACHED_GROUPS.items()), return_exceptions=True) 
        if temp_cache:
            _ALL_SCHEDULES_CACHE = temp_cache
    finally:
        _IS_CACHING = False 
    return _ALL_SCHEDULES_CACHE

async def search_teacher_schedule(teacher_name: str) -> str:
    all_lessons = await _fetch_all_schedules()
    if not all_lessons:
        return ""
    teacher_upper = teacher_name.strip().upper()
    found = [lsn for lsn in all_lessons if lsn['oqituvchi'].lower() != "noma'lum" and teacher_upper in lsn['oqituvchi'].upper()]
    if not found:
        return ""
    result = f"👨‍🏫 <b>{teacher_upper} ishtirokidagi darslar:</b>\n\n"
    for lsn in found:
        result += (
            f"📅 <b>{lsn['sana']}</b>\n"
            f"👥 Guruh: {lsn['guruh_nomi']}\n"
            f"⏱ Vaqt: {lsn['juftlik']} [{lsn['boshlanish_vaqti']} - {lsn['tugash_vaqti']}]\n"
            f"📖 Fan: {lsn['fan']} ({lsn['dars_turi']})\n"
            f"📍 Auditoriya: {lsn['auditoriya']}\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
    return result

async def get_rooms_status_by_faculty(faculty_name: str, current_time: str = None) -> str:
    all_lessons = await _fetch_all_schedules()
    tz = timezone(timedelta(hours=5))
    now_dt = datetime.now(tz)
    today_str = now_dt.strftime("%d.%m.%Y")
    real_current_time = current_time if current_time else now_dt.strftime("%H:%M") 
    
    faculty_all_rooms = {}
    occupied_rooms = {}
    for lsn in all_lessons:
        raw_room = lsn.get('auditoriya', '').strip()
        if not raw_room or raw_room.lower() == "noma'lum":
            continue
        room_key = normalize_room_key(raw_room)
        if not room_key:
            continue
        if lsn.get('fakultet') == faculty_name:
            if room_key not in faculty_all_rooms:
                faculty_all_rooms[room_key] = raw_room
        if today_str in lsn['sana']:
            if lsn['boshlanish_vaqti'] <= real_current_time <= lsn['tugash_vaqti']:
                if room_key not in occupied_rooms:
                    occupied_rooms[room_key] = set()
                occupied_rooms[room_key].add(lsn['guruh_nomi'])
                
    if not faculty_all_rooms:
        return f"❌ <i>{faculty_name} uchun dars jadvalida aniq xonalar ko'rsatilmagan.</i>"
        
    result = f"🏢 <b>{faculty_name} dars xonalari ({real_current_time}):</b>\n\n"
    for room_key, original_room_name in sorted(faculty_all_rooms.items(), key=lambda x: x[1]):
        matched_groups = set(occupied_rooms.get(room_key, []))
        for occ_key, groups in occupied_rooms.items():
            if occ_key != room_key and len(room_key) > 4 and len(occ_key) > 4:
                if room_key in occ_key or occ_key in room_key:
                    matched_groups.update(groups)
        if matched_groups:
            result += f"❌ <b>{original_room_name}</b> — Band (<i>{', '.join(sorted(matched_groups))}</i>)\n"
        else:
            result += f"✅ <b>{original_room_name}</b> — Bo'sh\n"
    result += "\n<i>*Izoh: Ro'yxat jadvallardagi xonalar asosida avtomatik shakllantirildi.</i>"
    return result

async def get_all_teachers_stats() -> dict:
    all_lessons = await _fetch_all_schedules()
    teachers = {}
    for lsn in all_lessons:
        t_name = lsn['oqituvchi'].strip()
        if not t_name or t_name.lower() == "noma'lum":
            continue
        t_upper = t_name.upper()
        if t_upper not in teachers:
            teachers[t_upper] = {"faculty": lsn.get('fakultet', 'Boshqa fakultet'), "count": 0}
        teachers[t_upper]["count"] += 1
    return teachers

async def get_teachers_by_faculty(faculty_name: str) -> list:
    teachers_data = await get_all_teachers_stats()
    return sorted([{"name": n, "count": d["count"]} for n, d in teachers_data.items() if d["faculty"] == faculty_name], key=lambda x: x["name"])

async def search_teacher_by_keyword(keyword: str) -> list:
    teachers_data = await get_all_teachers_stats()
    kw = keyword.strip().upper()
    return sorted([{"name": n, "faculty": d["faculty"], "count": d["count"]} for n, d in teachers_data.items() if kw in n], key=lambda x: x["name"])
