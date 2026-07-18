import os
import sqlite3
import threading
import json
import random
from datetime import datetime
from flask import Flask, jsonify, request, render_template
import telebot
from telebot import types

# 🔒 تنظیمات مالک اصلی و توکن ربات
BOT_TOKEN = "8956203339:AAFQqaanC1TShzJh7l_22gCNTM00vqF_Kks"
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
        user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, referred_by INTEGER DEFAULT 0,
        invite_count INTEGER DEFAULT 0, last_daily TEXT DEFAULT '', user_level TEXT DEFAULT '🥉 برنزی', total_spent INTEGER DEFAULT 0
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS plans (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, volume TEXT, days TEXT, price INTEGER, is_wholesale INTEGER DEFAULT 0)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS transactions (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER, status TEXT DEFAULT 'PENDING', photo_id TEXT, date TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, plan_name TEXT, price INTEGER, status TEXT DEFAULT 'PENDING', date TEXT, config_link TEXT DEFAULT ''
    )''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
    
    default_settings = [
        ('shop_name', 'NEXOVPN'), ('card_number', '۶۰۳۷۹۹۷۹۰۰۰۰۰۰۰۰'), ('support_id', 'NEXOVPN_Admin'),
        ('theme_color', '#3b82f6'), ('backend_url', 'https://nexovpn.onrender.com'), 
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

def get_main_inline_keyboard(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    webapp_url = get_setting('backend_url')
    markup.add(types.InlineKeyboardButton('📱 ورود به نسخه وب مینی‌اپ NEXOVPN', web_app=types.WebAppInfo(url=webapp_url)))
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
    if user_id == OWNER_ID: markup.add('➕ افزودن ادمین جدید')
    markup.add('🔙 بازگشت به منوی اصلی شیشه‌ای')
    return markup

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
                    bot.send_message(ref_id, f"🎉 یک کاربر از طریق لینک شما وارد شد! مبلغ ۲,۰۰۰ تومان به کیف پول شما هدیه داده شد.")
            except: pass
        conn.execute("INSERT INTO users (user_id, referred_by) VALUES (?, ?)", (user_id, referred_by))
        conn.commit()
    conn.close()
    bot.send_message(user_id, get_setting('welcome_text'), reply_markup=get_main_inline_keyboard(user_id))

@bot.message_handler(func=lambda m: m.text == '🔙 بازگشت به منوی اصلی شیشه‌ای')
def back_to_main_text(message):
    bot.send_message(message.from_user.id, get_setting('welcome_text'), reply_markup=get_main_inline_keyboard(message.from_user.id))

# --- 🎯 مدیریت کامل کلیک دکمه‌های شیشه‌ای ربات ---
@bot.callback_query_handler(func=lambda call: True)
def handle_all_callbacks(call):
    user_id = call.from_user.id
    data = call.data
    conn = get_db_connection()
    
    if data == 'back_to_home':
        bot.edit_message_text(get_setting('welcome_text'), user_id, call.message.message_id, reply_markup=get_main_inline_keyboard(user_id))
    elif data == 'btn_admin_panel' and is_admin(user_id):
        bot.send_message(user_id, "🛠️ پنل مدیریت فعال شد:", reply_markup=get_admin_keyboard(user_id))
    elif data == 'btn_account':
        u = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
        text = f"📋 **پروفایل کاربری شما**\n\n🆔 آیدی عددی: `{user_id}`\n💰 موجودی: {u['balance']:,} تومان\n🎖️ سطح: {u['user_level']}\n👥 زیرمجموعه‌ها: {u['invite_count']} نفر\n📊 کل خرید: {u['total_spent']:,} تومان"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("💰 شارژ کیف پول", callback_data="wallet_charge"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    elif data == 'btn_buy':
        plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 0").fetchall()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans:
            markup.add(types.InlineKeyboardButton(f"🚀 {p['name']} -> {p['price']:,} ت", callback_data=f"buy_p_{p['id']}"))
        markup.add(types.InlineKeyboardButton("💰 شارژ حساب", callback_data="wallet_charge"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text("🛒 لیست پلن‌های فعال فروشگاه جهت خرید:", user_id, call.message.message_id, reply_markup=markup)
    elif data == 'btn_referral':
        ref_link = f"https://t.me/{bot.get_me().username}?start=ref_{user_id}"
        u = conn.execute("SELECT invite_count FROM users WHERE user_id = ?", (user_id,)).fetchone()
        text = f"👥 **کسب درآمد اختصاصی**\n\nبا دعوت دوستان خود، به ازای هر نفر **۲,۰۰۰ تومان** شارژ هدیه بگیرید!\n\n📊 دعوت‌های شما: {u['invite_count']} نفر\n🔗 لینک دعوت شما:\n`{ref_link}`"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    elif data == 'btn_daily':
        u = conn.execute("SELECT last_daily FROM users WHERE user_id = ?", (user_id,)).fetchone()
        today_str = datetime.now().strftime("%Y-%m-%d")
        if u['last_daily'] == today_str:
            bot.answer_callback_query(call.id, "❌ هدیه امروز رو قبلاً گرفتی رفیق!", show_alert=True)
        else:
            gift = random.choice([500, 1000, 1500, 2000, 3000])
            conn.execute("UPDATE users SET balance = balance + ?, last_daily = ? WHERE user_id = ?", (gift, today_str, user_id))
            conn.commit()
            bot.answer_callback_query(call.id, f"🎉 مبلغ {gift:,} تومان هدیه شانس به ولتت اضافه شد!", show_alert=True)
    elif data == 'btn_test_config':
        test_config = f"vless://{random.randint(10000,99999)}a-test-nexovpn-free@{get_setting('shop_name')}.com:443?type=ws&security=tls#TEST"
        text = f"⏱️ **اکانت تست رایگان ۱ ساعته شما:**\n\n`{test_config}`"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup, parse_mode="Markdown")
    elif data == 'btn_tutorials':
        text = "📚 **راهنمای جامع اتصال**\n\n🤖 اندروید: برنامه v2rayNG\n🍏 آیفون: برنامه V2Box یا FoXray\n💻 ویندوز: برنامه v2rayN\n\nکافیه کانفیگ رو کپی کنی و داخل برنامه Import کنی."
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    elif data == 'btn_servers':
        text = f"📊 **وضعیت پینگ سرورها:**\n\n🇩🇪 آلمان: 🟢 {random.randint(15,35)}ms\n🇫🇮 فنلاند: 🟢 {random.randint(20,45)}ms"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔄 بروزرسانی", callback_data="btn_servers"), types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    elif data == 'btn_history':
        txs = conn.execute("SELECT * FROM transactions WHERE user_id = ? ORDER BY id DESC LIMIT 5", (user_id,)).fetchall()
        text = "📜 **تاریخچه تراکنش‌های شما:**\n\n" if txs else "📜 شما هنوز تراکنشی ندارید."
        for t in txs: text += f"🔹 کد: {t['id']} | مبلغ: {t['amount']:,} ت | وضعیت: {t['status']}\n"
        markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text(text, user_id, call.message.message_id, reply_markup=markup)
    elif data == 'btn_wholesale':
        plans = conn.execute("SELECT * FROM plans WHERE is_wholesale = 1").fetchall()
        markup = types.InlineKeyboardMarkup(row_width=1)
        for p in plans: markup.add(types.InlineKeyboardButton(f"📦 عمده: {p['name']} -> {p['price']:,} ت", callback_data=f"buy_p_{p['id']}"))
        markup.add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home"))
        bot.edit_message_text("💼 لیست پکیج‌های همکاری و فروش عمده:", user_id, call.message.message_id, reply_markup=markup)
    elif data == 'btn_support':
        bot.edit_message_text(f"☎️ پشتیبانی فنی و مالی:\n\n👑 مدیریت: @{get_setting('support_id')}", user_id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("🔙 بازگشت", callback_data="back_to_home")))
    elif data == "wallet_charge":
        msg = bot.send_message(user_id, f"💳 کارت به کارت به شماره کارت زیر:\n\n`{get_setting('card_number')}`\n\n📌 عکس رسید را ارسال کنید:", parse_mode="Markdown")
        bot.register_next_step_handler(msg, process_payment_receipt)
    elif data.startswith("buy_p_"):
        plan_id = int(data.replace("buy_p_", ""))
        execute_purchase(user_id, plan_id)
    elif data.startswith("trx_approve_"):
        trx_id = int(data.replace("trx_approve_", ""))
        trx = conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if trx and trx['status'] == 'PENDING':
            conn.execute("UPDATE transactions SET status = 'APPROVED' WHERE id = ?", (trx_id,))
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (trx['amount'], trx['user_id']))
            conn.commit()
            bot.edit_message_caption("✅ رسید تایید و ولت شارژ شد.", call.from_user.id, call.message.message_id)
            bot.send_message(trx['user_id'], f"🎉 رسید مالی شما تایید شد! مبلغ {trx['amount']:,} تومان به حساب شما اضافه شد.")
    elif data.startswith("trx_reject_"):
        trx_id = int(data.replace("trx_reject_", ""))
        trx = conn.execute("SELECT * FROM transactions WHERE id = ?", (trx_id,)).fetchone()
        if trx and trx['status'] == 'PENDING':
            conn.execute("UPDATE transactions SET status = 'REJECTED' WHERE id = ?", (trx_id,))
            conn.commit()
            bot.edit_message_caption("❌ رسید رد شد.", call.from_user.id, call.message.message_id)
            bot.send_message(trx['user_id'], "❌ رسید واریزی شما توسط مدیریت رد شد.")
    elif data.startswith("ord_deliver_"):
        order_id = int(data.replace("ord_deliver_", ""))
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order and order['status'] == 'PENDING':
            msg = bot.send_message(user_id, f"🔗 لینک کانفیگ را برای کاربر `{order['user_id']}` بفرستید:")
            bot.register_next_step_handler(msg, process_order_delivery, order_id)
    elif data.startswith("ord_cancel_"):
        order_id = int(data.replace("ord_cancel_", ""))
        order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if order and order['status'] == 'PENDING':
            conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (order['price'], order['user_id']))
            conn.execute("UPDATE orders SET status = 'CANCELLED' WHERE id = ?", (order_id,))
            conn.commit()
            bot.edit_message_text(f"❌ سفارش {order_id} لغو و وجه عودت داده شد.", call.from_user.id, call.message.message_id)
            bot.send_message(order['user_id'], f"❌ سفارش خرید شما لغو شد و وجه به کیف پولتان برگشت داده شد.")
    elif data.startswith("set_clr__"):
        color = data.replace("set_clr__", "")
        set_setting('theme_color', color)
        bot.answer_callback_query(call.id, "🎨 رنگ تم مینی‌اپ با موفقیت تغییر کرد!", show_alert=True)
    conn.close()

def execute_purchase(user_id, plan_id):
    conn = get_db_connection()
    plan = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if plan and user:
        if user['balance'] >= plan['price']:
            new_balance = user['balance'] - plan['price']
            new_spent = user['total_spent'] + plan['price']
            lvl = "🥉 برنزی"
            if new_spent > 500000: lvl = "👑 طلایی"
            elif new_spent > 150000: lvl = "🥈 نقره‌ای"
            
            today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
            conn.execute("INSERT INTO orders (user_id, plan_name, price, status, date) VALUES (?, ?, ?, 'PENDING', ?)", (user_id, plan['name'], plan['price'], today_str))
            conn.execute("UPDATE users SET balance = ?, total_spent = ?, user_level = ? WHERE user_id = ?", (new_balance, new_spent, lvl, user_id))
            conn.commit()
            
            bot.send_message(user_id, f"🎉 **خرید با موفقیت انجام شد!**\n\n🛒 سفارش شما برای **{plan['name']}** ثبت شد.\n⏳ ادمین به زودی لینک کانفیگ اختصاصی شما را ارسال خواهد کرد.\n\n💰 موجودی جدید شما: {new_balance:,} تومان")
            try:
                bot.send_message(OWNER_ID, f"🛍️ **سفارش جدید!**\n\n👤 کاربر: `{user_id}`\n📦 پلن: {plan['name']}\n💰 قیمت: {plan['price']:,} تومان")
            except: pass
        else:
            bot.send_message(user_id, "❌ خرید ناموفق! موجودی کیف پول شما کافی نیست.")
    conn.close()

def process_order_delivery(message, order_id):
    if not message.text: return
    conn = get_db_connection()
    conn.execute("UPDATE orders SET status = 'COMPLETED', config_link = ? WHERE id = ?", (message.text, order_id))
    order = conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    conn.commit()
    bot.send_message(order['user_id'], f"🚀 **اشتراک شما آماده شد!**\n\n📦 پلن: {order['plan_name']}\n🔗 لینک کانفیگ:\n`{message.text}`\n\n📌 همچنین از داخل مینی‌اپ تب «سفارشات من» همیشه به این لینک دسترسی دارید.", parse_mode="Markdown")
    bot.send_message(message.from_user.id, "✅ با موفقیت تحویل داده شد و در مینی‌اپ کاربری ثبت شد.")
    conn.close()

def process_payment_receipt(message):
    if not message.photo: return
    photo_id = message.photo[-1].file_id
    msg = bot.send_message(message.from_user.id, "💵 مبلغ واریزی را به تومان وارد کنید:")
    bot.register_next_step_handler(msg, save_receipt_db, photo_id)

def save_receipt_db(message, photo_id):
    try:
        amount = int(message.text)
        conn = get_db_connection()
        conn.execute("INSERT INTO transactions (user_id, amount, photo_id, date) VALUES (?, ?, ?, ?)", (message.from_user.id, amount, photo_id, datetime.now().strftime("%Y-%m-%d %H:%M")))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, "⏳ رسید ثبت شد و منتظر تایید مدیریت است.")
    except: pass

