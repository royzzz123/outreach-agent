#!/usr/bin/env python3
"""
Outreach Agent — Lead Discovery & Analysis (MiniMax M2)

Finds companies, researches them, enriches contacts, and explains WHY to reach out.
All leads saved to data/leads.csv and rendered via the web frontend.

Usage:
    python agent.py                                              # Default: SQL Developer, US
    python agent.py --query "Analytics Engineer" --max-leads 10
    python agent.py --query "BI Developer" --location "New York" --max-leads 15
"""

import argparse
import json
import sys

from openai import OpenAI

from config import config
from tools import find_decision_maker, save_lead, scrape_company_website, search_linkedin_jobs

# ---------------------------------------------------------------------------
# MiniMax client
# ---------------------------------------------------------------------------

def get_client() -> OpenAI:
    return OpenAI(api_key=config.minimax_api_key, base_url=config.minimax_base_url)


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_linkedin_jobs",
            "description": (
                "Search LinkedIn / Google Jobs for companies currently hiring target roles "
                "(SQL Developer, Data Analyst, BI Developer, Analytics Engineer, etc.). "
                "Returns company name, job title, location, description snippet, job URL."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Job role to search. E.g. 'Data Analyst'"},
                    "location": {"type": "string", "description": "Location filter. E.g. 'United States'"},
                    "max_results": {"type": "integer", "description": "Max results (default 10)"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_company_website",
            "description": (
                "Scrape the company website to understand what they do, their tech stack, "
                "and data-related pain signals. Always call this before analyze_lead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "website_url": {"type": "string", "description": "Leave empty to auto-discover."},
                },
                "required": ["company_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_decision_maker",
            "description": (
                "Find the best person to contact at a company via Hunter.io. "
                "Priority: CTO → VP Engineering → Head of Data → VP Analytics → CEO."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {"type": "string"},
                    "domain": {"type": "string", "description": "Company domain, e.g. 'acme.com'"},
                },
                "required": ["company_name", "domain"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_and_save_lead",
            "description": (
                "Analyze this lead with AI, then IMMEDIATELY save it to the database. "
                "This is one atomic operation — analysis + persistence happen together. "
                "Call this AFTER scraping the website and finding the decision maker. "
                "Pass ALL gathered data (company, contact, job, website, tech) so the AI "
                "can produce: reason_to_reach_out, fit_score (1-10), fit_reasoning."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "company": {"type": "string"},
                    "job_title": {"type": "string"},
                    "job_url": {"type": "string"},
                    "job_description": {"type": "string"},
                    "company_website": {"type": "string"},
                    "website_excerpt": {"type": "string"},
                    "tech_stack": {"type": "string", "description": "Comma-separated tech found on their site"},
                    "contact_name": {"type": "string"},
                    "contact_title": {"type": "string"},
                    "contact_email": {"type": "string"},
                    "contact_linkedin": {"type": "string", "description": "LinkedIn profile URL of the contact"},
                    "contact_phone": {"type": "string"},
                },
                "required": ["company", "job_title"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------

def execute_tool(name: str, inputs: dict) -> dict:
    if name == "search_linkedin_jobs":
        return search_linkedin_jobs(
            query=inputs["query"],
            location=inputs.get("location", "United States"),
            max_results=inputs.get("max_results", 10),
        )

    elif name == "scrape_company_website":
        return scrape_company_website(
            company_name=inputs["company_name"],
            website_url=inputs.get("website_url", ""),
        )

    elif name == "find_decision_maker":
        return find_decision_maker(
            company_name=inputs["company_name"],
            domain=inputs.get("domain", ""),
        )

    elif name == "analyze_and_save_lead":
        return _analyze_and_save(inputs)

    return {"error": f"Unknown tool: {name}"}


def _analyze_and_save(inputs: dict) -> dict:
    """
    Atomic operation: call MiniMax to analyze the lead, then immediately save to CSV.
    No separate save_lead step needed — data is never lost even if the agent is interrupted
    on a subsequent lead.
    """
    client = get_client()
    prompt = f"""You are a B2B sales analyst evaluating a prospect for a text-to-SQL AI consultancy.

Product: AI agents that let ANY team member query databases in plain English.
Value: eliminates analyst bottleneck, cuts data-request turnaround from days to seconds.

Prospect:
Company: {inputs.get('company')}
Hiring for: {inputs.get('job_title')}
Job description: {inputs.get('job_description', '')[:400]}
Website: {inputs.get('website_excerpt', '')[:400]}
Tech stack detected: {inputs.get('tech_stack', 'unknown')}
Contact: {inputs.get('contact_name', '')} — {inputs.get('contact_title', '')}

Output ONLY valid JSON with these exact keys:
{{
  "reason_to_reach_out": "1-2 punchy sentences. Reference the specific role + tech stack. Be concrete.",
  "fit_score": <integer 1-10>,
  "fit_reasoning": "one sentence explaining the score"
}}
"""

    resp = client.chat.completions.create(
        model=config.minimax_model,
        messages=[{"role": "user", "content": prompt}],
        max_tokens=512,
        temperature=0.3,
    )

    text = resp.choices[0].message.content.strip()
    if "<think>" in text and "</think>" in text:
        text = text.split("</think>")[-1].strip()
    if "```" in text:
        for part in text.split("```"):
            part = part.strip().lstrip("json").strip()
            try:
                analysis = json.loads(part)
                break
            except json.JSONDecodeError:
                continue
        else:
            analysis = {}
    else:
        try:
            analysis = json.loads(text)
        except json.JSONDecodeError:
            analysis = {"reason_to_reach_out": text[:200], "fit_score": 5, "fit_reasoning": "parse error"}

    # Build and immediately persist the full lead record
    lead = {
        "company":           inputs.get("company", ""),
        "contact_name":      inputs.get("contact_name", ""),
        "contact_title":     inputs.get("contact_title", ""),
        "contact_email":     inputs.get("contact_email", ""),
        "contact_linkedin":  inputs.get("contact_linkedin", ""),
        "contact_phone":     inputs.get("contact_phone", ""),
        "job_title":         inputs.get("job_title", ""),
        "job_url":           inputs.get("job_url", ""),
        "company_website":   inputs.get("company_website", ""),
        "tech_stack":        inputs.get("tech_stack", ""),
        "reason_to_reach_out": analysis.get("reason_to_reach_out", ""),
        "fit_score":         analysis.get("fit_score", ""),
        "fit_reasoning":     analysis.get("fit_reasoning", ""),
        "status":            "discovered",
    }

    save_result = save_lead(lead)
    return {**analysis, "saved": save_result.get("saved", False), "company": inputs.get("company")}


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are a lead discovery agent for a text-to-SQL AI consultancy.
Find companies bottlenecked by data access, research them, enrich contacts, and explain WHY to reach out.

STRICT WORKFLOW — process each company FULLY before moving to the next:
1. search_linkedin_jobs — get a list of companies
2. For EACH company, in sequence (finish one before starting the next):
   a. scrape_company_website — always use https:// prefix on URLs (e.g. "https://rivian.com")
   b. find_decision_maker — try the obvious domain (e.g. "rivian.com")
   c. analyze_and_save_lead — pass ALL data collected in steps a+b.
      This BOTH analyzes AND saves atomically. Never skip this step.
      Pass contact_linkedin from the find_decision_maker result as contact_linkedin.
3. After all leads: print a summary table.

SKIP if: clearly a staffing agency / recruiter.
NEVER batch analyze calls — do one company end-to-end at a time.
Always prefix website URLs with https://.
"""


# ---------------------------------------------------------------------------
# Main agent loop
# ---------------------------------------------------------------------------

def run_agent(
    query: str,
    location: str = "United States",
    max_leads: int = 10,
):
    client = get_client()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": (
            f"Find companies hiring '{query}' in '{location}'. "
            f"Process up to {max_leads} leads (skip staffing agencies). "
            f"Research each one and save to the database."
        )},
    ]

    print(f"\n[Agent] Searching: '{query}' | Location: {location} | Max leads: {max_leads}")
    print("=" * 60)

    while True:
        response = client.chat.completions.create(
            model=config.minimax_model,
            messages=messages,
            tools=TOOLS,
            tool_choice="auto",
            max_tokens=8192,
        )

        msg = response.choices[0].message
        finish_reason = response.choices[0].finish_reason

        # Print assistant text (strip <think> blocks for cleaner output)
        if msg.content:
            display = msg.content
            if "<think>" in display and "</think>" in display:
                display = display.split("</think>")[-1].strip()
            if display:
                print(f"\n[Agent] {display}")

        if finish_reason == "stop" or not msg.tool_calls:
            print("\n[Agent] Done. Open http://localhost:5050 to view leads.")
            break

        messages.append(msg)

        for tc in msg.tool_calls:
            name = tc.function.name
            try:
                inputs = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                inputs = {}

            # Clean log line
            log_args = {k: v for k, v in inputs.items() if k not in ("job_description", "website_excerpt")}
            print(f"\n  → {name}({json.dumps(log_args)[:120]})")

            result = execute_tool(name, inputs)

            # Brief result summary
            if isinstance(result, list):
                print(f"    ✓ {len(result)} results")
            elif isinstance(result, dict):
                if "error" in result:
                    print(f"    ✗ {result['error'][:80]}")
                elif "reason_to_reach_out" in result:
                    print(f"    ✓ Score {result.get('fit_score')}/10 — {result['reason_to_reach_out'][:80]}...")
                elif "saved" in result:
                    print(f"    ✓ Saved: {result.get('company')}")
                else:
                    print(f"    ✓ OK")

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "content": json.dumps(result),
            })


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Outreach Lead Discovery Agent")
    parser.add_argument("--query", default="Analytics Engineer",
                        help="Role to search for (default: 'Analytics Engineer')")
    parser.add_argument("--location", default="United States",
                        help="Location filter (default: 'United States')")
    parser.add_argument("--max-leads", type=int, default=10,
                        help="Max leads to process (default: 10)")
    args = parser.parse_args()

    if not config.minimax_api_key:
        print("ERROR: MINIMAX_API_KEY not set in .env")
        sys.exit(1)

    run_agent(query=args.query, location=args.location, max_leads=args.max_leads)


if __name__ == "__main__":
    main()
