"""
Professional Letter Builder (Streamlit)
---------------------------------------
Generates ATS-friendly, downloadable PDF letters:
Cover Letter, Application Letter, Letter of Motivation,
Statement of Purpose and Personal Statement.

Run locally:   streamlit run app.py
Deploy:        push app.py + requirements.txt to GitHub, then deploy on Streamlit Community Cloud.
"""

import io
import re
from datetime import datetime
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

import numpy as np
import streamlit as st
from PIL import Image, ImageFilter, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

TIMEZONE = "Africa/Nairobi"

# ----------------------------------------------------------------------------
# Letter types: which sections are on by default for each one
# ----------------------------------------------------------------------------
LETTER_TYPES = {
    "Cover Letter": {
        "address": True,
        "salutation": True,
        "closing": True,
        "re": "Application for the Position of Registered Nurse",
        "hint": "Open with the role you are applying for, highlight 2-3 relevant achievements, "
        "and close with a call to action.",
    },
    "Application Letter": {
        "address": True,
        "salutation": True,
        "closing": True,
        "re": "Application for the Position of Registered Nurse",
        "hint": "State the position and where you saw it advertised, summarise your qualifications, "
        "and request an interview.",
    },
    "Letter of Motivation": {
        "address": True,
        "salutation": True,
        "closing": True,
        "re": "Letter of Motivation for [Programme / Position]",
        "hint": "Explain why you want this opportunity, what you bring, and how it fits your goals.",
    },
    "Statement of Purpose": {
        "address": False,
        "salutation": False,
        "closing": False,
        "re": "Statement of Purpose for [Programme]",
        "hint": "Cover your academic/professional background, your goals, and why this "
        "programme and institution are the right fit.",
    },
    "Personal Statement": {
        "address": False,
        "salutation": False,
        "closing": False,
        "re": "Personal Statement",
        "hint": "Tell your story: motivation, key experiences, strengths and future aspirations.",
    },
}

SALUTATIONS = [
    "Dear Hiring Manager,",
    "Dear Sir/Madam,",
    "Dear Recruitment Officer,",
    "Dear Admissions Committee,",
    "Custom...",
]
CLOSINGS = ["Yours faithfully,", "Yours sincerely,"]


# ----------------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------------
def today_string() -> str:
    """Today's date based on the current calendar date (Nairobi time)."""
    now = datetime.now(ZoneInfo(TIMEZONE))
    return f"{now.day} {now:%B %Y}"


def safe_text(value: str) -> str:
    """Escape for ReportLab's mini-markup and normalise odd whitespace."""
    value = (value or "").replace("\u00a0", " ").replace("\t", " ")
    return escape(value.strip())


