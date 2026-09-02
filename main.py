import os
import socket
import datetime
from zoneinfo import  ZoneInfo
import requests
import warnings
from telegram.warnings import PTBUserWarning

warnings.filterwarnings("ignore", category=PTBUserWarning)

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

# ================= CONFIGURATION =================
BOT_TOKEN = "8870922523:AAE_AwnI-AQJPwIS6woHI0r_D7yYm6HW6zQ"
ADMIN_CHAT_ID = 6960228144
PRINTER_IP = "192.168.1.100"  # LAN Thermal Printer IP
PRINTER_PORT = 9100
TIMEZONE = ZoneInfo("Asia/Kolkata")
IMAGE_DIR = "repair_images"

WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbyJN01LaPle_BZx1T1P7y6zyHqLfUDagH0wpm_mGgjm1Dko69fiwh9qZPO1zVMQyfzT5Q/exec"

os.makedirs(IMAGE_DIR, exist_ok=True)

# ================= MAIN DASHBOARD KEYBOARD =================
# ================= MAIN DASHBOARD KEYBOARD =================
MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ New Repair", "🏁 End of Day"],
        ["🔍 Check Status", "🖨️ Reprint Token"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)

# ================= CONVERSATION STATES =================
NAME, MODEL, FAULT, REPAIR_DATE, COST_PRICE, CHARGED_PRICE, IMEI, LOCK_CODE, PHOTO = range(9)
EOD_PROFIT_INPUT = 1


