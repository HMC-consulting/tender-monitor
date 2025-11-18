import base64
from email.mime.text import MIMEText
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials


def send_email(subject, body, creds, email_to):
    """
    Sends an email using the Gmail API.
    """

    # Gmail API service
    service = build("gmail", "v1", credentials=creds)

    # Create MIME email
    message = MIMEText(body, "plain")
    message["to"] = email_to
    message["subject"] = subject

    # Encode in base64
    raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

    # Send the email
    service.users().messages().send(
        userId="me",
        body={"raw": raw_message}
    ).execute()
