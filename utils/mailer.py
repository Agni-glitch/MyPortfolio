import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from core.config import get_settings

log = logging.getLogger(__name__)


def _send_sync(to: str, subject: str, text: str, html: str | None, reply_to: str | None) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = f"{s.site_name} <{s.smtp_email}>"
    msg["To"] = to
    msg["Subject"] = subject
    if reply_to:
        msg["Reply-To"] = reply_to
    msg.set_content(text)
    if html:
        msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if s.smtp_port == 465:
        with smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, context=ctx, timeout=15) as server:
            server.login(s.smtp_email, s.smtp_password)
            server.send_message(msg)
    else:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
            server.starttls(context=ctx)
            server.login(s.smtp_email, s.smtp_password)
            server.send_message(msg)


async def send_email(to: str, subject: str, text: str, html: str | None = None, reply_to: str | None = None) -> bool:
    if not get_settings().smtp_password:
        log.warning("SMTP not configured; email to %s not sent", to)
        return False
    try:
        await asyncio.to_thread(_send_sync, to, subject, text, html, reply_to)
        return True
    except Exception:
        log.exception("Failed to send email to %s", to)
        return False


async def send_otp_email(to: str, code: str, ttl_minutes: int) -> bool:
    s = get_settings()
    text = (
        f"Your {s.site_name} admin password reset code is: {code}\n\n"
        f"It expires in {ttl_minutes} minutes. If you didn't request this, ignore this email."
    )
    html = f"""
    <div style="font-family:system-ui,sans-serif;max-width:480px;margin:auto">
      <h2>Password reset</h2>
      <p>Your verification code:</p>
      <p style="font-size:32px;font-weight:700;letter-spacing:8px">{code}</p>
      <p style="color:#666">Expires in {ttl_minutes} minutes. If you didn't request this, ignore this email.</p>
    </div>"""
    return await send_email(to, f"{s.site_name}: your reset code", text, html)
