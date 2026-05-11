import logging
import sqlite3
import asyncio
import sys
import httpx
import random
import string

import os
if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from db import db_query, DATABASE_URL

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, ConversationHandler, ContextTypes, filters
import httpx

# --- CONFIG ---
ADMIN_TOKEN = "8725003968:AAHnPLZWjoCsIPt4hKYEmzQmLkkRBogVBnQ"
MAIN_BOT_TOKEN = "8203606211:AAGNWwowtjnPMoI5uxo6Pt5j7a_5-srfCAo"
ADMIN_ID = 7529580444
DB_NAME = "nexus_bot.db"

# === MONKEY PATCH FOR BOT API 9.4+ CUSTOM EMOJI ON BUTTONS ===
original_to_dict = InlineKeyboardButton.to_dict

def custom_to_dict(self, *args, **kwargs):
    d = original_to_dict(self, *args, **kwargs)
    if 'text' in d and '||emoji:' in d['text']:
        parts = d['text'].split('||emoji:')
        d['text'] = parts[0]
        d['icon_custom_emoji_id'] = parts[1]
    return d

InlineKeyboardButton.to_dict = custom_to_dict
# --- EMOJI HELPERS ---
EMOJI_MAP = {
    "TELEGRAM": "5330237710655306682",
    "PRIME VIDEO": "5346056560537779652",
    "CAPCUT": "5364339557712020484",
    "CHATGPT": "5359726582447487916",
    "EARTH": "6093615976551551886",
    "NETFLIX": "4958664490557112996",
    "SPOTIFY": "4958941520242672323",
    "CRUNCHYROLL": "4958621463574741708",
    "YOUTUBE": "4985489542027936396",
    "EXPRESS VPN": "5796153709931009517",
    "GOOGLE": "5794295402136081349",
    "DUOLINGO": "5796371348808799072",
    "HUB": "6298428643181856596",
    "CANVA": "5796214303329620386",
    "NORD": "5397782960512444700",
    "GROK": "5918183506155933842",
    "CLAUDE": "6124926696161286141",
    "GEMINI": "5319114097545987364",
    "SURFSHARK": "5796592771552777710",
    "P@N*EL": "5217549292205528507",
    "F@PHOUSE": "5373159350363764070"
}

def get_prod_emoji_id(name):
    name_upper = name.upper()
    for key, val in EMOJI_MAP.items():
        if key in name_upper: return val
    return None

def get_prod_emoji_tag(name):
    e_id = get_prod_emoji_id(name)
    if e_id: return f'<tg-emoji emoji-id="{e_id}">✨</tg-emoji>'
    return "📦"

# States
ADD_PROD_NAME = 1
ADD_PROD_PRICE = 2
ADD_STOCK_DATA = 4
GEN_CODE_VAL = 5
BROADCAST_MSG = 6
ADJUST_BAL_ID = 7
ADJUST_BAL_AMT = 8
EDIT_PROD_PRICE = 9
EDIT_PROD_NAME = 10
PROFILE_VIEW = 11

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("nexus_max.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Database helpers imported from db.py

def main_menu():
    return ReplyKeyboardMarkup([
        ["Review Payments", "Bot Stats"],
        ["Products", "Gift Codes"],
        ["Broadcast", "Manage Users"],
        ["Maintenance", "Refresh"]
    ], resize_keyboard=True)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    text = (
        f"<tg-emoji emoji-id=\"5319213852456402176\">💙</tg-emoji> <b>NEXUS MAX ADMIN PANEL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5199785165735367039\">⚡</tg-emoji> <b>Status:</b> 🟢 Active\n\n"
        f"Control the bot ecosystem from here."
    )
    await update.message.reply_text(text, reply_markup=main_menu(), parse_mode="HTML")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ <b>Action Cancelled.</b>", reply_markup=main_menu(), parse_mode="HTML")
    return ConversationHandler.END

async def review_payments(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db_query("SELECT id, user_id, amount, utr FROM transactions WHERE status IN ('pending', 'review')", fetch="all")
    if not rows:
        await update.message.reply_text("✅ No pending reviews.")
        return
    for r in rows:
        text = f"💳 <b>DEPOSIT #{r[0]}</b>\n👤 User: <code>{r[1]}</code>\n💰 Amount: <code>{r[2]:.2f} USDT</code>\n🔢 UTR: <code>{r[3] if r[3] else 'PENDING'}</code>"
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("Approve||emoji:5215420556089776398", callback_data=f"pay_appr_{r[0]}"), 
            InlineKeyboardButton("Reject||emoji:5355303470507251772", callback_data=f"pay_rej_{r[0]}")
        ]])
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def handle_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; action, tx_id = query.data.split('_')[1:3]
    res = db_query("SELECT user_id, amount FROM transactions WHERE id = ?", (tx_id,), fetch="one")
    if not res: return
    u_id, amt = res
    if action == "appr":
        db_query("UPDATE transactions SET status='completed' WHERE id = ?", (tx_id,), commit=True)
        db_query("UPDATE users SET balance_usdt = balance_usdt + ? WHERE user_id = ?", (amt, u_id), commit=True)
        await query.edit_message_text(f"✅ Approved ${amt} for User {u_id}")
        async with httpx.AsyncClient() as client:
            try: await client.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json={"chat_id": u_id, "text": f"✅ <b>Deposit Confirmed!</b>\n\nYour wallet has been credited with <b>{amt:.2f} USDT</b>. ⚡", "parse_mode": "HTML"})
            except: pass
    else:
        db_query("UPDATE transactions SET status='rejected' WHERE id = ?", (tx_id,), commit=True)
        await query.edit_message_text(f"❌ Rejected Payment #{tx_id}")

