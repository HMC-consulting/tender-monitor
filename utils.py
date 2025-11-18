import requests
from bs4 import BeautifulSoup

def fetch_page(url):
    """
    Fetch a webpage safely with timeout and user-agent.
    Returns the HTML text or None.
    """
    try:
        response = requests.get(
            url,
            timeout=20,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        response.raise_for_status()
        return response.text
    except Exception:
        return None

def extract_text(html):
    """
    Convert HTML into plain lowercase text for keyword searching.
    """
    if not html:
        return ""
    soup = BeautifulSoup(html, "lxml")
    return soup.get_text(" ", strip=True).lower()
