FROM python:3.12-slim

WORKDIR /app

# Install shared package first
COPY shared/ /app/shared/

# Install agent dependencies
COPY agents/jira-agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy agent code
COPY agents/jira-agent/ /app/

# Create data directory for memory
RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
