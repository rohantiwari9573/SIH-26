FROM python:3.11-slim

WORKDIR /srv

RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.30.6 cryptography==43.0.1

COPY generate_cert.py app.py ./
RUN python generate_cert.py

EXPOSE 443

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "443", \
     "--ssl-certfile", "cert.pem", "--ssl-keyfile", "key.pem", "--no-server-header"]
