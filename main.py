import sqlite3
import csv
import datetime
from telegram import (
    Update,
    BotCommand,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)
import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

from config import BOT_TOKEN, ADMIN_CHAT_ID, MAIN_MENU_KEYBOARD, TIMEZONE, IMAGE_DIR, DB_FILE
from database import (
    init_db,
    db_add_repair,
    db_find_job,
    db_update_status,
    db_get_today_jobs,
    db_update_profit,
    db_add_ledger,
    db_get_customer_balance,
)
from printer import print_repair_token, print_eod_report
from modules.inventory import (
    inventory_main_menu,
    start_add_category,
    save_category_name,
    category_detail_menu,
    list_items_in_category,
    handle_qty_change,
    handle_item_delete,
    start_add_item,
    get_item_name,
    get_item_qty,
    get_item_cost,
    get_item_sell,
    get_item_warranty,
    start_item_edit,
    select_edit_field,
    save_edit_val,
    send_8am_restock_alert,
    cancel_inv,
    ADD_CAT_NAME,
    ITEM_NAME,
    ITEM_QTY,
    ITEM_COST,
    ITEM_SELL,
    ITEM_WARRANTY,
    EDIT_SELECT_FIELD,
    EDIT_NEW_VAL,
)

# ================= SECURITY DECORATOR =================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if update.effective_user.id != ADMIN_CHAT_ID:
            await update.effective_message.reply_text("⛔ Unauthorized access.")
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)
    return wrapper

# ================= CONVERSATION STATES =================
NAME, MODEL, FAULT, REPAIR_DATE, COST_PRICE, CHARGED_PRICE, LOCK_CODE, IMEI, PHOTO = range(9)
EOD_PROFIT_INPUT = 1
LEDGER_NAME, LEDGER_AMOUNT, LEDGER_NOTE = range(9, 12)
PAYMENT_NAME, PAYMENT_AMOUNT, PAYMENT_NOTE = range(12, 15)
KHATA_SEARCH = 15

# ================= MENU & NAVIGATION =================
@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_markdown("🛠 *SAMEER MOBILE - Control Panel*", reply_markup=MAIN_MENU_KEYBOARD)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END

async def handle_menu_shortcuts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "📊 Check Status":
        await update.message.reply_text("Send: `/status [JobID]` (e.g., `/status 1001`)", parse_mode="Markdown")
    elif text == "🖨️ Reprint Token":
        await update.message.reply_text("Send: `/reprint [JobID]` (e.g., `/reprint 1001`)", parse_mode="Markdown")

# ================= REPAIRS MODULE =================
@admin_only
async def start_new_repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📝 *New Repair*\n\nEnter *Customer Name*:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return NAME

async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("Enter *Device Model*:", parse_mode="Markdown")
    return MODEL

async def get_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model"] = update.message.text.strip()
    await update.message.reply_text("Describe the *Fault*:", parse_mode="Markdown")
    return FAULT

