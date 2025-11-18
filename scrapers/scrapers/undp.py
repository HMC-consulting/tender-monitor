# scrapers/undp.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
from utils import fetch_page, extract_text


UNDP_URL = "https://jobs.undp.org/cj_view_consultancies.cfm"


def _keyword_match(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def scrape_undp_consultancies(keywords):
    """
    Scrape UNDP consultancies listing, follow each item link,
    and filter using keywords on title + description.
    Returns list of tender dicts.
    """
    html = fetch_page(UNDP_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Heuristic: look at all table rows that have a link
    for row in soup.find_all("tr"):
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            continue

        href = urljoin(UNDP_URL, link["href"])

        # Try to find deadline in the same row
        deadline = None
        cells = row.find_all("td")
        for cell in cells:
            text = cell.get_text(" ", strip=True)
            if any(word in text.lower() for word in ["deadline", "closing", "until"]):
                deadline = text
                break

        # Fetch detail page and extract text
        detail_html = fetch_page(href)
        full_text = ""
        if detail_html:
            full_text = extract_text(detail_html) or ""

        text_to_search = (title + "\n" + full_text)
        matches = _keyword_match(text_to_search, keywords)

        if matches:
            summary = full_text[:400].replace("\n", " ").strip() if full_text else ""

            tenders.append({
                "source": "UNDP Consultancies",
                "title": title,
                "url": href,
                "deadline": deadline,
                "summary": summary,
                "matches": matches,
            })

    return tenders
