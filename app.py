"""
Career Document Studio  (Streamlit)
------------------------------------
One app, two builders, reachable from the Home page:
  * CV Builder      - ATS-friendly A4 CV with live content preview and PDF download
  * Letter Builder  - Cover Letter, Application Letter, Letter of Motivation,
                      Statement of Purpose, Personal Statement, with paper preview and PDF download

Run locally:  streamlit run app.py
Deploy:       push app.py, requirements.txt and .streamlit/config.toml to GitHub,
              then deploy on Streamlit Community Cloud (main file: app.py).
"""

import base64
import io
import re
from datetime import datetime
from html import escape
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import streamlit as st
from PIL import Image, ImageFilter, ImageOps
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

st.set_page_config(page_title="Career Document Studio", page_icon="📄", layout="wide")

# =============================================================================
# SHARED: colours, navigation and state persistence
# =============================================================================
NAVY = colors.HexColor("#1B365D")   # name, section headers, divider lines
SLATE = colors.HexColor("#333333")  # body text (softer than pure black)

# ---- Fonts: Cambria -> Caladea (metric-compatible with Cambria) -> Times --------
# Cambria is a Microsoft font and is not bundled. Put cambria.ttf, cambriab.ttf, cambriai.ttf and
# cambriaz.ttf in a "fonts" folder next to app.py (or install them on the machine) to use it.
FONT_SEARCH_DIRS = [
    Path(__file__).resolve().parent / "fonts",
    Path.home() / ".fonts",
    Path("C:/Windows/Fonts"),
    Path("/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/usr/share/fonts"),
    Path("/usr/local/share/fonts"),
]
FONT_FAMILIES = [
    ("Cambria", {"regular": ["cambria.ttc", "cambria.ttf"], "bold": ["cambriab.ttf"],
                 "italic": ["cambriai.ttf"], "bolditalic": ["cambriaz.ttf"]}),
    ("Caladea (Cambria-compatible)", {"regular": ["caladea-regular.ttf"], "bold": ["caladea-bold.ttf"],
                                      "italic": ["caladea-italic.ttf"], "bolditalic": ["caladea-bolditalic.ttf"]}),
]


def _index_fonts() -> dict:
    found = {}
    for base in FONT_SEARCH_DIRS:
        try:
            if base.is_dir():
                for p in base.rglob("*"):
                    if p.suffix.lower() in (".ttf", ".ttc"):
                        found.setdefault(p.name.lower(), p)
        except OSError:
            continue
    return found


def setup_fonts():
    """Return (regular, bold, italic, bold-italic, label) font names for the PDFs."""
    if "AppSerif" in pdfmetrics.getRegisteredFontNames():
        face = str(pdfmetrics.getFont("AppSerif").face.name).lower()
        label = "Cambria" if "cambria" in face else "Caladea (Cambria-compatible)" if "caladea" in face else face
        return "AppSerif", "AppSerif-Bold", "AppSerif-Italic", "AppSerif-BoldItalic", label
    index = _index_fonts()

    def pick(names):
        return next((index[n] for n in names if n in index), None)

    for label, files in FONT_FAMILIES:
        paths = {style: pick(names) for style, names in files.items()}
        if not (paths["regular"] and paths["bold"]):
            continue
        try:
            for style, suffix in (("regular", ""), ("bold", "-Bold"), ("italic", "-Italic"), ("bolditalic", "-BoldItalic")):
                path = paths[style] or paths["bold" if "bold" in style else "regular"]
                pdfmetrics.registerFont(TTFont(f"AppSerif{suffix}", str(path), subfontIndex=0))
            pdfmetrics.registerFontFamily("AppSerif", normal="AppSerif", bold="AppSerif-Bold",
                                          italic="AppSerif-Italic", boldItalic="AppSerif-BoldItalic")
            return "AppSerif", "AppSerif-Bold", "AppSerif-Italic", "AppSerif-BoldItalic", label
        except Exception:  # unreadable font file: try the next family
            continue
    return "Times-Roman", "Times-Bold", "Times-Italic", "Times-BoldItalic", "Times (Cambria not found)"


FONT, FONT_BOLD, FONT_ITALIC, FONT_BOLDITALIC, FONT_LABEL = setup_fonts()
BODY_SIZE = 12      # body text size
BODY_LEADING = 14.4  # single line spacing for 12 pt
BODY_AFTER = 6      # space after every paragraph (pt)

TIMEZONE = "Africa/Nairobi"

# Widget keys that must survive switching between Home / CV / Letter pages.
CV_KEYS = ["name", "headline", "phone", "email", "location", "linkedin",
           "portfolio", "profile", "competencies", "digital_skills"]


def _persistable(key: str) -> bool:
    return key in CV_KEYS or (key.startswith("lt_") and not key.startswith("lt_sig_file"))


def go(page: str) -> None:
    """Button callback: save widget values (Streamlit drops them when a page is not drawn), then switch page."""
    store = st.session_state.setdefault("_store", {})
    for k in list(st.session_state.keys()):
        if _persistable(k):
            store[k] = st.session_state[k]
    st.session_state["page"] = page


def restore_state() -> None:
    for k, v in st.session_state.get("_store", {}).items():
        if k not in st.session_state:
            st.session_state[k] = v


def new_id() -> int:
    st.session_state["_uid"] = st.session_state.get("_uid", 0) + 1
    return st.session_state["_uid"]


def rec(d: dict) -> dict:
    """Copy a record and give it a unique id (keeps widget keys stable when entries are removed)."""
    r = dict(d)
    r["_id"] = new_id()
    return r


# =============================================================================
# CV BUILDER - PDF
# =============================================================================
_base = getSampleStyleSheet()


def _ps(name, **over):
    props = dict(parent=_base["Normal"], fontName=FONT, fontSize=BODY_SIZE, leading=BODY_LEADING,
                 textColor=SLATE, alignment=TA_LEFT, spaceBefore=0, spaceAfter=0)
    props.update(over)
    return ParagraphStyle(name, **props)


