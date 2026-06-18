import os
import smtplib
import mimetypes
from email.message import EmailMessage
from pathlib import Path
from typing import Dict, List, Optional

from src.story_image import image_mime_parts
from src.story_storage import log_email_status


PLACEHOLDER_VALUES = {
    "your_email@gmail.com",
    "your_16_character_app_password",
    "your_password",
    "your_smtp_username",
    "your_smtp_password",
}


def _env_value(name: str) -> str:
    value = os.getenv(name, "").strip()
    return "" if value.lower() in PLACEHOLDER_VALUES else value


def _real_email_config() -> Dict[str, str]:
    gmail_address = _env_value("GMAIL_ADDRESS")
    gmail_app_password = _env_value("GMAIL_APP_PASSWORD")
    smtp_host = _env_value("SMTP_HOST") or ("smtp.gmail.com" if gmail_address else "")
    smtp_port = _env_value("SMTP_PORT") or "587"
    smtp_user = _env_value("SMTP_USERNAME") or gmail_address
    smtp_password = _env_value("SMTP_PASSWORD") or gmail_app_password
    from_email = _env_value("STORY_AGENT_FROM_EMAIL") or smtp_user

    return {
        "smtp_host": smtp_host,
        "smtp_port": smtp_port,
        "smtp_user": smtp_user,
        "smtp_password": smtp_password,
        "from_email": from_email,
        "gmail_address": gmail_address,
        "gmail_app_password": gmail_app_password,
    }


def get_email_mode() -> str:
    if os.getenv("STORY_AGENT_MOCK_EMAIL", "true").lower() == "true":
        return "mock"

    config = _real_email_config()
    if config["gmail_address"] and config["gmail_app_password"]:
        return "gmail_smtp"
    if config["smtp_host"] and config["smtp_user"] and config["smtp_password"]:
        return "smtp"
    return "missing_smtp_config"


def send_story_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    story_id: str,
    approved: bool,
    html_body: Optional[str] = None,
    inline_image_path: Optional[str] = None,
    attachment_paths: Optional[List[str]] = None,
) -> Dict[str, str]:
    """Send the approved story or log a mock send when SMTP is not configured."""
    attachments = [Path(path) for path in attachment_paths or []]
    existing_attachments = [path for path in attachments if path.exists()]
    missing_attachments = [str(path) for path in attachments if not path.exists()]
    attachment_names = [path.name for path in existing_attachments]

    if not approved:
        result = {
            "status": "blocked",
            "message": "Parent approval is required before sending.",
            "story_id": story_id,
        }
        log_email_status(result)
        return result

    mock_email = os.getenv("STORY_AGENT_MOCK_EMAIL", "true").lower() == "true"
    config = _real_email_config()
    smtp_host = config["smtp_host"]
    smtp_port = int(config["smtp_port"])
    smtp_user = config["smtp_user"]
    smtp_password = config["smtp_password"]
    from_email = config["from_email"]

    if mock_email:
        result = {
            "status": "mock_sent",
            "message": "Email was logged in mock mode. Set STORY_AGENT_MOCK_EMAIL=false and configure SMTP to send real email.",
            "story_id": story_id,
            "to": to_email,
            "subject": subject,
            "email_mode": get_email_mode(),
            "attachments": ",".join(str(path) for path in existing_attachments),
            "attachment_names": ",".join(attachment_names),
            "attachment_count": str(len(existing_attachments)),
            "missing_attachments": ",".join(missing_attachments),
        }
        log_email_status({**result, "body_preview": body[:500], "html_preview": (html_body or "")[:500]})
        return result

    missing = [
        name
        for name, value in {
            "SMTP host": smtp_host,
            "SMTP username or Gmail address": smtp_user,
            "SMTP password or Gmail app password": smtp_password,
            "From email": from_email,
        }.items()
        if not value
    ]
    if missing:
        result = {
            "status": "failed_config",
            "message": "Real email is enabled, but email configuration is incomplete: " + ", ".join(missing) + ".",
            "story_id": story_id,
            "to": to_email,
            "email_mode": get_email_mode(),
            "attachments": ",".join(str(path) for path in existing_attachments),
            "attachment_names": ",".join(attachment_names),
            "attachment_count": str(len(existing_attachments)),
            "missing_attachments": ",".join(missing_attachments),
        }
        log_email_status(result)
        return result

    msg = EmailMessage()
    msg["From"] = from_email
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    if html_body:
        msg.add_alternative(html_body, subtype="html")
        if inline_image_path:
            image_path = Path(inline_image_path)
            if image_path.exists():
                maintype, subtype = image_mime_parts(str(image_path))
                html_part = msg.get_payload()[-1]
                html_part.add_related(
                    image_path.read_bytes(),
                    maintype=maintype,
                    subtype=subtype,
                    cid="<story-illustration>",
                )
    for path in existing_attachments:
        mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        maintype, subtype = mime_type.split("/", 1)
        msg.add_attachment(
            path.read_bytes(),
            maintype=maintype,
            subtype=subtype,
            filename=path.name,
        )

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=20) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)
    except Exception as exc:
        result = {
            "status": "failed",
            "message": str(exc),
            "story_id": story_id,
            "to": to_email,
            "email_mode": get_email_mode(),
        }
        log_email_status(result)
        return result

    result = {
        "status": "sent",
        "message": "Email sent successfully.",
        "story_id": story_id,
        "to": to_email,
        "subject": subject,
        "email_mode": get_email_mode(),
        "attachments": ",".join(str(path) for path in existing_attachments),
        "attachment_names": ",".join(attachment_names),
        "attachment_count": str(len(existing_attachments)),
        "missing_attachments": ",".join(missing_attachments),
    }
    log_email_status(result)
    return result


def format_story_email(
    *,
    child_name: str,
    title: str,
    theme: str,
    story_text: str,
    parent_note: Optional[str] = None,
) -> str:
    note = parent_note or f"Tonight's story focuses on {theme}."
    return (
        f"Hi,\n\n"
        f"Here is today's personalized story for {child_name}.\n\n"
        f"{title}\n\n"
        f"{story_text}\n\n"
        f"Parent note: {note}\n"
    )


def format_story_email_html(
    *,
    child_name: str,
    title: str,
    theme: str,
    story_text: str,
    parent_note: Optional[str] = None,
    illustration_url: Optional[str] = None,
    illustration_cid: Optional[str] = None,
) -> str:
    import html

    note = parent_note or f"Tonight's story focuses on {theme}."
    paragraphs = "".join(
        f"<p>{html.escape(part.strip())}</p>"
        for part in story_text.split("\n")
        if part.strip()
    )
    image_block = ""
    if illustration_url:
        safe_url = html.escape(illustration_url, quote=True)
        image_block = (
            f'<p><img src="{safe_url}" alt="Story illustration" '
            'style="width:220px;max-width:100%;height:auto;border-radius:12px;margin:16px 0;display:block;" /></p>'
        )
    elif illustration_cid:
        safe_cid = html.escape(illustration_cid, quote=True)
        image_block = (
            f'<p><img src="cid:{safe_cid}" alt="Story illustration" '
            'style="width:220px;max-width:100%;height:auto;border-radius:12px;margin:16px 0;display:block;" /></p>'
        )

    return f"""<!doctype html>
<html>
  <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2933;">
    <p>Hi,</p>
    <p>Here is today's personalized story for {html.escape(child_name)}.</p>
    {image_block}
    <h2>{html.escape(title)}</h2>
    {paragraphs}
    <p><strong>Parent note:</strong> {html.escape(note)}</p>
  </body>
</html>"""
