FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY generate.py .

ENV INTERVAL=600

CMD ["sh", "-c", "while true; do python generate.py; sleep $INTERVAL; done"]
