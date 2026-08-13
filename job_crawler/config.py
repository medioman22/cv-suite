"""
Job-crawler configuration.
This starter is tuned to an ML / CV / robotics profile in Switzerland — RETUNE the
keywords, negatives, locations, and company lists below to your own field.
Edit the knobs below; no code changes needed elsewhere.
"""

# Load secrets from a git-ignored .env (KEY=VALUE lines) into the environment,
# so keys aren't hard-coded here and launchd/cron runs pick them up too.
import os as _os
_env = _os.path.join(_os.path.dirname(__file__), ".env")
if _os.path.exists(_env):
    for _l in open(_env):
        _l = _l.strip()
        if _l and not _l.startswith("#") and "=" in _l:
            _k, _v = _l.split("=", 1)
            _os.environ.setdefault(_k.strip(), _v.strip())

# ── HARD TITLE GATE ────────────────────────────────────────────────────────
# A posting is only considered if its TITLE contains one of these substrings.
# This is what kills the noise (video editors, PMs, voice actors, etc. whose
# *descriptions* happen to mention "AI/generative" but aren't ML/CV roles).
CORE_TITLE_TERMS = [
    "machine learning", "ml engineer", "ml/ai", "ai/ml", "computer vision",
    "perception", "robotic", "embodied", "avatar", "deep learning",
    "research scientist", "ai engineer", "ai researcher", "applied scientist",
    "digital human", "generative ai", "foundation model", "pose", "motion capture",
    "3d vision", "xr ", "ar/vr", "staff ml", "principal ml", "computer graphics",
]

# ── Profile keywords (lowercase). Weight = strength of signal. ─────────────
KEYWORDS = {
    # core spike
    "computer vision": 5, "embodied ai": 6, "perception": 4, "avatar": 5,
    "digital human": 5, "pose estimation": 5, "body tracking": 5, "motion capture": 4,
    "generative": 3, "diffusion": 4, "foundation model": 3, "vision-language": 4,
    "vlm": 3, "multimodal": 3, "robotics": 4, "human-robot": 5, "teleoperation": 5,
    "xr": 3, "ar/vr": 3, "on-device": 3, "real-time": 2,
    # role / level (kept specific; generic "senior/lead/manager" removed as noise)
    "machine learning engineer": 4, "ml engineer": 4, "research scientist": 4,
    "applied scientist": 4, "deep learning": 3, "staff": 2, "principal": 2,
}

# ── Downrank (noise / poor fit). Penalty subtracted from score. ────────────
NEGATIVE_KEYWORDS = {
    "sales": 4, "account executive": 5, "recruiter": 5, "talent acquisition": 5,
    "intern": 4, "internship": 4, "working student": 5, "apprentice": 4, "thesis": 3,
    "java": 2, "backend": 2, ".net": 3, "php": 3, "palantir": 3, "salesforce": 5,
    "fintech": 1, "banking": 1, "solution architect": 2, "product manager": 2,
    "unreal": 1, "technical animator": 2, "sap": 4, "sre": 1, "cybersecurity": 2,
    # noise seen in the wild
    "video editor": 5, "videographer": 5, "motion designer": 5, "voice actor": 6,
    "designer": 3, "frontend": 4, "customer success": 6, "web design": 5,
    "project manager": 4, "consultant": 2, "wordpress": 5, "content": 2,
    # non-ML roles that trip the title gate on "robotics"/"AI" (seen on jobs.ch)
    "legal counsel": 6, "category manager": 5, "technician": 3, "patent": 4,
    "procurement": 4, "sales manager": 5,
}

# ── Location scoring (substring, lowercase) ────────────────────────────────
# MATCH-ONLY (his 2026-07-14 pref): location no longer affects the score — the
# bonuses below are 0, so ranking is pure skills/domain match. Geography is kept
# only as the folder LOC tag. The BLOCK list still drops clear low-comp noise.
LOCATIONS_PRIMARY = ["switzerland", "zurich", "zürich", "lausanne", "geneva",
                     "genève", "basel", "bern", "nyon", "vaud", "lugano", "zug"]
LOCATIONS_SECONDARY = ["europe", "emea", "germany", "france", "italy", "austria",
                       "united kingdom", "london", "amsterdam", "munich", "milan",
                       "spain", "netherlands", "sweden", "ireland", "dublin", "paris",
                       "berlin", "poland", "portugal", "belgium", "denmark", "finland",
                       "norway", "czech", "stockholm", "copenhagen", "barcelona", "madrid"]
