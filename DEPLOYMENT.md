# Deployment

## Local

1. Install Python 3.11+ and Node 20+.
2. Run MongoDB 7 (`docker run -p 27017:27017 mongo:7` is enough).
3. `pip install -r backend/requirements.txt`
4. `python scripts/train_flood_model.py` if `models/*.pkl` are missing.
5. `PYTHONPATH=. uvicorn backend.main:app --host 0.0.0.0 --port 8000`
6. `cd frontend && npm install && npm run dev`

## VPS (209.159.153.35 or your server IP)

1. SSH in: `ssh root@YOUR_VPS_IP`
2. Ensure port **22**, **5173**, and **8000** are open in the VPS firewall / provider panel.
3. Run the deploy script (installs Docker if missing, clones repo to `/opt/miniproject`, creates `.env`, starts stack):

```bash
curl -fsSL https://raw.githubusercontent.com/balasan12626/MINIPROJECT/main/scripts/deploy-vps.sh | bash
```

Or manually:

```bash
git clone https://github.com/balasan12626/MINIPROJECT.git /opt/miniproject
cd /opt/miniproject
cp .env.example .env
# Edit .env: set GEMINI_API_KEY etc. Never commit .env.
sed -i 's|MONGODB_URI=.*|MONGODB_URI=mongodb://mongo:27017|' .env
docker compose up --build -d
```

MongoDB database `flood_response` and collections/indexes are created automatically when the backend starts (`mongo.ensure_indexes` + `seed_if_empty`).

App URLs after deploy:
- UI: `http://YOUR_VPS_IP:5173/`
- API health: `http://YOUR_VPS_IP:8000/api/health`


## Security implemented

- CORS from `CORS_ORIGINS`
- Pydantic request validation
- SlowAPI limiter attached (extend per-route as needed)
- JWT login for operators
- Review/SOS audit logs in Mongo
- No API keys shipped to the React bundle (browser talks only to this backend)

Rate-limit and RBAC are intentionally small: operator role is required conceptually for review; token decode is used when `Authorization: Bearer` is sent.
