"""
Configuration and constants for the Pixel 10 Pro Google One Gemini Bot.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Telegram ──────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")

# ── Device specs – Google Pixel 10 Pro (Android 16) ──────────────────────────
DEVICE_MODEL = "Pixel 10 Pro"
DEVICE_BRAND = "google"
DEVICE_MANUFACTURER = "Google"
ANDROID_VERSION = "16"
ANDROID_SDK = "36"
BUILD_ID = "AP4A.250405.002"
CHROME_VERSION = "124.0.6367.82"
CHROME_MAJOR_VERSION = 124

# Pool of realistic Pixel 10 Pro user-agent strings.
# The actual UA is assembled dynamically in device_simulator.py by
# substituting the per-session Chrome version patch suffix.
USER_AGENT_TEMPLATES = [
    (
        "Mozilla/5.0 (Linux; Android {android}; {model} Build/{build}; wv) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Version/4.0 Chrome/{chrome} Mobile Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Linux; Android {android}; {model} Build/{build}) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/{chrome} Mobile Safari/537.36"
    ),
]

# ── Google URLs ───────────────────────────────────────────────────────────────
GMAIL_LOGIN_URL = "https://accounts.google.com/signin/v2/identifier"
GOOGLE_ONE_URL = "https://one.google.com/"
GOOGLE_ONE_OFFERS_URL = "https://one.google.com/about/plans"
GOOGLE_ONE_BENEFITS_URL = "https://one.google.com/benefits"
GOOGLE_ONE_EXPLORE_URL = "https://one.google.com/explore-plan/gemini-advanced"
GOOGLE_ONE_HOME_URL = "https://one.google.com/home"

# URLs to scan for the free Pixel offer (in order of priority)
# The offer is found via: Google One → Profile → Settings
GOOGLE_ONE_SCAN_URLS = [
    "https://one.google.com/settings",
    "https://one.google.com/offer",
    "https://one.google.com/",
    "https://one.google.com/home",
    "https://one.google.com/benefits",
    "https://one.google.com/explore-plan/gemini-advanced",
    "https://one.google.com/about/plans",
]

# ── FREE Pixel offer detection keywords ──────────────────────────────────────
# These keywords identify the FREE 12-month Pixel-exclusive offer
FREE_OFFER_KEYWORDS = [
    "free",
    "no charge",
    "$0",
    "included",
    "at no cost",
    "complimentary",
    "pixel",
    "on us",
]

# General Gemini offer keywords (used alongside free keywords)
GEMINI_OFFER_KEYWORDS = [
    "gemini pro",
    "gemini advanced",
    "google ai premium",
    "google one ai premium",
    "ai premium",
    "12 month",
    "12-month",
    "1 year",
]

# URLs to EXCLUDE (support pages, not actual offer links)
EXCLUDED_URL_PATTERNS = [
    "support.google.com",
    "help.google.com",
    "policies.google.com",
    "play.google.com/about",
]

# ── HTTP request settings ─────────────────────────────────────────────────────
REQUEST_TIMEOUT = 30            # seconds

# ── Session storage ───────────────────────────────────────────────────────────
# In-memory dict keyed by Telegram chat_id.
# Values: {"email": ..., "password": ..., "device": <DeviceProfile>, "offer_link": ...}
SESSION_STORE: dict = {}

# ── Logging ───────────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
