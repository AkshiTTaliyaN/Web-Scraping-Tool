"""
LAYER 5 — KPI & Analytics Scraper
Extracts stat cards, metric numbers, and chart data from portal pages.
Works by trying multiple common dashboard patterns.
All data saved locally as CSV.
"""

import re
import pandas as pd
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException
from config import CSV_DIR, log


KPI_SELECTORS = [
    # Generic card patterns
    ".card", ".card-body", ".info-box", ".small-box",
    ".stat-card", ".kpi-card", ".metric-card", ".summary-card",
    ".widget", ".dashboard-widget", ".counter-box",
    # Bootstrap / AdminLTE patterns
    ".card .card-body", ".info-box-content",
    ".small-box-footer",
    # Specific value containers
    "[class*='kpi']", "[class*='metric']", "[class*='stat']",
    "[class*='counter']", "[class*='summary']", "[class*='total']",
    "[class*='count']", "[class*='number']",
    # Data attribute patterns
    "[data-stat]", "[data-metric]", "[data-value]",
]

NUMBER_PATTERN = re.compile(
    r'[\d,]+\.?\d*\s*(%|cr|lakh|k|m|b)?', re.IGNORECASE)


def is_likely_kpi(element):
    """Check if an element looks like a KPI card."""
    try:
        text = element.text.strip()
        if not text or len(text) > 300:
            return False
        if not NUMBER_PATTERN.search(text):
            return False
        if not element.is_displayed():
            return False
        return True
    except Exception:
        return False


def parse_kpi_element(element):
    """
    Parse a KPI element into label + value.
    Handles common layouts:
      - Label on top, number below
      - Number on top, label below
    """
    try:
        text = element.text.strip()
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        if not lines:
            return None

        number_line = None
        label_lines = []

        for line in lines:
            if NUMBER_PATTERN.search(line) and len(line) < 30:
                number_line = line
            else:
                label_lines.append(line)

        if number_line and label_lines:
            return {
                "label": " | ".join(label_lines[:2]),
                "value": number_line,
                "raw_text": text[:200]
            }
        elif lines:
            return {
                "label": lines[0] if len(lines) > 1 else "KPI",
                "value": lines[-1],
                "raw_text": text[:200]
            }
    except Exception:
        pass
    return None


def scrape_kpis_from_page(driver, url):
    """
    Scrape all KPI cards from current page.
    Returns list of dicts with label/value pairs.
    """
    kpis = []
    seen_texts = set()

    for selector in KPI_SELECTORS:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for el in elements:
                if not is_likely_kpi(el):
                    continue

                text = el.text.strip()
                # Deduplicate
                if text in seen_texts:
                    continue
                seen_texts.add(text)

                parsed = parse_kpi_element(el)
                if parsed:
                    parsed["source_url"] = url
                    parsed["selector"] = selector
                    kpis.append(parsed)

        except Exception:
            continue

    unique_kpis = []
    seen_values = set()
    for kpi in kpis:
        val = kpi.get("value", "")
        if val not in seen_values:
            seen_values.add(val)
            unique_kpis.append(kpi)

    if unique_kpis:
        log(f"  Found {len(unique_kpis)} KPI(s) on page")

    return unique_kpis


def scrape_visible_text_stats(driver):
    """
    Fallback: scrape any visible numbers with labels from page body.
    Useful when KPI cards don't match standard patterns.
    """
    stats = []
    try:
        body = driver.find_element(By.TAG_NAME, "body")
        all_elements = body.find_elements(
            By.XPATH,
            ".//*[not(self::script) and not(self::style) and "
            "string-length(normalize-space(text())) > 0 and "
            "string-length(normalize-space(text())) < 100]"
        )

        seen = set()
        for el in all_elements:
            try:
                text = el.text.strip()
                if text in seen:
                    continue
                if NUMBER_PATTERN.search(text) and 2 < len(text) < 80:
                    seen.add(text)
                    stats.append({"raw_text": text})
            except Exception:
                continue

    except Exception as e:
        log(f"  Text stats fallback error: {e}", level="WARN")

    return stats


def save_kpis(all_kpis, page_index, url):
    """Save KPIs from a page as CSV."""
    if not all_kpis:
        return None

    clean_url = re.sub(r'[^a-zA-Z0-9]', '_', url.split("//")[-1])[:50]
    filename = f"kpis_p{page_index}_{clean_url}.csv"
    filepath = CSV_DIR / filename

    df = pd.DataFrame(all_kpis)
    df.to_csv(filepath, index=False, encoding="utf-8-sig")
    log(f"  KPIs saved: {filename}")
    return str(filepath)


def scrape_page_kpis(driver, url, page_index):
    """
    Master KPI scraper for a single page.
    Returns saved file path or None.
    """
    kpis = scrape_kpis_from_page(driver, url)

    if not kpis:
        raw_stats = scrape_visible_text_stats(driver)
        if raw_stats:
            kpis = raw_stats
            log(f"  Used fallback text stat scraper: {len(kpis)} items")

    return save_kpis(kpis, page_index, url)
