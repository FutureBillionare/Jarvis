from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, KeepTogether)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

OUTPUT = "/Users/jakegoncalves/Desktop/Rodrigo_Lease_Agreement.pdf"

# Blinn College 2026–2027: Spring ends May 8 → Spring 2027 starts Jan 19
# Covers Summer Break, Thanksgiving/Fall Break, and Winter Break
LEASE_START    = "April 27, 2026"
LEASE_END      = "January 18, 2027"
AGREEMENT_DATE = "April 17, 2026"
DURATION       = "Approximately 8.5 months (Summer, Fall & Winter Breaks 2026–2027)"
PREMISES_ADDR  = "149 Fairview Ave, Apt. B, Port Chester, New York"
COUNTY_STATE   = "Westchester County, State of New York"

NAVY  = colors.HexColor("#1B2A4A")
GOLD  = colors.HexColor("#C9A84C")
BLUE  = colors.HexColor("#2E5FA3")
LGRAY = colors.HexColor("#F0F2F5")
WHITE = colors.white

doc = SimpleDocTemplate(
    OUTPUT,
    pagesize=letter,
    rightMargin=0.75*inch,
    leftMargin=0.75*inch,
    topMargin=0.5*inch,
    bottomMargin=0.75*inch,
)

styles = getSampleStyleSheet()

def style(name, **kw):
    base = styles["Normal"]
    return ParagraphStyle(name, parent=base, **kw)

body  = style("body",  fontSize=9.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=4)
bold  = style("bold",  fontSize=9.5, leading=14, alignment=TA_JUSTIFY, spaceAfter=4, fontName="Helvetica")
sec   = style("sec",   fontSize=10.5, leading=14, fontName="Helvetica", textColor=NAVY, spaceAfter=4, spaceBefore=12)
small = style("small", fontSize=8,   leading=11, alignment=TA_CENTER)
sig_label = style("siglabel", fontSize=9.5, fontName="Helvetica", leading=13)
sig_val   = style("sigval",   fontSize=11,  fontName="Helvetica-Oblique", leading=15, textColor=NAVY)
notice = style("notice", fontSize=8.5, leading=12, alignment=TA_CENTER, fontName="Helvetica",
               textColor=NAVY, spaceAfter=4)

def hr():
    return HRFlowable(width="100%", thickness=1, color=GOLD, spaceAfter=6, spaceBefore=2)

def section(num, title):
    return [Spacer(1, 6), Paragraph(f"{num}. {title}", sec), hr()]

def kv_table(rows, col_widths=None):
    if col_widths is None:
        col_widths = [1.8*inch, 5.0*inch]
    data = [[Paragraph(k, body), Paragraph(v, body)] for k, v in rows]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (0,-1), LGRAY),
        ("BACKGROUND", (1,0), (1,-1), WHITE),
        ("BOX",        (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("INNERGRID",  (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
        ("TOPPADDING", (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 8),
    ]))
    return t

# ── Header banner ──────────────────────────────────────────────────────────────
header_text = Paragraph(
    "<font color='white'>149 Fairview Ave<br/>Rental Agreement</font>",
    ParagraphStyle("hdr", fontSize=18, alignment=TA_CENTER, leading=26,
                   textColor=WHITE, fontName="Helvetica"),
)
banner = Table([[header_text]], colWidths=[6.85*inch])
banner.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,-1), NAVY),
    ("TOPPADDING",    (0,0), (-1,-1), 22),
    ("BOTTOMPADDING", (0,0), (-1,-1), 22),
    ("LEFTPADDING",   (0,0), (-1,-1), 12),
    ("RIGHTPADDING",  (0,0), (-1,-1), 12),
]))

story = [banner, Spacer(1, 14)]

# ── 1. Parties ─────────────────────────────────────────────────────────────────
story += section(1, "Parties and Premises")
story.append(Paragraph(
    f"This Residential Lease Agreement (\"Agreement\") is entered into as of "
    f"<b>{AGREEMENT_DATE}</b>, by and between:", body))