S = {
    "doctype": _ps("DocType", fontName=FONT_BOLD, fontSize=12, leading=16, textColor=NAVY, alignment=TA_CENTER, spaceAfter=6),
    "name": _ps("Name", fontName=FONT_BOLD, fontSize=20, leading=24, textColor=NAVY, alignment=TA_CENTER, spaceAfter=3),
    "headline": _ps("Headline", fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=NAVY, alignment=TA_CENTER, spaceAfter=5),
    "contact": _ps("Contact", fontSize=8.5, leading=12, alignment=TA_CENTER, spaceAfter=8),
    "section": _ps("Section", fontName=FONT_BOLD, fontSize=10.5, leading=14, textColor=NAVY, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    "body": _ps("Body", alignment=TA_JUSTIFY, spaceAfter=BODY_AFTER),
    "bullet": _ps("Bullet", alignment=TA_JUSTIFY, leftIndent=14, bulletIndent=0, bulletFontName=FONT,
                  bulletFontSize=BODY_SIZE, spaceAfter=BODY_AFTER),
    "job": _ps("Job", fontName=FONT_BOLD, spaceBefore=4, spaceAfter=2, keepWithNext=True),
    "detail": _ps("Detail", spaceAfter=BODY_AFTER),
    "label": _ps("Label", spaceAfter=2, keepWithNext=True),  # sub-heading above a bullet list
    "cell": _ps("Cell"),  # used inside two-column tables (row padding supplies the spacing)
}


def esc(value):
    return escape(str(value or "").strip(), quote=False).replace("\n", "<br/>")


def lines(value):
    return [x.strip().lstrip("•*- ").strip() for x in (value or "").splitlines() if x.strip()]


def section(story, title):
    story.append(Paragraph(esc(title.upper()), S["section"]))


def bullet_para(value):
    return Paragraph(esc(value), S["bullet"], bulletText="•")


def two_columns(story, cells, width, gap=BODY_AFTER):
    """Lay flowables out in two equal columns, filled left-to-right then down (keeps reading order)."""
    cells = list(cells)
    if not cells:
        return
    rows = [cells[i:i + 2] + [""] * (2 - len(cells[i:i + 2])) for i in range(0, len(cells), 2)]
    table = Table(rows, colWidths=[width / 2.0, width / 2.0], hAlign="LEFT")
    table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 0),
        ("RIGHTPADDING", (0, 0), (0, -1), 14),
        ("RIGHTPADDING", (1, 0), (1, -1), 0),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), gap),
    ]))
    story.append(table)


def nonempty(records, keys):
    return [r for r in records if any(str(r.get(k, "")).strip() for k in keys)]


EXPERIENCE_KEYS = ["role", "organisation", "hospital", "summary", "duties", "achievements"]


def referee_lines(r):
    """Referee as separate lines: name, title, institution, phone, email."""
    out = [r["name"]] if r["name"].strip() else []
    out += [x for x in (r["title"], r["organisation"], r["phone"], r["email"]) if x.strip()]
    return out


def header_flowables(doc_type, name, headline, contact_parts):
    """Centred heading block shared by the CV and every letter: type, name, headline, contact line, divider."""
    out = [Paragraph(esc(doc_type.upper()), S["doctype"]), Paragraph(esc(name.upper()), S["name"])]
    if headline.strip():
        out.append(Paragraph(esc(headline), S["headline"]))
    contact = " | ".join(esc(x) for x in contact_parts if x.strip())
    if contact:
        out.append(Paragraph(contact, S["contact"]))
    out.append(HRFlowable(width="100%", thickness=1.2, color=NAVY, spaceBefore=2, spaceAfter=5))
    return out


def header_html(doc_type, name, headline, contact_parts):
    """On-screen twin of header_flowables (list of single-line HTML strings)."""
    def t(x):
        return escape(str(x or "").strip(), quote=False)

    out = [f'<div style="text-align:center;font-size:12pt;font-weight:700;color:#1B365D;margin-bottom:6pt;">{t(doc_type.upper())}</div>',
           f'<div style="text-align:center;font-size:20pt;font-weight:700;line-height:1.2;color:#1B365D;">{t(name.upper())}</div>']
    if headline.strip():
        out.append(f'<div style="text-align:center;font-size:10.5pt;font-weight:700;color:#1B365D;margin-top:3pt;">{t(headline)}</div>')
    contact = " | ".join(t(x) for x in contact_parts if x.strip())
    if contact:
        out.append(f'<div style="text-align:center;font-size:8.5pt;margin-top:4pt;">{contact}</div>')
    out.append('<div style="border-top:1.2pt solid #1B365D;margin:8pt 0 4pt;"></div>')
    return out


