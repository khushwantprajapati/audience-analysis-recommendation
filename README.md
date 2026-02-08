# ROAS Audience Recommendation Engine

Semi-automated audience-level decision engine for Meta Ads with ROAS as the primary metric. The system turns performance data into clear recommendations: **Scale**, **Hold**, **Pause**, or **Retest**, with explanations and guardrails. No execution layer—recommendations are shown on a dashboard for human review.

## Architecture

- **Backend**: Python 3.12 + FastAPI (Meta API client, ingestion, metrics, rule engine, Claude analysis)
- **Frontend**: Next.js 14 (App Router) + Tailwind CSS
- **Database**: SQLite (default), configurable via `DATABASE_URL`
- **Meta**: OAuth 2.0 + Marketing API (ad sets, insights)
- **AI**: Anthropic Claude for validation and plain-English explanations

## Quick start

### 1. Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate   # Windows
# source .venv/bin/activate  # macOS/Linux
pip install -r requirements.txt
cp .env.example .env
# Edit .env: set META_APP_ID, META_APP_SECRET, META_REDIRECT_URI, ANTHROPIC_API_KEY (optional)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
cp .env.local.example .env.local
# Set NEXT_PUBLIC_API_URL=http://localhost:8000 if needed
npm run dev
```

Open [http://localhost:3000](http://localhost:3000), click **Connect Meta Account**, complete OAuth, then use the dashboard to sync data and generate recommendations.

### 3. Meta App setup

1. Create an app at [developers.facebook.com](https://developers.facebook.com).
2. Add **Facebook Login** and **Marketing API**.
3. Set valid OAuth redirect URI: `http://localhost:8000/api/auth/meta/callback` (or your backend URL).
4. Use App ID and App Secret in backend `.env`.

## Project layout

```
roas/
├── backend/
│   ├── app/
│   │   ├── main.py           # FastAPI app, CORS, lifespan, scheduler
│   │   ├── config.py         # Thresholds and env
│   │   ├── database.py       # SQLAlchemy engine and session
│   │   ├── models/          # Account, Audience, MetricSnapshot, Recommendation, ActionLog
│   │   ├── api/              # auth, accounts, audiences, recommendations, settings, ingestion
│   │   ├── services/         # meta_client, ingestion, metrics, rules, claude_analyzer, scheduler
│   │   └── schemas/          # Pydantic request/response
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── app/              # page (landing), dashboard, audience/[id], settings, history
│       ├── components/       # nav, recommendation-badge
│       └── lib/              # api, types
├── audience_recommendation_engine_meta_ads.md  # Full spec
└── README.md
```

## Features

- **Connect Meta account** via OAuth from the dashboard
- **Sync ad sets** and store 1d / 3d / 7d insights (spend, revenue, purchases, ROAS, CPA, CVR)
- **Rule engine**: performance buckets (Winner / Average / Loser), trend states (Stable / Improving / Declining / Volatile), decision matrix, audience-type modifiers, guardrails (max scale %, cooldown, no pause below min spend)
- **Claude analysis**: validate rule decision, 2–3 bullet reasons, risk flags, confidence (HIGH / MEDIUM / LOW)
- **Recommendations** listed on dashboard with filters; audience detail page with history
- **Settings** page shows current thresholds (from backend config)
- **History** page lists past recommendations by date
- **Scheduler**: sync all accounts every 6 hours; outcome logging (3d / 7d metrics) every 12 hours for feedback

## Configuration

Backend `.env` (see `.env.example`):

- `META_APP_ID`, `META_APP_SECRET`, `META_REDIRECT_URI` — Meta OAuth
- `ANTHROPIC_API_KEY` — optional; without it, recommendations use rule engine only with placeholder reasons
- `SECRET_KEY` — used for token encryption and Fernet
- `FRONTEND_URL` — for OAuth redirect after login (e.g. `http://localhost:3000`)
- `DATABASE_URL` — default `sqlite:///./roas.db`

Thresholds (noise, performance buckets, trend, scoring weights, guardrails) are in `app/config.py` and can be overridden via env or a future settings store.

## License

Use as needed for your project.