# --- PRODUCT MGMT ---
async def product_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🛍️ <b>NEXUS PRODUCT CENTER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome to the central product hub. Here you can launch new items, monitor inventory, and refill stock with ease.\n\n"
        "💡 <i>Tip: Use 'Inventory' to edit prices or delete items.</i>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("Create Product||emoji:5377660214096974712", callback_data="prod_add"), 
            InlineKeyboardButton("Inventory||emoji:5355303470507251772", callback_data="prod_list")
        ],
        [
            InlineKeyboardButton("Rapid Restock||emoji:5215420556089776398", callback_data="prod_stock_list"),
            InlineKeyboardButton("🧹 Clear All Stock", callback_data="prod_clear_all")
        ],
        [InlineKeyboardButton("Back to Admin||emoji:5001636926843782163", callback_data="back_main")]
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")
    else:
        await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")

async def prod_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    rows = db_query("SELECT id, name, stock FROM products", fetch="all")
    if not rows: await query.edit_message_text("❌ No products found."); return
    
    buttons = []
    for r in rows:
        stock_text = " (Out of stock)" if r[2] <= 0 else ""
        buttons.append([InlineKeyboardButton(f"📦 {r[1]}{stock_text}||emoji:5355303470507251772", callback_data=f"prod_mng_{r[0]}")])
    buttons.append([InlineKeyboardButton("🔙 Back to Menu||emoji:5001636926843782163", callback_data="prod_hub")])
    
    await query.edit_message_text("📋 <b>INVENTORY LIST</b>\n━━━━━━━━━━━━━━━━━━━━\nSelect a product to manage:", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def handle_prod_manage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    p_id = int(query.data.split('_')[2])
    r = db_query("SELECT id, name, price_usdt, stock FROM products WHERE id = ?", (p_id,), fetch="one")
    if not r: await query.edit_message_text("❌ Product not found."); return
    
    text = (
        f"🏷️ <b>PRODUCT DETAILS</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📛 <b>Name:</b> {r[1]}\n"
        f"💰 <b>Price:</b> <code>${r[2]:.2f}</code>\n"
        f"📦 <b>Stock:</b> <code>{r[3]} units</code>\n"
        f"🆔 <b>Ref:</b> <code>#{r[0]}</code>"
    )
    kb = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✏️ Edit Price", callback_data=f"prod_edit_prc_{r[0]}"),
            InlineKeyboardButton("📈 Restock", callback_data=f"stock_sel_{r[0]}")
        ],
        [
            InlineKeyboardButton("🗑️ Delete Product", callback_data=f"prod_del_{r[0]}")
        ],
        [
            InlineKeyboardButton("🔙 Back to List", callback_data="prod_list")
        ]
    ])
    await query.edit_message_text(text, reply_markup=kb, parse_mode="HTML")

