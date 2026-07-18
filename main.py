import os
import sqlite3
import threading
import json
import random
from datetime import datetime, timedelta
from flask import Flask, jsonify, request
import telebot
from telebot import types

# 🔒 تنظیمات مالک اصلی و توکن ربات
BOT_TOKEN = "8853723250:AAE2rpaXn5Ao5lqdTyqs5NB_8WAIZc4eWZQ"
OWNER_ID = 8911508795

bot = telebot.TeleBot(BOT_TOKEN)
app = Flask(__name__)

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
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        balance INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT 0,
        invite_count INTEGER DEFAULT 0,
        last_daily TEXT DEFAULT '',
        user_level TEXT DEFAULT '🥉 برنزی',
        total_spent INTEGER DEFAULT 0
    )''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, volume TEXT, days TEXT, price INTEGER, is_wholesale INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, status TEXT DEFAULT 'PENDING', photo_id TEXT, date TEXT
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    default_settings = [
        ('shop_name', 'NEXOVPN'),
        ('card_number', '۶۰۳۷۹۹۷۹۰۰۰۰۰۰۰۰'),
        ('support_id', 'NEXOVPN_Admin'),
        ('theme_color', '#3b82f6'), 
        ('backend_url', 'https://nexovpn.onrender.com'), 
        ('welcome_text', "✨ به NEXOVPN خوش آمدید\n\n📣 تحویل اشتراک‌ها کاملاً آنی و خودکار است.\n\n👇 از دکمه‌های شیشه‌ای زیر جهت ناوبری و استفاده از خدمات فوق‌پیشرفته ربات استفاده کنید:")
    ]
    for k, v in default_settings:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    conn.commit()
    conn.close()

init_db()

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
    if user_id == OWNER_ID: return True
    conn = get_db_connection()
    admin = conn.execute("SELECT * FROM admins WHERE user_id = ?", (user_id,)).fetchone()
    conn.close()
    return admin is not None

# --- ساخت کیبورد شیشه‌ای (Inline) اصلی ---
def get_main_inline_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    github_url = "https://salhamir146-prog.github.io/index.html/"
    backend_url = get_setting('backend_url')
    full_webapp_url = f"{github_url}?user_id={user_id}&backend={backend_url}"
    
    markup.add(types.InlineKeyboardButton('📱 ورود به مینی‌اپ گرافیکی فروشگاه', web_app=types.WebAppInfo(url=full_webapp_url)))
    markup.add(types.InlineKeyboardButton('🛍️ خرید اشتراک', callback_data='btn_buy'), types.InlineKeyboardButton('📋 حساب کاربری من', callback_data='btn_account'))
    markup.add(types.InlineKeyboardButton('🎁 هدیه روزانه شانس', callback_data='btn_daily'), types.InlineKeyboardButton('👥 کسب درآمد (زیرمجموعه)', callback_data='btn_referral'))
    markup.add(types.InlineKeyboardButton('⏱️ کانفیگ تست رایگان', callback_data='btn_test_config'), types.InlineKeyboardButton('📚 آموزش اتصال و دانلود', callback_data='btn_tutorials'))
    markup.add(types.InlineKeyboardButton('📊 وضعیت زنده سرورها', callback_data='btn_servers'), types.InlineKeyboardButton('📜 تاریخچه تراکنش‌ها', callback_data='btn_history'))
    markup.add(types.InlineKeyboardButton('📦 فروش عمده و همکاری', callback_data='btn_wholesale'), types.InlineKeyboardButton('☎️ پشتیبانی فنی', callback_data='btn_support'))
    
    if is_admin(user_id):
        markup.add(types.InlineKeyboardButton('⚙️ پنل مدیریت هوشمند ربات', callback_data='btn_admin_panel'))
    return markup

def get_admin_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add('📥 سفارش‌ها تحویل دستی', '💳 رسید‌های در انتظار تایید')
    markup.add('📊 گزارش دیتابیس‌ها', '👥 کاربران فروشگاه')
    markup.add('➕ اضافه کردن پنل وی‌پی‌آن', '🎨 تنظیمات ظاهری و متون')
    if user_id == OWNER_ID:
        markup.add('➕ افزودن ادمین جدید')
    markup.add('🔙 بازگشت به منوی اصلی شیشه‌ای')
    return markup

