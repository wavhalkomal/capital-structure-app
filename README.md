# Capital Structure Extraction Web App

This repo productizes the **Capital Structure Extraction Challenge** pipeline into a deployable web application.

- **Backend:** Python + FastAPI
- **Frontend:** React (Vite)
- **Pipeline:** Uses the existing parsers/renderers in `backend/parsers/` to produce an HTML table matching the train set style.

## What the app does

1. Upload **balance_sheet.json**, **debt_note.html**, **lease_note.html**, and **metadata.json**
2. Provide **Market Cap ($mm)** (required)
3. Backend runs:
   - `capital_structure_builder.py` → `built_capital_structure.json`
   - `html_renderer.py` → final `generated.html`
4. Frontend polls job status and shows an **iframe preview** of the rendered HTML.

The backend supports **up to 10 concurrent jobs** by design.

---

## Repo layout

```
.
├─ backend/
│  ├─ app/                 # FastAPI app + job manager
│  ├─ parsers/             # your existing scripts (copied here)
│  ├─ storage/             # per-job inputs/outputs (runtime)
│  ├─ Dockerfile
│  └─ requirements.txt
├─ frontend/
│  ├─ src/                 # React UI
│  └─ Dockerfile
├─ docker-compose.yml
├─ LICENSE
└─ README.md
```

---

## Local dev (recommended)

### 1) Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# optional
cp .env.example .env

uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Backend health check:

- `GET http://localhost:8000/api/health`

### 2) Frontend

```bash
cd frontend
npm install
cp .env.example .env
npm run dev
```

Open:

- `http://localhost:5173`

---

## Run with Docker Compose

```bash
docker compose up --build
```

- Frontend: `http://localhost:5173`
- Backend: `http://localhost:8000`

---

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

---

## Deployment

### Backend (Railway / Fly.io / Render)

- Deploy `backend/` as a Docker service.
- Set env vars:
  - `CORS_ALLOW_ORIGINS=<your-frontend-origin>`
  - `MAX_CONCURRENT_JOBS=10`
  - `MAX_UPLOAD_BYTES=52428800` (or higher if needed)

### Frontend (Vercel)

- Deploy `frontend/`.
- Set build-time env var:
  - `VITE_API_BASE=<your-backend-url>`

---

## Notes

- All output amounts are expected to be in **$mm**.
- The backend runs your existing scripts via subprocess to avoid assumptions about internal function names.
- You can extend this app with:
  - **Market cap lookup** (ticker → API)
  - **Citations** (link values to source ranges)
  - **Self-assessment** (diff output vs expected patterns)

---

## License

MIT (see `LICENSE`).
