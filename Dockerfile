# ---- Build stage: build dlib and dependency wheels ----
FROM python:3.9-bullseye AS build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake libopenblas-dev liblapack-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# Upgrade pip and build wheels
RUN python -m pip install --upgrade pip

# Build dlib wheel (may take a few minutes)
RUN pip wheel --wheel-dir /wheels dlib==19.24.6

# Build remaining dependency wheels, ignoring the local Windows-only dlib-bin line
RUN grep -v 'dlib-bin' requirements.txt > /tmp/requirements.filtered.txt && \
    pip wheel --wheel-dir /wheels -r /tmp/requirements.filtered.txt


# ---- Runtime stage ----
FROM python:3.9-slim-bullseye

# Runtime libs needed for numpy/dlib/opencv
RUN apt-get update && apt-get install -y --no-install-recommends \
    libopenblas0 liblapack3 libgomp1 \
    libgl1 libglib2.0-0 libsm6 libxext6 libxrender1 && \
    rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Copy app source and prebuilt wheels
COPY . /app
COPY --from=build /wheels /wheels

# Web server and dependencies from wheels (skip dlib-bin)
RUN pip install --no-cache-dir gunicorn && \
    pip install --no-index --find-links=/wheels dlib==19.24.6 && \
    grep -v 'dlib-bin' requirements.txt > /tmp/requirements.filtered.txt && \
    pip install --no-index --find-links=/wheels -r /tmp/requirements.filtered.txt

# Ensure writable folders exist (mapped to persistent storage at runtime if desired)
RUN mkdir -p /app/static/attendance /app/static/employees

# Container port (Render will inject $PORT)
ENV PORT=8080
EXPOSE 8080

# Single worker because the app uses background threads/scheduler
# Bind to $PORT if provided by the platform, default to 8080 for local runs
CMD ["sh", "-c", "gunicorn --workers 1 --timeout 120 -b 0.0.0.0:${PORT:-8080} app:app"]
