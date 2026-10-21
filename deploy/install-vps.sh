#!/usr/bin/env bash
# Target: student@192.168.2.213, existing HTTPS ingress sv23.bcse-vju.com -> port 80.
set -euo pipefail
project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
if [[ "$(id -un)" != "student" || "$project_dir" != "/home/student/qlychtsv" ]]; then
    printf '%s\n' 'Run as student from /home/student/qlychtsv; deployment paths are explicit.' >&2
    exit 1
fi
cd "$project_dir"
python3 -m venv .venv
.venv/bin/python -m pip install --disable-pip-version-check -r requirements-server.txt
install -d -m 700 instance
.venv/bin/python -m flask --app 'app:create_app()' init-db --demo
chmod 600 instance/secret.key

backup_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
for config in /etc/systemd/system/qlychtsv.service /etc/nginx/sites-available/qlychtsv; do
    if sudo test -e "$config"; then
        sudo cp -a -- "$config" "$config.bak.$backup_stamp"
    fi
done
if ! sudo test -e /etc/qlychtsv.env; then
    sudo install -m 640 -o root -g student deploy/qlychtsv.env /etc/qlychtsv.env
fi
sudo install -m 644 deploy/qlychtsv.service /etc/systemd/system/qlychtsv.service
sudo install -m 644 deploy/nginx.conf /etc/nginx/sites-available/qlychtsv
sudo ln -sfn /etc/nginx/sites-available/qlychtsv /etc/nginx/sites-enabled/qlychtsv
sudo nginx -t
sudo systemctl daemon-reload
sudo systemctl enable qlychtsv
sudo systemctl restart qlychtsv
sudo systemctl reload nginx
for attempt in {1..20}; do
    if curl --fail --silent -H 'Host: sv23.bcse-vju.com' http://127.0.0.1/ >/dev/null; then
        printf '%s\n' 'Application is ready at https://sv23.bcse-vju.com'
        exit 0
    fi
    sleep 1
done
sudo journalctl -u qlychtsv -n 30 --no-pager
exit 1
