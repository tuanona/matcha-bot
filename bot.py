import asyncio
import logging
import time
from datetime import datetime
from collections import defaultdict
from typing import Dict, Any, Optional

import httpx
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)
from telegram.error import TimedOut, NetworkError, BadRequest

# =======================
# LOGGING SETUP
# =======================
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =======================
# KONSTANTA & KONFIGURASI
# =======================
TOKEN = "TOKEN"

ADMIN_IDS = []
USER_IDS = []

# Data global (thread-safe untuk bot single instance)
SALES = []
carts = defaultdict(dict)
user_names = {}
user_states = {}

MENU = {
    "🍵 Matcha OG": 12000,
    "🍓 Strawberry Matcha": 16000,
    "🍪 Matcha Cookies": 16000,
    "🍫 Choco Matcha": 16000,
    "☁️ Matcha Cloud": 14000,
    "🍯 Honey Matcha": 15000,
    "🥥 Coconut Matcha": 15000,
    "🍊 Orange Matcha": 14000,
}

# State constants
STATE_WAITING_NAME = "waiting_name"
STATE_MENU = "menu"
STATE_SELECTING_PAYMENT = "selecting_payment"
STATE_WAITING_CASH = "waiting_cash"

# =======================
# UTILITY FUNCTIONS
# =======================
def is_authorized(uid: int) -> bool:
    """Check if user is authorized to use bot."""
    return uid in ADMIN_IDS or uid in USER_IDS

def is_admin(uid: int) -> bool:
    """Check if user is admin."""
    return uid in ADMIN_IDS

def format_currency(amount: int) -> str:
    """Format currency with thousands separator."""
    return f"Rp{amount:,}"

def clean_numeric_input(text: str) -> Optional[int]:
    """Clean and parse numeric input from user."""
    try:
        clean_text = text.replace(".", "").replace(",", "").replace(" ", "").replace("Rp", "")
        if clean_text.isdigit() and len(clean_text) <= 10:  # Prevent overflow
            return int(clean_text)
    except (ValueError, AttributeError):
        pass
    return None

def get_cart_total(cart: Dict[str, int]) -> int:
    """Calculate total price of items in cart."""
    return sum(MENU[item] * qty for item, qty in cart.items() if item in MENU)

# =======================
# KEYBOARD BUILDERS
# =======================
def build_main_menu_keyboard(uid: int) -> InlineKeyboardMarkup:
    """Build main menu keyboard with error handling."""
    try:
        menu_items = list(MENU.keys())
        buttons = []
        
        # Create grid layout (2 columns)
        for i in range(0, len(menu_items), 2):
            row = [InlineKeyboardButton(menu_items[i], callback_data=f"item_{menu_items[i]}")]
            if i + 1 < len(menu_items):
                row.append(InlineKeyboardButton(menu_items[i + 1], callback_data=f"item_{menu_items[i + 1]}"))
            buttons.append(row)

        # Action buttons
        buttons.append([InlineKeyboardButton("🛒 Checkout", callback_data="checkout")])
        
        if is_admin(uid):
            buttons.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin")])

        return InlineKeyboardMarkup(buttons)
    
    except Exception as e:
        logger.error(f"Error creating main menu keyboard: {e}")
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Restart", callback_data="restart")]])

def build_item_keyboard(item: str) -> InlineKeyboardMarkup:
    """Build item detail keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"dec_{item}"),
            InlineKeyboardButton("➕", callback_data=f"inc_{item}"),
        ],
        [
            InlineKeyboardButton("✅ Selesai", callback_data="back_to_menu"),
            InlineKeyboardButton("🏠 Menu Utama", callback_data="back_to_menu"),
        ]
    ])

def build_payment_keyboard() -> InlineKeyboardMarkup:
    """Build payment method selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Cash", callback_data="pay_cash"),
            InlineKeyboardButton("📱 QRIS", callback_data="pay_qris"),
        ],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_menu")]
    ])