LOCATIONS_US = ["united states", "usa", "u.s.", ", ca", ", wa", ", ny", ", tx",
                ", ma", "california", "seattle", "san francisco", "sunnyvale",
                "mountain view", "cupertino", "menlo park", "santa clara", "san mateo",
                "los gatos", "los angeles", "new york", "bellevue", "redmond",
                "austin", "boston", "canada", "toronto"]
# Keep CH/EU/US + remote + high-income hubs (Japan/Singapore/Korea/HK/Taiwan/China/
# Israel/Gulf/Australia/Canada — all get the +US reach bonus). Drop only low-comp
# regions where relocation makes little sense.
LOCATIONS_BLOCK = ["india", "bengaluru", "bangalore", "hyderabad", "pune", "gurgaon",
                   "chennai", "mumbai", "delhi", "noida", "kolkata",
                   "philippines", "manila", "indonesia", "jakarta", "vietnam", "hanoi",
                   "thailand", "bangkok", "malaysia", "kuala lumpur", "pakistan",
                   "bangladesh", "sri lanka", "nepal",
                   "egypt", "cairo", "nigeria", "lagos", "kenya", "morocco", "ghana",
                   "brazil", "brasil", "mexico", "argentina", "colombia", "chile",
                   "peru", "ecuador", "turkey", "istanbul", "ukraine"]
LOC_BONUS_PRIMARY   = 0      # match-only ranking (his 2026-07-14 pref): location is a tag, not a score
LOC_BONUS_REMOTE    = 0      # remote (any)
LOC_BONUS_SECONDARY = 0      # rest of Europe
LOC_BONUS_US        = 0      # US / Canada
LOC_PENALTY_OFF     = 6      # blocked region (Asia/ME/LATAM/…) — subtracted
ALLOW_REMOTE = True          # keep remote roles even if location text doesn't match
# Back-compat: some tooling still reads LOCATIONS (union of the tiers + remote).
LOCATIONS = LOCATIONS_PRIMARY + LOCATIONS_SECONDARY + LOCATIONS_US + ["remote"]
MIN_SCORE = 6                # minimum score to be suggested
MAX_PER_COMPANY = 3          # cap near-duplicate roles from one board (0 = no cap)

# ── Sources ────────────────────────────────────────────────────────────────
# Keyless aggregators — work out of the box, no account needed:
ENABLE_ARBEITNOW = True
ENABLE_REMOTIVE  = True
ENABLE_REMOTEOK  = True
REMOTIVE_QUERIES = ["machine learning", "computer vision", "robotics"]

# Per-company ATS boards (free, reliable, precise). Add the board slug/token for
# companies you care about. Verify a token by opening the URL shown in README.md.
# Starter set (verified working 2026-07-13) — embodied-AI / robotics / CV firms.
# Edit freely; find tokens per the README. Many are US-based, so they'll rank
# lower unless remote (location is a soft penalty, not a hard filter).
GREENHOUSE_COMPANIES = [
    "figure",     # humanoid robots
    "waymo",      # AV perception (US)
    "scaleai",    # data / robotics
    "anthropic",  # AI lab
    "wayve",      # autonomous driving, embodied AI (London)
    "nuro",       # AV robotics
    "scandit",    # computer vision — Zurich 🇨🇭
]
LEVER_COMPANIES      = []            # (none of the probed set used Lever)
ASHBY_COMPANIES      = [
    "1x",                    # humanoid robots
    "physicalintelligence",  # robot foundation models / embodied AI ⭐
    "synthesia",             # AI avatars / digital humans ⭐ (your exact space)
    "elevenlabs",            # voice AI (audio→face adjacency)
    "openai",                # AI lab (robotics/multimodal roles)
    "character",             # character.ai — embodied agents / NPCs
    "standardbots",          # robotics
    "pika",                  # generative video (diffusion)
]

# Adzuna — good Switzerland coverage. Free key: https://developer.adzuna.com/
# Export ADZUNA_APP_ID and ADZUNA_APP_KEY in your environment.
ENABLE_ADZUNA = True
ADZUNA_COUNTRY = "ch"
ADZUNA_QUERIES = ["machine learning engineer", "computer vision", "AI engineer",
                  "robotics", "research scientist", "perception", "deep learning"]

