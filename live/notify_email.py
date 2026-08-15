"""Send email for potions job summaries (plain + HTML multipart).

This host blocks outbound SMTP (ports 25/465/587 time out). Prefer HTTPS:

1. **Gmail Apps Script webhook** (keeps From = your Gmail) — recommended
2. **Resend** REST API (``RESEND_API_KEY``) if you have an account
3. Gmail SMTP app-password — only works if the network allows smtp.gmail.com:587

All transports send multipart plain+HTML. If ``html`` is omitted, it is rendered
from the plain body via ``live.format_email.plain_to_html``.

Credentials in gitignored ``.env.notify`` (see ``.env.notify.example``).
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import smtplib
import ssl
import subprocess
import urllib.error
import urllib.request
from email.message import EmailMessage
from pathlib import Path
from typing import List, Optional, Sequence, Union

AttachmentPath = Union[str, Path]

REPO = Path(__file__).resolve().parents[1]
ENV_CANDIDATES = (
    REPO / ".env.cursor",
    REPO / ".env.resend",
    REPO / ".env.notify",
    REPO / "live" / ".env.notify",
    Path.home() / ".config" / "potions" / "notify.env",
)


def load_notify_env() -> None:
    # Load all candidates (earlier files win for a given key).
    for path in ENV_CANDIDATES:
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val


def _truncate(body: str, limit: int = 100_000) -> str:
    if len(body) <= limit:
        return body
    return body[:limit] + "\n\n…[truncated]\n"


def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _https_json_curl(url: str, payload: dict, headers: dict, timeout: float = 30.0) -> bytes:
    """Use system curl — Python's OpenSSL often lacks the corporate MITM root CA."""
    import tempfile

    raw = json.dumps(payload).encode("utf-8")
    # Large attachment payloads exceed comfortable argv size; post via tempfile.
    with tempfile.NamedTemporaryFile(prefix="potions_notify_", suffix=".json", delete=False) as fh:
        fh.write(raw)
        body_path = fh.name
    try:
        cmd = [
            "curl",
            "-sS",
            "--fail-with-body",
            "--max-time",
            str(int(timeout)),
            "-X",
            "POST",
            url,
            "-H",
            "Content-Type: application/json",
        ]
        for k, v in headers.items():
            if k.lower() == "content-type":
                continue
            cmd.extend(["-H", "%s: %s" % (k, v)])
        cmd.extend(["--data-binary", "@%s" % body_path])
        proc = subprocess.run(cmd, capture_output=True)
        if proc.returncode != 0:
            err = (proc.stderr or b"") + b"\n" + (proc.stdout or b"")
            raise urllib.error.URLError(err.decode("utf-8", "replace").strip() or "curl failed")
        return proc.stdout or b""
    finally:
        try:
            Path(body_path).unlink(missing_ok=True)
        except Exception:
            pass


def _https_json(url: str, payload: dict, headers: dict, timeout: float = 30.0) -> bytes:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_ssl_context()) as resp:
            return resp.read()
    except Exception:
        # Fallback for Zscaler/Thales SSL inspection where curl's CA path works.
        return _https_json_curl(url, payload, headers, timeout=timeout)


def _attachment_payloads(paths: Optional[Sequence[AttachmentPath]]) -> List[dict]:
    """Resend-style attachment dicts (filename + base64 content)."""
    out: List[dict] = []
    for raw in paths or []:
        path = Path(raw)
        if not path.exists() or not path.is_file():
            continue
        data = path.read_bytes()
        # Soft cap per file (~8 MiB) to stay under provider limits.
        if len(data) > 8 * 1024 * 1024:
            continue
        mime, _ = mimetypes.guess_type(str(path))
        out.append(
            {
                "filename": path.name,
                "content": base64.b64encode(data).decode("ascii"),
                "content_type": mime or "application/octet-stream",
                "path": path,
            }
        )
    return out


def _send_webhook(
    url: str,
    *,
    subject: str,
    body: str,
    to: str,
    sender: str,
    html: str,
    attachments: Optional[Sequence[AttachmentPath]] = None,
) -> None:
    payload = {
        "to": to,
        "subject": subject,
        "body": body,
        "html": html,
        "from": sender or to,
    }
    atts = _attachment_payloads(attachments)
    if atts:
        payload["attachments"] = [
            {"filename": a["filename"], "content": a["content"], "type": a["content_type"]} for a in atts
        ]
    _https_json(
        url,
        payload,
        {"Content-Type": "application/json"},
    )


