import json
import os
import yaml
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor

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


def ensure_seen_file():
    """Make sure seen_tenders.json exists even on first run."""
    if not os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "w") as f:
            json.dump([], f)


def load_seen():
    ensure_seen_file()
    try:
        with open(SEEN_FILE, "r") as f:
            data = json.load(f)
            return set(data) if isinstance(data, list) else set()
    except:
        return set()


def save_seen(seen_ids):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)


# ------------------------------------------------------
# Keyword matching
# ------------------------------------------------------
def match_keywords(text: str):
    text = text.lower()

    tier1_hits = [kw for kw in TIER1_KEYWORDS if kw in text]
    if not tier1_hits:
        return False, [], []

    tier2_hits = [kw for kw in TIER2_KEYWORDS if kw in text]
    return True, tier1_hits, tier2_hits


# ------------------------------------------------------
# Fetch helper
# ------------------------------------------------------
def fetch(url: str) -> str | None:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (TenderMonitorBot)"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
        print(f"❌ Fetch failed {url}: {resp.status_code}")
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
    return None


def fetch_many(urls, max_workers=8):
    """Parallel fetch helper."""
    results = {}
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(fetch, u): u for u in urls}
        for fut in futures:
            url = futures[fut]
            try:
                results[url] = fut.result()
            except:
                results[url] = None
    return results


# ------------------------------------------------------
# UNDP CONSULTANCIES
# ------------------------------------------------------
def scrape_undp_consultancies():
    base_url = "https://jobs.undp.org"
    url = f"{base_url}/cj_view_consultancies.cfm"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    for row in soup.find_all("tr"):
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(strip=True)
        if not title:
            continue

        full_url = urljoin(base_url, link["href"])

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# UNDP PROCUREMENT (deduped)
# ------------------------------------------------------
def scrape_undp_procurement():
    base_url = "https://procurement-notices.undp.org"
    url = base_url + "/"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []
    seen_urls = set()

    for link in soup.find_all("a", href=True):
        href = link["href"]
        if "view_notice" not in href and "view_negotiation" not in href:
            continue

        full_url = urljoin(base_url, href)
        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# RELIEFWEB — API SEARCH + FULL DESCRIPTION SCAN
# ------------------------------------------------------
def scrape_reliefweb():
    api_url = "https://api.reliefweb.int/v1/jobs"

    # ReliefWeb requires quoted search tokens if they contain spaces
    quoted_tier1 = [f'"{kw}"' for kw in TIER1_KEYWORDS]

    payload = {
        "query": {
            "value": " OR ".join(quoted_tier1),
            "operator": "OR",
            "fields": ["title", "body"]
        },
        "fields": {
            "include": ["title", "url"]
        },
        "limit": 100
    }

    try:
        resp = requests.post(api_url, json=payload, timeout=30)
        if resp.status_code != 200:
            print(f"❌ ReliefWeb API returned {resp.status_code}")
            return []
    except Exception as e:
        print(f"❌ ReliefWeb API error: {e}")
        return []

    data = resp.json()
    if "data" not in data:
        return []

    tenders = []

    # Step 2 — Scrape full job pages
    for item in data["data"]:
        fields = item.get("fields", {})
        title = fields.get("title", "").strip()
        url = fields.get("url", "").strip()

        if not title or not url:
            continue

        page_html = fetch(url)
        if not page_html:
            continue

        soup = BeautifulSoup(page_html, "html.parser")

        body_div = soup.find("div", class_="rw-job__body")
        full_text = (title + " " + (body_div.get_text(" ", strip=True) if body_div else "")).lower()

        match, t1, t2 = match_keywords(full_text)
        if not match:
            continue

        tenders.append({
            "id": url,
            "title": title,
            "url": url,
            "tier1": t1,
            "tier2": t2
        })

    return tenders


# ------------------------------------------------------
# WORLD BANK — unchanged, but we can improve later
# ------------------------------------------------------
def scrape_world_bank():
    base_url = "https://wbgeprocure-rfxnow.worldbank.org"
    url = f"{base_url}/rfxnow/public/advertisement/index.html"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []
    seen_urls = set()

    for row in soup.find_all("tr"):
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(strip=True)
        full_url = urljoin(base_url, link["href"])

        if full_url in seen_urls:
            continue
        seen_urls.add(full_url)

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# Email builder
# ------------------------------------------------------
def build_email_bodies(items):
    if not items:
        return (
            "<html><body><h2>No NEW marine/ocean-related tenders found today.</h2></body></html>",
            "No NEW marine/ocean-related tenders found today."
        )

    # Text version
    text_lines = ["NEW Marine / Ocean Opportunities\n"]
    current_source = None

    for source, t in items:
        if source != current_source:
            text_lines.append(f"\n{source}")
            text_lines.append("-" * len(source))
            current_source = source

        text_lines.append(f"- {t['title']}")
        text_lines.append(f"  {t['url']}")
        if t['tier1']:
            text_lines.append(f"  Tier 1: {', '.join(t['tier1'])}")
        if t['tier2']:
            text_lines.append(f"  Tier 2: {', '.join(t['tier2'])}")

    body_text = "\n".join(text_lines)

    # HTML version
    html = []
    html.append("""
    <html><body style="font-family:Arial, sans-serif; font-size:14px;">
    <h2 style="color:#004080;">🌊 New Marine / Ocean Opportunities</h2>
    """)

    current_source = None

    for source, t in items:
        if source != current_source:
            html.append(f"<h3 style='margin-top:25px;color:#0066aa;'>{source}</h3><hr>")
            current_source = source

        html.append(f"""
        <div style="margin-bottom:20px;">
            <strong>{t['title']}</strong><br>
            <a href="{t['url']}" style="color:#1a73e8;">View Opportunity</a><br>
        """)

        if t['tier1']:
            html.append(f"<div style='font-size:12px;color:#006600;'>Tier 1: {', '.join(t['tier1'])}</div>")

        if t['tier2']:
            html.append(f"<div style='font-size:12px;color:#555;'>Tier 2: {', '.join(t['tier2'])}</div>")

        html.append("</div>")

    html.append("</body></html>")
    body_html = "".join(html)

    return body_html, body_text


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------
def main():
    config = load_config()
    email_to = config["email_to"]

    ensure_seen_file()
    seen = load_seen()
    updated = set(seen)

    new_items = []

    sources = [
        ("UNDP Consultancies", scrape_undp_consultancies),
        ("UNDP Procurement Notices", scrape_undp_procurement),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_world_bank)
    ]

    for name, func in sources:
        try:
            tenders = func()
        except Exception as e:
            print(f"❌ Error scraping {name}: {e}")
            continue

        for t in tenders:
            if t["id"] not in updated:
                new_items.append((name, t))
                updated.add(t["id"])

    body_html, body_text = build_email_bodies(new_items)

    creds = Credentials.from_authorized_user_file("token.json")

    send_email(
        subject="Daily Marine / Ocean Tender Report",
        body_html=body_html,
        body_text=body_text,
        creds=creds,
        email_to=email_to
    )

    save_seen(updated)


if __name__ == "__main__":
    main()
