import os
from dotenv import load_dotenv

load_dotenv()

# AWS Bedrock config (credentials via env vars, ~/.aws/credentials, or IAM role)
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Brave Search API (https://brave.com/search/api — free tier: 2,000 queries/month)
BRAVE_API_KEY = os.getenv("BRAVE_API_KEY", "")

# Firestore — set to your own GCP project ID, or leave empty to disable logging
FIRESTORE_PROJECT = os.getenv("FIRESTORE_PROJECT", "")

# Models — Bedrock cross-region inference profile IDs (March 2026)
MODEL_FAST = "us.anthropic.claude-haiku-4-5-20251001-v1:0"   # Intent parsing, recommendations
MODEL_SMART = "us.anthropic.claude-sonnet-4-6"               # Web search, complex reasoning

# Browser
HEADLESS = os.getenv("HEADLESS", "true").lower() == "true"
PAGE_LOAD_TIMEOUT_MS = 15000
SCREENSHOT_DELAY_MS = 1500

# Agent loop (legacy v1)
MAX_AGENT_STEPS = 35

# Seat scoring weights
WEIGHT_CENTER = 0.40
WEIGHT_ROW = 0.35
WEIGHT_ADJACENCY = 0.25
IDEAL_ROW_RATIO = 0.65  # 65% back from screen is ideal

# Human-like behavior
MIN_ACTION_DELAY_MS = 800
MAX_ACTION_DELAY_MS = 2500

# Chain entry points
CHAINS = {
    "fandango": "https://www.fandango.com",
    "amc": "https://www.amctheatres.com",
    "cinemark": "https://www.cinemark.com",
}
