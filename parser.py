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

async def fetch_html(url: str, data: dict = None) -> str:
    async with aiohttp.ClientSession() as session:
        try:
            if data:
                async with session.post(url, data=data) as response:
                    if response.status == 200: return await response.text()
            else:
                async with session.get(url) as response:
                    if response.status == 200: return await response.text()
        except Exception as e:
            print(f"URL ga ulanishda xatolik: {e}")
    return ""

async def get_faculties() -> dict:
    if _CACHE_STRUCT['faculties']: return _CACHE_STRUCT['faculties']
    html = await fetch_html(f"{BASE_URL}/")
    soup = BeautifulSoup(html, 'html.parser')
    faculties = {}
    for a in soup.find_all('a'):
        fid = a.get('data-id')
        name = a.text.strip()
        if fid and name and name.lower() != "bosh sahifa":
            faculties[fid] = name
    _CACHE_STRUCT['faculties'] = faculties
    return faculties

async def get_forms(fakul_id: str) -> dict:
    if fakul_id in _CACHE_STRUCT['forms']: return _CACHE_STRUCT['forms'][fakul_id]
    html = await fetch_html(f"{BASE_URL}/category.php?fakul_id={fakul_id}")
    soup = BeautifulSoup(html, 'html.parser')
    forms = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 't_shakli_id=' in href:
            tid = href.split('t_shakli_id=')[-1].split('&')[0]
            forms[tid] = a.text.strip()
    _CACHE_STRUCT['forms'][fakul_id] = forms
    return forms

async def get_courses(fakul_id: str, t_shakli_id: str) -> dict:
    cache_key = f"{fakul_id}_{t_shakli_id}"
    if cache_key in _CACHE_STRUCT['courses']: return _CACHE_STRUCT['courses'][cache_key]
    html = await fetch_html(f"{BASE_URL}/kurs.php?fakul_id={fakul_id}&t_shakli_id={t_shakli_id}")
    soup = BeautifulSoup(html, 'html.parser')
    courses = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 'kursid=' in href:
            kid = href.split('kursid=')[-1].split('&')[0]
            courses[kid] = a.text.strip()
    _CACHE_STRUCT['courses'][cache_key] = courses
    return courses

async def get_groups(fakul_id: str, t_shakli_id: str, kursid: str) -> dict:
    cache_key = f"{fakul_id}_{t_shakli_id}_{kursid}"
    if cache_key in _CACHE_STRUCT['groups']: return _CACHE_STRUCT['groups'][cache_key]
    html = await fetch_html(f"{BASE_URL}/group.php?kursid={kursid}&fraculid={fakul_id}&t_shakli_id={t_shakli_id}")
    soup = BeautifulSoup(html, 'html.parser')
    groups = {}
    for btn in soup.find_all('button', class_='btn'):
        gid = btn.get('data-groupid')
        name = " ".join(btn.text.split())
        if gid and name:
            groups[gid] = name
    _CACHE_STRUCT['groups'][cache_key] = groups
    return groups

async def search_group_id(target_name: str) -> str:
    global _CACHED_GROUPS, _GROUP_FACULTY_MAP
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
                        _CACHED_GROUPS[g_upper] = gid
                        _GROUP_FACULTY_MAP[g_upper] = fname
                        
    return _CACHED_GROUPS.get(target)

async def get_schedule_text(group_id: str, group_name: str, day_filter: str = "haftalik") -> str:
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

    cols = soup.find_all('div', class_='col-md-12')
    for col in cols:
        date_p = col.find('p', class_='bg-primary')
        if date_p:
            date_text = " ".join(date_p.text.split())
            
            if day_filter == "bugun" and today_str not in date_text: continue
            if day_filter == "ertaga" and tomorrow_str not in date_text: continue
            
            found_days += 1
            result_text += f"━━━━━━━━━━━━━━━━━━━━\n📅 <b>{date_text}</b>\n━━━━━━━━━━━━━━━━━━━━\n"

        table = col.find('table')
        if table and (day_filter == "haftalik" or (day_filter == "bugun" and today_str in date_text) or (day_filter == "ertaga" and tomorrow_str in date_text)):
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
            result_text += f"Bunday sanada dars topilmadi 😴"

    return result_text.strip()

# =====================================================================
# QOTIB QOLISHNI OLDINI OLUVCHI XAVFSIZ KESHLASH LOGIKASI
# =====================================================================