def _send_resend(
    *,
    api_key: str,
    subject: str,
    body: str,
    to: str,
    sender: str,
    html: str,
    attachments: Optional[Sequence[AttachmentPath]] = None,
) -> None:
    """Send via Resend with both ``text`` and ``html`` (multipart/alternative)."""
    # Resend requires a verified domain From; allow override via NOTIFY_FROM
    frm = sender or "Potions <onboarding@resend.dev>"
    payload: dict = {
        "from": frm,
        "to": [to],
        "subject": subject,
        "text": body,
        "html": html,
    }
    atts = _attachment_payloads(attachments)
    if atts:
        # Resend expects filename + base64 content.
        payload["attachments"] = [{"filename": a["filename"], "content": a["content"]} for a in atts]
    # Prefer curl first on this host (corporate TLS inspection breaks py OpenSSL).
    _https_json_curl(
        "https://api.resend.com/emails",
        payload,
        {
            "Content-Type": "application/json",
            "Authorization": "Bearer %s" % api_key,
        },
    )


def _send_smtp(
    *,
    user: str,
    password: str,
    subject: str,
    body: str,
    to: str,
    html: str,
    attachments: Optional[Sequence[AttachmentPath]] = None,
    timeout: float = 12.0,
) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    msg.set_content(body)
    msg.add_alternative(html, subtype="html")
    for att in _attachment_payloads(attachments):
        maintype, _, subtype = str(att["content_type"]).partition("/")
        if not subtype:
            maintype, subtype = "application", "octet-stream"
        raw = base64.b64decode(att["content"])
        msg.add_attachment(
            raw,
            maintype=maintype,
            subtype=subtype,
            filename=att["filename"],
        )

    context = ssl.create_default_context()
    # Prefer 465 (implicit SSL); fall back to 587 STARTTLS — both often firewalled here.
    last_err: Optional[BaseException] = None
    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=timeout, context=context) as smtp:
            smtp.login(user, password)
            smtp.send_message(msg)
            return
    except BaseException as exc:  # noqa: BLE001 — surface connect timeouts clearly
        last_err = exc
    try:
        with smtplib.SMTP("smtp.gmail.com", 587, timeout=timeout) as smtp:
            smtp.ehlo()
            smtp.starttls(context=context)
            smtp.ehlo()
            smtp.login(user, password)
            smtp.send_message(msg)
            return
    except BaseException as exc:  # noqa: BLE001
        last_err = exc
    raise TimeoutError(
        "Gmail SMTP unreachable (ports 465/587 blocked or filtered on this host). "
        "Use NOTIFY_WEBHOOK_URL (Google Apps Script) or RESEND_API_KEY instead. "
        "Last error: %r" % (last_err,)
    )


def _send_gmail_api(*, subject: str, body: str, to: str, html: Optional[str] = None) -> str:
    """Send multipart/alternative via Gmail API using ``.gmail_token.json``."""
    import base64

    from live.format_email import build_multipart_message

    # Ensure google env is loaded (token path / user).
    for path in (REPO / ".env.google", REPO / ".env.cursor"):
        if not path.exists():
            continue
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip().strip("'").strip('"')
            if key and key not in os.environ:
                os.environ[key] = val

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    token_raw = os.environ.get("GMAIL_TOKEN_PATH", ".gmail_token.json")
    token_path = Path(token_raw) if Path(token_raw).is_absolute() else REPO / token_raw
    if not token_path.exists():
        raise FileNotFoundError("missing %s" % token_path)
    scopes = [
        "https://www.googleapis.com/auth/gmail.modify",
        "https://www.googleapis.com/auth/gmail.send",
    ]
    creds = Credentials.from_authorized_user_file(str(token_path), scopes)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
    if not creds or not creds.valid:
        raise RuntimeError("Gmail token invalid; run: python -m live.gmail_prompt_agent auth")
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    msg = build_multipart_message(
        subject=subject,
        body=body[:100000],
        to_addr=to,
        from_addr=os.environ.get("GMAIL_USER", "me"),
        html_body=html,
    )
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    sent = service.users().messages().send(userId="me", body={"raw": raw}).execute()
    return sent.get("id", "")


def _ensure_html(*, subject: str, body: str, html: Optional[str]) -> str:
    """Return HTML body; auto-render from plain text when not provided."""
    if html:
        return _truncate(html)
    from live.format_email import plain_to_html

    return _truncate(plain_to_html(body, title=subject))


