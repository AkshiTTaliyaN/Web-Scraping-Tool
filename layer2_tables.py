"""
LAYER 2 — Smart Table Extraction
Tries 3 methods in order:
  1. pd.read_html() — fast, works on plain HTML tables
  2. Wait for JS + retry — handles JavaScript-rendered tables
  3. Selenium row-by-row — nuclear option, works on everything
All data stays in memory / local CSV only.
"""

import time
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException
from config import CSV_DIR, PAGE_LOAD_WAIT, log
import re


def sanitize_filename(url, page_index, table_index):
    """Generate a safe filename from URL"""
    clean = re.sub(r'[^a-zA-Z0-9]', '_', url.split("//")[-1])
    clean = re.sub(r'_+', '_', clean).strip('_')[:50]
    return f"table_p{page_index}_t{table_index}_{clean}.csv"


def method1_read_html(page_source):
    """
    Method 1: pandas read_html — fastest.
    Works on standard HTML <table> elements.
    """
    try:
        tables = pd.read_html(page_source, flavor='lxml')
        valid = [t for t in tables if t.shape[0] >= 2 and t.shape[1] >= 2]
        if valid:
            log(f"  Method 1 (read_html): found {len(valid)} table(s)")
        return valid
    except Exception:
        return []


def method2_wait_for_js(driver, wait_seconds=5):
    """
    Method 2: Wait for JavaScript to render, then retry read_html.
    Handles most modern JS-rendered dashboards.
    """
    log("  Method 2: waiting for JS render...")
    time.sleep(wait_seconds)

    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    time.sleep(1)
    driver.execute_script("window.scrollTo(0, 0);")
    time.sleep(1)

    return method1_read_html(driver.page_source)


def method3_selenium_extraction(driver):
    """
    Method 3: Selenium row-by-row extraction.
    Nuclear option — works even on custom div-based tables.
    Handles both <table> and <div>-based grid layouts.
    """
    log("  Method 3: Selenium row-by-row extraction...")
    results = []

    try:
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            rows_data = []
            rows = table.find_elements(By.TAG_NAME, "tr")
            if not rows:
                continue

            for row in rows:
                cells = row.find_elements(By.TAG_NAME, "th") or \
                        row.find_elements(By.TAG_NAME, "td")
                row_data = [cell.text.strip() for cell in cells]
                if any(row_data):
                    rows_data.append(row_data)

            if len(rows_data) >= 2:
                # First row as header
                try:
                    df = pd.DataFrame(rows_data[1:], columns=rows_data[0])
                    results.append(df)
                except Exception:
                    df = pd.DataFrame(rows_data)
                    results.append(df)

        if results:
            log(f"  Method 3A (HTML tables): found {len(results)} table(s)")
            return results
    except Exception as e:
        log(f"  Method 3A failed: {e}", level="WARN")

    try:
        grid_selectors = [
            "[role='grid']", "[role='table']",
            ".data-table", ".grid", ".datatable",
            "[class*='table']", "[class*='grid']",
            "[class*='data-grid']", "[class*='datagrid']"
        ]

        for selector in grid_selectors:
            grids = driver.find_elements(By.CSS_SELECTOR, selector)
            for grid in grids:
                rows = grid.find_elements(By.CSS_SELECTOR,
                    "[role='row'], .row, [class*='row']")
                rows_data = []
                for row in rows:
                    cells = row.find_elements(By.CSS_SELECTOR,
                        "[role='cell'], [role='columnheader'], "
                        ".cell, [class*='cell'], td, th")
                    row_data = [c.text.strip() for c in cells]
                    if any(row_data):
                        rows_data.append(row_data)

                if len(rows_data) >= 2:
                    try:
                        df = pd.DataFrame(rows_data[1:], columns=rows_data[0])
                        results.append(df)
                    except Exception:
                        df = pd.DataFrame(rows_data)
                        results.append(df)

        if results:
            log(f"  Method 3B (div grids): found {len(results)} table(s)")
            return results
    except Exception as e:
        log(f"  Method 3B failed: {e}", level="WARN")

    return results


def scrape_tables_from_page(driver, url, page_index):
    """
    Master table scraper — tries all 3 methods in order.
    Saves each table as a separate CSV file locally.
    Returns list of saved file paths.
    """
    saved = []
    tables = []

    tables = method1_read_html(driver.page_source)

    if not tables:
        tables = method2_wait_for_js(driver)

    if not tables:
        tables = method3_selenium_extraction(driver)

    if not tables:
        log(f"  No tables found on this page")
        return saved

    for i, df in enumerate(tables):
        if df.empty:
            continue

        df.columns = [str(c).strip() for c in df.columns]

        df = df.dropna(how='all').dropna(axis=1, how='all')

        if df.shape[0] < 1:
            continue

        filename = sanitize_filename(url, page_index, i + 1)
        filepath = CSV_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        log(f"  Saved: {filename} ({df.shape[0]} rows x {df.shape[1]} cols)")
        saved.append(str(filepath))

    return saved
