FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

# CSV data goes into /data volume shared with recreator
ENV CSV_DIR=/data

EXPOSE 8000

# -u for unbuffered output so logs appear in docker logs
CMD ["python", "-u", "app.py"]