def build_admin_keyboard() -> InlineKeyboardMarkup:
    """Build admin panel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Rekap Penjualan", callback_data="adm_rekap")],
        [InlineKeyboardButton("🗑️ Reset Data", callback_data="adm_reset")],
        [InlineKeyboardButton("🔙 Menu Kasir", callback_data="back_to_menu")]
    ])

def build_qris_keyboard() -> InlineKeyboardMarkup:
    """Build QRIS payment keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Pembayaran Selesai", callback_data="qris_done")],
        [InlineKeyboardButton("❌ Batal", callback_data="back_to_payment")]
    ])

def build_new_customer_keyboard() -> InlineKeyboardMarkup:
    """Build new customer keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Pembeli Baru", callback_data="new_customer")],
        [InlineKeyboardButton("🔧 Admin Panel", callback_data="admin")]
    ])

# =======================
# COMMAND HANDLERS
# =======================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    try:
        uid = update.effective_user.id
        
        if not is_authorized(uid):
            await update.message.reply_text(
                "🚫 *Akses Ditolak*\n\nAnda tidak memiliki izin untuk menggunakan bot ini.",
                parse_mode="Markdown"
            )
            return

        # Reset user state
        user_states[uid] = STATE_WAITING_NAME
        carts[uid].clear()
        context.user_data.clear()

        welcome_text = (
            "🍵 *Selamat Datang di Matcha Kasir Bot!*\n\n"
            "Untuk memulai transaksi, silakan masukkan nama pembeli:"
        )
        
        await update.message.reply_text(welcome_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error in cmd_start: {e}")
        await safe_reply(update.message, "❌ Terjadi kesalahan. Silakan coba lagi.")

async def cmd_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /admin command."""
    try:
        uid = update.effective_user.id
        
        if not is_admin(uid):
            await update.message.reply_text("🚫 *Akses Ditolak*\nFitur ini khusus admin.", parse_mode="Markdown")
            return

        await update.message.reply_text(
            "🔧 *Panel Admin*\n\nPilih menu yang diinginkan:",
            reply_markup=build_admin_keyboard(),
            parse_mode="Markdown"
        )
        
    except Exception as e:
        logger.error(f"Error in cmd_admin: {e}")
        await safe_reply(update.message, "❌ Error mengakses admin panel.")

