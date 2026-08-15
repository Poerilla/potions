"""Lightweight plain-text / markdown-ish → email HTML (no extra deps).

Produces multipart/alternative messages (plain + HTML) for Gmail prompt-agent
replies and other potions outbound mail. Preserves tables, fenced code,
headings, and monospace paths for Gmail clients.
"""

from __future__ import annotations

import html
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional


_FENCE_RE = re.compile(r"^```([\w+-]*)\s*$")
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)$")
_HR_RE = re.compile(r"^-{3,}\s*$")
_BULLET_RE = re.compile(r"^[-*]\s+(.+)$")
_NUMBERED_RE = re.compile(r"^(\d+)[.)]\s+(.+)$")
_TABLE_SEP_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)+\|?\s*$")


def _is_table_row(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.count("|") >= 2


def _split_table_cells(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    return [cell.strip() for cell in stripped.split("|")]


def plain_to_html(body: str, *, title: Optional[str] = None) -> str:
    """Convert agent/plain body text into a simple HTML document."""
    text = (body or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = text.split("\n")
    parts: list[str] = [
        "<!DOCTYPE html>",
        '<html><head><meta charset="utf-8">',
        "<style>",
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,"
        "sans-serif;font-size:14px;line-height:1.45;color:#222;}",
        "h1,h2,h3{margin:1.1em 0 0.4em;}",
        "pre,code{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;"
        "font-size:12.5px;}",
        "pre{background:#f4f4f5;border:1px solid #e4e4e7;border-radius:6px;"
        "padding:10px 12px;overflow-x:auto;}",
        "table{border-collapse:collapse;margin:0.6em 0;font-size:13px;}",
        "th,td{border:1px solid #d4d4d8;padding:4px 8px;text-align:left;vertical-align:top;}",
        "th{background:#f4f4f5;}",
        "ul{margin:0.4em 0 0.4em 1.2em;padding:0;}",
        "hr{border:none;border-top:1px solid #d4d4d8;margin:1em 0;}",
        ".meta{color:#71717a;font-size:12px;}",
        "</style></head><body>",
    ]
    if title:
        parts.append(f"<h1>{html.escape(title)}</h1>")

    i = 0
    in_code = False
    code_lang = ""
    code_buf: list[str] = []
    para_buf: list[str] = []
    list_buf: list[str] = []
    list_tag = "ul"

    def flush_para() -> None:
        nonlocal para_buf
        if not para_buf:
            return
        joined = " ".join(para_buf)
        parts.append(f"<p>{joined}</p>")
        para_buf = []

    def flush_list() -> None:
        nonlocal list_buf, list_tag
        if not list_buf:
            return
        items = "".join(f"<li>{item}</li>" for item in list_buf)
        parts.append(f"<{list_tag}>{items}</{list_tag}>")
        list_buf = []
        list_tag = "ul"

    def flush_code() -> None:
        nonlocal code_buf, in_code, code_lang
        lang_attr = f' class="language-{html.escape(code_lang)}"' if code_lang else ""
        content = html.escape("\n".join(code_buf))
        parts.append(f"<pre><code{lang_attr}>{content}</code></pre>")
        code_buf = []
        in_code = False
        code_lang = ""

    while i < len(lines):
        line = lines[i]

        if in_code:
            if _FENCE_RE.match(line):
                flush_code()
            else:
                code_buf.append(line)
            i += 1
            continue

        fence = _FENCE_RE.match(line)
        if fence:
            flush_para()
            flush_list()
            in_code = True
            code_lang = fence.group(1) or ""
            i += 1
            continue

        if _is_table_row(line):
            flush_para()
            flush_list()
            table_lines = []
            while i < len(lines) and (_is_table_row(lines[i]) or _TABLE_SEP_RE.match(lines[i])):
                table_lines.append(lines[i])
                i += 1
            # Drop separator rows
            rows = [r for r in table_lines if not _TABLE_SEP_RE.match(r)]
            if rows:
                parts.append("<table>")
                for idx, row in enumerate(rows):
                    cells = _split_table_cells(row)
                    tag = "th" if idx == 0 else "td"
                    parts.append(
                        "<tr>"
                        + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells)
                        + "</tr>"
                    )
                parts.append("</table>")
            continue

        if not line.strip():
            flush_para()
            flush_list()
            i += 1
            continue

        if _HR_RE.match(line):
            flush_para()
            flush_list()
            parts.append("<hr>")
            i += 1
            continue

        heading = _HEADING_RE.match(line)
        if heading:
            flush_para()
            flush_list()
            level = len(heading.group(1))
            parts.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
            i += 1
            continue

        bullet = _BULLET_RE.match(line)
        if bullet:
            flush_para()
            if list_buf and list_tag != "ul":
                flush_list()
            list_tag = "ul"
            list_buf.append(html.escape(bullet.group(1)))
            i += 1
            continue

        numbered = _NUMBERED_RE.match(line)
        if numbered:
            flush_para()
            if list_buf and list_tag != "ol":
                flush_list()
            list_tag = "ol"
            list_buf.append(html.escape(numbered.group(2)))
            i += 1
            continue

        # Status / key: value lines stay as paragraphs with light emphasis
        escaped = html.escape(line)
        if line.startswith("Status:") or line.startswith("Target:") or line.startswith("RL10:"):
            flush_list()
            flush_para()
            parts.append(f"<p><strong>{escaped}</strong></p>")
            i += 1
            continue

        # Paths / commands often look better in code if they look like paths
        if line.startswith("  ") or line.startswith("\t"):
            flush_para()
            flush_list()
            parts.append(f"<pre>{html.escape(line.rstrip())}</pre>")
            i += 1
            continue

        para_buf.append(escaped)
        i += 1

    flush_para()
    flush_list()
    if in_code:
        flush_code()
    parts.append("</body></html>")
    return "\n".join(parts)


def build_multipart_message(
    *,
    subject: str,
    body: str,
    to_addr: str,
    from_addr: str,
    html_body: Optional[str] = None,
) -> MIMEMultipart:
    """Build multipart/alternative MIME with plain + HTML parts."""
    plain = body or ""
    html_part = html_body if html_body is not None else plain_to_html(plain, title=subject)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["To"] = to_addr
    msg["From"] = from_addr
    msg.attach(MIMEText(plain[:100000], "plain", "utf-8"))
    msg.attach(MIMEText(html_part[:200000], "html", "utf-8"))
    return msg
