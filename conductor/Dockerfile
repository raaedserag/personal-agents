FROM python:3.12-slim

WORKDIR /app

# Install shared package
COPY shared/ /app/shared/

# Install conductor dependencies
COPY conductor/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy conductor code
COPY conductor/ /app/conductor/

# Copy profiles
COPY profiles/ /app/profiles/

WORKDIR /app/conductor

EXPOSE 10000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "10000"]
