import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone
import re
import asyncio

BASE_URL = "https://data.guldu.uz/dars"
_CACHED_GROUPS = {}  
_GROUP_FACULTY_MAP = {} 

_ALL_SCHEDULES_CACHE = []
_LAST_CACHE_TIME = None
_IS_CACHING = False 
_CACHE_STRUCT = {'faculties': None, 'forms': {}, 'courses': {}, 'groups': {}}

def clear_all_caches():
    """Bot xotirasidagi barcha eskirgan ma'lumotlarni tozalaydi"""
    global _CACHE_STRUCT, _CACHED_GROUPS, _GROUP_FACULTY_MAP, _ALL_SCHEDULES_CACHE, _LAST_CACHE_TIME
    _CACHE_STRUCT = {'faculties': None, 'forms': {}, 'courses': {}, 'groups': {}}
    _CACHED_GROUPS = {}
    _GROUP_FACULTY_MAP = {}
    _ALL_SCHEDULES_CACHE = []
    _LAST_CACHE_TIME = None

def normalize_room_key(name: str) -> str:
    """
    Xona nomini bino nomi bilan birga standart holatga keltiradi.
    Masalan: '517-auditoriya (Bosh bino)' va '517-xona (Bosh bino)' -> '517-xona (bosh bino)'
    Bu orqali 101-xona (2-maktab) va 101-xona (Bosh bino) bir-biri bilan aralashib ketmaydi!
    """
    if not name:
        return ""
    cleaned = " ".join(name.strip().lower().split())
    cleaned = cleaned.replace("auditoriya", "xona")
    # Defis atrofidagi ortiqcha bo'sh joylarni birlashtirish: "517 - xona" -> "517-xona"
    cleaned = re.sub(r'\s*-\s*', '-', cleaned)
    return cleaned

async def fetch_html(url: str, data: dict = None, retries: int = 3) -> str:
    """Saytdan ma'lumot olish (uzilishlar bo'lsa qayta urinish bilan)"""
    timeout = aiohttp.ClientTimeout(total=15)
    for attempt in range(retries):
        await asyncio.sleep(0.05)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                if data:
                    async with session.post(url, data=data) as response:
                        if response.status == 200:
                            text = await response.text()
                            if text.strip():
                                return text
                else:
                    async with session.get(url) as response:
                        if response.status == 200:
                            text = await response.text()
                            if text.strip():
                                return text
        except Exception as e:
            if attempt == retries - 1:
                print(f"URL ga ulanishda xatolik ({url}): {e}")
            await asyncio.sleep(0.3)
    return ""

async def get_faculties() -> dict:
    if _CACHE_STRUCT['faculties']:
        return _CACHE_STRUCT['faculties']
    html = await fetch_html(f"{BASE_URL}/")
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
    if fakul_id in _CACHE_STRUCT['forms']:
        return _CACHE_STRUCT['forms'][fakul_id]
    html = await fetch_html(f"{BASE_URL}/category.php?fakul_id={fakul_id}")
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
    if cache_key in _CACHE_STRUCT['courses']:
        return _CACHE_STRUCT['courses'][cache_key]
    html = await fetch_html(f"{BASE_URL}/kurs.php?fakul_id={fakul_id}&t_shakli_id={t_shakli_id}")
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
    if cache_key in _CACHE_STRUCT['groups']:
        return _CACHE_STRUCT['groups'][cache_key]
    
    # MUHIM TUZATISH: 'fraculid' xatosi tuzatildi, 'fakul_id' va 'fakulid' yuboriladi
    url = f"{BASE_URL}/group.php?kursid={kursid}&fakul_id={fakul_id}&fakulid={fakul_id}&t_shakli_id={t_shakli_id}"
    html = await fetch_html(url)
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

async def search_group_id(target_name: str) -> str:
    global _CACHED_GROUPS, _GROUP_FACULTY_MAP
    if not target_name:
        return None
    target = target_name.strip().upper()
    
    if not _CACHED_GROUPS:
        facs = await get_faculties()
        for fid, fname in facs.items():
            forms = await get_forms(fid)
            for tid in forms:
                courses = await get_courses(fid, tid)
                for kid in courses:
                    groups = await get_groups(fid, tid, kid)
                    for gid, gname in groups.items():
                        g_upper = gname.upper()
                        # Agar guruh oldin boshqa fakultetga yozilmagan bo'lsagina saqlaymiz
                        if g_upper not in _CACHED_GROUPS:
                            _CACHED_GROUPS[g_upper] = gid
                            _GROUP_FACULTY_MAP[g_upper] = fname
                        
    return _CACHED_GROUPS.get(target)

