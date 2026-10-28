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


## Citizen SOS page (`/sos`) needs HTTPS

Browsers only allow `navigator.geolocation` (and the phone camera) on **HTTPS** pages or on `localhost`.
On the VPS over plain `http://IP:5173` the *Share my location* button fails, and the citizen has to place the pin by hand.

For a real phone demo put nginx + Let's Encrypt in front of both ports:

1. Point a domain at the VPS (an IP address cannot get a Let's Encrypt certificate).
2. `apt install nginx certbot python3-certbot-nginx`, then `certbot --nginx -d your.domain`.
3. Proxy `https://your.domain/` → `http://127.0.0.1:5173` and `https://your.domain/api/` → `http://127.0.0.1:8000/api/`
   (keep `/ws` upgraded for the websocket), and add `https://your.domain` to `CORS_ORIGINS`.

Citizen photos are written to `uploads/sos/{run_id}/` (git-ignored). They are re-encoded on upload, which strips EXIF
(including the phone's GPS and model tags). They are personal data: delete them when a demo is finished.

## Security implemented

- CORS from `CORS_ORIGINS`
- Pydantic request validation
- SlowAPI limiter attached (extend per-route as needed); the public `POST /api/public/sos` is limited to 5/minute and
  10 per device per run, checks the photo's magic bytes (JPEG/PNG/WebP, ≤ 3 MB) and only accepts locations inside the
  simulated road network
- JWT login for operators
- Review/SOS audit logs in Mongo
- No API keys shipped to the React bundle (browser talks only to this backend)

Rate-limit and RBAC are intentionally small: operator role is required conceptually for review; token decode is used when `Authorization: Bearer` is sent.
