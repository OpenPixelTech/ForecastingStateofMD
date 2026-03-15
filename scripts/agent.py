"""
Open Pixel — Maryland Procurement Intelligence Agent
=====================================================
Reads a Maryland Procurement Forecast .xls file, scores opportunities
with Claude, detects new ones vs. the last run, and creates ClickUp tasks.

Usage:
    python scripts/agent.py --file forecasts/forecast.xls
    python scripts/agent.py --file forecasts/forecast.xls --dry-run
    python scripts/agent.py --file forecasts/forecast.xls --all
"""

import argparse
import json
import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path

import xlrd
import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
CLICKUP_API_KEY   = os.getenv("CLICKUP_API_KEY")
CLICKUP_LIST_ID   = os.getenv("CLICKUP_LIST_ID")

SNAPSHOT_FILE = "procurement_snapshot.json"
REPORTS_DIR   = Path("reports")

RELEVANCE_KEYWORDS = [
    "web", "website", "portal", "digital", "frontend", "front end",
    "cms", "content management", "intranet", "online platform",
    "mobile app", "accessibility", "section 508", "ada",
    "development support", "software development", "application development",
    "platform services", "moderniz", "it programming", "grant management",
    "digital economy", "online program", "scanbot", "react", "ui ", "ux "
]

OPEN_PIXEL_CONTEXT = """
Open Pixel is a web development consultancy based in Maryland (Crofton, MD).
Services: custom web development, portal design, CMS implementation,
digital accessibility (ADA/Section 508 compliance), UX/UI design,
web application development, intranet/extranet builds, digital strategy.
NAICS: 541512 (primary), 541511, 541519
NIGP: 20918 (primary), 20900, 91835
PSC: D301
"""


# ─────────────────────────────────────────────
# STEP 1: Parse XLS
# ─────────────────────────────────────────────
def parse_forecast(filepath: str) -> list[dict]:
    wb = xlrd.open_workbook(filepath)
    sh = wb.sheet_by_index(0)
    headers = [sh.cell_value(0, j) for j in range(sh.ncols)]
    rows = []
    for i in range(1, sh.nrows):
        row = [sh.cell_value(i, j) for j in range(sh.ncols)]
        rows.append(dict(zip(headers, row)))
    print(f"✅ Parsed {len(rows)} rows from {filepath}")
    return rows


# ─────────────────────────────────────────────
# STEP 2: Keyword pre-filter
# ─────────────────────────────────────────────
def prefilter(rows: list[dict]) -> list[dict]:
    candidates = []
    for row in rows:
        text = " ".join(str(v).lower() for v in row.values())
        if any(kw in text for kw in RELEVANCE_KEYWORDS):
            candidates.append(row)
    print(f"🔍 Pre-filter: {len(candidates)} candidates from {len(rows)} rows")
    return candidates


# ─────────────────────────────────────────────
# STEP 3: Score with Claude
# ─────────────────────────────────────────────
def score_with_claude(candidates: list[dict]) -> list[dict]:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    scored = []
    batch_size = 10
    batches = [candidates[i:i+batch_size] for i in range(0, len(candidates), batch_size)]

    for batch_num, batch in enumerate(batches):
        print(f"🤖 Scoring batch {batch_num + 1}/{len(batches)}...")

        solicitations_text = ""
        for idx, row in enumerate(batch):
            solicitations_text += f"""
---
Solicitation #{idx + 1}
Agency: {row.get('Agency Name', '')}
Category: {row.get('Procurement Category', '')}
Description: {row.get('Description', '')}
Est. Value: {row.get('Estimated Total Contract Award (no options)', '')}
Ad Date: {row.get('Estimated Advertisement Date', '')}
Method: {row.get('Procurement Method', '')}
PO: {row.get('PO Name', '')} | {row.get('PO Email', '')}
"""

        prompt = f"""You are a BD analyst for Open Pixel, a Maryland web development consultancy.

{OPEN_PIXEL_CONTEXT}

Analyze these Maryland state procurement solicitations. Return a JSON array where each object has:
- "index": solicitation number (integer)
- "relevant": true or false
- "score": 1-5 (5=perfect fit, 1=tangential)
- "reason": one sentence
- "summary": if relevant=true, 2-sentence plain-English summary for the BD team
- "action": if relevant=true, recommended next step

Mark relevant=true only if Open Pixel could realistically bid based on web dev / IT consulting.
Exclude hardware, construction, janitorial, food, pure network hardware renewals.
Return ONLY valid JSON array, no markdown, no preamble.

{solicitations_text}
"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        try:
            results = json.loads(raw)
            for result in results:
                idx = result.get("index", 1) - 1
                if 0 <= idx < len(batch) and result.get("relevant"):
                    enriched = batch[idx].copy()
                    enriched["_score"]   = result.get("score", 0)
                    enriched["_reason"]  = result.get("reason", "")
                    enriched["_summary"] = result.get("summary", "")
                    enriched["_action"]  = result.get("action", "")
                    scored.append(enriched)
        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parse error in batch {batch_num + 1}: {e}")

    scored.sort(key=lambda x: x.get("_score", 0), reverse=True)
    print(f"✅ Claude identified {len(scored)} relevant opportunities")
    return scored


# ─────────────────────────────────────────────
# STEP 4: Change detection
# ─────────────────────────────────────────────
def get_row_id(row: dict) -> str:
    key = f"{row.get('Agency Name','')}-{row.get('Description','')}-{row.get('Procurement Method','')}"
    return hashlib.md5(key.encode()).hexdigest()

def load_snapshot() -> dict:
    if Path(SNAPSHOT_FILE).exists():
        with open(SNAPSHOT_FILE) as f:
            return json.load(f)
    return {}

def save_snapshot(opportunities: list[dict]):
    snapshot = {get_row_id(o): {
        "agency":      o.get("Agency Name"),
        "description": o.get("Description"),
        "score":       o.get("_score"),
        "first_seen":  datetime.now().isoformat()
    } for o in opportunities}
    with open(SNAPSHOT_FILE, "w") as f:
        json.dump(snapshot, f, indent=2)
    print(f"💾 Snapshot saved ({len(snapshot)} entries)")

def find_new_opportunities(current: list[dict], snapshot: dict) -> list[dict]:
    new_opps = [o for o in current if get_row_id(o) not in snapshot]
    print(f"🆕 {len(new_opps)} new opportunities vs. last run")
    return new_opps


# ─────────────────────────────────────────────
# STEP 5: ClickUp task creation
# ─────────────────────────────────────────────
def create_clickup_task(opp: dict) -> bool:
    agency  = opp.get("Agency Name", "Unknown Agency")
    desc    = opp.get("Description", "")
    value   = opp.get("Estimated Total Contract Award (no options)", "TBD")
    ad_date = opp.get("Estimated Advertisement Date", "TBD")
    method  = opp.get("Procurement Method", "")
    po_name = opp.get("PO Name", "")
    po_email= opp.get("PO Email", "")
    score   = opp.get("_score", "")
    summary = opp.get("_summary", "")
    action  = opp.get("_action", "")

    task_name = f"🏛️ MD Procurement | {agency} — {desc[:60]}"
    task_body = f"""**Maryland State Procurement Opportunity**

