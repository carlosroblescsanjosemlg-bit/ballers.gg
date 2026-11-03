# Compilar Angular una vez. Node no forma parte del servidor final.
FROM node:24-bookworm-slim AS frontend-build
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SESSION_COOKIE_SECURE=1
WORKDIR /app
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY backend/app/ ./backend/app/
COPY backend/bd/ ./backend/bd/
COPY Main.py ./Main.py
COPY --from=frontend-build /build/frontend/dist/arena/browser/ ./frontend/dist/arena/browser/
RUN useradd --create-home --uid 10001 ballers
USER ballers
EXPOSE 10000
CMD ["python", "Main.py", "--production"]
