import os
import time
import re
import logging
from typing import Optional
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By

from device_simulator import DeviceProfile
import config

logger = logging.getLogger(__name__)

class GoogleAutomationError(Exception):
    """Raised when automation encounters an unrecoverable error."""
    pass

def _get_driver(device: DeviceProfile, chat_id: Optional[int], headless: bool = False) -> webdriver.Chrome:
    """Return a Chrome WebDriver configured for the device profile."""
    options = Options()
    
    if headless:
        options.add_argument("--headless=new")
        
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={device.user_agent}")
    options.add_argument("--window-size=390,844")
    
    mobile_emulation = {
        "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0},
        "userAgent": device.user_agent,
    }
    options.add_experimental_option("mobileEmulation", mobile_emulation)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    if chat_id:
        profile_dir = os.path.abspath(f"chrome_profiles/{chat_id}")
        os.makedirs(profile_dir, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")
        
    try:
        return webdriver.Chrome(service=Service(), options=options)
    except Exception as e:
        raise GoogleAutomationError(f"Error launching Chrome: {e}\nEnsure Chrome and ChromeDriver are installed.")

def setup_trusted_device(email: str, password: str, device: DeviceProfile, totp_secret: Optional[str] = None, chat_id: Optional[int] = None) -> bool:
    """
    Open browser to let user manually log in.
    Saves cookies to the chat_id profile directory.
    """
    logger.info("Opening browser for manual login...")
    driver = None
    try:
        driver = _get_driver(device, chat_id, headless=False)
        
        # Step 1: Go to Google One Plans page
        driver.get("https://one.google.com/about/plans")
        logger.info("Visited https://one.google.com/about/plans")
        time.sleep(3)
        
        # Step 2: Look for the Sign In / Sign Up button and click it
        try:
            # Look for anchor tag containing ServiceLogin
            sign_in_btn = driver.find_element(By.CSS_SELECTOR, "a[href*='ServiceLogin']")
            sign_in_btn.click()
            logger.info("Clicked Sign In button.")
        except:
            logger.info("Sign In button not found. Maybe already logged in or page structure changed.")
            # If not found, manually go to login page just in case
            if "myaccount.google.com" not in driver.current_url and "accounts.google.com" not in driver.current_url:
                driver.get("https://accounts.google.com/")
        
        # Step 3: Try to autofill email to save time
        time.sleep(4)
        try:
            email_field = driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
            email_field.send_keys(email)
            driver.find_element(By.ID, "identifierNext").click()
            logger.info("Autofilled email.")
        except:
            pass
            
        # Give user 120 seconds to complete login & 2FA
        logger.info(f"Waiting 120 seconds for user (chat_id: {chat_id}) to complete manual login...")
        
        # We check the URL every 2 seconds to see if they successfully logged in early
        for _ in range(60):
            current_url = driver.current_url
            # If we are back at one.google.com or myaccount, login is successful
            if "one.google.com" in current_url or "myaccount.google.com" in current_url or ("/u/0" in current_url and "accounts.google.com/signin" not in current_url):
                # Ensure we are not on the login page anymore
                if "ServiceLogin" not in current_url and "accounts.google.com/signin" not in current_url:
                    logger.info("Login successful detected!")
                    time.sleep(5) # wait for cookies to fully save
                    return True
            time.sleep(2)
            
        logger.info("120 seconds elapsed. Hoping login was successful.")
        return True
    except Exception as e:
        logger.error(f"Setup error: {e}")
        return False
    finally:
        if driver:
            driver.quit()

def check_gemini_offer(email: str, password: str, device: DeviceProfile, totp_secret: Optional[str] = None, chat_id: Optional[int] = None) -> Optional[str]:
    """
    Check for the free Pixel Gemini Pro offer using Selenium.
    If not logged in, it will prompt for manual login first.
    """
    driver = None
    try:
        # Open visible so user can see what is happening.
        driver = _get_driver(device, chat_id, headless=False)
        
        # Step 1: Go to Google One Plans page
        driver.get("https://one.google.com/about/plans")
        logger.info("Visited https://one.google.com/about/plans")
        time.sleep(3)
        
        # Step 2: Check if we need to log in
        try:
            sign_in_btn = driver.find_element(By.CSS_SELECTOR, "a[href*='ServiceLogin']")
            logger.info("Not logged in. Clicking Sign In button.")
            sign_in_btn.click()
            time.sleep(4)
            
            # Autofill email
            try:
                email_field = driver.find_element(By.CSS_SELECTOR, 'input[type="email"]')
                email_field.send_keys(email)
                driver.find_element(By.ID, "identifierNext").click()
            except:
                pass
                
            # Wait for manual login
            logger.info("Waiting up to 120 seconds for user to log in...")
            for _ in range(60):
                current_url = driver.current_url
                if "one.google.com" in current_url or "myaccount.google.com" in current_url:
                    if "ServiceLogin" not in current_url and "accounts.google.com/signin" not in current_url:
                        logger.info("Login successful detected!")
                        break
                time.sleep(2)
        except:
            logger.info("Already logged in or Sign In button not found. Proceeding to check offers.")

        # Step 3: Check Offers
        urls_to_check = [
            "https://one.google.com/explore-plan/gemini-advanced",
            "https://one.google.com/",
            "https://one.google.com/benefits"
        ]
        
        offer_pattern = re.compile(r'https?://one\.google\.com/offer/([A-Za-z0-9_-]+)', re.IGNORECASE)
        found_link = None
        
        for url in urls_to_check:
            logger.info(f"Checking {url} ...")
            driver.get(url)
            time.sleep(4)
            
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
            time.sleep(2)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(2)
            
            matches = offer_pattern.findall(driver.page_source)
            for code in matches:
                if code.lower() not in {"freetrial", "free-trial", "trial", "upgrade", "plans", "about", "home", "benefits"} and len(code) > 5:
                    found_link = f"https://one.google.com/offer/{code}"
                    break
                    
            if found_link:
                break
                
        if found_link:
            return found_link
        else:
            raise GoogleAutomationError("Gemini Pro offer not found. Ensure the account is eligible.")
    finally:
        if driver:
            driver.quit()