# jobs.ch — the largest Swiss board. Official public JSON search API (no key),
# Switzerland-wide; the single best source for Swiss on-site ML/CV/robotics roles.
ENABLE_JOBSCH  = True
JOBSCH_QUERIES = ["machine learning", "computer vision", "AI engineer",
                  "robotics", "research scientist", "perception", "deep learning"]
JOBSCH_PAGES   = 3                   # pages of ~20 results per query (rows capped at 20)
# NOTE — evaluated but NOT added: SwissDevJobs/SwissTechJobs (API deprecated,
# needs their permission), Himalayas (API ignores search/country filters — returns
# all 102k jobs, not efficiently filterable), We Work Remotely (only a generic
# web-dev RSS category — zero ML/CV roles survive the title gate), and
# Wellfound/Otta/Glassdoor/Indeed (login-walled or heavy anti-bot). jobs.ch +
# Adzuna already give strong Swiss on-site coverage.

# ── Big-tech direct career-site APIs (no public ATS boards) ────────────────
# Major tech firms in Matteo's field. Most are US-heavy, so the Swiss-first
# location scoring drops off-location roles unless they're a strong match or in
# a Zurich office (Google/Meta/Apple/MS/NVIDIA/Amazon all have one). See bigtech.py.
ENABLE_BIGTECH  = True
BIGTECH_QUERIES = ["computer vision", "machine learning", "perception",
                   "robotics", "research scientist", "deep learning"]
BIGTECH_LIMIT   = 20                 # results per query per source
ENABLE_AMAZON   = True
AMAZON_LOC      = "Switzerland"      # soft bias only; scoring still tiers location
ENABLE_NETFLIX  = True
ENABLE_SNAP     = True
# Any Workday-based careers site: {label, host, tenant, site}. Find the pieces in
# the careers URL: https://{host}.myworkdayjobs.com/.../{site}  (host e.g. nvidia.wd5).
WORKDAY_COMPANIES = [
    {"label": "NVIDIA", "host": "nvidia.wd5", "tenant": "nvidia", "site": "NVIDIAExternalCareerSite"},
]
# NOT directly crawlable (custom/GraphQL/blocked APIs) — covered by Adzuna +
# the LinkedIn email pipeline instead: Meta, Google, Apple, Microsoft.

# LinkedIn guest search — UNOFFICIAL, violates LinkedIn's ToS, easily rate-limited
# or blocked. OFF by default. If you enable it, keep volume low and the delay high.
# Use at your own risk. See README.md.
ENABLE_LINKEDIN = False
LINKEDIN_QUERIES = ["computer vision engineer", "machine learning engineer", "embodied AI"]
LINKEDIN_LOCATION = "Switzerland"
LINKEDIN_MAX_PER_QUERY = 25
LINKEDIN_DELAY_SEC = 8

# ── LinkedIn job-alert EMAIL ingestion (ToS-safe: reads YOUR OWN inbox) ────
# LinkedIn emails you job-alert digests; this turns those into inbox links.
EMAIL_MODE   = "imap"                # "folder" (read .eml files) or "imap"
EMAIL_EML_DIR = "linkedin_emails"    # drop/save LinkedIn alert emails here as .eml
# IMAP (e.g. Gmail): set env EMAIL_USER / EMAIL_PASS (Gmail needs an App Password)
EMAIL_HOST   = "imap.gmail.com"
EMAIL_FOLDER = "INBOX"
EMAIL_SEARCH = '(FROM "linkedin.com" SUBJECT "job")'   # narrow to job alerts
EMAIL_MAX    = 50

# ── Output ─────────────────────────────────────────────────────────────────
SUGGESTIONS_FILE = "suggestions.md"     # ranked crawler output (always written)
SEEN_PATH        = "seen.json"          # dedupe store
JOBS_MD_PATH     = "../tracking/JOBS.md"         # parsed so already-tracked jobs aren't re-suggested
APPEND_TO_INBOX  = True                 # feed top NEW links into your inbox workflow
INBOX_PATH       = "../tracking/INBOX.md"
MAX_INBOX_APPEND = 10
# Section headings each tool writes under (must match INBOX.md exactly):
INBOX_SECTION_CRAWLER  = "## 🤖 Crawler (ATS & aggregators)"
INBOX_SECTION_LINKEDIN = "## 🔗 LinkedIn (email / bookmarklet)"
