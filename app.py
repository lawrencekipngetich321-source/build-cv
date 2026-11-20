"""
Professional Letter Builder
Run with: streamlit run app.py

Dependencies:
    pip install streamlit reportlab pillow
"""

from datetime import date
from io import BytesIO
import re

import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    KeepTogether, HRFlowable
)
from reportlab.pdfbase.pdfmetrics import stringWidth
from xml.sax.saxutils import escape


# -------------------------------------------------------------------
# 1. PAGE CONFIGURATION AND DEFAULT CV HEADER DETAILS
# -------------------------------------------------------------------

st.set_page_config(
    page_title="Professional Letter Builder",
    page_icon="✉️",
    layout="wide"
)

DEFAULT_NAME = "KIPNGETICH LAWRENCE"
DEFAULT_TITLE = "Registered Nurse | BSc Nursing and Public Health"
DEFAULT_CONTACT = "+254 768 263 623 | Lawnetich15351@gmail.com | Kapsabet, Kenya"

LETTER_TYPES = [
    "Cover Letter",
    "Application Letter",
    "Letter of Motivation",
    "Statement of Purpose",
    "Personal Statement",
]

SALUTATIONS = [
    "Dear Hiring Manager,",
    "Dear Sir/Madam,",
    "Dear [Recipient Name],",
    "Dear Admissions Committee,",
    "Dear Selection Committee,",
    "To Whom It May Concern,",
    "Custom salutation",
]


# -------------------------------------------------------------------
# 2. HELPERS
# -------------------------------------------------------------------

def clean_text(value: str) -> str:
    """Normalize user-entered text without changing its meaning."""
    return (value or "").strip()


def prepare_signature(uploaded_file):
    """
    Prepare a legible black signature:
    - correct image orientation
    - convert to grayscale
    - increase contrast
    - remove light background
    - crop to the visible ink with a small margin
    Returns a PNG stream or None.
    """
    if uploaded_file is None:
        return None

    try:
        image = Image.open(uploaded_file)
        image = ImageOps.exif_transpose(image).convert("RGB")

        # White background and grayscale improve consistency in the PDF.
        gray = ImageOps.grayscale(image)
        gray = ImageEnhance.Contrast(gray).enhance(2.2)

        # Turn dark signature strokes into black and background into white.
        threshold = 205
        bw = gray.point(lambda px: 0 if px < threshold else 255, mode="1").convert("L")

        # Find the ink area. The signature is expected to be darker than paper.
        inverted = ImageOps.invert(bw)
        bbox = inverted.point(lambda px: 255 if px > 0 else 0).getbbox()

        if bbox:
            left, top, right, bottom = bbox
            pad_x = max(12, int((right - left) * 0.06))
            pad_y = max(10, int((bottom - top) * 0.18))
            left = max(0, left - pad_x)
            top = max(0, top - pad_y)
            right = min(bw.width, right + pad_x)
            bottom = min(bw.height, bottom + pad_y)
            bw = bw.crop((left, top, right, bottom))

        # Keep the signature crisp and reasonably sized.
        if bw.width > 1600:
            new_height = int(bw.height * (1600 / bw.width))
            bw = bw.resize((1600, new_height), Image.Resampling.LANCZOS)

        output = BytesIO()
        bw.save(output, format="PNG", optimize=True)
        output.seek(0)
        return output
    except Exception:
        return None


def paragraph_text(text: str) -> str:
    """Escape plain text safely for ReportLab Paragraph markup."""
    return escape(text).replace("\n", "<br/>")


