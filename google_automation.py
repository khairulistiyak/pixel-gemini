"""
Google One Pixel offer detection – Hybrid approach.

1. /setup — Opens a VISIBLE Chrome window for manual Google login.
   Saves cookies to a persistent profile. Only needs to be done ONCE.

2. /check_offer — Uses saved cookies to browse Google One pages
   and find the unique Pixel offer link (one.google.com/offer/UNIQUE_CODE).
   Falls back to Selenium if cookies are expired.

No Android emulator needed.
"""

import json
import logging
import os
import re
import shutil
import time
from typing import Optional
from urllib.parse import urlparse

import pyotp
import requests

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)

import config
from device_simulator import DeviceProfile

logger = logging.getLogger(__name__)

# ── Paths ────────────────────────────────────────────────────────────────────

BASE_DIR = os.path.dirname(__file__)
CHROME_PROFILES_DIR = os.path.join(BASE_DIR, "chrome_profiles")
COOKIES_DIR = os.path.join(BASE_DIR, "saved_cookies")
DEBUG_DIR = os.path.join(BASE_DIR, "debug_logs")


def _save_debug(name: str, content: str) -> None:
    os.makedirs(DEBUG_DIR, exist_ok=True)
    path = os.path.join(DEBUG_DIR, f"{name}.txt")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(content[:20000])
        logger.info("Debug saved: %s", path)
    except Exception:
        pass


def _save_screenshot(driver: webdriver.Chrome, name: str) -> None:
    debug_dir = os.path.join(BASE_DIR, "debug_screenshots")
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{name}.png")
    try:
        driver.save_screenshot(path)
        logger.info("Screenshot: %s", path)
    except Exception:
        pass


# ── Chrome driver ────────────────────────────────────────────────────────────

def _build_driver(profile: DeviceProfile,
                  headless: bool = True) -> webdriver.Chrome:
    """Build a Chrome WebDriver simulating Pixel 10 Pro."""
    options = Options()

    if headless:
        options.add_argument("--headless=new")

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument("--window-size=390,844")
    options.add_argument(f"--user-agent={profile.user_agent}")

    mobile_emulation = {
        "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0},
        "userAgent": profile.user_agent,
    }
    options.add_experimental_option("mobileEmulation", mobile_emulation)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    driver = webdriver.Chrome(service=Service(), options=options)
    driver.implicitly_wait(10)
    driver.set_page_load_timeout(60)
    return driver


# ── Cookie management ────────────────────────────────────────────────────────

def _cookies_path(chat_id: int) -> str:
    os.makedirs(COOKIES_DIR, exist_ok=True)
    return os.path.join(COOKIES_DIR, f"{chat_id}.json")


def _save_cookies(driver: webdriver.Chrome, chat_id: int) -> None:
    """Save browser cookies to a JSON file."""
    cookies = driver.get_cookies()
    path = _cookies_path(chat_id)
    with open(path, "w") as f:
        json.dump(cookies, f)
    logger.info("Saved %d cookies to %s", len(cookies), path)


def _load_cookies(driver: webdriver.Chrome, chat_id: int) -> bool:
    """Load saved cookies into the browser."""
    path = _cookies_path(chat_id)
    if not os.path.exists(path):
        return False

    try:
        with open(path) as f:
            cookies = json.load(f)

        # First navigate to the domain so cookies can be set
        driver.get("https://one.google.com/")
        time.sleep(2)

        for cookie in cookies:
            # Remove problematic fields
            for key in ["sameSite", "expiry", "httpOnly", "secure"]:
                cookie.pop(key, None)
            try:
                driver.add_cookie(cookie)
            except Exception:
                pass

        logger.info("Loaded %d cookies from %s", len(cookies), path)
        return True

    except Exception as exc:
        logger.warning("Failed to load cookies: %s", exc)
        return False