# --- ⚙️ مدیریت متون و فرایندهای ادمین پنل ربات ---
@bot.message_handler(func=lambda m: is_admin(m.from_user.id))
def handle_admin_features(message):
    t = message.text
    conn = get_db_connection()
    if t == '📥 سفارش‌ها تحویل دستی':
        orders = conn.execute("SELECT * FROM orders WHERE status = 'PENDING'").fetchall()
        if not orders: bot.send_message(message.from_user.id, "📦 هیچ سفارشی در صف وجود ندارد.")
        for ord in orders:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("✉️ ارسال لینک و تحویل", callback_data=f"ord_deliver_{ord['id']}"), types.InlineKeyboardButton("❌ لغو و عودت وجه", callback_data=f"ord_cancel_{ord['id']}"))
            bot.send_message(message.from_user.id, f"🛍️ **سفارش جدید**\n\n🆔 کد: {ord['id']}\n👤 کاربر: `{ord['user_id']}`\n📦 پلن: {ord['plan_name']}\n💵 مبلغ: {ord['price']:,} ت", reply_markup=markup, parse_mode="Markdown")
    elif t == '💳 رسید‌های در انتظار تایید':
        pending = conn.execute("SELECT * FROM transactions WHERE status = 'PENDING'").fetchall()
        if not pending: bot.send_message(message.from_user.id, "🟢 هیچ رسیدی در انتظار نیست.")
        for trx in pending:
            markup = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("✅ تایید", callback_data=f"trx_approve_{trx['id']}"), types.InlineKeyboardButton("❌ رد", callback_data=f"trx_reject_{trx['id']}"))
            if trx['photo_id'].startswith("کد پیگیری"):
                bot.send_message(message.from_user.id, f"💳 **درخواست شارژ متنی مینی‌اپ**\n\n👤 کاربر: `{trx['user_id']}`\n💵 مبلغ: {trx['amount']:,} ت\n📌 اطلاعات: {trx['photo_id']}", reply_markup=markup)
            else:
                bot.send_photo(message.from_user.id, trx['photo_id'], caption=f"💵 مبلغ: {trx['amount']:,} ت\n👤 کاربر: {trx['user_id']}", reply_markup=markup)
    elif t == '📊 گزارش دیتابیس‌ها':
        total_users = conn.execute("SELECT COUNT(*) as count FROM users").fetchone()['count']
        total_plans = conn.execute("SELECT COUNT(*) as count FROM plans").fetchone()['count']
        total_orders = conn.execute("SELECT COUNT(*) as count FROM orders WHERE status='COMPLETED'").fetchone()['count']
        bot.send_message(message.from_user.id, f"📊 آمار دیتابیس:\n\n👥 کل کاربران: {total_users} نفر\n📦 کل پلن‌های فعال: {total_plans} عدد\n✅ سفارشات موفق: {total_orders} عدد")
    elif t == '👥 کاربران فروشگاه':
        users = conn.execute("SELECT user_id FROM users LIMIT 15").fetchall()
        user_list = "\n".join([f"👤 `{u['user_id']}`" for u in users])
        bot.send_message(message.from_user.id, f"👥 لیست آخرین کاربران فعال:\n\n{user_list}", parse_mode="Markdown")
    elif t == '🎨 تنظیمات ظاهری و متون':
        markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True).add("✏️ تغییر نام فروشگاه", "✏️ تغییر شماره کارت", "✏️ تغییر آیدی پشتیبانی", "🎨 تغییر رنگ مینی‌اپ", "✏️ تغییر متن خوش‌آمدگویی", "🌐 ست کردن لینک رندر", "🔙 بازگشت به منوی اصلی شیشه‌ای")
        bot.send_message(message.from_user.id, "🎨 یکی از گزینه‌ها را جهت پیکربندی انتخاب کنید:", reply_markup=markup)
    elif t == '➕ اضافه کردن پنل وی‌پی‌آن':
        markup = types.ReplyKeyboardMarkup(resize_keyboard=True).add("🛒 کاربر عادی", "💼 فروش عمده", "🔙 لغو عملیات")
        msg = bot.send_message(message.from_user.id, "نوع پلن را انتخاب کنید:", reply_markup=markup)
        bot.register_next_step_handler(msg, process_plan_type)
    elif t == '➕ افزودن ادمین جدید' and message.from_user.id == OWNER_ID:
        msg = bot.send_message(message.from_user.id, "👤 آیدی عددی ادمین جدید را وارد کنید:")
        bot.register_next_step_handler(msg, process_add_admin)
    conn.close()

