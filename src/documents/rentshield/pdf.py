# Renders a build_notice() dict into a standalone, print-ready bilingual
# HTML page, then to a real PDF via headless Chromium (Playwright for
# Python) — a port of legacy-v1/api/src/services/esign/renderNoticeHtml.js
# and renderPdf.js onto this stack. The resulting PDF is what gets handed
# to paperless-ngx's own consumption pipeline (documents.tasks.consume_file)
# so every generated notice becomes a real, searchable Document.
from __future__ import annotations

import html as html_module

from playwright.sync_api import sync_playwright


def _esc(value) -> str:
    return html_module.escape(str(value) if value is not None else "")


def _render_side(side: dict, include_signature_field: bool = False) -> str:
    paragraphs = "\n".join(f"<p>{_esc(p)}</p>" for p in side["paragraphs"])
    if include_signature_field:
        # DocuSeal's <text-field> tag syntax (see docs/api HTML submission
        # docs) — turns the landlord's signature block into an actual
        # fillable/signable field, not just static text.
        signature_block = (
            f'<p style="margin-top:2em;">{_esc(side["landlord_name"])}<br>'
            f'<text-field name="Landlord Signature" role="Landlord" required="true" '
            f'style="width:220px;height:60px;display:inline-block;border-bottom:1px solid #333;margin-top:8px;">'
            f'</text-field></p>'
        )
    else:
        signature_block = f'<p style="margin-top:2em;">{_esc(side["landlord_name"])} — {_esc(side["sign_date"])}</p>'

    return f"""
    <header>
      <p class="kicker">{_esc(side["kicker"])}</p>
      <h1>{_esc(side["title"])}</h1>
      <p class="subtitle">{_esc(side["subtitle"])}</p>
    </header>
    <table class="meta">
      <tr><td>{_esc(side["date_label"])}</td><td>{_esc(side["date_value"])}</td></tr>
      <tr><td>{_esc(side["deadline_label"])}</td><td>{_esc(side["deadline_value"])}</td></tr>
    </table>
    <p><strong>{_esc(side["to"])}</strong></p>
    <p>{_esc(side["ejari_line"])}<br>{_esc(side["property_line"])}</p>
    {paragraphs}
    <p><strong>{_esc(side["reason_label"])}</strong><br>{_esc(side["reason_text"])}</p>
    <p>{_esc(side["closing"])}</p>
    <p class="footer">{_esc(side["footer"])}</p>
    {signature_block}
    """


def render_notice_html(document: dict, include_signature_field: bool = False) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<style>
  body {{ font-family: 'Times New Roman', serif; color: #1a1a1a; line-height: 1.6; padding: 40px; }}
  .kicker {{ text-transform: uppercase; letter-spacing: 0.08em; font-size: 11px; color: #666; }}
  h1 {{ font-size: 22px; margin: 4px 0; }}
  .subtitle {{ font-size: 12px; color: #444; }}
  .meta {{ margin: 16px 0; font-size: 13px; }}
  .meta td {{ padding: 2px 12px 2px 0; }}
  .footer {{ font-size: 11px; color: #666; margin-top: 24px; }}
  .divider {{ border: none; border-top: 2px solid #333; margin: 32px 0; }}
  [dir="rtl"] {{ text-align: right; font-family: 'Traditional Arabic', 'Arial', sans-serif; }}
</style>
</head>
<body>
  <section dir="ltr">{_render_side(document["en"], include_signature_field)}</section>
  <hr class="divider">
  <section dir="rtl">{_render_side(document["ar"])}</section>
</body>
</html>"""


# Mirrors legacy-v1/api/src/services/esign/renderPdf.js's pinned-Chromium
# fallback for this same sandbox (see that file's comment for why: the
# playwright-core version installed here can drift ahead of the browser
# revision this environment has pre-cached, and there is no network path
# to download a replacement).
_PINNED_CHROMIUM = "/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell"


def render_notice_pdf(document: dict) -> bytes:
    import os

    html_content = render_notice_html(document)
    launch_kwargs = {"executable_path": _PINNED_CHROMIUM} if os.path.exists(_PINNED_CHROMIUM) else {}
    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kwargs)
        try:
            page = browser.new_page()
            page.set_content(html_content, wait_until="load")
            return page.pdf(format="A4", print_background=True, margin={"top": "20px", "bottom": "20px"})
        finally:
            browser.close()
