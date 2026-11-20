import io
import re
from datetime import date
from xml.sax.saxutils import escape

import streamlit as st
from PIL import Image, ImageOps, ImageEnhance
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    HRFlowable, KeepTogether
)

# -------------------------------------------------------------------
# PAGE CONFIGURATION
# -------------------------------------------------------------------
st.set_page_config(
    page_title="Professional Letter Builder",
    page_icon="✉️",
    layout="wide"
)

st.title("Professional Letter Builder")
st.caption(
    "Create a clean, ATS-friendly professional letter and download it as a PDF."
)

# -------------------------------------------------------------------
# CV HEADER DETAILS
# These details are taken from the CV supplied with this request.
# Edit them here if your contact details change.
# -------------------------------------------------------------------
DEFAULT_NAME = "KIPNGETICH LAWRENCE"
DEFAULT_PROFESSION = "Registered Nurse | BSc Nursing and Public Health"
DEFAULT_PHONE = "+254 768 263 623"
DEFAULT_EMAIL = "Lawnetich15351@gmail.com"
DEFAULT_LOCATION = "Kapsabet, Kenya"

LETTER_TYPES = [
    "Cover Letter",
    "Application Letter",
    "Letter of Motivation",
    "Statement of Purpose",
    "Personal Statement",
]

SALUTATIONS = [
    "Dear Hiring Manager,",
    "Dear Recruitment Team,",
    "Dear Sir/Madam,",
    "Dear Professor [Surname],",
    "Dear [Recipient Name],",
]

CLOSINGS = ["Yours faithfully,", "Yours sincerely,", "Kind regards,"]

