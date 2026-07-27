"""
Telegram Bot entry point for the Pixel 10 Pro Google One Gemini Bot.

Commands:
  /start        – Show welcome message and available commands
  /login        – Begin credential capture flow (email → password)
  /check_offer  – Run Google One automation and look for Gemini Pro offer
  /get_link     – Show the last captured offer link
  /status       – Show current session status and device profile
"""

import logging
import os
import sys

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

import config
from device_simulator import create_device_profile
from google_automation import (
    GoogleAutomationError,
    check_gemini_offer,
    setup_trusted_device,
)

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(level=config.LOG_LEVEL, format=config.LOG_FORMAT)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
AWAIT_EMAIL, AWAIT_PASSWORD, AWAIT_2FA = range(3)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_session(chat_id: int) -> dict:
    """Return (creating if absent) the session dict for *chat_id*."""
    if chat_id not in config.SESSION_STORE:
        config.SESSION_STORE[chat_id] = {}
    return config.SESSION_STORE[chat_id]


# ── Handlers ──────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send welcome message with command menu."""
    await update.message.reply_text(
        "🤖 <b>Pixel 10 Pro Google One Bot</b>\n\n"
        "This bot simulates a Google Pixel 10 Pro (Android 16) device, "
        "logs into your Google account, and retrieves the <b>12-month free "
        "Gemini Pro</b> offer link from Google One.\n\n"
        "📋 <b>Available Commands:</b>\n"
        "• /login – Enter your Gmail credentials\n"
        "• /setup – ⚠️ FIRST TIME: Trust this device with Google\n"
        "• /check_offer – Detect the Gemini Pro offer\n"
        "• /get_link – Show the last captured offer link\n"
        "• /status – View current session &amp; device info\n\n"
        "🔐 <b>First time setup:</b>\n"
        "1️⃣ /login – Enter email, password, 2FA secret\n"
        "2️⃣ /setup – A Chrome window will open on your PC.\n"
        "    Complete Google verification manually.\n"
        "3️⃣ /check_offer – Now the bot can log in automatically!\n\n"
        "⚠️ <b>Privacy Note:</b> Credentials are held in memory only.",
        parse_mode="HTML",
    )


# ── /login conversation ───────────────────────────────────────────────────────