async def _fetch_all_schedules():
    global _ALL_SCHEDULES_CACHE, _LAST_CACHE_TIME, _IS_CACHING
    
    if _IS_CACHING: return _ALL_SCHEDULES_CACHE
        
    tz = timezone(timedelta(hours=5))
    now = datetime.now(tz)
    
    if _LAST_CACHE_TIME and (now - _LAST_CACHE_TIME).total_seconds() < 600 and _ALL_SCHEDULES_CACHE:
        return _ALL_SCHEDULES_CACHE
        
    _IS_CACHING = True
    try:
        temp_cache = []
        
        if not _CACHED_GROUPS:
            await search_group_id("DUMMY_LOAD")
            
        sem = asyncio.Semaphore(5) 
        
        async def fetch_group(gname, gid, session):
            faculty_name = _GROUP_FACULTY_MAP.get(gname.upper(), "Boshqa")
            async with sem:
                try:
                    async with session.post(f"{BASE_URL}/ll.php", data={"datagroupid": str(gid)}) as resp:
                        if resp.status == 200:
                            html = await resp.text()
                            if not html or "dars jadvali" not in html.lower(): return
                            
                            soup = BeautifulSoup(html, 'html.parser')
                            current_date_text = "" 
                            
                            for col in soup.find_all('div', class_='col-md-12'):
                                date_p = col.find('p', class_='bg-primary')
                                if date_p:
                                    current_date_text = " ".join(date_p.text.split())
                                    
                                if not current_date_text: 
                                    continue
                                
                                table = col.find('table')
                                if not table: continue
                                
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
                                
                                j_match = re.search(r'(\d+-juftlik)', time_text, re.IGNORECASE)
                                juftlik = j_match.group(1) if j_match else ""
                                
                                tds = table.find_all('td')
                                if len(tds) >= 3:
                                    teacher = list(tds[0].stripped_strings)[-1] if len(list(tds[0].stripped_strings)) > 1 else ""
                                    s_parts = list(tds[1].stripped_strings)
                                    dars_turi = s_parts[0] if len(s_parts) > 1 else ""
                                    fan = " ".join(s_parts[1:]) if len(s_parts) > 1 else ""
                                    room = " ".join(list(tds[2].stripped_strings)[1:]) if len(list(tds[2].stripped_strings)) > 1 else ""
                                    
                                    if teacher and teacher.lower() != "noma'lum":
                                        temp_cache.append({
                                            "guruh_nomi": gname, 
                                            "sana": current_date_text, 
                                            "juftlik": juftlik,
                                            "boshlanish_vaqti": start_time, 
                                            "tugash_vaqti": end_time,
                                            "oqituvchi": teacher, 
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
        return "⏳ <i>Ma'lumotlar bazasi hozir avtomatik yangilanmoqda. Iltimos, 1 daqiqadan so'ng qayta urinib ko'ring...</i>"
        
    all_lessons = await _fetch_all_schedules()
    if not all_lessons: return ""
        
    teacher_upper = teacher_name.strip().upper()
    found = [lsn for lsn in all_lessons if teacher_upper in lsn['oqituvchi'].upper()]
            
    if not found: return ""
    
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
        return "⏳ <i>Bo'sh xonalar ro'yxati hozir avtomatik yangilanmoqda. Iltimos, 1 daqiqadan so'ng qayta urinib ko'ring...</i>"
        
    all_lessons = await _fetch_all_schedules()
    
    tz = timezone(timedelta(hours=5))
    now_dt = datetime.now(tz)
    today_str = now_dt.strftime("%d.%m.%Y")
    real_current_time = now_dt.strftime("%H:%M") 
    
    faculty_all_rooms = set()
    occupied_rooms = {}
    
    for lsn in all_lessons:
        room = lsn['auditoriya'].strip()
        if not room or room.lower() == "noma'lum": continue
            
        if lsn.get('fakultet') == faculty_name:
            faculty_all_rooms.add(room)
            
        if today_str in lsn['sana']:
            if lsn['boshlanish_vaqti'] <= real_current_time <= lsn['tugash_vaqti']:
                occupied_rooms[room] = lsn['guruh_nomi']
                
    if not faculty_all_rooms:
        return f"❌ <i>{faculty_name} uchun dars jadvalida aniq xonalar ko'rsatilmagan.</i>"
        
    result = f"🏢 <b>{faculty_name} dars xonalari ({real_current_time}):</b>\n\n"
    
    for room in sorted(faculty_all_rooms):
        if room in occupied_rooms:
            group_name = occupied_rooms[room]
            result += f"❌ <b>{room}</b> — Band (<i>{group_name}</i>)\n"
        else:
            result += f"✅ <b>{room}</b> — Bo'sh\n"
            
    result += "\n<i>*Izoh: Ro'yxat jadvallardagi xonalar asosida avtomatik shakllantirildi.</i>"
    return result

# =====================================================================
# YANgi: O'QITUVCHILARNI IZLASH VA SARALASH FUNKSIYALARI
# =====================================================================

async def get_all_teachers_stats() -> dict:
    """Barcha o'qituvchilarni fakulteti va dars soatlari soni bilan yig'ish"""
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
    """Tanlangan fakultetdagi o'qituvchilar ro'yxatini qaytaradi"""
    teachers_data = await get_all_teachers_stats()
    faculty_teachers = []
    
    for name, data in teachers_data.items():
        if data["faculty"] == faculty_name:
            faculty_teachers.append({"name": name, "count": data["count"]})
            
    # Alifbo tartibida saralash
    return sorted(faculty_teachers, key=lambda x: x["name"])

async def search_teacher_by_keyword(keyword: str) -> list:
    """Ism yoki familiya orqali o'qituvchilarni izlash"""
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