# =======================
# MESSAGE HANDLERS
# =======================
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input from users."""
    try:
        uid = update.effective_user.id
        text = update.message.text.strip()
        
        if not is_authorized(uid):
            return

        state = user_states.get(uid)

        # Handle customer name input
        if state == STATE_WAITING_NAME:
            await handle_customer_name_input(update, context, text)
        
        # Handle cash payment input
        elif state == STATE_WAITING_CASH:
            await handle_cash_payment_input(update, context, text)
        
        else:
            await update.message.reply_text(
                "ℹ️ Silakan gunakan menu yang tersedia atau ketik /start untuk memulai."
            )
            
    except Exception as e:
        logger.error(f"Error in handle_text_input: {e}")
        await safe_reply(update.message, "❌ Terjadi kesalahan. Ketik /start untuk memulai ulang.")

async def handle_customer_name_input(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str) -> None:
    """Handle customer name input."""
    uid = update.effective_user.id
    
    if not name or len(name.strip()) < 2:
        await update.message.reply_text(
            "❌ Nama pembeli harus minimal 2 karakter. Silakan masukkan nama yang valid:"
        )
        return

    if len(name) > 50:  # Prevent too long names
        await update.message.reply_text(
            "❌ Nama terlalu panjang (maksimal 50 karakter). Silakan masukkan nama yang lebih singkat:"
        )
        return

    user_names[uid] = name.strip()
    user_states[uid] = STATE_MENU

    welcome_message = (
        f"✅ *Pembeli: {name.strip()}*\n\n"
        "🏠 *Menu Utama*\n"
        "Silakan pilih item yang diinginkan:"
    )

    await update.message.reply_text(
        welcome_message,
        reply_markup=build_main_menu_keyboard(uid),
        parse_mode="Markdown"
    )

async def handle_cash_payment_input(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    """Handle cash payment amount input."""
    uid = update.effective_user.id
    
    total = context.user_data.get("total")
    if not total:
        await update.message.reply_text("❌ Error: Data transaksi hilang. Silakan mulai ulang dengan /start")
        return

    cash_amount = clean_numeric_input(text)
    
    if cash_amount is None:
        await update.message.reply_text(
            f"❌ Format tidak valid. Masukkan nominal dalam angka.\n"
            f"Contoh: 20000 atau 20.000\n\n"
            f"Total yang harus dibayar: {format_currency(total)}"
        )
        return

    if cash_amount < total:
        shortage = total - cash_amount
        await update.message.reply_text(
            f"💰 *Pembayaran Kurang*\n\n"
            f"Uang diterima: {format_currency(cash_amount)}\n"
            f"Total tagihan: {format_currency(total)}\n"
            f"Kekurangan: {format_currency(shortage)}\n\n"
            f"Silakan masukkan nominal yang cukup:",
            parse_mode="Markdown"
        )
        return

    # Process successful cash payment
    await process_cash_payment(update, context, cash_amount, total)

# =======================
# CALLBACK QUERY HANDLERS
# =======================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main callback query handler with error handling."""
    try:
        query = update.callback_query
        uid = query.from_user.id
        data = query.data

        if not is_authorized(uid):
            await query.answer("🚫 Akses ditolak!", show_alert=True)
            return

        # Route to specific handlers
        if data.startswith("item_"):
            await handle_item_selection(query, context)
        elif data.startswith("inc_") or data.startswith("dec_"):
            await handle_quantity_change(query, context)
        elif data.startswith("adm_"):
            await handle_admin_callbacks(query, context)
        elif data == "checkout":
            await handle_checkout(query, context)
        elif data.startswith("pay_"):
            await handle_payment_method(query, context)
        elif data == "qris_done":
            await handle_qris_completion(query, context)
        elif data.startswith("back_"):
            await handle_navigation(query, context)
        elif data == "new_customer":
            await handle_new_customer(query, context)
        elif data == "admin":
            await handle_admin_panel(query, context)
        elif data == "restart":
            await handle_restart(query, context)
        else:
            await query.answer("❌ Perintah tidak dikenali.", show_alert=True)

        await safe_answer_callback(query)

    except Exception as e:
        logger.error(f"Error in handle_callback_query: {e}")
        try:
            await query.answer("❌ Terjadi kesalahan. Silakan coba lagi.", show_alert=True)
        except:
            pass

