import json
import os
import yaml
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

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
# HTTP helpers
# ------------------------------------------------------
def fetch(url: str) -> str | None:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (TenderMonitorBot)"}
        resp = requests.get(url, headers=headers, timeout=30)
        if resp.status_code == 200:
            return resp.text
        else:
            print(f"❌ Fetch {url} returned status {resp.status_code}")
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
    return None


def fetch_many(urls, max_workers=8):
    """
    Fetch many URLs in parallel. Returns dict {url: html_or_None}.
    """
    results = {}
    unique_urls = list(dict.fromkeys(urls))  # dedupe, preserve order

    def _fetch_one(u):
        return u, fetch(u)

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(_fetch_one, u): u for u in unique_urls}
        for future in as_completed(future_to_url):
            try:
                url, html = future.result()
                results[url] = html
            except Exception as e:
                url = future_to_url[future]
                print(f"❌ Error in fetch_many for {url}: {e}")
                results[url] = None

    return results


# ------------------------------------------------------
# UNDP CONSULTANCIES — PAGINATED + PARALLEL DETAIL FETCH
# ------------------------------------------------------
def scrape_undp_consultancies():
    base_url = "https://jobs.undp.org"
    max_pages = 3  # Fast mode
    jobs = []

    for page in range(1, max_pages + 1):
        url = f"{base_url}/cj_view_consultancies.cfm?cur_page={page}"
        html = fetch(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            break

        page_found = False

        for row in rows:
            link = row.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title:
                continue

            full_url = urljoin(base_url, link["href"])
            jobs.append({"title": title, "url": full_url})
            page_found = True

        if not page_found:
            break

    # Fetch detail pages in parallel
    url_list = [j["url"] for j in jobs]
    html_map = fetch_many(url_list, max_workers=8)

    tenders = []
    for job in jobs:
        title = job["title"]
        url = job["url"]
        detail_html = html_map.get(url)
        if not detail_html:
            continue

        detail_soup = BeautifulSoup(detail_html, "html.parser")
        full_text = detail_soup.get_text(" ", strip=True).lower()
        combined = f"{title.lower()} {full_text}"

        match, t1, t2 = match_keywords(combined)
        if match:
            tenders.append({
                "id": url,
                "title": title,
                "url": url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# UNDP PROCUREMENT NOTICES — PAGINATED + PARALLEL DETAIL FETCH
# ------------------------------------------------------
def scrape_undp_procurement():
    base_url = "https://procurement-notices.undp.org"
    max_pages = 3  # Fast mode
    items = []

    for page in range(1, max_pages + 1):
        url = f"{base_url}/index.cfm?cur_page={page}"
        html = fetch(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        links = soup.find_all("a", href=True)
        if not links:
            break

        page_found = False

        for link in links:
            href = link["href"]
            if "view_notice" not in href and "view_negotiation" not in href:
                continue

            title = link.get_text(strip=True)
            if not title:
                continue

            full_url = urljoin(base_url, href)
            items.append({"title": title, "url": full_url})
            page_found = True

        if not page_found:
            break

    # Fetch detail pages in parallel
    url_list = [i["url"] for i in items]
    html_map = fetch_many(url_list, max_workers=8)

    tenders = []
    for item in items:
        title = item["title"]
        url = item["url"]
        detail_html = html_map.get(url)
        if not detail_html:
            continue

        detail_soup = BeautifulSoup(detail_html, "html.parser")
        full_text = detail_soup.get_text(" ", strip=True).lower()
        combined = f"{title.lower()} {full_text}"

        match, t1, t2 = match_keywords(combined)
        if match:
            tenders.append({
                "id": url,
                "title": title,
                "url": url,
                "tier1": t1,
                "tier2": t2
            })

    return tenders


# ------------------------------------------------------
# RELIEFWEB — HTML LISTING + FULL DETAIL PAGES (LIMITED PAGES)
# ------------------------------------------------------
def scrape_reliefweb():
    base_url = "https://reliefweb.int"
    max_pages = 3  # Fast mode
    jobs = []

    # ReliefWeb paginates as /jobs, /jobs?page=1, /jobs?page=2, etc.
    for page in range(0, max_pages):
        if page == 0:
            url = f"{base_url}/jobs"
        else:
            url = f"{base_url}/jobs?page={page}"

        html = fetch(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        links = soup.select("a.rw-river-article__title-link")
        if not links:
            break

        page_found = False

        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href")
            if not title or not href:
                continue

            full_url = urljoin(base_url, href)
            jobs.append({"title": title, "url": full_url})
            page_found = True

        if not page_found:
            break

    # Fetch job pages in parallel
    url_list = [j["url"] for j in jobs]
    html_map = fetch_many(url_list, max_workers=8)

    tenders = []
    for job in jobs:
        title = job["title"]
        url = job["url"]
        page_html = html_map.get(url)
        if not page_html:
            continue

        page_soup = BeautifulSoup(page_html, "html.parser")

        # Try several possible containers for job body
        body_container = (
            page_soup.select_one("div.rw-job__body")
            or page_soup.select_one("div.rw-article__content")
            or page_soup.select_one("section.rw-article__body")
        )

        full_text = title.lower()
        if body_container:
            full_text += " " + body_container.get_text(" ", strip=True).lower()
        else:
            full_text += " " + page_soup.get_text(" ", strip=True).lower()

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
# WORLD BANK — PAGINATION LIMITED + PARALLEL DETAIL FETCH
# ------------------------------------------------------
def scrape_world_bank():
    """
    World Bank eProcure — best-effort HTML scraper.
    JavaScript-heavy, so we cap to a few pages for speed.
    """
    base_url = "https://wbgeprocure-rfxnow.worldbank.org"
    max_pages = 3  # Fast mode
    items = []

    for page in range(1, max_pages + 1):
        url = f"{base_url}/rfxnow/public/advertisement/index.html?page={page}"
        html = fetch(url)
        if not html:
            break

        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all("tr")
        if not rows:
            break

        page_found = False

        for row in rows:
            link = row.find("a", href=True)
            if not link:
                continue

            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                continue

            href = link["href"]
            full_url = urljoin(base_url, href)

            items.append({"title": title, "url": full_url})
            page_found = True

        if not page_found:
            break

    # Fetch detail pages in parallel
    url_list = [i["url"] for i in items]
    html_map = fetch_many(url_list, max_workers=6)

    tenders = []
    for item in items:
        title = item["title"]
        url = item["url"]
        detail_html = html_map.get(url)
        if not detail_html:
            continue

        detail_soup = BeautifulSoup(detail_html, "html.parser")
        text_block = detail_soup.get_text(" ", strip=True).lower()
        combined = f"{title.lower()} {text_block}"

        match, t1, t2 = match_keywords(combined)
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
# Build Email (HTML + Text versions)
# ------------------------------------------------------
def build_email_bodies(tenders_with_source):
    # Plain text
    if not tenders_with_source:
        body_text = "No NEW marine/ocean-related tenders found today."
    else:
        lines = ["NEW Marine / Ocean Opportunities\n"]
        current_source = None
        for source, t in tenders_with_source:
            if source != current_source:
                lines.append(f"\n{source}")
                lines.append("-" * len(source))
                current_source = source

            lines.append(f"- {t['title']}")
            lines.append(f"  {t['url']}")
            if t["tier1"]:
                lines.append(f"  Tier 1: {', '.join(t['tier1'])}")
            if t["tier2"]:
                lines.append(f"  Tier 2: {', '.join(t['tier2'])}")
        body_text = "\n".join(lines)

    # HTML
    if not tenders_with_source:
        body_html = """
        <html><body>
        <h2 style="color:#004080;">No NEW marine/ocean-related tenders found today.</h2>
        </body></html>
        """
        return body_html, body_text

    html = []
    html.append("""
    <html>
    <body style="font-family:Arial, sans-serif; font-size:14px; color:#333;">
    <h2 style="color:#004080; margin-bottom:20px;">
        🌊 New Marine / Ocean Opportunities
    </h2>
    """)

    current_source = None
    for source, t in tenders_with_source:
        if source != current_source:
            html.append(f"""
            <h3 style="color:#0066aa; margin-top:30px; margin-bottom:5px;">
                {source}
            </h3>
            <hr style="border:0; border-top:1px solid #ccc; margin-bottom:20px;">
            """)
            current_source = source

        html.append(f"""
            <div style="margin-bottom:25px;">
                <div style="font-size:15px; font-weight:bold; margin-bottom:6px;">
                    {t['title']}
                </div>
                <div style="margin-bottom:6px;">
                    <a href="{t['url']}" style="color:#1a73e8;">View Opportunity</a>
                </div>
        """)

        if t["tier1"]:
            html.append(f"""
                <div style="font-size:12px; color:#006600; margin-bottom:4px;">
                    <strong>Tier 1:</strong> {', '.join(t['tier1'])}
                </div>
            """)

        if t["tier2"]:
            html.append(f"""
                <div style="font-size:12px; color:#444;">
                    <strong>Tier 2:</strong> {', '.join(t['tier2'])}
                </div>
            """)

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

    seen = load_seen()
    updated_seen = set(seen)
    new_items = []

    sources = [
        ("UNDP Consultancies", scrape_undp_consultancies),
        ("UNDP Procurement Notices", scrape_undp_procurement),
        ("ReliefWeb", scrape_reliefweb),
        ("World Bank eProcure", scrape_world_bank),
    ]

    # Run scrapers sequentially (each one uses parallel detail fetching)
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
        email_to=email_to,
    )

    save_seen(updated_seen)


if __name__ == "__main__":
    main()