async def get_schedule_text(group_id: str, group_name: str, day_filter: str = "haftalik") -> str:
    # MUHIM HIMOYA: Agar group_id raqam bo'lmasa (masalan, bazadan guruh nomi kelsa yoki None bo'lsa)
    real_gid = str(group_id).strip() if group_id else ""
    if not real_gid.isdigit():
        found_id = await search_group_id(group_name or real_gid)
        if found_id:
            real_gid = str(found_id)

    url = f"{BASE_URL}/ll.php"
    html = await fetch_html(url, data={"datagroupid": real_gid})
    
    # Agar birinchi urinishda topilmasa, guruh nomi orqali ID ni qayta tekshirib ko'ramiz
    if (not html.strip() or "dars jadvali" not in html.lower()) and group_name:
        alt_gid = await search_group_id(group_name)
        if alt_gid and str(alt_gid) != real_gid:
            html = await fetch_html(url, data={"datagroupid": str(alt_gid)})

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
            if table and current_date_text and (
                day_filter == "haftalik" or 
                (day_filter == "bugun" and today_str in current_date_text) or 
                (day_filter == "ertaga" and tomorrow_str in current_date_text)
            ):
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
    
    # Agar hozir keshlanayotgan bo'lsa, tugashini kutamiz (bo'sh ro'yxat qaytarib yubormaslik uchun)
    while _IS_CACHING:
        await asyncio.sleep(0.5)
        if _ALL_SCHEDULES_CACHE:
            return _ALL_SCHEDULES_CACHE
        
    tz = timezone(timedelta(hours=5))
    now = datetime.now(tz)
    
    if _ALL_SCHEDULES_CACHE:
        return _ALL_SCHEDULES_CACHE
        
    _IS_CACHING = True
    try:
        temp_cache = []
        
        if not _CACHED_GROUPS:
            await search_group_id("DUMMY_LOAD")
            
        sem = asyncio.Semaphore(10) 
        
        async def fetch_group(gname, gid, session):
            faculty_name = _GROUP_FACULTY_MAP.get(gname.upper(), "Boshqa")
            async with sem:
                await asyncio.sleep(0.05)
                try:
                    async with session.post(f"{BASE_URL}/ll.php", data={"datagroupid": str(gid)}) as resp:
                        if resp.status == 200:
                            html = await resp.text()
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
                                
                                tables = col.find_all('table')
                                for table in tables:
                                    time_th = table.find('th')
                                    time_text = " ".join(time_th.text.split()) if time_th else ""
                                    
                                    times = re.findall(r'\d{1,2}:\d{2}', time_text)
                                    if len(times) > 0:
                                        st_parts = times[0].split(":")
                                        start_time = f"{int(st_parts[0]):02d}:{st_parts[1]}"
                                    else:
                                        start_time = "00:00"
                                        
                                    if len(times) > 1:
                                        en_parts = times[1].split(":")
                                        end_time = f"{int(en_parts[0]):02d}:{en_parts[1]}"
                                    else:
                                        end_time = "23:59"
                                    
                                    j_match = re.search(r'(\d+)\s*-?\s*juftlik', time_text, re.IGNORECASE)
                                    juftlik_raqami = j_match.group(1) if j_match else ""
                                    juftlik = f"{juftlik_raqami}-juftlik" if juftlik_raqami else ""
                                    
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
                                                "guruh_nomi": gname, 
                                                "sana": current_date_text, 
                                                "juftlik": juftlik,
                                                "juftlik_raqami": juftlik_raqami,
                                                "boshlanish_vaqti": start_time, 
                                                "tugash_vaqti": end_time,
                                                "oqituvchi": teacher if teacher else "Noma'lum", 
                                                "fan": fan, 
                                                "dars_turi": dars_turi, 
                                                "auditoriya": room,
                                                "fakultet": faculty_name
                                            })
                except Exception:
                    pass

        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as main_session:
            tasks = [fetch_group(gname, gid, main_session) for gname, gid in _CACHED_GROUPS.items()]
            await asyncio.gather(*tasks, return_exceptions=True) 
        
        if temp_cache:
            _ALL_SCHEDULES_CACHE = temp_cache
            _LAST_CACHE_TIME = now
            
    finally:
        _IS_CACHING = False 
        
    return _ALL_SCHEDULES_CACHE

