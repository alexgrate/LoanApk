import os
import sys
from pathlib import Path

import django

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.db import connections

from loans.models import REQUEST_TYPE_BY_MODEL

TABLES = ["request_document", "approval_audit_log", "loan_comment"]

KNOWN_UNMODELLED = {
    "extension": "tenor_extension, which this portal does not model",
}


def main():
    assumed = set(REQUEST_TYPE_BY_MODEL.values())
    print("The application assumes:", ", ".join(sorted(assumed)), "\n")

    found = set()
    problems = 0
    unmodelled = {}
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
                if value in assumed:
                    mark = "ok"
                elif value in KNOWN_UNMODELLED:
                    mark = "not modelled"
                    unmodelled[value] = unmodelled.get(value, 0) + count
                else:
                    mark = "NOT RECOGNISED"
                    problems += 1
                print(f"      {value!r:<24} {count:>6} rows   {mark}")
            print()

    for value in sorted(assumed - found):
        print(f"  {value!r} is assumed by the application but appears in no table")
        problems += 1

    for value, count in sorted(unmodelled.items()):
        print(
            f"  note: {value!r} ({count} rows) belongs to {KNOWN_UNMODELLED[value]}. "
            "Not an error."
        )

    if problems:
        print("\nUpdate REQUEST_TYPE_BY_MODEL in loans/models.py to match.")
    else:
        print("\nEvery modelled request_type matches. Documents and history will resolve.")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