async def handle_prod_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; p_id = query.data.split('_')[2]
    db_query("DELETE FROM products WHERE id = ?", (p_id,), commit=True)
    db_query("DELETE FROM accounts WHERE product_id = ?", (p_id,), commit=True)
    await query.edit_message_text("✅ <b>Product deleted!</b>", parse_mode="HTML")

async def clear_all_stock(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    db_query("UPDATE products SET stock = 0", commit=True)
    db_query("DELETE FROM accounts WHERE is_sold = 0", commit=True)
    await query.edit_message_text("🧹 <b>All stock cleared!</b>\n\nEvery product is now set to 0 stock, and unsold accounts have been purged from the system.", parse_mode="HTML")

async def prod_edit_price_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; p_id = int(query.data.split('_')[3])
    context.user_data["edit_prod_id"] = p_id
    await query.edit_message_text("💰 <b>Enter New Price (USDT):</b>\n<i>Example: 2.50</i>", parse_mode="HTML")
    return EDIT_PROD_PRICE

async def prod_edit_price_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: price = float(update.message.text)
    except: await update.message.reply_text("❌ Invalid price format."); return EDIT_PROD_PRICE
    p_id = context.user_data["edit_prod_id"]
    db_query("UPDATE products SET price_usdt = ? WHERE id = ?", (price, p_id), commit=True)
    res = db_query("SELECT name FROM products WHERE id = ?", (p_id,), fetch="one")
    await update.message.reply_text(f"✅ <b>Price Updated!</b>\n\nProduct: {res[0]}\nNew Price: ${price:.2f}", parse_mode="HTML")
    return ConversationHandler.END

async def prod_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("✨ <b>LAUNCH NEW PRODUCT</b>\n━━━━━━━━━━━━━━━━━━━━\nWhat is the name of the new product?", parse_mode="HTML"); return ADD_PROD_NAME

async def prod_add_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_prod_name"] = update.message.text
    await update.message.reply_text("💰 <b>Enter Price (USDT):</b>\n<i>Type /cancel to abort</i>", parse_mode="HTML"); return ADD_PROD_PRICE

async def prod_add_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: price = float(update.message.text)
    except: await update.message.reply_text("❌ Invalid price."); return ADD_PROD_PRICE
    name = context.user_data["new_prod_name"]
    db_query("INSERT INTO products (name, price_usdt, stock) VALUES (?, ?, 0)", (name, price), commit=True)
    await update.message.reply_text(f"✅ <b>Product Added!</b>\nName: {name}\nPrice: ${price:.2f}"); return ConversationHandler.END

# --- RESTOCK LOGIC (NEW) ---
async def prod_stock_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    products = db_query("SELECT id, name FROM products", fetch="all")
    if not products: await update.callback_query.answer("No products to restock!", show_alert=True); return
    buttons = [[InlineKeyboardButton(p[1], callback_data=f"stock_sel_{p[0]}")] for p in products]
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="back_main")])
    await update.callback_query.edit_message_text("📈 <b>Select Product to Restock:</b>", reply_markup=InlineKeyboardMarkup(buttons), parse_mode="HTML")

async def handle_stock_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; p_id = int(query.data.split('_')[2])
    context.user_data["stock_prod_id"] = p_id
    await query.edit_message_text("📄 <b>Paste Accounts Now</b>\n\nFormat: <code>email:password</code> (one per line)\n<i>The bot will automatically count and add them.</i>", parse_mode="HTML")
    return ADD_STOCK_DATA

