# Build from the repo root: docker compose build api
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1

COPY services/api/requirements.lock ./requirements.lock
RUN pip install --no-cache-dir -r requirements.lock

COPY services/api/ ./

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