def process_signature(data: bytes) -> Image.Image:
    """
    Turn a photo of a signature into a clean, black-on-transparent, tightly
    cropped image: flattens uneven lighting, removes the paper background,
    forces ink to black, then crops to the ink with a small margin.
    """
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        flat.alpha_composite(rgba)
        img = flat
    gray = img.convert("L")
    gray.thumbnail((1600, 1600))

    # Estimate paper background (handles shadows / uneven lighting)
    w, h = gray.size
    small = gray.resize((max(1, w // 8), max(1, h // 8)))
    small = small.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(4))
    background = np.asarray(small.resize((w, h), Image.BILINEAR), dtype=np.float32)

    pixels = np.asarray(gray, dtype=np.float32)
    normalised = np.clip(pixels / np.maximum(background, 1.0) * 255.0, 0, 255)
    ink = 255.0 - normalised
    alpha = np.clip((ink - 35.0) * 4.0, 0, 255).astype(np.uint8)

    mask = alpha > 80
    if not mask.any():
        raise ValueError("No signature strokes detected. Use a dark pen on white paper.")

    ys, xs = np.where(mask)
    pad_x = max(4, int((xs.max() - xs.min()) * 0.04))
    pad_y = max(4, int((ys.max() - ys.min()) * 0.10))
    x0, x1 = max(0, xs.min() - pad_x), min(w, xs.max() + pad_x + 1)
    y0, y1 = max(0, ys.min() - pad_y), min(h, ys.max() + pad_y + 1)

    out = np.zeros((h, w, 4), dtype=np.uint8)  # black ink, variable alpha
    out[..., 3] = alpha
    return Image.fromarray(out, "RGBA").crop((x0, y0, x1, y1))


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def build_pdf(d: dict) -> bytes:
    """Build the letter PDF. Uses real text and standard fonts, so ATS can parse it."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f"{d['letter_type']} - {d['name']}",
        author=d["name"],
    )

    def style(name, **over):
        props = dict(fontName="Helvetica", fontSize=10.5, leading=15, textColor=colors.black)
        props.update(over)
        return ParagraphStyle(name, **props)

    s_name = style("name", fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_CENTER)
    s_sub = style("sub", alignment=TA_CENTER)
    s_left = style("left", alignment=TA_LEFT)
    s_bold = style("bold", fontName="Helvetica-Bold", alignment=TA_LEFT)
    s_re = style("re", fontName="Helvetica-Bold", alignment=TA_CENTER)
    s_body = style("body", alignment=TA_JUSTIFY, leading=16, spaceAfter=20)  # 1.5 line spacing after each paragraph

    story = []

    # Header (centred, same details as the CV)
    story.append(Paragraph(safe_text(d["name"]).upper(), s_name))
    if d["headline"]:
        story.append(Paragraph(safe_text(d["headline"]), s_sub))
    contact = " | ".join(safe_text(x) for x in (d["phone"], d["email"], d["location"]) if x.strip())
    if contact:
        story.append(Paragraph(contact, s_sub))
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.black, spaceAfter=14))

    # Date
    story.append(Paragraph(safe_text(d["date"]), s_left))
    story.append(Spacer(1, 12))

    # Recipient address block (left, one entry per line)
    if d["include_address"]:
        entries = [
            x.strip().rstrip(",.;:")
            for x in (d["rec_name"], d["rec_institution"], d["rec_address"], d["rec_city"])
            if x.strip()
        ]
        if entries:
            # Standard address form: comma after every line, full stop after the last
            lines = ["To,"] + [
                safe_text(e) + ("." if i == len(entries) - 1 else ",")
                for i, e in enumerate(entries)
            ]
            story.append(Paragraph("<br/>".join(lines), s_left))
            story.append(Spacer(1, 14))

    # Salutation
    if d["include_salutation"] and d["salutation"].strip():
        story.append(Paragraph(safe_text(d["salutation"]), s_left))
        story.append(Spacer(1, 10))

    # RE: line (centred)
    if d["re_line"].strip():
        story.append(Paragraph(f"RE: {safe_text(d['re_line']).upper()}", s_re))
        story.append(Spacer(1, 12))

    # Body (justified / block); blank line = new paragraph
    paragraphs = [p for p in re.split(r"\n\s*\n", d["body"].strip()) if p.strip()]
    for p in paragraphs:
        story.append(Paragraph("<br/>".join(safe_text(line) for line in p.split("\n")), s_body))

    # Closing block: Yours faithfully -> signature -> name -> title
    if d["include_closing"]:
        block = [Spacer(1, 8), Paragraph(safe_text(d["closing"]), s_left), Spacer(1, 6)]
        if d["signature_png"]:
            with Image.open(io.BytesIO(d["signature_png"])) as im:
                iw, ih = im.size
            scale = min((3.2 * cm) / iw, (1.3 * cm) / ih)
            sig = RLImage(io.BytesIO(d["signature_png"]), width=iw * scale, height=ih * scale)
            sig.hAlign = "LEFT"
            block.append(sig)
        else:
            block.append(Spacer(1, 1.0 * cm))
        block.append(Spacer(1, 4))
        block.append(Paragraph(safe_text(d["sign_name"]), s_bold))
        if d["sign_title"].strip():
            block.append(Paragraph(safe_text(d["sign_title"]), s_left))
        story.append(KeepTogether(block))

    doc.build(story)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# UI
# ----------------------------------------------------------------------------
def main() -> None:
    st.set_page_config(page_title="Letter Builder", page_icon="✉️", layout="centered")
    st.title("✉️ Professional Letter Builder")
    st.caption("Create an ATS-friendly letter and download it as a PDF.")

    letter_type = st.selectbox("Letter type", list(LETTER_TYPES), key="letter_type")
    cfg = LETTER_TYPES[letter_type]
    k = letter_type.replace(" ", "_")  # per-type widget keys so defaults refresh on change

    # --- Personal details (header) -----------------------------------------
    st.subheader("1. Your details (letter heading)")
    name = st.text_input("Full name", "Kipngetich Lawrence", key="name")
    headline = st.text_input(
        "Professional headline",
        "Registered Nurse | BSc Nursing and Public Health",
        key="headline",
    )
    c1, c2, c3 = st.columns(3)
    phone = c1.text_input("Phone", "+254 768 263 623", key="phone")
    email = c2.text_input("Email", "Lawnetich15351@gmail.com", key="email")
    location = c3.text_input("Location", "Kapsabet, Kenya", key="location")

    # --- Date ---------------------------------------------------------------
    st.subheader("2. Date")
    date_str = today_string()
    st.text_input("Date (automatic, today's date)", date_str, disabled=True)

    # --- Recipient ----------------------------------------------------------
    st.subheader("3. Recipient address")
    include_address = st.checkbox("Include recipient address", cfg["address"], key=f"addr_{k}")
    rec_name = rec_institution = rec_address = rec_city = ""
    if include_address:
        rec_name = st.text_input("Name of person addressed", key=f"rn_{k}")
        rec_institution = st.text_input("Institution", key=f"ri_{k}")
        rec_address = st.text_input("Address", key=f"ra_{k}")
        rec_city = st.text_input("City / State", key=f"rc_{k}")

    # --- Salutation ---------------------------------------------------------
    st.subheader("4. Salutation")
    include_salutation = st.checkbox("Include salutation", cfg["salutation"], key=f"sal_on_{k}")
    salutation = ""
    if include_salutation:
        choice = st.selectbox("Salutation", SALUTATIONS, key=f"sal_{k}")
        salutation = (
            st.text_input("Custom salutation", "Dear Dr. ...,", key=f"sal_c_{k}")
            if choice == "Custom..."
            else choice
        )

    # --- RE line ------------------------------------------------------------
    st.subheader("5. RE: (subject line)")
    re_line = st.text_input("Subject (printed centred after 'RE:')", cfg["re"], key=f"re_{k}")

    # --- Body ---------------------------------------------------------------
    st.subheader("6. Body")
    st.caption(cfg["hint"] + " Leave a blank line between paragraphs.")
    body = st.text_area("Letter body", height=320, key=f"body_{k}")

    # --- Closing ------------------------------------------------------------
    st.subheader("7. Closing and signature")
    include_closing = st.checkbox("Include closing and signature", cfg["closing"], key=f"clo_on_{k}")
    closing, sign_name, sign_title, signature_png = "", name, "", None
    if include_closing:
        default_closing = 1 if salutation and not re.search(
            r"sir|madam|hiring|recruitment|committee", salutation, re.I
        ) else 0
        closing = st.selectbox("Closing", CLOSINGS, index=default_closing, key=f"cl_{k}_{salutation}")

        sig_file = st.file_uploader(
            "Upload signature (photo of a black-ink signature on white paper)",
            type=["png", "jpg", "jpeg", "webp"],
            key="sig",
        )
        if sig_file is not None:
            try:
                sig_img = process_signature(sig_file.getvalue())
                signature_png = image_to_png_bytes(sig_img)
                st.image(signature_png, caption="Cleaned and cropped signature", width=220)
            except Exception as exc:  # noqa: BLE001 - show friendly message to the user
                st.error(f"Could not process the signature: {exc}")

        sign_name = st.text_input("Name (printed under signature)", name, key=f"sn_{name}")
        sign_title = st.text_input(
            "Title (below name)", "Registered Nurse", key=f"st_{k}"
        )

    # --- Generate -----------------------------------------------------------
    st.divider()
    problems = []
    if not name.strip():
        problems.append("Enter your full name.")
    if not body.strip():
        problems.append("Write the body of the letter.")
    if include_closing and not sign_name.strip():
        problems.append("Enter the name for the signature block.")
    for p in problems:
        st.warning(p)

    if not problems:
        try:
            pdf_bytes = build_pdf(
                dict(
                    letter_type=letter_type, name=name, headline=headline, phone=phone,
                    email=email, location=location, date=date_str,
                    include_address=include_address, rec_name=rec_name,
                    rec_institution=rec_institution, rec_address=rec_address, rec_city=rec_city,
                    include_salutation=include_salutation, salutation=salutation,
                    re_line=re_line, body=body, include_closing=include_closing,
                    closing=closing, signature_png=signature_png,
                    sign_name=sign_name, sign_title=sign_title,
                )
            )
            file_name = re.sub(r"[^A-Za-z0-9]+", "_", f"{name}_{letter_type}").strip("_") + ".pdf"
            st.download_button(
                "⬇️ Download PDF",
                data=pdf_bytes,
                file_name=file_name,
                mime="application/pdf",
                type="primary",
                use_container_width=True,
            )
        except Exception as exc:  # noqa: BLE001
            st.error(f"Could not create the PDF: {exc}")


if __name__ == "__main__":
    main()
