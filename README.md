# 🚀 Capital Structure Extraction Platform

## AI‑Driven SEC Filing Parser + Enterprise Value Engine + Web Application

A production‑ready full‑stack financial analytics platform that
automates capital structure extraction from SEC filings and generates
institutional‑grade Enterprise Value outputs.

This system combines: - Financial parsing logic - Deterministic
enterprise value calculations - FastAPI backend orchestration - React
frontend UI - Dockerized deployment architecture

------------------------------------------------------------------------

# 📌 What This Project Does

The application allows users to upload SEC filing components and
automatically generates:

• Structured Capital Stack (JSON)\
• Net Debt Calculation\
• Enterprise Value Calculation\
• AAP‑style formatted HTML output\
• Downloadable artifacts

Designed for: - Private Equity screening - Credit research automation -
Investment banking modeling - Financial AI pipelines - SEC filing
intelligence systems

------------------------------------------------------------------------

# 📂 Required Inputs

Users upload:

-   balance_sheet.json
-   debt_note.html
-   lease_note.html
-   metadata.json
-   Market Cap (\$mm)

------------------------------------------------------------------------

# 📊 Financial Logic

Net Debt = Total Debt − Cash & Cash Equivalents

Enterprise Value = Net Debt + Noncontrolling Interests + Market
Capitalization

Precision safeguards ensure: - No rounding drift - Exact formatting
alignment - Deterministic outputs

------------------------------------------------------------------------

# 🏗️ System Architecture

Frontend (React + Vite) │ ▼ FastAPI Backend (Job Manager) │ ├──
balance_sheet_json_parser.py ├── debt_note_html_parser.py ├──
lease_note_html_parser.py ├── capital_structure_builder.py └──
html_renderer.py │ ▼ Outputs: ├── built_capital_structure.json └──
generated.html

------------------------------------------------------------------------

# 🧩 Tech Stack

Backend: - Python 3.10+ - FastAPI - BeautifulSoup (HTML parsing) -
Uvicorn - Subprocess execution - Docker

Frontend: - React (Vite) - Axios - Job polling architecture - iframe
HTML rendering

Infrastructure: - Docker Compose - Environment variable configuration -
Concurrent job handling (max 10 by default)

------------------------------------------------------------------------

# 📁 Repository Structure

. ├─ backend/ │ ├─ app/ │ ├─ parsers/ │ ├─ storage/ │ ├─ Dockerfile │ └─
requirements.txt │ ├─ frontend/ │ ├─ src/ │ ├─ Dockerfile │ └─
package.json │ ├─ docker-compose.yml ├─ LICENSE └─ README.md

------------------------------------------------------------------------

# 🛠️ Local Development

Backend:

cd backend python -m venv .venv source .venv/bin/activate pip install -r
requirements.txt uvicorn app.main:app --reload --port 8000

Health Check: GET http://localhost:8000/api/health

Frontend:

cd frontend npm install npm run dev

Access UI: http://localhost:5173

------------------------------------------------------------------------

# 🐳 Docker Deployment

docker compose up --build

Access: Frontend → http://localhost:5173\
Backend → http://localhost:8000

------------------------------------------------------------------------

## API

### Create a job

`POST /api/jobs` (multipart/form-data)

Fields:
- `balance_sheet` (file) → `balance_sheet.json`
- `debt_note` (file) → `debt_note.html`
- `lease_note` (file) → `lease_note.html`
- `metadata` (file) → `metadata.json`
- `market_cap_mm` (float) → market cap in **$mm**
- `period_end_text` (optional string) → override period-end text (if you need it)

Response:
```json
{ "job_id": "...", "status": "queued" }
```

### Poll status

`GET /api/jobs/{job_id}`

### Get result

`GET /api/jobs/{job_id}/result`

Returns:
- `html` (string)
- `built` (JSON)

### Download artifacts

- `GET /api/jobs/{job_id}/download/html`
- `GET /api/jobs/{job_id}/download/json`

------------------------------------------------------------------------

# ☁️ Production Deployment

Backend can be deployed on: - Render - Railway - Fly.io - AWS ECS -
Azure Container Apps

Frontend can be deployed on: - Vercel - Netlify

Required Backend Environment Variables:

CORS_ALLOW_ORIGINS=https://`<frontend-domain>`{=html}
MAX_CONCURRENT_JOBS=10 MAX_UPLOAD_BYTES=52428800

Frontend Environment Variable:

VITE_API_BASE=https://`<backend-domain>`{=html}

------------------------------------------------------------------------

# 📈 Market Cap Handling

Current Implementation: Market Cap is entered manually in the UI and
passed to the backend pipeline.

Future Enhancement: Automatic Market Cap fetching via API integration
using: - Polygon.io - Financial Modeling Prep - IEX Cloud - Alpha
Vantage

Proposed Flow: 1. User enters ticker 2. Backend fetches live market cap
3. Converts to \$mm 4. Stores value with timestamp in job artifacts

------------------------------------------------------------------------

# 🔐 Concurrency & Performance

-   Supports up to 10 concurrent jobs
-   Uses subprocess isolation for parser execution
-   Stores per-job artifacts under backend/storage/
-   Designed for stateless horizontal scaling

------------------------------------------------------------------------

# 💼 Real‑World Applications

-   Capital Structure Analytics
-   Deal Evaluation
-   Debt Instrument Classification
-   Enterprise Valuation Automation
-   Financial Data Engineering Projects

------------------------------------------------------------------------
⭐
# 👩🏻‍💻 Author

Komal Wavhal\
M.S. Computer Science (AI/ML)\
Financial AI & Automation Engineer

GitHub: https://github.com/wavhalkomal\
Portfolio: wavhalkomal.github.io

------------------------------------------------------------------------


## License

MIT (see `LICENSE`).
