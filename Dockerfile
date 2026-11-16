# Single deployable container: FastAPI serves the API and the built React frontend.
# Mount a persistent volume at /data (SQLite + artifacts). Without one, data is lost on restart.
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npx vite build

FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/snapshots ./snapshots
COPY --from=web /web/dist ./frontend_dist
ENV EARTHINSPECT_DATA_DIR=/data \
    EARTHINSPECT_FRONTEND_DIST=/app/frontend_dist
VOLUME ["/data"]
EXPOSE 8000
# Hosts such as Render inject $PORT; default to 8000 locally.
CMD ["sh", "-c", "python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
