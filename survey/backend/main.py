import json
import os
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from pydantic import BaseModel
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

load_dotenv()

app = FastAPI(title="Real Estate Automation Survey")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://surveyrealty.avlokai.com",
        "https://survey-realty.avlokai.com",
        "http://localhost:8000",
        "http://localhost:3000",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SUBMISSIONS_FILE = Path("submissions.json")
WEBHOOK_URL = "https://n8n.avlokai.com/webhook/send-mails"

_NAVY = colors.HexColor("#0d2137")
_GOLD = colors.HexColor("#c8993a")
_GRAY = colors.HexColor("#7a8fa6")
_LIGHT = colors.HexColor("#eef3fb")
_BORDER = colors.HexColor("#c4cdd8")

QUESTIONS = [
    {
        "id": 1,
        "text": "What type of real estate business do you run?",
        "type": "single",
        "options": ["Developer / Builder", "Real Estate Agency", "Independent Broker / Consultant", "Property Management Company", "Proptech / Platform"]
    },
    {
        "id": 2,
        "text": "How many people are on your team?",
        "type": "single",
        "options": ["Solo (just me)", "2–5 people", "6–20 people", "21–50 people", "50+ people"]
    },
    {
        "id": 3,
        "text": "How many leads do you receive per month?",
        "type": "single",
        "options": ["Fewer than 50", "50–200", "200–500", "500+"]
    },
    {
        "id": 4,
        "text": "Where do most of your leads come from?",
        "type": "multi",
        "options": ["99acres / MagicBricks / Housing.com", "Facebook / Instagram Ads", "Google Ads / SEO", "Referrals from past clients", "Walk-ins / cold calls", "Builder / developer partnerships"]
    },
    {
        "id": 5,
        "text": "What are your biggest operational pain points right now?",
        "type": "multi",
        "note": "Select all that apply",
        "options": ["Following up with leads on time", "Collecting documents (KYC / agreements)", "Scheduling and confirming site visits", "Tracking commissions and payouts", "Posting on social media consistently", "Collecting rent and sending reminders", "Managing maintenance requests"]
    },
    {
        "id": 6,
        "text": "What tools does your team currently use?",
        "type": "multi",
        "options": ["WhatsApp manually", "Excel or Google Sheets", "A CRM (HubSpot, Zoho, Salesforce, etc.)", "Tally / accounting software", "Property portal dashboards (99acres, etc.)", "Nothing formal — everything is manual"]
    },
    {
        "id": 7,
        "text": "How many hours per day does your team spend on repetitive admin tasks?",
        "type": "single",
        "options": ["Less than 1 hour", "1–3 hours", "3–5 hours", "More than 5 hours"]
    },
    {
        "id": 8,
        "text": "Which of these would you most want automated first?",
        "type": "multi",
        "note": "Pick your top priorities",
        "options": ["Lead follow-up via WhatsApp / email", "Document and KYC collection", "Site visit scheduling and reminders", "Rent collection and reminders", "Social media posting for listings", "Commission and payout tracking", "Legal document generation (agreements, NOC)"]
    },
    {
        "id": 9,
        "text": "Do you work with NRI (overseas) buyers or landlords?",
        "type": "single",
        "options": ["Yes, a significant portion", "Occasionally", "No, only domestic clients"]
    },
    {
        "id": 10,
        "text": "How many properties do you list or manage per month?",
        "type": "single",
        "options": ["Fewer than 10", "10–50", "50–150", "150+"]
    },
    {
        "id": 11,
        "text": "What is your monthly marketing spend?",
        "type": "single",
        "options": ["Under ₹10,000", "₹10,000 – ₹50,000", "₹50,000 – ₹2,00,000", "₹2,00,000+"]
    },
    {
        "id": 12,
        "text": "What outcome matters most to you right now?",
        "type": "multi",
        "note": "Pick up to 2",
        "options": ["Generate more leads", "Convert more leads into deals", "Save staff time and reduce errors", "Scale without hiring more people", "Improve client experience and retention", "Better visibility into business performance"]
    },
    {
        "id": 13,
        "text": "What is your budget for automation setup + tools?",
        "type": "single",
        "options": ["Under ₹30,000", "₹30,000 – ₹1,00,000", "₹1,00,000 – ₹3,00,000", "Flexible if the ROI is clear"]
    },
    {
        "id": 14,
        "text": "How would you prefer we follow up with you?",
        "type": "single",
        "options": ["WhatsApp call or message", "Email", "Phone call", "Zoom / video call"]
    },
]


