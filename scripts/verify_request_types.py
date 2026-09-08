"""Confirm the `request_type` strings used by the polymorphic tables.

`request_document`, `approval_audit_log` and `loan_comment` all point at an
application through a (request_type, request_id) pair rather than a foreign
key, so the exact strings matter. REQUEST_TYPE_BY_MODEL in loans/models.py
assumes 'cashback', 'cash_for_car' and 'public_sector'.

If those assumed values are wrong, nothing raises - documents and history
simply come back empty, on every application, and the portal looks like it has
no attachments rather than like it has a bug. That failure is quiet enough to
survive a casual review, which is why this check exists.

    .venv/bin/python scripts/verify_request_types.py
"""

import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connections  # noqa: E402

from loans.models import REQUEST_TYPE_BY_MODEL  # noqa: E402

TABLES = ["request_document", "approval_audit_log", "loan_comment"]


def main():
    assumed = set(REQUEST_TYPE_BY_MODEL.values())
    print("The application assumes:", ", ".join(sorted(assumed)), "\n")

    found = set()
    problems = 0
    with connections["loans"].cursor() as cursor:
        for table in TABLES:
            cursor.execute(
                f"SELECT request_type, count(*) FROM {table} "
                "GROUP BY request_type ORDER BY count(*) DESC"
            )
            rows = cursor.fetchall()
            print(f"  {table}:")
            if not rows:
                print("      (no rows)")
            for value, count in rows:
                found.add(value)
                mark = "ok" if value in assumed else "NOT RECOGNISED"
                print(f"      {value!r:<24} {count:>6} rows   {mark}")
                if value not in assumed:
                    problems += 1
            print()

    unused = assumed - found
    for value in sorted(unused):
        print(f"  {value!r} is assumed by the application but appears in no table")
        problems += 1

    if problems:
        print("\nUpdate REQUEST_TYPE_BY_MODEL in loans/models.py to match.")
    else:
        print("Every request_type matches. Documents and history will resolve.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