async def login_start(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> int:
    """Begin the login conversation – ask for email."""
    await update.message.reply_text(
        "📧 Please enter your Gmail address:",
        reply_markup=ReplyKeyboardRemove(),
    )
    return AWAIT_EMAIL


async def login_email(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the email and ask for password."""
    email = update.message.text.strip()
    context.user_data["pending_email"] = email
    await update.message.reply_text(
        f"✅ Email received: `{email}`\n\n🔒 Now enter your password:",
        parse_mode="Markdown",
    )
    return AWAIT_PASSWORD


async def login_password(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store the password and ask for 2FA secret."""
    # Delete the message containing the password for security
    password = update.message.text.strip()
    try:
        await update.message.delete()
    except Exception:
        pass

    context.user_data["pending_password"] = password
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=(
            "✅ Password received (message deleted for security).\n\n"
            "🔑 *Now enter your 2FA TOTP Secret Key:*\n\n"
            "This is the secret key you received when setting up "
            "Google Authenticator (usually a 16-32 character code "
            "like `JBSWY3DPEHPK3PXP`).\n\n"
            "💡 _You can find this in your Google Account → Security → "
            "2-Step Verification → Authenticator app → Change phone → "
            "'Can't scan it?' to see the secret key._\n\n"
            "Type /skip if 2FA is not enabled on this account."
        ),
        parse_mode="Markdown",
    )
    return AWAIT_2FA


async def login_2fa(update: Update,
                    context: ContextTypes.DEFAULT_TYPE) -> int:
    """Store 2FA secret, generate device profile, and finish login."""
    chat_id = update.effective_chat.id
    totp_secret = update.message.text.strip()

    # Delete the message containing the 2FA secret for security
    try:
        await update.message.delete()
    except Exception:
        pass

    email = context.user_data.pop("pending_email", "")
    password = context.user_data.pop("pending_password", "")

    session = _get_session(chat_id)
    session["email"] = email
    session["password"] = password
    session["totp_secret"] = totp_secret
    session["device"] = create_device_profile()
    session["offer_link"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ *All credentials saved!* A new Pixel 10 Pro device profile "
            "has been created.\n\n"
            + session["device"].summary()
            + "\n\n🔐 2FA: ✅ Enabled"
            + "\n\nUse /check\\_offer to search for the Gemini Pro offer."
        ),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def login_skip_2fa(update: Update,
                         context: ContextTypes.DEFAULT_TYPE) -> int:
    """Skip 2FA and finish login without TOTP secret."""
    chat_id = update.effective_chat.id
    email = context.user_data.pop("pending_email", "")
    password = context.user_data.pop("pending_password", "")

    session = _get_session(chat_id)
    session["email"] = email
    session["password"] = password
    session["totp_secret"] = None
    session["device"] = create_device_profile()
    session["offer_link"] = None

    await context.bot.send_message(
        chat_id=chat_id,
        text=(
            "✅ *Credentials saved* (without 2FA). A new Pixel 10 Pro device "
            "profile has been created.\n\n"
            + session["device"].summary()
            + "\n\n🔐 2FA: ❌ Skipped"
            + "\n\nUse /check\\_offer to search for the Gemini Pro offer."
        ),
        parse_mode="Markdown",
    )
    return ConversationHandler.END


async def login_cancel(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel the login conversation."""
    context.user_data.pop("pending_email", None)
    context.user_data.pop("pending_password", None)
    await update.message.reply_text(
        "❌ Login cancelled.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ConversationHandler.END


# ── /setup (trusted device) ──────────────────────────────────────────────────

async def setup_device(update: Update,
                       context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Open a visible Chrome window for the user to manually log in
    and trust the device. This bypasses Google's extra verification.
    """
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if not session.get("email") or not session.get("password"):
        await update.message.reply_text(
            "⚠️ No credentials found. Please use /login first."
        )
        return

    device = session.get("device")
    if not device:
        device = create_device_profile()
        session["device"] = device

    await update.message.reply_text(
        "🖥️ <b>Device Trust Setup</b>\n\n"
        "A Chrome window will open on your PC.\n"
        "The bot will auto-fill your email, password, and 2FA code.\n\n"
        "👉 <b>You need to:</b>\n"
        "1. Complete any extra Google verification (SMS code, etc.)\n"
        "2. If Google asks 'Trust this device?' — click <b>Yes</b>\n"
        "3. Wait for the bot to confirm success\n\n"
        "⏳ You have 2 minutes to complete the verification.\n"
        "The browser will close automatically after.",
        parse_mode="HTML",
    )

    try:
        success = setup_trusted_device(
            session["email"],
            session["password"],
            device,
            totp_secret=session.get("totp_secret"),
            chat_id=chat_id,
        )

        if success:
            await update.message.reply_text(
                "✅ <b>Device trusted successfully!</b>\n\n"
                "Google now recognizes this as a trusted device.\n"
                "You can now use /check_offer — it will log in "
                "without extra verification! 🎉",
                parse_mode="HTML",
            )
        else:
            await update.message.reply_text(
                "❌ <b>Setup timed out.</b>\n\n"
                "You didn't complete the verification in time.\n"
                "Try again with /setup.",
                parse_mode="HTML",
            )
    except Exception as exc:
        logger.exception("Error in setup_device for chat %s", chat_id)
        await update.message.reply_text(
            f"❌ Error during setup: {exc}"
        )


# ── /check_offer ──────────────────────────────────────────────────────────────

async def check_offer(update: Update,
                      context: ContextTypes.DEFAULT_TYPE) -> None:
    """Run Google One automation and report the result."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if not session.get("email") or not session.get("password"):
        await update.message.reply_text(
            "⚠️ No credentials found. Please use /login first."
        )
        return

    device = session.get("device")
    if not device:
        device = create_device_profile()
        session["device"] = device

    await update.message.reply_text(
        "⏳ Launching Pixel 10 Pro device simulator and logging in…\n"
        "This may take up to 60 seconds."
    )

    try:
        offer_link = check_gemini_offer(
            session["email"],
            session["password"],
            device,
            totp_secret=session.get("totp_secret"),
            chat_id=chat_id,
        )
    except GoogleAutomationError as exc:
        await update.message.reply_text(
            f"❌ <b>Error:</b>\n{exc}",
            parse_mode="HTML",
        )
        return
    except Exception as exc:
        logger.exception("Unexpected error in check_offer for chat %s", chat_id)
        await update.message.reply_text(
            f"❌ An unexpected error occurred: {exc}"
        )
        return

    if offer_link:
        session["offer_link"] = offer_link
        await update.message.reply_text(
            "🎉 <b>Gemini Pro Offer Found!</b>\n\n"
            "Click the link below to activate your 12-month free Gemini Pro:\n\n"
            f"🔗 {offer_link}\n\n"
            "<i>Use /get_link to retrieve this link again.</i>",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "😔 No active Gemini Pro offer was detected on your Google One "
            "account at this time.\n\n"
            "The offer may not be available for your account region or may "
            "have already been activated. Try again later."
        )


# ── /get_link ─────────────────────────────────────────────────────────────────

async def get_link(update: Update,
                   context: ContextTypes.DEFAULT_TYPE) -> None:
    """Return the last captured offer link for this session."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)
    link = session.get("offer_link")

    if link:
        await update.message.reply_text(
            f"🔗 <b>Last captured offer link:</b>\n\n{link}",
            parse_mode="HTML",
        )
    else:
        await update.message.reply_text(
            "ℹ️ No offer link has been captured yet. "
            "Use /check_offer to search for the Gemini Pro offer."
        )


# ── /status ───────────────────────────────────────────────────────────────────

async def status(update: Update,
                 context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show current session and device profile summary."""
    chat_id = update.effective_chat.id
    session = _get_session(chat_id)

    if not session:
        await update.message.reply_text(
            "ℹ️ No active session. Use /login to get started."
        )
        return

    email = session.get("email", "—")
    has_creds = bool(session.get("email") and session.get("password"))
    has_2fa = bool(session.get("totp_secret"))
    offer_link = session.get("offer_link")
    device = session.get("device")

    lines = [
        "📊 *Session Status*\n",
        f"Account: `{email}`",
        f"Credentials loaded: {'✅' if has_creds else '❌'}",
        f"2FA enabled: {'✅' if has_2fa else '❌'}",
        f"Offer link captured: {'✅' if offer_link else '❌'}",
    ]

    if device:
        lines.append("\n" + device.summary())

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
    )


# ── Application setup ─────────────────────────────────────────────────────────

def main() -> None:
    token = config.TELEGRAM_BOT_TOKEN
    if not token:
        logger.error(
            "TELEGRAM_BOT_TOKEN environment variable is not set. "
            "Set it in Replit Secrets and restart."
        )
        sys.exit(1)

    app = Application.builder().token(token).build()

    # /login conversation
    login_conv = ConversationHandler(
        entry_points=[CommandHandler("login", login_start)],
        states={
            AWAIT_EMAIL: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_email)
            ],
            AWAIT_PASSWORD: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_password)
            ],
            AWAIT_2FA: [
                CommandHandler("skip", login_skip_2fa),
                MessageHandler(filters.TEXT & ~filters.COMMAND, login_2fa),
            ],
        },
        fallbacks=[CommandHandler("cancel", login_cancel)],
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(login_conv)
    app.add_handler(CommandHandler("setup", setup_device))
    app.add_handler(CommandHandler("check_offer", check_offer))
    app.add_handler(CommandHandler("get_link", get_link))
    app.add_handler(CommandHandler("status", status))

    logger.info("Bot is running. Press Ctrl-C to stop.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
