import os
import sqlite3
import threading
import json
from flask import Flask, jsonify, request
import telebot
from telebot import types

# 🔒 تنظیمات مالک اصلی و توکن ربات (تایید شده)
BOT_TOKEN = "8853723250:AAE2rpaXn5Ao5lqdTyqs5NB_8WAIZc4eWZQ"
OWNER_ID = 8911508795

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

# رفع مشکل CORS برای اتصال امن مینی‌اپ گیت‌هاب به سرور رندر
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

DB_FILE = "nexovpn.db"

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0
    )''')
    
    # جدول ادمین‌ها
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
        user_id INTEGER PRIMARY KEY
    )''')
    
    # جدول پلن‌ها
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT,
        volume TEXT,
        days TEXT,
        price INTEGER,
        is_wholesale INTEGER DEFAULT 0
    )''')
    
    # جدول تراکنش‌ها
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'PENDING',
        photo_id TEXT
    )''')
    
    # جدول تنظیمات سیستم (نام فروشگاه، رنگ، متون و...)
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )''')
    
    # مقادیر اولیه و پیش‌فرض تنظیمات پویا
    default_settings = [
        ('shop_name', 'NEXOVPN'),
        ('card_number', '۶۰۳۷۹۹۷۹۰۰۰۰۰۰۰۰'),
        ('support_id', 'NEXOVPN_Admin'),
        ('theme_color', '#3b82f6'), 
        ('backend_url', 'https://nexovpn.onrender.com'), 
        ('welcome_text', "✨ به Test خوش آمدید\n\n📣 اطلاعیه خرید\n\n• پرداخت‌ها به‌صورت خودکار تأیید می‌شوند و تحویل اشتراک به‌صورت آنی انجام می‌شود.🙏 از همراهی شما با NEXOVPN سپاسگزاریم.\n\nاز طریق منوی زیر می‌توانید:\n🛍️ اشتراک مناسب خود را انتخاب فرمایید\n📋 وضعیت حساب کاربری خود را مشاهده فرمایید\n\n📱 در صورت تمایل، می‌توانید از دکمه مینی‌اپ هم وارد نسخه گرافیکی فروشگاه شوید.\n⚙️ در صورت نیاز، به بخش مدیریت وارد شوید")
    ]
    for k, v in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

init_db()

# --- توابع کمکی خواندن تنظیمات از دیتابیس ---
def get_setting(key, default=""):
    conn = get_db_connection()
    row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    conn.close()
    return row['value'] if row else default

def set_setting(key, value):
    conn = get_db_connection()
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def is_admin(user_id):
    if user_id == OWNER_ID:
        return True
    conn = get_db_connection()
    admin = conn.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return admin is not None

def backup_database():
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'rb') as doc:
                bot.send_document(OWNER_ID, doc, caption="🔄 نسخه پشتیبان خودکار دیتابیس NEXOVPN")
    except Exception as e:
        print(f"Backup Error: {e}")

# --- API‌های مخصوص مینی‌اپ گرافیکی ---
@app.route('/api/shop_config')
def get_shop_config():
    user_id = request.args.get('user_id', type=int)
    conn = get_db_connection()
    user_data = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone() if user_id else None
    conn.close()
    
    return jsonify({
        "shop_name": get_setting('shop_name'),
        "card_number": get_setting('card_number'),
        "theme_color": get_setting('theme_color'),
        "balance": user_data['balance'] if user_data else 0
    })

@app.route('/api/get_plans')
def get_plans():
    conn = get_db_connection()
    plans = conn.execute("SELECT * FROM plans").fetchall()
    conn.close()
    return jsonify([dict(p) for p in plans])

# --- سیستم کیبوردهای تلگرام ---
def get_main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    
    github_url = "https://salhamir146-prog.github.io/index.html/"
    backend_url = get_setting('backend_url')
    full_webapp_url = f"{github_url}?user_id={user_id}&backend={backend_url}"
    
    mini_app_btn = types.KeyboardButton('📱 ورود به مینی‌اپ NEXOVPN', web_app=types.WebAppInfo(url=full_webapp_url))
    
    btn_buy = types.KeyboardButton('🛍️ خرید اشتراک')
    btn_account = types.KeyboardButton('📋 اکانت من')
    btn_wholesale = types.KeyboardButton('📦 فروش عمده')
    btn_support = types.KeyboardButton('☎️ ارتباط با پشتیبانی')
    
    markup.add(mini_app_btn)
    markup.add(btn_buy, btn_account)
    markup.add(btn_wholesale, btn_support)
    
    if is_admin(user_id):
        markup.add(types.KeyboardButton('⚙️ پنل مدیریت'))
    return markup

def get_admin_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btns = [
        types.KeyboardButton('📥 سفارش‌ها تحویل دستی'),
        types.KeyboardButton('💳 رسید‌های در انتظار تایید'),
        types.KeyboardButton('📊 گزارش دیتابیس‌ها'),
        types.KeyboardButton('👥 کاربران فروشگاه'),
        types.KeyboardButton('💬 ارتباط با خریداران'),
        types.KeyboardButton('📜 تاریخچه پرداخت‌ها'),
        types.KeyboardButton('🎟️ ساخت کد تخفیف'),
        types.KeyboardButton('📢 پیام همگانی (برودکست)'),
        types.KeyboardButton('➕ اضافه کردن پنل وی‌پی‌آن'),
        types.KeyboardButton('🎨 تنظیمات ظاهری و متون')
    ]
    markup.add(*btns)
    if user_id == OWNER_ID:
        markup.add(types.KeyboardButton('➕ افزودن ادمین جدید'))
    markup.add(types.KeyboardButton('🔙 بازگشت به منوی اصلی'))
    return markup

# --- هندلرهای ربات تلگرام ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    conn.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    conn.commit()
    conn.close()
    
    welcome = get_setting('welcome_text')
    bot.send_message(user_id, welcome, reply_markup=get_main_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == '🛍️ خرید اشتراک')
def user_buy_shop(message):
    user_id = message.from_user.id
    buy_text = (
        "🛒 یه پلن از لیست پایین انتخاب کن.\n\n"
        "بعد از انتخاب، فاکتور رو می‌بینی و در صورت تأیید مبلغ از کیف کم می‌شه.\n\n"
        "اگه موجودی نداشتی اول «💰 کیف پول» رو بزن و شارژ کن، بعد برگرد همین صفحه."
    )
    conn = get_db_connection()
    plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 0").fetchall()
    conn.close()
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        markup.add(types.InlineKeyboardButton(f"🚀 {p['name']} | {p['volume']}G | {p['days']} روز -> {p['price']:,} تومان", callback_data=f"buy_p_{p['id']}"))
    markup.add(types.InlineKeyboardButton("💰 شارژ کیف پول", callback_data="wallet_charge"))
    bot.send_message(user_id, buy_text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '📋 اکانت من')
def user_account(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    user_data = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    
    balance = user_data['balance'] if user_data else 0
    shop_title = get_setting('shop_name')
    info_text = (
        f"📋 وضعیت حساب کاربری شما در {shop_title}:\n\n"
        f"🆔 آیدی عددی شما: `{user_id}`\n"
        f"💰 موجودی کیف پول: {balance:,} تومان\n"
        "🟢 وضعیت اکانت: فعال"
    )
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("💰 افزایش موجودی حساب", callback_data="wallet_charge"))
    bot.send_message(user_id, info_text, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda m: m.text == '📦 فروش عمده')
def user_wholesale(message):
    user_id = message.from_user.id
    conn = get_db_connection()
    plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 1").fetchall()
    conn.close()
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    for p in plans:
        markup.add(types.InlineKeyboardButton(f"📦 عمده: {p['name']} ({p['volume']} اکانت) -> {p['price']:,} ت", callback_data=f"buy_p_{p['id']}"))
        
    text = f"💼 بخش فروش عمده و همکاری {get_setting('shop_name')}.\nیکی از پنل‌های زیر را انتخاب کنید:"
    bot.send_message(user_id, text, reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '☎️ ارتباط با پشتیبانی')
def user_support(message):
    admin_user = get_setting('support_id')
    text = f"☎️ جهت ارتباط با بخش پشتیبانی فنی و مالی با آیدی زیر در ارتباط باشید:\n\n👑 مدیریت: @{admin_user}"
    bot.send_message(message.from_user.id, text)

@bot.message_handler(func=lambda m: m.text == '⚙️ پنل مدیریت' and is_admin(m.from_user.id))
def admin_panel(message):
    bot.send_message(message.from_user.id, "🛠️ به پنل مدیریت هوشمند خوش آمدید:", reply_markup=get_admin_keyboard(message.from_user.id))

@bot.message_handler(func=lambda m: m.text == '🔙 بازگشت به منوی اصلی')
def back_to_main(message):
    bot.send_message(message.from_user.id, "🏠 به منوی اصلی برگشتید.", reply_markup=get_main_keyboard(message.from_user.id))

# --- منوی شخصی‌سازی متون و رنگ دکمه‌ها ---
@bot.message_handler(func=lambda m: m.text == '🎨 تنظیمات ظاهری و متون' and is_admin(m.from_user.id))
def admin_customization_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("✏️ تغییر نام فروشگاه", "✏️ تغییر شماره کارت")
    markup.add("✏️ تغییر آیدی پشتیبانی", "🎨 تغییر رنگ مینی‌اپ")
    markup.add("✏️ تغییر متن خوش‌آمدگویی", "🌐 ست کردن لینک رندر")
    markup.add("⚙️ پنل مدیریت")
    bot.send_message(message.from_user.id, "🎨 بخش مدیریت پوسته و متون؛ گزینه مورد نظر را انتخاب کنید:", reply_markup=markup)

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and m.text.startswith("✏️ تغییر"))
def edit_settings_handler(message):
    t = message.text
    if "نام فروشگاه" in t:
        msg = bot.send_message(message.from_user.id, "📝 نام جدید فروشگاه را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'shop_name'))
    elif "شماره کارت" in t:
        msg = bot.send_message(message.from_user.id, "💳 شماره کارت جدید ۱۶ رقمی را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'card_number'))
    elif "آیدی پشتیبانی" in t:
        msg = bot.send_message(message.from_user.id, "👤 آیدی پشتیبانی را بدون @ وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'support_id'))
    elif "متن خوش‌آمدگویی" in t:
        msg = bot.send_message(message.from_user.id, "📝 متن جدید استارت ربات را ارسال کنید:", reply_markup=types.ReplyKeyboardRemove())
        bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'welcome_text'))

@bot.message_handler(func=lambda m: m.text == '🎨 تغییر رنگ مینی‌اپ' and is_admin(m.from_user.id))
def change_color_start(message):
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("🔵 آبی هوشمند", callback_data="set_clr_#3b82f6"),
        types.InlineKeyboardButton("🟢 سبز زمردی", callback_data="set_clr_#10b981"),
        types.InlineKeyboardButton("🔴 قرمز یاقوتی", callback_data="set_clr_#ef4444"),
        types.InlineKeyboardButton("🟣 بنفش لوکس", callback_data="set_clr_#8b5cf6")
    )
    bot.send_message(message.from_user.id, "🎨 یک رنگ جذاب برای مینی‌اپ انتخاب کنید:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '🌐 ست کردن لینک رندر' and is_admin(m.from_user.id))
def change_backend_url_start(message):
    msg = bot.send_message(message.from_user.id, "🌐 آدرس کامل وب‌سرویس رندر خود را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'backend_url'))

def save_generic_setting(message, key):
    set_setting(key, message.text)
    bot.send_message(message.from_user.id, "✅ تغییرات ثبت شد!", reply_markup=get_admin_keyboard(message.from_user.id))
    backup_database()

# --- سیستم اضافه کردن پنل وی‌پی‌آن واقعی ---
@bot.message_handler(func=lambda m: m.text == '➕ اضافه کردن پنل وی‌پی‌آن' and is_admin(m.from_user.id))
def admin_add_plan_start(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🛒 کاربر عادی", "💼 فروش عمده", "🔙 لغو عملیات")
    msg = bot.send_message(message.from_user.id, "نوع پلن را انتخاب کنید:", reply_markup=markup)
    bot.register_next_step_handler(msg, process_plan_type)

def process_plan_type(message):
    if message.text == "🔙 لغو عملیات":
        bot.send_message(message.from_user.id, "عملیات لغو شد.", reply_markup=get_admin_keyboard(message.from_user.id))
        return
    is_wholesale = 1 if message.text == "💼 فروش عمده" else 0
    msg = bot.send_message(message.from_user.id, "📝 نام پنل را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, process_plan_name, is_wholesale)

def process_plan_name(message, is_wholesale):
    name = message.text
    msg = bot.send_message(message.from_user.id, "📊 حجم پلن را به گیگابایت وارد کنید:")
    bot.register_next_step_handler(msg, process_plan_volume, is_wholesale, name)

def process_plan_volume(message, is_wholesale, name):
    volume = message.text
    msg = bot.send_message(message.from_user.id, "⏱️ مدت زمان اعتبار را به روز وارد کنید:")
    bot.register_next_step_handler(msg, process_plan_days, is_wholesale, name, volume)

def process_plan_days(message, is_wholesale, name, volume):
    days = message.text
    msg = bot.send_message(message.from_user.id, "💰 قیمت پنل را به تومان وارد کنید (فقط عدد):")
    bot.register_next_step_handler(msg, process_plan_price, is_wholesale, name, volume, days)

def process_plan_price(message, is_wholesale, name, volume, days):
    try:
        price = int(message.text)
        conn = get_db_connection()
        conn.execute("INSERT INTO plans (name, volume, days, price, is_wholesale) VALUES (?, ?, ?, ?, ?)", (name, volume, days, price, is_wholesale))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, "✅ پلن جدید با موفقیت اضافه شد!", reply_markup=get_admin_keyboard(message.from_user.id))
        backup_database()
    except ValueError:
        bot.send_message(message.from_user.id, "❌ خطا در قیمت! عملیات لغو شد.", reply_markup=get_admin_keyboard(message.from_user.id))

# --- افزودن ادمین جدید توسط مالک ---
@bot.message_handler(func=lambda m: m.text == '➕ افزودن ادمین جدید' and m.from_user.id == OWNER_ID)
def owner_add_admin_start(message):
    msg = bot.send_message(message.from_user.id, "👤 آیدی عددی ادمین جدید را وارد کنید:")
    bot.register_next_step_handler(msg, process_add_admin)

def process_add_admin(message):
    try:
        new_admin_id = int(message.text)
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, f"✅ ادمین با آیدی عددی {new_admin_id} با موفقیت اضافه شد.")
        backup_database()
    except ValueError:
        bot.send_message(message.from_user.id, "❌ آیدی عددی نامعتبر است.")

# --- مدیریت کلیک روی گزینه‌های ادمین ---
@bot.message_handler(func=lambda m: is_admin(m.from_user.id))
def handle_admin_features(message):
    t = message.text
    conn = get_db_connection()
    if t == '📥 سفارش‌ها تحویل دستی':
        bot.send_message(message.from_user.id, "📦 در حال حاضر سفارش تحویل دستی در صف وجود ندارد.")
    elif t == '💳 رسید‌های در انتظار تایید':
        pending = conn.execute("SELECT * FROM transactions WHERE status = 'PENDING'").fetchall()
        if not pending:
            bot.send_message(message.from_user.id, "🟢 هیچ رسید جدیدی در انتظار تایید نیست!")
        for trx in pending:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"trx_approve_{trx['id']}"),
                types.InlineKeyboardButton("❌ رد رسید", callback_data=f"trx_reject_{trx['id']}")
            )
            bot.send_photo(message.from_user.id, trx['photo_id'], caption=f"💰 درخواست شارژ\n👤 کاربر: {trx['user_id']}\n💵 مبلغ: {trx['amount']:,} تومان", reply_markup=markup)
    elif t == '📊 گزارش دیتابیس‌ها':
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
        total_plans = conn.execute("SELECT COUNT(*) as count FROM plans").fetchone()['count']
        bot.send_message(message.from_user.id, f"📊 آمار دیتابیس:\n\n👥 کل کاربران: {total_users} نفر\n📦 کل پلن‌های فعال: {total_plans} عدد")
    elif t == '👥 کاربران فروشگاه':
        users = conn.execute("SELECT user_id FROM users LIMIT 10").fetchall()
        user_list = "\n".join([f"👤 `{u['user_id']}`" for u in users])
        bot.send_message(message.from_user.id, f"👥 لیست آخرین کاربران فعال:\n\n{user_list}", parse_mode="Markdown")
    conn.close()

# --- سیستم کالبک سورس ---
@bot.callback_query_handler(func=lambda call: True)
def inline_clicks(call):
    user_id = call.from_user.id
    conn = get_db_connection()
    
    if call.data.startswith("set_clr_"):
        color = call.data.replace("set_clr_", "")
        set_setting('theme_color', color)
        bot.answer_callback_query(call.id, f"🎨 رنگ پوسته مینی‌اپ تغییر یافت!", show_alert=True)
        backup_database()
        
    elif call.data == "wallet_charge":
        card = get_setting('card_number')
        text = f"💳 جهت شارژ حساب، مبلغ مورد نظر را به شماره کارت زیر واریز کنید:\n\n`{card}`\n\n📌 بعد از واریز، عکس رسید را بفرستید."
        msg = bot.send_message(user_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_payment_receipt)
        
    elif call.data.startswith("buy_p_"):
        plan_id = int(call.data.replace("buy_p_", ""))
        plan = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        
        if plan and user:
            if user['balance'] >= plan['price']:
                new_balance = user['balance'] - plan['price']
                conn.execute("UPDATE users SET balance = ? WHERE user_id = ?", (new_balance, user_id))
                conn.commit()
                bot.send_message(user_id, f"🎉 پرداخت با موفقیت انجام شد!\n🛍️ اشتراک {plan['name']} به صورت آنی صادر شد.\n💰 موجودی جدید شما: {new_balance:,} تومان")
                backup_database()
            else:
                bot.answer_callback_query(call.id, "❌ موجودی کافی نیست!", show_alert=True)
                
    elif call.data.startswith("trx_approve_"):
        trx_id = int(call.data.replace("trx_approve_", ""))
        trx = conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if trx and trx['status'] == 'PENDING':
            conn.execute("UPDATE transactions SET status = 'APPROVED' WHERE id = ?", (trx_id,))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (trx['amount'], trx['user_id']))
            conn.commit()
            bot.edit_message_caption("✅ این رسید تایید و حساب کاربر شارژ شد.", call.from_user.id, call.message.message_id)
            bot.send_message(trx['user_id'], f"🎉 رسید واریزی شما تایید شد!\n💰 مبلغ {trx['amount']:,} تومان به کیف پول شما اضافه شد.")
            backup_database()
            
    elif call.data.startswith("trx_reject_"):
        trx_id = int(call.data.replace("trx_reject_", ""))
        trx = conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if trx and trx['status'] == 'PENDING':
            conn.execute("UPDATE transactions SET status = 'REJECTED' WHERE id = ?", (trx_id,))
            conn.commit()
            bot.edit_message_caption("❌ این رسید رد شد.", call.from_user.id, call.message.message_id)
            bot.send_message(trx['user_id'], "❌ رسید واریزی شما توسط مدیریت رد شد.")
            
    conn.close()

def process_payment_receipt(message):
    if not message.photo:
        bot.send_message(message.from_user.id, "❌ لطفاً فقط عکس رسید را بفرستید.")
        return
    photo_id = message.photo[-1].file_id
    msg = bot.send_message(message.from_user.id, "💵 مبلغ واریزی را به تومان وارد کنید (فقط عدد):")
    bot.register_next_step_handler(msg, save_receipt_db, photo_id)

def save_receipt_db(message, photo_id):
    try:
        amount = int(message.text)
        conn = get_db_connection()
        conn.execute("INSERT INTO transactions (user_id, amount, photo_id) VALUES (?, ?, ?)", (message.from_user.id, amount, photo_id))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, "⏳ رسید شما ثبت شد و پس از تایید حساب شارژ می‌شود.")
        backup_database()
    except ValueError:
        bot.send_message(message.from_user.id, "❌ خطا در مقدار!")

# --- وب‌سرور هوشمند متصل به مینی‌اپ ---
@app.route('/')
def home():
    return "NEXOVPN Core Server is Live! 🚀"

# 🟢 انتقال استارت ربات به بیرون از بلاک اصلی جهت اجرای اجباری توسط Gunicorn
def start_bot_polling():
    print("NEXOVPN Bot Polling Started Successfully... 🚀")
    bot.infinity_polling()

threading.Thread(target=start_bot_polling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
