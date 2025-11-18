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
        try:
            with open(SEEN_FILE, "r") as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()
    return set()


def save_seen(seen_ids):
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)


# ------------------------------------------------------
# Keyword matching (Tier 1 required)
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
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
    return None


# ------------------------------------------------------
# UNDP CONSULTANCIES (jobs.undp.org)
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
# UNDP PROCUREMENT NOTICES
# ------------------------------------------------------
def scrape_undp_procurement():
    base_url = "https://procurement-notices.undp.org"
    url = base_url + "/"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    for link in soup.find_all("a", href=True):
        href = link["href"]

        if "view_notice" not in href and "view_negotiation" not in href:
            continue

        title = link.get_text(strip=True)
        if not title or len(title) < 3:
            continue

        full_url = urljoin(base_url, href)

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
# RELIEFWEB — API SEARCH (title + body)
# ------------------------------------------------------
def scrape_reliefweb():
    api_url = "https://api.reliefweb.int/v1/jobs"

    payload = {
        "query": {
            "value": " OR ".join(TIER1_KEYWORDS),
            "operator": "OR",
            "fields": ["title", "body"]
        },
        "fields": {
            "include": ["title", "url", "body"]
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

    for item in data["data"]:
        fields = item.get("fields", {})
        title = fields.get("title", "").strip()
        url = fields.get("url", "").strip()
        body = fields.get("body", "")

        if not title or not url:
            continue

        text = (title + " " + body).lower()
        match, t1, t2 = match_keywords(text)
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
# WORLD BANK
# ------------------------------------------------------
def scrape_world_bank():
    base_url = "https://wbgeprocure-rfxnow.worldbank.org"
    url = f"{base_url}/rfxnow/public/advertisement/index.html"

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
# HTML EMAIL BUILDER
# ------------------------------------------------------
def build_email_bodies(items):

    if not items:
        html = """
        <html><body>
        <h2 style="color:#004080;">No NEW marine/ocean-related tenders found today.</h2>
        </body></html>
        """
        return html, "No NEW marine/ocean-related tenders found today."

    # TEXT VERSION
    lines = ["NEW Marine / Ocean Tender Opportunities\n"]
    current_source = None

    for source, t in items:
        if source != current_source:
            lines.append(f"\n{source}")
            lines.append("-" * len(source))
            current_source = source

        lines.append(f"- {t['title']}")
        lines.append(f"  {t['url']}")
    body_text = "\n".join(lines)

    # HTML VERSION
    html = []
    html.append("""
    <html>
    <body style="font-family:Arial, sans-serif; font-size:14px;">
    <h2 style="color:#0a4b78;">🌊 New Marine / Ocean Opportunities</h2>
    """)

    current_source = None
    for source, t in items:
        if source != current_source:
            html.append(f"""
            <h3 style="color:#003d66; margin-top:30px;">{source}</h3>
            <hr>
            """)
            current_source = source

        html.append(f"""
        <div style="margin-bottom:20px; padding:10px 0;">
            <strong style="font-size:15px;">{t['title']}</strong><br>
            <a href="{t['url']}" style="color:#1a73e8;">View Opportunity</a><br>
        </div>
        """)

    html.append("</body></html>")

    return "".join(html), body_text


# ------------------------------------------------------
# MAIN
# ------------------------------------------------------
def main():
    config = load_config()
    email_to = config["email_to"]

    seen = load_seen()
    updated_seen = set(seen)
    new_items = []

    sources = [
        ("UNDP Consultancies", scrape_undp_consultancies),
        ("UNDP Procurement Notices", scrape_undp_procurement),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_world_bank)
    ]

    for source_name, func in sources:
        try:
            tenders = func()
        except Exception as e:
            print(f"❌ Error scraping {source_name}: {e}")
            continue

        for t in tenders:
            if t["id"] not in seen:
                new_items.append((source_name, t))
                updated_seen.add(t["id"])

    body_html, body_text = build_email_bodies(new_items)

    creds = Credentials.from_authorized_user_file("token.json")

    send_email(
        subject="Daily Marine / Ocean Tender Report",
        body_html=body_html,
        body_text=body_text,
        creds=creds,
        email_to=email_to
    )

    save_seen(updated_seen)


if __name__ == "__main__":
    main()