class Answer(BaseModel):
    question_id: int
    selected: List[str]
    other_text: Optional[str] = None


class Submission(BaseModel):
    name: str
    email: str
    phone: str
    company: Optional[str] = None
    answers: List[Answer]


def _style(name, **kw):
    return ParagraphStyle(name, **kw)


def generate_pdf(submission: Submission, analysis: dict) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=16 * mm,
    )

    W = A4[0] - 36 * mm  # usable width

    h1 = _style("h1", fontSize=18, textColor=colors.white, alignment=TA_CENTER,
                fontName="Helvetica-Bold")
    h2 = _style("h2", fontSize=13, textColor=_NAVY, fontName="Helvetica-Bold",
                spaceAfter=6)
    label = _style("lbl", fontSize=9, textColor=_GRAY, fontName="Helvetica-Bold")
    value = _style("val", fontSize=10, textColor=colors.HexColor("#1a2d42"),
                   fontName="Helvetica")
    body = _style("body", fontSize=10, textColor=colors.HexColor("#3d5168"),
                  fontName="Helvetica", leading=16)
    small = _style("sm", fontSize=8, textColor=_GRAY, fontName="Helvetica",
                   alignment=TA_CENTER)

    story = []

    # ── Header ──────────────────────────────────────────────────────────────
    hdr = Table(
        [[Paragraph("Avlok AI — Real Estate Automation Report", h1)]],
        colWidths=[W],
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _NAVY),
        ("TOPPADDING", (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING", (0, 0), (-1, -1), 12),
        ("RIGHTPADDING", (0, 0), (-1, -1), 12),
    ]))
    story.append(hdr)
    story.append(Spacer(1, 14))

    # ── Client info ─────────────────────────────────────────────────────────
    info_rows = [
        [Paragraph("Name", label), Paragraph(submission.name, value)],
        [Paragraph("Email", label), Paragraph(submission.email, value)],
        [Paragraph("Phone", label), Paragraph(submission.phone, value)],
        [Paragraph("Company", label), Paragraph(submission.company or "—", value)],
        [Paragraph("Date", label), Paragraph(datetime.now().strftime("%B %d, %Y"), value)],
    ]
    info_tbl = Table(info_rows, colWidths=[32 * mm, W - 32 * mm])
    info_tbl.setStyle(TableStyle([
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 0), (-1, -1), [_LIGHT, colors.white]),
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, _BORDER),
    ]))
    story.append(info_tbl)
    story.append(Spacer(1, 18))

    # ── Summary ─────────────────────────────────────────────────────────────
    story.append(Paragraph("Business Profile Summary", h2))
    summary_tbl = Table(
        [[Paragraph(analysis.get("summary", ""), body)]],
        colWidths=[W],
    )
    summary_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), _LIGHT),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING", (0, 0), (-1, -1), 14),
        ("RIGHTPADDING", (0, 0), (-1, -1), 14),
        ("LINEBEFORE", (0, 0), (0, -1), 4, _NAVY),
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
    ]))
    story.append(summary_tbl)
    story.append(Spacer(1, 18))

    # ── Recommendations ──────────────────────────────────────────────────────
    story.append(Paragraph("Recommended Automations &amp; Pricing", h2))

    prio_bg = {"High": "#fff1f0", "Medium": "#fffbf0", "Low": "#f0fff4"}
    prio_tc = {"High": "#c0392b", "Medium": "#c7821a", "Low": "#27ae60"}

    col_h = _style("ch", fontSize=9, textColor=colors.white,
                   fontName="Helvetica-Bold", alignment=TA_CENTER)
    col_lh = _style("clh", fontSize=9, textColor=colors.white,
                    fontName="Helvetica-Bold", alignment=TA_LEFT)

    pricing_header = [
        Paragraph("#", col_h),
        Paragraph("Automation", col_lh),
        Paragraph("Why it fits you", col_lh),
        Paragraph("Priority", col_h),
        Paragraph("Build Fee", col_h),
        Paragraph("Monthly Fee", col_h),
    ]

    CW = [8*mm, 42*mm, 62*mm, 16*mm, 24*mm, 24*mm]

    rows = [pricing_header]

    for i, rec in enumerate(analysis.get("recommendations", [])[:10]):
        priority = rec.get("priority", "Medium")
        tc = colors.HexColor(prio_tc.get(priority, "#c7821a"))
        bg_hex = prio_bg.get(priority, "#fffbf0")

        n_s = _style(f"n{i}", fontSize=9, textColor=_NAVY,
                     fontName="Helvetica-Bold", alignment=TA_CENTER)
        nm_s = _style(f"nm{i}", fontSize=9, textColor=_NAVY,
                      fontName="Helvetica-Bold", leading=13)
        w_s = _style(f"w{i}", fontSize=8, textColor=colors.HexColor("#3d5168"),
                     fontName="Helvetica", leading=12)
        p_s = _style(f"p{i}", fontSize=8, textColor=tc,
                     fontName="Helvetica-Bold", alignment=TA_CENTER)
        fee_s = _style(f"f{i}", fontSize=9, textColor=_NAVY,
                       fontName="Helvetica-Bold", alignment=TA_CENTER)

        build = rec.get("build_fee_inr", 0)
        monthly = rec.get("monthly_fee_inr", 0)

        rows.append([
            Paragraph(str(i + 1), n_s),
            Paragraph(rec.get("name", ""), nm_s),
            Paragraph(rec.get("why", ""), w_s),
            Paragraph(priority, p_s),
            Paragraph(f"₹{build:,}", fee_s),
            Paragraph(f"₹{monthly:,}/mo", fee_s),
        ])

    pricing_tbl = Table(rows, colWidths=CW, repeatRows=1)

    row_styles = [
        ("BACKGROUND", (0, 0), (-1, 0), _NAVY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (1, 1), (2, -1), "LEFT"),
        ("BOX", (0, 0), (-1, -1), 0.5, _BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.3, _BORDER),
    ]

    for i, rec in enumerate(analysis.get("recommendations", [])[:10]):
        priority = rec.get("priority", "Medium")
        bg_hex = prio_bg.get(priority, "#fffbf0")
        row_styles.append(
            ("BACKGROUND", (0, i + 1), (-1, i + 1), colors.HexColor(bg_hex))
        )

    pricing_tbl.setStyle(TableStyle(row_styles))
    story.append(pricing_tbl)

    # ── Totals ───────────────────────────────────────────────────────────────
    recs = analysis.get("recommendations", [])[:10]
    total_build = sum(r.get("build_fee_inr", 0) for r in recs)
    total_monthly = sum(r.get("monthly_fee_inr", 0) for r in recs)

    tot_s = _style("tot", fontSize=10, textColor=_NAVY, fontName="Helvetica-Bold",
                   alignment=TA_CENTER)
    totals_row = [
        [
            Paragraph("Total (all 10 automations)", _style("tl", fontSize=9,
                      textColor=_NAVY, fontName="Helvetica-Bold")),
            Paragraph(f"₹{total_build:,}", tot_s),
            Paragraph(f"₹{total_monthly:,}/mo", tot_s),
        ]
    ]
    totals_tbl = Table(totals_row, colWidths=[W - 48*mm, 24*mm, 24*mm])
    totals_tbl.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#eef3fb")),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, _NAVY),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    story.append(Spacer(1, 4))
    story.append(totals_tbl)

    story.append(Spacer(1, 20))
    story.append(Paragraph(
        "Generated by Avlok AI · survey-realty.avlokai.com · Confidential",
        small,
    ))

    doc.build(story)
    return buffer.getvalue()


