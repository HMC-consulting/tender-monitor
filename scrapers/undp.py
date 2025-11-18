# scrapers/undp.py

from urllib.parse import urljoin
from bs4 import BeautifulSoup
from utils import fetch_page, extract_text

# Two entry URLs for UNDP:
UNDP_CONSULT_URL = "https://jobs.undp.org/cj_view_consultancies.cfm"
UNDP_PROC_URL    = "https://procurement-notices.undp.org/"

def _keyword_match(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]

def scrape_undp_procurement_notices(keywords):
    """
    Scrape UNDP procurement-notices site, following individual adverts,
    and filter using keywords in title + description.
    """
    html = fetch_page(UNDP_PROC_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    # Look for links of negotiation or procurement pages
    for link in soup.find_all("a", href=True):
        href = link["href"].strip()
        title = link.get_text(" ", strip=True)
        if not title:
            continue

        # Only process links that follow the format view_negotiation or view_procurement
        if "view_negotiation" in href or "view_procurement" in href or "view_notice" in href:
            full_url = urljoin(UNDP_PROC_URL, href)

            # Fetch detail page
            detail_html = fetch_page(full_url)
            full_text = ""
            if detail_html:
                full_text = extract_text(detail_html) or ""

            text_to_search = (title + "\n" + full_text)
            matches = _keyword_match(text_to_search, keywords)

            if matches:
                # Try to find deadline
                deadline = None
                # quick heuristic: look for date formats in full_text
                # (can extend later)

                summary = full_text[:400].replace("\n", " ").strip()

                tenders.append({
                    "source": "UNDP Procurement Notices",
                    "title": title,
                    "url": full_url,
                    "deadline": deadline,
                    "summary": summary,
                    "matches": matches,
                })

    return tenders

def scrape_undp_consultancies(keywords):
    """
    Scrape UNDP consultancies listing, follow each item link,
    and filter using keywords on title + description.
    Returns list of tender dicts.
    """
    html = fetch_page(UNDP_CONSULT_URL)
    if not html:
        return []

    soup = BeautifulSoup(html, "html.parser")
    tenders = []

    for row in soup.find_all("tr"):
        link = row.find("a", href=True)
        if not link:
            continue

        title = link.get_text(" ", strip=True)
        if not title:
            continue

        href = urljoin(UNDP_CONSULT_URL, link["href"])

        deadline = None
        cells = row.find_all("td")
        for cell in cells:
            text = cell.get_text(" ", strip=True)
            if any(word in text.lower() for word in ["deadline", "closing", "until"]):
                deadline = text
                break

        detail_html = fetch_page(href)
        full_text = ""
        if detail_html:
            full_text = extract_text(detail_html) or ""

        text_to_search = (title + "\n" + full_text)
        matches = _keyword_match(text_to_search, keywords)

        if matches:
            summary = full_text[:400].replace("\n", " ").strip()

            tenders.append({
                "source": "UNDP Consultancies",
                "title": title,
                "url": href,
                "deadline": deadline,
                "summary": summary,
                "matches": matches,
            })

    return tenders
