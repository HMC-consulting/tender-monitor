# scrapers/reliefweb.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
from utils import fetch_page, extract_text


RELIEFWEB_URL = "https://reliefweb.int/jobs?search=marine"


def _keyword_match(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def scrape_reliefweb_jobs(keywords):
    """
    Scrape ReliefWeb job listings (marine search), follow each job link
    and filter by keywords in title + description.
    Returns list of tender dicts.
    """
    html = fetch_page(RELIEFWEB_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Heuristic: job cards often live under <h3><a> structures
    for h3 in soup.find_all("h3"):
        link = h3.find("a", href=True)
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            continue

        href = urljoin(RELIEFWEB_URL, link["href"])

        # Try to grab a nearby summary snippet from sibling div
        summary = ""
        summary_div = h3.find_next_sibling("div")
        if summary_div:
            summary = summary_div.get_text(" ", strip=True)

        # Fetch detail page for fuller text (best-effort)
        detail_html = fetch_page(href)
        full_text = ""
        if detail_html:
            full_text = extract_text(detail_html) or ""

        text_to_search = (title + "\n" + summary + "\n" + full_text)
        matches = _keyword_match(text_to_search, keywords)

        if matches:
            # Prefer full_text for summary, but fall back to local snippet
            if full_text:
                short_summary = full_text[:400].replace("\n", " ").strip()
            else:
                short_summary = summary

            tenders.append({
                "source": "ReliefWeb Jobs (marine)",
                "title": title,
                "url": href,
                "deadline": None,  # could be improved later
                "summary": short_summary,
                "matches": matches,
            })

    return tenders
