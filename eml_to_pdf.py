#!/usr/bin/env python3
"""
eml_to_pdf.py
-------------
Converts .eml files into PDFs organised by date.
- Preserves tables, bold, italic and inline images from the HTML body
- Embeds PDF and image attachments into the same output file
- Output filename: YYYY-MM-DD_HHMMSS_subject.pdf

Requirements:
    pip install reportlab pypdf pillow beautifulsoup4

Usage:
    python eml_to_pdf.py --input ./emails --output ./generated_pdfs
"""

import argparse
import base64
import email
import email.policy
import os
import re
import sys
import tempfile
from datetime import datetime
from email.header import decode_header
from email.utils import parsedate_to_datetime
from io import BytesIO
from pathlib import Path

from bs4 import BeautifulSoup, NavigableString, Tag
from PIL import Image as PILImage

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable, Image, Paragraph, SimpleDocTemplate,
    Spacer, Table, TableStyle,
)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

# ---------------------------------------------------------------------------
# Fonts
# ---------------------------------------------------------------------------
FONT = "Helvetica"
FONT_BOLD = "Helvetica-Bold"
FONT_ITALIC = "Helvetica-Oblique"
FONT_BOLDITALIC = "Helvetica-BoldOblique"
FONT_MONO = "Courier"

for _name, _path in [
    ("DejaVu", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ("DejaVu", "/usr/share/fonts/dejavu/DejaVuSans.ttf"),
]:
    if os.path.exists(_path):
        try:
            pdfmetrics.registerFont(TTFont("DejaVu", _path))
            _b  = _path.replace("DejaVuSans", "DejaVuSans-Bold")
            _i  = _path.replace("DejaVuSans", "DejaVuSans-Oblique")
            _bi = _path.replace("DejaVuSans", "DejaVuSans-BoldOblique")
            if os.path.exists(_b):
                pdfmetrics.registerFont(TTFont("DejaVu-Bold", _b))
                FONT_BOLD = "DejaVu-Bold"
            if os.path.exists(_i):
                pdfmetrics.registerFont(TTFont("DejaVu-Italic", _i))
                FONT_ITALIC = "DejaVu-Italic"
            if os.path.exists(_bi):
                pdfmetrics.registerFont(TTFont("DejaVu-BoldItalic", _bi))
                FONT_BOLDITALIC = "DejaVu-BoldItalic"
            FONT = "DejaVu"
            break
        except Exception:
            pass

# ---------------------------------------------------------------------------
# Colours and dimensions
# ---------------------------------------------------------------------------
DARK_BLUE    = colors.HexColor("#1a237e")
BLUE_BG      = colors.HexColor("#e8eaf6")
GRAY_BG      = colors.HexColor("#f5f5f5")
BORDER_COLOR = colors.HexColor("#c5cae9")
GRAY_TEXT    = colors.HexColor("#555555")
BLACK        = colors.HexColor("#212121")

PAGE_W, PAGE_H = A4
MARGIN    = 2 * cm
CONTENT_W = PAGE_W - 2 * MARGIN   # ~487 pt


def _style(name, **kw):
    defaults = dict(fontName=FONT, fontSize=9, leading=13,
                    textColor=BLACK, wordWrap="CJK")
    defaults.update(kw)
    return ParagraphStyle(name, **defaults)

STYLE_NORMAL = _style("n")
STYLE_LABEL  = _style("lbl", fontName=FONT_BOLD, fontSize=8, textColor=GRAY_TEXT)
STYLE_TITLE  = _style("tit", fontName=FONT_BOLD, fontSize=13,
                       textColor=DARK_BLUE, leading=18)
STYLE_H1     = _style("h1", fontName=FONT_BOLD, fontSize=12, leading=16,
                       spaceBefore=8, spaceAfter=4)
STYLE_H2     = _style("h2", fontName=FONT_BOLD, fontSize=10, leading=14,
                       spaceBefore=6, spaceAfter=3)
STYLE_H3     = _style("h3", fontName=FONT_BOLD, fontSize=9,  leading=13,
                       spaceBefore=4, spaceAfter=2)
STYLE_MONO   = _style("mono", fontName=FONT_MONO, fontSize=8, leading=11)
STYLE_LI     = _style("li", leftIndent=16)


# ---------------------------------------------------------------------------
# Email helpers
# ---------------------------------------------------------------------------

def decode_header_value(value):
    if not value:
        return ""
    parts = decode_header(value)
    res = []
    for part, charset in parts:
        if isinstance(part, bytes):
            res.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            res.append(str(part))
    return "".join(res)


def extract_date(msg):
    try:
        return parsedate_to_datetime(msg.get("Date", ""))
    except Exception:
        return datetime.min


def sanitize_name(text, max_len=60):
    text = re.sub(r'[\\/*?:"<>|]', "_", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_len]


def extract_body(msg):
    """Returns (html, plain_text, cid_images={cid: (bytes, mimetype)})."""
    html, text, cid_images = "", "", {}
    if msg.is_multipart():
        for part in msg.walk():
            content_type = part.get_content_type()
            disposition  = str(part.get("Content-Disposition", ""))
            cid          = part.get("Content-ID", "").strip("<>")
            if content_type.startswith("image/") and cid:
                data = part.get_payload(decode=True)
                if data:
                    cid_images[cid] = (data, content_type)
            if "attachment" in disposition:
                continue
            charset = part.get_content_charset() or "utf-8"
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            try:
                content = payload.decode(charset, errors="replace")
            except Exception:
                content = payload.decode("utf-8", errors="replace")
            if content_type == "text/html" and not html:
                html = content
            elif content_type == "text/plain" and not text:
                text = content
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            content = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            content = str(msg.get_payload())
        if msg.get_content_type() == "text/html":
            html = content
        else:
            text = content
    return html.strip(), text.strip(), cid_images


def extract_attachments(msg):
    attachments = []
    if msg.is_multipart():
        for part in msg.walk():
            filename_raw = part.get_filename()
            disposition  = str(part.get("Content-Disposition", ""))
            if filename_raw and "attachment" in disposition:
                data = part.get_payload(decode=True)
                if data:
                    attachments.append({
                        "name": decode_header_value(filename_raw),
                        "type": part.get_content_type(),
                        "data": data,
                    })
    return attachments


# ---------------------------------------------------------------------------
# HTML → Flowables
# ---------------------------------------------------------------------------

TAGS_IGNORE = {"style", "script", "head", "meta", "link", "noscript"}
TAGS_BLOCK  = {"p", "div", "section", "article", "h1", "h2", "h3", "h4",
               "h5", "h6", "ul", "ol", "blockquote", "pre", "table", "hr"}


def _esc(txt):
    return (txt.replace("&", "&amp;")
               .replace("<", "&lt;")
               .replace(">", "&gt;"))


def _inline_xml(node, bold=False, italic=False, underline=False, mono=False):
    """Converts inline nodes to XML markup for ReportLab Paragraph."""
    if isinstance(node, NavigableString):
        txt = _esc(str(node))
        if not txt:
            return ""
        if bold and italic:
            return f"<b><i>{txt}</i></b>"
        if bold:
            return f"<b>{txt}</b>"
        if italic:
            return f"<i>{txt}</i>"
        if underline:
            return f"<u>{txt}</u>"
        if mono:
            return f"<font name='{FONT_MONO}'>{txt}</font>"
        return txt

    if not isinstance(node, Tag):
        return ""

    tag = node.name.lower() if node.name else ""
    if tag in TAGS_IGNORE:
        return ""
    if tag == "br":
        return "<br/>"
    if tag in ("b", "strong"):
        bold = True
    if tag in ("i", "em"):
        italic = True
    if tag == "u":
        underline = True
    if tag in ("code", "tt"):
        mono = True

    return "".join(_inline_xml(child, bold, italic, underline, mono) for child in node.children)


def _inline_image(src, cid_images, max_w=CONTENT_W, max_h=350):
    """Loads an image from a data: URI or cid: reference and returns an Image flowable, or None."""
    data = None
    try:
        if src.startswith("data:"):
            m = re.match(r"data:[^;]+;base64,(.+)", src, re.DOTALL)
            if m:
                data = base64.b64decode(m.group(1))
        elif src.startswith("cid:"):
            cid = src[4:].strip()
            if cid in cid_images:
                data, _ = cid_images[cid]
        if not data:
            return None
        img   = PILImage.open(BytesIO(data)).convert("RGB")
        ratio = min(max_w / img.width, max_h / img.height, 1.0)
        w, h  = img.width * ratio, img.height * ratio
        buf   = BytesIO()
        img.save(buf, format="JPEG", quality=85)
        buf.seek(0)
        return Image(buf, width=w, height=h)
    except Exception:
        return None


def _table_rl(table_node, cid_images):
    """Converts a <table> element into a ReportLab Table."""
    trs = []

    def collect(node, is_header=False):
        for child in node.children:
            if not isinstance(child, Tag):
                continue
            t = child.name.lower()
            if t == "tr":
                trs.append((child, is_header))
            elif t == "thead":
                collect(child, True)
            elif t in ("tbody", "tfoot"):
                collect(child, False)

    collect(table_node)
    if not trs:
        return None

    max_cols = max(
        sum(1 for c in tr.children if isinstance(c, Tag) and c.name in ("td", "th"))
        for tr, _ in trs
    ) or 1
    col_w = CONTENT_W / max_cols

    table_data, styles = [], [
        ("FONTNAME",      (0, 0), (-1, -1), FONT),
        ("FONTSIZE",      (0, 0), (-1, -1), 8),
        ("LEADING",       (0, 0), (-1, -1), 11),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ("GRID",          (0, 0), (-1, -1), 0.5, BORDER_COLOR),
    ]

    for i, (tr, is_hdr) in enumerate(trs):
        cells = [c for c in tr.children if isinstance(c, Tag) and c.name in ("td", "th")]
        row = []
        for j, cell in enumerate(cells):
            is_header_cell = is_hdr or cell.name == "th"
            if is_header_cell:
                styles += [
                    ("BACKGROUND", (j, i), (j, i), BLUE_BG),
                    ("FONTNAME",   (j, i), (j, i), FONT_BOLD),
                ]
            txt  = "".join(_inline_xml(child) for child in cell.children).strip() or " "
            cell_style = ParagraphStyle(
                "tc",
                fontName=FONT_BOLD if is_header_cell else FONT,
                fontSize=8, leading=11, wordWrap="CJK",
            )
            row.append(Paragraph(txt, cell_style))
        while len(row) < max_cols:
            row.append(Paragraph(" ", STYLE_NORMAL))
        table_data.append(row)

    t = Table(table_data, colWidths=[col_w] * max_cols, repeatRows=1)
    t.setStyle(TableStyle(styles))
    return t


def html_to_flowables(html, cid_images=None):
    if cid_images is None:
        cid_images = {}

    soup = BeautifulSoup(html, "html.parser")
    body = soup.find("body") or soup
    result = []

    def proc(node):
        if isinstance(node, NavigableString):
            txt = str(node).strip()
            if txt:
                result.append(Paragraph(_esc(txt), STYLE_NORMAL))
            return

        if not isinstance(node, Tag):
            return

        tag = node.name.lower() if node.name else ""
        if tag in TAGS_IGNORE:
            return

        # Image
        if tag == "img":
            src    = node.get("src", "")
            img_rl = _inline_image(src, cid_images)
            if img_rl:
                result.append(Spacer(1, 4))
                result.append(img_rl)
                result.append(Spacer(1, 4))
            return

        # Table
        if tag == "table":
            tab = _table_rl(node, cid_images)
            if tab:
                result.append(Spacer(1, 4))
                result.append(tab)
                result.append(Spacer(1, 6))
            return

        # Headings
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            style_map = {"h1": STYLE_H1, "h2": STYLE_H2, "h3": STYLE_H3}
            style     = style_map.get(tag, STYLE_H3)
            txt       = "".join(_inline_xml(child) for child in node.children).strip()
            if txt:
                result.append(Paragraph(txt, style))
            return

        # Lists
        if tag in ("ul", "ol"):
            for child in node.children:
                if isinstance(child, Tag) and child.name == "li":
                    txt    = "".join(_inline_xml(f) for f in child.children).strip()
                    prefix = "• " if tag == "ul" else "‣ "
                    if txt:
                        result.append(Paragraph(prefix + txt, STYLE_LI))
            return

        # Blockquote
        if tag == "blockquote":
            style_q = ParagraphStyle("bq", parent=STYLE_NORMAL, leftIndent=20,
                                     textColor=colors.HexColor("#444444"))
            txt = "".join(_inline_xml(child) for child in node.children).strip()
            if txt:
                result.append(Paragraph(txt, style_q))
            return

        # Pre
        if tag == "pre":
            for line in node.get_text().splitlines():
                result.append(Paragraph(_esc(line) or " ", STYLE_MONO))
            return

        # HR
        if tag == "hr":
            result.append(HRFlowable(width="100%", thickness=0.5,
                                     color=colors.HexColor("#cccccc")))
            return

        # BR
        if tag == "br":
            result.append(Spacer(1, 4))
            return

        # Paragraphs / divs
        if tag in ("p", "div", "section", "article"):
            has_block = any(
                isinstance(child, Tag) and child.name in TAGS_BLOCK | {"img", "table"}
                for child in node.children
            )
            if has_block:
                for child in node.children:
                    proc(child)
            else:
                txt = "".join(_inline_xml(child) for child in node.children).strip()
                if txt:
                    result.append(Paragraph(txt, STYLE_NORMAL))
                else:
                    result.append(Spacer(1, 4))
            return

        # Everything else: recurse into children
        for child in node.children:
            proc(child)

    for child in body.children:
        proc(child)

    return result


def text_to_flowables(text):
    result = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            result.append(Paragraph(_esc(line), STYLE_NORMAL))
        else:
            result.append(Spacer(1, 4))
    return result


# ---------------------------------------------------------------------------
# PDF generation
# ---------------------------------------------------------------------------

def create_email_pdf(info, output_path):
    doc = SimpleDocTemplate(
        output_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    flowables = []

    # Title
    flowables.append(Paragraph("Email — Legal Process Document", STYLE_TITLE))
    flowables.append(Spacer(1, 0.2 * cm))
    flowables.append(HRFlowable(width="100%", thickness=2, color=DARK_BLUE))
    flowables.append(Spacer(1, 0.4 * cm))

    # Header table
    rows = [["From:", info["from"]], ["To:", info["to"]]]
    if info.get("cc"):
        rows.append(["CC:", info["cc"]])
    rows += [["Date:", info["date_str"]], ["Subject:", info["subject"]]]

    header_table = Table(
        [[Paragraph(f"<b>{label}</b>", STYLE_LABEL), Paragraph(_esc(value), STYLE_NORMAL)]
         for label, value in rows],
        colWidths=[2.2 * cm, CONTENT_W - 2.2 * cm],
    )
    header_table.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("BACKGROUND",    (0, 0), (0, -1),  BLUE_BG),
        ("ROWBACKGROUNDS",(0, 0), (-1, -1), [GRAY_BG, colors.white]),
        ("BOX",           (0, 0), (-1, -1), 0.5, BORDER_COLOR),
        ("INNERGRID",     (0, 0), (-1, -1), 0.25, colors.HexColor("#e0e0e0")),
        ("TOPPADDING",    (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING",   (0, 0), (-1, -1), 6),
    ]))
    flowables.append(header_table)
    flowables.append(Spacer(1, 0.4 * cm))

    # Divider + body
    flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#9e9e9e")))
    flowables.append(Spacer(1, 0.2 * cm))
    flowables.append(Paragraph("<b>Email Body</b>", STYLE_LABEL))
    flowables.append(Spacer(1, 0.3 * cm))
    flowables.extend(info["body_flowables"])

    # Attachments list
    if info["attachments"]:
        flowables.append(Spacer(1, 0.4 * cm))
        flowables.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#9e9e9e")))
        flowables.append(Spacer(1, 0.2 * cm))
        names = ", ".join(a["name"] for a in info["attachments"])
        flowables.append(
            Paragraph(f"<b>Attachments ({len(info['attachments'])}):</b> {_esc(names)}", STYLE_LABEL)
        )

    doc.build(flowables)


# ---------------------------------------------------------------------------
# Embed attachments
# ---------------------------------------------------------------------------

def _image_to_pdf_bytes(data):
    try:
        img   = PILImage.open(BytesIO(data)).convert("RGB")
        mg    = 1.5 * cm
        ratio = min((PAGE_W - 2*mg) / img.width, (PAGE_H - 2*mg) / img.height, 1.0)
        nw, nh = int(img.width * ratio), int(img.height * ratio)
        img    = img.resize((nw, nh))
        ib = BytesIO()
        img.save(ib, format="JPEG", quality=85)
        ib.seek(0)
        pb = BytesIO()
        SimpleDocTemplate(pb, pagesize=A4, leftMargin=mg, rightMargin=mg,
                          topMargin=mg, bottomMargin=mg).build([Image(ib, nw, nh)])
        pb.seek(0)
        return pb.read()
    except Exception:
        return None


def _separator_page(name, file_type):
    buf  = BytesIO()
    st1  = ParagraphStyle("s1", fontName=FONT_BOLD, fontSize=11, textColor=DARK_BLUE)
    st2  = ParagraphStyle("s2", fontName=FONT, fontSize=9, textColor=GRAY_TEXT)
    SimpleDocTemplate(buf, pagesize=A4).build([
        Spacer(1, 8*cm),
        HRFlowable(width="100%", thickness=2, color=DARK_BLUE),
        Spacer(1, 0.5*cm),
        Paragraph(f"ATTACHMENT — {file_type}", st1),
        Spacer(1, 0.3*cm),
        Paragraph(_esc(name), st2),
        Spacer(1, 0.5*cm),
        HRFlowable(width="100%", thickness=2, color=DARK_BLUE),
    ])
    buf.seek(0)
    return buf


def _notice_page(name, file_type, error=""):
    buf  = BytesIO()
    st1  = ParagraphStyle("a1", fontName=FONT_BOLD, fontSize=10,
                           textColor=colors.HexColor("#b71c1c"))
    st2  = ParagraphStyle("a2", fontName=FONT, fontSize=9)
    SimpleDocTemplate(buf, pagesize=A4).build([
        Spacer(1, 8*cm),
        Paragraph(f"NON-RENDERABLE ATTACHMENT: {_esc(name)}", st1),
        Spacer(1, 0.3*cm),
        Paragraph(error or f"Type '{file_type}' cannot be rendered directly in the PDF.", st2),
        Paragraph("The original file is preserved in the source .eml.", st2),
    ])
    buf.seek(0)
    return buf


def embed_attachments(main_pdf, attachments, final_path):
    writer = PdfWriter()
    for page in PdfReader(main_pdf).pages:
        writer.add_page(page)

    for attachment in attachments:
        name, data, file_type = attachment["name"], attachment["data"], attachment["type"].lower()
        try:
            if "pdf" in file_type or name.lower().endswith(".pdf"):
                for page in [PdfReader(_separator_page(name, "PDF")).pages[0]]:
                    writer.add_page(page)
                for page in PdfReader(BytesIO(data)).pages:
                    writer.add_page(page)
            elif file_type.startswith("image/") or name.lower().endswith(
                    (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".webp")):
                pb = _image_to_pdf_bytes(data)
                if pb:
                    writer.add_page(PdfReader(_separator_page(name, "Image")).pages[0])
                    for page in PdfReader(BytesIO(pb)).pages:
                        writer.add_page(page)
            else:
                writer.add_page(PdfReader(_notice_page(name, file_type)).pages[0])
        except Exception as e:
            try:
                writer.add_page(PdfReader(_notice_page(name, file_type, str(e))).pages[0])
            except Exception:
                pass

    with open(final_path, "wb") as f:
        writer.write(f)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

def process_eml(eml_path, output_dir):
    with open(eml_path, "rb") as f:
        msg = email.message_from_binary_file(f, policy=email.policy.compat32)

    date_dt   = extract_date(msg)
    subject   = decode_header_value(msg.get("Subject", "(no subject)"))
    sender    = decode_header_value(msg.get("From", ""))
    recipient = decode_header_value(msg.get("To", ""))
    cc        = decode_header_value(msg.get("Cc", ""))

    body_html, body_text, cid_images = extract_body(msg)
    attachments = extract_attachments(msg)

    if date_dt == datetime.min:
        date_str_file    = "0000-00-00_000000"
        date_str_display = "Date not found"
    else:
        date_str_file    = date_dt.strftime("%Y-%m-%d_%H%M%S")
        date_str_display = date_dt.strftime("%d/%m/%Y %H:%M:%S %Z")

    pdf_name   = sanitize_name(subject, 60)
    final_path = os.path.join(output_dir, f"{date_str_file}_{pdf_name}.pdf")

    if body_html:
        body_flowables = html_to_flowables(body_html, cid_images)
    elif body_text:
        body_flowables = text_to_flowables(body_text)
    else:
        body_flowables = [Paragraph("(no content)", STYLE_NORMAL)]

    info = {
        "from": sender, "to": recipient, "cc": cc,
        "date_str": date_str_display, "subject": subject,
        "body_flowables": body_flowables,
        "attachments": attachments,
    }

    with tempfile.TemporaryDirectory() as tmp:
        main_pdf = os.path.join(tmp, "email.pdf")
        create_email_pdf(info, main_pdf)
        if attachments:
            embed_attachments(main_pdf, attachments, final_path)
        else:
            import shutil
            shutil.copy(main_pdf, final_path)

    return final_path


def main():
    parser = argparse.ArgumentParser(
        description="Converts .eml files to PDFs preserving HTML formatting.")
    parser.add_argument("--input",  "-i", default=".",                help="Folder with .eml files")
    parser.add_argument("--output", "-o", default="./generated_pdfs", help="Output folder")
    args = parser.parse_args()

    input_dir  = Path(args.input)
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(input_dir.glob("*.eml"))
    if not files:
        print(f"❌ No .eml files found in: {input_dir.resolve()}")
        sys.exit(1)

    print(f"\n📂 Input  : {input_dir.resolve()}")
    print(f"📂 Output : {output_dir.resolve()}")
    print(f"📧 Emails : {len(files)}\n" + "-" * 60)

    ok = errors = 0
    for eml in files:
        print(f"  ⏳  {eml.name}")
        try:
            pdf = process_eml(str(eml), str(output_dir))
            print(f"  ✅  → {Path(pdf).name}\n")
            ok += 1
        except Exception as ex:
            print(f"  ❌  Error: {ex}\n")
            errors += 1

    print("-" * 60)
    print(f"\n✅ Done! {ok} PDF(s) generated  |  {errors} error(s)\n")


if __name__ == "__main__":
    main()
