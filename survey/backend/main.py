import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openai import OpenAI
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="Real Estate Automation Survey")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SUBMISSIONS_FILE = Path("submissions.json")

# ---------------------------------------------------------------------------
# Survey questions — static, no AI needed to render these
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.get("/api/questions")
def get_questions():
    return QUESTIONS


@app.post("/api/submit")
async def submit_survey(submission: Submission):
    # Build compact text — only answered questions
    q_map = {q["id"]: q["text"] for q in QUESTIONS}
    lines = []
    for ans in submission.answers:
        chosen = list(ans.selected)
        if ans.other_text:
            chosen.append(f"Other: {ans.other_text}")
        if chosen:
            lines.append(f"Q{ans.question_id}. {q_map.get(ans.question_id, '')}: {', '.join(chosen)}")

    answers_text = "\n".join(lines)

    # Single OpenAI call — gpt-4o-mini, capped at 350 output tokens
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a real estate automation consultant. "
                    "Analyze the survey and return JSON with these keys: "
                    "\"summary\" (2 sentences about their business profile), "
                    "\"recommendations\" (array of exactly 3 objects, each with \"name\", \"why\" (1 sentence), \"priority\" (High/Medium/Low)). "
                    "Be specific to their answers. No fluff."
                )
            },
            {
                "role": "user",
                "content": f"Business: {submission.company or 'N/A'}\n{answers_text}"
            }
        ],
        max_tokens=350,
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

    return {"success": True, "analysis": analysis, "tokens_used": tokens_used}


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
    # gpt-4o-mini: ~$0.15/1M input + $0.60/1M output, blended ~$0.30/1M
    cost = (total_tokens / 1_000_000) * 0.30
    return {"total": len(subs), "total_tokens": total_tokens, "estimated_cost_usd": round(cost, 4)}
