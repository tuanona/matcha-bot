import asyncio
import logging
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
TOKEN = ""
ADMIN_IDS = frozenset([])
USER_IDS = frozenset([])

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

# Views (menggantikan 'states' untuk merepresentasikan apa yang dilihat pengguna)
VIEW_WELCOME = "welcome"
VIEW_GETTING_NAME = "getting_name"
VIEW_MENU = "menu"
VIEW_ITEM_DETAIL = "item_detail"
VIEW_CHECKOUT = "checkout"
VIEW_WAITING_CASH = "waiting_cash"
VIEW_QRIS = "qris"
VIEW_POST_TRANSACTION = "post_transaction"
VIEW_ADMIN_PANEL = "admin_panel"
VIEW_ADMIN_REKAP = "admin_rekap"

# =======================
# STATE MANAGEMENT (PENDEKATAN FUNGSIONAL)
# =======================
# Data global terpusat. Setiap key adalah user_id.
# Value adalah dictionary yang berisi state lengkap pengguna tersebut.
bot_state = defaultdict(lambda: {
    "customer_name": None,
    "cart": {},
    "current_view": VIEW_WELCOME,
    "total": 0,
})

# Data penjualan harian
SALES = []

# =======================
# FUNGSI LOGIKA MURNI (PURE LOGIC FUNCTIONS)
# =======================
def is_authorized(uid: int) -> bool:
    """Check if user is authorized (admin or cashier)."""
    return uid in ADMIN_IDS or uid in USER_IDS

def is_admin(uid: int) -> bool:
    """Check if user is an admin."""
    return uid in ADMIN_IDS

def format_currency(amount: int) -> str:
    """Format currency with thousands separator."""
    return f"Rp{amount:,}"

def clean_numeric_input(text: str) -> Optional[int]:
    """Clean and parse numeric input."""
    try:
        clean_text = text.replace(".", "").replace(",", "").replace(" ", "").lower().replace("rp", "")
        return int(clean_text) if clean_text.isdigit() and len(clean_text) < 10 else None
    except (ValueError, AttributeError):
        return None

def calculate_cart_total(cart: Dict[str, int]) -> int:
    """Calculate total price of items in a cart."""
    return sum(MENU.get(item, 0) * qty for item, qty in cart.items())

def update_cart(cart: Dict[str, int], item: str, action: str) -> Dict[str, int]:
    """
    Pure function to update cart. Returns a *new* cart object.
    """
    new_cart = cart.copy()
    current_qty = new_cart.get(item, 0)

    if action == "inc":
        new_cart[item] = current_qty + 1
    elif action == "dec" and current_qty > 0:
        new_cart[item] = current_qty - 1
        if new_cart[item] == 0:
            del new_cart[item]
            
    return new_cart

def generate_cart_summary_text(cart: Dict[str, int]) -> str:
    """Generate formatted text for items in cart."""
    if not cart:
        return "Keranjang kosong."
    return "\n".join([
        f"• {item} x{qty} = {format_currency(MENU.get(item, 0) * qty)}"
        for item, qty in cart.items()
    ])

# =======================
# KEYBOARD BUILDERS (UI COMPONENTS)
# =======================
def build_welcome_keyboard(uid: int) -> InlineKeyboardMarkup:
    """Builds the main welcome screen keyboard."""
    buttons = [[InlineKeyboardButton("✅ Mulai Sesi Transaksi", callback_data="start_transaction")]]
    if is_admin(uid):
        buttons.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def build_menu_keyboard(uid: int) -> InlineKeyboardMarkup:
    """Builds the main product menu keyboard."""
    menu_items = list(MENU.keys())
    buttons = [
        [
            InlineKeyboardButton(menu_items[i], callback_data=f"item_{menu_items[i]}"),
            InlineKeyboardButton(menu_items[i + 1], callback_data=f"item_{menu_items[i + 1]}"),
        ]
        for i in range(0, len(menu_items), 2)
    ]
    buttons.append([InlineKeyboardButton("🛒 Checkout", callback_data="checkout")])
    if is_admin(uid):
        buttons.append([InlineKeyboardButton("🔧 Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(buttons)

def build_item_keyboard(item: str) -> InlineKeyboardMarkup:
    """Builds keyboard for adjusting item quantity."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data=f"dec_{item}"),
            InlineKeyboardButton("➕", callback_data=f"inc_{item}"),
        ],
        [InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_menu")]
    ])

def build_payment_keyboard() -> InlineKeyboardMarkup:
    """Builds payment method selection keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("💵 Cash", callback_data="pay_cash"),
            InlineKeyboardButton("📱 QRIS", callback_data="pay_qris"),
        ],
        [InlineKeyboardButton("⬅️ Kembali ke Menu", callback_data="back_to_menu")]
    ])
    
