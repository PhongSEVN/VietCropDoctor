FROM nginx:1.27-alpine

# python3 for the health-aggregator sidecar (pure stdlib, ~15 MB extra)
RUN apk add --no-cache python3

# ── Nginx configuration ───────────────────────────────────────────────────────
COPY nginx.conf          /etc/nginx/nginx.conf
COPY conf.d/             /etc/nginx/conf.d/

# ── Health aggregator sidecar ─────────────────────────────────────────────────
COPY health_aggregator.py  /usr/local/bin/health_aggregator.py
COPY docker-entrypoint.sh  /docker-entrypoint.sh
RUN  chmod +x /docker-entrypoint.sh

EXPOSE 80

HEALTHCHECK --interval=10s --timeout=5s --retries=3 \
    CMD wget -qO- http://127.0.0.1/health || exit 1

ENTRYPOINT ["/docker-entrypoint.sh"]