async def prod_stock_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lines = update.message.text.strip().split('\n'); p_id = context.user_data["stock_prod_id"]
    count = 0
    for line in lines:
        if ':' in line:
            email, pwd = line.split(':', 1)
            db_query("INSERT INTO accounts (product_id, email, password) VALUES (?, ?, ?)", (p_id, email.strip(), pwd.strip()), commit=True)
            count += 1
    db_query("UPDATE products SET stock = stock + ? WHERE id = ?", (count, p_id), commit=True)
    res = db_query("SELECT name, stock FROM products WHERE id = ?", (p_id,), fetch="one")
    await update.message.reply_text(f"✅ <b>Stock Added!</b>\n\nProduct: {res[0]}\nAdded: {count}\nTotal in stock: {res[1]}", parse_mode="HTML")
    
    # Broadcast to all users
    emoji = get_prod_emoji_tag(res[0])
    broadcast_text = (
        f"📢 <b>STOCK UPDATE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"📦 <b>Product:</b> {emoji} <b>{res[0]}</b>\n"
        f"➕ <b>Added:</b> <code>{count}</code>\n"
        f"📊 <b>Total Stock:</b> <code>{res[1]}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━"
    )
    kb = {"inline_keyboard": [[{"text": "🛒 Buy Now", "url": f"https://t.me/{(await context.bot.get_me()).username}"}]]}
    
    users = db_query("SELECT user_id FROM users", fetch="all")
    async with httpx.AsyncClient() as client:
        for u in users:
            try:
                await client.post(
                    f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", 
                    json={
                        "chat_id": u[0], 
                        "text": broadcast_text, 
                        "reply_markup": kb,
                        "parse_mode": "HTML"
                    }
                )
                await asyncio.sleep(0.05)
            except: continue
            
    return ConversationHandler.END

# --- GIFT CODE MGMT ---
async def gift_code_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🎁 Generate Code", callback_data="code_gen")], [InlineKeyboardButton("📋 List Active Codes", callback_data="code_list")]])
    await update.message.reply_text("🎁 <b>GIFT CODE SYSTEM</b>", reply_markup=kb, parse_mode="HTML")

async def code_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db_query("SELECT code, value FROM redeem_codes WHERE is_used = 0", fetch="all")
    if not rows: await update.callback_query.answer("No active codes."); return
    text = "📋 <b>ACTIVE REDEEM CODES</b>\n━━━━━━━━━━━━━━━━━━━━\n\n"
    for r in rows: text += f"<code>{r[0]}</code> - ${r[1]:.2f}\n"
    await update.callback_query.edit_message_text(text, parse_mode="HTML")

async def generate_code_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: val = float(update.message.text)
    except: await update.message.reply_text("❌ Invalid value."); return GEN_CODE_VAL
    code = "NEX-" + ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    db_query("INSERT INTO redeem_codes (code, value) VALUES (?, ?)", (code, val), commit=True)
    await update.message.reply_text(f"🎁 <b>CODE GENERATED!</b>\n\nCode: <code>{code}</code>\nValue: <code>{val} USDT</code>", parse_mode="HTML")
    return ConversationHandler.END

# --- USER MGMT REDESIGN ---
async def manage_users_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    rows = db_query("""
        SELECT u.user_id, u.balance_usdt, 
        (SELECT COUNT(*) FROM orders WHERE user_id = u.user_id) as orders,
        (SELECT SUM(amount) FROM transactions WHERE user_id = u.user_id AND status = 'completed') as deposits
        FROM users u
        ORDER BY u.balance_usdt DESC
        LIMIT 10
    """, fetch="all")
    
    text = (
        f"<tg-emoji emoji-id=\"5319213852456402176\">💙</tg-emoji> <b>USER MANAGEMENT HUB</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<code>USER ID    | BAL  | ORD | DEP</code>\n"
    )
    for r in rows:
        dep = r[3] if r[3] else 0
        text += f"<code>{str(r[0])[:10]:<10} | {r[1]:>4.1f} | {r[2]:>3} | {dep:>3.1f}</code>\n"
    
    text += (
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🖊️ <b>Enter User ID for full profile & actions:</b>"
    )
    await update.message.reply_text(text, parse_mode="HTML")
    return ADJUST_BAL_ID