async def handle_item_selection(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle item selection from menu."""
    uid = query.from_user.id
    item = query.data.split("_", 1)[1]
    
    if item not in MENU:
        await query.answer("❌ Item tidak tersedia!", show_alert=True)
        return

    # Initialize item in cart if not exists
    if uid not in carts:
        carts[uid] = {}
    carts[uid].setdefault(item, 0)

    price = MENU[item]
    qty = carts[uid][item]
    subtotal = price * qty

    item_text = (
        f"🛍️ *{item}*\n\n"
        f"💰 Harga: {format_currency(price)}\n"
        f"🔢 Jumlah: {qty}\n"
        f"💵 Subtotal: {format_currency(subtotal)}"
    )

    await safe_edit_message(query, item_text, build_item_keyboard(item))

async def handle_quantity_change(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle quantity increase/decrease with change detection."""
    uid = query.from_user.id
    action, item = query.data.split("_", 1)
    
    if item not in MENU:
        await query.answer("❌ Item tidak tersedia!", show_alert=True)
        return

    # Get current quantity
    old_qty = carts[uid].get(item, 0)
    new_qty = old_qty

    # Calculate new quantity
    if action == "inc":
        new_qty += 1
    elif action == "dec" and old_qty > 0:
        new_qty -= 1

    # Only update if quantity changed
    if new_qty != old_qty:
        if new_qty > 0:
            carts[uid][item] = new_qty
        else:
            carts[uid].pop(item, None)

        price = MENU[item]
        subtotal = price * new_qty

        item_text = (
            f"🛍️ *{item}*\n\n"
            f"💰 Harga: {format_currency(price)}\n"
            f"🔢 Jumlah: {new_qty}\n"
            f"💵 Subtotal: {format_currency(subtotal)}"
        )

        await safe_edit_message(query, item_text, build_item_keyboard(item))
    else:
        # No change, just answer callback to stop loading
        await query.answer()

async def handle_checkout(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle checkout process."""
    uid = query.from_user.id
    cart = carts.get(uid, {})
    
    if not cart:
        await query.answer("🛒 Keranjang belanja kosong!", show_alert=True)
        return

    total = get_cart_total(cart)
    customer_name = user_names.get(uid, "Tidak diketahui")
    
    # Format order summary
    order_lines = [
        f"• {item} x{qty} = {format_currency(MENU[item] * qty)}"
        for item, qty in cart.items()
        if item in MENU
    ]
    
    checkout_text = (
        f"🧾 *Ringkasan Pesanan*\n\n"
        f"👤 Pembeli: {customer_name}\n\n"
        f"🛍️ *Items:*\n" + "\n".join(order_lines) + "\n\n"
        f"💰 *Total: {format_currency(total)}*\n\n"
        f"Silakan pilih metode pembayaran:"
    )
    
    context.user_data["total"] = total
    user_states[uid] = STATE_SELECTING_PAYMENT
    
    await safe_edit_message(query, checkout_text, build_payment_keyboard())

async def handle_payment_method(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle payment method selection."""
    uid = query.from_user.id
    method = query.data.split("_")[1]
    
    total = context.user_data.get("total")
    if not total:
        await query.answer("❌ Error: Data transaksi hilang!", show_alert=True)
        return

    customer_name = user_names.get(uid, "Tidak diketahui")

    if method == "cash":
        user_states[uid] = STATE_WAITING_CASH
        cash_text = (
            f"💵 *Pembayaran Tunai*\n\n"
            f"👤 Pembeli: {customer_name}\n"
            f"💰 Total: {format_currency(total)}\n\n"
            f"Ketik nominal uang yang diterima:"
        )
        await safe_edit_message(query, cash_text)

    elif method == "qris":
        qris_text = (
            f"📱 *Pembayaran QRIS*\n\n"
            f"👤 Pembeli: {customer_name}\n"
            f"💰 Total: {format_currency(total)}\n\n"
            f"🔲 Silakan scan QRIS dan konfirmasi pembayaran"
        )
        await safe_edit_message(query, qris_text, build_qris_keyboard())

async def handle_qris_completion(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle QRIS payment completion."""
    uid = query.from_user.id
    
    total = context.user_data.get("total")
    if not total:
        await query.answer("❌ Error: Data transaksi hilang!", show_alert=True)
        return

    cart_items = carts[uid].copy()
    customer_name = user_names.get(uid, "Tidak diketahui")
    
    # Save transaction
    await save_transaction(uid, customer_name, cart_items, total, "QRIS")
    
    # Generate receipt
    receipt_text = generate_receipt(customer_name, cart_items, total, "QRIS")
    
    await safe_edit_message(query, receipt_text, build_new_customer_keyboard())

async def handle_navigation(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle navigation callbacks."""
    uid = query.from_user.id
    action = query.data
    
    if action == "back_to_menu":
        customer_name = user_names.get(uid, "")
        if customer_name:
            user_states[uid] = STATE_MENU
            menu_text = f"🏠 *Menu Utama*\n👤 Pembeli: {customer_name}"
            await safe_edit_message(query, menu_text, build_main_menu_keyboard(uid))
        else:
            await handle_restart(query, context)
    
    elif action == "back_to_payment":
        cart = carts.get(uid, {})
        total = context.user_data.get("total", 0)
        customer_name = user_names.get(uid, "Tidak diketahui")
        
        order_lines = [
            f"• {item} x{qty} = {format_currency(MENU[item] * qty)}"
            for item, qty in cart.items()
            if item in MENU
        ]
        
        checkout_text = (
            f"🧾 *Ringkasan Pesanan*\n\n"
            f"👤 Pembeli: {customer_name}\n\n"
            f"🛍️ *Items:*\n" + "\n".join(order_lines) + "\n\n"
            f"💰 *Total: {format_currency(total)}*\n\n"
            f"Silakan pilih metode pembayaran:"
        )
        
        user_states[uid] = STATE_SELECTING_PAYMENT
        await safe_edit_message(query, checkout_text, build_payment_keyboard())

async def handle_new_customer(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle new customer setup."""
    uid = query.from_user.id
    
    # Clear previous customer data
    user_names.pop(uid, None)
    carts[uid].clear()
    context.user_data.clear()
    user_states[uid] = STATE_WAITING_NAME
    
    await safe_edit_message(
        query,
        "👥 *Pembeli Baru*\n\nSilakan masukkan nama pembeli selanjutnya:"
    )

async def handle_admin_panel(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin panel access."""
    uid = query.from_user.id
    
    if not is_admin(uid):
        await query.answer("🚫 Akses ditolak! Admin only.", show_alert=True)
        return
    
    await safe_edit_message(
        query,
        "🔧 *Panel Admin*\n\nPilih menu yang diinginkan:",
        build_admin_keyboard()
    )

async def handle_restart(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle restart command."""
    uid = query.from_user.id
    
    # Clear user data
    user_names.pop(uid, None)
    carts[uid].clear()
    context.user_data.clear()
    user_states[uid] = STATE_WAITING_NAME
    
    await safe_edit_message(
        query,
        "🔄 *Bot Direstart*\n\nSilakan masukkan nama pembeli untuk memulai:"
    )

# =======================
# ADMIN HANDLERS
# =======================
async def handle_admin_callbacks(query, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle admin-specific callbacks."""
    uid = query.from_user.id
    
    if not is_admin(uid):
        await query.answer("🚫 Admin only!", show_alert=True)
        return
    
    action = query.data
    
    if action == "adm_rekap":
        await show_sales_report(query)
    elif action == "adm_reset":
        await reset_all_data(query)

async def show_sales_report(query) -> None:
    """Show sales report for admin."""
    if not SALES:
        report_text = "📊 *Rekap Penjualan*\n\nBelum ada transaksi hari ini."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="admin")]])
        await safe_edit_message(query, report_text, keyboard)
        return

    # Calculate summary
    item_summary = defaultdict(int)
    total_revenue = 0
    cash_total = 0
    qris_total = 0
    
    for sale in SALES:
        total_revenue += sale["total"]
        if sale["payment_method"] == "Cash":
            cash_total += sale["total"]
        else:
            qris_total += sale["total"]
        
        for item, qty in sale["items"].items():
            item_summary[item] += qty

    # Format report
    item_lines = [
        f"• {item} x{qty} = {format_currency(MENU[item] * qty)}"
        for item, qty in item_summary.items()
        if item in MENU
    ]
    
    # Recent transactions (last 5)
    recent_transactions = [
        f"• {sale['customer_name']} - {sale['payment_method']} - {format_currency(sale['total'])}"
        for sale in SALES[-5:]
    ]
    
    report_text = (
        f"📊 *Rekap Penjualan Hari Ini*\n\n"
        f"*Ringkasan Item:*\n" + "\n".join(item_lines) + "\n\n"
        f"📈 Total Transaksi: {len(SALES)}\n"
        f"💵 Cash: {format_currency(cash_total)}\n"
        f"📱 QRIS: {format_currency(qris_total)}\n"
        f"💰 *Total Revenue: {format_currency(total_revenue)}*\n\n"
        f"*5 Transaksi Terakhir:*\n" + "\n".join(recent_transactions)
    )
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="admin")]])
    await safe_edit_message(query, report_text, keyboard)

