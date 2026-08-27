FROM python:3.11-slim

WORKDIR /code
# So `docker compose exec api python scripts/whatever.py` can import the app
# package without needing PYTHONPATH set by hand every time — running a
# script directly only puts the script's own directory on sys.path, not /code.
ENV PYTHONPATH=/code

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
