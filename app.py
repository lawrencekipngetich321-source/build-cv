import io
import re
from datetime import date

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from xml.sax.saxutils import escape


# ---------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Professional CV Builder",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded",
)

APP_NAME = "Professional CV Builder"
NAVY = colors.HexColor("#17365D")
BLUE = colors.HexColor("#2F5597")
PALE_BLUE = colors.HexColor("#EAF0F8")
DARK = colors.HexColor("#202A35")
MUTED = colors.HexColor("#5B6573")
LIGHT_LINE = colors.HexColor("#D8DEE8")


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
def lines_to_list(value: str):
    """Convert newline-separated text into a clean list."""
    return [line.strip(" •\t-") for line in (value or "").splitlines() if line.strip(" •\t-")]


def safe(value):
    """Escape user-entered text for ReportLab Paragraph markup."""
    return escape(str(value or "").strip()).replace("\n", "<br/>")


def add_text_field(label, key, default="", help_text=None):
    return st.text_input(label, value=st.session_state.get(key, default), key=key, help=help_text)


def section_title(text):
    return Paragraph(escape(text.upper()), STYLES["section"])


def add_bullet_list(story, items):
    for item in items:
        if item.strip():
            story.append(Paragraph("• " + safe(item), STYLES["bullet"]))


def build_pdf(cv):
    """Create a clean, ATS-friendly A4 PDF using ReportLab."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=17 * mm,
        title=f"{cv['name']} - Curriculum Vitae",
        author=cv["name"],
    )

    story = []

    # Name and professional headline
    story.append(Paragraph(safe(cv["name"]).upper(), STYLES["name"]))
    if cv["headline"]:
        story.append(Paragraph(safe(cv["headline"]), STYLES["headline"]))

    contact_parts = [
        value for value in [
            cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]
        ] if value.strip()
    ]
    if contact_parts:
        story.append(Spacer(1, 4))
        story.append(Paragraph("  |  ".join(safe(x) for x in contact_parts), STYLES["contact"]))

    story.append(Spacer(1, 8))
    story.append(HRFlowable(width="100%", thickness=1.4, color=BLUE, spaceAfter=10))

    # Professional profile
    if cv["profile"].strip():
        story.append(section_title("Professional Profile"))
        story.append(Paragraph(safe(cv["profile"]), STYLES["body"]))
        story.append(Spacer(1, 5))

    # Core competencies
    competencies = lines_to_list(cv["competencies"])
    if competencies:
        story.append(section_title("Core Competencies"))
        # Use a compact two-column table while keeping text selectable.
        rows = []
        midpoint = (len(competencies) + 1) // 2
        left_items, right_items = competencies[:midpoint], competencies[midpoint:]
        for i in range(midpoint):
            left = "• " + safe(left_items[i])
            right = "• " + safe(right_items[i]) if i < len(right_items) else ""
            rows.append([
                Paragraph(left, STYLES["compact"]),
                Paragraph(right, STYLES["compact"]),
            ])
        table = Table(rows, colWidths=[(A4[0] - 36 * mm) / 2] * 2, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 1),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ]))
        story.append(table)
        story.append(Spacer(1, 5))

    # Professional experience
    experience = [item for item in cv["experience"] if item["role"].strip() or item["organisation"].strip()]
    if experience:
        story.append(section_title("Professional Experience"))
        for item in experience:
            heading = f"<b>{safe(item['role'])}</b>"
            organisation_line = " | ".join(
                safe(x) for x in [item["organisation"], item["location"], item["dates"]] if x.strip()
            )
            if organisation_line:
                heading += f"<br/><font color='#5B6573'>{organisation_line}</font>"
            block = [Paragraph(heading, STYLES["job_heading"])]
            if item["summary"].strip():
                block.append(Paragraph(safe(item["summary"]), STYLES["body"]))
            bullets = lines_to_list(item["duties"])
            for duty in bullets:
                block.append(Paragraph("• " + safe(duty), STYLES["bullet"]))
            block.append(Spacer(1, 5))
            story.append(KeepTogether(block))

    # Education
    education = [item for item in cv["education"] if item["qualification"].strip() or item["institution"].strip()]
    if education:
        story.append(section_title("Education"))
        for item in education:
            line = f"<b>{safe(item['qualification'])}</b>"
            details = " | ".join(safe(x) for x in [item["institution"], item["dates"]] if x.strip())
            if details:
                line += f"<br/><font color='#5B6573'>{details}</font>"
            story.append(Paragraph(line, STYLES["body"]))
            if item["details"].strip():
                story.append(Paragraph(safe(item["details"]), STYLES["small"]))
            story.append(Spacer(1, 4))

    # Registration and certifications
    if cv["registration"].strip():
        story.append(section_title("Professional Registration"))
        add_bullet_list(story, lines_to_list(cv["registration"]))
        story.append(Spacer(1, 4))

    if cv["certifications"].strip():
        story.append(section_title("Certifications and Professional Development"))
        add_bullet_list(story, lines_to_list(cv["certifications"]))
        story.append(Spacer(1, 4))

    # Digital and technical skills
    if cv["digital_skills"].strip():
        story.append(section_title("Digital and Technical Skills"))
        add_bullet_list(story, lines_to_list(cv["digital_skills"]))
        story.append(Spacer(1, 4))

    # Languages
    if cv["languages"].strip():
        story.append(section_title("Languages"))
        story.append(Paragraph(safe(cv["languages"]), STYLES["body"]))
        story.append(Spacer(1, 4))

    # Optional referees
    refs = [ref for ref in cv["references"] if any(v.strip() for v in ref.values())]
    if refs:
        story.append(section_title("Referees"))
        for ref in refs:
            parts = [f"<b>{safe(ref['name'])}</b>"] if ref["name"].strip() else []
            parts += [safe(x) for x in [ref["title"], ref["organisation"], ref["phone"], ref["email"]] if x.strip()]
            story.append(Paragraph(" | ".join(parts), STYLES["small"]))
            story.append(Spacer(1, 3))

    def draw_page(canvas, document):
        canvas.saveState()
        width, height = A4
        canvas.setStrokeColor(LIGHT_LINE)
        canvas.setLineWidth(0.5)
        canvas.line(18 * mm, 12 * mm, width - 18 * mm, 12 * mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 8 * mm, "CURRICULUM VITAE")
        canvas.drawRightString(width - 18 * mm, 8 * mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=draw_page, onLaterPages=draw_page)
    buffer.seek(0)
    return buffer.getvalue()


# ReportLab styles are global and created once.
styles = getSampleStyleSheet()
STYLES = {
    "name": ParagraphStyle(
        "CVName", parent=styles["Title"], fontName="Helvetica-Bold",
        fontSize=21, leading=25, textColor=NAVY, alignment=TA_LEFT,
        spaceAfter=2,
    ),
    "headline": ParagraphStyle(
        "CVHeadline", parent=styles["Normal"], fontName="Helvetica",
        fontSize=10.5, leading=14, textColor=BLUE, spaceAfter=2,
    ),
    "contact": ParagraphStyle(
        "CVContact", parent=styles["Normal"], fontName="Helvetica",
        fontSize=8.5, leading=12, textColor=MUTED,
    ),
    "section": ParagraphStyle(
        "CVSection", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=10.5, leading=13, textColor=NAVY,
        spaceBefore=9, spaceAfter=5, keepWithNext=True,
    ),
    "body": ParagraphStyle(
        "CVBody", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.2, leading=13, textColor=DARK, spaceAfter=3,
    ),
    "bullet": ParagraphStyle(
        "CVBullet", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8.9, leading=12, textColor=DARK,
        leftIndent=10, firstLineIndent=-7, spaceAfter=2,
    ),
    "compact": ParagraphStyle(
        "CVCompact", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8.4, leading=11, textColor=DARK,
    ),
    "job_heading": ParagraphStyle(
        "CVJobHeading", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=9.4, leading=13, textColor=DARK, spaceBefore=3,
        spaceAfter=3, keepWithNext=True,
    ),
    "small": ParagraphStyle(
        "CVSmall", parent=styles["BodyText"], fontName="Helvetica",
        fontSize=8.5, leading=11, textColor=MUTED, spaceAfter=2,
    ),
}


# ---------------------------------------------------------------------
# Default CV information based on the uploaded CV (editable by the user)
# ---------------------------------------------------------------------
DEFAULTS = {
    "name": "Kipngetich Lawrence",
    "headline": "Registered Nurse | BSc Nursing and Public Health",
    "phone": "+254 768 263 623",
    "email": "Lawnetich15351@gmail.com",
    "location": "Kapsabet, Kenya",
    "linkedin": "",
    "portfolio": "",
    "profile": (
        "Compassionate and motivated Registered Nurse with a Bachelor of Science in Nursing "
        "and Public Health and experience delivering patient-centred care in healthcare settings. "
        "Skilled in patient assessment, medication administration, emergency care, patient education "
        "and multidisciplinary teamwork. Background in clinical research and health data collection, "
        "with strong communication, critical-thinking and problem-solving skills. Committed to "
        "professional, ethical and evidence-informed practice."
    ),
    "competencies": "\n".join([
        "Comprehensive patient assessment",
        "Nursing care planning and implementation",
        "Medication administration",
        "Emergency and acute care",
        "Patient and family education",
        "Leadership and teamwork",
        "Interpersonal and communication skills",
        "Microsoft Office and computer literacy",
        "Clinical research",
        "Data analysis using IBM SPSS",
        "Digital data collection",
    ]),
    "registration": "\n".join([
        "Registered Nurse – Nursing Council of Kenya (NCK)",
        "Practising Licence No.: 584208",
        "NCK Registration Certificate Serial No.: 218736",
        "Year of registration/licensure: 2026",
    ]),
    "certifications": "Certificate in Leadership Development and Mentorship – Kenyatta University (July 2024)",
    "digital_skills": "\n".join([
        "Open Data Kit (ODK) – electronic research data collection",
        "IBM SPSS – data management and analysis",
        "Microsoft Office applications",
        "EMR/EHR, KHIS/DHIS2 and HMIS – add details of actual use and proficiency before submitting",
    ]),
    "languages": "English – Fluent; Kiswahili – Fluent",
}

DEFAULT_EXPERIENCE = [
    {
        "role": "Registered Nurse / Infection Prevention and Control Chair",
        "organisation": "Oasis Doctors Plaza",
        "location": "Webuye, Kenya",
        "dates": "August 2026 – Present",
        "summary": "",
        "duties": "\n".join([
            "Provide nursing care in accordance with professional standards, hospital protocols and patient safety requirements.",
            "Serve as Infection Prevention and Control (IPC) Chair, supporting implementation and compliance with infection prevention and control standards.",
            "Promote safe medication administration, effective patient assessment, monitoring and timely escalation of clinical concerns.",
            "Oversee nursing documentation, handover practices and compliance with reporting requirements.",
            "Promote appropriate utilization and accountability of nursing resources while supporting continuous quality improvement.",
            "Supervise nurse interns and nurse aides assigned to the unit, supporting adherence to nursing standards and patient safety protocols.",
            "Collaborate with the multidisciplinary healthcare team to deliver quality patient-centred care.",
        ]),
    },
    {
        "role": "Nurse Intern",
        "organisation": "Embu Level 5 Hospital",
        "location": "Embu, Kenya",
        "dates": "July 2025 – July 2026",
        "summary": "",
        "duties": "\n".join([
            "Delivered comprehensive nursing care in medical, surgical, paediatric, maternity, emergency and outpatient departments.",
            "Conducted patient assessments, monitored vital signs and implemented individualized nursing care plans.",
            "Administered medications and intravenous therapies safely in accordance with hospital protocols.",
            "Provided health education and counselling to patients and caregivers.",
            "Maintained accurate clinical documentation and continuity of patient care.",
            "Collaborated with multidisciplinary healthcare teams and applied infection prevention and control measures.",
            "Participated in ward rounds, case discussions and continuous quality improvement activities.",
        ]),
    },
    {
        "role": "Research Assistant",
        "organisation": "Kenyatta University, Global Ultrasound Institute & Butterfly Networks",
        "location": "Nakuru County, Kenya",
        "dates": "July – August 2024",
        "summary": "Point-of-Care Ultrasound (POCUS) research project",
        "duties": "\n".join([
            "Collected research data using Open Data Kit (ODK).",
            "Extracted patient information from hospital records while maintaining confidentiality.",
            "Supported implementation of a Point-of-Care Ultrasound research project.",
            "Prepared accurate reports for the county research supervisor.",
            "Ensured data quality and adherence to research protocols.",
        ]),
    },
]

DEFAULT_EDUCATION = [
    {
        "qualification": "Bachelor of Science in Nursing and Public Health (BScN & PH)",
        "institution": "Kenyatta University, Kenya",
        "dates": "August 2019 – July 2024",
        "details": "",
    },
    {
        "qualification": "Kenya Certificate of Secondary Education (KCSE)",
        "institution": "Friends’ School Kamusinga, Kenya",
        "dates": "January 2015 – November 2018",
        "details": "",
    },
]


def init_state():
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    if "experience" not in st.session_state:
        st.session_state.experience = [dict(x) for x in DEFAULT_EXPERIENCE]
    if "education" not in st.session_state:
        st.session_state.education = [dict(x) for x in DEFAULT_EDUCATION]
    if "references" not in st.session_state:
        st.session_state.references = [
            {"name": "", "title": "", "organisation": "", "phone": "", "email": ""}
            for _ in range(3)
        ]


def collect_cv():
    return {
        **{key: st.session_state.get(key, default) for key, default in DEFAULTS.items()},
        "experience": st.session_state.experience,
        "education": st.session_state.education,
        "references": st.session_state.references,
    }


init_state()

st.title("📄 Professional CV Builder")
st.caption("Create a clean, readable, ATS-friendly CV and export it as an A4 PDF.")
st.info(
    "Your uploaded CV has been used to prefill the form. Review every field, correct any outdated "
    "information and remove details you do not want to publish before generating your PDF."
)

entry_tab, preview_tab = st.tabs(["1. Enter / Edit Details", "2. Preview & Generate PDF"])

with entry_tab:
    st.subheader("Personal and contact details")
    c1, c2 = st.columns(2)
    with c1:
        add_text_field("Full name", "name")
        add_text_field("Professional headline", "headline")
        add_text_field("Phone number", "phone")
    with c2:
        add_text_field("Email address", "email")
        add_text_field("Location", "location")
        add_text_field("LinkedIn URL (optional)", "linkedin")
        add_text_field("Portfolio URL (optional)", "portfolio")

    st.divider()
    st.subheader("Professional profile")
    st.text_area("Profile summary", key="profile", height=130,
                 help="Aim for 3–5 concise sentences tailored to the role you are applying for.")

    st.subheader("Core competencies")
    st.caption("Enter one skill per line.")
    st.text_area("Skills", key="competencies", height=180)

    st.divider()
    st.subheader("Professional experience")
    st.caption("Edit the prefilled roles or add another role. Put each responsibility on a new line.")
    for index, item in enumerate(st.session_state.experience):
        with st.expander(f"Experience {index + 1}: {item.get('role', 'New role')}", expanded=(index == 0)):
            item["role"] = st.text_input("Job title", item["role"], key=f"exp_role_{index}")
            item["organisation"] = st.text_input("Organisation", item["organisation"], key=f"exp_org_{index}")
            col_a, col_b = st.columns(2)
            with col_a:
                item["location"] = st.text_input("Location", item["location"], key=f"exp_loc_{index}")
            with col_b:
                item["dates"] = st.text_input("Dates", item["dates"], key=f"exp_dates_{index}")
            item["summary"] = st.text_input("Project / brief description (optional)", item["summary"], key=f"exp_summary_{index}")
            item["duties"] = st.text_area("Responsibilities / achievements (one per line)", item["duties"], height=150, key=f"exp_duties_{index}")
            if st.button("Remove this experience", key=f"remove_exp_{index}"):
                st.session_state.experience.pop(index)
                st.rerun()

    if st.button("＋ Add another experience"):
        st.session_state.experience.append({
            "role": "", "organisation": "", "location": "", "dates": "", "summary": "", "duties": ""
        })
        st.rerun()

    st.divider()
    st.subheader("Education")
    for index, item in enumerate(st.session_state.education):
        with st.expander(f"Education {index + 1}: {item.get('qualification', 'New qualification')}", expanded=(index == 0)):
            item["qualification"] = st.text_input("Qualification", item["qualification"], key=f"edu_qual_{index}")
            item["institution"] = st.text_input("Institution", item["institution"], key=f"edu_inst_{index}")
            item["dates"] = st.text_input("Dates", item["dates"], key=f"edu_dates_{index}")
            item["details"] = st.text_input("Additional details (optional)", item["details"], key=f"edu_details_{index}")
            if st.button("Remove this education", key=f"remove_edu_{index}"):
                st.session_state.education.pop(index)
                st.rerun()

    if st.button("＋ Add another education"):
        st.session_state.education.append({
            "qualification": "", "institution": "", "dates": "", "details": ""
        })
        st.rerun()

    st.divider()
    st.subheader("Professional registration and certifications")
    st.caption("Enter one item per line. Only include current, verifiable information.")
    st.text_area("Professional registration / licences", key="registration", height=100)
    st.text_area("Certifications and professional development", key="certifications", height=100)

    st.subheader("Digital and technical skills")
    st.caption("Enter one skill or platform per line. Describe your actual level of use accurately.")
    st.text_area("Digital skills", key="digital_skills", height=120)

    st.subheader("Languages")
    st.text_input("Languages and proficiency", key="languages")

    st.divider()
    st.subheader("Referees (optional)")
    st.caption("You may leave these blank and write “Available upon request” instead.")
    for index, ref in enumerate(st.session_state.references):
        with st.expander(f"Referee {index + 1}", expanded=False):
            ref["name"] = st.text_input("Name", ref["name"], key=f"ref_name_{index}")
            ref["title"] = st.text_input("Title", ref["title"], key=f"ref_title_{index}")
            ref["organisation"] = st.text_input("Organisation", ref["organisation"], key=f"ref_org_{index}")
            ref["phone"] = st.text_input("Phone", ref["phone"], key=f"ref_phone_{index}")
            ref["email"] = st.text_input("Email", ref["email"], key=f"ref_email_{index}")

    st.success("Your entries are held in this app session. Download your PDF before closing or refreshing the app.")

with preview_tab:
    cv = collect_cv()
    st.subheader("CV preview")
    st.caption("This is a content preview. The downloaded PDF uses a polished A4 layout with consistent spacing and typography.")

    st.markdown(f"# {cv['name']}")
    st.markdown(f"**{cv['headline']}**")
    contact = "  |  ".join(x for x in [cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]] if x)
    st.caption(contact)

    if cv["profile"].strip():
        st.markdown("### PROFESSIONAL PROFILE")
        st.write(cv["profile"])

    if lines_to_list(cv["competencies"]):
        st.markdown("### CORE COMPETENCIES")
        st.write(" • ".join(lines_to_list(cv["competencies"])))

    if cv["experience"]:
        st.markdown("### PROFESSIONAL EXPERIENCE")
        for item in cv["experience"]:
            if item["role"].strip() or item["organisation"].strip():
                st.markdown(f"**{item['role']}**")
                st.caption(" | ".join(x for x in [item["organisation"], item["location"], item["dates"]] if x))
                if item["summary"].strip():
                    st.write(item["summary"])
                for duty in lines_to_list(item["duties"]):
                    st.markdown(f"- {duty}")

    if cv["education"]:
        st.markdown("### EDUCATION")
        for item in cv["education"]:
            if item["qualification"].strip() or item["institution"].strip():
                st.markdown(f"**{item['qualification']}**")
                st.caption(" | ".join(x for x in [item["institution"], item["dates"]] if x))
                if item["details"].strip():
                    st.write(item["details"])

    for heading, key in [
        ("PROFESSIONAL REGISTRATION", "registration"),
        ("CERTIFICATIONS AND PROFESSIONAL DEVELOPMENT", "certifications"),
        ("DIGITAL AND TECHNICAL SKILLS", "digital_skills"),
    ]:
        items = lines_to_list(cv[key])
        if items:
            st.markdown(f"### {heading}")
            for item in items:
                st.markdown(f"- {item}")

    if cv["languages"].strip():
        st.markdown("### LANGUAGES")
        st.write(cv["languages"])

    filled_refs = [r for r in cv["references"] if any(v.strip() for v in r.values())]
    if filled_refs:
        st.markdown("### REFEREES")
        for ref in filled_refs:
            st.write(" | ".join(x for x in [ref["name"], ref["title"], ref["organisation"], ref["phone"], ref["email"]] if x))

    st.divider()
    st.subheader("Generate your CV")
    st.write("The PDF is A4-sized, text-selectable and designed for clear reading and straightforward applicant tracking system (ATS) parsing.")
    try:
        pdf_bytes = build_pdf(cv)
        safe_filename = re.sub(r"[^A-Za-z0-9_-]+", "_", cv["name"]).strip("_") or "Professional_CV"
        st.download_button(
            label="⬇️ Download CV as PDF",
            data=pdf_bytes,
            file_name=f"{safe_filename}_CV.pdf",
            mime="application/pdf",
            type="primary",
            use_container_width=True,
        )
        st.success("Your PDF is ready. Open it after downloading and check page breaks, dates and contact details before submitting.")
    except Exception as exc:
        st.error("The PDF could not be generated. Check that all entries contain normal text and try again.")
        st.exception(exc)

with st.sidebar:
    st.header("Design settings")
    st.write("The PDF uses a clean navy-and-blue professional style.")
    st.markdown("- A4 page size\n- Clear section hierarchy\n- Readable font sizes\n- Consistent spacing\n- Selectable PDF text\n- No unnecessary personal biodata")
    st.divider()
    st.caption("Tip: Tailor your profile and skills to each vacancy. Keep your CV accurate and preferably 2–3 pages depending on relevant experience.")
