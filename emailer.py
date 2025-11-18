from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def send_email(subject, body_html, body_text, creds: Credentials, email_to):
    """
    Sends a multipart (HTML + plain text) email using Gmail API.
    """

    # Build Gmail API client
    service = build("gmail", "v1", credentials=creds)

    # Create email container
    message = MIMEMultipart("alternative")
    message["To"] = email_to
    message["Subject"] = subject

    # Add text + HTML versions
    part_text = MIMEText(body_text, "plain")
    part_html = MIMEText(body_html, "html")

    message.attach(part_text)
    message.attach(part_html)

    # Gmail API requires base64url encoded bytes
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")

    # Send email
    service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()
