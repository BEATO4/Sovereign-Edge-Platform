FROM python:3.12-slim
WORKDIR /app
COPY services/service_broker/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/service_broker/ ./services/service_broker/
COPY services/__init__.py ./services/
EXPOSE 8000
CMD ["uvicorn", "services.service_broker.main:app", "--host", "0.0.0.0", "--port", "8000"]
