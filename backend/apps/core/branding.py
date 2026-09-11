"""School identity for generated documents (report cards, IEPs, letters).

Everything here degrades gracefully: with no SchoolProfile row, or an empty
one, the helpers return sensible blanks so a document still renders.
"""
from __future__ import annotations

import base64
import html as _html
import mimetypes

from apps.core.models import SchoolProfile


def logo_data_uri(profile: SchoolProfile | None = None) -> str:
    """The logo as a base64 ``data:`` URI so a document stays self-contained,
    or "" when there is no logo / it can't be read."""
    profile = profile or SchoolProfile.load()
    return _image_data_uri(profile.logo)


def signature_data_uri(profile: SchoolProfile | None = None) -> str:
    """The principal's uploaded signature, same treatment as the logo."""
    profile = profile or SchoolProfile.load()
    return _image_data_uri(profile.signature)


def _image_data_uri(field) -> str:
    if not field:
        return ""
    try:
        with field.open("rb") as fh:
            raw = fh.read()
    except (OSError, ValueError):
        return ""
    mime = mimetypes.guess_type(field.name)[0] or "image/png"
    return f"data:{mime};base64,{base64.b64encode(raw).decode()}"


def letterhead_html(profile: SchoolProfile | None = None) -> str:
    """A styled <header> block for the top of a generated document."""
    p = profile or SchoolProfile.load()
    name = _html.escape(p.name or "")
    logo = logo_data_uri(p)
    lines = [_html.escape(line) for line in p.address_block.splitlines()]
    contact = " · ".join(
        _html.escape(x) for x in (p.phone, p.email, p.website) if x
    )

    left = f'<img src="{logo}" alt="" class="lh-logo">' if logo else ""
    meta = ""
    if lines:
        meta += '<div class="lh-addr">' + "<br>".join(lines) + "</div>"
    if contact:
        meta += f'<div class="lh-contact">{contact}</div>'
    if p.motto:
        meta += f'<div class="lh-motto">{_html.escape(p.motto)}</div>'

    return f"""<header class="letterhead">
  {left}
  <div class="lh-body">
    <div class="lh-name">{name or "&nbsp;"}</div>
    {meta}
  </div>
</header>"""


LETTERHEAD_CSS = "\n".join([
    ".letterhead{display:flex;gap:16px;align-items:flex-start;",
    " border-bottom:2px solid #1c2126;padding-bottom:12px;margin-bottom:18px}",
    ".letterhead .lh-logo{max-height:72px;max-width:180px;object-fit:contain}",
    ".letterhead .lh-name{font-size:19px;font-weight:700;letter-spacing:.01em}",
    ".letterhead .lh-addr,.letterhead .lh-contact{font-size:12px;",
    " color:#5b6572;margin-top:2px;white-space:pre-line}",
    ".letterhead .lh-motto{font-size:12px;font-style:italic;",
    " color:#5b6572;margin-top:4px}",
])


def signature_block_html(profile: SchoolProfile | None = None) -> str:
    p = profile or SchoolProfile.load()
    if not p.principal_name:
        return ""
    sig = signature_data_uri(p)
    img = (
        f'<img src="{sig}" alt="" style="max-height:52px;max-width:200px;'
        f'object-fit:contain;display:block;margin-bottom:2px">'
        if sig
        else ""
    )
    return (
        '<div class="sigblock" style="margin-top:34px">'
        f'{img}'
        '<div style="border-top:1px solid #1c2126;width:240px;padding-top:4px">'
        f"{_html.escape(p.principal_name)}<br>"
        f'<span style="font-size:12px;color:#5b6572">{_html.escape(p.principal_title or "")}</span>'
        "</div></div>"
    )
