import sqlite3
import random
from datetime import datetime, timezone, timedelta

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# =========================
# SETTINGS
# =========================

TOKEN = "PUT_YOUR_BOT_TOKEN_HERE"

DB_FILE = "coins_bot.db"

STARTING_COINS = 100
DAILY_COINS = 300
WIN_REWARD = 100
LOSS_AMOUNT = 50

# Miner settings
MINERS = {
    1: {"name": "⛏️ ماینر آهنی", "price": 500, "rate": 10},
    2: {"name": "⚙️ ماینر حرفه‌ای", "price": 2000, "rate": 30},
    3: {"name": "💎 ماینر الماسی", "price": 5000, "rate": 80},
}

# =========================
# DATABASE
# =========================

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            coins INTEGER NOT NULL DEFAULT 100,
            last_daily TEXT,
            miner_level INTEGER NOT NULL DEFAULT 0,
            miner_last_claim TEXT
        )
    """)
    conn.commit()

    # Migration for an older database made by the previous bot.
    columns = {
        row[1]
        for row in conn.execute("PRAGMA table_info(users)").fetchall()
    }

    if "miner_level" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN miner_level INTEGER NOT NULL DEFAULT 0"
        )

    if "miner_last_claim" not in columns:
        conn.execute(
            "ALTER TABLE users ADD COLUMN miner_last_claim TEXT"
        )

    conn.commit()
    return conn


def ensure_user(user):
    conn = get_db()

    row = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?",
        (user.id,),
    ).fetchone()

    if row is None:
        conn.execute(
            """
            INSERT INTO users
            (user_id, username, first_name, coins, last_daily,
             miner_level, miner_last_claim)
            VALUES (?, ?, ?, ?, NULL, 0, ?)
            """,
            (
                user.id,
                user.username,
                user.first_name,
                STARTING_COINS,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
    else:
        conn.execute(
            """
            UPDATE users
            SET username = ?, first_name = ?
            WHERE user_id = ?
            """,
            (user.username, user.first_name, user.id),
        )

    conn.commit()
    conn.close()


def get_coins(user_id):
    conn = get_db()
    row = conn.execute(
        "SELECT coins FROM users WHERE user_id = ?",
        (user_id,),
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def add_coins(user_id, amount):
    conn = get_db()
    conn.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (amount, user_id),
    )
    conn.commit()
    conn.close()


def has_coins(user_id, amount):
    return get_coins(user_id) >= amount


# =========================
# MENUS
# =========================

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "✊ سنگ کاغذ قیچی",
                callback_data="rps"
            )
        ],
        [
            InlineKeyboardButton(
                "🎲 تاس زوج/فرد",
                callback_data="dice"
            )
        ],
        [
            InlineKeyboardButton(
                "💰 موجودی",
                callback_data="balance"
            ),
            InlineKeyboardButton(
                "🎁 سکه روزانه",
                callback_data="daily"
            )
        ],
        [
            InlineKeyboardButton(
                "⛏️ ماینر",
                callback_data="miner"
            ),
            InlineKeyboardButton(
                "🏆 رتبه‌بندی",
                callback_data="ranking"
            )
        ],
        [
            InlineKeyboardButton(
                "💸 انتقال سکه",
                callback_data="transfer"
            )
        ],
    ])


def back_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "🔙 برگشت",
                callback_data="menu"
            )
        ]
    ])


def rps_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🪨 سنگ", callback_data="rps_rock"),
            InlineKeyboardButton("📄 کاغذ", callback_data="rps_paper"),
            InlineKeyboardButton("✂️ قیچی", callback_data="rps_scissors"),
        ],
        [
            InlineKeyboardButton("🔙 برگشت", callback_data="menu")
        ],
    ])


def dice_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔵 زوج", callback_data="dice_even"),
            InlineKeyboardButton("🔴 فرد", callback_data="dice_odd"),
        ],
        [
            InlineKeyboardButton("🔙 برگشت", callback_data="menu")
        ],
    ])


def miner_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(
                "⛏️ استخراج",
                callback_data="miner_claim"
            ),
            InlineKeyboardButton(
                "📊 ماینر من",
                callback_data="miner_info"
            ),
        ],
        [
            InlineKeyboardButton(
                "🛒 خرید / ارتقا",
                callback_data="miner_shop"
            )
        ],
        [
            InlineKeyboardButton(
                "🔙 برگشت",
                callback_data="menu"
            )
        ],
    ])


def miner_shop_menu():
    buttons = []

    for level, miner in MINERS.items():
        buttons.append([
            InlineKeyboardButton(
                f"{miner['name']} | {miner['price']} 🪙",
                callback_data=f"buy_miner_{level}",
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            "🔙 برگشت",
            callback_data="miner"
        )
    ])

    return InlineKeyboardMarkup(buttons)


# =========================
# MINER SYSTEM
# =========================

def get_miner(user_id):
    conn = get_db()

    row = conn.execute(
        """
        SELECT miner_level, miner_last_claim
        FROM users
        WHERE user_id = ?
        """,
        (user_id,),
    ).fetchone()

    conn.close()

    if row:
        return row[0], row[1]

    return 0, None


def set_miner(user_id, level):
    # Start the mining clock when the miner is bought/upgraded.
    now = datetime.now(timezone.utc).isoformat()

    conn = get_db()
    conn.execute(
        """
        UPDATE users
        SET miner_level = ?, miner_last_claim = ?
        WHERE user_id = ?
        """,
        (level, now, user_id),
    )
    conn.commit()
    conn.close()


def ready_miner_coins(user_id):
    level, last_claim = get_miner(user_id)

    if level <= 0:
        return 0

    if not last_claim:
        return 0

    try:
        last = datetime.fromisoformat(last_claim)
    except ValueError:
        return 0

    elapsed_seconds = int(
        (datetime.now(timezone.utc) - last).total_seconds()
    )

    hours = elapsed_seconds // 3600
    return hours * MINERS[level]["rate"]


def claim_miner(user_id):
    level, last_claim = get_miner(user_id)

    if level <= 0:
        return 0, "❌ شما هنوز ماینر ندارید."

    miner = MINERS[level]
    now = datetime.now(timezone.utc)

    if not last_claim:
        last = now
    else:
        try:
            last = datetime.fromisoformat(last_claim)
        except ValueError:
            last = now

    elapsed_seconds = int((now - last).total_seconds())
    hours = elapsed_seconds // 3600

    if hours <= 0:
        remaining = 3600 - elapsed_seconds
        minutes = max(1, remaining // 60)

        return (
            0,
            f"⏳ هنوز سکه‌ای آماده نیست.\n"
            f"حدود {minutes} دقیقه دیگر دوباره امتحان کن."
        )

    amount = hours * miner["rate"]

    # Give the mined coins.
    add_coins(user_id, amount)

    # Preserve leftover minutes/seconds.
    new_last = last + timedelta(hours=hours)

    conn = get_db()
    conn.execute(
        """
        UPDATE users
        SET miner_last_claim = ?
        WHERE user_id = ?
        """,
        (new_last.isoformat(), user_id),
    )
    conn.commit()
    conn.close()

    return amount, f"⛏️ استخراج انجام شد!\n🪙 +{amount} سکه"


# =========================
# LEADERBOARD
# =========================

def leaderboard(limit=10):
    conn = get_db()

    rows = conn.execute(
        """
        SELECT first_name, username, coins
        FROM users
        ORDER BY coins DESC, user_id ASC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    conn.close()
    return rows