async def manage_users_profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.text.isdigit():
        await update.message.reply_text("❌ Please enter a valid numerical User ID.")
        return ADJUST_BAL_ID
    
    u_id = int(update.message.text)
    user = db_query("SELECT user_id, username, balance_usdt, created_at, language FROM users WHERE user_id = ?", (u_id,), fetch="one")
    if not user:
        await update.message.reply_text("❌ <b>User not found in database.</b>")
        return ADJUST_BAL_ID
    stats = db_query("SELECT COUNT(*), SUM(total_cost) FROM orders WHERE user_id = ?", (u_id,), fetch="one")
    
    context.user_data["adj_user_id"] = u_id
    text = (
        f"<tg-emoji emoji-id=\"5431684550424011313\">🏷️</tg-emoji> <b>USER PROFILE</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🆔 <b>ID:</b> <code>{user[0]}</code>\n"
        f"👤 <b>Username:</b> @{user[1] if user[1] else 'None'}\n"
        f"💰 <b>Balance:</b> <code>${user[2]:.2f}</code>\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"<tg-emoji emoji-id=\"5364040533498932357\">💎</tg-emoji> <b>Orders:</b> <code>{stats[0]}</code>\n"
        f"<tg-emoji emoji-id=\"5260463209562776385\">✅</tg-emoji> <b>Spent:</b> <code>${stats[1] if stats[1] else 0:.2f}</code>"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Adjust Balance||emoji:5215420556089776398", callback_data="adj_bal_start")],
        [InlineKeyboardButton("🔙 Back to Search", callback_data="user_search_back")]
    ])
    await update.message.reply_text(text, reply_markup=kb, parse_mode="HTML")
    return PROFILE_VIEW

async def handle_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    if query.data == "adj_bal_start":
        await query.edit_message_text("💰 <b>ADJUST BALANCE</b>\n━━━━━━━━━━━━━━━━━━━━\n<b>Enter amount to ADD:</b>\n<i>(Use - to subtract)</i>", parse_mode="HTML")
        return ADJUST_BAL_AMT
    elif query.data == "user_search_back":
        await query.edit_message_text("👤 <b>Enter User ID to lookup:</b>", parse_mode="HTML")
        return ADJUST_BAL_ID