def build_pdf(data: dict, signature_stream: BytesIO | None) -> bytes:
    """Create a clean, ATS-friendly A4 PDF letter."""
    output = BytesIO()

    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        rightMargin=25 * mm,
        leftMargin=25 * mm,
        topMargin=17 * mm,
        bottomMargin=20 * mm,
        title=f"{data['letter_type']} - {data['sender_name']}",
        author=data["sender_name"],
        subject=data["subject"],
    )

    styles = getSampleStyleSheet()
    header_name = ParagraphStyle(
        "HeaderName", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=15, leading=18, alignment=TA_CENTER, spaceAfter=3
    )
    header_title = ParagraphStyle(
        "HeaderTitle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9.5, leading=12, alignment=TA_CENTER, spaceAfter=2
    )
    header_contact = ParagraphStyle(
        "HeaderContact", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=11, alignment=TA_CENTER, spaceAfter=7
    )
    date_style = ParagraphStyle(
        "Date", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=10
    )
    address_style = ParagraphStyle(
        "Address", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=0
    )
    subject_style = ParagraphStyle(
        "Subject", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=11, leading=15, alignment=TA_CENTER,
        spaceBefore=12, spaceAfter=12
    )
    salutation_style = ParagraphStyle(
        "Salutation", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15, alignment=TA_LEFT, spaceAfter=9
    )
    body_style = ParagraphStyle(
        "Body", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=16, alignment=TA_JUSTIFY,
        spaceAfter=9, allowWidows=0, allowOrphans=0
    )
    closing_style = ParagraphStyle(
        "Closing", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15, alignment=TA_LEFT
    )
    name_style = ParagraphStyle(
        "SenderName", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=14, alignment=TA_LEFT, spaceBefore=3
    )

    story = []

    # Centered CV-style identity header.
    story.append(Paragraph(paragraph_text(data["sender_name"].upper()), header_name))
    if data["sender_title"]:
        story.append(Paragraph(paragraph_text(data["sender_title"]), header_title))
    if data["sender_contact"]:
        story.append(Paragraph(paragraph_text(data["sender_contact"]), header_contact))
    story.append(HRFlowable(
        width="100%", thickness=0.6, color=colors.HexColor("#777777"),
        spaceBefore=1, spaceAfter=12
    ))

    # Automatically populated date, formatted in a professional style.
    story.append(Paragraph(data["date"].strftime("%d %B %Y"), date_style))

    # Recipient address: each entry is a separate line, aligned left.
    address_lines = [
        "<b>TO,</b>",
        paragraph_text(data["recipient_name"]),
        paragraph_text(data["institution"]),
        paragraph_text(data["recipient_address"]),
        paragraph_text(data["city_state"]),
    ]
    address_lines = [line for line in address_lines if line]
    story.append(Paragraph("<br/>".join(address_lines), address_style))
    story.append(Spacer(1, 8))

    # Centered RE line.
    story.append(Paragraph(
        f"RE: {paragraph_text(data['subject'])}",
        subject_style
    ))

    story.append(Paragraph(paragraph_text(data["salutation"]), salutation_style))

    # Body is split into paragraphs on blank lines and justified.
    body_paragraphs = [
        part.strip() for part in re.split(r"\n\s*\n", data["body"].strip())
        if part.strip()
    ]
    for part in body_paragraphs:
        # Preserve intentional single line breaks inside a paragraph.
        story.append(Paragraph(paragraph_text(part), body_style))

    story.append(Spacer(1, 7))
    closing_items = [Paragraph(paragraph_text(data["closing"]), closing_style)]

    if signature_stream is not None:
        signature_stream.seek(0)
        # Image is kept within a modest signature area and preserves aspect ratio.
        signature_image = Image.open(signature_stream)
        max_w, max_h = 43 * mm, 19 * mm
        scale = min(max_w / signature_image.width, max_h / signature_image.height, 1.0)
        draw_w = signature_image.width * scale
        draw_h = signature_image.height * scale
        signature_stream.seek(0)
        closing_items.append(Spacer(1, 2))
        closing_items.append(RLImage(signature_stream, width=draw_w, height=draw_h))
    else:
        closing_items.append(Spacer(1, 18))

    closing_items.append(Paragraph(paragraph_text(data.get("closing_name", data["sender_name"])), name_style))
    if data["sender_title"]:
        closing_items.append(Paragraph(paragraph_text(data["sender_title"]), closing_style))

    story.append(KeepTogether(closing_items))

    def add_page_number(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#666666"))
        canvas.drawRightString(
            A4[0] - 25 * mm, 10 * mm, f"Page {document.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=add_page_number, onLaterPages=add_page_number)
    output.seek(0)
    return output.getvalue()


# -------------------------------------------------------------------
# 3. USER INTERFACE
# -------------------------------------------------------------------

st.title("Professional Letter Builder")
st.caption(
    "Create a clean, professional and ATS-friendly letter, then download it as a PDF."
)

with st.sidebar:
    st.header("Letter type")
    letter_type = st.selectbox("Choose the document", LETTER_TYPES, index=0)
    st.caption("The selected type is used in the PDF document metadata.")

    st.divider()
    st.header("Your CV header")
    sender_name = st.text_input("Your full name", value=DEFAULT_NAME)
    sender_title = st.text_input("Professional title / qualification", value=DEFAULT_TITLE)
    sender_contact = st.text_input("Phone | Email | Location", value=DEFAULT_CONTACT)

    st.info(
        "The name, professional title and contact details are prefilled from "
        "the CV provided. You can edit them before generating the letter."
    )

left, right = st.columns([1, 1], gap="large")

with left:
    st.subheader("1. Recipient details")
    current_date = date.today()
    st.date_input(
        "Date",
        value=current_date,
        disabled=True,
        help="Automatically uses your computer's current calendar date."
    )

    recipient_name = st.text_input(
        "Name of person addressed to",
        placeholder="e.g. Dr. Jane Doe"
    )
    institution = st.text_input(
        "Institution / organization",
        placeholder="e.g. County Referral Hospital"
    )
    recipient_address = st.text_input(
        "Recipient's address",
        placeholder="e.g. P.O. Box 123-50200"
    )
    city_state = st.text_input(
        "City / State",
        placeholder="e.g. Bungoma, Kenya"
    )

    st.subheader("2. Subject / RE")
    subject = st.text_input(
        "RE: (enter the purpose of the letter)",
        placeholder="e.g. APPLICATION FOR THE POSITION OF REGISTERED NURSE"
    )

with right:
    st.subheader("3. Salutation")
    salutation_choice = st.selectbox("Choose salutation", SALUTATIONS, index=0)
    if salutation_choice == "Custom salutation":
        salutation = st.text_input(
            "Enter your salutation",
            placeholder="Dear Hiring Manager,"
        )
    elif salutation_choice == "Dear [Recipient Name],":
        salutation = f"Dear {recipient_name}," if recipient_name else "Dear Recipient,"
    else:
        salutation = salutation_choice

    st.subheader("4. Letter body")
    st.caption(
        "Write in paragraphs. Leave one blank line between paragraphs. "
        "The PDF will use justified block alignment."
    )
    body = st.text_area(
        "Body of the letter",
        height=330,
        placeholder=(
            "Paragraph 1: Introduce yourself and state the purpose of the letter.\n\n"
            "Paragraph 2: Explain your relevant qualifications, experience and skills.\n\n"
            "Paragraph 3: Explain your motivation, suitability and/or intended contribution.\n\n"
            "Final paragraph: Thank the recipient and state your availability for further discussion."
        )
    )

st.divider()
st.subheader("5. Closing and signature")

close_col, sign_col = st.columns([1, 1], gap="large")
with close_col:
    closing = st.selectbox(
        "Closing phrase",
        ["Yours sincerely,", "Yours faithfully,", "Kind regards,"],
        index=0
    )
    signature_name = st.text_input(
        "Name below signature",
        value=sender_name
    )

with sign_col:
    signature_upload = st.file_uploader(
        "Upload signature image (PNG, JPG or JPEG)",
        type=["png", "jpg", "jpeg"],
        help="A clear image of a handwritten signature on a plain, light background works best."
    )
    signature_stream = prepare_signature(signature_upload) if signature_upload else None

    if signature_upload and signature_stream:
        st.image(signature_stream, caption="Signature preview (cropped and cleaned)", width=280)
        signature_stream.seek(0)
    elif signature_upload:
        st.warning("The signature image could not be processed. Try a clearer PNG or JPG image.")

st.divider()

# -------------------------------------------------------------------
# 4. VALIDATION AND PDF DOWNLOAD
# -------------------------------------------------------------------

required_fields = {
    "Your full name": sender_name,
    "Recipient name": recipient_name,
    "Institution": institution,
    "Recipient address": recipient_address,
    "City / State": city_state,
    "RE / subject": subject,
    "Salutation": salutation,
    "Letter body": body,
    "Name below signature": signature_name,
}
missing = [label for label, value in required_fields.items() if not clean_text(value)]

preview_data = {
    "letter_type": letter_type,
    "sender_name": clean_text(sender_name),
    "sender_title": clean_text(sender_title),
    "sender_contact": clean_text(sender_contact),
    "date": current_date,
    "recipient_name": clean_text(recipient_name),
    "institution": clean_text(institution),
    "recipient_address": clean_text(recipient_address),
    "city_state": clean_text(city_state),
    "subject": clean_text(subject),
    "salutation": clean_text(salutation),
    "body": clean_text(body),
    "closing": clean_text(closing),
    "closing_name": clean_text(signature_name),
}

if missing:
    st.info("Complete the following fields to enable PDF generation: " + ", ".join(missing))
else:
    try:
        pdf_bytes = build_pdf(preview_data, signature_stream)
        st.download_button(
            label="Download professional letter (PDF)",
            data=pdf_bytes,
            file_name=f"{letter_type.lower().replace(' ', '_')}.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True
        )
        st.success("Your PDF is ready. Review the downloaded document before sending it.")
    except Exception as exc:
        st.error(f"PDF generation failed: {exc}")
        st.caption("Check the entered content and uploaded signature, then try again.")

st.caption(
    "ATS-friendly formatting: selectable text, standard fonts, clear headings, "
    "simple layout and no decorative columns or text boxes in the PDF."
)
