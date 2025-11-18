# scrapers/worldbank.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
from utils import fetch_page, extract_text


WORLD_BANK_URL = "https://wbgeprocure-rfxnow.worldbank.org/rfxnow/public/advertisement/index.html"


def _keyword_match(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def scrape_worldbank(keywords):
    """
    Scrape World Bank eProcure advertisement page for opportunities
    and filter them by keywords (title + description text).
    Returns a list of dicts:
      { "source": "...", "title": "...", "url": "...", "deadline": "...", "summary": "...", "matches": [...] }
    """
    html = fetch_page(WORLD_BANK_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Heuristic: look for table rows with links that look like adverts
    rows = soup.find_all("tr")
    for row in rows:
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            continue

        href = urljoin(WORLD_BANK_URL, link["href"])

        # Try to pull a deadline or date from the same row (best-effort)
        deadline = None
        cells = row.find_all("td")
        for cell in cells:
            text = cell.get_text(" ", strip=True)
            if any(word in text.lower() for word in ["closing", "deadline", "due date"]):
                deadline = text
                break

        # Fetch detail page to scan full text
        detail_html = fetch_page(href)
        full_text = ""
        if detail_html:
            full_text = extract_text(detail_html) or ""
        text_to_search = (title + "\n" + full_text)
        matches = _keyword_match(text_to_search, keywords)

        if matches:
            # Optional: short summary snippet from full text
            summary = full_text[:400].replace("\n", " ").strip() if full_text else ""

            tenders.append({
                "source": "World Bank eProcure",
                "title": title,
                "url": href,
                "deadline": deadline,
                "summary": summary,
                "matches": matches,
            })

    return tenders
