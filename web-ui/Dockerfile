FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn jinja2 pyjwt cryptography httpx
COPY . /app
EXPOSE 3000
CMD ["uvicorn", "web-ui.dashboard_server:app", "--host", "0.0.0.0", "--port", "3000"]