def send_email(
    *,
    subject: str,
    body: str,
    to: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    html: Optional[str] = None,
    attachments: Optional[Sequence[AttachmentPath]] = None,
) -> str:
    """Send multipart plain+HTML via webhook, Resend, Gmail API, or SMTP."""
    load_notify_env()
    user = (user or os.environ.get("GMAIL_USER") or "").strip()
    password = (password or os.environ.get("GMAIL_APP_PASSWORD") or "").replace(" ", "")
    to = (to or os.environ.get("NOTIFY_TO") or user).strip()
    # NOTIFY_FROM only — do not fall back to GMAIL_USER (Resend rejects unverified domains).
    sender = (os.environ.get("NOTIFY_FROM") or "").strip()
    webhook = (os.environ.get("NOTIFY_WEBHOOK_URL") or "").strip()
    resend_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    body = _truncate(body)
    html_body = _ensure_html(subject=subject, body=body, html=html)

    if not to:
        raise SystemExit("Missing NOTIFY_TO (or GMAIL_USER).")

    # Agent CLI replies: prefer Gmail API (From = your Gmail, works under corp TLS).
    # Also covers in-flight daemons still branching to Resend via GMAIL_REPLY_VIA.
    if (body or "").lstrip().startswith("potions-prompt agent reply"):
        try:
            rid = _send_gmail_api(subject=subject, body=body, to=to, html=html_body)
            return "gmail-api:%s" % rid
        except Exception as exc:
            # Fall through to webhook/Resend so a reply still goes out.
            print("gmail-api agent reply failed (%s); falling back" % exc, flush=True)

    # HTTPS first — SMTP is blocked on this machine.
    def _http_err(prefix: str, exc: BaseException) -> SystemExit:
        detail = str(exc)
        if isinstance(exc, urllib.error.HTTPError):
            try:
                detail = "%s %s" % (exc.code, exc.read().decode("utf-8", "replace"))
            except Exception:
                detail = str(exc)
        return SystemExit("%s: %s" % (prefix, detail))

    if webhook:
        try:
            _send_webhook(
                webhook,
                subject=subject,
                body=body,
                to=to,
                sender=sender,
                html=html_body,
                attachments=attachments,
            )
            return to
        except urllib.error.URLError as exc:
            raise _http_err("NOTIFY_WEBHOOK_URL failed", exc) from exc

    if resend_key:
        try:
            _send_resend(
                api_key=resend_key,
                subject=subject,
                body=body,
                to=to,
                sender=sender,
                html=html_body,
                attachments=attachments,
            )
            return to
        except urllib.error.URLError as exc:
            raise _http_err("Resend API failed", exc) from exc

    if user and password:
        try:
            _send_smtp(
                user=user,
                password=password,
                subject=subject,
                body=body,
                to=to,
                html=html_body,
                attachments=attachments,
            )
            return to
        except TimeoutError as exc:
            raise SystemExit(str(exc)) from exc

    raise SystemExit(
        "No working email transport. This host blocks Gmail SMTP.\n"
        "Set NOTIFY_WEBHOOK_URL (Apps Script — see .env.notify.example) "
        "or RESEND_API_KEY in .env.notify."
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--subject", default="potions notify")
    ap.add_argument("--body", default="")
    ap.add_argument("--body-file", type=Path, default=None)
    ap.add_argument(
        "--html-file",
        type=Path,
        default=None,
        help="HTML multipart alternative (default: auto-rendered from plain body)",
    )
    ap.add_argument("--attach", type=Path, action="append", default=[], help="Attachment path (repeatable)")
    ap.add_argument("--to", default=None)
    ap.add_argument("--test", action="store_true", help="Send a short test email")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if args.test:
        body = (
            "potions notify_email test OK\n"
            "If you got this, HTTPS notify (webhook/Resend) or SMTP is working.\n"
        )
        subject = "potions: notify test"
        html = None
        attachments = None
    else:
        subject = args.subject
        if args.body_file:
            body = args.body_file.read_text(encoding="utf-8", errors="replace")
        else:
            body = args.body or "(empty body)"
        html = args.html_file.read_text(encoding="utf-8", errors="replace") if args.html_file else None
        attachments = list(args.attach) or None

    to = send_email(subject=subject, body=body, to=args.to, html=html, attachments=attachments)
    print("sent to %s" % to, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
