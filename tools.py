"""
Tool implementations for the outreach lead-discovery agent.
Each function maps 1:1 to a tool definition in agent.py.
"""

import csv
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from config import config


# ---------------------------------------------------------------------------
# 1. SEARCH — find companies hiring target roles
# ---------------------------------------------------------------------------

def search_linkedin_jobs(query: str, location: str = "United States", max_results: int = 10) -> list[dict]:
    """
    Search via SerpAPI Google Jobs (most reliable).
    Falls back to direct Google scraping if no SERP_API_KEY.
    """
    if config.serp_api_key:
        return _search_via_serpapi(query, location, max_results)
    return _search_via_google_scrape(query, location, max_results)


def _search_via_serpapi(query: str, location: str, max_results: int) -> list[dict]:
    params = {
        "engine": "google_jobs",
        "q": query,
        "location": location,
        "api_key": config.serp_api_key,
        "num": max_results,
    }
    try:
        resp = requests.get("https://serpapi.com/search", params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for job in data.get("jobs_results", [])[:max_results]:
            company = job.get("company_name", "")
            results.append({
                "company": company,
                "title": job.get("title", ""),
                "location": job.get("location", ""),
                "job_url": job.get("job_id", ""),
                "description_snippet": job.get("description", "")[:600],
                "source": "serpapi",
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def _search_via_google_scrape(query: str, location: str, max_results: int) -> list[dict]:
    """Free fallback using Google search."""
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"}
    search_q = f'site:linkedin.com/jobs "{query}" "{location}"'
    try:
        url = f"https://www.google.com/search?q={requests.utils.quote(search_q)}&num={max_results}"
        resp = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        results = []
        for g in soup.select("div.g")[:max_results]:
            title_el = g.select_one("h3")
            link_el = g.select_one("a")
            snippet_el = g.select_one(".VwiC3b")
            if not title_el:
                continue
            title = title_el.get_text()
            href = link_el["href"] if link_el else ""
            snippet = snippet_el.get_text() if snippet_el else ""
            company = _company_from_title(title)
            results.append({
                "company": company,
                "title": title,
                "location": location,
                "job_url": href,
                "description_snippet": snippet,
                "source": "google_scrape",
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


def _company_from_title(title: str) -> str:
    if " at " in title:
        return title.split(" at ", 1)[-1].strip()
    if " - " in title:
        return title.split(" - ", 1)[-1].strip()
    return title


# ---------------------------------------------------------------------------
# 2. SCRAPE — get company context from their website
# ---------------------------------------------------------------------------

def scrape_company_website(company_name: str, website_url: str = "") -> dict:
    """
    Scrape the company website for product description and tech stack signals.
    Returns url, text_excerpt, tech_mentions.
    """
    if not website_url:
        website_url = _find_company_website(company_name)
    if not website_url:
        return {"error": f"Could not find website for {company_name}"}

    # Auto-add scheme if missing (agent sometimes passes bare domain)
    if not website_url.startswith("http"):
        website_url = "https://" + website_url

    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        resp = requests.get(website_url, headers=headers, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")

        for tag in soup(["nav", "footer", "script", "style", "header"]):
            tag.decompose()

        text = soup.get_text(separator=" ", strip=True)[:4000]

        tech_keywords = [
            "Tableau", "Looker", "Power BI", "Metabase", "Redash", "Superset",
            "Snowflake", "BigQuery", "Redshift", "dbt", "Databricks", "Fivetran",
            "PostgreSQL", "MySQL", "SQL Server", "Oracle", "MongoDB",
            "Salesforce", "HubSpot", "Shopify", "SAP", "NetSuite",
            "Python", "R", "Excel", "Google Sheets",
        ]
        found_tech = [kw for kw in tech_keywords if kw.lower() in text.lower()]

        return {
            "url": website_url,
            "text_excerpt": text[:2000],
            "tech_mentions": found_tech,
            "company_name": company_name,
        }
    except Exception as e:
        return {"error": str(e), "url": website_url}


def _find_company_website(company_name: str) -> str:
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        q = f"{company_name} official site"
        url = f"https://www.google.com/search?q={requests.utils.quote(q)}&num=5"
        resp = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.select("a[href]"):
            href = a["href"]
            if "/url?q=" in href:
                actual = href.split("/url?q=")[1].split("&")[0]
                parsed = urlparse(actual)
                if parsed.netloc and "google" not in parsed.netloc and "youtube" not in parsed.netloc:
                    return actual
        return ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# 3. ENRICH — find decision maker contact info
# ---------------------------------------------------------------------------

def find_decision_maker(company_name: str, domain: str) -> dict:
    """
    Find best contact via Hunter.io domain search.
    Priority: CTO → VP Eng → Head of Data → VP Analytics → CEO → Founder
    """
    if config.hunter_api_key and domain:
        result = _hunter_domain_search(domain)
        if result.get("email"):
            return result
        # Try common domain variants if primary fails
        for variant in _domain_variants(company_name, domain):
            result = _hunter_domain_search(variant)
            if result.get("email"):
                return result

    if config.apollo_api_key:
        return _apollo_people_search(company_name)

    return {"note": "No enrichment API result", "email": "", "name": "", "title": "", "linkedin_url": ""}


def _hunter_domain_search(domain: str) -> dict:
    priority_titles = [
        "cto", "chief technology", "vp engineering", "vp of engineering",
        "head of data", "head of analytics", "vp data", "vp analytics",
        "director of engineering", "director of data", "chief data",
        "ceo", "founder", "co-founder",
    ]
    try:
        params = {
            "domain": domain,
            "api_key": config.hunter_api_key,
            "limit": 20,
            "seniority": "senior,executive,director",
        }
        resp = requests.get("https://api.hunter.io/v2/domain-search", params=params, timeout=10)
        emails = resp.json().get("data", {}).get("emails", [])

        def score(e):
            title = (e.get("position") or "").lower()
            for i, kw in enumerate(priority_titles):
                if kw in title:
                    return i
            return 99

        emails.sort(key=score)
        if emails:
            top = emails[0]
            return {
                "name": f"{top.get('first_name', '')} {top.get('last_name', '')}".strip(),
                "email": top.get("value", ""),
                "title": top.get("position", ""),
                "confidence": top.get("confidence", 0),
                "contact_linkedin": top.get("linkedin", ""),  # normalized key
                "phone": top.get("phone_number", ""),
                "source": "hunter.io",
            }
        return {"email": ""}
    except Exception as e:
        return {"error": str(e), "email": ""}


def _domain_variants(company_name: str, original_domain: str) -> list[str]:
    """Generate plausible domain alternatives."""
    slug = re.sub(r"[^a-z0-9]", "", company_name.lower())
    base = original_domain.split(".")[0]
    variants = []
    for tld in [".com", ".io", ".co"]:
        for name in [slug, base]:
            candidate = f"{name}{tld}"
            if candidate != original_domain:
                variants.append(candidate)
    return variants[:4]


def _apollo_people_search(company_name: str) -> dict:
    try:
        payload = {
            "api_key": config.apollo_api_key,
            "q_organization_name": company_name,
            "person_titles": ["CTO", "VP Engineering", "Head of Data", "VP Data", "CEO"],
            "page": 1,
            "per_page": 5,
        }
        resp = requests.post(
            "https://api.apollo.io/v1/mixed_people/search",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        people = resp.json().get("people", [])
        if people:
            p = people[0]
            return {
                "name": p.get("name", ""),
                "email": p.get("email", ""),
                "title": p.get("title", ""),
                "linkedin_url": p.get("linkedin_url", ""),
                "source": "apollo.io",
            }
        return {"email": "", "name": "", "title": ""}
    except Exception as e:
        return {"error": str(e), "email": ""}


# ---------------------------------------------------------------------------
# 4. SAVE — persist lead to CSV
# ---------------------------------------------------------------------------

LEAD_FIELDS = [
    "company", "contact_name", "contact_title",
    "contact_email", "contact_linkedin", "contact_phone",
    "job_title", "job_url", "company_website", "tech_stack",
    "reason_to_reach_out", "fit_score", "fit_reasoning",
    "status", "created_at",
]


def save_lead(lead: dict) -> dict:
    """Append lead to CSV. Creates file + headers if it doesn't exist."""
    path = Path(config.leads_csv)
    path.parent.mkdir(parents=True, exist_ok=True)

    lead.setdefault("status", "discovered")
    lead["created_at"] = datetime.utcnow().isoformat()

    write_header = not path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LEAD_FIELDS, extrasaction="ignore")
        if write_header:
            writer.writeheader()
        writer.writerow(lead)

    return {"saved": True, "path": str(path), "company": lead.get("company")}
