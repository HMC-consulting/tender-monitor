from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def send_email(subject, body_html, body_text, creds: Credentials, email_to):
    """
    Sends a multipart (HTML + plain text) email using Gmail API.
    """

    service = build("gmail", "v1", credentials=creds)

    message = MIMEMultipart("alternative")
    message["To"] = email_to
    message["Subject"] = subject

    # Add text + HTML versions
    part1 = MIMEText(body_text, "plain")
    part2 = MIMEText(body_html, "html")

    message.attach(part1)
    message.attach(part2)

    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()
