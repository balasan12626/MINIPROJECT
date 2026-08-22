#!/usr/bin/env bash
# Fix "DATA UNAVAILABLE" / 502 when frontend works but backend is down.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/miniproject}"
cd "${APP_DIR}"

echo "== Disk / memory =="
df -h /
free -h || true
echo

echo "== Open firewall (backend 8000 + frontend 5173) =="
if command -v ufw >/dev/null 2>&1; then
  ufw allow 22/tcp || true
  ufw allow 5173/tcp || true
  ufw allow 8000/tcp || true
  ufw --force enable || true
  ufw status || true
fi
echo

echo "== Ensure .env =="
if [ ! -f .env ]; then
  cp .env.example .env
fi
grep -q '^MONGODB_URI=' .env && sed -i 's|^MONGODB_URI=.*|MONGODB_URI=mongodb://mongo:27017|' .env || echo 'MONGODB_URI=mongodb://mongo:27017' >> .env
grep -q '^DATABASE_NAME=' .env || echo 'DATABASE_NAME=flood_response' >> .env
grep -q '^CORS_ORIGINS=' .env && sed -i 's|^CORS_ORIGINS=.*|CORS_ORIGINS=http://209.159.153.35:5173,http://127.0.0.1:5173|' .env || echo 'CORS_ORIGINS=http://209.159.153.35:5173,http://127.0.0.1:5173' >> .env
echo

echo "== Rebuild stack =="
docker compose down || true
docker compose up --build -d

echo "== Wait for backend (up to 3 min) =="
for i in $(seq 1 36); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null 2>&1; then
    echo "Backend OK:"
    curl -s "http://127.0.0.1:8000/api/health"
    echo
    break
  fi
  echo "waiting... ($i/36)"
  sleep 5
done

echo
echo "== Container status =="
docker compose ps

echo
echo "== Test via frontend proxy =="
curl -sf "http://127.0.0.1:5173/api/health" && echo || echo "Frontend proxy still failing — see backend logs below"

echo
echo "== Backend logs (last 40 lines) =="
docker compose logs backend --tail 40

echo
echo "Open: http://209.159.153.35:5173/"
