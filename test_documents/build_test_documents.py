"""Generate the test .docx files in this folder.  Run:  python test_documents/build_test_documents.py

Each document is built to exercise a different part of the pipeline (see QUESTIONS.md).
All names, numbers and contact details are fictional.
"""

from pathlib import Path

import docx

OUT = Path(__file__).parent


def add_table(document, rows, merged_note=None):
    table = document.add_table(rows=len(rows), cols=len(rows[0]))
    table.style = "Table Grid"
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            table.cell(r, c).text = text
    if merged_note:  # one extra row whose cells are merged across the whole table
        cells = table.add_row().cells
        merged = cells[0].merge(cells[-1])
        merged.text = merged_note


def bold_heading(document, text, size=14):
    run = document.add_paragraph().add_run(text)
    run.bold = True
    run.font.size = docx.shared.Pt(size)


def aurora() -> None:
    """Real Word heading styles + a plans table with repeated values and a merged row."""
    d = docx.Document()
    d.add_heading("Aurora Cloud Hosting: Service Plans & Support Guide", 0)

    d.add_heading("1. Company Overview", 1)
    d.add_paragraph(
        "Aurora Cloud Hosting was founded in 2019 and is headquartered in Rotterdam, the Netherlands. "
        "The company is led by CEO Lars Veldman and operates three data centers: Rotterdam, Frankfurt and Dublin. "
        "All customer data stays inside the European Union."
    )

    d.add_heading("2. Hosting Plans", 1)
    d.add_paragraph("The table below compares the four hosting plans offered in 2026.")
    add_table(
        d,
        [
            ["Plan", "Price per month", "vCPU", "RAM", "Storage", "Daily backups", "Dedicated IP"],
            ["Starter", "EUR 9", "1", "2 GB", "40 GB", "No", "No"],
            ["Business", "EUR 29", "4", "8 GB", "160 GB", "Yes", "No"],
            ["Pro", "EUR 79", "8", "32 GB", "640 GB", "Yes", "Yes"],
            ["Enterprise", "Custom quote", "32", "128 GB", "2 TB", "Yes", "Yes"],
        ],
        merged_note="All prices exclude VAT (21%). Annual prepayment gives a 15% discount.",
    )

    d.add_heading("3. Support", 1)
    d.add_heading("3.1 Support Hours", 2)
    d.add_paragraph(
        "Standard support is available Monday to Friday, 08:00 to 18:00 CET, by email at "
        "support@aurorahost.example. Pro and Enterprise customers also get 24/7 phone support "
        "on +31 20 555 0142."
    )
    d.add_heading("3.2 First-Response Times", 2)
    d.add_paragraph("The guaranteed time until a support ticket receives a first reply depends on the plan:")
    for line in [
        "Starter: within 24 hours",
        "Business: within 8 hours",
        "Pro: within 1 hour",
        "Enterprise: within 15 minutes",
    ]:
        d.add_paragraph(line, style="List Bullet")

    d.add_heading("3.3 Uptime Guarantee", 2)
    d.add_paragraph(
        "Business plans are guaranteed 99.9% monthly uptime. Pro and Enterprise plans are guaranteed 99.99%. "
        "If uptime falls below the guarantee, the customer receives a service credit of 5% of the monthly fee "
        "for each full 0.1% below the guaranteed level, capped at 50% of the monthly fee. Starter plans have "
        "no uptime guarantee."
    )

    d.add_heading("4. Billing", 1)
    d.add_paragraph(
        "Invoices are issued on the 1st of each month and are due within 14 days. Late payments incur a fee of "
        "1.5% per month. First-time customers may request a full refund within 30 days of signing up. "
        "Cancellations require 30 days written notice."
    )
    d.save(OUT / "Aurora_Cloud_Hosting_Service_Guide.docx")