def build_qris_keyboard() -> InlineKeyboardMarkup:
    """Builds keyboard for QRIS payment confirmation."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Pembayaran Selesai", callback_data="qris_done")],
        [InlineKeyboardButton("❌ Batal", callback_data="back_to_checkout")]
    ])

def build_admin_keyboard() -> InlineKeyboardMarkup:
    """Builds admin panel keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📊 Rekap Penjualan", callback_data="adm_rekap")],
        [InlineKeyboardButton("🗑️ Reset Data Harian", callback_data="adm_reset")],
        [InlineKeyboardButton("🔙 Halaman Utama", callback_data="end_session")]
    ])

def build_post_transaction_keyboard() -> InlineKeyboardMarkup:
    """Builds keyboard for actions after a successful transaction."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Pelanggan Baru", callback_data="new_customer")],
        [InlineKeyboardButton("➕ Tambah Item (Pelanggan Sama)", callback_data="continue_same_customer")],
        [InlineKeyboardButton("🚪 Selesai Sesi (Tutup Toko)", callback_data="end_session")]
    ])

# =======================
# RENDER FUNCTIONS (UI UPDATERS / ACTIONS)
# =======================
async def render_view(update: Update, context: ContextTypes.DEFAULT_TYPE, new_text: str, new_keyboard: Optional[InlineKeyboardMarkup] = None):
    """Generic function to render a view by editing or sending a message."""
    query = update.callback_query
    try:
        if query:
            await query.edit_message_text(text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
        elif update.message:
            await update.message.reply_text(text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            logger.debug("Message not modified, skipping edit.")
            if query: await query.answer() # Acknowledge the callback
        else:
            logger.error(f"Error rendering view: {e}")
            if query: await query.answer("❌ Terjadi kesalahan saat menampilkan menu.", show_alert=True)
    except Exception as e:
        logger.error(f"Unexpected error in render_view: {e}")
        if query: await query.answer("❌ Terjadi kesalahan fatal.", show_alert=True)


async def show_welcome_screen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the initial welcome screen."""
    uid = update.effective_user.id
    bot_state[uid]['current_view'] = VIEW_WELCOME
    text = "🍵 *Selamat Datang di Matcha Kasir Bot!*\n\nSilakan mulai sesi untuk mencatat transaksi."
    await render_view(update, context, text, build_welcome_keyboard(uid))

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Displays the main product menu."""
    uid = update.effective_user.id
    state = bot_state[uid]
    state['current_view'] = VIEW_MENU
    
    cart_summary = generate_cart_summary_text(state['cart'])
    total_text = format_currency(calculate_cart_total(state['cart']))
    
    text = (
        f"👤 *Pelanggan: {state['customer_name']}*\n\n"
        f"🛒 *Keranjang Saat Ini:*\n{cart_summary}\n\n"
        f"💰 *Total Sementara: {total_text}*\n\n"
        "Silakan pilih item:"
    )
    await render_view(update, context, text, build_menu_keyboard(uid))

# =======================
# COMMAND HANDLERS
# =======================
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles /start command, showing the main gateway."""
    uid = update.effective_user.id
    if not is_authorized(uid):
        await update.message.reply_text("🚫 *Akses Ditolak*. Anda tidak terdaftar.", parse_mode="Markdown")
        return
    
    # Reset session and show welcome screen
    reset_user_session(uid, full_reset=True)
    await show_welcome_screen(update, context)

# =======================
# MESSAGE HANDLER
# =======================
async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles text inputs based on the user's current view."""
    uid = update.effective_user.id
    if not is_authorized(uid): return

    state = bot_state[uid]
    view = state['current_view']
    text = update.message.text.strip()

    if view == VIEW_GETTING_NAME:
        if not text or len(text) < 2 or len(text) > 50:
            await update.message.reply_text("❌ Nama tidak valid (min 2, maks 50 karakter). Coba lagi:")
            return
        state['customer_name'] = text
        await show_main_menu(update, context)

    elif view == VIEW_WAITING_CASH:
        total = state.get('total', 0)
        cash_amount = clean_numeric_input(text)
        
        if cash_amount is None:
            await update.message.reply_text(f"❌ Format tidak valid. Masukkan angka saja.\nTotal: {format_currency(total)}")
            return
        
        if cash_amount < total:
            await update.message.reply_text(f"💰 Uang kurang. Dibutuhkan {format_currency(total - cash_amount)} lagi.")
            return
            
        await process_and_show_receipt(update, context, "Cash", cash_amount)

    else:
        await update.message.reply_text("ℹ️ Silakan gunakan tombol yang tersedia atau /start untuk memulai ulang.")

