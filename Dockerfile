# Tejido container image — multi-stage build.
#
# Stage 1 builds the React frontend in a node image (avoids dragging
# node into the runtime). Stage 2 is a slim Python image with ffmpeg
# and the build tools pywhispercpp needs to compile its C++ extension.
#
# Designed for Railway, Fly, or any container PaaS. The runtime expects
# a writable persistent volume mounted at /data — see the README's
# "Deploy to Railway" section. Without that volume everything still
# starts up but every redeploy wipes admin edits + transcripts.

# ---------------------------------------------------------------------------
# Stage 1: build the frontend bundle.
FROM node:20-slim AS web-builder
WORKDIR /web

# Cache npm install separately from the source.
COPY web/package.json web/package-lock.json ./
RUN npm ci

COPY web/ ./
RUN npm run build

# ---------------------------------------------------------------------------
# Stage 2: Python runtime with ffmpeg.
FROM python:3.12-slim

# pywhispercpp compiles a C++ extension at install time → needs build
# tools + cmake. ffmpeg is a runtime dep for converting WebM/Opus voice
# notes to the 16 kHz mono WAV whisper.cpp wants.
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        build-essential \
        cmake \
        git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps first so the layer caches when only app code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code + bundled config defaults (used as the seed for the volume
# on first boot — see config._seed_volume_from_repo_defaults).
COPY src/ ./src/
COPY config/ ./config/

# Built React bundle from stage 1.
COPY --from=web-builder /web/dist ./web/dist

# Runtime configuration:
# - PYTHONPATH so `python -m circle.run` finds the package.
# - HOST=0.0.0.0 so the container accepts traffic from the PaaS proxy.
#   ($PORT is provided by Railway/Fly/etc; circle.run honors it.)
# - TEJIDO_DATA_ROOT points at the mounted volume, so all admin
#   edits and participant transcripts persist across redeploys.
ENV PYTHONPATH=/app/src \
    HOST=0.0.0.0 \
    TEJIDO_DATA_ROOT=/data

# Hint for `docker run` / Railway port detection. Real port comes from $PORT.
EXPOSE 8000

CMD ["python", "-m", "circle.run"]
