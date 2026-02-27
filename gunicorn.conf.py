"""
Gunicorn configuration for production deployment.

Usage: gunicorn -c gunicorn.conf.py app.main:app
"""
import multiprocessing
import os

# Bind
bind = os.environ.get("GUNICORN_BIND", "127.0.0.1:8000")

# Workers: 2 * CPU + 1 is a good default; cap at 4 for a personal tool
workers = min(multiprocessing.cpu_count() * 2 + 1, 4)
worker_class = "uvicorn.workers.UvicornWorker"

# Timeouts
timeout = 120          # kill worker if request takes >120s
graceful_timeout = 30  # wait 30s for in-flight requests on restart
keepalive = 5

# Logging
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.environ.get("LOG_LEVEL", "info")

# Worker recycling — prevent memory leaks from long-lived workers
max_requests = 1000
max_requests_jitter = 100

# Security
limit_request_line = 8190
limit_request_fields = 100
limit_request_field_size = 8190

# Disable scheduler in web workers — run it as a separate service
raw_env = [
    "RUN_SCHEDULER=false",
]