# ================= HELPER API =================
def call_sheet(payload):
    try:
        r = requests.post(WEBHOOK_URL, json=payload, timeout=12)
        return r.json()
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ================= SECURITY DECORATOR =================
def admin_only(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if user_id != ADMIN_CHAT_ID:
            await update.effective_message.reply_text("⛔ Unauthorized access.")
            return ConversationHandler.END
        return await func(update, context, *args, **kwargs)

    return wrapper


# ================= NATIVE SOCKET THERMAL PRINTING =================
def send_escpos_raw(commands: bytes):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((PRINTER_IP, PRINTER_PORT))
    s.sendall(commands)
    s.close()


def print_repair_token(data, job_id):
    try:
        raw = bytearray()
        raw += b"\x1b\x40"
        raw += b"\x1b\x61\x01\x1d\x21\x11\x1b\x45\x01"
        raw += b"SAMEER MOBILE\n"
        raw += b"\x1d\x21\x00\x1b\x45\x00"
        raw += b"Mobile Repair & Solutions\n--------------------------------\n"
        raw += b"\x1d\x21\x01\x1b\x45\x01"
        raw += f"TOKEN: #{job_id}\n".encode("utf-8")
        raw += b"\x1d\x21\x00\x1b\x45\x00--------------------------------\n\x1b\x61\x00"
        raw += f"Date:     {data['date']}\n".encode("utf-8")
        raw += f"Customer: {data['name']}\n".encode("utf-8")
        raw += f"Model:    {data['model']}\n".encode("utf-8")
        raw += f"Fault:    {data['fault']}\n".encode("utf-8")

        lock = data.get("lock_code", "None")
        if lock and lock != "None":
            raw += f"Lock/PIN: {lock}\n".encode("utf-8")

        if data.get("imei") and data.get("imei") != "N/A":
            raw += f"IMEI:     {data['imei']}\n".encode("utf-8")

        raw += f"Est. Amt: Rs. {data['charged']:.2f}\n--------------------------------\n\x1b\x61\x01"
        raw += b"Bring token for device pickup\n*** Thank You ***\n\n\n\n\x1d\x56\x41\x10"
        send_escpos_raw(bytes(raw))
        return True, "Printed"
    except Exception as e:
        return False, str(e)


def print_eod_report(today_str, total_jobs, total_cost, total_charged, total_profit):
    try:
        raw = bytearray()
        raw += b"\x1b\x40\x1b\x61\x01\x1d\x21\x11\x1b\x45\x01"
        raw += b"DAILY CLOSING REPORT\n\x1d\x21\x00\x1b\x45\x00"
        raw += f"Date: {today_str}\n--------------------------------\n\x1b\x61\x00".encode("utf-8")
        raw += f"Total Jobs Done:  {total_jobs}\n".encode("utf-8")
        raw += f"Total Cost:       Rs. {total_cost:.2f}\n".encode("utf-8")
        raw += f"Total Revenue:    Rs. {total_charged:.2f}\n--------------------------------\n\x1b\x45\x01".encode(
            "utf-8")
        raw += f"NET PROFIT:       Rs. {total_profit:.2f}\n\x1b\x45\x00--------------------------------\n\n\n\n\x1d\x56\x41\x10".encode(
            "utf-8")
        send_escpos_raw(bytes(raw))
        return True
    except Exception as e:
        print(f"EOD Print Error: {e}")
        return False


# ================= START / MENU =================
@admin_only
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_text = (
        "🛠 *SAMEER MOBILE - Control Panel*\n\n"
        "Tap a button below to get started 👇"
    )
    await update.message.reply_markdown(welcome_text, reply_markup=MAIN_MENU_KEYBOARD)


async def handle_menu_shortcuts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text == "🔍 Check Status":
        await update.message.reply_text("Send: `/status [JobID]` (e.g., `/status 1001`)", parse_mode="Markdown")
    elif text == "🖨️ Reprint Token":
        await update.message.reply_text("Send: `/reprint [JobID]` (e.g., `/reprint 1001`)", parse_mode="Markdown")


# ================= NEW REPAIR FLOW =================
@admin_only
async def start_new_repair(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("📝 *New Repair*\n\n1️⃣ Enter *Customer Name*:", parse_mode="Markdown",
                                    reply_markup=ReplyKeyboardRemove())
    return NAME


async def get_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    await update.message.reply_text("2️⃣ Enter *Device Model*:", parse_mode="Markdown")
    return MODEL


async def get_model(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["model"] = update.message.text.strip()
    await update.message.reply_text("3️⃣ Describe the *Fault / Issue*:", parse_mode="Markdown")
    return FAULT


async def get_fault(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["fault"] = update.message.text.strip()
    reply_keyboard = [["Today"]]
    await update.message.reply_text(
        "4️⃣ Enter *Date* (YYYY-MM-DD) or tap *Today*:",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return REPAIR_DATE


async def get_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["date"] = datetime.date.today().strftime("%Y-%m-%d") if inp.lower() == "today" else inp
    await update.message.reply_text("5️⃣ Enter *Part / Repair Cost* (₹):", reply_markup=ReplyKeyboardRemove(),
                                    parse_mode="Markdown")
    return COST_PRICE


async def get_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["cost"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number for cost:")
        return COST_PRICE
    await update.message.reply_text("6️⃣ Enter *Price Charged to Customer* (₹):", parse_mode="Markdown")
    return CHARGED_PRICE


async def get_charged(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["charged"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number for price charged:")
        return CHARGED_PRICE

    reply_keyboard = [["No Lock / Skip"]]
    await update.message.reply_text(
        "7️⃣ Enter *PIN / Pattern Lock*:\n"
        "*(For Pattern, enter dot numbers 1-9, e.g., `12359` or tap No Lock)*",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return LOCK_CODE


async def get_lock_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["lock_code"] = "None" if "no lock" in inp.lower() or "skip" in inp.lower() else inp

    reply_keyboard = [["Skip IMEI"]]
    await update.message.reply_text(
        "8️⃣ Enter *IMEI* (or tap Skip):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return IMEI


async def get_imei(update: Update, context: ContextTypes.DEFAULT_TYPE):
    inp = update.message.text.strip()
    context.user_data["imei"] = "N/A" if inp.lower() == "skip imei" else inp
    reply_keyboard = [["Skip Image"]]
    await update.message.reply_text(
        "9️⃣ Send *Condition Photo* (or tap Skip):",
        reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return PHOTO


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    photo_file = await update.message.photo[-1].get_file()
    fname = f"{context.user_data.get('model', 'device')}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg".replace(
        " ", "_")
    fpath = os.path.join(IMAGE_DIR, fname)
    await photo_file.download_to_drive(fpath)
    context.user_data["image_status"] = fname
    return await save_repair_entry(update, context)


async def skip_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["image_status"] = "No Image"
    return await save_repair_entry(update, context)


async def save_repair_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = context.user_data
    payload = {
        "action": "add_repair",
        "date": data["date"],
        "name": data["name"],
        "model": data["model"],
        "fault": data["fault"],
        "cost": data["cost"],
        "charged": data["charged"],
        "lock_code": data.get("lock_code", "None"),
        "imei": data.get("imei", "N/A"),
        "image": data.get("image_status", "No Image"),
    }
    res = call_sheet(payload)

    if res.get("status") == "success":
        job_id = res["job_id"]
        printed, p_stat = print_repair_token(data, job_id)
        p_badge = "🖨️ *Token Printed!*" if printed else f"⚠️ *Print Error:* `{p_stat}`"

        summary = (
            f"✅ *Repair Saved to Google Sheet!*\n\n"
            f"🏷 *Token:* `#{job_id}`\n"
            f"👤 *Customer:* {data['name']}\n"
            f"📱 *Model:* {data['model']}\n"
            f"🔧 *Fault:* {data['fault']}\n"
            f"🔐 *Lock / PIN:* `{data.get('lock_code', 'None')}`\n"
            f"💰 *Charged:* ₹{data['charged']:.2f}\n"
            f"{p_badge}"
        )
    else:
        summary = f"⚠️ *Error saving to sheet:* {res.get('message', 'Unknown error')}"

    await update.message.reply_markdown(summary, reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END


# ================= REPRINT & STATUS =================
@admin_only
async def reprint_token(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/reprint 1001`", parse_mode="Markdown")
        return
    job_id = context.args[0].strip()
    res = call_sheet({"action": "find_job", "job_id": job_id})
    if res.get("status") != "success":
        await update.message.reply_text(f"❌ Job `#{job_id}` not found.")
        return
    printed, stat = print_repair_token(res, job_id)
    await update.message.reply_text(f"🖨️ Reprint #{job_id}: {stat}", reply_markup=MAIN_MENU_KEYBOARD)


@admin_only
async def check_or_update_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: `/status 1001`", parse_mode="Markdown")
        return
    job_id = context.args[0].strip()
    res = call_sheet({"action": "find_job", "job_id": job_id})
    if res.get("status") != "success":
        await update.message.reply_text(f"❌ Job `#{job_id}` not found.")
        return
    row_num = res["row_index"]
    keyboard = [
        [
            InlineKeyboardButton("⏳ In Progress", callback_data=f"st_{job_id}_{row_num}_In Progress"),
            InlineKeyboardButton("✅ Completed", callback_data=f"st_{job_id}_{row_num}_Completed"),
        ],
        [
            InlineKeyboardButton("📦 Delivered", callback_data=f"st_{job_id}_{row_num}_Delivered"),
            InlineKeyboardButton("❌ Returned", callback_data=f"st_{job_id}_{row_num}_Returned"),
        ],
    ]
    await update.message.reply_markdown(
        f"📱 *Job #{job_id}* ({res['model']})\n🔐 Lock: `{res.get('lock_code', 'None')}`\nStatus: `{res['job_status']}`\nSelect new status:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def handle_status_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, job_id, row_num, new_status = query.data.split("_", 3)
    call_sheet({"action": "update_cell", "row_index": int(row_num), "col_index": 11, "value": new_status})
    await query.edit_message_text(f"✅ Job `#{job_id}` updated to *{new_status}*.", parse_mode="Markdown")


# ================= SEQUENTIAL EOD PROFIT FLOW =================
@admin_only
async def start_eod_flow(update: Update, context: ContextTypes.DEFAULT_TYPE):
    target = update.callback_query.message if update.callback_query else update.message
    if update.callback_query:
        await update.callback_query.answer()

    today_str = datetime.date.today().strftime("%Y-%m-%d")
    res = call_sheet({"action": "get_today_jobs", "date": today_str})
    today_jobs = res.get("jobs", [])

    if not today_jobs:
        await target.reply_text(f"ℹ️ No repair jobs found for today (`{today_str}`).", reply_markup=MAIN_MENU_KEYBOARD)
        return ConversationHandler.END

    context.user_data["eod_jobs"] = today_jobs
    context.user_data["current_index"] = 0
    context.user_data["entered_profits"] = []
    context.user_data["date"] = today_str

    await target.reply_text(f"📋 *Starting EOD Review for {today_str}* ({len(today_jobs)} jobs):", parse_mode="Markdown")
    return await prompt_next_job(update, context)


async def prompt_next_job(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.user_data["eod_jobs"]
    idx = context.user_data["current_index"]
    j = jobs[idx]

    reply_keyboard = [[f"Keep ₹{j['auto_profit']:.0f}"]]
    text = (
        f"📱 *Job {idx + 1}/{len(jobs)}* — `Token #{j['job_id']}`\n"
        f"👤 {j['customer']} | 📱 {j['model']} ({j['fault']})\n"
        f"💸 Cost: ₹{j['cost']:.0f} | Charged: ₹{j['charged']:.0f}\n"
        f"📊 Est. Profit: ₹{j['auto_profit']:.0f}\n\n"
        f"👉 Enter actual profit (or tap button):"
    )
    target = update.callback_query.message if update.callback_query else update.message
    await target.reply_text(text, reply_markup=ReplyKeyboardMarkup(reply_keyboard, one_time_keyboard=True,
                                                                   resize_keyboard=True), parse_mode="Markdown")
    return EOD_PROFIT_INPUT


async def handle_profit_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    jobs = context.user_data["eod_jobs"]
    idx = context.user_data["current_index"]
    j = jobs[idx]
    inp = update.message.text.strip()

    val = j["auto_profit"] if "Keep" in inp else float(inp)
    j["final_profit"] = val
    context.user_data["entered_profits"].append(j)

    # Column 12 in the new sheet structure corresponds to Profit
    call_sheet({"action": "update_cell", "row_index": j["row_index"], "col_index": 12, "value": val})
    context.user_data["current_index"] += 1

    if context.user_data["current_index"] < len(jobs):
        return await prompt_next_job(update, context)

    records = context.user_data["entered_profits"]
    d_str = context.user_data["date"]
    tot_cost = sum(x["cost"] for x in records)
    tot_charged = sum(x["charged"] for x in records)
    tot_profit = sum(x["final_profit"] for x in records)

    print_eod_report(d_str, len(records), tot_cost, tot_charged, tot_profit)

    summary_lines = "\n".join([f"• `#{x['job_id']}` {x['model']} ➔ ₹{x['final_profit']:,.2f}" for x in records])
    res = (
        f"🏁 *EOD Completed ({d_str})*\n\n"
        f"{summary_lines}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📱 *Jobs:* {len(records)} | 💰 *Revenue:* ₹{tot_charged:,.2f}\n"
        f"📈 *Total Net Profit:* ₹{tot_profit:,.2f}\n"
        f"🖨️ *Receipt Printed to Bench!*"
    )
    await update.message.reply_markdown(res, reply_markup=MAIN_MENU_KEYBOARD)
    context.user_data.clear()
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


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END


# ================= SET BOT COMMANDS =================
async def post_init(application):
    commands = [
        BotCommand("start", "Open Main Menu"),
        BotCommand("newrepair", "Log a new repair job"),
        BotCommand("eod", "Start End of Day review"),
        BotCommand("status", "Check/Update job status"),
        BotCommand("reprint", "Reprint thermal receipt"),
    ]
    await application.bot.set_my_commands(commands)


# ================= MAIN =================
def main():
    app = ApplicationBuilder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))

    # Repair Entry Conversation
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

    # EOD Review Conversation
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

    app.add_handler(CommandHandler("reprint", reprint_token))
    app.add_handler(CommandHandler("status", check_or_update_status))
    app.add_handler(CallbackQueryHandler(handle_status_callback, pattern="^st_"))
    app.add_handler(MessageHandler(filters.Regex("^(🔍 Check Status|🖨️ Reprint Token)$"), handle_menu_shortcuts))

    if app.job_queue:
        app.job_queue.run_daily(send_9pm_reminder, time=datetime.time(hour=21, minute=0, second=0, tzinfo=TIMEZONE))
        print("⏰ 9:00 PM EOD reminder scheduled.")

    print("🚀 Shop Automation Bot is LIVE.")
    app.run_polling()


if __name__ == "__main__":
    main()