async def get_fault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fault"] = update.message.text.strip()
    await update.message.reply_text(
        "Enter *Date* (YYYY-MM-DD) or tap *Today*:",
        reply_markup=ReplyKeyboardMarkup([["Today"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return REPAIR_DATE

async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["date"] = datetime.date.today().strftime("%Y-%m-%d") if inp.lower() == "today" else inp
    await update.message.reply_text("Enter *Part/Repair Cost* (₹):", reply_markup=ReplyKeyboardRemove(), parse_mode="Markdown")
    return COST_PRICE

async def get_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["cost"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number:")
        return COST_PRICE
    await update.message.reply_text("Enter *Price Charged to Customer* (₹):", parse_mode="Markdown")
    return CHARGED_PRICE

async def get_charged(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["charged"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number:")
        return CHARGED_PRICE
    await update.message.reply_text(
        "Enter *PIN / Pattern Lock* (or tap Skip):",
        reply_markup=ReplyKeyboardMarkup([["No Lock / Skip"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return LOCK_CODE

async def get_lock_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["lock_code"] = "None" if "skip" in inp.lower() or "no lock" in inp.lower() else inp
    await update.message.reply_text(
        "Enter *IMEI* (or tap Skip):",
        reply_markup=ReplyKeyboardMarkup([["Skip IMEI"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return IMEI

async def get_imei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["imei"] = "N/A" if inp.lower() == "skip imei" else inp
    await update.message.reply_text(
        "Send *Condition Photo* (or tap Skip):",
        reply_markup=ReplyKeyboardMarkup([["Skip Image"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return PHOTO

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    fname = f"{context.user_data.get('model', 'device')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg".replace(" ", "_")
    await photo_file.download_to_drive(f"{IMAGE_DIR}/{fname}")
    context.user_data["image_status"] = fname
    return await save_repair(update, context)

async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["image_status"] = "No Image"
    return await save_repair(update, context)

async def save_repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    res = db_add_repair(data)
    job_id = res["job_id"]
    printed, stat = print_repair_token(data, job_id)
    badge = "🖨️ *Token Printed!*" if printed else f"⚠️ *Print Error:* `{stat}`"
    summary = (
        f"✅ *Repair Saved*\n🏷 *Token:* `#{job_id}`\n👤 *Customer:* {data['name']}\n📱 *Model:* {data['model']}\n"
        f"🔧 *Fault:* {data['fault']}\n🔐 *Lock:* `{data.get('lock_code', 'None')}`\n💰 *Charged:* ₹{data['charged']:.2f}\n{badge}"
    )
    await update.message.reply_markdown(summary, reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END

# ================= STATUS UPDATE =================
@admin_only
async def check_or_update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/status 1001`", parse_mode="Markdown")
        return
    job_id = context.args[0].strip()
    res = db_find_job(job_id)
    if res.get("status") != "success":
        await update.message.reply_text(f"❌ Job `#{job_id}` not found.")
        return

    keyboard = [
        [
            InlineKeyboardButton("⏳ In Progress", callback_data=f"st_{job_id}_In Progress"),
            InlineKeyboardButton("✅ Completed", callback_data=f"st_{job_id}_Completed"),
        ],
        [
            InlineKeyboardButton("📦 Delivered", callback_data=f"st_{job_id}_Delivered"),
            InlineKeyboardButton("❌ Returned", callback_data=f"st_{job_id}_Returned"),
        ],
    ]
    await update.message.reply_markdown(
        f"📱 *Job #{job_id}* ({res['model']})\n👤 Customer: {res['name']}\n🔐 Lock: `{res.get('lock_code', 'None')}`\nStatus: `{res['job_status']}`\nSelect new status:",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

async def handle_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, job_id, new_status = query.data.split("_", 2)
    db_update_status(job_id, new_status)
    await query.edit_message_text(f"✅ Job `#{job_id}` updated to *{new_status}*.", parse_mode="Markdown")

# ================= LEDGER MODULE =================
@admin_only
async def start_udhar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📒 *Add Udhar*\n\nEnter *Customer Name*:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return LEDGER_NAME

async def get_udhar_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["l_name"] = update.message.text.strip()
    await update.message.reply_text("Enter *Due Amount* (₹):", parse_mode="Markdown")
    return LEDGER_AMOUNT

async def get_udhar_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["l_amount"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter valid amount:")
        return LEDGER_AMOUNT
    await update.message.reply_text("Enter *Reason / Note*:", parse_mode="Markdown")
    return LEDGER_NOTE

async def save_udhar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    today = datetime.date.today().strftime("%Y-%m-%d")
    name, amt = context.user_data["l_name"], context.user_data["l_amount"]
    db_add_ledger(today, name, "Debit", amt, note)
    await update.message.reply_markdown(f"✅ *Udhar Recorded!*\n👤 {name}\n💰 ₹{amt:.2f}\n📝 {note}", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END

@admin_only
async def start_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("💵 *Receive Payment*\n\nEnter *Customer Name*:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return PAYMENT_NAME

async def get_payment_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["p_name"] = update.message.text.strip()
    await update.message.reply_text("Enter *Amount Received* (₹):", parse_mode="Markdown")
    return PAYMENT_AMOUNT

async def get_payment_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["p_amount"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter valid amount:")
        return PAYMENT_AMOUNT
    await update.message.reply_text("Payment Mode (Cash/UPI):", parse_mode="Markdown")
    return PAYMENT_NOTE

async def save_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    note = update.message.text.strip()
    today = datetime.date.today().strftime("%Y-%m-%d")
    name, amt = context.user_data["p_name"], context.user_data["p_amount"]
    db_add_ledger(today, name, "Credit", amt, note)
    await update.message.reply_markdown(f"✅ *Payment Logged!*\n👤 {name}\n💵 ₹{amt:.2f}\n📝 {note}", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END

@admin_only
async def start_khata_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🔍 Enter *Customer Name* for Khata balance:", parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
    return KHATA_SEARCH

async def perform_khata_lookup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text.strip()
    res = db_get_customer_balance(name)
    bal = res["balance"]
    status_line = f"🔴 *Pending Due:* ₹{bal:,.2f}" if bal > 0 else f"🟢 *All Cleared / Advance:* ₹{abs(bal):,.2f}"
    hist = "\n".join([f"• `{h['date']}` | {h['type']}: ₹{h['amount']:.0f} ({h['note']})" for h in res["history"]])
    msg = f"📒 *Customer Khata: {name}*\n━━━━━━━━━━━━━━━━━━━\nUdhar: ₹{res['total_debit']:,.2f}\nPaid:  ₹{res['total_credit']:,.2f}\n{status_line}\n\n*Recent Transactions:*\n{hist}"
    await update.message.reply_markdown(msg, reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END

# ================= EOD CLOSING MODULE =================
@admin_only
async def start_eod_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    jobs = db_get_today_jobs(today_str)
    if not jobs:
        await target.reply_text(f"ℹ️ No repairs logged for today (`{today_str}`).", reply_markup=MAIN_MENU_KEYBOARD)
        return ConversationHandler.END
    context.user_data["eod_jobs"] = jobs
    context.user_data["current_index"] = 0
    context.user_data["entered_profits"] = []
    context.user_data["date"] = today_str
    return await prompt_next_eod(update, context)

async def prompt_next_eod(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs, idx = context.user_data["eod_jobs"], context.user_data["current_index"]
    j = jobs[idx]
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(
        f"📱 *Job {idx + 1}/{len(jobs)}* — `Token #{j['job_id']}`\n👤 {j['customer']} | {j['model']} ({j['fault']})\n💸 Cost: ₹{j['cost']:.0f} | Charged: ₹{j['charged']:.0f}\nEst. Profit: ₹{j['auto_profit']:.0f}\n\nEnter actual profit:",
        reply_markup=ReplyKeyboardMarkup([[f"Keep ₹{j['auto_profit']:.0f}"]], one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return EOD_PROFIT_INPUT

async def handle_profit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs, idx = context.user_data["eod_jobs"], context.user_data["current_index"]
    j = jobs[idx]
    inp = update.message.text.strip()
    val = j["auto_profit"] if "Keep" in inp else float(inp)
    j["final_profit"] = val
    context.user_data["entered_profits"].append(j)
    db_update_profit(j["job_id"], val)
    context.user_data["current_index"] += 1
    if context.user_data["current_index"] < len(jobs):
        return await prompt_next_eod(update, context)

    records = context.user_data["entered_profits"]
    d_str = context.user_data["date"]
    tot_cost = sum(x["cost"] for x in records)
    tot_charged = sum(x["charged"] for x in records)
    tot_profit = sum(x["final_profit"] for x in records)
    print_eod_report(d_str, len(records), tot_cost, tot_charged, tot_profit)

    summary = "\n".join([f"• `#{x['job_id']}` {x['model']} ➔ ₹{x['final_profit']:,.2f}" for x in records])
    await update.message.reply_markdown(
        f"🏁 *EOD Completed ({d_str})*\n\n{summary}\n━━━━━━━━━━━━━━━━━━━\n📱 Jobs: {len(records)} | 💰 Revenue: ₹{tot_charged:,.2f}\n📈 Net Profit: ₹{tot_profit:,.2f}\n🖨️ *Receipt Printed to Bench!*",
        reply_markup=MAIN_MENU_KEYBOARD,
    )
    return ConversationHandler.END

# ================= 9:00 PM REMINDER =================
async def send_9pm_reminder(context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("🏁 Start End of Day Review", callback_data="start_eod")]]
    await context.bot.send_message(
        chat_id=ADMIN_CHAT_ID,
        text="🔔 *9:00 PM Closing Reminder*\nReady to review profits and print closing receipt?",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )

# ================= EXPORT & REPRINT =================
@admin_only
async def reprint_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/reprint 1001`", parse_mode="Markdown")
        return
    res = db_find_job(context.args[0].strip())
    if res.get("status") != "success":
        await update.message.reply_text("❌ Job not found.")
        return
    printed, stat = print_repair_token(res, res["job_id"])
    await update.message.reply_text(f"🖨️ Reprint #{res['job_id']}: {stat}", reply_markup=MAIN_MENU_KEYBOARD)

@admin_only
async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM repairs")
    rows, headers = c.fetchall(), [d[0] for d in c.description]
    conn.close()
    with open("repairs_backup.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)
    with open("repairs_backup.csv", "rb") as f:
        await update.message.reply_document(document=f, filename="repairs_backup.csv", caption="📊 Database CSV Export")

# ================= SET BOT COMMANDS =================
async def post_init(application):
    await application.bot.set_my_commands([
        BotCommand("start", "Open Main Menu"),
        BotCommand("newrepair", "Log a new repair job"),
        BotCommand("udhar", "Log customer due amount"),
        BotCommand("payment", "Log payment received"),
        BotCommand("khata", "Check customer balance"),
        BotCommand("eod", "Start End of Day review"),
        BotCommand("status", "Check/Update job status"),
        BotCommand("reprint", "Reprint thermal receipt"),
        BotCommand("export", "Export database CSV backup"),
    ])

# ================= MAIN EXECUTION =================
def main():
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    # Core Navigation & Buttons
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("reprint", reprint_token))
    app.add_handler(CommandHandler("status", check_or_update_status))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(CallbackQueryHandler(handle_status_callback, pattern="^st_"))
    app.add_handler(MessageHandler(filters.Regex("^📥 Export Backup$"), export_data))
    app.add_handler(MessageHandler(filters.Regex("^(📊 Check Status|🖨️ Reprint Token)$"), handle_menu_shortcuts))

    # Repair Flow
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("newrepair", start_new_repair),
            MessageHandler(filters.Regex("^➕ New Repair$"), start_new_repair),
        ],
        states={
            NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            MODEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_model)],
            FAULT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_fault)],
            REPAIR_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_date)],
            COST_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_cost)],
            CHARGED_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_charged)],
            LOCK_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_lock_code)],
            IMEI: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_imei)],
            PHOTO: [
                MessageHandler(filters.PHOTO, handle_photo),
                MessageHandler(filters.TEXT & ~filters.COMMAND, skip_photo),
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Udhar Flow
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("udhar", start_udhar),
            MessageHandler(filters.Regex("^📒 Udhar / Due$"), start_udhar),
        ],
        states={
            LEDGER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_udhar_name)],
            LEDGER_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_udhar_amount)],
            LEDGER_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_udhar)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Payment Flow
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("payment", start_payment),
            MessageHandler(filters.Regex("^💵 Receive Payment$"), start_payment),
        ],
        states={
            PAYMENT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment_name)],
            PAYMENT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_payment_amount)],
            PAYMENT_NOTE: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_payment)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # Khata Lookup Flow
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("khata", start_khata_lookup),
            MessageHandler(filters.Regex("^🔍 Customer Khata$"), start_khata_lookup),
        ],
        states={
            KHATA_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, perform_khata_lookup)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    # EOD Flow
    app.add_handler(ConversationHandler(
        entry_points=[
            CommandHandler("eod", start_eod_flow),
            CallbackQueryHandler(start_eod_flow, pattern="^start_eod$"),
            MessageHandler(filters.Regex("^🏁 End of Day$"), start_eod_flow),
        ],
        states={
            EOD_PROFIT_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_profit_input)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
    ))

    # ================= INVENTORY HANDLERS =================
    app.add_handler(MessageHandler(filters.Regex("^📦 Stock / Inventory$"), inventory_main_menu))
    app.add_handler(CallbackQueryHandler(inventory_main_menu, pattern="^cat_back_main$"))
    app.add_handler(CallbackQueryHandler(category_detail_menu, pattern="^cat_view_"))
    app.add_handler(CallbackQueryHandler(list_items_in_category, pattern="^item_list_"))
    app.add_handler(CallbackQueryHandler(handle_qty_change, pattern="^qty_(add|sub)_"))
    app.add_handler(CallbackQueryHandler(handle_item_delete, pattern="^item_del_"))

    # Add Category Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_category, pattern="^cat_add_new$")],
        states={
            ADD_CAT_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_category_name)],
        },
        fallbacks=[CommandHandler("cancel", cancel_inv)],
        per_message=False,
    ))

    # Add Item Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_add_item, pattern="^item_add_")],
        states={
            ITEM_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_name)],
            ITEM_QTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_qty)],
            ITEM_COST: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_cost)],
            ITEM_SELL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_sell)],
            ITEM_WARRANTY: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_item_warranty)],
        },
        fallbacks=[CommandHandler("cancel", cancel_inv)],
        per_message=False,
    ))

    # Edit Item Conversation
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(start_item_edit, pattern="^item_edit_")],
        states={
            EDIT_SELECT_FIELD: [CallbackQueryHandler(select_edit_field, pattern="^edfield_")],
            EDIT_NEW_VAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, save_edit_val)],
        },
        fallbacks=[CommandHandler("cancel", cancel_inv)],
        per_message=False,
    ))

    # ================= DAILY SCHEDULER JOBS =================
    if app.job_queue:
        # 8:00 AM Daily Restock Alert
        app.job_queue.run_daily(
            send_8am_restock_alert,
            time=datetime.time(hour=8, minute=0, second=0, tzinfo=TIMEZONE),
        )
        # 9:00 PM Closing Reminder
        app.job_queue.run_daily(
            send_9pm_reminder,
            time=datetime.time(hour=21, minute=0, second=0, tzinfo=TIMEZONE),
        )
        print("⏰ 8:00 AM restock and 9:00 PM EOD reminder scheduled.")

    print("🚀 Shop Automation Bot (Modular Architecture) is LIVE.")
    app.run_polling()

if __name__ == "__main__":
    main()