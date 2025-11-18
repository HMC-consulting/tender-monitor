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
    """Load previously-seen tender URLs."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                data = json.load(f)
                return set(data) if isinstance(data, list) else set()
        except Exception:
            return set()
    return set()


def save_seen(seen_ids):
    """Save updated seen tender IDs."""
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)


# ------------------------------------------------------
# Keyword tier matching
# ------------------------------------------------------
def match_keywords(text: str):
    """
    Tier 1 keywords must be present.
    Tier 2 are optional secondary matches.
    """
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
        print(f"❌ Fetch failed {url} — status {resp.status_code}")
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

        full_url = link["href"]
        if not full_url.startswith("http"):
            full_url = urljoin(base_url, full_url)

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2,
            })

    return tenders


# ------------------------------------------------------
# UNDP PROCUREMENT NOTICES (procurement-notices.undp.org)
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

        if not any(key in href for key in ["view_notice", "view_negotiation"]):
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
                "tier2": t2,
            })

    return tenders


# ------------------------------------------------------
# RELIEFWEB
# ------------------------------------------------------
def scrape_reliefweb():
    base_url = "https://reliefweb.int"
    url = f"{base_url}/jobs?search=marine"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    links = soup.select("a.rw-river-article__title-link")

    for link in links:
        title = link.get_text(strip=True)
        if not title:
            continue

        href = link.get("href")
        if not href:
            continue

        full_url = urljoin(base_url, href)

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2,
            })

    return tenders


# ------------------------------------------------------
# WORLD BANK EPROCURE
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
        if not title or len(title) < 3:
            continue

        href = link["href"]
        full_url = urljoin(base_url, href)

        match, t1, t2 = match_keywords(title)
        if match:
            tenders.append({
                "id": full_url,
                "title": title,
                "url": full_url,
                "tier1": t1,
                "tier2": t2,
            })

    return tenders


# ------------------------------------------------------
# Email builder
# ------------------------------------------------------
def build_email_body(tenders_with_source):
    if not tenders_with_source:
        return "No NEW marine/ocean-related tenders found today."

    lines = ["🌊 NEW Marine / Ocean Tender & Consultancy Opportunities", ""]

    current_source = None
    for source, t in tenders_with_source:
        if source != current_source:
            lines.append(f"📌 {source}")
            lines.append("-" * (4 + len(source)))
            current_source = source

        lines.append(f"• {t['title']}")
        lines.append(f"  ➤ {t['url']}")
        if t["tier1"]:
            lines.append(f"  🔹 tier 1: {', '.join(t['tier1'])}")
        if t["tier2"]:
            lines.append(f"  🔸 tier 2: {', '.join(t['tier2'])}")
        lines.append("")

    return "\n".join(lines)


# ------------------------------------------------------
# Main
# ------------------------------------------------------
def main():
    config = load_config()
    email_to = config["email_to"]

    seen = load_seen()
    updated_seen = set(seen)

    results = []

    sources = [
        ("UNDP Consultancies", scrape_undp_consultancies),
        ("UNDP Procurement Notices", scrape_undp_procurement),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_world_bank),
    ]

    for source_name, func in sources:
        try:
            tenders = func()
        except Exception as e:
            print(f"❌ Error scraping {source_name}: {e}")
            tenders = []

        for t in tenders:
            if t["id"] not in seen:
                results.append((source_name, t))
                updated_seen.add(t["id"])

    email_body = build_email_body(results)

    creds = Credentials.from_authorized_user_file("token.json")
    send_email(
        subject="Daily Marine / Ocean Tender Report",
        body=email_body,
        creds=creds,
        email_to=email_to,
    )

    save_seen(updated_seen)


if __name__ == "__main__":
    main()