story.append(Spacer(1, 6))
story.append(kv_table([
    ("LANDLORD",  "Jake Goncalves"),
    ("TENANT",    "Rodrigo Schtscherbyna"),
    ("PREMISES",  PREMISES_ADDR),
    ("COUNTY",    COUNTY_STATE),
]))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "Landlord hereby leases to Tenant the above-described residential apartment (the \"Premises\") on the "
    "terms and conditions set forth herein. The lease of the Premises includes use of common areas of the "
    "building but excludes any parking spaces, storage units, or other appurtenances unless expressly stated "
    "in a separate written addendum signed by both parties.", body))

# ── 2. Lease Term ──────────────────────────────────────────────────────────────
story += section(2, "Lease Term")
story.append(kv_table([
    ("COMMENCEMENT DATE", LEASE_START),
    ("EXPIRATION DATE",   LEASE_END),
    ("TERM TYPE",         "Fixed-Term Tenancy — Blinn College Summer, Fall & Winter Breaks 2026–2027"),
    ("DURATION",          DURATION),
]))
story.append(Spacer(1, 8))
story.append(Paragraph(
    "This is a <b>fixed-term tenancy</b> aligned with Blinn College's academic break periods: "
    "<b>Summer Break 2026</b> (Spring semester concluding May 8, 2026; Fall semester commencing August 24, 2026), "
    "<b>Thanksgiving/Fall Break 2026</b> (approximately November 25–29, 2026), and "
    "<b>Winter Break 2026–2027</b> (Fall 2026 semester concluding December 12, 2026; Spring 2027 semester "
    "commencing January 19, 2027). The lease runs continuously from Commencement Date through Expiration Date "
    "encompassing all three break periods. Tenant shall vacate and surrender the Premises in good condition on "
    "or before the Expiration Date. No holdover tenancy shall be created without the prior written consent of "
    "Landlord. In the event Tenant holds over without such consent, Tenant shall be liable for use and occupancy "
    "at a rate of <b>two times (2x) the monthly rent</b> for each month or portion thereof of holdover.", body))

# ── 3. Rent ────────────────────────────────────────────────────────────────────
story += section(3, "Rent")
story.append(Paragraph(
    "Tenant agrees to pay rent in the amount of <b>$0.00 (zero dollars) per month</b>. This is a "
    "rent-free arrangement for the duration of the Blinn College Summer, Fall &amp; Winter Breaks 2026–2027 term. No monthly "
    "payment is required by Tenant. Late fees and grace period provisions of RPL §238-a are not "
    "applicable given the $0 rent amount.", body))
story.append(Spacer(1, 4))
story.append(Paragraph(
    "<b>Acceptable Payment Methods:</b> N/A — rent-free tenancy.", body))

# ── 4. Security Deposit ────────────────────────────────────────────────────────
story += section(4, "Security Deposit")
story.append(Paragraph(
    "No security deposit is required under this Agreement. The Security Deposit amount is "
    "<b>$0.00 (zero dollars)</b>.", body))

