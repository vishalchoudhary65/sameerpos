import os
from zoneinfo import ZoneInfo
from telegram import ReplyKeyboardMarkup

BOT_TOKEN = "8870922523:AAE_AwnI-AQJPwIS6woHI0r_D7yYm6HW6zQ"
ADMIN_CHAT_ID = 6960228144
PRINTER_IP = "192.168.1.100"
PRINTER_PORT = 9100
TIMEZONE = ZoneInfo("Asia/Kolkata")
IMAGE_DIR = "repair_images"
DB_FILE = "shop.db"

os.makedirs(IMAGE_DIR, exist_ok=True)

MAIN_MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        ["➕ New Repair", "🏁 End of Day"],
        ["📒 Udhar / Due", "💵 Receive Payment"],
        ["🔍 Customer Khata", "🖨️ Reprint Token"],
        ["📊 Check Status", "📦 Stock / Inventory"],
        ["📥 Export Backup"],
    ],
    resize_keyboard=True,
    is_persistent=True,
)