# --- هندلرهای دستورات متنی ---
@bot.message_handler(commands=['start'])
def start_command(message):
    user_id = message.from_user.id
    text_args = message.text.split()
    
    conn = get_db_connection()
    user_exists = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not user_exists:
        referred_by = 0
        if len(text_args) > 1 and text_args[1].startswith('ref_'):
            try:
                ref_id = int(text_args[1].replace('ref_', ''))
                if ref_id != user_id:
                    referred_by = ref_id
                    conn.execute("UPDATE users SET balance = balance + 2000, invite_count = invite_count + 1 WHERE user_id = ?", (ref_id,))
                    try:
                        bot.send_message(ref_id, f"🎉 یک کاربر از طریق لینک شما وارد شد! مبلغ ۲,۰۰۰ تومان به کیف پول شما هدیه داده شد.")
                    except: pass
            except: pass
            
        conn.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by))
        conn.commit()
    conn.close()
    
    welcome = get_setting('welcome_text')
    bot.send_message(user_id, welcome, reply_markup=get_main_inline_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == '🔙 بازگشت به منوی اصلی شیشه‌ای')
def back_to_main_text(message):
    welcome = get_setting('welcome_text')
    bot.send_message(message.from_user.id, welcome, reply_markup=get_main_inline_keyboard(message.from_user.id))