def make_pdf(cv):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
                            topMargin=16*mm, bottomMargin=17*mm,
                            title=f"{cv['name']} - Curriculum Vitae", author=cv["name"])
    story = header_flowables("Curriculum Vitae", cv["name"], cv["headline"],
                             [cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]])

    if cv["profile"].strip():
        section(story, "Professional Profile")
        story.append(Paragraph(esc(cv["profile"]), S["body"]))
        story.append(Spacer(1, 5))
    if lines(cv["competencies"]):
        section(story, "Core Competencies")
        two_columns(story, [bullet_para(x) for x in lines(cv["competencies"])], doc.width)
        story.append(Spacer(1, 5))

    exp = nonempty(cv["experience"], EXPERIENCE_KEYS)
    if exp:
        section(story, "Professional Experience")
        for item in exp:
            heading = Paragraph(f"<b>{esc(item['role'])}</b>", S["job"])
            detail = " | ".join(esc(x) for x in (item["organisation"], item["location"], item["dates"]) if x.strip())
            block = [heading]
            if detail:
                block.append(Paragraph(detail, S["detail"]))
            for label, key in (("Hospital description", "hospital"), ("Project", "summary")):
                if item.get(key, "").strip():
                    block.append(Paragraph(f"<b>{label}:</b> {esc(item[key])}", S["body"]))
            for label, key in (("Responsibilities", "duties"), ("Achievements", "achievements")):
                points = lines(item.get(key, ""))
                if points:
                    block.append(Paragraph(f"<b>{label}:</b>", S["label"]))
                    block.extend(bullet_para(p) for p in points)
            block.append(Spacer(1, 6))
            story.append(KeepTogether(block))

    edu = nonempty(cv["education"], ["qualification", "institution"])
    if edu:
        section(story, "Education")
        for item in edu:
            story.append(Paragraph(f"<b>{esc(item['qualification'])}</b>", S["job"]))
            detail = " | ".join(esc(x) for x in (item["institution"], item["dates"], item["details"]) if x.strip())
            if detail:
                story.append(Paragraph(detail, S["detail"]))
        story.append(Spacer(1, 5))

    regs = nonempty(cv["registrations"], ["body", "licence_no", "certificate_no", "year", "valid_from", "valid_to"])
    if regs:
        section(story, "Professional Registration and Licensure")
        for r in regs:
            fields = [("Professional body", r["body"]), ("Licence number", r["licence_no"]),
                      ("Registration certificate number", r["certificate_no"]), ("Year of registration", r["year"])]
            validity = " to ".join(x for x in (r["valid_from"], r["valid_to"]) if x.strip())
            fields.append(("Licence validity", validity))
            cells = [Paragraph(f"<b>{esc(label)}:</b> {esc(value)}", S["cell"]) for label, value in fields if value.strip()]
            two_columns(story, cells, doc.width)
            story.append(Spacer(1, 5))

    certs = nonempty(cv["certifications"], ["name", "institution", "year"])
    if certs:
        section(story, "Certifications and Professional Development")
        for c in certs:
            detail = " | ".join(esc(x) for x in (c["institution"], c["year"]) if x.strip())
            story.append(Paragraph(esc(c["name"]), S["job"]))
            if detail:
                story.append(Paragraph(detail, S["detail"]))
        story.append(Spacer(1, 4))

    pubs = nonempty(cv["publications"], ["authors", "title", "date", "apa"])
    if pubs:
        section(story, "Publications")
        for p in pubs:
            for label, key in (("Authors", "authors"), ("Title", "title"), ("Date of publication", "date"), ("APA reference", "apa")):
                if p[key].strip():
                    story.append(Paragraph(f"<b>{label}:</b> {esc(p[key])}", S["body"]))
            story.append(Spacer(1, 6))

    if lines(cv["digital_skills"]):
        section(story, "Digital and Technical Skills")
        two_columns(story, [bullet_para(x) for x in lines(cv["digital_skills"])], doc.width)
        story.append(Spacer(1, 5))

    langs = nonempty(cv["languages"], ["language", "level"])
    if langs:
        section(story, "Languages")
        cells = [Paragraph(f"<b>{esc(item['language'])}:</b> {esc(item['level'])}", S["cell"]) for item in langs]
        two_columns(story, cells, doc.width)
        story.append(Spacer(1, 5))

    refs = nonempty(cv["references"], ["name", "title", "organisation", "phone", "email"])
    if refs:
        section(story, "Referees")
        cells = []
        for r in refs:
            parts = referee_lines(r)
            cells.append([Paragraph(f"<b>{esc(x)}</b>" if r["name"].strip() and i == 0 else esc(x), S["cell"])
                          for i, x in enumerate(parts)])
        two_columns(story, cells, doc.width, gap=10)

    def footer(canvas, document):
        canvas.saveState()
        w, _ = A4
        canvas.setStrokeColor(NAVY)
        canvas.setLineWidth(0.45)
        canvas.line(19*mm, 12*mm, w-19*mm, 12*mm)
        canvas.setFont(FONT, 8)
        canvas.setFillColor(SLATE)
        canvas.drawString(19*mm, 8*mm, "CURRICULUM VITAE")
        canvas.drawRightString(w-19*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()


# =============================================================================
# CV BUILDER - defaults, editors and page
# =============================================================================
# Prefilled details are drawn from the supplied CV; review them before publishing.
DEFAULTS = {
    "name": "Kipngetich Lawrence",
    "headline": "Registered Nurse | BSc Nursing and Public Health",
    "phone": "+254 768 263 623",
    "email": "Lawnetich15351@gmail.com",
    "location": "Kapsabet, Kenya",
    "linkedin": "",
    "portfolio": "",
    "profile": ("Compassionate and motivated Registered Nurse with a Bachelor of Science in Nursing and Public Health and experience delivering patient-centred care in healthcare settings. Skilled in patient assessment, medication administration, emergency care, patient education and multidisciplinary teamwork. Background in clinical research and health data collection, with strong communication, critical-thinking and problem-solving skills. Committed to professional, ethical and evidence-informed practice."),
    "competencies": "\n".join(["Comprehensive patient assessment", "Nursing care planning and implementation", "Medication administration", "Emergency and acute care", "Patient and family education", "Leadership and teamwork", "Interpersonal and communication skills", "Microsoft Office and computer literacy", "Clinical research", "Data analysis using IBM SPSS", "Digital data collection"]),
    "digital_skills": "\n".join(["Open Data Kit (ODK) – electronic research data collection", "IBM SPSS – data management and analysis", "Microsoft Office applications", "EMR/EHR, KHIS/DHIS2 and HMIS – describe your actual use and proficiency accurately"]),
}

DEFAULT_EXPERIENCE = [
    {"role": "Registered Nurse / Infection Prevention and Control Chair", "organisation": "Oasis Doctors Plaza", "location": "Webuye, Kenya", "dates": "August 2026 – Present", "summary": "", "duties": "\n".join(["Provide nursing care in accordance with professional standards, hospital protocols and patient safety requirements.", "Serve as Infection Prevention and Control (IPC) Chair, supporting implementation and compliance with infection prevention and control standards.", "Promote safe medication administration, effective patient assessment, monitoring and timely escalation of clinical concerns.", "Oversee nursing documentation, handover practices and compliance with reporting requirements.", "Promote appropriate utilization and accountability of nursing resources while supporting continuous quality improvement.", "Supervise nurse interns and nurse aides assigned to the unit, supporting adherence to nursing standards and patient safety protocols.", "Collaborate with the multidisciplinary healthcare team to deliver quality patient-centred care."])},
    {"role": "Nurse Intern", "organisation": "Embu Level 5 Hospital", "location": "Embu, Kenya", "dates": "July 2025 – July 2026", "summary": "", "duties": "\n".join(["Delivered comprehensive nursing care in medical, surgical, paediatric, maternity, emergency and outpatient departments.", "Conducted patient assessments, monitored vital signs and implemented individualized nursing care plans.", "Administered medications and intravenous therapies safely in accordance with hospital protocols.", "Provided health education and counselling to patients and caregivers.", "Maintained accurate clinical documentation and continuity of patient care.", "Collaborated with multidisciplinary healthcare teams and applied infection prevention and control measures.", "Participated in ward rounds, case discussions and continuous quality improvement activities."])},
    {"role": "Research Assistant", "organisation": "Kenyatta University, Global Ultrasound Institute & Butterfly Networks", "location": "Nakuru County, Kenya", "dates": "July – August 2024", "summary": "Point-of-Care Ultrasound (POCUS) research project", "duties": "\n".join(["Collected research data using Open Data Kit (ODK).", "Extracted patient information from hospital records while maintaining confidentiality.", "Supported implementation of a Point-of-Care Ultrasound research project.", "Prepared accurate reports for the county research supervisor.", "Ensured data quality and adherence to research protocols."])},
]
DEFAULT_EDUCATION = [
    {"qualification": "Bachelor of Science in Nursing and Public Health (BScN & PH)", "institution": "Kenyatta University, Kenya", "dates": "August 2019 – July 2024", "details": ""},
    {"qualification": "Kenya Certificate of Secondary Education (KCSE)", "institution": "Friends’ School Kamusinga, Kenya", "dates": "January 2015 – November 2018", "details": ""},
]
EMPTY_EXP = {"role": "", "organisation": "", "location": "", "dates": "", "hospital": "", "summary": "", "duties": "", "achievements": ""}
EMPTY_EDU = {"qualification": "", "institution": "", "dates": "", "details": ""}
EMPTY_REG = {"body": "", "licence_no": "", "certificate_no": "", "year": "", "valid_from": "", "valid_to": ""}
EMPTY_CERT = {"name": "", "institution": "", "year": ""}
EMPTY_PUB = {"authors": "", "title": "", "date": "", "apa": ""}
EMPTY_LANG = {"language": "", "level": "Fluent"}
EMPTY_REF = {"name": "", "title": "", "organisation": "", "phone": "", "email": ""}


def init_state():
    ss = st.session_state
    for key, value in DEFAULTS.items():
        ss.setdefault(key, value)
    lists = {
        "experience": [{**EMPTY_EXP, **x} for x in DEFAULT_EXPERIENCE],
        "education": DEFAULT_EDUCATION,
        "registrations": [{"body": "Nursing Council of Kenya (NCK)", "licence_no": "584208", "certificate_no": "218736", "year": "2026", "valid_from": "", "valid_to": ""}],
        "certifications": [{"name": "Certificate in Leadership Development and Mentorship", "institution": "Kenyatta University", "year": "2024"}],
        "publications": [],
        "languages": [{"language": "English", "level": "Fluent"}, {"language": "Kiswahili", "level": "Fluent"}],
        "references": [EMPTY_REF for _ in range(3)],
    }
    for key, items in lists.items():
        if key not in ss:
            ss[key] = [rec(x) for x in items]


def edit_experience():
    st.subheader("Professional experience")
    st.caption("Enter one responsibility and one achievement per line in their own boxes. Filled boxes print with their titles.")
    for i, item in enumerate(st.session_state.experience):
        uid = item["_id"]
        for k, v in EMPTY_EXP.items():
            item.setdefault(k, v)
        with st.expander(f"Experience {i+1}: {item.get('role') or 'New role'}", expanded=(i == 0)):
            item["role"] = st.text_input("Job title", item["role"], key=f"ex_role_{uid}")
            item["organisation"] = st.text_input("Organisation", item["organisation"], key=f"ex_org_{uid}")
            a, b = st.columns(2)
            item["location"] = a.text_input("Location", item["location"], key=f"ex_loc_{uid}")
            item["dates"] = b.text_input("Dates", item["dates"], key=f"ex_dates_{uid}")
            item["hospital"] = st.text_area("Hospital description (optional)", item["hospital"], key=f"ex_hosp_{uid}", height=90)
            item["summary"] = st.text_input("Project (optional)", item["summary"], key=f"ex_summary_{uid}")
            item["duties"] = st.text_area("Responsibilities", item["duties"], key=f"ex_duties_{uid}", height=140)
            item["achievements"] = st.text_area("Achievements (optional)", item["achievements"], key=f"ex_ach_{uid}", height=110)
            if st.button("Remove experience", key=f"ex_remove_{uid}"):
                st.session_state.experience.pop(i)
                st.rerun()
    if st.button("＋ Add experience", key="ex_add"):
        st.session_state.experience.append(rec(EMPTY_EXP))
        st.rerun()


def edit_education():
    st.subheader("Education")
    for i, item in enumerate(st.session_state.education):
        uid = item["_id"]
        with st.expander(f"Education {i+1}: {item.get('qualification') or 'New qualification'}"):
            for label, key, suffix in [("Qualification", "qualification", "qual"), ("Institution", "institution", "inst"), ("Dates", "dates", "dates"), ("Additional details", "details", "details")]:
                item[key] = st.text_input(label, item[key], key=f"edu_{suffix}_{uid}")
            if st.button("Remove education", key=f"edu_remove_{uid}"):
                st.session_state.education.pop(i)
                st.rerun()
    if st.button("＋ Add education", key="edu_add"):
        st.session_state.education.append(rec(EMPTY_EDU))
        st.rerun()


def edit_registrations():
    st.subheader("Professional registration and licensure")
    st.caption("Add a separate record for each professional body or licence. Leave validity dates blank if not applicable.")
    for i, r in enumerate(st.session_state.registrations):
        uid = r["_id"]
        with st.expander(f"Registration {i+1}: {r.get('body') or 'New registration'}", expanded=True):
            r["body"] = st.text_input("Professional body / regulator", r["body"], key=f"reg_body_{uid}")
            a, b = st.columns(2)
            r["licence_no"] = a.text_input("Licence number", r["licence_no"], key=f"reg_lic_{uid}")
            r["certificate_no"] = b.text_input("Registration certificate number", r["certificate_no"], key=f"reg_cert_{uid}")
            r["year"] = a.text_input("Year of registration", r["year"], key=f"reg_year_{uid}")
            r["valid_from"] = a.text_input("Licence valid from", r["valid_from"], key=f"reg_from_{uid}", placeholder="e.g. January 2026")
            r["valid_to"] = b.text_input("Licence valid to", r["valid_to"], key=f"reg_to_{uid}", placeholder="e.g. December 2026")
            if st.button("Remove registration", key=f"reg_remove_{uid}"):
                st.session_state.registrations.pop(i)
                st.rerun()
    if st.button("＋ Add professional registration", key="reg_add"):
        st.session_state.registrations.append(rec(EMPTY_REG))
        st.rerun()


def edit_certifications():
    st.subheader("Certifications and professional development")
    st.caption("Add each certification separately with its issuing institution and year.")
    for i, c in enumerate(st.session_state.certifications):
        uid = c["_id"]
        with st.expander(f"Certification {i+1}: {c.get('name') or 'New certification'}", expanded=True):
            c["name"] = st.text_input("Certificate / course name", c["name"], key=f"cert_name_{uid}")
            a, b = st.columns(2)
            c["institution"] = a.text_input("Issuing institution", c["institution"], key=f"cert_inst_{uid}")
            c["year"] = b.text_input("Year awarded", c["year"], key=f"cert_year_{uid}")
            if st.button("Remove certification", key=f"cert_remove_{uid}"):
                st.session_state.certifications.pop(i)
                st.rerun()
    if st.button("＋ Add certification", key="cert_add"):
        st.session_state.certifications.append(rec(EMPTY_CERT))
        st.rerun()


def edit_publications():
    st.subheader("Publications (optional)")
    st.caption("This section is excluded from the CV PDF unless at least one publication entry contains information.")
    for i, p in enumerate(st.session_state.publications):
        uid = p["_id"]
        with st.expander(f"Publication {i+1}: {p.get('title') or 'New publication'}", expanded=True):
            p["authors"] = st.text_input("Authors", p["authors"], key=f"pub_authors_{uid}")
            p["title"] = st.text_input("Title of publication", p["title"], key=f"pub_title_{uid}")
            p["date"] = st.text_input("Date of publication", p["date"], key=f"pub_date_{uid}", placeholder="e.g. 2025 or 15 March 2025")
            p["apa"] = st.text_area("Full APA-style reference", p["apa"], key=f"pub_apa_{uid}", height=90, help="Include journal or publisher, volume, issue, pages and DOI/URL where applicable.")
            if st.button("Remove publication", key=f"pub_remove_{uid}"):
                st.session_state.publications.pop(i)
                st.rerun()
    if st.button("＋ Add publication", key="pub_add"):
        st.session_state.publications.append(rec(EMPTY_PUB))
        st.rerun()


def edit_languages():
    st.subheader("Languages and proficiency")
    st.caption("Add any additional languages and choose an accurate level of mastery.")
    levels = ["Native", "Fluent", "Advanced", "Upper-intermediate", "Intermediate", "Basic", "Beginner"]
    for i, lang in enumerate(st.session_state.languages):
        uid = lang["_id"]
        a, b, c = st.columns([2, 2, 1])
        lang["language"] = a.text_input("Language", lang["language"], key=f"lang_name_{uid}")
        current = lang["level"] if lang["level"] in levels else "Fluent"
        lang["level"] = b.selectbox("Proficiency level", levels, index=levels.index(current), key=f"lang_level_{uid}")
        if c.button("Remove", key=f"lang_remove_{uid}"):
            st.session_state.languages.pop(i)
            st.rerun()
    if st.button("＋ Add language", key="lang_add"):
        st.session_state.languages.append(rec(EMPTY_LANG))
        st.rerun()


def edit_referees():
    st.subheader("Referees (optional)")
    st.caption("Include referees only with their permission. Each referee prints on separate lines: name, title, institution, phone, email.")
    for i, r in enumerate(st.session_state.references):
        uid = r["_id"]
        with st.expander(f"Referee {i+1}: {r.get('name') or 'New referee'}"):
            for label, key, ph in [("Name", "name", "e.g. Dr. Emmanuel Koch"),
                                   ("Professional title", "title", "e.g. Lecturer"),
                                   ("Institution", "organisation", "e.g. University of Hungary"),
                                   ("Phone", "phone", ""), ("Email", "email", "")]:
                r[key] = st.text_input(label, r[key], key=f"ref_{key}_{uid}", placeholder=ph)
            if st.button("Remove referee", key=f"ref_remove_{uid}"):
                st.session_state.references.pop(i)
                st.rerun()
    if st.button("＋ Add referee", key="ref_add"):
        st.session_state.references.append(rec(EMPTY_REF))
        st.rerun()


def get_cv():
    ss = st.session_state
    return {**{k: ss.get(k, v) for k, v in DEFAULTS.items()},
            "experience": ss.experience, "education": ss.education,
            "registrations": ss.registrations, "certifications": ss.certifications,
            "publications": ss.publications, "languages": ss.languages,
            "references": ss.references}


def cv_preview_html(cv: dict) -> str:
    """Paper-style CV preview that mirrors the PDF: Cambria 12 pt, justified, single spacing, 6 pt after paragraphs."""
    def t(x):
        return escape(str(x or "").strip(), quote=False).replace("\n", "<br>")

    h = [f'<div style="box-sizing:border-box;background:#FFFFFF;color:#333333;font-family:{PAPER_FONT};font-size:12pt;'
         'line-height:1.2;max-width:794px;margin:8px auto 24px;padding:46px 72px;border:1px solid #AAB7C7;'
         'border-radius:4px;box-shadow:0 6px 20px rgba(27,54,93,0.18);">']

    def heading(title):
        h.append(f'<div style="font-size:10.5pt;font-weight:700;color:#1B365D;margin:12pt 0 7pt;">{t(title.upper())}</div>')

    def para(text):
        h.append(f'<div style="text-align:justify;margin-bottom:6pt;">{t(text)}</div>')

    def bullet_html(text):
        return ('<div style="padding-left:14pt;text-indent:-14pt;text-align:justify;">'
                '<span style="display:inline-block;width:14pt;text-indent:0;">&bull;</span>' + t(text) + "</div>")

    def grid(cells, gap=6):
        """Two columns, filled left-to-right then down (inline blocks, no whitespace between them)."""
        out = []
        for i, cell in enumerate(cells):
            margin = "margin-right:4%;" if i % 2 == 0 else ""
            out.append(f'<div style="display:inline-block;vertical-align:top;width:47.9%;{margin}margin-bottom:{gap}pt;">{cell}</div>')
        h.append("".join(out))
        h.append('<div style="clear:both;"></div>')

    h.extend(header_html("Curriculum Vitae", cv["name"], cv["headline"],
                         [cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]]))

    if cv["profile"].strip():
        heading("Professional Profile")
        para(cv["profile"])
    if lines(cv["competencies"]):
        heading("Core Competencies")
        grid([bullet_html(x) for x in lines(cv["competencies"])])

    exp = nonempty(cv["experience"], EXPERIENCE_KEYS)
    if exp:
        heading("Professional Experience")
        for item in exp:
            h.append(f'<div style="font-weight:700;margin:4pt 0 2pt;">{t(item["role"])}</div>')
            detail = " | ".join(t(x) for x in (item["organisation"], item["location"], item["dates"]) if x.strip())
            if detail:
                h.append(f'<div style="margin-bottom:6pt;">{detail}</div>')
            for label, key in (("Hospital description", "hospital"), ("Project", "summary")):
                if item.get(key, "").strip():
                    h.append(f'<div style="text-align:justify;margin-bottom:6pt;"><b>{label}:</b> {t(item[key])}</div>')
            for label, key in (("Responsibilities", "duties"), ("Achievements", "achievements")):
                points = lines(item.get(key, ""))
                if points:
                    h.append(f'<div style="font-weight:700;margin-bottom:2pt;">{label}:</div>')
                    for point in points:
                        h.append('<div style="margin-bottom:6pt;">' + bullet_html(point) + "</div>")
            h.append('<div style="height:6pt;"></div>')

    edu = nonempty(cv["education"], ["qualification", "institution"])
    if edu:
        heading("Education")
        for item in edu:
            h.append(f'<div style="font-weight:700;margin:4pt 0 2pt;">{t(item["qualification"])}</div>')
            detail = " | ".join(t(x) for x in (item["institution"], item["dates"], item["details"]) if x.strip())
            if detail:
                h.append(f'<div style="margin-bottom:6pt;">{detail}</div>')

    regs = nonempty(cv["registrations"], ["body", "licence_no", "certificate_no", "year", "valid_from", "valid_to"])
    if regs:
        heading("Professional Registration and Licensure")
        for r in regs:
            validity = " to ".join(x for x in (r["valid_from"], r["valid_to"]) if x.strip())
            fields = (("Professional body", r["body"]), ("Licence number", r["licence_no"]),
                      ("Registration certificate number", r["certificate_no"]),
                      ("Year of registration", r["year"]), ("Licence validity", validity))
            grid([f"<b>{t(label)}:</b> {t(value)}" for label, value in fields if value.strip()])
            h.append('<div style="height:5pt;"></div>')

    certs = nonempty(cv["certifications"], ["name", "institution", "year"])
    if certs:
        heading("Certifications and Professional Development")
        for c in certs:
            h.append(f'<div style="font-weight:700;margin:4pt 0 2pt;">{t(c["name"])}</div>')
            detail = " | ".join(t(x) for x in (c["institution"], c["year"]) if x.strip())
            if detail:
                h.append(f'<div style="margin-bottom:6pt;">{detail}</div>')

    pubs = nonempty(cv["publications"], ["authors", "title", "date", "apa"])
    if pubs:
        heading("Publications")
        for p in pubs:
            for label, key in (("Authors", "authors"), ("Title", "title"), ("Date of publication", "date"), ("APA reference", "apa")):
                if p[key].strip():
                    h.append(f'<div style="text-align:justify;margin-bottom:6pt;"><b>{label}:</b> {t(p[key])}</div>')
            h.append('<div style="height:6pt;"></div>')

    if lines(cv["digital_skills"]):
        heading("Digital and Technical Skills")
        grid([bullet_html(x) for x in lines(cv["digital_skills"])])

    langs = nonempty(cv["languages"], ["language", "level"])
    if langs:
        heading("Languages")
        grid([f"<b>{t(item['language'])}:</b> {t(item['level'])}" for item in langs])

    refs = nonempty(cv["references"], ["name", "title", "organisation", "phone", "email"])
    if refs:
        heading("Referees")
        cells = []
        for r in refs:
            parts = [t(x) for x in referee_lines(r)]
            if r["name"].strip():
                parts[0] = f"<b>{parts[0]}</b>"
            cells.append("<br>".join(parts))
        grid(cells, gap=10)

    h.append("</div>")
    return "".join(h)


