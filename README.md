# OSW Email Automation 🚀

**Enterprise-grade, AI-personalised email outreach system for OpenSource Weekend (OSW)**

Built with Python · Groq LLM · Async SMTP · Rich Terminal Dashboard

---

## Table of Contents

1. [System Architecture](#system-architecture)
2. [Tech Stack](#tech-stack)
3. [Project Structure](#project-structure)
4. [Quick Start](#quick-start)
5. [CSV Input Format](#csv-input-format)
6. [Configuration (.env)](#configuration-env)
7. [Usage & CLI Reference](#usage--cli-reference)
8. [Workflow Explained](#workflow-explained)
9. [Email Template Preview](#email-template-preview)
10. [Error Handling & Retry Policy](#error-handling--retry-policy)
11. [Logging & Monitoring](#logging--monitoring)
12. [Security & Compliance](#security--compliance)
13. [Running Tests](#running-tests)
14. [Scaling Beyond 200 Emails](#scaling-beyond-200-emails)

---

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        OSW EMAIL AUTOMATION                          │
├──────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐     ┌─────────────────┐     ┌──────────────────┐  │
│  │  CSV Input  │────▶│  models.py      │────▶│  personalizer.py │  │
│  │  (pandas)   │     │  Validate &     │     │  Groq LLM        │  │
│  └─────────────┘     │  load rows      │     │  (async,         │  │
│                       └─────────────────┘     │   semaphore,     │  │
│                                               │   retries)       │  │
│                                               └────────┬─────────┘  │
│                                                        │            │
│                                               ┌────────▼─────────┐  │
│                                               │  renderer.py     │  │
│                                               │  Jinja2 HTML     │  │
│                                               │  template inject │  │
│                                               └────────┬─────────┘  │
│                                                        │            │
│  ┌──────────────────┐                        ┌────────▼─────────┐  │
│  │  logger.py       │◀───────────────────────│  dispatcher.py   │  │
│  │  JSONL + colour  │                        │  aiosmtplib      │  │
│  │  console logs    │                        │  Semaphore rate  │  │
│  └──────────────────┘                        │  limit + retry   │  │
│                                               └────────┬─────────┘  │
│  ┌──────────────────┐                                  │            │
│  │  dashboard.py    │◀─────────────────────────────────┘            │
│  │  Rich terminal   │                                               │
│  │  metrics panel   │                                               │
│  └──────────────────┘                                               │
└──────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
CSV File
  │
  ▼
[1] LOAD & VALIDATE
    • pandas read_csv
    • Column alias normalisation
    • RFC-5321 email validation (email-validator)
    • Batch limit applied
  │
  ▼
[2] LLM PERSONALISATION  (async, concurrency-limited)
    • Groq SDK AsyncGroq client
    • System prompt + tailored user prompt per recipient
    • Returns ≤ 5 concise bullet points
    • tenacity retry + exponential back-off on RateLimitError / ConnectionError
    • Fallback bullets on final failure (no email skipped)
  │
  ▼
[3] HTML RENDERING
    • Jinja2 renders static email_template.html
    • Injects: recipient_name, company_name, benefit_bullets_html
    • Plain-text fallback generated for MIME multipart
  │
  ▼
[4] SMTP DISPATCH  (async, rate-limited)
    • aiosmtplib STARTTLS connection per send
    • asyncio.Semaphore caps concurrent sends
    • Configurable inter-send delay (SEND_DELAY_SECONDS)
    • tenacity retry on transient SMTP errors
  │
  ▼
[5] LOGGING & DASHBOARD
    • Per-event JSONL records (timestamp, status, LLM output, errors)
    • Rich terminal dashboard with success/failure metrics
    • Exportable JSONL logs for downstream analytics
```

---

## Tech Stack

| Layer | Library | Purpose |
|---|---|---|
| LLM Personalisation | `groq` (AsyncGroq) | AI bullet generation |
| Data ingestion | `pandas` | CSV parsing & normalisation |
| Email building | `email` stdlib + `jinja2` | MIME multipart / HTML templating |
| SMTP delivery | `aiosmtplib` | Async STARTTLS SMTP |
| Rate limiting | `asyncio.Semaphore` + `asyncio-throttle` | Concurrency control |
| Retry / back-off | `tenacity` | Exponential retry on failures |
| Logging | `colorlog` + stdlib `logging` | Coloured console + JSONL files |
| Terminal dashboard | `rich` | Pretty metrics panel |
| Config | `python-dotenv` | `.env` file loading |
| Validation | `email-validator` | RFC-compliant email checks |
| Progress | `rich.progress` | Live progress bars |

---

## Project Structure

```
OSW_EMAIL_AUTOMATION/
├── main.py                        # CLI entry point & async orchestrator
├── requirements.txt               # All Python dependencies
├── sample_recipients.csv          # 26-row demo CSV
├── tests.py                       # Offline unit test suite
├── .env                           # Runtime configuration (edit this!)
│
├── osw_mailer/                    # Core package
│   ├── __init__.py
│   ├── config.py                  # Settings with validation
│   ├── models.py                  # Recipient dataclass + CSV loader
│   ├── personalizer.py            # Groq LLM async personaliser
│   ├── renderer.py                # Jinja2 HTML renderer
│   ├── dispatcher.py              # Async SMTP batch dispatcher
│   ├── dashboard.py               # Rich terminal dashboard
│   ├── logger.py                  # Dual-sink logging (console + JSONL)
│   └── templates/
│       └── email_template.html    # Static HTML email template
│
└── logs/                          # Auto-created at runtime
    ├── run_<timestamp>.jsonl      # General application logs
    └── send_events_<timestamp>.jsonl  # Structured send-event records
```

---

## Quick Start

### 1. Set up virtual environment

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment

Edit `.env` and fill in:
- `GROQ_API_KEY` — get from [console.groq.com](https://console.groq.com)
- `SMTP_USERNAME` / `SMTP_PASSWORD` — your Gmail app password
- `SENDER_EMAIL` — the From address

### 4. Prepare your CSV

Use the column names from [CSV Input Format](#csv-input-format)  
or drop your file in the project directory.

### 5. Run!

```bash
# Process ALL rows in the CSV
python main.py --csv sample_recipients.csv

# Process only 200 rows
python main.py --csv recipients.csv --limit 200

# Dry run (no emails sent — saves HTML preview to logs/)
python main.py --csv recipients.csv --dry-run
```

---

## CSV Input Format

| Column | Required | Description |
|---|---|---|
| `email` | ✅ | Recipient email address |
| `name` | ✅ | Full name of contact |
| `company_name` | ✅ | Organisation / company name |
| `company_type` | ✅ | See types below |
| `city` | optional | City (adds location context to LLM) |
| `state` | optional | State / province |
| `capacity` | optional | Team/community size |
| `industry` | optional | Industry sector (improves personalisation) |

### Supported `company_type` values

| Value | Description |
|---|---|
| `corporate` | Enterprise / business organisation |
| `startup` | Early-stage startup / venture |
| `community` | Developer / open-source community |
| `student` | Student group / college club |
| `individual` | Freelancer / independent developer |
| `ngo` | Non-profit organisation |
| `government` | Government / public-sector body |

> Column headers are **case-insensitive** and support common aliases  
> (e.g. `company`, `organisation`, `e-mail`, `full_name`).

---

## Configuration (.env)

```env
# Batch size: integer (e.g. 200) or "Max" for all rows
NO_OF_EMAIL_TO_PROCESS=Max

# Groq LLM
GROQ_API_KEY=your_groq_api_key_here
GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# SMTP (Gmail example — use App Password, not account password)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=you@gmail.com
SMTP_PASSWORD=your_16_char_app_password
SENDER_NAME=OpenSource Weekend Team
SENDER_EMAIL=you@gmail.com

# Rate limiting
MAX_CONCURRENT_SENDS=10     # emails in-flight simultaneously
SEND_DELAY_SECONDS=1        # seconds between concurrent groups

# Retry policy
MAX_RETRIES=3
RETRY_MIN_WAIT_SECONDS=2
RETRY_MAX_WAIT_SECONDS=30

# Logging
LOG_DIR=logs
LOG_LEVEL=INFO
```

---

## Usage & CLI Reference

```
python main.py [OPTIONS]

Options:
  --csv PATH      Path to recipients CSV file  [required]
  --limit N       Override batch limit from .env
  --dry-run       Personalise but skip SMTP send; saves HTML preview
  --no-dash       Skip the terminal metrics dashboard
  --help          Show this message and exit

Examples:
  python main.py --csv recipients.csv
  python main.py --csv recipients.csv --limit 50 --dry-run
  python main.py --csv big_list.csv --limit 500 --no-dash
```

---

## Workflow Explained

### Step 1 — Data Ingestion
`main.py` calls `load_recipients()` which uses **pandas** to read the CSV,  
normalises column names, validates emails with `email-validator`,  
and skips invalid rows with a warning log.

### Step 2 — LLM Personalisation
Each `Recipient` is passed to `generate_benefit_bullets()` (in `personalizer.py`).  
An **AsyncGroq** client sends a carefully crafted system + user prompt to Groq.  
Up to `MAX_CONCURRENT_SENDS` calls run simultaneously via `asyncio.Semaphore`.  
`tenacity` retries on `RateLimitError` or connectivity failures with exponential back-off.

### Step 3 — HTML Rendering
`renderer.py` calls `render_email(recipient)` which uses **Jinja2** to inject:
- `{{ recipient_name }}` — first name  
- `{{ company_name }}` — organisation  
- `{{ benefit_bullets_html }}` — LLM bullets converted to `<li>` elements

### Step 4 — SMTP Dispatch
`dispatcher.py` builds a `MIMEMultipart("alternative")` message with both  
plain-text and HTML parts. `aiosmtplib.send()` delivers via STARTTLS.  
A `Semaphore` limits concurrent sends; `tenacity` retries transient SMTP errors.

### Step 5 — Logging & Dashboard
Every send attempt writes a JSON record to `logs/send_events_<ts>.jsonl`.  
The `rich` dashboard displays a metrics panel and last-20-records table.

---

## Error Handling & Retry Policy

| Scenario | Behaviour |
|---|---|
| Invalid email in CSV | Skipped with a WARNING log |
| Missing required CSV column | Raises `ValueError` at startup |
| Groq `RateLimitError` | Retried up to `MAX_RETRIES` with exponential back-off |
| Groq API unreachable | Same retry + back-off; fallback bullets on final failure |
| SMTP connection error | Retried up to `MAX_RETRIES` with exponential back-off |
| SMTP auth failure | Logged as `failed`; not retried (auth errors are permanent) |
| Network timeout | Retried; 30-second per-connection timeout |
| Groq final failure | **Fallback bullets inserted** — email still sent |

---

## Logging & Monitoring

Two JSONL files are written per session under `logs/`:

### `run_<timestamp>.jsonl` — General application log
```json
{"ts":"2025-03-02T16:55:01+00:00","level":"INFO","logger":"osw_mailer.models","message":"CSV loaded: 200 valid recipients, 3 skipped."}
```

### `send_events_<timestamp>.jsonl` — Per-email structured events
```json
{
  "ts": "2025-03-02T16:55:12+00:00",
  "recipient_email": "alice@techcorp.com",
  "recipient_name": "Alice Johnson",
  "company": "TechCorp Solutions",
  "company_type": "corporate",
  "status": "success",
  "attempt": 1,
  "llm_output": "• Networking with 500+ practitioners\n• ..."
}
```

Both files are **newline-delimited JSON** and can be ingested into:
- **Elasticsearch / OpenSearch** for dashboards
- **BigQuery / Redshift** for analytics
- **Grafana** for live monitoring
- Any log aggregator (Datadog, Splunk, Loki)

---

## Security & Compliance

### SPF / DKIM / DMARC
- Use a dedicated sending domain with SPF records pointing to your SMTP provider.
- Enable DKIM signing in your email provider's DNS settings.
- Add a DMARC policy (`v=DMARC1; p=quarantine`) to protect your domain reputation.

### Credentials
- Store all secrets in `.env` — **never commit to Git**.
- Use Gmail App Passwords (not your account password) for SMTP.
- Rotate the Groq API key periodically.

### GDPR / CAN-SPAM / Indian IT Act compliance
- Every email includes a visible **Unsubscribe** link in the footer.
- Recipient data is never logged in raw form beyond email address + name.
- Process only data you have a legal basis to contact.
- Honor unsubscribe requests by removing records from your CSV before the next run.
- Store logs only as long as operationally necessary.

### Transport Security
- All SMTP connections use **STARTTLS** (TLS 1.2+).
- Groq SDK communicates over **HTTPS**.

---

## Running Tests

```bash
# Run the full offline unit test suite (no credentials required)
python tests.py

# Or with unittest discovery
python -m unittest tests -v
```

The test suite covers:
- Recipient data model behaviour
- CSV loading: valid rows, invalid emails, missing columns, limit enforcement
- HTML renderer: bullet conversion, template injection
- Personalizer: bullet cleaning, prompt building, mocked LLM calls

---

## Scaling Beyond 200 Emails

| Bottleneck | Solution |
|---|---|
| SMTP throughput | Use a transactional email API: **SendGrid**, **AWS SES**, **Mailgun** |
| LLM rate limits | Increase `MAX_RETRIES`, reduce `MAX_CONCURRENT_SENDS`, or upgrade Groq plan |
| CSV size | Stream CSV with `pandas.read_csv(chunksize=N)` in `models.py` |
| Scale to 10 k+ emails | Add **Redis + Celery** or **RabbitMQ** as a task queue |
| Deliverability | Warm up sending IP, segment sends over multiple hours, monitor bounce rates |

---

## License

MIT — see project repository for details.  

---

*Built for GDG × OpenSource Weekend — empowering the open-source community at scale.*