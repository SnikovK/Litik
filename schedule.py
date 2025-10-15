# schedule.py
import pandas as pd
from datetime import datetime, timedelta

# ожидаемые имена колонок (варианты)
EXPECTED = {
    "day": ["день", "day"],
    "time": ["время", "time"],
    "subject": ["предмет", "subject", "название"],
    "tag": ["тег", "tag", "хэштег", "hashtag"],
    "room": ["аудитория", "room", "кабинет"]
}

def find_column(cols, variants):
    for v in variants:
        for c in cols:
            if str(c).strip().lower() == v:
                return c
    # попытка частичного совпадения
    for v in variants:
        for c in cols:
            if v in str(c).strip().lower():
                return c
    return None

# Загрузка таблицы с валидацией
try:
    raw = pd.read_excel("РАСПИСАНЕИ.xlsx")
except Exception as e:
    raise RuntimeError(f"Не удалось загрузить РАСПИСАНЕИ.xlsx: {e}")

cols = list(raw.columns)
col_day = find_column(cols, EXPECTED["day"])
col_time = find_column(cols, EXPECTED["time"])
col_subject = find_column(cols, EXPECTED["subject"])
col_tag = find_column(cols, EXPECTED["tag"])
col_room = find_column(cols, EXPECTED["room"])

missing = [name for name, c in (("День", col_day), ("Время", col_time),
                                ("Предмет", col_subject), ("Тег", col_tag),
                                ("Аудитория", col_room)) if c is None]
if missing:
    raise RuntimeError(f"В файле расписания не найдены колонки: {missing}. Найденные колонки: {cols}")

# переименуем для удобства
SCHEDULE = raw.rename(columns={
    col_day: "День",
    col_time: "Время",
    col_subject: "Предмет",
    col_tag: "Тег",
    col_room: "Аудитория"
}).copy()

# очистка строк
for c in ["День", "Время", "Предмет", "Тег", "Аудитория"]:
    SCHEDULE[c] = SCHEDULE[c].astype(str).str.strip().replace({"nan": ""})

# нормализация названий дней
MAP_DAYS = {
    "monday": "Понедельник", "tuesday": "Вторник", "wednesday": "Среда",
    "thursday": "Четверг", "friday": "Пятница", "saturday": "Суббота",
    "sunday": "Воскресенье",
    "понедельник": "Понедельник", "вторник": "Вторник", "среда": "Среда",
    "четверг": "Четверг", "пятница": "Пятница", "суббота": "Суббота",
    "воскресенье": "Воскресенье"
}

def normalize_day_name(d):
    if not d: 
        return ""
    key = str(d).strip().lower()
    return MAP_DAYS.get(key, d.strip())

SCHEDULE["День"] = SCHEDULE["День"].apply(normalize_day_name)

# --- функции API ---
def get_day_schedule(user_tags, day: str = None) -> str:
    """Возвращает текст-расписание на указанный день (или сегодня)."""
    now = datetime.now()
    if day is None:
        day_name = normalize_day_name(now.strftime("%A"))
    else:
        day_name = normalize_day_name(day)

    df = SCHEDULE[(SCHEDULE["День"] == day_name) & (SCHEDULE["Тег"].isin(user_tags))]
    if df.empty:
        return f"📅 На {day_name} по вашим подпискам пар нет."

    lines = [f"📅 Расписание на {day_name}:"]
    for _, r in df.iterrows():
        lines.append(f"⏰ {r['Время']} — {r['Предмет']} ({r['Тег']})\n📍 Кабинет: {r['Аудитория']}")
    return "\n\n".join(lines)
def get_next_class(user_tags) -> str:
    """Возвращает ближайшую или текущую пару сегодня для данных тегов."""
    now = datetime.now()
    today = normalize_day_name(now.strftime("%A"))

    df = SCHEDULE[(SCHEDULE["День"] == today) & (SCHEDULE["Тег"].isin(user_tags))].copy()
    if df.empty:
        return "📅 Сегодня по вашим подпискам пар нет."

    candidates = []
    for _, r in df.iterrows():
        t = r["Время"]
        if not t:
            continue
        start, end = t.split("-")[0].strip(), t.split("-")[1].strip()
        try:
            st = datetime.strptime(start, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
            en = datetime.strptime(end, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        except Exception:
            continue

        if st <= now <= en:
            # Пара идёт прямо сейчас
            return f"▶ Сейчас идёт пара:\n⏰ {r['Время']} — {r['Предмет']} ({r['Тег']})\n📍 Кабинет: {r['Аудитория']}"
        elif st > now:
            candidates.append((st, r))

    if not candidates:
        return "✅ Сегодня пары уже закончились."

    candidates.sort(key=lambda x: x[0])
    st, row = candidates[0]
    minutes = int((st - now).total_seconds() // 60)
    return f"⏭ Следующая пара через {minutes} мин.\n\n⏰ {row['Время']} — {row['Предмет']} ({row['Тег']})\n📍 Кабинет: {row['Аудитория']}"


# --- новые функции для бота ---
def get_next_day_schedule(user_tags) -> str:
    """Возвращает расписание на следующий день по тегам."""
    next_day = datetime.now() + timedelta(days=1)
    return get_day_schedule(user_tags, day=next_day.strftime("%A"))

def get_week_schedule(user_tags) -> str:
    """Возвращает расписание на ближайшую неделю (7 дней) по тегам."""
    now = datetime.now()
    lines = []
    for i in range(7):
        day = now + timedelta(days=i)
        day_text = get_day_schedule(user_tags, day=day.strftime("%A"))
        lines.append(day_text)
    return "\n\n".join(lines)

# --- утилита для /debug ---
def preview(n=10):
    return SCHEDULE.head(n).to_dict(orient="records")
