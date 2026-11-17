"""Install project-owned MySQL, API and HTTP(S) user services without sudo.

Run on the board after extracting verified Ubuntu packages to runtime/ and
installing the offline Python wheels into .venv/. All mutable state and secrets
stay under shared/; app releases can be switched independently.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import time


def secret_file(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.chmod(path, 0o600)
    with os.fdopen(descriptor, "w") as stream:
        stream.write(content)


def mysql_args(root: Path) -> list[str]:
    return [str(root / "runtime/usr/sbin/mysqld"), "--no-defaults",
            f"--basedir={root}/runtime/usr", f"--datadir={root}/shared/mysql",
            f"--lc-messages-dir={root}/runtime/usr/share/mysql",
            f"--secure-file-priv={root}/shared/mysql-files",
            f"--socket={root}/shared/mysql.sock", f"--pid-file={root}/shared/mysql.pid",
            f"--log-error={root}/shared/mysql-error.log", "--mysqlx=0",
            "--skip-log-bin", "--max-connections=30", "--innodb-buffer-pool-size=128M",
            "--default-time-zone=+00:00"]


def ensure_database(root: Path, credentials: dict[str, str]) -> None:
    import pymysql
    data = root / "shared/mysql"
    data.mkdir(exist_ok=True)
    (root / "shared/mysql-files").mkdir(exist_ok=True, mode=0o700)
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = str(root / "runtime/usr/lib/aarch64-linux-gnu")
    fresh = not (data / "mysql").exists()
    initialized = root / "shared/mysql-bootstrap-complete"
    if fresh:
        subprocess.run(mysql_args(root) + ["--initialize-insecure"], check=True, env=env)
    # An existing managed instance must be stopped before the private socket
    # bootstrap. No system MySQL service is changed.
    subprocess.run(["systemctl", "--user", "stop", "dnb26-api", "dnb26-mysql"], check=False)
    log = (root / "shared/mysql-bootstrap.log").open("ab")
    process = subprocess.Popen(mysql_args(root) + ["--skip-networking"], env=env, stdout=log, stderr=log)
    connection = None
    try:
        for _ in range(90):
            if process.poll() is not None:
                raise RuntimeError("MySQL bootstrap exited; inspect shared/mysql-error.log")
            try:
                try:
                    connection = pymysql.connect(unix_socket=str(root / "shared/mysql.sock"),
                        user="root", password=credentials["root_password"])
                except pymysql.err.OperationalError as exc:
                    # Recover only an interrupted initial bootstrap. The server
                    # has no TCP listener, and existing managed credentials are
                    # never replaced after the completion marker is written.
                    if exc.args[0] != 1045 or initialized.exists():
                        raise
                    connection = pymysql.connect(unix_socket=str(root / "shared/mysql.sock"),
                        user="root", password="")
                break
            except pymysql.err.OperationalError:
                time.sleep(1)
        if connection is None:
            raise RuntimeError("Timed out waiting for private MySQL bootstrap socket")
        with connection.cursor() as cursor:
            cursor.execute("ALTER USER 'root'@'localhost' IDENTIFIED BY %s", (credentials["root_password"],))
            cursor.execute("CREATE DATABASE IF NOT EXISTS smarthome_db CHARACTER SET utf8mb4")
            for host in ("localhost", "127.0.0.1"):
                cursor.execute("CREATE USER IF NOT EXISTS 'dnb26'@%s IDENTIFIED BY %s", (host, credentials["database_password"]))
                cursor.execute("ALTER USER 'dnb26'@%s IDENTIFIED BY %s", (host, credentials["database_password"]))
                cursor.execute("GRANT ALL PRIVILEGES ON smarthome_db.* TO 'dnb26'@%s", (host,))
            cursor.execute("SHUTDOWN")
        process.wait(timeout=30)
        initialized.touch(mode=0o600)
    finally:
        if connection:
            connection.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=30)
        log.close()


def create_configs(root: Path, ip: str, credentials: dict[str, str]) -> None:
    shared = root / "shared"
    tls = shared / "tls"
    tls.mkdir(exist_ok=True)
    cert, key = tls / "server.crt", tls / "server.key"
    if not cert.exists():
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "365",
            "-keyout", str(key), "-out", str(cert), "-subj", "/CN=dnb26.local",
            "-addext", f"subjectAltName=DNS:dnb26.local,DNS:localhost,IP:{ip},IP:127.0.0.1"],
            check=True, capture_output=True)
        key.chmod(0o600)
    env_file = shared / "app.env"
    if not env_file.exists():
        settings = {
            "DNB_DATABASE_HOST": "127.0.0.1", "DNB_DATABASE_PORT": "3307",
            "DNB_DATABASE_USER": "dnb26", "DNB_DATABASE_PASSWORD": credentials["database_password"],
            "DNB_DATABASE_NAME": "smarthome_db", "DNB_DATABASE_INIT": "true",
            "DNB_DATA_DIR": f"{shared}/data", "DNB_API_TOKEN": credentials["api_token"],
            "DNB_HARDWARE_MODE": "mock", "DNB_CAMERA_ENABLED": "true", "DNB_CAMERA_SOURCE": "0",
            "DNB_CUSTOM_MODEL": f"{shared}/models/custom.pt",
            "DNB_GENERAL_MODEL": f"{shared}/models/general.pt",
            "DNB_FACE_PREDICTOR": f"{shared}/models/shape_predictor_68_face_landmarks.dat",
            "DNB_AUTO_BOOTSTRAP_FACES": "true",
            "DNB_BOOTSTRAP_FACES_DIR": f"{root}/current/integrations/face_recognition/photos",
            "DNB_CORS_ORIGINS": "https://localhost,http://localhost,capacitor://localhost",
            "OMP_NUM_THREADS": "2", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "2",
            "MPLCONFIGDIR": f"{shared}/cache/matplotlib", "YOLO_CONFIG_DIR": f"{shared}/cache/ultralytics",
        }
        secret_file(env_file, "\n".join(f"{k}={v}" for k, v in settings.items()) + "\n")
    nginx = f'''pid {shared}/nginx.pid;
error_log {shared}/nginx-error.log;
worker_processes 1;
events {{ worker_connections 128; }}
http {{
  include {root}/runtime/etc/nginx/mime.types;
  default_type application/octet-stream;
  access_log {shared}/nginx-access.log;
  client_body_temp_path {shared}/nginx-body;
  proxy_temp_path {shared}/nginx-proxy;
  fastcgi_temp_path {shared}/nginx-fastcgi;
  uwsgi_temp_path {shared}/nginx-uwsgi;
  scgi_temp_path {shared}/nginx-scgi;
  client_max_body_size 9m;
  server {{
    listen 8080;
    listen 8443 ssl;
    server_name _;
    ssl_certificate {cert};
    ssl_certificate_key {key};
    ssl_protocols TLSv1.2 TLSv1.3;
    root {root}/current/integrations/gui/project/dist;
    location / {{ try_files $uri $uri/ /index.html; add_header Cache-Control "no-cache"; }}
    location /api/stream {{
      proxy_pass http://127.0.0.1:8000;
      proxy_buffering off; proxy_cache off; proxy_read_timeout 3600s;
    }}
    location /api/camera/stream {{
      proxy_pass http://127.0.0.1:8000;
      proxy_buffering off; proxy_cache off; proxy_read_timeout 3600s;
    }}
    location /api/ {{ proxy_pass http://127.0.0.1:8000; proxy_read_timeout 90s; }}
    location /uploads/ {{ proxy_pass http://127.0.0.1:8000; add_header Cache-Control "no-store"; }}
    location /downloads/ {{ alias {shared}/downloads/; autoindex off; }}
  }}
}}
'''
    # nginx-common is not needed system-wide; supply a small explicit type map.
    mime = root / "runtime/etc/nginx/mime.types"
    mime.parent.mkdir(parents=True, exist_ok=True)
    mime.write_text("types { text/html html; text/css css; application/javascript js; application/json json; image/png png; image/jpeg jpg jpeg; image/svg+xml svg; image/x-icon ico; application/manifest+json webmanifest; application/vnd.android.package-archive apk; application/x-x509-ca-cert crt; }\n")
    (shared / "nginx.conf").write_text(nginx)
    for name in ("nginx-body", "nginx-proxy", "nginx-fastcgi", "nginx-uwsgi", "nginx-scgi", "cache", "downloads"):
        (shared / name).mkdir(exist_ok=True)


def user_service(root: Path, name: str, command: str, extra: str = "") -> None:
    folder = Path.home() / ".config/systemd/user"
    folder.mkdir(parents=True, exist_ok=True)
    prestart = f"ExecStartPre={root}/.venv/bin/python {root}/current/deploy/wait_database.py\n" if name == "api" else ""
    text = f"""[Unit]
