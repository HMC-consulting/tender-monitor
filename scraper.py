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
# Config
# ------------------------------------------------------
def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


# ------------------------------------------------------
# Duplicate tracking using seen_tenders.json
# ------------------------------------------------------
SEEN_FILE = "seen_tenders.json"


def load_seen():
    """Load previously seen tender IDs (URLs) from JSON."""
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return set(data)
        except Exception:
            pass
    return set()


def save_seen(seen_ids):
    """Save updated set of seen tender IDs back to JSON."""
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(list(seen_ids)), f, indent=2)


# ------------------------------------------------------
# Keyword tier-matching
# ------------------------------------------------------
def match_keywords(text: str):
    """
    Apply tiered keyword logic.

    Tier 1 (TIER1_KEYWORDS) must match at least once
    for the tender to be considered relevant.

    Tier 2 (TIER2_KEYWORDS) are optional additional matches.

    Returns:
        (is_match: bool, tier1_hits: list[str], tier2_hits: list[str])
    """
    text = text.lower()

    tier1_hits = [kw for kw in TIER1_KEYWORDS if kw in text]
    if not tier1_hits:
        return False, [], []

    tier2_hits = [kw for kw in TIER2_KEYWORDS if kw in text]
    return True, tier1_hits, tier2_hits


# ------------------------------------------------------
# Simple fetch helper
# ------------------------------------------------------
def fetch(url: str) -> str | None:
    """Fetch a URL and return HTML text or None on failure."""
    try:
        resp = requests.get(url, timeout=25)
        if resp.status_code == 200:
            return resp.text
        print(f"Fetch failed {url} with status {resp.status_code}")
    except Exception as e:
        print(f"Error fetching {url}: {e}")
    return None


# ------------------------------------------------------
# SCRAPER: UNDP Consultancies (jobs.undp.org)
# ------------------------------------------------------
def scrape_undp_consultancies():
    """
    Scrape UNDP consultancy listings (jobs.undp.org).
    Uses only the listing titles for now.
    """
    base_url = "https://jobs.undp.org"
    url = f"{base_url}/cj_view_consultancies.cfm"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")

    tenders = []

    # Look for rows in the main consultancy table
    rows = soup.find_all("tr")
    for row in rows:
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(strip=True)
        href = link["href"]
        full_url = href if href.startswith("http") else urljoin(base_url, href)

        text_to_check = title.lower()
        is_match, t1, t2 = match_keywords(text_to_check)
        if not is_match:
            continue

        tenders.append({
            "id": full_url,
            "title": title,
            "url": full_url,
            "tier1": t1,
            "tier2": t2,
        })

    return tenders


# ------------------------------------------------------
# SCRAPER: UNDP Procurement Notices (procurement-notices.undp.org)
# ------------------------------------------------------
def scrape_undp_procurement():
    """
    Scrape UNDP Procurement Notices site, including negotiations/notices.
    This is where things like nego_id=40327 live.
    """
    base_url = "https://procurement-notices.undp.org"
    url = f"{base_url}/"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Heuristic: find all links that look like individual notices/negotiations
    for link in soup.find_all("a", href=True):
        href = link["href"]
        # Focus on individual notice / negotiation pages
        if "view_notice.cfm" not in href and "view_negotiation.cfm" not in href:
            continue

        title = link.get_text(strip=True)
        if not title:
            continue

        full_url = href if href.startswith("http") else urljoin(base_url, href)

        is_match, t1, t2 = match_keywords(title.lower())
        if not is_match:
            continue

        tenders.append({
            "id": full_url,
            "title": title,
            "url": full_url,
            "tier1": t1,
            "tier2": t2,
        })

    return tenders


# ------------------------------------------------------
# SCRAPER: ReliefWeb Jobs (filtered by "marine" search)
# ------------------------------------------------------
def scrape_reliefweb():
    """
    Scrape ReliefWeb jobs page using ?search=marine.
    This is a heuristic but tends to concentrate relevant roles.
    """
    base_url = "https://reliefweb.int"
    url = f"{base_url}/jobs?search=marine"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # ReliefWeb job titles usually use this CSS class on <a>
    title_links = soup.select("a.rw-river-article__title-link")

    for link in title_links:
        title = link.get_text(strip=True)
        href = link.get("href")
        if not href or not title:
            continue

        full_url = urljoin(base_url, href)

        is_match, t1, t2 = match_keywords(title.lower())
        if not is_match:
            continue

        tenders.append({
            "id": full_url,
            "title": title,
            "url": full_url,
            "tier1": t1,
            "tier2": t2,
        })

    return tenders


# ------------------------------------------------------
# SCRAPER: World Bank eProcure (HTML table heuristic)
# ------------------------------------------------------
def scrape_world_bank():
    """
    Scrape World Bank eProcure advertisement listing page.
    This is HTML-based and may not see everything if JS is involved,
    but will pick up visible table rows.
    """
    base_url = "https://wbgeprocure-rfxnow.worldbank.org"
    url = f"{base_url}/rfxnow/public/advertisement/index.html"

    html = fetch(url)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    rows = soup.find_all("tr")
    for row in rows:
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(strip=True)
        href = link["href"]
        full_url = href if href.startswith("http") else urljoin(base_url, href)

        is_match, t1, t2 = match_keywords(title.lower())
        if not is_match:
            continue

        tenders.append({
            "id": full_url,
            "title": title,
            "url": full_url,
            "tier1": t1,
            "tier2": t2,
        })

    return tenders


# ------------------------------------------------------
# Build Email Body
# ------------------------------------------------------
def build_email_body(tenders_with_source):
    """
    tenders_with_source: list of (source_name, tender_dict)
    """
    if not tenders_with_source:
        return "No NEW marine/ocean-related tenders found today."

    lines = []
    lines.append("🌊 NEW Marine / Ocean Tender & Consultancy Opportunities")
    lines.append("")

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
# MAIN
# ------------------------------------------------------
def main():
    # Load config and email target
    config = load_config()
    email_to = config["email_to"]

    # Load seen tender IDs (URLs)
    seen = load_seen()
    updated_seen = set(seen)

    all_new_tenders = []

    # List of (source_name, scraper_function)
    sources = [
        ("UNDP Consultancies", scrape_undp_consultancies),
        ("UNDP Procurement Notices", scrape_undp_procurement),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_world_bank),
    ]

    # Run each scraper
    for source_name, scraper in sources:
        try:
            tenders = scraper()
        except Exception as e:
            print(f"Error scraping {source_name}: {e}")
            tenders = []

        for t in tenders:
            tid = t["id"]
            if tid in seen:
                continue  # already reported previously

            all_new_tenders.append((source_name, t))
            updated_seen.add(tid)

    # Build email content
    email_body = build_email_body(all_new_tenders)

    # Send email
    creds = Credentials.from_authorized_user_file("token.json")
    send_email(
        subject="Daily Marine / Ocean Tender Report",
        body=email_body,
        creds=creds,
        email_to=email_to,
    )

    # Save updated seen IDs
    save_seen(updated_seen)


if __name__ == "__main__":
    main()