# ── 5. Utilities ───────────────────────────────────────────────────────────────
story += section(5, "Utilities and Services")
story.append(Paragraph("Responsibility for utilities and services shall be allocated as follows:", body))
story.append(Spacer(1, 4))
util_data = [
    [Paragraph("<b>Utility / Service</b>", body), Paragraph("<b>Responsible Party</b>", body)],
    [Paragraph("Heat",            body), Paragraph("■ Landlord  ☐ Tenant", body)],
    [Paragraph("Hot Water",       body), Paragraph("■ Landlord  ☐ Tenant", body)],
    [Paragraph("Electricity",     body), Paragraph("☐ Landlord  ■ Tenant", body)],
    [Paragraph("Gas",             body), Paragraph("■ Landlord  ☐ Tenant", body)],
    [Paragraph("Internet / Cable",body), Paragraph("☐ Landlord  ■ Tenant", body)],
    [Paragraph("Trash Removal",   body), Paragraph("■ Landlord  ☐ Tenant", body)],
]
ut = Table(util_data, colWidths=[3.0*inch, 3.85*inch])
ut.setStyle(TableStyle([
    ("BACKGROUND", (0,0), (-1,0), NAVY),
    ("TEXTCOLOR",  (0,0), (-1,0), WHITE),
    ("BACKGROUND", (0,1), (-1,-1), WHITE),
    ("ROWBACKGROUNDS", (0,1), (-1,-1), [LGRAY, WHITE]),
    ("BOX",        (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
    ("INNERGRID",  (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
    ("VALIGN",     (0,0), (-1,-1), "MIDDLE"),
    ("TOPPADDING", (0,0), (-1,-1), 5),
    ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ("LEFTPADDING",   (0,0), (-1,-1), 8),
]))
story.append(ut)

# ── 6. Occupancy ───────────────────────────────────────────────────────────────
story += section(6, "Occupancy and Use")
story.append(Paragraph(
    "The Premises shall be occupied solely as a private residential dwelling by <b>Rodrigo Schtscherbyna</b> "
    "and any additional occupants listed in a written addendum signed by Landlord. No other persons shall "
    "occupy the Premises on a permanent basis without prior written consent of Landlord.", body))
story.append(Paragraph(
    "<b>Subletting and Short-Term Rentals:</b> Tenant shall not sublet the Premises or any portion thereof, "
    "nor list the Premises on any short-term rental platform (including Airbnb or VRBO), without prior "
    "written consent of Landlord. NYC Local Law 18 (2023) regulates short-term rental registration.", body))
story.append(Paragraph(
    "<b>Use:</b> Tenant shall use the Premises solely for lawful residential purposes, in compliance with "
    "all applicable laws, codes, and building rules.", body))

# ── 7. Maintenance ─────────────────────────────────────────────────────────────
story += section(7, "Maintenance and Repairs")
story.append(Paragraph(
    "<b>Landlord's Obligations:</b> Landlord shall maintain the Premises in a habitable condition pursuant "
    "to RPL §235-b (Implied Warranty of Habitability) and shall make all repairs necessary to keep the "
    "Premises safe and in good condition.", body))
story.append(Paragraph(
    "<b>Tenant's Obligations:</b> Tenant shall keep the Premises clean and in good condition and shall be "
    "responsible for any damage beyond normal wear and tear. Tenant shall promptly notify Landlord in "
    "writing of any condition requiring repair.", body))

# ── 8. Entry ───────────────────────────────────────────────────────────────────
story += section(8, "Landlord's Right of Entry")
story.append(Paragraph(
    "Landlord or Landlord's agents may enter the Premises for repairs, inspections, or showings upon "
    "providing Tenant at least <b>24 hours advance written notice</b>, except in the case of emergency. "
    "Tenant shall not unreasonably withhold consent for entry.", body))

# ── 9. Rules ───────────────────────────────────────────────────────────────────
story += section(9, "Rules and Restrictions")
story.append(Paragraph(
    "<b>Pets:</b> No pets permitted without prior written consent of Landlord.", body))
story.append(Paragraph(
    "<b>Smoking:</b> Smoking of tobacco, cannabis, or any other substance is strictly prohibited within "
    "the Premises and all common areas of the building.", body))
story.append(Paragraph(
    "<b>Noise:</b> Tenant shall not create or permit unreasonable noise or disturbances. NYC Noise Code applies.", body))
story.append(Paragraph(
    "<b>Alterations:</b> Tenant shall make no alterations, holes, installations, or modifications to the "
    "Premises without prior written consent of Landlord.", body))

# ── 10. Termination ────────────────────────────────────────────────────────────
story += section(10, "Termination and Move-Out")
story.append(Paragraph(
    f"This Agreement shall terminate on <b>{LEASE_END}</b>, coinciding with the day before the "
    "commencement of Blinn College's Spring 2027 semester (January 19, 2027). The fixed end date "
    "constitutes adequate notice of lease expiration (RPL §232-a).", body))
story.append(Paragraph(
    "Upon termination, Tenant shall: (i) vacate and surrender the Premises in broom-clean condition, "
    "reasonable wear and tear excepted; (ii) return all keys and access cards to Landlord; and "
    "(iii) provide Landlord with a forwarding address.", body))

# ── 11. Good Cause Notice ──────────────────────────────────────────────────────
story += section(11, "Good Cause Eviction Law Notice")
notice_box_text = (
    "REQUIRED NOTICE — NY Real Property Law §231-c (effective April 20, 2024) This unit MAY be subject to "
    "the New York Good Cause Eviction Law. Under Good Cause Eviction, Landlord may not evict Tenant or "
    "fail to renew a lease without good cause, and rent increases at renewal may be limited to the local "
    "rent standard (CPI + 5%, max 10%). Tenant should consult NYC HPD or an attorney to determine whether "
    "this unit is covered."
)
notice_inner = Paragraph(notice_box_text, notice)
notice_table = Table([[notice_inner]], colWidths=[6.85*inch])
notice_table.setStyle(TableStyle([
    ("BACKGROUND",    (0,0), (-1,-1), colors.HexColor("#EDF2FB")),
    ("BOX",           (0,0), (-1,-1), 1, NAVY),
    ("TOPPADDING",    (0,0), (-1,-1), 10),
    ("BOTTOMPADDING", (0,0), (-1,-1), 10),
    ("LEFTPADDING",   (0,0), (-1,-1), 14),
    ("RIGHTPADDING",  (0,0), (-1,-1), 14),
]))
story.append(notice_table)

# ── 12–13. Disclosures (condensed) ────────────────────────────────────────────
story += section(12, "Required NYC Disclosures and Attachments")
disclosures = [
    ("A. Bedbug Disclosure (NYC Admin Code §27-2018.1)",
     "Landlord discloses the history of bedbug infestation in the Premises and building for the preceding year. "
     "Attach the NYC HPD Bedbug Disclosure Form."),
    ("B. Lead-Based Paint Disclosure (42 U.S.C. §4852d)",
     "For buildings built prior to 1978: Landlord discloses any known presence of lead-based paint. "
     "The EPA pamphlet has been provided to Tenant."),
    ("C. Window Guard Notice (24 RCNY §12-01)",
     "Tenant must indicate whether any child(ren) age 10 or under reside in the Premises."),
    ("D. Flood History Disclosure (NYC Local Law 86 of 2023)",
     "Landlord discloses whether the Premises has experienced flooding in the past 5 years and FEMA flood zone status."),
    ("E. CO / Smoke Detector Notice (NY Executive Law §378)",
     "Landlord confirms functioning carbon monoxide and smoke detectors are installed as of the commencement date."),
]
for title, text in disclosures:
    story.append(Paragraph(f"<b><font color='#2E5FA3'>{title}</font></b>", style("dh", fontSize=9.5, leading=13, spaceAfter=2, spaceBefore=4)))
    story.append(Paragraph(text, style("db", fontSize=9, leading=13, leftIndent=12, spaceAfter=4)))

# ── 14. General Provisions ─────────────────────────────────────────────────────
story += section(14, "General Provisions")
provisions = [
    ("Entire Agreement", "This Agreement constitutes the entire agreement between the parties and supersedes all prior negotiations."),
    ("Governing Law", "This Agreement shall be governed by the laws of the State of New York and applicable NYC ordinances."),
    ("Severability", "If any provision is found invalid, the remaining provisions shall remain in full force and effect."),
    ("Notices", "All notices shall be in writing and delivered by hand, certified mail, or email with confirmation of receipt."),
]
for k, v in provisions:
    story.append(Paragraph(f"<b>{k}:</b> {v}", body))

# ── 15. Signatures ─────────────────────────────────────────────────────────────
story += section(15, "Signatures")
story.append(Paragraph(
    "By signing below, the parties acknowledge that they have read, understand, and agree to all terms "
    "and conditions of this Lease Agreement.", body))
story.append(Spacer(1, 14))

# Signature block — 2 columns
ll_col = [
    [Paragraph("LANDLORD", sig_label)],
    [Spacer(1, 6)],
    [Paragraph("Name: Jake Goncalves", body)],
    [Spacer(1, 4)],
    [Paragraph("Signature:", body)],
    # Jake's signature in script style
    [Paragraph("<i>Jake Goncalves</i>", ParagraphStyle(
        "jsig", fontSize=16, fontName="Helvetica-Oblique",
        textColor=NAVY, leading=20))],
    [HRFlowable(width=2.8*inch, thickness=0.8, color=BLUE, spaceAfter=4)],
    [Paragraph(f"Date: {AGREEMENT_DATE}", body)],
    [Spacer(1, 8)],
    [Paragraph("Address for Notices:", body)],
    [Paragraph("149 Fairview Ave, Apt. B, Port Chester, NY", body)],
]

rt_col = [
    [Paragraph("TENANT", sig_label)],
    [Spacer(1, 6)],
    [Paragraph("Name: Rodrigo Schtscherbyna", body)],
    [Spacer(1, 4)],
    [Paragraph("Signature:", body)],
    [Spacer(1, 20)],
    [HRFlowable(width=2.8*inch, thickness=0.8, color=BLUE, spaceAfter=4)],
    [Paragraph("Date: ___________________________", body)],
    [Spacer(1, 8)],
    [Paragraph("Address for Notices:", body)],
    [Paragraph("_________________________________", body)],
]

from reportlab.platypus import KeepInFrame

def col_to_table(rows):
    t = Table(rows, colWidths=[3.2*inch])
    t.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("LEFTPADDING",  (0,0), (-1,-1), 0),
        ("RIGHTPADDING", (0,0), (-1,-1), 0),
        ("TOPPADDING",   (0,0), (-1,-1), 1),
        ("BOTTOMPADDING",(0,0), (-1,-1), 1),
    ]))
    return t

sig_row = Table(
    [[col_to_table(ll_col), col_to_table(rt_col)]],
    colWidths=[3.4*inch, 3.4*inch]
)
sig_row.setStyle(TableStyle([
    ("VALIGN",  (0,0), (-1,-1), "TOP"),
    ("TOPPADDING",   (0,0), (-1,-1), 0),
    ("BOTTOMPADDING",(0,0), (-1,-1), 0),
    ("LEFTPADDING",  (0,0), (-1,-1), 4),
    ("RIGHTPADDING", (0,0), (-1,-1), 4),
]))
story.append(sig_row)
story.append(Spacer(1, 20))

# Footer
footer_text = (
    "This document is a residential lease agreement. The parties are encouraged to seek independent legal "
    "counsel before execution. Required NYC HPD forms (Bedbug Disclosure, Window Guard Notice, Lead Paint "
    "EPA form) must be attached as separate exhibits prior to signing. Lease term corresponds to Blinn "
    "College Summer, Fall &amp; Winter Breaks 2026–2027 (May 4, 2026 – January 18, 2027). "
    "Premises: 149 Fairview Ave, Apt. B, Port Chester, New York."
)
footer_box = Table(
    [[Paragraph(footer_text, small)]],
    colWidths=[6.85*inch]
)
footer_box.setStyle(TableStyle([
    ("BOX",           (0,0), (-1,-1), 0.5, colors.HexColor("#AAAAAA")),
    ("TOPPADDING",    (0,0), (-1,-1), 8),
    ("BOTTOMPADDING", (0,0), (-1,-1), 8),
    ("LEFTPADDING",   (0,0), (-1,-1), 10),
    ("RIGHTPADDING",  (0,0), (-1,-1), 10),
]))
story.append(footer_box)

doc.build(story)
print(f"PDF generated: {OUTPUT}")
