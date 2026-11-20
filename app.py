import io
import re
from html import escape

import streamlit as st
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable, KeepTogether

st.set_page_config(page_title="Professional CV Builder", page_icon="📄", layout="wide")

NAVY = colors.HexColor("#17365D")
BLUE = colors.HexColor("#2F5597")
DARK = colors.HexColor("#202A35")
SUBTITLE = colors.HexColor("#3F4B59")
LINE = colors.HexColor("#AAB7C7")

_base = getSampleStyleSheet()
S = {
    "name": ParagraphStyle("Name", parent=_base["Title"], fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, alignment=TA_CENTER, spaceAfter=3),
    "headline": ParagraphStyle("Headline", parent=_base["Normal"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=BLUE, alignment=TA_CENTER, spaceAfter=5),
    "contact": ParagraphStyle("Contact", parent=_base["Normal"], fontName="Helvetica", fontSize=8.5, leading=12, textColor=DARK, alignment=TA_CENTER, spaceAfter=8),
    "section": ParagraphStyle("Section", parent=_base["Heading2"], fontName="Helvetica-Bold", fontSize=10.5, leading=14, textColor=NAVY, alignment=TA_LEFT, spaceBefore=12, spaceAfter=7, keepWithNext=True),
    "body": ParagraphStyle("Body", parent=_base["BodyText"], fontName="Helvetica", fontSize=9.2, leading=13, textColor=DARK, spaceAfter=4),
    "bullet": ParagraphStyle("Bullet", parent=_base["BodyText"], fontName="Helvetica", fontSize=9, leading=12.5, textColor=DARK, leftIndent=11, firstLineIndent=-7, spaceAfter=3),
    "job": ParagraphStyle("Job", parent=_base["BodyText"], fontName="Helvetica-Bold", fontSize=9.4, leading=13, textColor=DARK, spaceBefore=4, spaceAfter=2, keepWithNext=True),
    "detail": ParagraphStyle("Detail", parent=_base["BodyText"], fontName="Helvetica", fontSize=8.8, leading=12, textColor=SUBTITLE, spaceAfter=4),
}


def esc(value):
    return escape(str(value or "").strip()).replace("\n", "<br/>")


def lines(value):
    return [x.strip().lstrip("•*- ").strip() for x in (value or "").splitlines() if x.strip()]


def section(story, title):
    story.append(Paragraph(esc(title.upper()), S["section"]))


def bullets(story, values):
    for value in values:
        story.append(Paragraph("• " + esc(value), S["bullet"]))


def nonempty(records, keys):
    return [r for r in records if any(str(r.get(k, "")).strip() for k in keys)]


def make_pdf(cv):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
                            topMargin=16*mm, bottomMargin=17*mm,
                            title=f"{cv['name']} - Curriculum Vitae", author=cv["name"])
    story = [Paragraph(esc(cv["name"]).upper(), S["name"])]
    if cv["headline"].strip():
        story.append(Paragraph(esc(cv["headline"]), S["headline"]))
    contact = [x for x in (cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]) if x.strip()]
    if contact:
        story.append(Paragraph(" | ".join(esc(x) for x in contact), S["contact"]))
    story.append(HRFlowable(width="100%", thickness=1.2, color=BLUE, spaceBefore=2, spaceAfter=5))

    if cv["profile"].strip():
        section(story, "Professional Profile")
        story.append(Paragraph(esc(cv["profile"]), S["body"]))
        story.append(Spacer(1, 5))
    if lines(cv["competencies"]):
        section(story, "Core Competencies")
        bullets(story, lines(cv["competencies"]))
        story.append(Spacer(1, 5))

    exp = nonempty(cv["experience"], ["role", "organisation", "duties"])
    if exp:
        section(story, "Professional Experience")
        for item in exp:
            heading = Paragraph(f"<b>{esc(item['role'])}</b>", S["job"])
            detail = " | ".join(esc(x) for x in (item["organisation"], item["location"], item["dates"]) if x.strip())
            block = [heading]
            if detail:
                block.append(Paragraph(detail, S["detail"]))
            if item["summary"].strip():
                block.append(Paragraph(esc(item["summary"]), S["body"]))
            block.extend(Paragraph("• " + esc(d), S["bullet"]) for d in lines(item["duties"]))
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
            for label, value in fields:
                if value.strip():
                    story.append(Paragraph(f"<b>{esc(label)}:</b> {esc(value)}", S["body"]))
            story.append(Spacer(1, 5))

    certs = nonempty(cv["certifications"], ["name", "institution", "year"])
    if certs:
        section(story, "Certifications and Professional Development")
        for c in certs:
            detail = " | ".join(esc(x) for x in (c["institution"], c["year"]) if x.strip())
            story.append(Paragraph(f"<b>{esc(c['name'])}</b>" + (f"<br/>{detail}" if detail else ""), S["body"]))
            story.append(Spacer(1, 3))
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
        bullets(story, lines(cv["digital_skills"]))
        story.append(Spacer(1, 5))

    langs = nonempty(cv["languages"], ["language", "level"])
    if langs:
        section(story, "Languages")
        for item in langs:
            story.append(Paragraph(f"<b>{esc(item['language'])}:</b> {esc(item['level'])}", S["body"]))
        story.append(Spacer(1, 5))

    refs = nonempty(cv["references"], ["name", "title", "organisation", "phone", "email"])
    if refs:
        section(story, "Referees")
        for r in refs:
            parts = ([f"<b>{esc(r['name'])}</b>"] if r["name"].strip() else [])
            parts += [esc(x) for x in (r["title"], r["organisation"], r["phone"], r["email"]) if x.strip()]
            story.append(Paragraph(" | ".join(parts), S["detail"]))
            story.append(Spacer(1, 3))

    def footer(canvas, document):
        canvas.saveState()
        w, _ = A4
        canvas.setStrokeColor(LINE)
        canvas.setLineWidth(0.45)
        canvas.line(19*mm, 12*mm, w-19*mm, 12*mm)
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(SUBTITLE)
        canvas.drawString(19*mm, 8*mm, "CURRICULUM VITAE")
        canvas.drawRightString(w-19*mm, 8*mm, f"Page {document.page}")
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    buffer.seek(0)
    return buffer.getvalue()


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
    {"role": "Research Assistant", "organisation": "Kenyatta University, Global Ultrasound Institute & Butterfly Networks", "location": "Nakuru County, Kenya", "dates": "July – August 2024", "summary": "Point-of-Care Ultrasound (POCUS) research project", "duties": "\n".join(["Collected research data using Open Data Kit (ODK).", "Extracted patient information from hospital records while maintaining confidentiality.", "Supported implementation of a Point-of-Care Ultrasound research project.", "Prepared accurate reports for the county research supervisor.", "Ensured data quality and adherence to research protocols."])}
]
DEFAULT_EDUCATION = [
    {"qualification": "Bachelor of Science in Nursing and Public Health (BScN & PH)", "institution": "Kenyatta University, Kenya", "dates": "August 2019 – July 2024", "details": ""},
    {"qualification": "Kenya Certificate of Secondary Education (KCSE)", "institution": "Friends’ School Kamusinga, Kenya", "dates": "January 2015 – November 2018", "details": ""},
]
EMPTY_REG = {"body": "", "licence_no": "", "certificate_no": "", "year": "", "valid_from": "", "valid_to": ""}
EMPTY_CERT = {"name": "", "institution": "", "year": ""}
EMPTY_PUB = {"authors": "", "title": "", "date": "", "apa": ""}
EMPTY_LANG = {"language": "", "level": ""}
EMPTY_REF = {"name": "", "title": "", "organisation": "", "phone": "", "email": ""}


