# Build context must be repo root: docker build -f services/auth-service/Dockerfile .
ARG BASE_IMAGE=banking/base:latest
FROM ${BASE_IMAGE}

# Service-specific deps (may be empty)
COPY services/auth-service/requirements.txt ./requirements.txt
RUN if [ -s requirements.txt ]; then pip install --no-cache-dir -r requirements.txt; fi

# Shared library — reachable because context = repo root
COPY shared/ /app/shared/

# Service source
COPY services/auth-service/ .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
