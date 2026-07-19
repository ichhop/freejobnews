"""
Government Job Scraper — starter template
--------------------------------------------
This is a working example scraper structure you can adapt per source site.
Each government site has different HTML, so you'll write one `parse_*` function
per source and register it below. The scheduler/dedup/DB logic stays the same
for every source, which is the point of structuring it this way.

Run:
    pip install requests beautifulsoup4 python-dateutil
    python scraper.py

Notes:
- This environment has no live network access, so this script is untested
  against the internet from here — run it on your own machine/server.
- Respect each site's robots.txt and rate limits. Add delays between requests
  (see SOURCES config below) and avoid parallel hammering of the same host.
- Always store the source URL you scraped, so you can re-verify or take a
  listing down if the source updates/removes a notice.
"""

import re
import json
import time
import sqlite3
import hashlib
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

import requests
from bs4 import BeautifulSoup

USER_AGENT = "SarkariScanBot/0.1 (+https://example.com/bot-info)"
REQUEST_DELAY_SECONDS = 3  # be polite -- don't hammer govt servers
DB_PATH = "jobs.db"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class JobPosting:
    source: str              # e.g. "ssc.nic.in"
    org: str                 # e.g. "Staff Selection Commission"
    post_title: str          # e.g. "Combined Graduate Level Exam 2026"
    qualification: Optional[str]
    vacancies: Optional[int]
    last_date: Optional[str]      # ISO date string if parseable, else raw text
    apply_link: str
    notification_pdf: Optional[str]
    scraped_at: str
    raw_hash: str = ""       # used for change detection / de-dup

    def compute_hash(self):
        key = f"{self.source}|{self.post_title}|{self.last_date}"
        self.raw_hash = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self.raw_hash


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------

def init_db(path=DB_PATH):
    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            raw_hash TEXT PRIMARY KEY,
            source TEXT,
            org TEXT,
            post_title TEXT,
            qualification TEXT,
            vacancies INTEGER,
            last_date TEXT,
            apply_link TEXT,
            notification_pdf TEXT,
            scraped_at TEXT,
            first_seen TEXT,
            is_active INTEGER DEFAULT 1
        )
    """)
    conn.commit()
    return conn


def upsert_job(conn, job: JobPosting):
    job.compute_hash()
    existing = conn.execute(
        "SELECT raw_hash FROM jobs WHERE raw_hash = ?", (job.raw_hash,)
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE jobs SET scraped_at = ?, vacancies = ?, last_date = ? WHERE raw_hash = ?",
            (job.scraped_at, job.vacancies, job.last_date, job.raw_hash),
        )
    else:
        conn.execute(
            """INSERT INTO jobs
               (raw_hash, source, org, post_title, qualification, vacancies,
                last_date, apply_link, notification_pdf, scraped_at, first_seen, is_active)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
            (job.raw_hash, job.source, job.org, job.post_title, job.qualification,
             job.vacancies, job.last_date, job.apply_link, job.notification_pdf,
             job.scraped_at, job.scraped_at),
        )
    conn.commit()


# ---------------------------------------------------------------------------
# Fetch helper
# ---------------------------------------------------------------------------

def fetch(url: str) -> Optional[str]:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        resp.raise_for_status()
        return resp.text
    except requests.RequestException as e:
        print(f"[fetch error] {url}: {e}")
        return None


def extract_vacancy_count(text: str) -> Optional[int]:
    """Pull the first integer-looking vacancy figure out of free text."""
    match = re.search(r"(\d[\d,]{2,})\s*(?:posts?|vacanc)", text, re.IGNORECASE)
    if match:
        return int(match.group(1).replace(",", ""))
    return None


# ---------------------------------------------------------------------------
# Per-source parsers
# Each government site needs its own parser because HTML structures differ.
# This is the SSC example -- treat it as a TEMPLATE, not a guarantee the
# selectors are current (govt sites redesign without notice; expect to
# maintain these).
# ---------------------------------------------------------------------------

def parse_ssc(html: str, base_url: str) -> list[JobPosting]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    now = datetime.utcnow().isoformat()

    # SSC's "Notice Board" / "What's New" section is typically a list of
    # <a> tags with PDF links inside a table or ul. Adjust selector to
    # match the live site structure when you implement this for real.
    for link in soup.select("a[href$='.pdf']"):
        title = link.get_text(strip=True)
        if not title or len(title) < 8:
            continue
        href = link.get("href")
        full_url = href if href.startswith("http") else base_url.rstrip("/") + "/" + href.lstrip("/")

        job = JobPosting(
            source="ssc.nic.in",
            org="Staff Selection Commission",
            post_title=title,
            qualification=None,       # not reliably available at listing level
            vacancies=extract_vacancy_count(title),
            last_date=None,            # would need to open the PDF/notice page to get this reliably
            apply_link=base_url,
            notification_pdf=full_url,
            scraped_at=now,
        )
        results.append(job)

    return results


# Register additional site parsers here, one per source, e.g.:
# def parse_upsssc(html, base_url) -> list[JobPosting]: ...
# def parse_ibps(html, base_url) -> list[JobPosting]: ...


# ---------------------------------------------------------------------------
# Source registry — add one entry per government site you track
# ---------------------------------------------------------------------------

SOURCES = [
    {
        "name": "ssc",
        "url": "https://ssc.nic.in/",
        "parser": parse_ssc,
    },
    # {
    #     "name": "upsssc",
    #     "url": "https://upsssc.gov.in/",
    #     "parser": parse_upsssc,
    # },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def run():
    conn = init_db()
    total_new = 0

    for source in SOURCES:
        print(f"Scraping {source['name']} ...")
        html = fetch(source["url"])
        if not html:
            continue

        jobs = source["parser"](html, source["url"])
        print(f"  found {len(jobs)} listings")

        for job in jobs:
            upsert_job(conn, job)
            total_new += 1

        time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()
    print(f"Done. Processed {total_new} listings across {len(SOURCES)} source(s).")


def export_json(path="jobs_export.json"):
    """Dump current DB contents to JSON for the frontend/API to consume."""
    conn = init_db()
    rows = conn.execute("SELECT * FROM jobs WHERE is_active = 1 ORDER BY scraped_at DESC").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM jobs LIMIT 0").description]
    data = [dict(zip(cols, row)) for row in rows]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    conn.close()
    print(f"Exported {len(data)} jobs to {path}")


if __name__ == "__main__":
    run()
    export_json()
