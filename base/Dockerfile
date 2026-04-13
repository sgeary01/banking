FROM python:3.12-slim

WORKDIR /app

# System deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install all shared Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# This image is used as a base — individual services add their own files on top
