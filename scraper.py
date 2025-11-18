import yaml
from keywords import KEYWORDS
from utils import fetch_page, extract_text
from emailer import send_email
from google.oauth2.credentials import Credentials


def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def scan_site(url, keywords):
    """
    Fetches a webpage, extracts text, and checks for keyword matches.
    Returns a list of matched keywords.
    """
    html = fetch_page(url)
    text = extract_text(html)
    matches = [kw for kw in keywords if kw.lower() in text]
    return matches


def main():
    # Load configuration
    config = load_config()
    email_to = config["email_to"]
    sites = config["sites"]

    results = {}

    # Scan every site
    for site in sites:
        matches = scan_site(site, KEYWORDS)
        if matches:
            results[site] = matches

    # Build email body
    if not results:
        email_body = "No matching tenders found today."
    else:
        email_body = "Daily Tender Report\n\n"
        for site, matches in results.items():
            email_body += f"\nSITE: {site}\n"
            for match in matches:
                email_body += f"  - {match}\n"

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
