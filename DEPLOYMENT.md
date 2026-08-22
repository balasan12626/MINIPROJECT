# Deployment

## Local

1. Install Python 3.11+ and Node 20+.
2. Run MongoDB 7 (`docker run -p 27017:27017 mongo:7` is enough).
3. `pip install -r backend/requirements.txt`
4. `python scripts/train_flood_model.py` if `models/*.pkl` are missing.
5. `PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000`
6. `cd frontend && npm install && npm run dev`

## Docker Compose

`docker compose up --build` starts MongoDB, API on `:8000`, and nginx-served UI on `:5173` proxying `/api` and `/ws`.

Secrets stay in `.env` (gitignored). `.env.example` is the template.

## Security implemented

- CORS from `CORS_ORIGINS`
- Pydantic request validation
- SlowAPI limiter attached (extend per-route as needed)
- JWT login for operators
- Review/SOS audit logs in Mongo
- No API keys shipped to the React bundle (browser talks only to this backend)

Rate-limit and RBAC are intentionally small: operator role is required conceptually for review; token decode is used when `Authorization: Bearer` is sent.