def meridian() -> None:
    """Fake (bold) numbered headings, a callout box, codes/emails/phones, and a directory table."""
    d = docx.Document()
    bold_heading(d, "Meridian Health Clinic: Patient Policy Handbook", 16)
    d.add_paragraph("Version 3.2, effective 1 February 2026. Applies to all patients of the clinic.")

    t = d.add_table(rows=1, cols=1)
    t.style = "Table Grid"
    t.cell(0, 0).text = "IMPORTANT: Please bring a photo ID and your insurance card to every visit."

    bold_heading(d, "1. Appointments")
    d.add_paragraph(
        "Appointments can be booked online or by calling the front desk on 555-0110. Please cancel at least "
        "24 hours in advance; missed appointments without notice are charged a no-show fee of EUR 25. "
        "Children under 16 must be accompanied by a parent or legal guardian."
    )

    bold_heading(d, "2. Opening Hours")
    d.add_paragraph(
        "The clinic is open Monday to Thursday from 07:30 to 19:00 and on Friday from 07:30 to 15:00. "
        "It is closed on Saturdays, Sundays and public holidays. For emergencies outside opening hours, call "
        "555-0199 or go to the nearest hospital emergency room."
    )

    bold_heading(d, "3. Medical Records")
    d.add_paragraph(
        "To request a copy of your medical records, submit form FORM-HC-204 to records@meridianclinic.example. "
        "Requests are processed within 5 business days. The first copy is free; each additional copy costs "
        "EUR 0.10 per page."
    )

    bold_heading(d, "4. Billing & Insurance")
    d.add_paragraph(
        "The clinic accepts patients insured by Allianz, AXA and Zorg Plus. Patients with other insurers pay "
        "at the time of the visit and can claim reimbursement themselves. Interest-free payment plans of up to "
        "12 months are available for bills above EUR 500."
    )

    bold_heading(d, "5. Department Directory")
    add_table(
        d,
        [
            ["Department", "Head of Department", "Room", "Extension"],
            ["General Practice", "Dr. Sofia Marin", "101", "2101"],
            ["Pediatrics", "Dr. Amara Okoye", "110", "2110"],
            ["Cardiology", "Dr. Tomas Becker", "204", "2204"],
            ["Radiology", "Dr. Ines Duarte", "B12", "2312"],
        ],
    )
    d.save(OUT / "Meridian_Clinic_Patient_Policy.docx")


def minutes() -> None:
    """No headings at all: plain paragraphs and bullets (everything ends up in one unnamed section)."""
    d = docx.Document()
    d.add_paragraph(
        "Minutes of the Board Meeting of Lindqvist Foundation, held on 12 March 2026 at 14:00 in Utrecht."
    )
    d.add_paragraph(
        "Present: Anna Keller (Chair), Ravi Patel (Treasurer), Mei Tanaka (Secretary) and Jonas Berg. "
        "Apologies were received from Clara Dubois."
    )
    d.add_paragraph(
        "The board reviewed the 2025 annual accounts, which closed with a surplus of EUR 18,400. "
        "The Treasurer noted that donations grew by 12% compared with 2024."
    )
    d.add_paragraph("The following decisions were taken:")
    for line in [
        "A budget of EUR 240,000 was approved for the 2026 website relaunch.",
        "The proposal to relocate the office to Hamburg was rejected by 4 votes to 1.",
        "The membership fee will remain at EUR 60 per year.",
    ]:
        d.add_paragraph(line, style="List Bullet")
    d.add_paragraph("Action items:")
    for line in [
        "Ravi Patel will send the revised financial forecast by 27 March 2026.",
        "Mei Tanaka will book a venue for the annual general meeting.",
    ]:
        d.add_paragraph(line, style="List Bullet")
    d.add_paragraph("The next board meeting will take place on 16 April 2026 at 10:00. The meeting closed at 15:45.")
    d.save(OUT / "Lindqvist_Foundation_Board_Minutes.docx")


if __name__ == "__main__":
    aurora()
    meridian()
    minutes()
    print("Created 3 documents in", OUT)