# -------------------------------------------------------------------
# HELPERS
# -------------------------------------------------------------------
def clean_text(value: str) -> str:
    """Normalize line endings and remove unsafe control characters."""
    value = (value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "".join(ch for ch in value if ch in "\n\t" or ord(ch) >= 32).strip()


def prepare_signature(uploaded_file):
    """
    Trim excess white/near-white margins, convert the signature to
    black ink on a white background, and resize it for a legible PDF.
    """
    if uploaded_file is None:
        return None

    try:
        image = Image.open(uploaded_file).convert("RGB")
        image = ImageOps.exif_transpose(image)

        # Convert to grayscale and increase contrast.
        gray = ImageOps.grayscale(image)
        gray = ImageEnhance.Contrast(gray).enhance(2.2)

        # Find the ink area. Pixels darker than this threshold are treated
        # as signature strokes.
        threshold = 220
        mask = gray.point(lambda p: 255 if p < threshold else 0)
        bbox = mask.getbbox()

        if bbox:
            # Add a small margin around the signature so strokes are not cut.
            left, top, right, bottom = bbox
            pad_x = max(8, int((right - left) * 0.04))
            pad_y = max(8, int((bottom - top) * 0.12))
            left = max(0, left - pad_x)
            top = max(0, top - pad_y)
            right = min(gray.width, right + pad_x)
            bottom = min(gray.height, bottom + pad_y)
            gray = gray.crop((left, top, right, bottom))

        # Make the background white and the signature dark/clear.
        gray = gray.point(lambda p: 0 if p < 185 else 255)
        output = Image.new("RGB", gray.size, "white")
        output.paste(Image.merge("RGB", (gray, gray, gray)))

        # Keep a sensible maximum size while preserving proportions.
        output.thumbnail((1400, 500), Image.Resampling.LANCZOS)

        buffer = io.BytesIO()
        output.save(buffer, format="PNG", optimize=True)
        buffer.seek(0)
        return buffer
    except Exception as exc:
        st.error(f"Could not process the signature image: {exc}")
        return None


def add_body_paragraphs(story, body, body_style):
    """Create readable paragraphs while preserving intentional line breaks."""
    paragraphs = [p.strip() for p in clean_text(body).split("\n") if p.strip()]
    if not paragraphs:
        story.append(Paragraph(" ", body_style))
        return

    for paragraph in paragraphs:
        # Escape user text before passing it to ReportLab's paragraph parser.
        safe = escape(paragraph).replace("\t", "&nbsp;&nbsp;&nbsp;&nbsp;")
        story.append(Paragraph(safe, body_style))
        story.append(Spacer(1, 4.2 * mm))


def build_pdf(data, signature_buffer):
    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=24 * mm,
        leftMargin=24 * mm,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title=f"{data['letter_type']} - {data['sender_name']}",
        author=data["sender_name"],
    )

    styles = getSampleStyleSheet()
    header_name = ParagraphStyle(
        "HeaderName", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=15, leading=18, alignment=TA_CENTER, spaceAfter=3
    )
    header_detail = ParagraphStyle(
        "HeaderDetail", parent=styles["Normal"], fontName="Helvetica",
        fontSize=9, leading=12, alignment=TA_CENTER, spaceAfter=2
    )
    date_style = ParagraphStyle(
        "DateStyle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=8
    )
    address_style = ParagraphStyle(
        "AddressStyle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10, leading=14, alignment=TA_LEFT, spaceAfter=1
    )
    salutation_style = ParagraphStyle(
        "SalutationStyle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15, alignment=TA_LEFT, spaceBefore=8, spaceAfter=8
    )
    subject_style = ParagraphStyle(
        "SubjectStyle", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=15, alignment=TA_LEFT, spaceBefore=4, spaceAfter=10
    )
    body_style = ParagraphStyle(
        "BodyStyle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=16, alignment=TA_LEFT,
        spaceAfter=3, splitLongWords=True
    )
    closing_style = ParagraphStyle(
        "ClosingStyle", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=15, alignment=TA_LEFT
    )
    name_style = ParagraphStyle(
        "SenderNameStyle", parent=styles["Normal"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=14, alignment=TA_LEFT, spaceBefore=3
    )

    story = []

    # Centered sender headline/details, matching the supplied CV.
    story.append(Paragraph(escape(data["sender_name"].upper()), header_name))
    story.append(Paragraph(escape(data["profession"]), header_detail))
    contact_line = " | ".join(
        part for part in [
            data["phone"].strip(),
            data["email"].strip(),
            data["location"].strip()
        ] if part
    )
    story.append(Paragraph(escape(contact_line), header_detail))
    story.append(Spacer(1, 5 * mm))
    story.append(HRFlowable(width="100%", thickness=0.7, color=colors.black))
    story.append(Spacer(1, 6 * mm))

    # Automatically generated date based on the current calendar date.
    story.append(Paragraph(escape(data["date"]), date_style))
    story.append(Spacer(1, 1 * mm))

    # Recipient block: each supplied field is on its own line.
    recipient_lines = [
        ("To: ", data["to"]),
        ("", data["recipient_name"]),
        ("", data["institution"]),
        ("", data["address"]),
        ("", data["city_state"]),
    ]
    for label, value in recipient_lines:
        if value.strip():
            story.append(
                Paragraph(
                    f"<b>{escape(label)}</b>{escape(value.strip())}",
                    address_style
                )
            )

    story.append(Spacer(1, 5 * mm))
    story.append(Paragraph(escape(data["salutation"]), salutation_style))

    # Subject / RE line in its own distinct paragraph.
    if data["subject"].strip():
        story.append(Paragraph(
            f"<b>RE: {escape(data['subject'].strip())}</b>",
            subject_style
        ))

    add_body_paragraphs(story, data["body"], body_style)
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(escape(data["closing"]), closing_style))
    story.append(Spacer(1, 2 * mm))

    if signature_buffer is not None:
        signature_buffer.seek(0)
        signature_image = Image.open(signature_buffer).convert("RGB")
        sig_io = io.BytesIO()
        signature_image.save(sig_io, format="PNG")
        sig_io.seek(0)

        # Fit within a compact signature area without stretching.
        sig_width, sig_height = signature_image.size
        max_width, max_height = 48 * mm, 19 * mm
        scale = min(max_width / sig_width, max_height / sig_height, 1.0)
        story.append(RLImage(
            sig_io,
            width=sig_width * scale,
            height=sig_height * scale
        ))
        story.append(Spacer(1, 1 * mm))

    if data["sender_signature_name"].strip():
        story.append(Paragraph(
            escape(data["sender_signature_name"].strip()), name_style
        ))

    doc.build(story)
    buffer.seek(0)
    return buffer


