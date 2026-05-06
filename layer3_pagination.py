"""
LAYER 3 — Pagination Handler
Detects and loops through all pages of a paginated table.
Handles: numbered pages, next buttons, load-more buttons, infinite scroll.
"""

import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, ElementNotInteractableException,
    StaleElementReferenceException, TimeoutException
)
from config import log

NEXT_PAGE_SELECTORS = [
    "a[aria-label='Next']",
    "a[aria-label='next']",
    "button[aria-label='Next']",
    "button[aria-label='next page']",
    ".pagination .next",
    ".pagination-next",
    "[class*='next-page']",
    "[class*='nextPage']",
    "li.next a",
    "a.next",
    "button.next",
    "[rel='next']",
    ".page-next",
    "a[title='Next']",
    "button[title='Next Page']",
]

LOAD_MORE_SELECTORS = [
    "button[class*='load-more']",
    "button[class*='loadMore']",
    "a[class*='load-more']",
    "[data-action='load-more']",
    "button:contains('Load More')",
    "button:contains('Show More')",
    "button:contains('View More')",
]


def find_next_button(driver):
    """Try all known next-page selectors. Returns element or None."""
    for selector in NEXT_PAGE_SELECTORS:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed() and btn.is_enabled():
                classes = btn.get_attribute("class") or ""
                aria_disabled = btn.get_attribute("aria-disabled") or ""
                if "disabled" not in classes and aria_disabled != "true":
                    return btn
        except NoSuchElementException:
            continue
    return None


def find_load_more_button(driver):
    """Find load-more button. Returns element or None."""
    for selector in LOAD_MORE_SELECTORS:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, selector)
            if btn.is_displayed() and btn.is_enabled():
                return btn
        except NoSuchElementException:
            continue

    try:
        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            text = btn.text.strip().lower()
            if text in ["load more", "show more", "view more", "load more records"]:
                if btn.is_displayed() and btn.is_enabled():
                    return btn
    except Exception:
        pass
    return None


def get_total_pages(driver):
    """
    Try to detect total number of pages from pagination info.
    Returns integer or None if cannot detect.
    """
    try:
        import re
        body_text = driver.find_element(By.TAG_NAME, "body").text

        matches = re.findall(r'of\s+(\d+)', body_text[:2000])
        if matches:
            return int(matches[-1])
    except Exception:
        pass
    return None


def scrape_with_pagination(driver, scrape_fn, url, page_index,
                           max_pages=50):
    """
    Master pagination handler.
    Calls scrape_fn() on each page, collects all results.

    Args:
        driver: Selenium WebDriver
        scrape_fn: function(driver, url, page_index) → list of DataFrames
        url: current page URL
        page_index: index for filename generation
        max_pages: safety limit to prevent infinite loops

    Returns:
        List of all saved CSV file paths across all pages
    """
    all_saved = []
    page_num = 1

    total = get_total_pages(driver)
    if total:
        log(f"  Pagination detected: {total} pages total")

    while page_num <= max_pages:
        log(f"  Scraping page {page_num}" +
            (f" of {total}" if total else ""))

        saved = scrape_fn(driver, url, f"{page_index}_pg{page_num}")
        all_saved.extend(saved)

        next_btn = find_next_button(driver)
        if next_btn:
            try:
                driver.execute_script("arguments[0].scrollIntoView();",
                                      next_btn)
                time.sleep(0.5)
                next_btn.click()
                time.sleep(2)  # wait for next page to load
                page_num += 1
                continue
            except (ElementNotInteractableException,
                    StaleElementReferenceException) as e:
                log(f"  Next button click failed: {e}", level="WARN")
                break

        load_more = find_load_more_button(driver)
        if load_more:
            try:
                prev_height = driver.execute_script(
                    "return document.body.scrollHeight")
                load_more.click()
                time.sleep(2)
                new_height = driver.execute_script(
                    "return document.body.scrollHeight")
                if new_height > prev_height:
                    page_num += 1
                    continue
                else:
                    break  # no new content loaded
            except Exception as e:
                log(f"  Load more failed: {e}", level="WARN")
                break

        prev_height = driver.execute_script(
            "return document.body.scrollHeight")
        driver.execute_script(
            "window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        new_height = driver.execute_script(
            "return document.body.scrollHeight")

        if new_height > prev_height:
            page_num += 1
            continue

        break

    log(f"  Pagination complete: scraped {page_num} page(s)")
    return all_saved