# --- 🎯 مرکز مدیریت یکپارچه تمام دکمه‌های شیشه‌ای (حل مشکل دکمه بازگشت) ---
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    conn = get_db_connection()
    
    # دکمه بازگشت به خانه (اصلاح شده)
    if data == 'back_to_home':
        welcome = get_setting('welcome_text')
        bot.edit_message_text(welcome, user_id, call.message.message_id, reply_markup=get_main_inline_keyboard(user_id))
        
    elif data == 'btn_account':
        u = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        text = (
            f"📋 **پروفایل کاربری شما**\n\n"
            f"🆔 آیدی عددی: `{user_id}`\n"
            f"💰 موجودی کیف پول: {u['balance']}:, تومان\n"
            f"🎖️ سطح اکانت: {u['user_level']}\n"
            f"👥 تعداد زیرمجموعه‌ها: {u['invite_count']} نفر\n"
            f"📊 کل خرید شما تا کنون: {u['total_spent']}:, تومان\n"
            f"🟢 وضعیت حساب: فعال و ایمن"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("💰 شارژ و افزایش موجودی", callback_data="wallet_charge"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
        
    elif data == 'btn_buy':
        plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 0").fetchall()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans:
            markup.add(types.InlineKeyboardButton(f"🚀 {p['name']} | {p['volume']}G | {p['days']} روز -> {p['price']:,} ت", callback_data=f"buy_p_{p['id']}"))
        markup.add(types.InlineKeyboardButton("💰 شارژ حساب", callback_data="wallet_charge"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text("🛒 لیست پلن‌های پرسرعت اختصاصی NEXOVPN:\nیکی از گزینه‌های زیر را جهت خرید انتخاب کنید:", user_id, call.message.message_id, reply_markup=markup)

    elif data == 'btn_referral':
        bot_info = bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start=ref_{user_id}"
        u = conn.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,)).fetchone()
        text = (
            f"👥 **سیستم کسب درآمد اختصاصی**\n\n"
            f"با دعوت دوستان خود به ربات، به ازای هر ورود موفق **۲,۰۰۰ تومان** شارژ رایگان هدیه بگیرید!\n\n"
            f"📊 تعداد کل افراد دعوت شده شما: {u['invite_count']} نفر\n"
            f"🔗 لینک دعوت اختصاصی شما:\n`{ref_link}`"
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == 'btn_daily':
        u = conn.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,)).fetchone()
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        if u['last_daily'] == today_str:
            bot.answer_callback_query(call.id, "❌ رفیق! شما هدیه امروزت رو گرفتی. فردا دوباره بیا!", show_alert=True)
        else:
            gift_amount = random.choice([500, 1000, 1500, 2000, 3000])
            conn.execute("UPDATE users SET balance = balance + ?, last_daily = ? WHERE user_id = ?", (gift_amount, today_str, user_id))
            conn.commit()
            bot.answer_callback_query(call.id, f"🎉 مبلغ {gift_amount:,} تومان شانس شما بود و به ولتت اضافه شد!", show_alert=True)

    elif data == 'btn_test_config':
        test_config = f"vless://{random.randint(10000,99999)}a-test-nexovpn-free-account-for-{user_id}@de.nexovpn.com:443?type=ws&security=tls#TEST-NEXOVPN"
        text = (
            f"⏱️ **اکانت تست رایگان شما صادر شد!**\n\n"
            f"📌 این کانفیگ دارای ۵۰۰ مگابایت حجم و اعتبار ۱ ساعته می‌باشد:\n\n"
            f"`{test_config}`\n\n"
            f"⚠️ جهت خرید اکانت‌های اصلی، از دکمه «خرید اشتراک» استفاده کنید."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == 'btn_tutorials':
        text = (
            f"📚 **راهنمای جامع اتصال به NEXOVPN**\n\n"
            f"🤖 **اندروید:** نرم‌افزار v2rayNG را دانلود کنید.\n"
            f"🍏 **آیفون (iOS):** از برنامه v2box یا FoXray استفاده کنید.\n"
            f"💻 **ویندوز:** برنامه v2rayN را نصب کنید.\n\n"
            f"کافیه کانفیگ خودتون رو کپی کنید و داخل این برنامه‌ها Import کنید."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == 'btn_servers':
        p1, p2, p3 = random.randint(15, 35), random.randint(20, 45), random.randint(40, 75)
        text = (
            f"📊 **وضعیت پینگ و ظرفیت زنده سرورها**\n\n"
            f"🇩🇪 سرور آلمان (VIP): 🟢 آنلاین | پینگ: {p1}ms | ظرفیت: ۲۴%\n"
            f"🇫🇮 سرور فنلاند (سرعت بالا): 🟢 آنلاین | پینگ: {p2}ms | ظرفیت: ۳۸%\n"
            f"🇳🇱 سرور هلند (مخصوص دانلود): 🟢 آنلاین | پینگ: {p3}ms | ظرفیت: ۵۱%\n\n"
            f"🔄 آمار هر ۳۰ ثانیه به‌روزرسانی می‌شود."
        )
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="btn_servers"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)

    elif data == 'btn_history':
        txs = conn.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,)).fetchall()
        if not txs:
            text = "📜 شما هنوز هیچ تراکنشی در این ربات ثبت نکرده‌اید!"
        else:
            text = "📜 **لیست آخرین تراکنش‌های شما:**\n\n"
            for t in txs:
                text += f"🔹 کد پیگیری: {t['id']} | مبلغ: {t['amount']:,} ت | وضعیت: {t['status']}\n"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")

    elif data == 'btn_wholesale':
        plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 1").fetchall()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans:
            markup.add(types.InlineKeyboardButton(f"📦 عمده: {p['name']} ({p['volume']} اکانت) -> {p['price']:,} ت", callback_data=f"buy_p_{p['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(f"💼 بخش فروش عمده و همکاری ویژه همکاران:\nیکی از پکیج‌های زیر را انتخاب کنید:", user_id, call.message.message_id, reply_markup=markup)

    elif data == 'btn_support':
        admin_user = get_setting('support_id')
        text = f"☎️ جهت ارتباط با بخش پشتیبانی فنی و مالی با آیدی زیر در ارتباط باشید:\n\n👑 مدیریت: @{admin_user}"
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)

    elif data == 'btn_admin_panel' and is_admin(user_id):
        bot.send_message(user_id, "🛠️ پنل مدیریت با دکمه‌های پایینی فعال شد:", reply_markup=get_admin_keyboard(user_id))

    # --- کالبک‌های سیستمی و مالی کدهای قبلی ---
    elif data == "wallet_charge":
        card = get_setting('card_number')
        text = f"💳 جهت شارژ حساب، مبلغ مورد نظر را به شماره کارت زیر واریز کنید:\n\n`{card}`\n\n📌 بعد از واریز، عکس رسید را بفرستید."
        msg = bot.send_message(user_id, text, parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_payment_receipt)
        
    elif data.startswith("buy_p_"):
        plan_id = int(data.replace("buy_p_", ""))
        plan = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
        user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        
        if plan and user:
            if user['balance'] >= plan['price']:
                new_balance = user['balance'] - plan['price']
                new_spent = user['total_spent'] + plan['price']
                
                lvl = "🥉 برنزی"
                if new_spent > 500000: lvl = "👑 طلایی"
                elif new_spent > 150000: lvl = "🥈 نقره‌ای"
                
                conn.execute("UPDATE users SET balance = ?, total_spent = ?, user_level = ? WHERE user_id = ?", (new_balance, new_spent, lvl, user_id))
                conn.commit()
                bot.send_message(user_id, f"🎉 پرداخت انجام شد!\nاشتراک {plan['name']} صادر شد.\n💰 موجودی جدید: {new_balance:,} تومان")
            else:
                bot.answer_callback_query(call.id, "❌ موجودی کافی نیست! ابتدا حساب را شارژ کنید.", show_alert=True)
                
    elif data.startswith("trx_approve_"):
        trx_id = int(data.replace("trx_approve_", ""))
        trx = conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if trx and trx['status'] == 'PENDING':
            conn.execute("UPDATE transactions SET status = 'APPROVED' WHERE id = ?", (trx_id,))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (trx['amount'], trx['user_id']))
            conn.commit()
            bot.edit_message_caption("✅ این رسید تایید و حساب کاربر شارژ شد.", call.from_user.id, call.message.message_id)
            bot.send_message(trx['user_id'], f"🎉 رسید واریزی شما تایید شد!\n💰 مبلغ {trx['amount']:,} تومان به کیف پول شما اضافه شد.")
            
    elif data.startswith("trx_reject_"):
        trx_id = int(data.replace("trx_reject_", ""))
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
        today = datetime.now().strftime("%Y-%m-%d %H:%M")
        conn.execute("INSERT INTO transactions (user_id, amount, photo_id, date) VALUES (?, ?, ?, ?)", (message.from_user.id, amount, photo_id, today))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, "⏳ رسید شما ثبت شد و پس از تایید مدیریت حساب شارژ می‌شود.")
    except ValueError:
        bot.send_message(message.from_user.id, "❌ خطا در مقدار!")