**Agency:** {agency}
**Description:** {desc}
**Estimated Value:** {value}
**Anticipated Ad Date:** {ad_date}
**Procurement Method:** {method}

**Procurement Officer:** {po_name}
**Email:** {po_email}

---
**Claude Assessment (Score: {score}/5)**
{summary}

**Next Step:** {action}

---
*Source: MD Procurement Forecast — gomdsmallbiz.maryland.gov*
*Auto-generated by Open Pixel Procurement Agent — {datetime.now().strftime('%B %d, %Y')}*
"""

    url = f"https://api.clickup.com/api/v2/list/{CLICKUP_LIST_ID}/task"
    headers = {"Authorization": CLICKUP_API_KEY, "Content-Type": "application/json"}
    payload = {
        "name": task_name,
        "description": task_body,
        "notify_all": True,
        "tags": ["bd", "maryland-state", "procurement"],
        "priority": 2 if score >= 4 else 3,
    }

    r = requests.post(url, headers=headers, json=payload)
    if r.status_code in (200, 201):
        print(f"  ✅ Task created: {task_name[:70]}")
        return True
    else:
        print(f"  ❌ ClickUp error {r.status_code}: {r.text[:200]}")
        return False


# ─────────────────────────────────────────────
# STEP 6: Save CSV report
# ─────────────────────────────────────────────
def save_report(all_opps: list[dict], new_opps: list[dict], source_file: str):
    import csv
    REPORTS_DIR.mkdir(exist_ok=True)
    new_ids = {get_row_id(o) for o in new_opps}
    run_date = datetime.now().strftime('%Y-%m-%d %H:%M')
    filename = REPORTS_DIR / f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

    fieldnames = [
        "is_new", "score", "agency", "description", "value",
        "ad_date", "method", "po_name", "po_email", "summary", "action", "run_date", "source_file"
    ]

    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for o in all_opps:
            writer.writerow({
                "is_new":      "YES" if get_row_id(o) in new_ids else "no",
                "score":       o.get("_score"),
                "agency":      o.get("Agency Name"),
                "description": o.get("Description"),
                "value":       o.get("Estimated Total Contract Award (no options)"),
                "ad_date":     o.get("Estimated Advertisement Date"),
                "method":      o.get("Procurement Method"),
                "po_name":     o.get("PO Name"),
                "po_email":    o.get("PO Email"),
                "summary":     o.get("_summary"),
                "action":      o.get("_action"),
                "run_date":    run_date,
                "source_file": source_file,
            })
    print(f"📄 Report saved: {filename}")


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Open Pixel MD Procurement Agent")
    parser.add_argument("--file",    required=True, help="Path to MD Procurement Forecast .xls")
    parser.add_argument("--dry-run", action="store_true", help="Score but don't create ClickUp tasks")
    parser.add_argument("--all",     action="store_true", help="Process all opps, not just new ones")
    args = parser.parse_args()

    if not Path(args.file).exists():
        print(f"❌ File not found: {args.file}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  Open Pixel Procurement Agent")
    print(f"  {datetime.now().strftime('%B %d, %Y %H:%M')}")
    print(f"{'='*60}\n")

    rows         = parse_forecast(args.file)
    candidates   = prefilter(rows)
    all_opps     = score_with_claude(candidates)

    if not all_opps:
        print("ℹ️  No relevant opportunities found.")
        return

    snapshot     = load_snapshot()
    new_opps     = all_opps if (args.all or not snapshot) else find_new_opportunities(all_opps, snapshot)

    if not args.dry_run and new_opps:
        print(f"\n📋 Creating {len(new_opps)} ClickUp tasks...\n")
        successes = sum(create_clickup_task(o) for o in new_opps)
        print(f"\n✅ {successes}/{len(new_opps)} tasks created")
    elif args.dry_run:
        print(f"\n🔍 DRY RUN — would create {len(new_opps)} ClickUp tasks:")
        for o in new_opps:
            print(f"  [{o.get('_score')}/5] {o.get('Agency Name')} — {o.get('Description','')[:60]}")
            print(f"         → {o.get('_action')}")

    save_snapshot(all_opps)
    save_report(all_opps, new_opps, args.file)

    print(f"\n{'='*60}")
    print(f"  Done. {len(all_opps)} total | {len(new_opps)} new this run.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