def cv_page():
    init_state()
    st.button("🏠 Back to Home", key="top_home_cv", on_click=go, args=("home",))
    st.title("📄 Professional CV Builder")
    st.caption("Enter your details, preview your CV and export a clean, ATS-friendly A4 PDF.")
    st.info("The form is prefilled using your supplied CV. Review all details and remove or correct anything that is outdated before downloading.")
    data_tab, preview_tab = st.tabs(["1. Enter / Edit Details", "2. Preview & Generate PDF"])

    with data_tab:
        st.subheader("Personal and contact details")
        left, right = st.columns(2)
        with left:
            st.text_input("Full name", key="name")
            st.text_input("Professional headline", key="headline")
            st.text_input("Phone number", key="phone")
            st.text_input("Location", key="location")
        with right:
            st.text_input("Email address", key="email")
            st.text_input("LinkedIn URL (optional)", key="linkedin")
            st.text_input("Portfolio URL (optional)", key="portfolio")
        st.divider()
        st.subheader("Professional profile")
        st.text_area("Profile summary", key="profile", height=125)
        st.subheader("Core competencies")
        st.caption("Enter one skill or competency per line.")
        st.text_area("Competencies", key="competencies", height=150)
        st.divider(); edit_experience()
        st.divider(); edit_education()
        st.divider(); edit_registrations()
        st.divider(); edit_certifications()
        st.divider(); edit_publications()
        st.divider()
        st.subheader("Digital and technical skills")
        st.caption("Enter one skill or platform per line. Describe your actual use accurately.")
        st.text_area("Digital and technical skills", key="digital_skills", height=115)
        st.divider(); edit_languages()
        st.divider(); edit_referees()

    with preview_tab:
        cv = get_cv()
        st.subheader("Curriculum Vitae preview")
        st.caption("This is how your CV will look. Go back to the first tab to make changes.")
        st.markdown(cv_preview_html(cv), unsafe_allow_html=True)

        st.divider()
        st.subheader("Generate PDF")
        st.write("The PDF uses a centred header, navy headings, justified slate-grey body text with single line spacing, standard section names and selectable text. Short lists (competencies, skills, languages, registration details and referees) are set in two columns; everything else is a single column with no graphics.")
        st.caption(f"PDF font: {FONT_LABEL}")
        try:
            pdf = make_pdf(cv)
            filename = re.sub(r"[^A-Za-z0-9_-]+", "_", cv["name"]).strip("_") or "Professional_CV"
            st.download_button("⬇️ Download ATS-friendly CV (PDF)", data=pdf, file_name=f"{filename}_CV.pdf", mime="application/pdf", type="primary", key="dl_cv")
            st.success("PDF generated. Review page breaks, dates and contact information before submitting.")
        except Exception as exc:
            st.error("PDF generation failed. Check the entered details and try again.")
            st.exception(exc)

    with st.sidebar:
        st.divider()
        st.header("CV layout")
        st.markdown("- Centred name and headline\n- Dark, legible section headings\n- Whitespace between sections\n- Single-column ATS-friendly structure\n- Repeatable registration entries\n- Multiple certifications\n- Optional publications\n- Multiple languages and proficiency levels\n- Referees on separate lines")
        st.divider()
        st.caption("ATS systems differ. Use standard headings, avoid graphics and columns, and follow each employer's requested file format.")
        st.caption("Entries are held in the active app session. Download your PDF before closing the app.")