def leaderboard_text(limit=10):
    rows = leaderboard(limit)

    if not rows:
        return "🏆 هنوز کاربری ثبت نشده است."

    lines = [
        f"🏆 ثروتمندترین کاربران — Top {limit}",
        ""
    ]

    for number, (first_name, username, coins) in enumerate(rows, 1):
        if username:
            name = "@" + username
        else:
            name = first_name or "کاربر"

        lines.append(
            f"{number}. {name} — 🪙 {coins}"
        )

    return "\n".join(lines)


# =========================
# GAME RESULT
# =========================

def probability_result():
    # 30% win / 30% loss / 40% draw
    value = random.random()

    if value < 0.30:
        return "win"

    if value < 0.60:
        return "loss"

    return "draw"


# =========================
# START / COMMANDS
# =========================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)

    await update.message.reply_text(
        "🎮 به ربات سکه خوش آمدی!\n\n"
        "از منوی زیر استفاده کن:",
        reply_markup=main_menu(),
    )


async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)

    await update.message.reply_text(
        f"💰 موجودی شما: {get_coins(user.id)} 🪙",
        reply_markup=main_menu(),
    )


async def ranking_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    ensure_user(user)

    await update.message.reply_text(
        leaderboard_text(10),
        reply_markup=main_menu(),
    )


