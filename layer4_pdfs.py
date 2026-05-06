"""
LAYER 4 — PDF Downloader & Content Extractor
Downloads all PDFs from portal pages using session cookies.
Then extracts tables and text from each PDF locally.
Uses pdfplumber (text PDFs) with PyMuPDF fallback (scanned/complex PDFs).
All files saved locally — never uploaded anywhere.
"""

import time
import requests
from pathlib import Path
from config import PDF_DIR, CSV_DIR, log
import pandas as pd
import re


def get_session_cookies(driver):
    """Extract Selenium session cookies for use with requests."""
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie["name"], cookie["value"])
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/pdf,*/*",
        "Referer": driver.current_url,
    })
    return session


def find_pdf_links(driver):
    """Find all PDF links on the current page."""
    from selenium.webdriver.common.by import By
    pdf_links = set()

    try:
        anchors = driver.find_elements(By.TAG_NAME, "a")
        for anchor in anchors:
            href = anchor.get_attribute("href") or ""
            text = anchor.text.strip().lower()

            if href.lower().endswith(".pdf"):
                pdf_links.add(href)
                continue

            if "pdf" in href.lower() and href.startswith("http"):
                pdf_links.add(href)
                continue

            if any(kw in text for kw in
                   ["download", "report", "pdf", "view report",
                    "annual report", "statement"]):
                if href and href.startswith("http"):
                    pdf_links.add(href)

        buttons = driver.find_elements(By.TAG_NAME, "button")
        for btn in buttons:
            onclick = btn.get_attribute("onclick") or ""
            if "pdf" in onclick.lower() or "download" in onclick.lower():
                log(f"  Found download button (onclick): {btn.text[:50]}",
                    level="INFO")

    except Exception as e:
        log(f"  PDF link finder error: {e}", level="WARN")

    return list(pdf_links)


def download_pdf(url, session, filename=None):
    """
    Download a single PDF using the portal session.
    Returns local file path or None on failure.
    """
    try:
        if not filename:
            filename = url.split("/")[-1].split("?")[0]
            if not filename.lower().endswith(".pdf"):
                filename += ".pdf"

        filename = re.sub(r'[^\w\-_.]', '_', filename)
        filepath = PDF_DIR / filename

        if filepath.exists() and filepath.stat().st_size > 0:
            log(f"  Already downloaded: {filename}")
            return str(filepath)

        response = session.get(url, timeout=60, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")
        if "pdf" not in content_type.lower() and \
           not url.lower().endswith(".pdf"):
            first_bytes = b""
            for chunk in response.iter_content(chunk_size=4):
                first_bytes = chunk
                break
            if not first_bytes.startswith(b"%PDF"):
                log(f"  Not a PDF, skipping: {url[:60]}", level="WARN")
                return None

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        size_kb = filepath.stat().st_size // 1024
        log(f"  Downloaded: {filename} ({size_kb} KB)")
        return str(filepath)

    except Exception as e:
        log(f"  PDF download failed ({url[:60]}): {e}", level="WARN")
        return None


def download_all_pdfs(driver):
    """
    Find and download all PDFs from current page.
    Returns list of local file paths.
    """
    pdf_links = find_pdf_links(driver)
    if not pdf_links:
        return []

    log(f"  Found {len(pdf_links)} PDF link(s)")
    session = get_session_cookies(driver)
    downloaded = []

    for url in pdf_links:
        path = download_pdf(url, session)
        if path:
            downloaded.append(path)
        time.sleep(0.5)  # be polite

    return downloaded


def extract_with_pdfplumber(pdf_path):
    """
    Extract tables and text from text-based PDFs.
    Best for reports with structured tables.
    """
    try:
        import pdfplumber
        tables_found = []
        text_pages = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                tables = page.extract_tables()
                for i, table in enumerate(tables):
                    if not table:
                        continue
                    cleaned = [
                        [str(cell).strip() if cell else "" for cell in row]
                        for row in table
                    ]
                    if len(cleaned) >= 2:
                        try:
                            df = pd.DataFrame(
                                cleaned[1:], columns=cleaned[0])
                            tables_found.append(
                                (f"page{page_num}_table{i+1}", df))
                        except Exception:
                            df = pd.DataFrame(cleaned)
                            tables_found.append(
                                (f"page{page_num}_table{i+1}", df))

                if not tables:
                    text = page.extract_text()
                    if text:
                        text_pages.append(f"--- Page {page_num} ---\n{text}")

        return tables_found, text_pages

    except ImportError:
        log("  pdfplumber not installed", level="WARN")
        return [], []
    except Exception as e:
        log(f"  pdfplumber failed: {e}", level="WARN")
        return [], []



def save_pdf_extracts(pdf_path, tables, text_pages):
    """Save extracted PDF content as CSV and TXT files locally."""
    saved = []
    base_name = Path(pdf_path).stem

    for table_name, df in tables:
        if df.empty:
            continue
        filename = f"pdf_{base_name}_{table_name}.csv"
        filepath = CSV_DIR / filename
        df.to_csv(filepath, index=False, encoding="utf-8-sig")
        log(f"  PDF table saved: {filename}")
        saved.append(str(filepath))

    if text_pages:
        txt_path = CSV_DIR / f"pdf_{base_name}_text.txt"
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join(text_pages))
        log(f"  PDF text saved: pdf_{base_name}_text.txt")
        saved.append(str(txt_path))

    return saved


def extract_pdf_content(pdf_path):
    log(f"  Extracting content from: {Path(pdf_path).name}")

    tables, text_pages = extract_with_pdfplumber(pdf_path)

    if not tables and not text_pages:
        log(f"  Scanned PDF — downloaded but cannot extract text: "
            f"{Path(pdf_path).name}", level="WARN")
        return []

    return save_pdf_extracts(pdf_path, tables, text_pages)

def extract_all_downloaded_pdfs():
    """
    Process all PDFs in the PDF_DIR folder.
    Called after all downloads are complete.
    Returns list of all extracted file paths.
    """
    pdf_files = list(PDF_DIR.glob("*.pdf"))
    if not pdf_files:
        log("No PDFs to extract")
        return []

    log(f"\nExtracting content from {len(pdf_files)} PDF(s)...")
    all_extracted = []

    for pdf_path in pdf_files:
        extracted = extract_pdf_content(str(pdf_path))
        all_extracted.extend(extracted)

    return all_extracted
