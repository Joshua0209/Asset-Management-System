# Dev image for the FastAPI backend.
#
# Compose bind-mounts ./backend over /app, so source edits flow through
# uvicorn --reload without a rebuild. The image still installs the project
# in editable mode at build time so site-packages metadata exists; the bind
# mount at runtime supplies the actual source tree.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# curl is used by the compose healthcheck against /health.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first so the layer caches across source edits.
# pyproject.toml + the package source are both needed for the editable install
# (setuptools requires the discoverable package to exist at install time).
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir -e '.[dev]'

# Drop root before runtime. The uploads dir is pre-created so the named
# volume initialises with app-owned permissions on first mount.
RUN useradd --create-home --uid 1000 app \
    && mkdir -p /app/uploads \
    && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
