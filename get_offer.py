import time
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from device_simulator import create_device_profile

def run():
    print("📱 Generating Pixel 10 Pro Profile...")
    profile = create_device_profile()
    
    options = Options()
    # We open a visible browser so you can log in manually
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(f"--user-agent={profile.user_agent}")
    options.add_argument("--window-size=390,844")
    
    mobile_emulation = {
        "deviceMetrics": {"width": 390, "height": 844, "pixelRatio": 3.0},
        "userAgent": profile.user_agent,
    }
    options.add_experimental_option("mobileEmulation", mobile_emulation)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    
    print("🌐 Launching Chrome Browser...")
    try:
        driver = webdriver.Chrome(service=Service(), options=options)
    except Exception as e:
        print(f"Error launching Chrome: {e}\nEnsure Chrome and ChromeDriver are installed.")
        return

    print("\n=======================================================")
    print("1️⃣  A browser window has opened.")
    print("2️⃣  Please log into your Google Account in that window.")
    print("3️⃣  Complete any 2FA/Verification if asked.")
    print("=======================================================\n")
    
    driver.get("https://accounts.google.com/")
    
    input("🛑 PRESS 'ENTER' HERE ONLY AFTER YOU HAVE SUCCESSFULLY LOGGED IN...")

    print("\n🔍 Searching for Gemini Pro 12-Month Offer...")
    
    urls_to_check = [
        "https://one.google.com/explore-plan/gemini-advanced",
        "https://one.google.com/",
        "https://one.google.com/benefits"
    ]
    
    offer_pattern = re.compile(r'https?://one\.google\.com/offer/([A-Za-z0-9_-]+)', re.IGNORECASE)
    
    found_link = None
    for url in urls_to_check:
        print(f"Checking {url} ...")
        driver.get(url)
        time.sleep(3)
        
        # Scroll to ensure dynamic content loads
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2)")
        time.sleep(2)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(2)
        
        # Search raw HTML for the unique offer URL
        matches = offer_pattern.findall(driver.page_source)
        for code in matches:
            if code.lower() not in {"freetrial", "free-trial", "trial", "upgrade", "plans", "about", "home", "benefits"} and len(code) > 5:
                found_link = f"https://one.google.com/offer/{code}"
                break
                
        if found_link:
            break
            
    if found_link:
        print("\n🎉🎉🎉 OFFER FOUND! 🎉🎉🎉")
        print(f"🔗 YOUR UNIQUE ACTIVATION LINK: {found_link}")
        print("\n👉 Just open this link, add your card, and claim the trial!")
    else:
        print("\n❌ Could not find the offer link.")
        print("Make sure this Google Account hasn't claimed it before and is eligible.")
        
    input("\nPress 'ENTER' to close the browser...")
    driver.quit()

if __name__ == "__main__":
    run()
