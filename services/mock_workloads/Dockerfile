FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn
COPY services/mock_workloads/ ./services/mock_workloads/
COPY services/__init__.py ./services/
ENV SERVICE_NAME=jira
ENV PORT=8081
CMD python -c "import uvicorn, os; from services.mock_workloads.apps import create_mock_service; name = os.environ.get('SERVICE_NAME', 'jira'); port = int(os.environ.get('PORT', 8081)); uvicorn.run(create_mock_service(name, port), host='0.0.0.0', port=port)"
