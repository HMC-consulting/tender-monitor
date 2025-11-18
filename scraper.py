import json
import os
import yaml
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from emailer import send_email
from google.oauth2.credentials import Credentials
from keywords import TIER1_KEYWORDS, TIER2_KEYWORDS


# ------------------------------------------------------
# Load config
# ------------------------------------------------------
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------
# Duplicate tracking
# ------------------------------------------------------
SEEN_FILE = "seen_tenders.json"

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r") as f:
            try:
                return set(json.load(f))
            except:
                return set()
    return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)


# ------------------------------------------------------
# Keyword tier-matching
# ------------------------------------------------------
def match_keywords(text):
    text = text.lower()

    tier1_hits = [kw for kw in TIER1_KEYWORDS if kw in text]
    if not tier1_hits:
        return False, [], []

    tier2_hits = [kw for kw in TIER2_KEYWORDS if kw in text]
    return True, tier1_hits, tier2_hits


# ------------------------------------------------------
# Fetch utility
# ------------------------------------------------------
def fetch(url):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return r.text
        return None
    except:
        return None


# ------------------------------------------------------
# SCRAPER: UNDP Consultancies
# URL: https://jobs.undp.org/cj_view_consultancies.cfm
# ------------------------------------------------------
def scrape_undp():
    url = "https://jobs.undp.org/cj_view_consultancies.cfm"
    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")

    tenders = []

    for row in rows:
        link = row.find("a")
        if not link:
            continue

        title = link.text.strip()
        href = link.get("href")

        full_url = href if href.startswith("http") else urljoin(url, href)

        text_to_check = f"{title}".lower()

        is_match, t1, t2 = match_keywords(text_to_check)
        if is_match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# SCRAPER: ReliefWeb Jobs/Consultancies
# Example: https://reliefweb.int/jobs?search=marine
# ------------------------------------------------------
def scrape_reliefweb():
    base = "https://reliefweb.int"
    url = "https://reliefweb.int/jobs?search=marine"
    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = soup.select("article div.rw-river-article__body")  # job cards

    tenders = []

    for item in items:
        title_el = item.find("a")
        if not title_el:
            continue

        title = title_el.text.strip()
        href = title_el.get("href")
        full_url = urljoin(base, href)

        text_to_check = title.lower()

        is_match, t1, t2 = match_keywords(text_to_check)
        if is_match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# SCRAPER: World Bank eProcure
# URL: https://wbgeprocure-rfxnow.worldbank.org/...
# ------------------------------------------------------
def scrape_wbg():
    base_url = "https://wbgeprocure-rfxnow.worldbank.org"
    target = (
        "https://wbgeprocure-rfxnow.worldbank.org/rfxnow/public/advertisement/index.html"
    )

    html = fetch(target)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    rows = soup.select("table tr")

    tenders = []

    for row in rows:
        link = row.find("a")
        if not link:
            continue

        title = link.text.strip()
        href = link.get("href")

        full_url = href if href.startswith("http") else urljoin(base_url, href)

        is_match, t1, t2 = match_keywords(title.lower())
        if is_match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# MAIN: combine all scrapers
# ------------------------------------------------------
def main():
    config = load_config()
    email_to = config["email_to"]

    seen = load_seen()
    new_seen = set(seen)

    all_tenders = []

    # Run each scraper individually
    sources = [
        ("UNDP Consultancies", scrape_undp),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_wbg),
    ]

    for name, func in sources:
        try:
            tenders = func()
        except Exception as e:
            tenders = []
            print(f"Error scraping {name}: {e}")

        for t in tenders:
            if t["id"] not in seen:
                all_tenders.append((name, t))
                new_seen.add(t["id"])

    # Build email
    if not all_tenders:
        email_body = "No NEW marine/ocean-related tenders found today."
    else:
        lines = ["NEW Marine / Ocean Tender Results", ""]
        for source, t in all_tenders:
            lines.append(f"Source: {source}")
            lines.append(f"Title: {t['title']}")
            lines.append(f"URL: {t['url']}")
            lines.append(f"Tier 1 match: {', '.join(t['tier1'])}")
            if t["tier2"]:
                lines.append(f"Tier 2 match: {', '.join(t['tier2'])}")
            lines.append("")

        email_body = "\n".join(lines)

    # Email sending
    creds = Credentials.from_authorized_user_file("token.json")
    send_email(
        subject="Daily Marine/Ocean Tender Report",
        body=email_body,
        creds=creds,
        email_to=email_to
    )

    # Save updated seen list
    save_seen(new_seen)


if __name__ == "__main__":
    main()
