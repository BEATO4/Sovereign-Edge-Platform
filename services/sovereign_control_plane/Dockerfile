FROM python:3.12-slim
WORKDIR /app
COPY services/sovereign_control_plane/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY services/sovereign_control_plane/ ./services/sovereign_control_plane/
COPY services/__init__.py ./services/
EXPOSE 8080
CMD ["uvicorn", "services.sovereign_control_plane.main:app", "--host", "0.0.0.0", "--port", "8080"]
