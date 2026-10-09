FROM python:3.12-slim

RUN useradd --create-home --uid 1000 appuser
WORKDIR /app

# Optional extra root CAs (certs/*.pem, gitignored) for building and running behind a TLS-intercepting
# proxy: appended to Debian's bundle, which pip, requests (Discogs) and ytmusicapi are all pointed at.
# Empty folder = the stock bundle. Same idea as ytmusic-adapter's and naviseerr-client's Dockerfiles.
COPY certs/ /tmp/certs/
RUN for pem in /tmp/certs/*.pem; do \
      [ -f "$pem" ] || continue; \
      cat "$pem" >> /etc/ssl/certs/ca-certificates.crt; echo >> /etc/ssl/certs/ca-certificates.crt; \
    done
ENV REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    PIP_CERT=/etc/ssl/certs/ca-certificates.crt

COPY pyproject.toml ./
COPY curator ./curator
RUN pip install --no-cache-dir .

# categories.yaml plus the output/, history/ and runs/ folders live under CURATOR_ROOT.
# Mount volumes at /app/output, /app/history and /app/runs to keep editions across restarts
# (not at /app itself: an empty volume there would hide categories.yaml).
COPY categories.yaml ./
RUN mkdir -p output history runs && chown -R appuser /app
ENV CURATOR_ROOT=/app

USER appuser

HEALTHCHECK --interval=10s --timeout=5s --retries=5 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8010/health', timeout=3)" || exit 1

EXPOSE 8010

# One process on purpose: the run queue lives in memory (plus runs/*.json), so a second
# worker would start a second, parallel run and hit YouTube Music rate limits.
CMD ["uvicorn", "curator.service:app", "--host", "0.0.0.0", "--port", "8010"]