async def reset_all_data(query) -> None:
    """Reset all sales data (admin only)."""
    global SALES, carts, user_names, user_states
    
    SALES.clear()
    carts.clear()
    user_names.clear()
    user_states.clear()
    
    reset_text = (
        "🗑️ *Data Berhasil Direset*\n\n"
        "Semua data penjualan dan keranjang telah dihapus."
    )
    
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="admin")]])
    await safe_edit_message(query, reset_text, keyboard)

# =======================
# PAYMENT PROCESSING
# =======================
async def process_cash_payment(update: Update, context: ContextTypes.DEFAULT_TYPE, cash_amount: int, total: int) -> None:
    """Process cash payment completion."""
    uid = update.effective_user.id
    change = cash_amount - total
    
    cart_items = carts[uid].copy()
    customer_name = user_names.get(uid, "Tidak diketahui")
    
    # Save transaction
    await save_transaction(uid, customer_name, cart_items, total, "Cash")
    
    # Generate receipt with change info
    receipt_text = generate_receipt(customer_name, cart_items, total, "Cash", cash_amount, change)
    
    await update.message.reply_text(receipt_text, parse_mode="Markdown")
    await update.message.reply_text(
        "✅ Transaksi selesai! Silakan pilih:",
        reply_markup=build_new_customer_keyboard()
    )