# -------------------------------------------------------------------
# INPUT FORM
# -------------------------------------------------------------------
with st.form("letter_builder_form"):
    st.subheader("1. Choose your letter type")
    letter_type = st.selectbox("Letter type", LETTER_TYPES)

    st.subheader("2. Sender details — centered at the top")
    col1, col2 = st.columns(2)
    with col1:
        sender_name = st.text_input("Your full name", value=DEFAULT_NAME)
        phone = st.text_input("Telephone", value=DEFAULT_PHONE)
        location = st.text_input("Your location", value=DEFAULT_LOCATION)
    with col2:
        profession = st.text_input("Professional headline", value=DEFAULT_PROFESSION)
        email = st.text_input("Email address", value=DEFAULT_EMAIL)
        current_date = st.date_input(
            "Letter date (automatically set to today)",
            value=date.today(),
            help="The date defaults to the current calendar date. You may change it if needed."
        )

    st.subheader("3. Recipient address — left aligned")
    to_line = st.text_input("To", value="The Hiring Manager")
    recipient_name = st.text_input("Name of person addressed to")
    institution = st.text_input("Institution / organisation")
    recipient_address = st.text_input("Street / postal address")
    city_state = st.text_input("City / State / Country")

    st.subheader("4. Salutation and subject")
    salutation_choice = st.selectbox("Salutation", SALUTATIONS)
    custom_salutation = ""
    if salutation_choice == "Dear [Recipient Name],":
        custom_salutation = st.text_input(
            "Enter the recipient's name",
            placeholder="Dear Dr. Kamau,"
        )
    subject = st.text_input(
        "RE: Subject / position / programme",
        placeholder="Application for the Position of Registered Nurse"
    )

    st.subheader("5. Letter body")
    st.caption(
        "Write in clear paragraphs. Leave a blank line between paragraphs. "
        "Use plain text for the most reliable ATS-readable PDF."
    )
    body = st.text_area(
        "Body of the letter",
        height=300,
        placeholder=(
            "Write your opening paragraph...\n\n"
            "Add your qualifications, relevant experience and motivation...\n\n"
            "Close with a concise statement of interest and availability..."
        )
    )

    st.subheader("6. Closing and signature")
    closing = st.selectbox("Formal closing", CLOSINGS, index=0)
    signature_file = st.file_uploader(
        "Upload your handwritten signature (black ink on a light background)",
        type=["png", "jpg", "jpeg"],
        help="The app trims excess margins and converts the signature to clear black ink."
    )
    sender_signature_name = st.text_input(
        "Your name below the signature",
        value=DEFAULT_NAME
    )

    submitted = st.form_submit_button(
        "Generate downloadable PDF",
        type="primary",
        use_container_width=True
    )

# -------------------------------------------------------------------
# OUTPUT
# -------------------------------------------------------------------
if submitted:
    errors = []
    if not sender_name.strip():
        errors.append("Enter your full name.")
    if not body.strip():
        errors.append("Enter the body of your letter.")
    if not subject.strip():
        errors.append("Enter the RE / subject line.")

    if errors:
        for error in errors:
            st.error(error)
    else:
        if salutation_choice == "Dear [Recipient Name],":
            salutation = custom_salutation.strip() or "Dear Hiring Manager,"
            if not salutation.lower().startswith("dear "):
                salutation = f"Dear {salutation}"
            if not salutation.endswith(","):
                salutation += ","
        else:
            salutation = salutation_choice

        signature_buffer = prepare_signature(signature_file)

        letter_data = {
            "letter_type": letter_type,
            "sender_name": clean_text(sender_name),
            "profession": clean_text(profession),
            "phone": clean_text(phone),
            "email": clean_text(email),
            "location": clean_text(location),
            "date": current_date.strftime("%d %B %Y"),
            "to": clean_text(to_line),
            "recipient_name": clean_text(recipient_name),
            "institution": clean_text(institution),
            "address": clean_text(recipient_address),
            "city_state": clean_text(city_state),
            "salutation": clean_text(salutation),
            "subject": clean_text(subject),
            "body": clean_text(body),
            "closing": clean_text(closing),
            "sender_signature_name": clean_text(sender_signature_name),
        }

        try:
            pdf_file = build_pdf(letter_data, signature_buffer)
            safe_name = re.sub(
                r"[^A-Za-z0-9_-]+", "_", sender_name.strip()
            ).strip("_") or "professional_letter"
            st.success("Your letter PDF is ready.")
            st.download_button(
                label="Download PDF",
                data=pdf_file.getvalue(),
                file_name=f"{safe_name}_{letter_type.lower().replace(' ', '_')}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
        except Exception as exc:
            st.error(f"PDF generation failed. Please check your entries and try again. Details: {exc}")

st.divider()
st.caption(
    "Formatting: A4 page, centered sender heading, left-aligned recipient block, "
    "plain-text paragraphs, consistent spacing and a selectable signature image. "
    "No tables, columns, decorative graphics or text boxes are used in the PDF."
)