async def manage_users_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: amt = float(update.message.text)
    except: await update.message.reply_text("❌ Invalid amount format."); return ADJUST_BAL_AMT
    u_id = context.user_data["adj_user_id"]
    db_query("UPDATE users SET balance_usdt = balance_usdt + ? WHERE user_id = ?", (amt, u_id), commit=True)
    await update.message.reply_text(f"✅ <b>Balance Updated!</b>\nUser <code>{u_id}</code> balance adjusted by <b>${amt:.2f}</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- MAINTENANCE ---
async def toggle_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    res = db_query("SELECT value FROM settings WHERE key='maintenance'", fetch="one")
    new_val = 'on' if res[0] == 'off' else 'off'
    db_query("UPDATE settings SET value = ? WHERE key='maintenance'", (new_val,), commit=True)
    status = "🔴 ENABLED" if new_val == 'on' else "🟢 DISABLED"
    await update.message.reply_text(f"🔧 <b>Maintenance Mode:</b> {status}", parse_mode="HTML")

# --- BROADCAST ---
async def broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("📢 <b>Enter message to broadcast:</b>\n<i>Type /cancel to abort</i>", parse_mode="HTML"); return BROADCAST_MSG

async def broadcast_finish(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text; users = db_query("SELECT user_id FROM users", fetch="all")
    count = 0
    async with httpx.AsyncClient() as client:
        for u in users:
            try:
                await client.post(f"https://api.telegram.org/bot{MAIN_BOT_TOKEN}/sendMessage", json={"chat_id": u[0], "text": f"📢 <b>ANNOUNCEMENT</b>\n━━━━━━━━━━━━━━━━━━━━\n\n{msg}", "parse_mode": "HTML"})
                count += 1; await asyncio.sleep(0.05)
            except: continue
    await update.message.reply_text(f"✅ <b>Broadcast complete!</b> Sent to {count} users."); return ConversationHandler.END

# --- STATS ---
async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    u_count = db_query("SELECT COUNT(*) FROM users", fetch="one")[0]
    o_count = db_query("SELECT COUNT(*) FROM orders", fetch="one")[0]
    revenue = db_query("SELECT SUM(total_cost) FROM orders", fetch="one")[0] or 0
    liab = db_query("SELECT SUM(balance_usdt) FROM users", fetch="one")[0] or 0
    text = (f"📊 <b>NEXUS MAX STATISTICS</b>\n━━━━━━━━━━━━━━━━━━━━\n👥 <b>Total Users:</b> <code>{u_count}</code>\n📦 <b>Total Orders:</b> <code>{o_count}</code>\n💰 <b>Total Revenue:</b> <code>${revenue:.2f}</code>\n💳 <b>User Balances:</b> <code>${liab:.2f}</code>\n━━━━━━━━━━━━━━━━━━━━")
    await update.message.reply_text(text, parse_mode="HTML")

def main():
    app = ApplicationBuilder().token(ADMIN_TOKEN).job_queue(None).build()
    fb = [CommandHandler("cancel", cancel)]
    
    code_conv = ConversationHandler(entry_points=[CallbackQueryHandler(lambda u,c: u.callback_query.edit_message_text("💰 <b>Enter value:</b>", parse_mode="HTML"), pattern="^code_gen$")], states={GEN_CODE_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, generate_code_finish)]}, fallbacks=fb)
    broad_conv = ConversationHandler(entry_points=[MessageHandler(filters.Regex("^📢 Broadcast$"), broadcast_start)], states={BROADCAST_MSG: [MessageHandler(filters.TEXT & ~filters.COMMAND, broadcast_finish)]}, fallbacks=fb)
    prod_add_conv = ConversationHandler(entry_points=[CallbackQueryHandler(prod_add_start, pattern="^prod_add$")], states={ADD_PROD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_add_price)], ADD_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_add_finish)]}, fallbacks=fb)
    prod_edit_conv = ConversationHandler(entry_points=[CallbackQueryHandler(prod_edit_price_start, pattern="^prod_edit_prc_")], states={EDIT_PROD_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_edit_price_finish)]}, fallbacks=fb)
    prod_stock_conv = ConversationHandler(entry_points=[CallbackQueryHandler(handle_stock_selection, pattern="^stock_sel_")], states={ADD_STOCK_DATA: [MessageHandler(filters.TEXT & ~filters.COMMAND, prod_stock_finish)]}, fallbacks=fb)
    user_conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Regex("^Manage Users$"), manage_users_start)], 
        states={
            ADJUST_BAL_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_users_profile)],
            PROFILE_VIEW: [CallbackQueryHandler(handle_user_callback, pattern="^(adj_bal_start|user_search_back)$")],
            ADJUST_BAL_AMT: [MessageHandler(filters.TEXT & ~filters.COMMAND, manage_users_finish)],
        }, 
        fallbacks=fb
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handlers([code_conv, broad_conv, prod_add_conv, prod_edit_conv, prod_stock_conv, user_conv])
    app.add_handler(MessageHandler(filters.Regex("^Review Payments$"), review_payments))
    app.add_handler(MessageHandler(filters.Regex("^Bot Stats$"), show_stats))
    app.add_handler(MessageHandler(filters.Regex("^Products$"), product_menu))
    app.add_handler(MessageHandler(filters.Regex("^Gift Codes$"), gift_code_menu))
    app.add_handler(MessageHandler(filters.Regex("^Maintenance$"), toggle_maintenance))
    app.add_handler(MessageHandler(filters.Regex("^Refresh$"), start))
    app.add_handler(CallbackQueryHandler(handle_payment, pattern="^pay_"))
    app.add_handler(CallbackQueryHandler(prod_list, pattern="^prod_list$"))
    app.add_handler(CallbackQueryHandler(handle_prod_manage, pattern="^prod_mng_"))
    app.add_handler(CallbackQueryHandler(product_menu, pattern="^prod_hub$"))
    app.add_handler(CallbackQueryHandler(handle_prod_delete, pattern="^prod_del_"))
    app.add_handler(CallbackQueryHandler(code_list, pattern="^code_list$"))
    app.add_handler(CallbackQueryHandler(prod_stock_list, pattern="^prod_stock_list$"))
    app.add_handler(CallbackQueryHandler(clear_all_stock, pattern="^prod_clear_all$"))
    app.add_handler(CallbackQueryHandler(lambda u,c: product_menu(u,c), pattern="^back_main$"))
    
    print("Nexus Max Admin is online!"); app.run_polling()

if __name__ == "__main__":
    try:
        loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop); main()
    except KeyboardInterrupt: pass