def _cookies_to_requests(chat_id: int) -> Optional[requests.Session]:
    """Create a requests.Session from saved cookies."""
    path = _cookies_path(chat_id)
    if not os.path.exists(path):
        return None

    try:
        with open(path) as f:
            cookies = json.load(f)

        session = requests.Session()
        for cookie in cookies:
            session.cookies.set(
                cookie["name"],
                cookie["value"],
                domain=cookie.get("domain", ".google.com"),
            )

        logger.info("Created requests session with %d cookies", len(cookies))
        return session

    except Exception as exc:
        logger.warning("Failed to create session from cookies: %s", exc)
        return None


# ── Offer detection ──────────────────────────────────────────────────────────

OFFER_URL_PATTERN = re.compile(
    r'https?://one\.google\.com/offer/([A-Za-z0-9_-]+)',
    re.IGNORECASE,
)

GENERIC_SLUGS = {"freetrial", "free-trial", "trial", "upgrade",
                 "plans", "about", "home", "benefits"}

# Pages to scan for the offer
SCAN_URLS = [
    "https://one.google.com/",
    "https://one.google.com/home",
    "https://one.google.com/settings",
    "https://one.google.com/benefits",
    "https://one.google.com/explore-plan/gemini-advanced",
    "https://one.google.com/about/plans",
]


def _find_offer_in_html(html: str, page_url: str) -> Optional[str]:
    """Scan HTML for unique Pixel offer URL (one.google.com/offer/CODE)."""
    matches = OFFER_URL_PATTERN.findall(html)
    if not matches:
        return None

    candidates = []
    seen = set()

    for code in matches:
        if code in seen:
            continue
        seen.add(code)

        url = f"https://one.google.com/offer/{code}"

        if code.lower() in GENERIC_SLUGS:
            score = 5
            is_pixel = False
        elif len(code) >= 8 and code.replace("-", "").replace("_", "").isalnum():
            score = 50
            is_pixel = True
            logger.info("🎯 Found UNIQUE Pixel offer: %s", url)
        else:
            score = 15
            is_pixel = len(code) > 5

        candidates.append({"url": url, "code": code,
                           "score": score, "is_pixel": is_pixel})

    if candidates:
        candidates.sort(key=lambda x: x["score"], reverse=True)
        for i, c in enumerate(candidates[:5]):
            logger.info("  Offer #%d [score=%d] %s", i + 1, c["score"], c["url"])

        pixel = [c for c in candidates if c["is_pixel"]]
        if pixel:
            return pixel[0]["url"]
        return candidates[0]["url"]

    return None


def _scan_with_requests(session: requests.Session,
                        device: DeviceProfile) -> Optional[str]:
    """Scan Google One pages using HTTP requests (fast, no browser)."""
    session.headers.update({
        "User-Agent": device.user_agent,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })

    for i, url in enumerate(SCAN_URLS):
        try:
            logger.info("Scanning %d/%d: %s", i + 1, len(SCAN_URLS), url)
            resp = session.get(url, allow_redirects=True, timeout=30)
            logger.info("  → Status: %d, URL: %s", resp.status_code, resp.url)

            # Check if redirected to login
            if "accounts.google.com" in resp.url:
                logger.warning("  → Redirected to login (cookies expired)")
                return None

            _save_debug(f"scan_{i + 1}", f"URL: {resp.url}\n\n{resp.text}")

            offer = _find_offer_in_html(resp.text, resp.url)
            if offer:
                return offer

        except Exception as exc:
            logger.warning("Error scanning %s: %s", url, exc)

    return None


def _scan_with_selenium(driver: webdriver.Chrome) -> Optional[str]:
    """Scan Google One pages using Selenium (slower but handles JS)."""
    for i, url in enumerate(SCAN_URLS):
        try:
            logger.info("Browser scan %d/%d: %s", i + 1, len(SCAN_URLS), url)
            driver.get(url)
            time.sleep(4)

            _save_screenshot(driver, f"scan_{i + 1}")

            # Dismiss consent banners
            for sel in ('[aria-label="Accept all"]', 'button[jsname="higCR"]'):
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    time.sleep(1)
                    break
                except NoSuchElementException:
                    pass

            # Scroll to load content
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)

            # Check page source for offer URLs
            offer = _find_offer_in_html(driver.page_source, driver.current_url)
            if offer:
                return offer

            # Also check all links on the page
            links = driver.find_elements(By.TAG_NAME, "a")
            for link in links:
                try:
                    href = link.get_attribute("href") or ""
                    match = OFFER_URL_PATTERN.search(href)
                    if match:
                        code = match.group(1)
                        if code.lower() not in GENERIC_SLUGS and len(code) >= 8:
                            logger.info("🎯 Found Pixel offer link: %s", href)
                            return href
                except Exception:
                    continue

        except Exception as exc:
            logger.warning("Browser error on %s: %s", url, exc)

    return None