async def save_transaction(uid: int, customer_name: str, items: Dict[str, int], total: int, method: str) -> None:
    """Save transaction to memory."""
    transaction = {
        "timestamp": datetime.now().isoformat(),
        "user_id": uid,
        "customer_name": customer_name,
        "items": items.copy(),
        "total": total,
        "payment_method": method
    }
    
    SALES.append(transaction)
    
    # Clear user cart and reset state
    carts[uid].clear()
    user_states[uid] = STATE_MENU
    
    logger.info(f"Transaction saved: {customer_name} - {method} - {format_currency(total)}")

def generate_receipt(customer_name: str, items: Dict[str, int], total: int, method: str, 
                    cash_amount: int = None, change: int = None) -> str:
    """Generate formatted receipt."""
    item_lines = [
        f"• {item} x{qty} = {format_currency(MENU[item] * qty)}"
        for item, qty in items.items()
        if item in MENU
    ]
    
    receipt = (
        f"🧾 *STRUK PEMBAYARAN*\n"
        f"{'=' * 25}\n\n"
        f"👤 Pembeli: {customer_name}\n"
        f"📅 Waktu: {datetime.now().strftime('%d/%m/%Y %H:%M')}\n"
        f"💳 Metode: {method}\n\n"
        f"🛍️ *Pesanan:*\n" + "\n".join(item_lines) + "\n\n"
        f"💰 *Total: {format_currency(total)}*"
    )
    
    if method == "Cash" and cash_amount is not None and change is not None:
        receipt += (
            f"\n💵 Tunai: {format_currency(cash_amount)}\n"
            f"💸 Kembalian: {format_currency(change)}"
        )
    
    receipt += f"\n\n✅ *LUNAS*\n{'=' * 25}"
    
    return receipt

