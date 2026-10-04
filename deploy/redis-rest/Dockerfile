FROM python:3.12-slim
RUN pip install --no-cache-dir "redis>=5" "starlette>=0.37" "uvicorn>=0.30"
COPY app.py /app/app.py
WORKDIR /app
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "2", "--no-access-log"]