# ── Public API ───────────────────────────────────────────────────────────────

class GoogleAutomationError(Exception):
    """Raised when automation encounters an unrecoverable error."""


def setup_trusted_device(email: str, password: str,
                         device: DeviceProfile,
                         totp_secret: Optional[str] = None,
                         chat_id: Optional[int] = None) -> bool:
    """
    Open a VISIBLE Chrome window for the user to manually log in.
    Saves cookies for future automated use.
    
    The user must complete any Google verification (SMS, CAPTCHA) manually.
    After login, cookies are saved so /check_offer can work without login.
    """
    driver = None
    try:
        logger.info("Opening visible Chrome for manual login...")
        driver = _build_driver(device, headless=False)

        # Go to Google One (which will redirect to login)
        driver.get("https://one.google.com/")
        time.sleep(3)

        # Auto-fill email if on login page
        if "accounts.google.com" in driver.current_url:
            try:
                email_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'input[type="email"], input[name="identifier"]'))
                )
                email_field.clear()
                email_field.send_keys(email)

                next_btn = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#identifierNext"))
                )
                next_btn.click()
                time.sleep(3)
            except TimeoutException:
                pass

            # Auto-fill password
            try:
                pw_field = WebDriverWait(driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, 'input[type="password"]'))
                )
                pw_field.clear()
                pw_field.send_keys(password)

                pw_next = WebDriverWait(driver, 5).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, "#passwordNext"))
                )
                pw_next.click()
                time.sleep(3)
            except TimeoutException:
                pass

            # Auto-fill TOTP
            if totp_secret:
                try:
                    totp = pyotp.TOTP(totp_secret)
                    code = totp.now()

                    # Look for TOTP input
                    totp_selectors = [
                        'input[name="totpPin"]',
                        'input[type="tel"]',
                        '#totpPin',
                    ]
                    for sel in totp_selectors:
                        try:
                            field = WebDriverWait(driver, 5).until(
                                EC.element_to_be_clickable(
                                    (By.CSS_SELECTOR, sel))
                            )
                            field.send_keys(code)
                            logger.info("Auto-filled TOTP code")

                            # Click next
                            for btn_sel in ['#totpNext', 'button[type="submit"]']:
                                try:
                                    btn = driver.find_element(By.CSS_SELECTOR, btn_sel)
                                    btn.click()
                                    time.sleep(3)
                                    break
                                except NoSuchElementException:
                                    continue
                            break
                        except TimeoutException:
                            continue
                except Exception:
                    pass

        # Wait for user to complete login (up to 3 minutes)
        logger.info("Waiting for user to complete login...")
        for _ in range(36):  # 36 * 5 = 180 seconds
            time.sleep(5)
            try:
                current = driver.current_url
                host = urlparse(current).hostname or ""

                if host in ("one.google.com", "myaccount.google.com"):
                    path = urlparse(current).path or ""
                    if "signin" not in path and "challenge" not in path:
                        logger.info("✅ Login successful! URL: %s", current)

                        # Navigate to Google One to get all cookies
                        driver.get("https://one.google.com/")
                        time.sleep(3)

                        # Save cookies
                        if chat_id:
                            _save_cookies(driver, chat_id)

                        return True
            except Exception:
                pass

        logger.warning("Login timeout.")
        return False

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def check_gemini_offer(email: str, password: str,
                       device: DeviceProfile,
                       totp_secret: Optional[str] = None,
                       chat_id: Optional[int] = None) -> Optional[str]:
    """
    Check for the free Pixel Gemini Pro offer.

    Strategy:
    1. Use saved cookies with requests (fast, no browser)
    2. Use saved cookies with Selenium (handles JS)
    3. Fall back to full login
    """
    # ── Strategy 1: Fast scan with saved cookies (requests) ──────────────
    if chat_id:
        session = _cookies_to_requests(chat_id)
        if session:
            logger.info("=== Strategy 1: requests + saved cookies ===")
            offer = _scan_with_requests(session, device)
            if offer:
                return offer
            logger.info("Requests scan found no offer, trying Selenium...")

    # ── Strategy 2: Selenium with saved cookies ──────────────────────────
    driver = None
    try:
        logger.info("=== Strategy 2: Selenium + saved cookies ===")
        driver = _build_driver(device, headless=True)

        if chat_id and _load_cookies(driver, chat_id):
            # Verify we're logged in
            driver.get("https://one.google.com/")
            time.sleep(4)

            host = urlparse(driver.current_url).hostname or ""
            if host == "one.google.com":
                logger.info("✅ Logged in via saved cookies!")
                offer = _scan_with_selenium(driver)
                if offer:
                    return offer
            else:
                logger.info("Cookies expired, redirected to: %s",
                            driver.current_url)

        # ── Strategy 3: Full automated login ─────────────────────────────
        logger.info("=== Strategy 3: Full automated login ===")
        driver.get(config.GMAIL_LOGIN_URL)
        time.sleep(3)
        _save_screenshot(driver, "login_page")

        # Email
        try:
            email_field = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR,
                     'input[type="email"], input[name="identifier"]'))
            )
            email_field.send_keys(email)
            driver.find_element(By.CSS_SELECTOR, "#identifierNext").click()
            time.sleep(3)
        except TimeoutException:
            # May be a "Verify" page — try clicking Next
            try:
                btn = driver.find_element(
                    By.CSS_SELECTOR, 'button[jsname="LgbsSe"]')
                btn.click()
                time.sleep(3)
            except NoSuchElementException:
                pass

        _save_screenshot(driver, "after_email")

        # Password
        try:
            pw_field = WebDriverWait(driver, 15).until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, 'input[type="password"]'))
            )
            pw_field.send_keys(password)
            driver.find_element(By.CSS_SELECTOR, "#passwordNext").click()
            time.sleep(3)
        except TimeoutException:
            _save_screenshot(driver, "no_password")
            raise GoogleAutomationError(
                "Google is blocking automated login (CAPTCHA/challenge).\n\n"
                "💡 Run /setup first to manually log in.\n"
                "After that, /check_offer will use saved cookies."
            )

        _save_screenshot(driver, "after_password")

        # TOTP 2FA
        if totp_secret:
            try:
                totp = pyotp.TOTP(totp_secret)
                code = totp.now()

                for sel in ['input[name="totpPin"]', 'input[type="tel"]']:
                    try:
                        field = WebDriverWait(driver, 10).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
                        )
                        field.send_keys(code)

                        for btn_sel in ['#totpNext', 'button[type="submit"]']:
                            try:
                                driver.find_element(By.CSS_SELECTOR, btn_sel).click()
                                break
                            except NoSuchElementException:
                                continue
                        time.sleep(4)
                        break
                    except TimeoutException:
                        continue
            except Exception:
                pass

        _save_screenshot(driver, "after_login")

        # Check if login succeeded
        host = urlparse(driver.current_url).hostname or ""
        if "accounts.google.com" in driver.current_url:
            _save_screenshot(driver, "login_blocked")
            raise GoogleAutomationError(
                "Login blocked by Google security.\n\n"
                "💡 Run /setup first to manually log in.\n"
                "After that, /check_offer will use saved cookies."
            )

        # Save cookies for next time
        if chat_id:
            _save_cookies(driver, chat_id)

        # Scan for offers
        offer = _scan_with_selenium(driver)
        if offer:
            return offer

        raise GoogleAutomationError(
            "Logged in but no Pixel offer found.\n\n"
            "The offer may not be available for this account, "
            "or it may require the Google One Android app."
        )

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
