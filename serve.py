import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

env_file = BASE_DIR / ".env"
if not env_file.exists():
    sys.exit(
        f"No .env at {env_file}\n"
        "Copy .env.example to .env and fill it in before starting the server."
    )
load_dotenv(env_file)


if os.getenv("USE_SAMPLE_DB", "False").lower() == "true":
    required_settings = ("DJANGO_SECRET_KEY",)
else:
    required_settings = ("DJANGO_SECRET_KEY", "LOANS_DB_HOST", "LOANS_DB_PASSWORD")

for required in required_settings:
    if not os.getenv(required):
        sys.exit(f"{required} is not set in {env_file}. Refusing to start.")

if os.getenv("DJANGO_DEBUG", "False").lower() != "true":
    missing_mail = [
        name
        for name in ("MS_GRAPH_TENANT_ID", "MS_GRAPH_CLIENT_ID", "MS_GRAPH_CLIENT_SECRET", "MS_GRAPH_SENDER")
        if not os.getenv(name)
    ]
    if missing_mail:
        sys.exit(
            "Email is not configured: " + ", ".join(missing_mail) + " unset in "
            f"{env_file}.\nPassword setup and reset links would silently never "
            "be delivered. Refusing to start."
        )

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve

from config.wsgi import application

host = os.getenv("DJANGO_BIND_HOST", "0.0.0.0")
port = int(os.getenv("DJANGO_PORT", "8600"))
threads = int(os.getenv("DJANGO_THREADS", "8"))

print(f"Loan Reports portal -> http://{host}:{port}  ({threads} threads)", flush=True)

from django.conf import settings

db = settings.DATABASES["loans"]
print(f"Settings: DEBUG={settings.DEBUG}  hosts={settings.ALLOWED_HOSTS}", flush=True)
print(f"Database: {db.get('HOST')}/{db.get('NAME')}", flush=True)
print(
    f"Exports:  PII {'INCLUDED' if settings.EXPORT_INCLUDE_PII else 'masked'}",
    flush=True,
)
if settings.SAMPLE_DB:
    print("WARNING: serving FABRICATED sample data (USE_SAMPLE_DB is set).", flush=True)

trusted_proxy = os.getenv("DJANGO_TRUSTED_PROXY", "127.0.0.1")

serve(
    application,
    host=host,
    port=port,
    threads=threads,
    ident="",
    trusted_proxy=trusted_proxy,
    trusted_proxy_count=1,
    trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
    clear_untrusted_proxy_headers=True,
)
