FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONUTF8=1
COPY requirements.txt .
RUN python -m pip install --no-cache-dir -r requirements.txt
COPY . .
ARG APP_VERSION=1.1.1
ARG APP_COMMIT=local
ARG DEMO_FAULT=0
LABEL org.opencontainers.image.title="Cap Avenir" \
      org.opencontainers.image.version=$APP_VERSION \
      org.opencontainers.image.revision=$APP_COMMIT \
      com.cap-avenir.demo-fault=$DEMO_FAULT
ENV CAP_AVENIR_VERSION=$APP_VERSION CAP_AVENIR_COMMIT=$APP_COMMIT \
    CAP_AVENIR_DEMO_FAULT=$DEMO_FAULT CAP_AVENIR_RUNTIME_DIR=/app/runtime
RUN mkdir -p /app/data /app/runtime
EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --start-period=10s --retries=6 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=2)"
CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
