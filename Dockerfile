# GaugeBench Studio, ready for any container host (Render, Railway, Fly.io, Cloud Run, ...).
#
# The Gemini API key is NOT part of the image. Give it to the running container as an
# environment variable / secret (GEMINI_API_KEY) in your host's dashboard. It is only
# ever read by the server; the browser never sees it.
#
#   docker build -t gaugebench .
#   docker run -p 8765:8765 -e GEMINI_API_KEY=... gaugebench
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    GAUGEBENCH_PUBLIC=1 \
    PORT=8765

# DejaVu: the font the gauge renderer prints its scale numbers with on Linux
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY gaugebench ./gaugebench
COPY runs ./runs

# Large suites live outside git, as GitHub release assets, and are baked into the image at
# build time (ADD re-checks the URL on every build, so a re-uploaded zip is picked up).
# Point SUITE_ZIP / ROUNDS_ZIP at other zips to change what the Archive shows.
ARG SUITE_ZIP=https://github.com/SoumyadeepRoyKarmakar/gaugebench/releases/download/data/v2.zip
ARG ROUNDS_ZIP=https://github.com/SoumyadeepRoyKarmakar/gaugebench/releases/download/data/rounds.zip
ADD ${SUITE_ZIP} /tmp/suites/v2.zip
ADD ${ROUNDS_ZIP} /tmp/suites/rounds.zip
RUN python -m gaugebench fetch-suite /tmp/suites/v2.zip /tmp/suites/rounds.zip --dest runs && rm -r /tmp/suites

# run as an unprivileged user
RUN useradd --create-home --uid 10001 studio && chown -R studio /app
USER studio

EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import os,urllib.request; urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8765\")}/healthz', timeout=4)"

# --public: per-visitor and daily limits on Gemini, no developer error details, binds 0.0.0.0:$PORT
CMD ["python", "-m", "gaugebench", "app", "--public", "--suites", "runs"]
