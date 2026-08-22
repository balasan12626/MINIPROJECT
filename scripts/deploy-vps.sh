#!/usr/bin/env bash
# Deploy flood-response stack on VPS with Docker Compose + MongoDB.
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/miniproject}"
REPO_URL="${REPO_URL:-https://github.com/balasan12626/MINIPROJECT.git}"
VPS_IP="${VPS_IP:-209.159.153.35}"

echo "== Disk space =="
df -h /
echo

echo "== Docker =="
if ! command -v docker >/dev/null 2>&1; then
  echo "Installing Docker..."
  curl -fsSL https://get.docker.com | sh
  systemctl enable docker
  systemctl start docker
fi
docker --version
docker compose version || docker-compose --version

echo "== Clone / update repo at ${APP_DIR} =="
if [ -d "${APP_DIR}/.git" ]; then
  git -C "${APP_DIR}" pull --ff-only
else
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone "${REPO_URL}" "${APP_DIR}"
fi
cd "${APP_DIR}"

echo "== Create .env (never committed to git) =="
if [ ! -f .env ]; then
  cp .env.example .env
fi
# Docker internal MongoDB service name is "mongo"
grep -q '^MONGODB_URI=' .env && sed -i 's|^MONGODB_URI=.*|MONGODB_URI=mongodb://mongo:27017|' .env || echo 'MONGODB_URI=mongodb://mongo:27017' >> .env
grep -q '^DATABASE_NAME=' .env || echo 'DATABASE_NAME=flood_response' >> .env
grep -q '^CORS_ORIGINS=' .env && sed -i "s|^CORS_ORIGINS=.*|CORS_ORIGINS=http://${VPS_IP}:5173,http://127.0.0.1:5173|" .env || echo "CORS_ORIGINS=http://${VPS_IP}:5173,http://127.0.0.1:5173" >> .env

echo "== Build and start containers =="
docker compose down 2>/dev/null || true
docker compose up --build -d

echo "== Wait for backend health =="
for i in $(seq 1 30); do
  if curl -sf "http://127.0.0.1:8000/api/health" >/dev/null; then
    curl -s "http://127.0.0.1:8000/api/health"
    echo
    break
  fi
  sleep 3
done

echo
echo "Done. Open: http://${VPS_IP}:5173/"
echo "MongoDB (Docker): mongodb://mongo:27017  database: flood_response"
echo "Collections/indexes are created automatically on backend startup."
