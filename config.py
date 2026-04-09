import os
from dataclasses import dataclass, field
from typing import List

from dotenv import load_dotenv
load_dotenv()

@dataclass
class Config:
    # --- API Keys ---
    minimax_api_key: str = os.getenv("MINIMAX_API_KEY", "")
    minimax_model: str = os.getenv("MINIMAX_MODEL", "MiniMax-M2-7")
    minimax_base_url: str = "https://api.minimaxi.chat/v1"      # MiniMax international endpoint

    serp_api_key: str = os.getenv("SERP_API_KEY", "")          # serpapi.com — for LinkedIn/Google job search
    hunter_api_key: str = os.getenv("HUNTER_API_KEY", "")      # hunter.io — email finder
    apollo_api_key: str = os.getenv("APOLLO_API_KEY", "")      # apollo.io — richer contact enrichment

    # --- Your Identity (injected into outreach messages) ---
    sender_name: str = os.getenv("SENDER_NAME", "")
    sender_role: str = os.getenv("SENDER_ROLE", "Founder")
    website_url: str = os.getenv("WEBSITE_URL", "")
    pitch_pdf_url: str = os.getenv("PITCH_PDF_URL", "")        # Hosted PDF link (Google Drive, Notion, etc.)
    cal_link: str = os.getenv("CAL_LINK", "")                  # Cal.com booking link

    # --- Gmail (App Password — not your main password) ---
    gmail_user: str = os.getenv("GMAIL_USER", "")
    gmail_app_password: str = os.getenv("GMAIL_APP_PASSWORD", "")  # https://myaccount.google.com/apppasswords

    # --- LinkedIn Automation (Playwright) ---
    linkedin_email: str = os.getenv("LINKEDIN_EMAIL", "")
    linkedin_password: str = os.getenv("LINKEDIN_PASSWORD", "")

    # --- Targeting Parameters ---
    company_size_min: int = 50
    company_size_max: int = 500
    target_roles: List[str] = field(default_factory=lambda: [
        "SQL Developer",
        "Data Analyst",
        "BI Developer",
        "Analytics Engineer",
        "Business Intelligence Analyst",
        "Tableau Developer",
        "Looker Developer",
        "Reporting Analyst",
        "Data Engineer",
        "Database Administrator",
    ])
    target_industries: List[str] = field(default_factory=lambda: [
        "SaaS",
        "E-commerce",
        "Fintech",
        "Healthcare",
        "Logistics",
        "Digital Agency",
    ])

    # --- Paths ---
    leads_csv: str = "data/leads.csv"
    sent_log: str = "data/sent_log.csv"
    linkedin_queue: str = "data/linkedin_queue.csv"


config = Config()
