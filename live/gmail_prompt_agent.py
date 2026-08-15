"""Poll Gmail for subject ``potions-prompt``, run Cursor CLI agent, reply by email.

Setup
-----
1. Copy ``.env.google.example`` → ``.env.google`` (or use the filled local file).
2. Enable Gmail API on the Google Cloud project; OAuth client type = Desktop.
3. One-time auth (opens browser / prints URL)::

       python -m live.gmail_prompt_agent auth

4. Poll once or daemonize::

       python -m live.gmail_prompt_agent poll --once
       python -m live.gmail_prompt_agent poll          # loop

Only unread messages whose Subject equals ``GMAIL_PROMPT_SUBJECT`` (default
``potions-prompt``) are processed. Body = agent prompt. Reply is threaded
multipart/alternative (plain + HTML). Messages are marked read on first read,
before the agent run.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .format_email import build_multipart_message

REPO = Path(__file__).resolve().parents[1]
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
]
ENV_FILES = (
    REPO / ".env.google",
    REPO / ".env.cursor",
    REPO / ".env.resend",
)


def load_env() -> None:
    for path in ENV_FILES:
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


def _require_google_libs():
    try:
        from google.auth.transport.requests import Request  # noqa: F401
        from google.oauth2.credentials import Credentials  # noqa: F401
        from google_auth_oauthlib.flow import InstalledAppFlow  # noqa: F401
        from googleapiclient.discovery import build  # noqa: F401
    except ImportError as exc:
        raise SystemExit(
            "Missing Google API deps. Install with:\n"
            "  pip install google-auth google-auth-oauthlib google-api-python-client\n"
            "(%s)" % exc
        ) from exc


def _client_config() -> dict:
    cid = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not cid or not secret:
        raise SystemExit("GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET missing in .env.google")
    return {
        "installed": {
            "client_id": cid,
            "client_secret": secret,
            "project_id": os.environ.get("GOOGLE_PROJECT_ID", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": [os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost")],
        }
    }


def _token_path() -> Path:
    raw = os.environ.get("GMAIL_TOKEN_PATH", ".gmail_token.json")
    p = Path(raw)
    return p if p.is_absolute() else REPO / p


def _processed_dir() -> Path:
    d = REPO / ".gmail_processed"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _auth_manual_paste():
    """Headless-friendly OAuth: open URL on any device, paste redirect URL back.

    Google redirects to ``http://localhost/?code=...`` after consent. On a remote
    host that page fails to load — that is OK. Copy the **full** address-bar URL
    (including ``?code=...``) and paste it into the terminal.
    """
    from urllib.parse import parse_qs, urlparse

    from google_auth_oauthlib.flow import InstalledAppFlow

    redirect = os.environ.get("GOOGLE_REDIRECT_URI", "http://localhost").strip() or "http://localhost"
    flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
    flow.redirect_uri = redirect
    auth_url, _state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
    )
    print("", flush=True)
    print("1) Open this URL in your browser (phone/laptop is fine):", flush=True)
    print(auth_url, flush=True)
    print("", flush=True)
    print("2) Approve access. The browser will say localhost refused to connect — ignore that.", flush=True)
    print("3) Copy the FULL URL from the address bar (starts with http://localhost/?code=...)", flush=True)
    print("   and paste it below, then press Enter.", flush=True)
    print("", flush=True)
    raw = input("Paste redirect URL: ").strip().strip('"').strip("'")
    if not raw:
        raise SystemExit("Empty paste — auth cancelled.")
    if raw.startswith("http://") or raw.startswith("https://"):
        code = parse_qs(urlparse(raw).query).get("code", [None])[0]
        if not code:
            raise SystemExit("No ?code= in pasted URL. Copy the entire address bar.")
        # Exchange code only — authorization_response can fail on redirect_uri/port mismatch.
        flow.fetch_token(code=code)
    else:
        flow.fetch_token(code=raw)
    return flow.credentials


def get_credentials(*, interactive: bool = False, local_server: bool = False):
    _require_google_libs()
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    token_path = _token_path()
    creds = None
    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds
    if creds and creds.valid:
        return creds
    if not interactive:
        raise SystemExit("No valid Gmail token. Run: python -m live.gmail_prompt_agent auth")
    if local_server:
        from google_auth_oauthlib.flow import InstalledAppFlow

        flow = InstalledAppFlow.from_client_config(_client_config(), SCOPES)
        creds = flow.run_local_server(port=8080, open_browser=True)
    else:
        # Default: paste-back flow (works when browser ≠ this host).
        creds = _auth_manual_paste()
    token_path.write_text(creds.to_json(), encoding="utf-8")
    os.chmod(token_path, 0o600)
    print("Wrote token %s" % token_path, flush=True)
    return creds


def gmail_service(creds=None):
    _require_google_libs()
    from googleapiclient.discovery import build

    return build("gmail", "v1", credentials=creds or get_credentials(), cache_discovery=False)


def _subject_filter() -> str:
    return os.environ.get("GMAIL_PROMPT_SUBJECT", "potions-prompt").strip()


def _normalize_subject(subject: str) -> str:
    """Strip Re:/Fwd: prefixes and collapse whitespace for matching."""
    s = (subject or "").strip()
    # Repeat to handle "Re: Re:" / "FW:" chains
    for _ in range(5):
        low = s.lower()
        for prefix in ("re:", "fw:", "fwd:"):
            if low.startswith(prefix):
                s = s[len(prefix) :].strip()
                break
        else:
            break
    return s


def _subject_matches(subject: str) -> bool:
    return _normalize_subject(subject) == _subject_filter()


def list_prompt_messages(service) -> List[dict]:
    """Find candidate prompt mails.

    Self-sent mail often has no UNREAD label (Gmail marks it read on send),
    so we search recent inbox by subject and skip already-processed ids.
    Also matches ``Re: potions-prompt`` follow-ups.
    """
    subj = _subject_filter().replace('"', "")
    lookback = os.environ.get("GMAIL_LOOKBACK", "14d").strip() or "14d"
    # Prefer unread, but also catch self-sent / already-read prompts.
    # Gmail subject: query is contains-ish, so Re: potions-prompt matches too.
    queries = [
        'is:unread subject:"%s"' % subj,
        'in:inbox newer_than:%s subject:"%s"' % (lookback, subj),
    ]
    seen = set()
    out: List[dict] = []
    for q in queries:
        resp = service.users().messages().list(userId="me", q=q, maxResults=20).execute()
        for stub in resp.get("messages") or []:
            mid = stub["id"]
            if mid in seen:
                continue
            seen.add(mid)
            if (_processed_dir() / ("%s.json" % mid)).exists():
                continue
            out.append(stub)
    return out


def _decode_body(payload: dict) -> str:
    if payload.get("body", {}).get("data"):
        return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")
    parts = payload.get("parts") or []
    texts = []
    for part in parts:
        mime = part.get("mimeType", "")
        if mime == "text/plain" and part.get("body", {}).get("data"):
            texts.append(base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace"))
        elif mime.startswith("multipart/"):
            nested = _decode_body(part)
            if nested:
                texts.append(nested)
    return "\n".join(texts).strip()


def fetch_message(service, msg_id: str) -> Dict[str, Any]:
    msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
    headers = {h["name"].lower(): h["value"] for h in msg.get("payload", {}).get("headers", [])}
    body = _decode_body(msg.get("payload") or {})
    return {
        "id": msg_id,
        "threadId": msg.get("threadId"),
        "subject": headers.get("subject", ""),
        "from": headers.get("from", ""),
        "to": headers.get("to", ""),
        "message_id": headers.get("message-id", ""),
        "body": body,
        "snippet": msg.get("snippet", ""),
    }


def run_agent(prompt: str) -> str:
    agent_bin = os.environ.get("AGENT_BIN", "agent").strip() or "agent"
    timeout = int(os.environ.get("AGENT_TIMEOUT_SEC", "900"))
    # Workspace = potions repo; prompt is the email body.
    cmd = [
        agent_bin,
        "-p",
        "--force",
        "--workspace",
        str(REPO),
        prompt,
    ]
    model = os.environ.get("AGENT_MODEL", "").strip()
    if model:
        cmd[1:1] = ["--model", model]
    env = os.environ.copy()
    # System trust (Thales Root CA V3) is enough. Drop incomplete override
    # bundles that break verify (SSL_CERT_FILE / OPENSSL_CONF experiments).
    for k in (
        "OPENSSL_CONF",
        "SSL_CERT_FILE",
        "SSL_CERT_DIR",
        "NODE_EXTRA_CA_CERTS",
        "NODE_OPTIONS",
        "AGENT_CLI_CREDENTIAL_STORE",
    ):
        env.pop(k, None)
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(REPO),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        return (
            "[gmail_prompt_agent] agent binary not found (%s). "
            "Install Cursor CLI or set AGENT_BIN." % agent_bin
        )
    except subprocess.TimeoutExpired:
        return "[gmail_prompt_agent] agent timed out after %ss" % timeout
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return (
            "[gmail_prompt_agent] agent exit %s\n\nSTDOUT:\n%s\n\nSTDERR:\n%s"
            % (proc.returncode, out[:8000], err[:4000])
        )
    if not out:
        return "[gmail_prompt_agent] agent returned empty stdout.\nSTDERR:\n%s" % err[:4000]
    return out


def _extract_email(addr: str) -> str:
    addr = (addr or "").strip()
    if "<" in addr and ">" in addr:
        return addr.split("<", 1)[1].split(">", 1)[0].strip()
    return addr


def _is_transient_gmail_error(exc: BaseException) -> bool:
    name = type(exc).__name__
    text = str(exc).lower()
    needles = (
        "broken pipe",
        "connection reset",
        "temporarily unavailable",
        "timed out",
        "timeout",
        "unexpected eof",
        "ssleof",
        "503",
        "500",
    )
    return name in {"SSLEOFError", "SSLError", "ConnectionError", "OSError", "HttpError"} or any(
        n in text for n in needles
    )


def send_reply(service, original: dict, body: str) -> str:
    """Threaded multipart/alternative (plain+HTML) reply via Gmail API (default).

    Rebuilds the Gmail client and retries on transient SSL/connection errors —
    common after a long Cursor agent run leaves the httplib2 session stale.

    Set GMAIL_REPLY_VIA=resend to send through notify_email (also multipart).
    """
    subj = original.get("subject") or _subject_filter()
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    to_addr = _extract_email(original.get("from") or "") or os.environ.get("NOTIFY_TO") or os.environ.get(
        "GMAIL_USER", ""
    )
    via = (os.environ.get("GMAIL_REPLY_VIA") or "gmail").strip().lower()
    if via in {"resend", "notify", "email"}:
        from .format_email import plain_to_html
        from .notify_email import send_email

        channel = send_email(
            subject=subj,
            body=body,
            to=to_addr,
            html=plain_to_html(body, title=subj),
        )
        print("reply via %s → %s" % (channel, to_addr), flush=True)
        return "resend:%s" % channel
    msg = build_multipart_message(
        subject=subj,
        body=body[:100000],
        to_addr=to_addr,
        from_addr=os.environ.get("GMAIL_USER", "me"),
    )
    if original.get("message_id"):
        msg["In-Reply-To"] = original["message_id"]
        msg["References"] = original["message_id"]
    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
    payload = {"raw": raw, "threadId": original.get("threadId")}

    last_exc: Optional[BaseException] = None
    for attempt in range(1, 4):
        try:
            # Fresh client each attempt (avoids stale TLS after long agent runs).
            svc = gmail_service()
            sent = svc.users().messages().send(userId="me", body=payload).execute()
            rid = sent.get("id", "")
            print("reply via gmail → %s (%s)" % (to_addr, rid), flush=True)
            return rid
        except Exception as exc:
            last_exc = exc
            if attempt >= 3 or not _is_transient_gmail_error(exc):
                raise
            wait_s = 2 * attempt
            print(
                "send_reply transient error (attempt %s/3): %s; retry in %ss"
                % (attempt, exc, wait_s),
                flush=True,
            )
            time.sleep(wait_s)
    raise last_exc  # pragma: no cover


def mark_read(service, msg_id: str) -> None:
    """Remove UNREAD on first read (before the agent run)."""
    service.users().messages().modify(
        userId="me", id=msg_id, body={"removeLabelIds": ["UNREAD"]}
    ).execute()


def _claim_marker(mid: str, original: dict) -> Path:
    """Claim message before work (marker exists ⇒ skip; reduces duplicate agent runs)."""
    marker = _processed_dir() / ("%s.json" % mid)
    if marker.exists():
        raise FileExistsError(mid)
    payload = {
        "id": mid,
        "status": "claimed",
        "from": original.get("from"),
        "subject": original.get("subject"),
    }
    fd = os.open(str(marker), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, indent=2) + "\n")
    return marker


def _is_echo_prompt(original: dict, prompt: str) -> Optional[str]:
    """Detect Resend/Gmail copies of our own agent replies (avoid reply loops)."""
    frm = (original.get("from") or "").lower()
    if "resend.dev" in frm or "onboarding@resend" in frm:
        return "resend echo sender"
    # Body is (or starts with) a prior agent reply envelope
    head = (prompt or "").lstrip()
    if head.lower().startswith("potions-prompt agent reply"):
        return "prior agent-reply body"
    if "\nsource_message_id:" in (prompt or "") and "workspace: " in (prompt or ""):
        return "agent-reply footer"
    return None


def process_once(service=None) -> int:
    load_env()
    service = service or gmail_service()
    msgs = list_prompt_messages(service)
    if not msgs:
        print("no pending potions-prompt mail", flush=True)
        return 0
    n = 0
    for stub in msgs:
        mid = stub["id"]
        marker = _processed_dir() / ("%s.json" % mid)
        if marker.exists():
            continue
        original = fetch_message(service, mid)
        # Exact base subject, allowing Re:/Fwd: prefixes
        if not _subject_matches(original["subject"]):
            print("skip subject mismatch: %r" % original["subject"], flush=True)
            continue
        prompt = (original.get("body") or original.get("snippet") or "").strip()
        # Strip quoted reply tails so follow-ups stay focused
        if prompt:
            cut_markers = (
                "\nOn ",
                "\n-----Original Message-----",
                "\npotions-prompt agent reply\n",
                "\nFrom: ",
            )
            cut_at = len(prompt)
            for m in cut_markers:
                i = prompt.find(m)
                if 0 < i < cut_at:
                    cut_at = i
            prompt = prompt[:cut_at].strip()
        echo_reason = _is_echo_prompt(original, prompt)
        if echo_reason:
            print("skip echo (%s): %s from %s" % (echo_reason, mid, original.get("from")), flush=True)
            try:
                mark_read(service, mid)
            except Exception as exc:
                print("mark_read skipped: %s" % exc, flush=True)
            marker.write_text(
                json.dumps(
                    {"id": mid, "skipped": "echo", "reason": echo_reason, "from": original.get("from")},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
            continue
        if not prompt:
            prompt = "(empty body)"
        try:
            marker = _claim_marker(mid, original)
        except FileExistsError:
            print("skip already claimed: %s" % mid, flush=True)
            continue
        # Mark read on first read — before the (possibly long) agent run.
        try:
            mark_read(service, mid)
        except Exception as exc:
            print("mark_read skipped: %s" % exc, flush=True)
        print("processing %s from %s (%d chars)" % (mid, original.get("from"), len(prompt)), flush=True)
        result = run_agent(prompt)
        reply_body = (
            "potions-prompt agent reply\n"
            "-------------------------\n\n"
            "%s\n\n"
            "--\n"
            "workspace: %s\n"
            "source_message_id: %s\n"
        ) % (result, REPO, mid)
        marker.write_text(
            json.dumps(
                {
                    "id": mid,
                    "status": "reply_pending",
                    "from": original.get("from"),
                    "subject": original.get("subject"),
                    "result_chars": len(result or ""),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        # Fresh client inside send_reply (stale TLS after long agent runs).
        rid = send_reply(None, original, reply_body)
        marker.write_text(
            json.dumps(
                {"id": mid, "status": "replied", "reply_id": rid, "from": original.get("from")},
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print("replied %s → %s" % (mid, rid), flush=True)
        n += 1
    return n


def cmd_auth(args: argparse.Namespace) -> int:
    load_env()
    get_credentials(interactive=True, local_server=bool(getattr(args, "local_server", False)))
    # Smoke: profile
    svc = gmail_service()
    profile = svc.users().getProfile(userId="me").execute()
    print("authenticated as %s" % profile.get("emailAddress"), flush=True)
    return 0


def cmd_poll(args: argparse.Namespace) -> int:
    load_env()
    service = gmail_service()
    if args.once:
        process_once(service)
        return 0
    interval = int(args.interval or os.environ.get("GMAIL_POLL_SECONDS", "90"))
    print("polling every %ss for subject=%r" % (interval, _subject_filter()), flush=True)
    while True:
        try:
            process_once(service)
        except Exception as exc:
            print("poll error: %s" % exc, flush=True)
        time.sleep(max(15, interval))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_auth = sub.add_parser("auth", help="OAuth login; write .gmail_token.json")
    p_auth.add_argument(
        "--local-server",
        action="store_true",
        help="Use localhost callback server (only if browser runs on THIS machine).",
    )
    p_auth.set_defaults(func=cmd_auth)

    p_poll = sub.add_parser("poll", help="Poll Gmail and run agent on potions-prompt mail")
    p_poll.add_argument("--once", action="store_true")
    p_poll.add_argument("--interval", type=int, default=None)
    p_poll.set_defaults(func=cmd_poll)

    p_test = sub.add_parser("dry-run-agent", help="Run agent on a local prompt string (no Gmail)")
    p_test.add_argument("prompt")

    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "dry-run-agent":
        load_env()
        print(run_agent(args.prompt))
        return 0
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