# =======================
# CALLBACK QUERY HANDLER (Main Router)
# =======================
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Main router for all inline button clicks."""
    query = update.callback_query
    await query.answer() # Acknowledge callback immediately
    
    uid = query.from_user.id
    if not is_authorized(uid):
        await query.answer("🚫 Akses Ditolak!", show_alert=True)
        return

    data = query.data
    state = bot_state[uid]

    # --- Navigation & Session Control ---
    if data == "start_transaction":
        reset_user_session(uid, full_reset=False) # Keep user logged in, clear cart/name
        state['current_view'] = VIEW_GETTING_NAME
        await render_view(update, context, "👤 Silakan masukkan *nama pelanggan*:")
    
    elif data == "end_session":
        reset_user_session(uid, full_reset=True)
        await show_welcome_screen(update, context)
        
    elif data == "new_customer":
        reset_user_session(uid, full_reset=False)
        state['current_view'] = VIEW_GETTING_NAME
        await render_view(update, context, "👤 Silakan masukkan *nama pelanggan berikutnya*:")

    elif data == "continue_same_customer":
        await show_main_menu(update, context)

    elif data == "back_to_menu":
        await show_main_menu(update, context)
        
    # --- Item & Cart Management ---
    elif data.startswith("item_"):
        item = data.split("_", 1)[1]
        state['current_view'] = VIEW_ITEM_DETAIL
        price = MENU.get(item, 0)
        qty = state['cart'].get(item, 0)
        text = (
            f"🛍️ *{item}*\n\n"
            f"💰 Harga: {format_currency(price)}\n"
            f"🔢 Jumlah: {qty}\n"
            f"💵 Subtotal: {format_currency(price * qty)}"
        )
        await render_view(update, context, text, build_item_keyboard(item))

    elif data.startswith(("inc_", "dec_")):
        action, item = data.split("_", 1)
        state['cart'] = update_cart(state['cart'], item, action)
        # Re-render the item detail view with updated info
        price = MENU.get(item, 0)
        qty = state['cart'].get(item, 0)
        text = (
            f"🛍️ *{item}*\n\n"
            f"💰 Harga: {format_currency(price)}\n"
            f"🔢 Jumlah: {qty}\n"
            f"💵 Subtotal: {format_currency(price * qty)}"
        )
        await render_view(update, context, text, build_item_keyboard(item))

    # --- Checkout & Payment ---
    elif data == "checkout":
        if not state['cart']:
            await query.answer("🛒 Keranjang kosong!", show_alert=True)
            return
        state['total'] = calculate_cart_total(state['cart'])
        state['current_view'] = VIEW_CHECKOUT
        cart_summary = generate_cart_summary_text(state['cart'])
        text = (
            f"🧾 *Ringkasan Pesanan*\n\n"
            f"👤 Pelanggan: {state['customer_name']}\n\n"
            f"🛍️ *Items:*\n{cart_summary}\n\n"
            f"💰 *Total: {format_currency(state['total'])}*\n\n"
            f"Pilih metode pembayaran:"
        )
        await render_view(update, context, text, build_payment_keyboard())

    elif data == "back_to_checkout": # from QRIS cancellation
        # Re-trigger checkout logic to show the summary again
        await handle_callback_query(Update(update.update_id, callback_query=query.from_data({"data": "checkout"})), context)
        
    elif data == "pay_cash":
        state['current_view'] = VIEW_WAITING_CASH
        text = (
            f"💵 *Pembayaran Tunai*\n\n"
            f"💰 Total: {format_currency(state['total'])}\n\n"
            "Ketik nominal uang yang diterima:"
        )
        await render_view(update, context, text)

    elif data == "pay_qris":
        state['current_view'] = VIEW_QRIS
        text = (
            f"📱 *Pembayaran QRIS*\n\n"
            f"💰 Total: {format_currency(state['total'])}\n\n"
            "🔲 Silakan scan QRIS dan konfirmasi pembayaran."
        )
        await render_view(update, context, text, build_qris_keyboard())
        
    elif data == "qris_done":
        await process_and_show_receipt(update, context, "QRIS")

    # --- Admin Panel ---
    elif data == "admin_panel":
        if not is_admin(uid): return
        state['current_view'] = VIEW_ADMIN_PANEL
        await render_view(update, context, "🔧 *Panel Admin*", build_admin_keyboard())

    elif data == "adm_rekap":
        if not is_admin(uid): return
        state['current_view'] = VIEW_ADMIN_REKAP
        report_text = generate_sales_report()
        await render_view(update, context, report_text, InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="admin_panel")]]))

    elif data == "adm_reset":
        if not is_admin(uid): return
        SALES.clear()
        logger.info(f"Data reset by admin {uid}")
        await render_view(update, context, "🗑️ *Data Penjualan Harian Berhasil Direset*", InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Kembali", callback_data="admin_panel")]]))
        
# =======================
# CORE LOGIC HELPERS
# =======================
def reset_user_session(uid: int, full_reset: bool = False):
    """Resets user state. Full reset returns to welcome screen."""
    if full_reset:
        bot_state[uid] = {
            "customer_name": None, "cart": {}, 
            "current_view": VIEW_WELCOME, "total": 0
        }
    else: # Soft reset for new customer
        bot_state[uid]['customer_name'] = None
        bot_state[uid]['cart'] = {}
        bot_state[uid]['total'] = 0

def generate_sales_report() -> str:
    """Generates a summary of all transactions."""
    if not SALES:
        return "📊 *Rekap Penjualan*\n\nBelum ada transaksi hari ini."

    item_summary = defaultdict(int)
    total_revenue, cash_total, qris_total = 0, 0, 0
    
    for sale in SALES:
        total_revenue += sale["total"]
        if sale["payment_method"] == "Cash": cash_total += sale["total"]
        else: qris_total += sale["total"]
        for item, qty in sale["items"].items(): item_summary[item] += qty

    item_lines = [f"• {item} x{qty}" for item, qty in sorted(item_summary.items())]
    
    return (
        f"📊 *Rekap Penjualan Hari Ini*\n\n"
        f"*Penjualan Item:*\n" + "\n".join(item_lines) + "\n\n"
        f"📈 Total Transaksi: {len(SALES)}\n"
        f"💵 Cash: {format_currency(cash_total)}\n"
        f"📱 QRIS: {format_currency(qris_total)}\n"
        f"💰 *Total Omzet: {format_currency(total_revenue)}*"
    )

async def process_and_show_receipt(update: Update, context: ContextTypes.DEFAULT_TYPE, method: str, cash_received: int = 0):
    """Finalizes transaction, saves it, and displays the receipt."""
    uid = update.effective_user.id
    state = bot_state[uid]
    
    # Save transaction
    transaction = {
        "timestamp": datetime.now().isoformat(),
        "cashier_id": uid,
        "customer_name": state['customer_name'],
        "items": state['cart'],
        "total": state['total'],
        "payment_method": method
    }
    SALES.append(transaction)
    logger.info(f"Transaction saved: {state['customer_name']} - {format_currency(state['total'])}")

    # Generate receipt text
    cart_summary = generate_cart_summary_text(state['cart'])
    receipt = (
        f"🧾 *STRUK PEMBAYARAN*\n{'=' * 25}\n"
        f"👤 Pelanggan: {state['customer_name']}\n"
        f"📅 Waktu: {datetime.now().strftime('%d/%m/%y %H:%M')}\n"
        f"💳 Metode: {method}\n\n"
        f"🛍️ *Pesanan:*\n{cart_summary}\n\n"
        f"💰 *Total: {format_currency(state['total'])}*"
    )
    if method == "Cash":
        receipt += f"\n💵 Tunai: {format_currency(cash_received)}\n💸 Kembalian: {format_currency(cash_received - state['total'])}"
    receipt += f"\n\n✅ *LUNAS*\n{'=' * 25}"

    # Update view and show receipt
    state['current_view'] = VIEW_POST_TRANSACTION
    
    # Send receipt as a new message, then show post-transaction options
    if update.callback_query:
        # If it's a callback, we need to delete the old message and send two new ones.
        # A simpler way is to just edit the message to show the receipt first, then send the options.
        await render_view(update, context, receipt)
        await context.bot.send_message(chat_id=uid, text="Pilih langkah selanjutnya:", reply_markup=build_post_transaction_keyboard())
    else: # If from text input (cash)
        await update.message.reply_text(receipt, parse_mode="Markdown")
        await update.message.reply_text("Pilih langkah selanjutnya:", reply_markup=build_post_transaction_keyboard())

# =======================
# MAIN APPLICATION SETUP
# =======================
def main():
    """Starts the bot."""
    logger.info("🚀 Starting bot application...")
    app = ApplicationBuilder().token(TOKEN).build()

    # Add handlers
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))
    app.add_handler(CallbackQueryHandler(handle_callback_query))

    logger.info("🤖 Bot is polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
