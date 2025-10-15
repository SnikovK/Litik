import asyncio
import re
import sqlite3
from aiogram import Bot, Dispatcher, Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, BotCommand
from aiogram.utils.keyboard import InlineKeyboardBuilder
import traceback


from schedule import get_day_schedule, get_next_class
from schedule import get_next_day_schedule, get_week_schedule

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

MOSCOW_TZ = ZoneInfo("Europe/Moscow")

API_TOKEN = ""

bot = Bot(token=API_TOKEN)
dp = Dispatcher()
router = Router()

# --- главное меню ---
main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📚 Подписки"), KeyboardButton(text="📅 Расписание")],
        [KeyboardButton(text="ℹ️ Помощь")]
    ],
    resize_keyboard=True
)

# --- база данных ---
conn = sqlite3.connect("subscriptions.db")
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER,
    hashtag TEXT
)
""")
conn.commit()

def add_subscription(user_id: int, hashtag: str):
    cursor.execute("INSERT INTO subscriptions (user_id, hashtag) VALUES (?, ?)", (user_id, hashtag))
    conn.commit()

def remove_subscription(user_id: int, hashtag: str):
    cursor.execute("DELETE FROM subscriptions WHERE user_id=? AND hashtag=?", (user_id, hashtag))
    conn.commit()

def remove_all_subscriptions(user_id: int):
    cursor.execute("DELETE FROM subscriptions WHERE user_id=?", (user_id,))
    conn.commit()

def get_subscriptions(user_id: int):
    cursor.execute("SELECT hashtag FROM subscriptions WHERE user_id=?", (user_id,))
    return [row[0] for row in cursor.fetchall()]

def get_users_by_hashtag(hashtag: str):
    cursor.execute("SELECT user_id FROM subscriptions WHERE hashtag=?", (hashtag,))
    return [row[0] for row in cursor.fetchall()]

# --- доступные хэштеги ---
AVAILABLE_TAGS = {
    "Новости курса": ["#важно","#лекция", "#новость", "#рассылка"],
    "Мастерские": ["#юзефович", "#сидоров", "#арутюнов", "#чередниченко_мастер", "#нагимов", "#торопцев"],
    "Теор. и практ. стилистика": ["#папян", "#ткаченко", "#шитькова", "#годенко"],
    "Зарубеж. литература": ["#попов", "#муратова"],
    "Русская литература": ["#болычев", "#кожухаров", "#кольцова"],
    "Эйкономикс": ["#царёва1", "#царёва2"],
    "Современка": ["#дьячкова", "#болычевСовр", "#кожухаровСовр"],
    "История критики": ["#чередниченко"],
    "История искусств": ["#юрчик"],
    "Введение в лит. процесс": ["#чупринин"],
    "Спецкурс": ["#саленко", "#есаулов"],
    "Литература страны изучаемого языка": ["#казнина", "#латфуллина", "#липкин", "#попов_пер"],
    "Иностранный язык": ["#гладилин", "#латфуллина", "#липкин"],
    "Спецкурс переводчики": ["#гвоздева", "#городецкий", "#артамонова", "#кешокова", "#можаева"],
}

# --- команды ---
@router.message(Command("start"))
async def start(message: Message):
    await message.answer(
        "Привет! Меня зовут Литик. Используй меню ниже 👇",
        reply_markup=main_menu
    )
# --- обработка кнопок главного меню ---
@router.message(F.text == "📚 Подписки")
async def menu_tags(message: Message):
    await tags(message)


@router.message(F.text == "📅 Расписание")
async def menu_schedule(message: Message):
    await schedule_cmd(message)


@router.message(F.text == "ℹ️ Помощь")
async def menu_help(message: Message):
    await help_command(message)

@router.message(Command("tags"))
async def tags(message: Message):
    for category, tags in AVAILABLE_TAGS.items():
        kb = InlineKeyboardBuilder()
        for tag in tags:
            kb.add(InlineKeyboardButton(text=tag, callback_data=f"subscribe:{tag}"))
        kb.adjust(2)
        await message.answer(f"📚 <b>{category}</b>", parse_mode="HTML", reply_markup=kb.as_markup())

    kb_main = InlineKeyboardBuilder()
    kb_main.add(InlineKeyboardButton(text="📌 Мои подписки", callback_data="show_mytags"))
    kb_main.add(InlineKeyboardButton(text="❌ Отписаться от всех", callback_data="unsubscribe_all"))
    await message.answer("🔽 Управление:", reply_markup=kb_main.as_markup())

@router.message(Command("schedule"))
async def schedule_cmd(message: Message):
    try:
        await message.answer("Выберите вариант расписания:", reply_markup=schedule_keyboard())
    except Exception as e:
        await message.answer(f"Ошибка при загрузке расписания: {e}")

@router.callback_query(F.data.startswith("subscribe:"))
async def subscribe_button(callback: CallbackQuery):
    tag = callback.data.split(":")[1]
    user_id = callback.from_user.id
    current = get_subscriptions(user_id)
    if tag in current:
        remove_subscription(user_id, tag)
        await callback.answer(f"❌ Отписка от {tag}")
    else:
        add_subscription(user_id, tag)
        await callback.answer(f"✅ Подписка на {tag}")

@router.callback_query(F.data == "show_mytags")
async def show_mytags(callback: CallbackQuery):
    tags = get_subscriptions(callback.from_user.id)
    text = "📌 Твои подписки:\n" + "\n".join(tags) if tags else "У тебя пока нет подписок"
    await callback.message.answer(text)
    await callback.answer()

@router.callback_query(F.data == "unsubscribe_all")
async def unsubscribe_all_button(callback: CallbackQuery):
    remove_all_subscriptions(callback.from_user.id)
    await callback.message.answer("❌ Ты отписался от всех тегов")
    await callback.answer()

@router.message(Command("mytags"))
async def mytags_cmd(message: Message):
    tags = get_subscriptions(message.from_user.id)
    text = "📌 Твои подписки:\n" + "\n".join(tags) if tags else "У тебя пока нет подписок"
    await message.answer(text)

@router.message(Command("day"))
async def send_day_schedule(message: Message):
    user_id = message.from_user.id
    try:
        user_tags = get_subscriptions(user_id)
        print(f"[DAY] user={user_id} tags={user_tags}")   # log в консоль
    except Exception as e:
        traceback.print_exc()
        await message.answer("Ошибка доступа к базе подписок. Смотри логи.")
        return

    if not user_tags:
        await message.answer("❗ Сначала подпишитесь на теги через /tags")
        return

    try:
        text = get_day_schedule(user_tags)
    except Exception as e:
        traceback.print_exc()
        await message.answer("Ошибка при формировании расписания. Смотри логи сервера.")
        return

    if not text:
        await message.answer("По вашим подпискам расписание не найдено.")
        return

    await message.answer(text, parse_mode="Markdown")

# команда для дебага содержимого расписания (видно только тебе)
@router.message(Command("debug"))
async def cmd_debug(message: Message):
    user_id = message.from_user.id
    # показываем превью расписания и колонки
    try:
        preview = preview  # функция в schedule.py
        from schedule import preview as schedule_preview
        head = schedule_preview(10)
        text = f"Preview (first rows):\n{head}"
    except Exception as e:
        import traceback; traceback.print_exc()
        text = f"Ошибка при доступе к расписанию: {e}"
    await message.answer(f"🔎 Debug info:\nUser tags: {get_subscriptions(user_id)}\n\n{str(text)}")

@router.message(Command("next"))
async def send_next_class(message: Message):
    user_tags = get_subscriptions(message.from_user.id)
    if not user_tags:
        await message.answer("❗ Сначала подпишись на теги через /tags")
        return
    text = get_next_class(user_tags)
    await message.answer(text, parse_mode="Markdown")
# --- отписаться от всех через команду ---
@router.message(Command("unsubscribe_all"))
async def unsubscribe_all_cmd(message: Message):
    remove_all_subscriptions(message.from_user.id)
    await message.answer("❌ Ты отписался от всех тегов")

# --- подписка через команду ---
@router.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❗ Используй: /subscribe #тег")
        return
    tag = parts[1]
    if not tag.startswith("#"):
        await message.answer("❗ Тег должен начинаться с #")
        return

    current = get_subscriptions(message.from_user.id)
    if tag in current:
        await message.answer(f"⚠️ Ты уже подписан на {tag}")
    else:
        add_subscription(message.from_user.id, tag)
        await message.answer(f"✅ Подписка на {tag} оформлена")

# --- отписка через команду ---
@router.message(Command("unsubscribe"))
async def unsubscribe_cmd(message: Message):
    parts = message.text.split()
    if len(parts) < 2:
        await message.answer("❗ Используй: /unsubscribe #тег")
        return
    tag = parts[1]

    current = get_subscriptions(message.from_user.id)
    if tag not in current:
        await message.answer(f"⚠️ Ты не подписан на {tag}")
    else:
        remove_subscription(message.from_user.id, tag)
        await message.answer(f"❌ Отписка от {tag} выполнена")

@router.message(Command("nextday"))
async def nextday_cmd(message: Message):
    user_tags = get_subscriptions(message.from_user.id)
    if not user_tags:
        await message.answer("❗ Сначала подпишитесь на теги через /tags")
        return
    text = get_next_day_schedule(user_tags)
    await message.answer(text, parse_mode="Markdown")

@router.message(Command("week"))
async def week_cmd(message: Message):
    user_tags = get_subscriptions(message.from_user.id)
    if not user_tags:
        await message.answer("❗ Сначала подпишитесь на теги через /tags")
        return

    from datetime import datetime, timedelta
    now = datetime.now(MOSCOW_TZ)

    # Отправляем расписание по дням
    for i in range(7):
        day = now + timedelta(days=i)
        day_text = get_day_schedule(user_tags, day=day.strftime("%A"))
        await message.answer(day_text, parse_mode="Markdown")

# --- клавиатура расписания ---
def schedule_keyboard():
    kb = InlineKeyboardBuilder()
    kb.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data="schedule_day"),
        InlineKeyboardButton(text="📅 Завтра", callback_data="schedule_nextday"),
    )
    kb.row(
        InlineKeyboardButton(text="📅 Неделя", callback_data="schedule_week"),
    )
    return kb.as_markup()

# --- обработка нажатий кнопок расписания ---
@router.callback_query(F.data.startswith("schedule_"))
async def schedule_buttons(callback: CallbackQuery):
    user_tags = get_subscriptions(callback.from_user.id)
    if not user_tags:
        await callback.message.answer("❗ Сначала подпишитесь на теги через /tags")
        await callback.answer()
        return

    if callback.data == "schedule_day":
        text = get_day_schedule(user_tags)
        await callback.message.answer(text, parse_mode="Markdown")

    elif callback.data == "schedule_nextday":
        text = get_next_day_schedule(user_tags)
        await callback.message.answer(text, parse_mode="Markdown")

    elif callback.data == "schedule_week":
        text = get_week_schedule(user_tags)
        await callback.message.answer(text, parse_mode="Markdown")

    await callback.answer()
    
# --- помощь ---
@router.message(Command("help"))
async def help_command(message: Message):
    text = (
        "Бот призван помочь получать информацию только о тех семинарах/лекциях, которые вам нужны.\n\nВы сами выбирате на что подписываться, а бот просто пересылает вам сообщение с хэштегом из общекурсового чата.\n\n "
        "📝 Доступные команды:\n\n"
        "/tags – открывает меню подписок\n"
        "/mytags - показать мои подписки \n"
        "/unsubscribe_all – отписаться сразу от всех, а почему бы и нет?\n"
        "/subscribe – подписаться, например /subscribe #папян \n"
        "/unsubscribe – отписаться, например /unsubscribe #папян - не рекомендую() \n"
        "/day – расписание на текущий день \n"
        "/next – узнать какая следующая пара \n"
        "/nextday – расписание на следующий день \n"
        "/week – расписание на текущую неделю\n\n"
        "Важно! Для корректного отображения расписания необходимо подписаться на всех своих семинарских! преподавателей и на хэштег #лекция.\n"
        "То есть если вы в семинарской группе у Годенко, то на Папяна подписываться не нужно!\n"
        "У переводчиков пока расписание не сделано((\n"
        "По всем вопросам касательно бота, пишите сюда @Snikov"  
    )
    await message.answer(text)
# --- установка команд в меню Telegram ---    
async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Запуск бота"),
        BotCommand(command="help", description="Помощь"),
        BotCommand(command="tags", description="Управление подписками"),
        BotCommand(command="mytags", description="Мои подписки"),
        BotCommand(command="day", description="Расписание на сегодня"),
        BotCommand(command="next", description="Следующая пара"),
        BotCommand(command="nextday", description="Расписание на завтра"),
        BotCommand(command="week", description="Расписание на неделю"),
        BotCommand(command="schedule", description="Меню расписания"),
    ]
    await bot.set_my_commands(commands)

# --- пересылка постов ---
@router.message()
async def catch_posts(message: Message):
    hashtags = re.findall(r"#\w+", (message.text or message.caption or ""))
    if not hashtags:
        return
    sent_to = set()
    for tag in hashtags:
        for user_id in get_users_by_hashtag(tag):
            if user_id not in sent_to:
                try:
                    await bot.forward_message(user_id, message.chat.id, message.message_id)
                    sent_to.add(user_id)
                except:
                    pass

dp.include_router(router)

async def main():
    print("Бот запущен...")
    await set_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

