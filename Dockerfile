# ----------- FRONTEND BUILD STAGE -----------
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build


# ----------- BACKEND STAGE -----------
FROM python:3.11-slim

WORKDIR /app

# Install required system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libxml2-dev \
    libxslt1-dev \
  && rm -rf /var/lib/apt/lists/*

# Copy backend code
COPY backend/ /app/backend/

# Install Python deps
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy built frontend into container
COPY --from=frontend-build /app/frontend/dist /app/frontend/dist

WORKDIR /app/backend

# IMPORTANT: Railway injects PORT
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]