async def _send_webhook(submission: Submission, analysis: dict, pdf_bytes: bytes):
    try:
        async with httpx.AsyncClient(timeout=30) as hc:
            await hc.post(
                WEBHOOK_URL,
                files={"data": ("automation_report.pdf", pdf_bytes, "application/pdf")},
                data={
                    "name": submission.name,
                    "email": submission.email,
                    "phone": submission.phone,
                    "company": submission.company or "",
                    "summary": analysis.get("summary", ""),
                },
            )
    except Exception:
        pass


@app.get("/api/questions")
def get_questions():
    return QUESTIONS


@app.post("/api/submit")
async def submit_survey(submission: Submission, background_tasks: BackgroundTasks):
    q_map = {q["id"]: q["text"] for q in QUESTIONS}
    lines = []
    for ans in submission.answers:
        chosen = list(ans.selected)
        if ans.other_text:
            chosen.append(f"Other: {ans.other_text}")
        if chosen:
            lines.append(f"Q{ans.question_id}. {q_map.get(ans.question_id, '')}: {', '.join(chosen)}")

    answers_text = "\n".join(lines)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a real estate automation consultant for the Indian market. "
                    "Analyze the survey and return JSON with exactly these keys: "
                    "\"summary\" (2 sentences about their business profile), "
                    "\"recommendations\" (array of exactly 10 objects, each with: "
                    "\"name\" (automation name), "
                    "\"why\" (1 sentence why it fits their specific business), "
                    "\"priority\" (High/Medium/Low), "
                    "\"build_fee_inr\" (integer, one-time setup cost in INR — simple: 25000-60000, medium: 60000-150000, complex: 150000-300000), "
                    "\"monthly_fee_inr\" (integer, monthly recurring fee in INR — simple: 3000-8000, medium: 8000-18000, complex: 18000-40000)). "
                    "Order by priority descending. Be specific to their answers. No fluff."
                )
            },
            {
                "role": "user",
                "content": f"Business: {submission.company or 'N/A'}\n{answers_text}"
            }
        ],
        max_tokens=900,
        response_format={"type": "json_object"},
        temperature=0.3,
    )

    analysis = json.loads(response.choices[0].message.content)
    tokens_used = response.usage.total_tokens

    record = {
        "id": datetime.now().isoformat(),
        "name": submission.name,
        "email": submission.email,
        "phone": submission.phone,
        "company": submission.company,
        "answers": [a.model_dump() for a in submission.answers],
        "analysis": analysis,
        "tokens_used": tokens_used,
        "submitted_at": datetime.now().isoformat(),
    }

    submissions = []
    if SUBMISSIONS_FILE.exists():
        with open(SUBMISSIONS_FILE) as f:
            submissions = json.load(f)
    submissions.append(record)
    with open(SUBMISSIONS_FILE, "w") as f:
        json.dump(submissions, f, indent=2)

    pdf_bytes = generate_pdf(submission, analysis)
    background_tasks.add_task(_send_webhook, submission, analysis, pdf_bytes)

    return {"success": True, "analysis": analysis}


@app.get("/api/admin/submissions")
def get_submissions():
    if not SUBMISSIONS_FILE.exists():
        return []
    with open(SUBMISSIONS_FILE) as f:
        return json.load(f)


@app.get("/api/admin/stats")
def get_stats():
    if not SUBMISSIONS_FILE.exists():
        return {"total": 0, "total_tokens": 0, "estimated_cost_usd": 0}
    with open(SUBMISSIONS_FILE) as f:
        subs = json.load(f)
    total_tokens = sum(s.get("tokens_used", 0) for s in subs)
    cost = (total_tokens / 1_000_000) * 0.30
    return {"total": len(subs), "total_tokens": total_tokens, "estimated_cost_usd": round(cost, 4)}
