"""
LAYER 1 — Driver Setup & Login
Handles Chrome initialization and secure portal login.
All data stays local. No external connections except the portal itself.
"""

import os
import time
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from config import PDF_DIR, PAGE_LOAD_WAIT, log

load_dotenv()

PORTAL_URL = os.getenv("PORTAL_URL")
EMAIL      = os.getenv("PORTAL_EMAIL")
PASSWORD   = os.getenv("PORTAL_PASSWORD")


def init_driver():
    """
    Initialize Chrome in stealth mode.
    PDFs auto-download to local PDF_DIR — never open in browser.
    """
    options = webdriver.ChromeOptions()

    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--start-maximized")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    prefs = {
        "download.default_directory"   : str(PDF_DIR.resolve()),
        "download.prompt_for_download" : False,
        "download.directory_upgrade"   : True,
        "plugins.always_open_pdf_externally": True,
        "safebrowsing.enabled"         : True,
    }
    options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=options
    )
    driver.execute_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    driver.execute_cdp_cmd("Network.setUserAgentOverride", {
        "userAgent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                     "AppleWebKit/537.36 (KHTML, like Gecko) "
                     "Chrome/122.0.0.0 Safari/537.36"
    })

    log("Driver initialized")
    return driver


def login(driver):
    """
    Log in using credentials from .env file.
    Returns True on success, False on failure.
    """
    if not PORTAL_URL or not EMAIL or not PASSWORD:
        log("ERROR: Missing credentials in .env file", level="ERROR")
        return False

    log(f"Navigating to login page...")
    driver.get(PORTAL_URL)
    wait = WebDriverWait(driver, PAGE_LOAD_WAIT)

    try:
        email_field = wait.until(EC.presence_of_element_located(
            (By.ID, "login_email")
        ))
        email_field.clear()
        email_field.send_keys(EMAIL)
        time.sleep(0.5)

        password_field = wait.until(EC.presence_of_element_located(
            (By.ID, "login_password")
        ))
        password_field.clear()
        password_field.send_keys(PASSWORD)
        time.sleep(0.5)

        login_button = wait.until(EC.element_to_be_clickable(
            (By.CSS_SELECTOR, "button.btn-login")
        ))
        login_button.click()

        time.sleep(3)

        if PORTAL_URL in driver.current_url and "login" in driver.current_url.lower():
            log("Login may have failed — still on login page", level="WARN")
            return False

        log("Login successful")
        return True

    except TimeoutException:
        log("Login timed out — could not find login fields", level="ERROR")
        return False
    except Exception as e:
        log(f"Login error: {e}", level="ERROR")
        return False


def relogin_if_needed(driver):
    """
    Detect if session expired and re-login automatically.
    Called before each page scrape.
    """
    if "login" in driver.current_url.lower():
        log("Session expired — re-logging in...", level="WARN")
        return login(driver)
    return True