async def search_teacher_schedule(teacher_name: str) -> str:
    if _IS_CACHING and not _ALL_SCHEDULES_CACHE:
        return "⏳ <i>Ma'lumotlar bazasi hozir avtomatik yangilanmoqda. Iltimos, 15 soniyadan so'ng qayta urinib ko'ring...</i>"
        
    all_lessons = await _fetch_all_schedules()
    if not all_lessons:
        return ""
        
    teacher_upper = teacher_name.strip().upper()
    found = [
        lsn for lsn in all_lessons 
        if lsn['oqituvchi'].lower() != "noma'lum" and teacher_upper in lsn['oqituvchi'].upper()
    ]
            
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
    if _IS_CACHING and not _ALL_SCHEDULES_CACHE:
        return "⏳ <i>Bo'sh xonalar ro'yxati hozir avtomatik yangilanmoqda. Iltimos, 15 soniyadan so'ng qayta urinib ko'ring...</i>"
        
    all_lessons = await _fetch_all_schedules()
    
    tz = timezone(timedelta(hours=5))
    now_dt = datetime.now(tz)
    today_str = now_dt.strftime("%d.%m.%Y")
    real_current_time = current_time if current_time else now_dt.strftime("%H:%M") 
    
    faculty_all_rooms = {}  # {room_key: original_room_name}
    occupied_rooms = {}     # {room_key: set(guruh_nomlari)}
    
    target_faculty = faculty_name.strip()
    
    for lsn in all_lessons:
        # FAQAT tanlangan fakultetga tegishli guruhlar va xonalarni olamiz
        if lsn.get('fakultet', '').strip() != target_faculty:
            continue
            
        raw_room = lsn.get('auditoriya', '').strip()
        if not raw_room or raw_room.lower() == "noma'lum":
            continue
            
        room_key = normalize_room_key(raw_room)
        if not room_key:
            continue
            
        # Fakultetga tegishli xonalar ro'yxatiga qo'shish
        if room_key not in faculty_all_rooms:
            faculty_all_rooms[room_key] = raw_room
            
        # Bugun va hozirgi dars vaqti oralig'ida shu xonada darsi bor shu fakultet guruhlarini yig'ish
        if today_str in lsn['sana']:
            if lsn['boshlanish_vaqti'] <= real_current_time <= lsn['tugash_vaqti']:
                if room_key not in occupied_rooms:
                    occupied_rooms[room_key] = set()
                occupied_rooms[room_key].add(lsn['guruh_nomi'])

    if not faculty_all_rooms:
        return f"❌ <i>{faculty_name} uchun dars jadvalida aniq xonalar ko'rsatilmagan.</i>"
        
    result = f"🏢 <b>{faculty_name} dars xonalari ({real_current_time}):</b>\n\n"
    
    sorted_rooms = sorted(faculty_all_rooms.items(), key=lambda x: x[1])
    
    for room_key, original_room_name in sorted_rooms:
        matched_groups = occupied_rooms.get(room_key, set())
        
        if matched_groups:
            groups_str = ", ".join(sorted(matched_groups))
            result += f"❌ <b>{original_room_name}</b> — Band (<i>{groups_str}</i>)\n"
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
            teachers[t_upper] = {
                "faculty": lsn.get('fakultet', 'Boshqa fakultet'),
                "count": 0
            }
        teachers[t_upper]["count"] += 1
        
    return teachers

async def get_teachers_by_faculty(faculty_name: str) -> list:
    teachers_data = await get_all_teachers_stats()
    faculty_teachers = []
    
    for name, data in teachers_data.items():
        if data["faculty"] == faculty_name:
            faculty_teachers.append({"name": name, "count": data["count"]})
            
    return sorted(faculty_teachers, key=lambda x: x["name"])

async def search_teacher_by_keyword(keyword: str) -> list:
    teachers_data = await get_all_teachers_stats()
    keyword_upper = keyword.strip().upper()
    results = []
    
    for name, data in teachers_data.items():
        if keyword_upper in name:
            results.append({
                "name": name, 
                "faculty": data["faculty"],
                "count": data["count"]
            })
            
    return sorted(results, key=lambda x: x["name"])
