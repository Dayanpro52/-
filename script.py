import telebot
from telebot import types
import time
import threading

TOKEN = "токен"
bot = telebot.TeleBot(TOKEN)

# ---------------- МОДЕЛИ ----------------

class Habit:
    def __init__(self, name, htype):
        self.name = name
        self.type = htype              # daily / once / interval
        self.time = None
        self.interval = None
        self.last_call = None

        self.reward = ""
        self.punishment = ""

        self.done = 0
        self.missed = 0
        self.streak = 0

        self.frozen = False
        self.waiting = False
        self.wait_start = None


class User:
    def __init__(self):
        self.habits = []
        self.state = None
        self.temp = None


users = {}

def get_user(uid):
    if uid not in users:
        users[uid] = User()
    return users[uid]

# ---------------- МЕНЮ ----------------

def main_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("➕ Добавить", "📋 Привычки")
    kb.add("📊 Статистика", "🧊 Архив")
    return kb

# ---------------- START ----------------

@bot.message_handler(commands=["start"])
def start(m):
    bot.send_message(
        m.chat.id,
        "👋 Я бот дисциплины.\n"
        "Я не мотивирую — я учитываю.",
        reply_markup=main_menu()
    )

# ---------------- ОБРАБОТКА ----------------

@bot.message_handler(content_types=["text"])
def handle(m):
    u = get_user(m.chat.id)
    t = m.text.strip()

    # --- меню ---
    if t == "➕ Добавить":
        u.state = "name"
        bot.send_message(m.chat.id, "✍️ Название привычки:")

    elif t == "📋 Привычки":
        bot.send_message(m.chat.id, habits_text(u), reply_markup=main_menu())

    elif t == "📊 Статистика":
        bot.send_message(m.chat.id, stats_text(u), reply_markup=main_menu())

    elif t == "🧊 Архив":
        bot.send_message(m.chat.id, archive_text(u), reply_markup=main_menu())

    # --- создание ---
    elif u.state == "name":
        u.temp = Habit(t, None)
        u.state = "type"
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("🔁 Ежедневная", "⏰ Одноразовая", "🔄 По интервалам")
        bot.send_message(m.chat.id, "Тип:", reply_markup=kb)

    elif u.state == "type":
        if "Еж" in t: u.temp.type = "daily"
        elif "Одно" in t: u.temp.type = "once"
        else: u.temp.type = "interval"
        u.state = "reward"
        bot.send_message(m.chat.id, "🏆 Награда:")

    elif u.state == "reward":
        u.temp.reward = t
        u.state = "punish"
        bot.send_message(m.chat.id, "⚠️ Наказание:")

    elif u.state == "punish":
        u.temp.punishment = t
        u.state = "interval" if u.temp.type == "interval" else "time"
        bot.send_message(
            m.chat.id,
            "🔢 Интервал в часах:" if u.temp.type == "interval" else "⏰ Время HH:MM"
        )

    elif u.state == "time":
        u.temp.time = t
        u.habits.append(u.temp)
        u.temp = None
        u.state = None
        bot.send_message(m.chat.id, "✅ Добавлено", reply_markup=main_menu())

    elif u.state == "interval":
        u.temp.interval = int(t)
        u.temp.last_call = time.time()
        u.habits.append(u.temp)
        u.temp = None
        u.state = None
        bot.send_message(m.chat.id, "✅ Добавлено", reply_markup=main_menu())

    # --- закончил ---
    elif t.startswith("✅ Закончил"):
        i = int(t.split("#")[1]) - 1
        h = u.habits[i]
        h.done += 1
        h.streak += 1
        h.waiting = False
        if h.type == "once":
            h.frozen = True
        bot.send_message(m.chat.id, f"🏆 Награда:\n{h.reward}")

    # --- заморозка ---
    elif t.startswith("🧊 Заморозить"):
        u.habits[int(t.split("#")[1])-1].frozen = True
        bot.send_message(m.chat.id, "🧊 Заморожено")

    elif t.startswith("🔥 Разморозить"):
        u.habits[int(t.split("#")[1])-1].frozen = False
        bot.send_message(m.chat.id, "🔥 Активно")

    # --- удалить ---
    elif t.startswith("🗑 Удалить"):
        u.habits.pop(int(t.split("#")[1])-1)
        bot.send_message(m.chat.id, "🗑 Удалено навсегда")

# ---------------- ТЕКСТЫ ----------------

def habits_text(u):
    if not u.habits:
        return "Пусто."
    s = "📋 Привычки:\n\n"
    for i,h in enumerate(u.habits,1):
        if h.frozen: continue
        s += (
            f"{i}. 🔥 {h.name}\n"
            f"   ✅ Закончил #{i}\n"
            f"   🧊 Заморозить #{i}\n"
            f"   🗑 Удалить #{i}\n\n"
        )
    return s

def archive_text(u):
    s = "🧊 Архив:\n\n"
    for i,h in enumerate(u.habits,1):
        if h.frozen:
            s += f"{i}. {h.name} | 🔥 Разморозить #{i}\n"
    return s if s != "🧊 Архив:\n\n" else "Архив пуст."

def stats_text(u):
    done = sum(h.done for h in u.habits)
    miss = sum(h.missed for h in u.habits)
    streak = max((h.streak for h in u.habits), default=0)
    total = done + miss
    percent = int((done/total)*100) if total else 0
    return (
        "📊 Статистика:\n\n"
        f"✅ Выполнено: {done}\n"
        f"❌ Пропущено: {miss}\n"
        f"🔥 Лучшая серия: {streak}\n"
        f"📈 Успех: {percent}%"
    )

# ---------------- НАПОМИНАНИЯ ----------------

def reminder():
    while True:
        now = time.strftime("%H:%M")
        cur = time.time()

        for uid,u in users.items():
            for i,h in enumerate(u.habits):
                if h.frozen: continue

                if h.waiting and cur - h.wait_start > 3600:
                    h.missed += 1
                    h.streak = 0
                    h.waiting = False
                    bot.send_message(uid, f"❌ Пропуск:\n{h.punishment}")

                trigger = (
                    (h.type=="daily" and h.time==now) or
                    (h.type=="once" and h.time==now) or
                    (h.type=="interval" and cur-h.last_call>=h.interval*3600)
                )

                if trigger and not h.waiting:
                    h.waiting = True
                    h.wait_start = cur
                    if h.type=="interval": h.last_call = cur
                    bot.send_message(
                        uid,
                        f"⏰ Пора НАЧАТЬ:\n{h.name}\n\n"
                        f"Когда закончишь:\n✅ Закончил #{i+1}"
                    )
        time.sleep(60)

threading.Thread(target=reminder, daemon=True).start()
bot.infinity_polling()