def init_state():
    for key, value in DEFAULTS.items():
        if key not in st.session_state:
            st.session_state[key] = value
    defaults = {
        "experience": DEFAULT_EXPERIENCE,
        "education": DEFAULT_EDUCATION,
        "registrations": [{"body": "Nursing Council of Kenya (NCK)", "licence_no": "584208", "certificate_no": "218736", "year": "2026", "valid_from": "", "valid_to": ""}],
        "certifications": [{"name": "Certificate in Leadership Development and Mentorship", "institution": "Kenyatta University", "year": "2024"}],
        "publications": [],
        "languages": [{"language": "English", "level": "Fluent"}, {"language": "Kiswahili", "level": "Fluent"}],
        "references": [EMPTY_REF.copy() for _ in range(3)],
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = [dict(x) for x in value]


def edit_experience():
    st.subheader("Professional experience")
    st.caption("Enter one responsibility or achievement per line.")
    for i, item in enumerate(st.session_state.experience):
        with st.expander(f"Experience {i+1}: {item.get('role') or 'New role'}", expanded=(i == 0)):
            item["role"] = st.text_input("Job title", item["role"], key=f"ex_role_{i}")
            item["organisation"] = st.text_input("Organisation", item["organisation"], key=f"ex_org_{i}")
            a, b = st.columns(2)
            item["location"] = a.text_input("Location", item["location"], key=f"ex_loc_{i}")
            item["dates"] = b.text_input("Dates", item["dates"], key=f"ex_dates_{i}")
            item["summary"] = st.text_input("Project / short description (optional)", item["summary"], key=f"ex_summary_{i}")
            item["duties"] = st.text_area("Responsibilities / achievements", item["duties"], key=f"ex_duties_{i}", height=140)
            if st.button("Remove experience", key=f"ex_remove_{i}"):
                st.session_state.experience.pop(i); st.rerun()
    if st.button("＋ Add experience"):
        st.session_state.experience.append({"role":"", "organisation":"", "location":"", "dates":"", "summary":"", "duties":""}); st.rerun()


def edit_education():
    st.subheader("Education")
    for i, item in enumerate(st.session_state.education):
        with st.expander(f"Education {i+1}: {item.get('qualification') or 'New qualification'}"):
            for label, key, suffix in [("Qualification", "qualification", "qual"), ("Institution", "institution", "inst"), ("Dates", "dates", "dates"), ("Additional details", "details", "details")]:
                item[key] = st.text_input(label, item[key], key=f"edu_{suffix}_{i}")
            if st.button("Remove education", key=f"edu_remove_{i}"):
                st.session_state.education.pop(i); st.rerun()
    if st.button("＋ Add education"):
        st.session_state.education.append({"qualification":"", "institution":"", "dates":"", "details":""}); st.rerun()


def edit_registrations():
    st.subheader("Professional registration and licensure")
    st.caption("Add a separate record for each professional body or licence. Leave validity dates blank if not applicable.")
    for i, r in enumerate(st.session_state.registrations):
        with st.expander(f"Registration {i+1}: {r.get('body') or 'New registration'}", expanded=True):
            r["body"] = st.text_input("Professional body / regulator", r["body"], key=f"reg_body_{i}")
            a, b = st.columns(2)
            r["licence_no"] = a.text_input("Licence number", r["licence_no"], key=f"reg_lic_{i}")
            r["certificate_no"] = b.text_input("Registration certificate number", r["certificate_no"], key=f"reg_cert_{i}")
            r["year"] = a.text_input("Year of registration", r["year"], key=f"reg_year_{i}")
            r["valid_from"] = a.text_input("Licence valid from", r["valid_from"], key=f"reg_from_{i}", placeholder="e.g. January 2026")
            r["valid_to"] = b.text_input("Licence valid to", r["valid_to"], key=f"reg_to_{i}", placeholder="e.g. December 2026")
            if st.button("Remove registration", key=f"reg_remove_{i}"):
                st.session_state.registrations.pop(i); st.rerun()
    if st.button("＋ Add professional registration"):
        st.session_state.registrations.append(EMPTY_REG.copy()); st.rerun()


def edit_certifications():
    st.subheader("Certifications and professional development")
    st.caption("Add each certification separately with its issuing institution and year.")
    for i, c in enumerate(st.session_state.certifications):
        with st.expander(f"Certification {i+1}: {c.get('name') or 'New certification'}", expanded=True):
            c["name"] = st.text_input("Certificate / course name", c["name"], key=f"cert_name_{i}")
            a, b = st.columns(2)
            c["institution"] = a.text_input("Issuing institution", c["institution"], key=f"cert_inst_{i}")
            c["year"] = b.text_input("Year awarded", c["year"], key=f"cert_year_{i}")
            if st.button("Remove certification", key=f"cert_remove_{i}"):
                st.session_state.certifications.pop(i); st.rerun()
    if st.button("＋ Add certification"):
        st.session_state.certifications.append(EMPTY_CERT.copy()); st.rerun()


def edit_publications():
    st.subheader("Publications (optional)")
    st.caption("This section is excluded from the CV PDF unless at least one publication entry contains information.")
    for i, p in enumerate(st.session_state.publications):
        with st.expander(f"Publication {i+1}: {p.get('title') or 'New publication'}", expanded=True):
            p["authors"] = st.text_input("Authors", p["authors"], key=f"pub_authors_{i}")
            p["title"] = st.text_input("Title of publication", p["title"], key=f"pub_title_{i}")
            p["date"] = st.text_input("Date of publication", p["date"], key=f"pub_date_{i}", placeholder="e.g. 2025 or 15 March 2025")
            p["apa"] = st.text_area("Full APA-style reference", p["apa"], key=f"pub_apa_{i}", height=90, help="Include journal or publisher, volume, issue, pages and DOI/URL where applicable.")
            if st.button("Remove publication", key=f"pub_remove_{i}"):
                st.session_state.publications.pop(i); st.rerun()
    if st.button("＋ Add publication"):
        st.session_state.publications.append(EMPTY_PUB.copy()); st.rerun()


def edit_languages():
    st.subheader("Languages and proficiency")
    st.caption("Add any additional languages and choose an accurate level of mastery.")
    levels = ["Native", "Fluent", "Advanced", "Upper-intermediate", "Intermediate", "Basic", "Beginner"]
    for i, lang in enumerate(st.session_state.languages):
        a, b, c = st.columns([2, 2, 1])
        lang["language"] = a.text_input("Language", lang["language"], key=f"lang_name_{i}")
        current = lang["level"] if lang["level"] in levels else "Fluent"
        lang["level"] = b.selectbox("Proficiency level", levels, index=levels.index(current), key=f"lang_level_{i}")
        if c.button("Remove", key=f"lang_remove_{i}"):
            st.session_state.languages.pop(i); st.rerun()
    if st.button("＋ Add language"):
        st.session_state.languages.append(EMPTY_LANG.copy()); st.rerun()


def edit_referees():
    st.subheader("Referees (optional)")
    st.caption("Include referees only with their permission.")
    for i, r in enumerate(st.session_state.references):
        with st.expander(f"Referee {i+1}"):
            for label, key in [("Name", "name"), ("Professional title", "title"), ("Organisation", "organisation"), ("Phone", "phone"), ("Email", "email")]:
                r[key] = st.text_input(label, r[key], key=f"ref_{key}_{i}")
            if st.button("Remove referee", key=f"ref_remove_{i}"):
                st.session_state.references.pop(i); st.rerun()
    if st.button("＋ Add referee"):
        st.session_state.references.append(EMPTY_REF.copy()); st.rerun()


def get_cv():
    return {**{k: st.session_state.get(k, v) for k, v in DEFAULTS.items()},
            "experience": st.session_state.experience, "education": st.session_state.education,
            "registrations": st.session_state.registrations, "certifications": st.session_state.certifications,
            "publications": st.session_state.publications, "languages": st.session_state.languages,
            "references": st.session_state.references}


init_state()
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
    st.subheader("CV content preview")
    st.markdown(f"<h1 style='text-align:center;color:#17365D;margin-bottom:0'>{escape(cv['name'])}</h1>", unsafe_allow_html=True)
    st.markdown(f"<p style='text-align:center;color:#2F5597;font-weight:700'>{escape(cv['headline'])}</p>", unsafe_allow_html=True)
    contact = " | ".join(escape(x) for x in (cv["phone"], cv["email"], cv["location"], cv["linkedin"], cv["portfolio"]) if x.strip())
    st.markdown(f"<p style='text-align:center;color:#202A35'>{contact}</p>", unsafe_allow_html=True)
    st.divider()

    def preview_section(title):
        st.markdown(f"### {title}")

    if cv["profile"].strip():
        preview_section("PROFESSIONAL PROFILE"); st.write(cv["profile"])
    if lines(cv["competencies"]):
        preview_section("CORE COMPETENCIES")
        for x in lines(cv["competencies"]): st.markdown(f"- {x}")
    for item in nonempty(cv["experience"], ["role", "organisation", "duties"]):
        preview_section("PROFESSIONAL EXPERIENCE")
        st.markdown(f"**{item['role']}**")
        st.caption(" | ".join(x for x in (item["organisation"], item["location"], item["dates"]) if x.strip()))
        if item["summary"].strip(): st.write(item["summary"])
        for duty in lines(item["duties"]): st.markdown(f"- {duty}")
    edu = nonempty(cv["education"], ["qualification", "institution"])
    if edu:
        preview_section("EDUCATION")
        for item in edu:
            st.markdown(f"**{item['qualification']}**")
            st.write(" | ".join(x for x in (item["institution"], item["dates"], item["details"]) if x.strip()))
    regs = nonempty(cv["registrations"], ["body", "licence_no", "certificate_no", "year", "valid_from", "valid_to"])
    if regs:
        preview_section("PROFESSIONAL REGISTRATION AND LICENSURE")
        for r in regs:
            for label, key in [("Professional body", "body"), ("Licence number", "licence_no"), ("Certificate number", "certificate_no"), ("Year of registration", "year")]:
                if r[key].strip(): st.write(f"**{label}:** {r[key]}")
            validity = " to ".join(x for x in (r["valid_from"], r["valid_to"]) if x.strip())
            if validity: st.write(f"**Licence validity:** {validity}")
    certs = nonempty(cv["certifications"], ["name", "institution", "year"])
    if certs:
        preview_section("CERTIFICATIONS AND PROFESSIONAL DEVELOPMENT")
        for c in certs:
            st.markdown(f"**{c['name']}**"); st.write(" | ".join(x for x in (c["institution"], c["year"]) if x.strip()))
    pubs = nonempty(cv["publications"], ["authors", "title", "date", "apa"])
    if pubs:
        preview_section("PUBLICATIONS")
        for p in pubs:
            for label, key in [("Authors", "authors"), ("Title", "title"), ("Date of publication", "date"), ("APA reference", "apa")]:
                if p[key].strip(): st.write(f"**{label}:** {p[key]}")
    if lines(cv["digital_skills"]):
        preview_section("DIGITAL AND TECHNICAL SKILLS")
        for x in lines(cv["digital_skills"]): st.markdown(f"- {x}")
    langs = nonempty(cv["languages"], ["language", "level"])
    if langs:
        preview_section("LANGUAGES")
        for x in langs: st.write(f"**{x['language']}:** {x['level']}")
    refs = nonempty(cv["references"], ["name", "title", "organisation", "phone", "email"])
    if refs:
        preview_section("REFEREES")
        for r in refs: st.write(" | ".join(x for x in r.values() if x.strip()))

    st.divider()
    st.subheader("Generate PDF")
    st.write("The PDF uses a centred header, high-contrast headings, consistent section spacing, a single-column reading order, standard section names and selectable text. No tables or graphics are used in the CV body.")
    try:
        pdf = make_pdf(cv)
        filename = re.sub(r"[^A-Za-z0-9_-]+", "_", cv["name"]).strip("_") or "Professional_CV"
        st.download_button("⬇️ Download ATS-friendly CV (PDF)", data=pdf, file_name=f"{filename}_CV.pdf", mime="application/pdf", type="primary", use_container_width=True)
        st.success("PDF generated. Review page breaks, dates and contact information before submitting.")
    except Exception as exc:
        st.error("PDF generation failed. Check the entered details and try again.")
        st.exception(exc)

with st.sidebar:
    st.header("CV layout")
    st.markdown("- Centred name and headline\n- Dark, legible section headings\n- Whitespace between sections\n- Single-column ATS-friendly structure\n- Repeatable registration entries\n- Multiple certifications\n- Optional publications\n- Multiple languages and proficiency levels")
    st.divider()
    st.caption("ATS systems differ. Use standard headings, avoid graphics and columns, and follow each employer's requested file format.")
    st.caption("Entries are held in the active app session. Download your PDF before closing the app.")
