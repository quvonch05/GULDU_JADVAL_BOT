import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime, timedelta, timezone

BASE_URL = "https://data.guldu.uz/dars"
_CACHED_GROUPS = {}  # Guruhlarni tez qidirish uchun xotira

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
    html = await fetch_html(f"{BASE_URL}/")
    soup = BeautifulSoup(html, 'html.parser')
    faculties = {}
    for a in soup.find_all('a'):
        fid = a.get('data-id')
        name = a.text.strip()
        if fid and name and name.lower() != "bosh sahifa":
            faculties[fid] = name
    return faculties

async def get_forms(fakul_id: str) -> dict:
    html = await fetch_html(f"{BASE_URL}/category.php?fakul_id={fakul_id}")
    soup = BeautifulSoup(html, 'html.parser')
    forms = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 't_shakli_id=' in href:
            tid = href.split('t_shakli_id=')[-1].split('&')[0]
            forms[tid] = a.text.strip()
    return forms

async def get_courses(fakul_id: str, t_shakli_id: str) -> dict:
    html = await fetch_html(f"{BASE_URL}/kurs.php?fakul_id={fakul_id}&t_shakli_id={t_shakli_id}")
    soup = BeautifulSoup(html, 'html.parser')
    courses = {}
    for a in soup.find_all('a'):
        href = a.get('href', '')
        if 'kursid=' in href:
            kid = href.split('kursid=')[-1].split('&')[0]
            courses[kid] = a.text.strip()
    return courses

async def get_groups(fakul_id: str, t_shakli_id: str, kursid: str) -> dict:
    html = await fetch_html(f"{BASE_URL}/group.php?kursid={kursid}&fraculid={fakul_id}&t_shakli_id={t_shakli_id}")
    soup = BeautifulSoup(html, 'html.parser')
    groups = {}
    for btn in soup.find_all('button', class_='btn'):
        gid = btn.get('data-groupid')
        name = " ".join(btn.text.split())
        if gid and name:
            groups[gid] = name
    return groups

async def search_group_id(target_name: str) -> str:
    """Guruh nomini yozganda uning ID sini butun saytdan qidirib topadi."""
    global _CACHED_GROUPS
    target = target_name.strip().upper()
    
    if not _CACHED_GROUPS:
        facs = await get_faculties()
        for fid in facs:
            forms = await get_forms(fid)
            for tid in forms:
                courses = await get_courses(fid, tid)
                for kid in courses:
                    groups = await get_groups(fid, tid, kid)
                    for gid, gname in groups.items():
                        _CACHED_GROUPS[gname.upper()] = gid
                        
    return _CACHED_GROUPS.get(target)

async def get_schedule_text(group_id: str, group_name: str, day_filter: str = "haftalik") -> str:
    url = f"{BASE_URL}/ll.php"
    html = await fetch_html(url, data={"datagroupid": str(group_id)})
    
    if not html.strip() or "dars jadvali" not in html.lower():
        return "Bu guruh uchun hozircha dars jadvali kiritilmagan."

    # O'zbekiston vaqtini aniqlash (UTC+5)
    tz = timezone(timedelta(hours=5))
    today_dt = datetime.now(tz)
    tomorrow_dt = today_dt + timedelta(days=1)
    
    today_str = today_dt.strftime("%d.%m.%Y")
    tomorrow_str = tomorrow_dt.strftime("%d.%m.%Y")

    soup = BeautifulSoup(html, 'html.parser')
    
    header_title = "To'liq haftalik dars jadvali"
    if day_filter == "bugun": header_title = "Bugungi dars jadvali"
    if day_filter == "ertaga": header_title = "Ertangi dars jadvali"
    
    result_text = f"👥 Guruh: <a href='https://data.guldu.uz'><b>{group_name}</b></a>\n📘 {header_title}\n\n"
    found_days = 0

    cols = soup.find_all('div', class_='col-md-12')
    for col in cols:
        date_p = col.find('p', class_='bg-primary')
        if date_p:
            date_text = " ".join(date_p.text.split())
            
            # Filtrlar
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
        result_text += f"Bunday sanada dars topilmadi 😴"

    return result_text.strip()