# Web-Scraping-Tool
An automatic web scraping tool, which extracts any data from a given website or url
Extracts HTML tables, downloads PDFs, scrapes KPI data, and produces
clean CSV files — all stored locally on your machine.

## Setup

**Step 1 — Create your `.env` file:**
```bash
cp .env.template .env
```

**Step 2 — Fill in your portal credentials:**
```
PORTAL_URL="url"
PORTAL_EMAIL=email
PORTAL_PASSWORD=pass
```

**Step 3 — Set your target sections in `config.py`:**
```python
# Leave empty for full portal crawl
# Set specific URLs to scrape only those pages (recommended)
SECTION_1_URL = "https://your-portal.com/section1"
SECTION_2_URL = "https://your-portal.com/section2"
```
## Usage

```bash
python main.py
```
