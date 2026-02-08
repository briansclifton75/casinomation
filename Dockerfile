FROM python:3.11-slim

WORKDIR /app

COPY . /app

ENV PYTHONUNBUFFERED=1 \
    CASINOMATION_DB=/data/casinomation.db \
    CASINOMATION_SCHEDULER_ENABLED=true \
    CASINOMATION_DAILY_RUN_AT=09:00

EXPOSE 8000

VOLUME ["/data"]

CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "8000"]