# =============================================================================
# LETTER BUILDER - configuration, helpers, PDF and preview
# =============================================================================
LETTER_TYPES = {
    "Cover Letter": {
        "address": True, "salutation": True, "closing": True,
        "re": "Application for the Position of Registered Nurse",
        "hint": "Open with the role you are applying for, highlight 2-3 relevant achievements, and close with a call to action.",
    },
    "Application Letter": {
        "address": True, "salutation": True, "closing": True,
        "re": "Application for the Position of Registered Nurse",
        "hint": "State the position and where you saw it advertised, summarise your qualifications, and request an interview.",
    },
    "Letter of Motivation": {
        "address": True, "salutation": True, "closing": True,
        "re": "Letter of Motivation for [Programme / Position]",
        "hint": "Explain why you want this opportunity, what you bring, and how it fits your goals.",
    },
    "Statement of Purpose": {
        "address": False, "salutation": False, "closing": False,
        "re": "Statement of Purpose for [Programme]",
        "hint": "Cover your academic/professional background, your goals, and why this programme and institution are the right fit.",
    },
    "Personal Statement": {
        "address": False, "salutation": False, "closing": False,
        "re": "Personal Statement",
        "hint": "Tell your story: motivation, key experiences, strengths and future aspirations.",
    },
}
SALUTATIONS = ["Dear Hiring Manager,", "Dear Sir/Madam,", "Dear Recruitment Officer,", "Dear Admissions Committee,", "Custom..."]
CLOSINGS = ["Yours faithfully,", "Yours sincerely,"]
GENERIC_SALUTATION = re.compile(r"sir|madam|hiring|recruitment|committee", re.I)


