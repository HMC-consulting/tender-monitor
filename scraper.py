import yaml
import re
from bs4 import BeautifulSoup
from keywords import KEYWORDS
from utils import fetch_page
from emailer import send_email
from google.oauth2.credentials import Credentials


def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def extract_links(html, base_url):
    """
    Extracts all <a href="..."> links and their text.
    Returns a list of dicts: {"url": full_url, "text": text}
    """
    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = a.get_text(" ", strip=True)

        # Build full URL if relative
        if href.startswith("http"):
            full_url = href
        else:
            # join with base site
            full_url = base_url.rstrip("/") + "/" + href.lstrip("/")

        # Clean text
        cleaned_text = re.sub(r"\s+", " ", text)

        links.append({"url": full_url, "text": cleaned_text})

    return links


def keyword_match(text, keywords):
    """
    Returns list of matching keywords within the text (case insensitive).
    """
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def scan_site_for_tenders(url, keywords):
    """
    Fetches the site, extracts all links, and checks for keyword matches.
    Returns list of tender records: [{"title": ..., "url": ..., "matches": [...]}, ...]
    """
    html = fetch_page(url)
    links = extract_links(html, url)

    tenders = []

    for link in links:
        matches = keyword_match(link["text"], keywords)

        if matches:
            tenders.append({
                "title": link["text"] or "(no title)",
                "url": link["url"],
                "matches": matches
            })

    return tenders


def build_email_body(results):
    """
    Creates a clean, readable email summarizing all found tenders.
    """
    if not results:
        return "No matching tenders found today."

    body = "🌊 Daily Tender Opportunities Report\n\n"

    for site, tenders in results.items():
        body += f"📌 Source: {site}\n"

        for t in tenders:
            body += f"\n🔹 {t['title']}\n"
            body += f"   ➤ {t['url']}\n"
            body += f"   🔍 Matched keywords: {', '.join(t['matches'])}\n"

        body += "\n" + ("-" * 50) + "\n\n"

    return body


def main():
    # Load configuration
    config = load_config()
    email_to = config["email_to"]
    sites = config["sites"]

    results = {}

    # Scan sites for tenders
    for site in sites:
        tenders = scan_site_for_tenders(site, KEYWORDS)
        if tenders:
            results[site] = tenders

    # Build email body
    email_body = build_email_body(results)

    # Load Gmail credentials
    creds = Credentials.from_authorized_user_file("token.json")

    # Send email
    send_email(
        subject="Daily Tender Report",
        body=email_body,
        creds=creds,
        email_to=email_to
    )


if __name__ == "__main__":
    main()