# --- سیستم استپ‌هندلرهای ادمین پنل برای شخصی‌سازی متون و افزودن مقادیر ---
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
    markup = types.InlineKeyboardMarkup().add(
        types.InlineKeyboardButton("🔵 آبی هوشمند", callback_data="set_clr__#3b82f6"),
        types.InlineKeyboardButton("🟢 سبز زمردی", callback_data="set_clr__#10b981"),
        types.InlineKeyboardButton("🔴 قرمز یاقوتی", callback_data="set_clr__#ef4444"),
        types.InlineKeyboardButton("🟣 بنفش لوکس", callback_data="set_clr__#8b5cf6")
    )
    bot.send_message(message.from_user.id, "🎨 یک رنگ جذاب برای مینی‌اپ انتخاب کنید:", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == '🌐 ست کردن لینک رندر' and is_admin(m.from_user.id))
def change_backend_url_start(message):
    msg = bot.send_message(message.from_user.id, "🌐 آدرس کامل وب‌سرویس رندر خود را وارد کنید:", reply_markup=types.ReplyKeyboardRemove())
    bot.register_next_step_handler(msg, lambda m: save_generic_setting(m, 'backend_url'))

def save_generic_setting(message, key):
    set_setting(key, message.text)
    bot.send_message(message.from_user.id, "✅ تغییرات ثبت شد!", reply_markup=get_admin_keyboard(message.from_user.id))

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
    msg = bot.send_message(message.from_user.id, "💰 قیمت پنل را به تومان وارد کنید:")
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

