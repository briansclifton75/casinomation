from __future__ import annotations

import email
import imaplib
import os
import re
from email.header import decode_header
from email.message import Message
from typing import Iterable


def _decode_mime(value: str | None) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    decoded: list[str] = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            decoded.append(chunk.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(chunk)
    return "".join(decoded)


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _message_body(msg: Message) -> str:
    if msg.is_multipart():
        text_parts: list[str] = []
        html_parts: list[str] = []
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition", ""))
            if "attachment" in disp.lower():
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            value = payload.decode(charset, errors="replace")
            if ctype == "text/plain":
                text_parts.append(value)
            elif ctype == "text/html":
                html_parts.append(value)
        if text_parts:
            return "\n".join(text_parts)
        if html_parts:
            return _strip_html("\n".join(html_parts))
        return ""

    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    body = payload.decode(charset, errors="replace")
    if msg.get_content_type() == "text/html":
        return _strip_html(body)
    return body


class GmailPromoIngestor:
    def __init__(self) -> None:
        self.host = os.getenv("CASINOMATION_IMAP_HOST", "imap.gmail.com")
        self.port = int(os.getenv("CASINOMATION_IMAP_PORT", "993"))
        self.user = os.getenv("CASINOMATION_IMAP_USER", "")
        self.password = os.getenv("CASINOMATION_IMAP_APP_PASSWORD", "")
        raw_allowlist = os.getenv("CASINOMATION_EMAIL_ALLOWLIST", "")
        self.allowlist = {x.strip().lower() for x in raw_allowlist.split(",") if x.strip()}

    def configured(self) -> bool:
        return bool(self.user and self.password)

    def fetch_recent(self, max_messages: int = 20) -> Iterable[dict[str, str]]:
        if not self.configured():
            return []

        with imaplib.IMAP4_SSL(self.host, self.port) as mail:
            mail.login(self.user, self.password)
            mail.select("INBOX")
            status, data = mail.search(None, "ALL")
            if status != "OK":
                return []

            ids = [x for x in data[0].split() if x][-max_messages:]
            results: list[dict[str, str]] = []

            for msg_id in reversed(ids):
                res, msg_data = mail.fetch(msg_id, "(RFC822)")
                if res != "OK" or not msg_data:
                    continue

                raw_email = msg_data[0][1]
                if not raw_email:
                    continue

                msg = email.message_from_bytes(raw_email)
                sender = _decode_mime(msg.get("From"))
                sender_l = sender.lower()
                if self.allowlist and not any(a in sender_l for a in self.allowlist):
                    continue

                message_id = _decode_mime(msg.get("Message-ID")) or f"imap-{msg_id.decode()}"
                subject = _decode_mime(msg.get("Subject"))
                body = _message_body(msg)

                results.append(
                    {
                        "message_id": message_id.strip(),
                        "sender": sender.strip(),
                        "subject": subject.strip(),
                        "body": body.strip(),
                    }
                )

            return results