Description=DnB26 {name}
After=network.target
{extra}
[Service]
Type=simple
WorkingDirectory={root}/current
EnvironmentFile={root}/shared/app.env
Environment=LD_LIBRARY_PATH={root}/runtime/usr/lib/aarch64-linux-gnu
Environment=PYTHONUNBUFFERED=1
Environment=DNB_PROJECT_ROOT={root}
StandardOutput=append:{root}/shared/{name}-service.log
StandardError=append:{root}/shared/{name}-service.log
{prestart}ExecStart={command}
Restart=on-failure
RestartSec=5
TimeoutStopSec=35
UMask=0077
[Install]
WantedBy=default.target
"""
    (folder / f"dnb26-{name}.service").write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--ip", default="192.168.137.2")
    parser.add_argument("--refresh-config-only",action="store_true",help="Refresh project configs and API/Web units without stopping MySQL")
    args = parser.parse_args()
    import ipaddress
    ipaddress.ip_address(args.ip)
    root = args.root.expanduser().resolve()
    if root == Path.home() or root == Path("/") or not (root / "runtime/usr/sbin/mysqld").is_file():
        raise ValueError("Expected an isolated project root with extracted MySQL binary")
    shared = root / "shared"
    shared.mkdir(exist_ok=True, mode=0o700)
    (shared / "models").mkdir(exist_ok=True)
    secret_path = shared / "credentials.json"
    if secret_path.exists():
        credentials = json.loads(secret_path.read_text())
    else:
        credentials = {key: secrets.token_hex(24) for key in ("root_password", "database_password", "api_token")}
        secret_file(secret_path, json.dumps(credentials))
    create_configs(root, args.ip, credentials)
    if not args.refresh_config_only:
        ensure_database(root, credentials)
    user_service(root, "mysql", " ".join(mysql_args(root) + ["--bind-address=127.0.0.1", "--port=3307"]))
    user_service(root, "api", f"/bin/bash {root}/current/deploy/start_api.sh", "After=dnb26-mysql.service\nRequires=dnb26-mysql.service")
    user_service(root, "web", f"{root}/runtime/usr/sbin/nginx -p {root}/shared/ -c {root}/shared/nginx.conf -g 'daemon off;'")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    for name in ("mysql", "api", "web"):
        subprocess.run(["systemctl", "--user", "enable", "--now", f"dnb26-{name}"], check=True)
    if args.refresh_config_only:
        subprocess.run(["systemctl","--user","restart","dnb26-api","dnb26-web"],check=True)
    print(f"Services enabled. LAN: http://{args.ip}:8080 HTTPS: https://{args.ip}:8443")
    print(f"Credentials are private on the board: {secret_path} (not printed).")
    print("User services start at user login; boot-before-login needs administrator-enabled linger.")


if __name__ == "__main__":
    main()