def process_add_admin(message):
    try:
        new_admin_id = int(message.text)
        conn = get_db_connection()
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (new_admin_id,))
        conn.commit()
        conn.close()
        bot.send_message(message.from_user.id, f"✅ ادمین {new_admin_id} با موفقیت اضافه شد.", reply_markup=get_admin_keyboard(message.from_user.id))
    except ValueError:
        bot.send_message(message.from_user.id, "❌ آیدی عددی نامعتبر است.")

# ================= 🚀 API‌های پیشرفته درون مینی‌اپ =================

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/api/shop_config')
def get_shop_config():
    user_id = request.args.get('user_id', type=int)
    conn = get_db_connection()
    user_data = conn.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)).fetchone() if user_id else None
    conn.close()
    return jsonify({"shop_name": get_setting('shop_name'), "card_number": get_setting('card_number'), "theme_color": get_setting('theme_color'), "balance": user_data['balance'] if user_data else 0})

@app.route('/api/get_plans')
def get_plans():
    conn = get_db_connection()
    plans = conn.execute("SELECT * FROM plans").fetchall()
    conn.close()
    return jsonify([dict(p) for p in plans])

@app.route('/api/buy_plan_direct', methods=['POST'])
def buy_plan_direct():
    data = request.json
    user_id = data.get('user_id')
    plan_id = data.get('plan_id')
    
    conn = get_db_connection()
    plan = conn.execute("SELECT * FROM plans WHERE id = ?", (plan_id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()
    
    if not plan or not user:
        conn.close()
        return jsonify({"success": False, "message": "اطلاعات نامعتبر"})
    
    if user['balance'] < plan['price']:
        conn.close()
        return jsonify({"success": False, "message": "موجودی کیف پول شما کافی نیست! ابتدا حساب را شارژ کنید."})
        
    new_balance = user['balance'] - plan['price']
    new_spent = user['total_spent'] + plan['price']
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    
    conn.execute("INSERT INTO orders (user_id, plan_name, price, status, date) VALUES (?, ?, ?, 'PENDING', ?)", (user_id, plan['name'], plan['price'], today_str))
    conn.execute("UPDATE users SET balance = ?, total_spent = ? WHERE user_id = ?", (new_balance, new_spent, user_id))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(OWNER_ID, f"🛍️ **سفارش جدید از مینی‌اپ مستقل!**\n\n👤 کاربر: `{user_id}`\n📦 پلن: {plan['name']}\n💰 قیمت: {plan['price']:,} تومان")
    except: pass
    
    return jsonify({"success": True})

@app.route('/api/submit_payment_direct', methods=['POST'])
def submit_payment_direct():
    data = request.json
    user_id = data.get('user_id')
    amount = data.get('amount')
    ref_code = data.get('ref_code')
    
    conn = get_db_connection()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn.execute("INSERT INTO transactions (user_id, amount, photo_id, date) VALUES (?, ?, ?, ?)", (user_id, amount, f"کد پیگیری: {ref_code}", today))
    conn.commit()
    conn.close()
    
    try:
        bot.send_message(OWNER_ID, f"💳 **اعلام واریزی آنلاین از مینی‌اپ!**\n\n👤 کاربر: `{user_id}`\n💵 مبلغ: {amount:,} تومان\n📌 کدپیگیری: {ref_code}\n\n⚙️ جهت تایید به منوی رسیدها بروید.")
    except: pass
    
    return jsonify({"success": True})

@app.route('/api/get_user_orders')
def get_user_orders():
    user_id = request.args.get('user_id', type=int)
    conn = get_db_connection()
    orders = conn.execute("SELECT * FROM orders WHERE user_id = ? ORDER BY id DESC", (user_id,)).fetchall()
    conn.close()
    return jsonify([dict(o) for o in orders])

def start_bot_polling():
    print("NEXOVPN Single-Instance Pro Bot Running... 🚀")
    bot.infinity_polling()

threading.Thread(target=start_bot_polling, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