# =======================
# UTILITY FUNCTIONS FOR ERROR HANDLING
# =======================
async def safe_reply(message, text: str, reply_markup=None, parse_mode: str = "Markdown") -> bool:
    """Safely send reply with error handling."""
    try:
        await message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        logger.error(f"BadRequest in safe_reply: {e}")
        try:
            # Fallback without parse_mode if markdown fails
            await message.reply_text(text, reply_markup=reply_markup)
            return True
        except Exception as fallback_error:
            logger.error(f"Fallback reply failed: {fallback_error}")
            return False
    except Exception as e:
        logger.error(f"Error in safe_reply: {e}")
        return False

async def safe_edit_message(query, text: str, reply_markup=None, parse_mode: str = "Markdown") -> bool:
    """Safely edit message with error handling."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        return True
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            # Message content is the same, just answer callback
            logger.debug("Message not modified, skipping edit")
            return True
        else:
            logger.error(f"BadRequest in safe_edit_message: {e}")
            try:
                # Fallback without parse_mode
                await query.edit_message_text(text, reply_markup=reply_markup)
                return True
            except Exception as fallback_error:
                logger.error(f"Fallback edit failed: {fallback_error}")
                return False
    except Exception as e:
        logger.error(f"Error in safe_edit_message: {e}")
        return False

async def safe_answer_callback(query, text: str = "", show_alert: bool = False) -> bool:
    """Safely answer callback query."""
    try:
        await query.answer(text, show_alert=show_alert)
        return True
    except Exception as e:
        logger.error(f"Error answering callback query: {e}")
        return False

# =======================
# APPLICATION SETUP
# =======================
def create_application():
    """Create and configure the application."""
    try:
        app = ApplicationBuilder().token(TOKEN).build()
        
        # Add handlers
        app.add_handler(CommandHandler("start", cmd_start))
        app.add_handler(CommandHandler("admin", cmd_admin))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        
        return app
    except Exception as e:
        logger.error(f"Failed to create application: {e}")
        return None

# =======================
# MAIN FUNCTION WITH RETRY LOGIC
# =======================
async def run_bot_with_retry():
    """Run bot with automatic retry on network errors."""
    max_retries = 5
    retry_delay = 15
    
    for attempt in range(max_retries):
        try:
            logger.info(f"🤖 Starting Matcha Kasir Bot... (Attempt {attempt + 1}/{max_retries})")
            
            app = create_application()
            if not app:
                logger.error("Failed to create application")
                return
            
            # Start polling
            await app.initialize()
            await app.start()
            await app.updater.start_polling(drop_pending_updates=True)
            
            logger.info("✅ Bot is running successfully!")
            
            # Keep running until interrupted
            while True:
                await asyncio.sleep(1)
                
        except (httpx.RemoteProtocolError, httpx.ConnectError, NetworkError, TimedOut) as e:
            logger.error(f"Network error occurred: {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"Retrying in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                continue
            else:
                logger.error("Max retries reached. Stopping bot.")
                break
                
        except KeyboardInterrupt:
            logger.info("Bot stopped by user (Ctrl+C)")
            break
            
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            
            if attempt < max_retries - 1:
                logger.info(f"Restarting in {retry_delay} seconds...")
                await asyncio.sleep(retry_delay)
                continue
            else:
                logger.error("Max retries reached due to unexpected errors.")
                break
        
        finally:
            # Cleanup
            if 'app' in locals():
                try:
                    await app.updater.stop()
                    await app.stop()
                    await app.shutdown()
                except Exception as cleanup_error:
                    logger.error(f"Error during cleanup: {cleanup_error}")

def main():
    """Main function to run the bot."""
    try:
        logger.info("🍵 Matcha Kasir Bot - Starting...")
        logger.info(f"Authorized Users: {len(USER_IDS)} kasir, {len(ADMIN_IDS)} admin")
        logger.info("Press Ctrl+C to stop the bot")
        
        # Run the async bot
        asyncio.run(run_bot_with_retry())
        
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error in main: {e}")
    finally:
        logger.info("🛑 Bot shutdown complete")

if __name__ == "__main__":
    main()
