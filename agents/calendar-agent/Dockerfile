FROM python:3.12-slim

WORKDIR /app

COPY shared/ /app/shared/

COPY agents/calendar-agent/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY agents/calendar-agent/ /app/

RUN mkdir -p /app/data

EXPOSE 8000

CMD ["uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
