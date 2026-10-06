# Slim Debian base: small, but still glibc, so every dependency installs from prebuilt wheels
FROM python:3.12-slim

# No .pyc files on disk; logs go straight to stdout (and from there to CloudWatch)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Dependencies first: this layer is rebuilt only when requirements.txt changes,
# so code-only changes rebuild in seconds
COPY requirements.txt .
RUN pip install -r requirements.txt

# Code is owned by root and only readable by the app user: a compromised
# process cannot rewrite its own code
COPY . .

RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

# Exec form: uvicorn runs as PID 1 and receives SIGTERM directly when ECS
# stops the task, so in-flight requests can finish
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