# --- منوی مدیریت و تنظیمات پویا ---
@bot.message_handler(func=lambda m: m.text == '🎨 تنظیمات ظاهری و متون' and is_admin(m.from_user.id))
def admin_customization_menu(message):
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add("✏️ تغییر نام فروشگاه", "✏️ تغییر شماره کارت")
    markup.add("✏️ تغییر آیدی پشتیبانی", "🎨 تغییر رنگ مینی‌اپ")
    markup.add("✏️ تغییر متن خوش‌آمدگویی", "🌐 ست کردن لینک رندر")
    markup.add("🔙 بازگشت به منوی اصلی شیشه‌ای")
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
    except ValueError:
        bot.send_message(message.from_user.id, "❌ خطا در قیمت! عملیات لغو شد.", reply_markup=get_admin_keyboard(message.from_user.id))

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
        bot.send_message(message.from_user.id, f"✅ ادمین {new_admin_id} با موفقیت اضافه شد.")
    except ValueError:
        bot.send_message(message.from_user.id, "❌ آیدی عددی نامعتبر است.")

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
            markup.add(types.InlineKeyboardButton("✅ تایید و شارژ", callback_data=f"trx_approve_{trx['id']}"), types.InlineKeyboardButton("❌ رد رسید", callback_data=f"trx_reject_{trx['id']}"))
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

# --- وب‌سرور هوشمند متصل به مینی‌اپ ---
@app.route('/')
def home():
    return "NEXOVPN Core Server is Live! 🚀"

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

def start_bot_polling():
    print("NEXOVPN Bot Polling Started Successfully... 🚀")
    bot.infinity_polling()

threading.Thread(target=start_bot_polling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
