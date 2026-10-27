import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.conf import settings
from django.db import connections

from loans.models import (
    Admin,
    ApprovalAuditLog,
    CashbackRequest,
    CashForCarRequest,
    LoanComment,
    PublicSectorRequest,
    RequestDocument,
)

MODELS = [
    CashbackRequest,
    CashForCarRequest,
    PublicSectorRequest,
    Admin,
    RequestDocument,
    ApprovalAuditLog,
    LoanComment,
]

INTENTIONALLY_UNMAPPED = {
    "admins": {
        "password_hash": "a reporting portal must not read password hashes",
        "roles": "authorisation is not delegated to the loan system's roles",
    },
}


def live_columns(cursor, table):
    cursor.execute(
        """
        SELECT column_name, data_type, is_nullable
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        [table],
    )
    return {row[0]: (row[1], row[2]) for row in cursor.fetchall()}


def main():
    if settings.SAMPLE_DB:
        print("USE_SAMPLE_DB is set - this would compare the models against a")
        print("database generated from those same models, which proves nothing.")
        print("Point .env at the real database and run again.")
        return 2

    problems = 0
    connection = connections["loans"]
    print(f"Comparing models against {connection.settings_dict['NAME']}\n")

    with connection.cursor() as cursor:
        for model in MODELS:
            table = model._meta.db_table
            live = live_columns(cursor, table)
            if not live:
                print(f"  MISSING TABLE  {table}")
                problems += 1
                continue

            mapped = {f.attname for f in model._meta.fields}
            expected = INTENTIONALLY_UNMAPPED.get(table, {})

            missing = mapped - set(live)
            unmapped = set(live) - mapped - set(expected)

            status = "ok" if not (missing or unmapped) else "DIFFERS"
            print(f"  {table:<24} {len(live):>3} columns  {status}")

            for column in sorted(missing):
                print(f"      model has {column!r}, the table does not")
                problems += 1
            for column in sorted(unmapped):
                print(f"      table has {column!r}, the model does not")
                problems += 1

    print()
    if problems:
        print(f"{problems} difference(s). Re-run inspectdb and update loans/models.py:")
        print("  .venv/bin/python manage.py inspectdb <table> --database=loans")
    else:
        print("Models and database agree.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
