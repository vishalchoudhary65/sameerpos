from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    ContextTypes,
    ConversationHandler,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from database import (
    db_get_categories,
    db_add_category,
    db_get_category_by_id,
    db_add_item,
    db_get_items_by_category,
    db_get_item_by_id,
    db_adjust_qty,
    db_update_item,
    db_delete_item,
    db_get_low_stock_for_alert,
)
from config import MAIN_MENU_KEYBOARD, ADMIN_CHAT_ID

# Conversation states for adding a category
ADD_CAT_NAME = 101

# Conversation states for adding an item
ITEM_NAME, ITEM_QTY, ITEM_COST, ITEM_SELL, ITEM_WARRANTY = range(102, 107)

# Conversation states for editing an item
EDIT_SELECT_FIELD, EDIT_NEW_VAL = range(107, 109)


# ================= CATEGORY MENUS =================
async def inventory_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Entry point when user taps '📦 Stock / Inventory'."""
    categories = db_get_categories()

    buttons = []
    if categories:
        for cat_id, cat_name in categories:
            buttons.append([InlineKeyboardButton(f"📁 {cat_name}", callback_data=f"cat_view_{cat_id}")])

    buttons.append([InlineKeyboardButton("➕ Add New Category", callback_data="cat_add_new")])
    reply_markup = InlineKeyboardMarkup(buttons)

    text = "📦 *Spare Parts & Inventory Categories*\n\nSelect a category or add a new one below:" if categories else "📦 *Inventory is empty.*\n\nNo categories found. Start by creating one:"

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_markdown(text, reply_markup=reply_markup)


# ================= ADD CATEGORY CONVERSATION =================
async def start_add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.message.reply_text("📁 Enter *Category Name* (e.g., Folder/Displays, Batteries, Charging CC):", parse_mode="Markdown")
    return ADD_CAT_NAME


async def save_category_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cat_name = update.message.text.strip()
    success, result = db_add_category(cat_name)

    if success:
        await update.message.reply_markdown(f"✅ Category *{cat_name}* created successfully!", reply_markup=MAIN_MENU_KEYBOARD)
    else:
        await update.message.reply_markdown(f"⚠️ {result}", reply_markup=MAIN_MENU_KEYBOARD)

    return ConversationHandler.END


# ================= CATEGORY SUBMENU (VIEW / ADD / EDIT / DELETE) =================
async def category_detail_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[2])
    cat = db_get_category_by_id(cat_id)

    if not cat:
        await query.message.reply_text("Category not found.")
        return

    cat_id, cat_name = cat
    context.user_data["current_cat_id"] = cat_id
    context.user_data["current_cat_name"] = cat_name

    buttons = [
        [InlineKeyboardButton("📋 View All Items", callback_data=f"item_list_{cat_id}")],
        [InlineKeyboardButton("➕ Add New Item", callback_data=f"item_add_{cat_id}")],
        [InlineKeyboardButton("⬅️ Back to Categories", callback_data="cat_back_main")],
    ]
    await query.message.edit_text(
        f"📁 *Category: {cat_name}*\n\nChoose an action:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(buttons),
    )


async def list_items_in_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[2])
    items = db_get_items_by_category(cat_id)
    cat = db_get_category_by_id(cat_id)
    cat_name = cat[1] if cat else ""

    if not items:
        buttons = [
            [InlineKeyboardButton("➕ Add First Item", callback_data=f"item_add_{cat_id}")],
            [InlineKeyboardButton("⬅️ Back", callback_data=f"cat_view_{cat_id}")],
        ]
        await query.message.edit_text(
            f"📁 *{cat_name}*\n\nNo items saved in this category yet.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(buttons),
        )
        return

    await query.message.reply_markdown(f"📦 *Items in {cat_name}:*")
    for item in items:
        item_id, name, qty, cost, sell, warranty = item
        status_icon = "🔴" if qty == 0 else ("🟡" if qty <= 2 else "🟢")

        text = (
            f"{status_icon} *{name}*\n"
            f"• Stock: *{qty} pcs*\n"
            f"• Purchase: ₹{cost:.0f} | Selling: ₹{sell:.0f}\n"
            f"• Warranty: `{warranty}`"
        )
        keyboard = [
            [
                InlineKeyboardButton("➕ 1", callback_data=f"qty_add_{item_id}_{cat_id}"),
                InlineKeyboardButton("➖ 1", callback_data=f"qty_sub_{item_id}_{cat_id}"),
                InlineKeyboardButton("✏️ Edit", callback_data=f"item_edit_{item_id}"),
                InlineKeyboardButton("🗑️ Del", callback_data=f"item_del_{item_id}_{cat_id}"),
            ]
        ]
        await query.message.reply_markdown(text, reply_markup=InlineKeyboardMarkup(keyboard))


# ================= QUICK QUANTITY ADJUSTMENT (+1 / -1) =================
async def handle_qty_change(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    _, action, item_id, cat_id = query.data.split("_")
    delta = 1 if action == "add" else -1

    row = db_adjust_qty(int(item_id), delta)
    if row:
        _, name, new_qty = row
        await query.answer(f"{name}: {new_qty} pcs left", show_alert=False)
        item = db_get_item_by_id(int(item_id))
        if item:
            item_id, _, name, qty, cost, sell, warranty = item
            status_icon = "🔴" if qty == 0 else ("🟡" if qty <= 2 else "🟢")
            text = (
                f"{status_icon} *{name}*\n"
                f"• Stock: *{qty} pcs*\n"
                f"• Purchase: ₹{cost:.0f} | Selling: ₹{sell:.0f}\n"
                f"• Warranty: `{warranty}`"
            )
            keyboard = [
                [
                    InlineKeyboardButton("➕ 1", callback_data=f"qty_add_{item_id}_{cat_id}"),
                    InlineKeyboardButton("➖ 1", callback_data=f"qty_sub_{item_id}_{cat_id}"),
                    InlineKeyboardButton("✏️ Edit", callback_data=f"item_edit_{item_id}"),
                    InlineKeyboardButton("🗑️ Del", callback_data=f"item_del_{item_id}_{cat_id}"),
                ]
            ]
            await query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))


# ================= DELETE ITEM =================
async def handle_item_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, _, item_id, cat_id = query.data.split("_")
    db_delete_item(int(item_id))
    await query.message.edit_text("🗑️ *Item removed from stock.*", parse_mode="Markdown")


# ================= ADD ITEM CONVERSATION =================
async def start_add_item(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    cat_id = int(query.data.split("_")[2])
    context.user_data["item_cat_id"] = cat_id

    await query.message.reply_text("1️⃣ Enter *Item Name* (e.g., Combo M12 Original):", parse_mode="Markdown")
    return ITEM_NAME


async def get_item_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["item_name"] = update.message.text.strip()
    await update.message.reply_text("2️⃣ Enter *Quantity in Stock*:", parse_mode="Markdown")
    return ITEM_QTY


async def get_item_qty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["item_qty"] = int(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid number for quantity:")
        return ITEM_QTY
    await update.message.reply_text("3️⃣ Enter *Purchase / Cost Price* (₹):", parse_mode="Markdown")
    return ITEM_COST


async def get_item_cost(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["item_cost"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid numeric cost price:")
        return ITEM_COST
    await update.message.reply_text("4️⃣ Enter *Selling Price* (₹):", parse_mode="Markdown")
    return ITEM_SELL


async def get_item_sell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        context.user_data["item_sell"] = float(update.message.text.strip())
    except ValueError:
        await update.message.reply_text("⚠️ Enter a valid numeric selling price:")
        return ITEM_SELL

    reply_kb = [["No Warranty / Testing Only"], ["30 Days", "3 Months", "6 Months"]]
    await update.message.reply_text(
        "5️⃣ Enter or tap *Warranty Period*:",
        reply_markup=ReplyKeyboardMarkup(reply_kb, one_time_keyboard=True, resize_keyboard=True),
        parse_mode="Markdown",
    )
    return ITEM_WARRANTY


async def get_item_warranty(update: Update, context: ContextTypes.DEFAULT_TYPE):
    warranty = update.message.text.strip()
    d = context.user_data
    cat_id = d["item_cat_id"]

    db_add_item(cat_id, d["item_name"], d["item_qty"], d["item_cost"], d["item_sell"], warranty)

    summary = (
        f"✅ *Item Added Successfully!*\n\n"
        f"📦 *Name:* {d['item_name']}\n"
        f"🔢 *Qty:* {d['item_qty']} pcs\n"
        f"💸 *Purchase:* ₹{d['item_cost']:.2f}\n"
        f"💰 *Selling:* ₹{d['item_sell']:.2f}\n"
        f"🛡️ *Warranty:* {warranty}"
    )
    await update.message.reply_markdown(summary, reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END


# ================= EDIT ITEM CONVERSATION =================
async def start_item_edit(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    item_id = int(query.data.split("_")[2])
    item = db_get_item_by_id(item_id)

    if not item:
        await query.message.reply_text("Item not found.")
        return ConversationHandler.END

    context.user_data["edit_item_id"] = item_id
    context.user_data["edit_item_cache"] = list(item)

    buttons = [
        [InlineKeyboardButton("Name", callback_data="edfield_2"), InlineKeyboardButton("Qty", callback_data="edfield_3")],
        [InlineKeyboardButton("Purchase Price", callback_data="edfield_4"), InlineKeyboardButton("Selling Price", callback_data="edfield_5")],
        [InlineKeyboardButton("Warranty", callback_data="edfield_6")],
    ]
    await query.message.reply_markdown(f"✏️ *Editing:* `{item[2]}`\nSelect field to change:", reply_markup=InlineKeyboardMarkup(buttons))
    return EDIT_SELECT_FIELD


async def select_edit_field(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    field_idx = int(query.data.split("_")[1])
    context.user_data["edit_field_idx"] = field_idx

    labels = {2: "Name", 3: "Stock Quantity", 4: "Purchase Price", 5: "Selling Price", 6: "Warranty"}
    await query.message.reply_text(f"Enter new value for *{labels[field_idx]}*:", parse_mode="Markdown")
    return EDIT_NEW_VAL


async def save_edit_val(update: Update, context: ContextTypes.DEFAULT_TYPE):
    new_val = update.message.text.strip()
    idx = context.user_data["edit_field_idx"]
    item = context.user_data["edit_item_cache"]

    try:
        if idx in (3,):
            item[idx] = int(new_val)
        elif idx in (4, 5):
            item[idx] = float(new_val)
        else:
            item[idx] = new_val
    except ValueError:
        await update.message.reply_text("⚠️ Invalid format. Cancelled.", reply_markup=MAIN_MENU_KEYBOARD)
        return ConversationHandler.END

    db_update_item(item[0], item[2], item[3], item[4], item[5], item[6])
    await update.message.reply_markdown(f"✅ *{item[2]}* updated successfully!", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END


# ================= 8:00 AM DAILY RESTOCK ENGINE =================
async def send_8am_restock_alert(context: ContextTypes.DEFAULT_TYPE):
    low_items = db_get_low_stock_for_alert(threshold=2)
    if not low_items:
        return

    lines = []
    for name, cat_name, qty in low_items:
        badge = "🔴 *OUT OF STOCK*" if qty == 0 else f"🟡 *{qty} left*"
        lines.append(f"• *{name}* ({cat_name}) ➔ {badge}")

    message = (
        "🔔 *8:00 AM Inventory Restock Alert*\n\n"
        "The following items need reordering from the market:\n\n"
        + "\n".join(lines)
        + "\n\n_Use the Stock menu to adjust quantities after purchasing._"
    )
    await context.bot.send_message(chat_id=ADMIN_CHAT_ID, text=message, parse_mode="Markdown")


async def cancel_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=MAIN_MENU_KEYBOARD)
    return ConversationHandler.END