"""Caddy is the only peer; override with its exact address if not loopback."""

import os

bind = "0.0.0.0:8000"
workers = int(os.environ.get("WEB_CONCURRENCY", min(2 * (os.cpu_count() or 1) + 1, 8)))
timeout = 30
graceful_timeout = 30
max_requests = 1000
max_requests_jitter = 100
accesslog = "-"
# Only normalized paths; never log raw requests or query strings.
logger_class = "apps.core.access_log.PrivateOrderLogger"
access_log_format = "%(h)s %(m)s %(U)s %(s)s %(b)s %(D)s"
forwarded_allow_ips = os.environ.get("FORWARDED_ALLOW_IPS", "127.0.0.1,::1")
if "*" in forwarded_allow_ips.split(","):
    raise ValueError("FORWARDED_ALLOW_IPS must list explicit proxy addresses")
