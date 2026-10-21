"""Gunicorn is reachable only through local Nginx."""
bind = "127.0.0.1:8001"
workers = 2
worker_class = "gthread"
threads = 2
timeout = 60
graceful_timeout = 30
accesslog = "-"
errorlog = "-"
capture_output = True
forwarded_allow_ips = "127.0.0.1"
# systemd owns process management; do not write a separate control socket in HOME.
control_socket_disable = True
