"""
CONFIG — Central settings for the complete scraper system.
Edit this file to tune the scraper behaviour.
"""

from pathlib import Path
from datetime import datetime
import os

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "scraped_data"
PDF_DIR    = OUTPUT_DIR / "pdfs"
CSV_DIR    = OUTPUT_DIR / "tables"
LOG_DIR    = OUTPUT_DIR / "logs"

for d in [OUTPUT_DIR, PDF_DIR, CSV_DIR, LOG_DIR]:
    d.mkdir(parents=True, exist_ok=True)

PAGE_LOAD_WAIT = 10

PAGE_DELAY = 2

MAX_PAGES = 100

MAX_PAGINATION_PAGES = 50

JS_RENDER_WAIT = 5

HEADLESS = False
    
# Enter the urls of the pages you want to extract data from, so it only crawls those pages
SECTION_1_URL = ""   # e.g. "https://portal.com/section1"
SECTION_2_URL = ""   # e.g. "https://portal.com/section2"

LOG_FILE = LOG_DIR / f"scrape_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

def log(message, level="INFO"):
    """
    Print and save log message locally.
    NEVER logs any actual scraped data — only status messages.
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    line = f"[{timestamp}] [{level}] {message}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
