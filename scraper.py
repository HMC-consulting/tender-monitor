import yaml
from google.oauth2.credentials import Credentials

from keywords import KEYWORDS
from emailer import send_email

from scrapers.worldbank import scrape_worldbank
from scrapers.undp import (
    scrape_undp_consultancies,
    scrape_undp_procurement_notices,
)
from scrapers.reliefweb import scrape_reliefweb_jobs

from history import load_history, save_history, filter_new_tenders


def load_config():
    with open("config.yaml", "r") as f:
        return yaml.safe_load(f)


def build_email_body(tenders):
    """
    Build a concise, human-readable email listing real opportunities only.
    Expected tender dict fields:
      source, title, url, deadline (optional), summary (optional), matches (list)
    """
    if not tenders:
        return "No NEW matching tenders or consultancy opportunities found today."

    # Group by source
    by_source = {}
    for t in tenders:
        src = t.get("source", "Unknown source")
        by_source.setdefault(src, []).append(t)

    lines = []
    lines.append("🌊 Daily Tender & Consultancy Opportunities Report (NEW items only)\n")

    for source, items in by_source.items():
        lines.append(f"\n📌 {source}\n" + "-" * (4 + len(source)))

        for t in items:
            title = t.get("title", "(no title)")
            url = t.get("url", "")
            deadline = t.get("deadline")
            matches = t.get("matches", [])

            lines.append(f"\n🔹 {title}")
            if url:
                lines.append(f"   ➤ {url}")
            if deadline:
                lines.append(f"   📅 Deadline: {deadline}")
            if matches:
                lines.append(f"   🔍 Matched keywords: {', '.join(matches)}")

    return "\n".join(lines)


def main():
    # Load config for email target
    config = load_config()
    email_to = config["email_to"]

    # 1) Collect all raw tenders from all sites
    all_tenders = []

    # World Bank eProcure
    wb_tenders = scrape_worldbank(KEYWORDS)
    all_tenders.extend(wb_tenders)

    # UNDP Consultancies (jobs.undp.org)
    undp_consult_tenders = scrape_undp_consultancies(KEYWORDS)
    all_tenders.extend(undp_consult_tenders)

    # UNDP Procurement Notices (procurement-notices.undp.org)
    undp_proc_tenders = scrape_undp_procurement_notices(KEYWORDS)
    all_tenders.extend(undp_proc_tenders)

    # ReliefWeb Jobs (we'll assume scrapers.reliefweb handles the right URL)
    reliefweb_tenders = scrape_reliefweb_jobs(KEYWORDS)
    all_tenders.extend(reliefweb_tenders)

    # 2) Load history and filter out already-seen tenders
    history = load_history()
    new_tenders = filter_new_tenders(all_tenders, history)

    # 3) Build email body from new items only
    email_body = build_email_body(new_tenders)

    # 4) Save updated history (so future runs know what we've seen)
    save_history(history)

    # 5) Load Gmail credentials
    creds = Credentials.from_authorized_user_file("token.json")

    # 6) Send email
    send_email(
        subject="Daily Tender & Consultancy Report",
        body=email_body,
        creds=creds,
        email_to=email_to,
    )


if __name__ == "__main__":
    main()