def today_string() -> str:
    """Today's date from the current calendar day (Nairobi time)."""
    try:
        now = datetime.now(ZoneInfo(TIMEZONE))
    except Exception:  # tz database missing
        now = datetime.now()
    return f"{now.day} {now:%B %Y}"


def safe_text(value: str) -> str:
    """Escape for ReportLab's mini-markup and normalise odd whitespace."""
    value = (value or "").replace("\u00a0", " ").replace("\t", " ")
    return escape(value.strip(), quote=False)


def process_signature(data: bytes) -> Image.Image:
    """Photo of a signature -> clean black-on-transparent image, tightly cropped."""
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(data)))
    if img.mode in ("RGBA", "LA", "P"):
        rgba = img.convert("RGBA")
        flat = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        flat.alpha_composite(rgba)
        img = flat
    gray = img.convert("L")
    gray.thumbnail((1600, 1600))

    w, h = gray.size
    small = gray.resize((max(1, w // 8), max(1, h // 8)))
    small = small.filter(ImageFilter.MaxFilter(9)).filter(ImageFilter.GaussianBlur(4))
    background = np.asarray(small.resize((w, h), Image.Resampling.BILINEAR), dtype=np.float32)

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
    return Image.fromarray(out).crop((x0, y0, x1, y1))


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def address_lines(d: dict) -> list:
    """Standard address form: 'To,' then a comma after each line and a full stop after the last."""
    if not d["include_address"]:
        return []
    entries = [x.strip().rstrip(",.;:") for x in (d["rec_name"], d["rec_institution"], d["rec_address"], d["rec_city"]) if x.strip()]
    if not entries:
        return []
    return ["To,"] + [e + ("." if i == len(entries) - 1 else ",") for i, e in enumerate(entries)]


def body_paragraphs(body: str) -> list:
    return [p for p in re.split(r"\n\s*\n", body.strip()) if p.strip()]


def build_letter_pdf(d: dict) -> bytes:
    """Build the letter PDF (real text, standard fonts, ATS-parsable)."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm, topMargin=1.8 * cm, bottomMargin=1.8 * cm,
        title=f"{d['letter_type']} - {d['name']}", author=d["name"],
    )

    def style(name, **over):
        props = dict(fontName=FONT, fontSize=BODY_SIZE, leading=BODY_LEADING, textColor=SLATE)
        props.update(over)
        return ParagraphStyle(name, **props)

    s_left = style("l_left", alignment=TA_LEFT)
    s_bold = style("l_bold", fontName=FONT_BOLD, alignment=TA_LEFT)
    s_re = style("l_re", fontName=FONT_BOLD, textColor=NAVY, alignment=TA_CENTER)
    s_body = style("l_body", alignment=TA_JUSTIFY, spaceAfter=BODY_AFTER)  # same body format as the CV

    # Same heading block and divider line as the CV
    story = header_flowables(d["letter_type"], d["name"], d["headline"], [d["phone"], d["email"], d["location"]])
    story.append(Spacer(1, 9))

    story.append(Paragraph(safe_text(d["date"]), s_left))
    story.append(Spacer(1, 12))

    addr = address_lines(d)
    if addr:
        story.append(Paragraph("<br/>".join(safe_text(x) for x in addr), s_left))
        story.append(Spacer(1, 14))

    if d["include_salutation"] and d["salutation"].strip():
        story.append(Paragraph(safe_text(d["salutation"]), s_left))
        story.append(Spacer(1, 10))

    if d["re_line"].strip():
        story.append(Paragraph("<u>RE: " + safe_text(d["re_line"].upper()) + "</u>", s_re))
        story.append(Spacer(1, 12))

    for p in body_paragraphs(d["body"]):
        story.append(Paragraph("<br/>".join(safe_text(line) for line in p.split("\n")), s_body))

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


PAPER_FONT = "Cambria,Caladea,'Times New Roman',Times,serif"


def letter_preview_html(d: dict) -> str:
    """A paper-style on-screen preview that mirrors the PDF layout (single line of HTML, no blank lines)."""
    def t(x):
        return escape((x or "").strip(), quote=False).replace("\n", "<br>")

    h = [f'<div style="box-sizing:border-box;background:#FFFFFF;color:#333333;font-family:{PAPER_FONT};font-size:12pt;'
         'line-height:1.2;max-width:794px;margin:8px auto 24px;padding:46px 83px;border:1px solid #AAB7C7;'
         'border-radius:4px;box-shadow:0 6px 20px rgba(27,54,93,0.18);">']
    h.extend(header_html(d["letter_type"], d["name"], d["headline"], [d["phone"], d["email"], d["location"]]))
    h.append(f'<div style="margin:9pt 0 12pt;">{t(d["date"])}</div>')

    addr = address_lines(d)
    if addr:
        h.append('<div style="margin-bottom:14pt;">' + "<br>".join(t(x) for x in addr) + "</div>")
    if d["include_salutation"] and d["salutation"].strip():
        h.append(f'<div style="margin-bottom:10pt;">{t(d["salutation"])}</div>')
    if d["re_line"].strip():
        h.append(f'<div style="text-align:center;font-weight:700;text-decoration:underline;color:#1B365D;margin-bottom:12pt;">RE: {t(d["re_line"].upper())}</div>')
    for p in body_paragraphs(d["body"]):
        h.append('<p style="text-align:justify;margin:0 0 6pt;">' + "<br>".join(t(x) for x in p.split("\n")) + "</p>")

    if d["include_closing"]:
        h.append(f'<div style="margin-top:8pt;">{t(d["closing"])}</div>')
        if d["signature_png"]:
            b64 = base64.b64encode(d["signature_png"]).decode("ascii")
            h.append(f'<img src="data:image/png;base64,{b64}" style="display:block;max-height:49px;max-width:121px;margin:6pt 0 4pt;">')
        else:
            h.append('<div style="height:40px;"></div>')
        h.append(f'<div style="font-weight:700;">{t(d["sign_name"])}</div>')
        if d["sign_title"].strip():
            h.append(f'<div>{t(d["sign_title"])}</div>')
    h.append("</div>")
    return "".join(h)


# =============================================================================
# LETTER BUILDER - page
# =============================================================================
def letter_page():
    ss = st.session_state

    def dflt(key, value):
        ss.setdefault(key, value)
        return key

    st.button("🏠 Back to Home", key="top_home_letter", on_click=go, args=("home",))
    st.title("✉️ Professional Letter Builder")
    st.caption("Create an ATS-friendly letter, preview it, and download it as a PDF.")
    data_tab, preview_tab = st.tabs(["1. Enter / Edit Details", "2. Preview & Generate PDF"])

    with data_tab:
        st.selectbox("Letter type", list(LETTER_TYPES), key="lt_letter_type")
        letter_type = ss["lt_letter_type"]
        cfg = LETTER_TYPES[letter_type]
        k = letter_type.replace(" ", "_")  # per-type keys so defaults refresh when the type changes

        st.subheader("1. Your details (letter heading)")
        name = st.text_input("Full name", key=dflt("lt_name", DEFAULTS["name"]))
        headline = st.text_input("Professional headline", key=dflt("lt_headline", DEFAULTS["headline"]))
        c1, c2, c3 = st.columns(3)
        phone = c1.text_input("Phone", key=dflt("lt_phone", DEFAULTS["phone"]))
        email = c2.text_input("Email", key=dflt("lt_email", DEFAULTS["email"]))
        location = c3.text_input("Location", key=dflt("lt_location", DEFAULTS["location"]))

        st.subheader("2. Date")
        date_str = today_string()
        st.text_input("Date (automatic, today's date)", date_str, disabled=True)

        st.subheader("3. Recipient address")
        include_address = st.checkbox("Include recipient address", key=dflt(f"lt_addr_{k}", cfg["address"]))
        rec_name = rec_institution = rec_address = rec_city = ""
        if include_address:
            rec_name = st.text_input("Name of person addressed", key=dflt(f"lt_rn_{k}", ""), placeholder="e.g. Dr. Jane Mwangi")
            rec_institution = st.text_input("Institution", key=dflt(f"lt_ri_{k}", ""))
            rec_address = st.text_input("Address", key=dflt(f"lt_ra_{k}", ""))
            rec_city = st.text_input("City / State", key=dflt(f"lt_rc_{k}", ""))

        st.subheader("4. Salutation")
        include_salutation = st.checkbox("Include salutation", key=dflt(f"lt_sal_on_{k}", cfg["salutation"]))
        salutation, sal_idx = "", "none"
        if include_salutation:
            choice = st.selectbox("Salutation", SALUTATIONS, key=dflt(f"lt_sal_{k}", SALUTATIONS[0]))
            sal_idx = SALUTATIONS.index(choice)
            if choice == "Custom...":
                salutation = st.text_input("Custom salutation", key=dflt(f"lt_salc_{k}", ""), placeholder="e.g. Dear Dr. Mwangi,")
            else:
                salutation = choice

        st.subheader("5. RE: (subject line)")
        re_line = st.text_input("Subject (printed centred after 'RE:')", key=dflt(f"lt_re_{k}", cfg["re"]))

        st.subheader("6. Body")
        st.caption(cfg["hint"] + " Leave a blank line between paragraphs.")
        body = st.text_area("Letter body", height=320, key=dflt(f"lt_body_{k}", ""))

        st.subheader("7. Closing and signature")
        include_closing = st.checkbox("Include closing and signature", key=dflt(f"lt_clo_on_{k}", cfg["closing"]))
        closing, sign_name, sign_title = "", name, ""
        if include_closing:
            named = bool(salutation.strip()) and not GENERIC_SALUTATION.search(salutation)
            closing = st.selectbox("Closing", CLOSINGS, key=dflt(f"lt_cl_{k}_{sal_idx}", CLOSINGS[1] if named else CLOSINGS[0]))

            ver = ss.get("sig_ver", 0)
            sig_file = st.file_uploader("Upload signature (photo of a black-ink signature on white paper)",
                                        type=["png", "jpg", "jpeg", "webp"], key=f"lt_sig_file_{ver}")
            if sig_file is not None:
                fid = (sig_file.name, sig_file.size)
                if ss.get("sig_fid") != fid:
                    try:
                        ss["sigdata"] = image_to_png_bytes(process_signature(sig_file.getvalue()))
                        ss["sig_fid"] = fid
                    except Exception as exc:  # show a friendly message instead of crashing
                        st.error(f"Could not process the signature: {exc}")
            if ss.get("sigdata"):
                st.image(ss["sigdata"], caption="Cleaned and cropped signature", width=220)
                if st.button("Remove signature", key="sig_remove"):
                    ss.pop("sigdata", None)
                    ss.pop("sig_fid", None)
                    ss["sig_ver"] = ver + 1
                    st.rerun()

            # Signature name follows the heading name until you edit it yourself.
            if "lt_sign_name" not in ss or ss["lt_sign_name"] == ss.get("_synced_name"):
                ss["lt_sign_name"] = name
            ss["_synced_name"] = name
            sign_name = st.text_input("Name (printed under signature)", key="lt_sign_name")
            sign_title = st.text_input("Title (below name)", key=dflt("lt_sign_title", "Registered Nurse"))

    with preview_tab:
        problems = []
        if not name.strip():
            problems.append("Enter your full name.")
        if not body.strip():
            problems.append("Write the body of the letter.")
        if include_salutation and not salutation.strip():
            problems.append("Enter the custom salutation (or pick one from the list).")
        if include_closing and not sign_name.strip():
            problems.append("Enter the name for the signature block.")

        d = dict(
            letter_type=letter_type, name=name, headline=headline, phone=phone, email=email,
            location=location, date=date_str, include_address=include_address, rec_name=rec_name,
            rec_institution=rec_institution, rec_address=rec_address, rec_city=rec_city,
            include_salutation=include_salutation, salutation=salutation, re_line=re_line, body=body,
            include_closing=include_closing, closing=closing,
            signature_png=ss.get("sigdata") if include_closing else None,
            sign_name=sign_name, sign_title=sign_title,
        )

        st.subheader(f"{letter_type} preview")
        st.caption("This is how your letter will look. Go back to the first tab to make changes.")
        st.markdown(letter_preview_html(d), unsafe_allow_html=True)

        st.divider()
        st.subheader("Generate PDF")
        st.caption(f"PDF font: {FONT_LABEL}")
        for p in problems:
            st.warning(p)
        if not problems:
            try:
                pdf_bytes = build_letter_pdf(d)
                file_name = re.sub(r"[^A-Za-z0-9]+", "_", f"{name}_{letter_type}").strip("_") + ".pdf"
                st.download_button("⬇️ Download PDF", data=pdf_bytes, file_name=file_name,
                                   mime="application/pdf", type="primary", key="dl_letter")
                st.success("PDF generated. Check spelling, names and dates before sending.")
            except Exception as exc:
                st.error("PDF generation failed. Check the entered details and try again.")
                st.exception(exc)

    with st.sidebar:
        st.divider()
        st.header("Letter layout")
        st.markdown("- Centred heading with your details\n- Automatic date\n- Address block: To, name, institution, address, city\n- Centred RE: subject line\n- Justified body with 1.5 spacing between paragraphs\n- Closing, cleaned signature, name and title\n- Single-column, ATS-friendly PDF")


# =============================================================================
# HOME PAGE
# =============================================================================
def home_page():
    st.markdown(
        '<div style="background:linear-gradient(135deg,#17365D,#2F5597);color:#FFFFFF;padding:30px 34px;'
        'border-radius:14px;margin-bottom:22px;">'
        '<div style="font-size:32px;font-weight:700;line-height:1.2;">Career Document Studio</div>'
        '<div style="font-size:16px;margin-top:8px;color:#DCE6F5;">Build an ATS-friendly CV and professional letters, '
        'preview them, and download print-ready PDFs.</div></div>',
        unsafe_allow_html=True,
    )

    def card(title, items):
        li = "".join(f"<li style='margin:4px 0;'>{x}</li>" for x in items)
        return (
            "<div style='background:#EEF3FA;color:#202A35;border-left:6px solid #2F5597;border-radius:10px;"
            "padding:20px 24px;margin-bottom:12px;min-height:230px;'>"
            f"<div style='font-size:22px;font-weight:700;color:#17365D;margin-bottom:8px;'>{title}</div>"
            f"<ul style='margin:0;padding-left:20px;font-size:15px;line-height:1.5;'>{li}</ul></div>"
        )

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(card("📄 CV Builder", [
            "Prefilled from your CV, fully editable",
            "Experience, education, licences, certifications",
            "Optional publications and multiple languages",
            "Referees on separate lines",
            "Content preview, then ATS-friendly A4 PDF",
        ]), unsafe_allow_html=True)
        st.button("Open CV Builder", key="home_cv", type="primary", on_click=go, args=("cv",))
    with right:
        st.markdown(card("✉️ Letter Builder", [
            "Cover, application and motivation letters",
            "Statement of purpose and personal statement",
            "Automatic date and standard address block",
            "Signature upload with automatic cleaning",
            "Paper preview, then ATS-friendly PDF",
        ]), unsafe_allow_html=True)
        st.button("Open Letter Builder", key="home_letter", type="primary", on_click=go, args=("letter",))

    st.caption("Your entries are kept while you move between the builders. Download your PDFs before closing the app.")


# =============================================================================
# MAIN
# =============================================================================
def main():
    restore_state()
    st.session_state.setdefault("page", "home")
    page = st.session_state["page"]

    with st.sidebar:
        st.markdown("### Career Document Studio")
        for key, label in (("home", "🏠 Home"), ("cv", "📄 CV Builder"), ("letter", "✉️ Letter Builder")):
            st.button(label, key=f"nav_{key}", on_click=go, args=(key,),
                      type="primary" if page == key else "secondary")

    if page == "cv":
        cv_page()
    elif page == "letter":
        letter_page()
    else:
        home_page()


if __name__ == "__main__":
    main()
