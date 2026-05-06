"""
MAIN RUNNER — Complete 6-Layer Web Scraper
Orchestrates all layers in sequence.
Run this file to start the full scraper.

Usage:
    python main.py

All data stays local. Nothing is uploaded or shared externally.
"""

import time
import sys
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv
import os

# Load all layers
from config import (
    PAGE_DELAY, MAX_PAGES, SECTION_1_URL, SECTION_2_URL,
    OUTPUT_DIR, CSV_DIR, PDF_DIR, log
)
from layer1_driver    import init_driver, login, relogin_if_needed
from layer2_tables    import scrape_tables_from_page
from layer3_pagination import scrape_with_pagination
from layer4_pdfs      import download_all_pdfs, extract_all_downloaded_pdfs
from layer5_kpis      import scrape_page_kpis
from layer6_validator import run_validation_and_merge

load_dotenv()
PORTAL_URL = os.getenv("PORTAL_URL")



def get_all_internal_links(driver, base_domain, start_url):
    """
    Crawl portal and collect all internal page URLs.
    Stays within same domain only.
    Smarter version: skips logout/delete/export links.
    """
    from selenium.webdriver.common.by import By

    SKIP_KEYWORDS = [
        "logout", "log-out", "signout", "sign-out",
        "delete", "remove", "export", "download",
        "print", "javascript", "mailto", "#"
    ]

    visited  = set()
    to_visit = {start_url}
    all_urls = []

    log(f"\nCrawling domain: {base_domain}")

    while to_visit and len(all_urls) < MAX_PAGES:
        url = to_visit.pop()

        if url in visited:
            continue
        visited.add(url)

        try:
            driver.get(url)
            time.sleep(PAGE_DELAY)

            if not relogin_if_needed(driver):
                log("Could not re-login, stopping crawl", level="ERROR")
                break

            all_urls.append(url)

            anchors = driver.find_elements(By.TAG_NAME, "a")
            for anchor in anchors:
                try:
                    href = anchor.get_attribute("href") or ""
                    if not href or not href.startswith("http"):
                        continue
                    if base_domain not in href:
                        continue
                    if any(kw in href.lower() for kw in SKIP_KEYWORDS):
                        continue
                    if href not in visited:
                        to_visit.add(href)
                except Exception:
                    continue

        except Exception as e:
            log(f"Crawl error on {url}: {e}", level="WARN")
            continue

    log(f"Crawl complete: {len(all_urls)} pages found")
    return all_urls


def get_target_urls(driver):
    """
    Determine which URLs to scrape.
    If SECTION_1_URL and SECTION_2_URL are set → scrape only those.
    Otherwise → crawl entire portal.
    """
    if SECTION_1_URL or SECTION_2_URL:
        urls = []
        if SECTION_1_URL:
            urls.append(SECTION_1_URL)
            log(f"Target Section 1: {SECTION_1_URL}")
        if SECTION_2_URL:
            urls.append(SECTION_2_URL)
            log(f"Target Section 2: {SECTION_2_URL}")
        return urls
    else:
        base_domain = urlparse(PORTAL_URL).netloc
        return get_all_internal_links(driver, base_domain, PORTAL_URL)



def scrape_page(driver, url, page_index, results):
    """
    Run all scraping layers on a single page.
    Updates results dict in place.
    """
    log(f"\n[{page_index}] {url}")

    page_result = {
        "url"      : url,
        "tables"   : [],
        "pdfs"     : [],
        "kpis"     : None,
        "status"   : "ok"
    }

    try:
        driver.get(url)
        time.sleep(PAGE_DELAY)

        if not relogin_if_needed(driver):
            page_result["status"] = "session_expired"
            results.append(page_result)
            return

        table_files = scrape_with_pagination(
            driver,
            scrape_tables_from_page,
            url,
            page_index
        )
        page_result["tables"] = table_files

        pdf_files = download_all_pdfs(driver)
        page_result["pdfs"] = pdf_files

        kpi_file = scrape_page_kpis(driver, url, page_index)
        page_result["kpis"] = kpi_file

    except KeyboardInterrupt:
        log("\nScraping interrupted by user", level="WARN")
        page_result["status"] = "interrupted"
        results.append(page_result)
        raise  # re-raise to stop the loop cleanly

    except Exception as e:
        log(f"Error scraping {url}: {e}", level="ERROR")
        page_result["status"] = f"error: {e}"

    results.append(page_result)


def print_summary(results, final_data):
    """Print final scraping summary."""
    total_tables = sum(len(r.get("tables", [])) for r in results)
    total_pdfs   = sum(len(r.get("pdfs",   [])) for r in results)
    total_kpis   = sum(1 for r in results if r.get("kpis"))
    errors       = sum(1 for r in results if "error" in r.get("status",""))

    print("\n" + "="*60)
    print("  ✅ COMPLETE SCRAPER — FINAL REPORT")
    print("="*60)
    print(f"  Pages scraped    : {len(results)}")
    print(f"  Table CSVs saved : {total_tables}  →  {CSV_DIR}")
    print(f"  PDFs downloaded  : {total_pdfs}  →  {PDF_DIR}")
    print(f"  KPI pages        : {total_kpis}")
    print(f"  Errors           : {errors}")
    print(f"  Final datasets   : {len(final_data)}  →  {OUTPUT_DIR}/final/")
    print("="*60)
    print("\n  Final datasets ready for dashboard:")
    for name in final_data:
        df = final_data[name]
        print(f"    • {name}: {df.shape[0]} rows x {df.shape[1]} cols")
    print("="*60)


def run():
    print("="*60)
    print("  🤖 COMPLETE 6-LAYER WEB SCRAPER")
    print("  All data stays local. Nothing shared externally.")
    print("="*60)

    if not PORTAL_URL:
        log("ERROR: PORTAL_URL missing in .env", level="ERROR")
        sys.exit(1)

    driver = init_driver()
    results = []

    try:
        if not login(driver):
            log("Cannot proceed without login", level="ERROR")
            return

        target_urls = get_target_urls(driver)

        if not target_urls:
            log("No URLs to scrape", level="ERROR")
            return

        log(f"\nScraping {len(target_urls)} page(s)...\n")

        for i, url in enumerate(target_urls, 1):
            try:
                scrape_page(driver, url, i, results)
            except KeyboardInterrupt:
                log("Stopped by user — saving what we have...", level="WARN")
                break

        log("\nExtracting PDF content...")
        extract_all_downloaded_pdfs()

        final_data = run_validation_and_merge()

        print_summary(results, final_data)

    except Exception as e:
        log(f"Fatal error: {e}", level="ERROR")
        import traceback
        traceback.print_exc()

    finally:
        driver.quit()
        log("\nBrowser closed. All data saved locally.")


if __name__ == "__main__":
    run()