async def daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    ensure_user(user)

    conn = get_db()

    row = conn.execute(
        "SELECT last_daily FROM users WHERE user_id = ?",
        (user.id,),
    ).fetchone()

    last_daily = row[0] if row else None
    now = datetime.now(timezone.utc)

    if last_daily:
        try:
            last = datetime.fromisoformat(last_daily)
        except ValueError:
            last = now - timedelta(hours=24)
    else:
        last = now - timedelta(hours=24)

    elapsed = (now - last).total_seconds()

    if elapsed < 24 * 3600:
        remaining = int(24 * 3600 - elapsed)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        conn.close()

        await update.message.reply_text(
            "⏳ سکه روزانه را قبلاً گرفتی.\n"
            f"زمان باقی‌مانده: {hours} ساعت و {minutes} دقیقه",
            reply_markup=main_menu(),
        )
        return

    conn.execute(
        """
        UPDATE users
        SET coins = coins + ?, last_daily = ?
        WHERE user_id = ?
        """,
        (
            DAILY_COINS,
            now.isoformat(),
            user.id,
        ),
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"🎁 +{DAILY_COINS} سکه دریافت کردی!\n"
        f"💰 موجودی: {get_coins(user.id)}",
        reply_markup=main_menu(),
    )


async def transfer(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    user = update.effective_user
    ensure_user(user)

    if len(context.args) != 2:
        await update.message.reply_text(
            "فرمت درست:\n\n"
            "/transfer @username amount\n\n"
            "مثال:\n"
            "/transfer @ali 100"
        )
        return

    username = context.args[0].lstrip("@").lower()

    try:
        amount = int(context.args[1])
    except ValueError:
        await update.message.reply_text(
            "❌ مقدار سکه باید عدد باشد."
        )
        return

    if amount <= 0:
        await update.message.reply_text(
            "❌ مقدار باید بیشتر از صفر باشد."
        )
        return

    conn = get_db()

    target = conn.execute(
        """
        SELECT user_id
        FROM users
        WHERE LOWER(username) = ?
        """,
        (username,),
    ).fetchone()

    if not target:
        conn.close()

        await update.message.reply_text(
            "❌ کاربر پیدا نشد.\n"
            "او باید حداقل یک بار /start را زده باشد."
        )
        return

    target_id = target[0]

    if target_id == user.id:
        conn.close()

        await update.message.reply_text(
            "❌ نمی‌توانی به خودت سکه انتقال بدهی."
        )
        return

    if not has_coins(user.id, amount):
        conn.close()

        await update.message.reply_text(
            "❌ موجودی کافی نیست."
        )
        return

    conn.execute(
        "UPDATE users SET coins = coins - ? WHERE user_id = ?",
        (amount, user.id),
    )

    conn.execute(
        "UPDATE users SET coins = coins + ? WHERE user_id = ?",
        (amount, target_id),
    )

    conn.commit()
    conn.close()

    await update.message.reply_text(
        f"✅ {amount} سکه به @{username} منتقل شد.",
        reply_markup=main_menu(),
    )


# =========================
# BUTTON HANDLER
# =========================

async def buttons(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    query = update.callback_query
    await query.answer()

    user = query.from_user
    ensure_user(user)

    data = query.data

    # Main menu
    if data == "menu":
        await query.edit_message_text(
            "🎮 منوی اصلی:",
            reply_markup=main_menu(),
        )
        return

    # Balance
    if data == "balance":
        await query.edit_message_text(
            f"💰 موجودی شما: {get_coins(user.id)} 🪙",
            reply_markup=back_menu(),
        )
        return

    # Daily
    if data == "daily":
        await daily_button(user, query)
        return

    # RPS menu
    if data == "rps":
        await query.edit_message_text(
            "✊ یکی را انتخاب کن:",
            reply_markup=rps_menu(),
        )
        return

    # RPS game
    if data.startswith("rps_"):
        choice = data.replace("rps_", "")

        if not has_coins(user.id, LOSS_AMOUNT):
            await query.answer(
                "❌ حداقل 50 سکه برای بازی لازم داری.",
                show_alert=True,
            )
            return

        bot_choice = random.choice(
            ["rock", "paper", "scissors"]
        )

        result = probability_result()

        names = {
            "rock": "🪨 سنگ",
            "paper": "📄 کاغذ",
            "scissors": "✂️ قیچی",
        }

        if result == "win":
            add_coins(user.id, WIN_REWARD)
            result_text = "🎉 بردی! +100 سکه"
        elif result == "loss":
            add_coins(user.id, -LOSS_AMOUNT)
            result_text = "😢 باختی! -50 سکه"
        else:
            result_text = "🤝 مساوی شد! تغییری در سکه‌ها نیست."

        await query.edit_message_text(
            "✊ سنگ کاغذ قیچی\n\n"
            f"انتخاب تو: {names[choice]}\n"
            f"انتخاب ربات: {names[bot_choice]}\n\n"
            f"{result_text}\n"
            f"💰 موجودی: {get_coins(user.id)}",
            reply_markup=rps_menu(),
        )
        return

    # Dice menu
    if data == "dice":
        await query.edit_message_text(
            "🎲 زوج یا فرد؟",
            reply_markup=dice_menu(),
        )
        return

    # Dice game
    if data.startswith("dice_"):
        choice = data.replace("dice_", "")

        if not has_coins(user.id, LOSS_AMOUNT):
            await query.answer(
                "❌ حداقل 50 سکه برای بازی لازم داری.",
                show_alert=True,
            )
            return

        number = random.randint(1, 6)
        result = probability_result()

        if result == "win":
            add_coins(user.id, WIN_REWARD)
            result_text = "🎉 بردی! +100 سکه"
        elif result == "loss":
            add_coins(user.id, -LOSS_AMOUNT)
            result_text = "😢 باختی! -50 سکه"
        else:
            result_text = "🤝 مساوی شد! تغییری در سکه‌ها نیست."

        selected = "زوج" if choice == "even" else "فرد"

        await query.edit_message_text(
            "🎲 تاس زوج/فرد\n\n"
            f"عدد تاس: 🎲 {number}\n"
            f"انتخاب تو: {selected}\n\n"
            f"{result_text}\n"
            f"💰 موجودی: {get_coins(user.id)}",
            reply_markup=dice_menu(),
        )
        return

    # Miner main page
    if data == "miner":
        level, _ = get_miner(user.id)

        if level:
            miner = MINERS[level]

            text = (
                "⛏️ ماینر من\n\n"
                f"{miner['name']}\n"
                f"📈 سطح: {level}\n"
                f"⚡ تولید: {miner['rate']} سکه در ساعت\n"
                f"🪙 آماده استخراج: {ready_miner_coins(user.id)}\n"
                f"💰 موجودی: {get_coins(user.id)}"
            )
        else:
            text = (
                "⛏️ ماینر\n\n"
                "شما هنوز ماینر ندارید.\n"
                "از فروشگاه یک ماینر بخر."
            )

        await query.edit_message_text(
            text,
            reply_markup=miner_menu(),
        )
        return

    # Miner info
    if data == "miner_info":
        level, _ = get_miner(user.id)

        if not level:
            text = "❌ شما هنوز ماینر ندارید."
        else:
            miner = MINERS[level]

            text = (
                "📊 اطلاعات ماینر\n\n"
                f"{miner['name']}\n"
                f"📈 سطح: {level}\n"
                f"⚡ تولید: {miner['rate']} سکه در ساعت\n"
                f"⛏️ آماده استخراج: {ready_miner_coins(user.id)}\n"
                f"💰 موجودی: {get_coins(user.id)}"
            )

        await query.edit_message_text(
            text,
            reply_markup=miner_menu(),
        )
        return

    # Miner claim
    if data == "miner_claim":
        amount, text = claim_miner(user.id)

        await query.edit_message_text(
            f"{text}\n\n"
            f"💰 موجودی: {get_coins(user.id)}",
            reply_markup=miner_menu(),
        )
        return

    # Miner shop
    if data == "miner_shop":
        await query.edit_message_text(
            "🛒 فروشگاه ماینر\n\n"
            "سطح‌ها به ترتیب قابل خرید هستند.",
            reply_markup=miner_shop_menu(),
        )
        return

    # Buy / upgrade miner
    if data.startswith("buy_miner_"):
        level = int(data.split("_")[-1])
        miner = MINERS[level]

        current_level, _ = get_miner(user.id)

        if level != current_level + 1:
            await query.answer(
                "❌ اول باید سطح قبلی را داشته باشی.",
                show_alert=True,
            )
            return

        if not has_coins(user.id, miner["price"]):
            await query.answer(
                f"❌ {miner['price']} سکه لازم داری.",
                show_alert=True,
            )
            return

        add_coins(user.id, -miner["price"])
        set_miner(user.id, level)

        await query.edit_message_text(
            "✅ ماینر فعال شد!\n\n"
            f"{miner['name']}\n"
            f"📈 سطح: {level}\n"
            f"⚡ تولید: {miner['rate']} سکه در ساعت\n"
            f"💰 موجودی: {get_coins(user.id)}",
            reply_markup=miner_menu(),
        )
        return

    # Leaderboard
    if data == "ranking":
        await query.edit_message_text(
            leaderboard_text(10),
            reply_markup=back_menu(),
        )
        return

    # Transfer
    if data == "transfer":
        await query.edit_message_text(
            "💸 انتقال سکه\n\n"
            "دستور:\n"
            "/transfer @username amount\n\n"
            "مثال:\n"
            "/transfer @ali 100",
            reply_markup=back_menu(),
        )
        return


async def daily_button(user, query):
    conn = get_db()

    row = conn.execute(
        "SELECT last_daily FROM users WHERE user_id = ?",
        (user.id,),
    ).fetchone()

    last_daily = row[0] if row else None
    now = datetime.now(timezone.utc)

    if last_daily:
        try:
            last = datetime.fromisoformat(last_daily)
        except ValueError:
            last = now - timedelta(hours=24)
    else:
        last = now - timedelta(hours=24)

    elapsed = (now - last).total_seconds()

    if elapsed < 24 * 3600:
        remaining = int(24 * 3600 - elapsed)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60

        conn.close()

        await query.edit_message_text(
            "⏳ سکه روزانه را قبلاً گرفتی.\n"
            f"زمان باقی‌مانده: {hours} ساعت و {minutes} دقیقه",
            reply_markup=back_menu(),
        )
        return

    conn.execute(
        """
        UPDATE users
        SET coins = coins + ?, last_daily = ?
        WHERE user_id = ?
        """,
        (
            DAILY_COINS,
            now.isoformat(),
            user.id,
        ),
    )

    conn.commit()
    conn.close()

    await query.edit_message_text(
        f"🎁 +{DAILY_COINS} سکه دریافت کردی!\n"
        f"💰 موجودی: {get_coins(user.id)}",
        reply_markup=back_menu(),
    )


# =========================
# RUN
# =========================

def main():
    if TOKEN == "PUT_YOUR_BOT_TOKEN_HERE":
        print("❌ TOKEN را داخل فایل وارد کن.")
        return

    get_db().close()

    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("balance", balance))
    app.add_handler(CommandHandler("daily", daily))
    app.add_handler(CommandHandler("ranking", ranking_command))
    app.add_handler(CommandHandler("transfer", transfer))

    app.add_handler(
        CallbackQueryHandler(buttons)
    )

    print("🤖 Bot is running...")
    app.run_polling()


if __name__ == "__main__":
    main()
