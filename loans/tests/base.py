from datetime import datetime, timedelta, timezone

from django.db import connections
from django.test import TransactionTestCase

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
    Admin,
    CashbackRequest,
    CashForCarRequest,
    PublicSectorRequest,
    RequestDocument,
    ApprovalAuditLog,
    LoanComment,
]

TINY_PNG = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmM"
    "IQAAAABJRU5ErkJggg=="
)

SPINE_FLAGS = [
    "reviewed",
    "credit_approved",
    "control_approved",
    "disbursed",
    "rejected",
    "correction_requested",
]


class LoanDataTestCase(TransactionTestCase):
    databases = {"default", "loans"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        connection = connections["loans"]
        with connection.schema_editor() as editor:
            for model in MODELS:
                editor.create_model(model)

    @classmethod
    def tearDownClass(cls):
        connection = connections["loans"]
        with connection.schema_editor() as editor:
            for model in reversed(MODELS):
                editor.delete_model(model)
        super().tearDownClass()

    def setUp(self):
        super().setUp()
        with connections["loans"].cursor() as cursor:
            for model in reversed(MODELS):
                cursor.execute(f'TRUNCATE TABLE "{model._meta.db_table}" CASCADE')

    def make_loan(self, model=CashbackRequest, pk=1, **overrides):
        created = datetime.now(timezone.utc) - timedelta(days=30)
        row = {
            "id": pk,
            "reference_no": f"REF-{pk:05d}",
            "first_name": "Test",
            "date_of_birth": "1990-01-01",
            "bvn": "12345678901",
            "nin": "10987654321",
            "loan_amount": 500000,
            "tenor_months": 12,
            "consent_given": True,
            "agreement_accepted": True,
            "correction_count": 0,
            "is_legacy": False,
            "created_at": created,
            "updated_at": created,
        }
        for flag in SPINE_FLAGS:
            row[flag] = False
        if model is CashbackRequest:
            row["surname"] = "Applicant"
        else:
            row["last_name"] = "Applicant"
        if model is CashForCarRequest:
            row.update({
                "floauto_sale_guarantee": False,
                "valuation_shortfall_guarantee": False,
                "buyout_obligation": False,
                "floauto_evaluated": False,
                "applicant_accepted": False,
                "applicant_declined": False,
                "statement_payment_confirmed": False,
            })
        row.update(overrides)

        table = model._meta.db_table
        columns = ", ".join(f'"{c}"' for c in row)
        placeholders = ", ".join(["%s"] * len(row))
        with connections["loans"].cursor() as cursor:
            cursor.execute(
                f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})',
                list(row.values()),
            )
        return pk

    def make_document(self, request_type="cashback", request_id=1, doc_id=1,
                      mime_type="image/png", data=TINY_PNG, **overrides):
        row = {
            "id": doc_id,
            "request_type": request_type,
            "request_id": request_id,
            "doc_type": "ID_CARD",
            "file_url": None,
            "file_name": "id-card.png",
            "mime_type": mime_type,
            "data": data,
            "uploaded_at": datetime.now(timezone.utc),
        }
        row.update(overrides)
        columns = ", ".join(f'"{c}"' for c in row)
        placeholders = ", ".join(["%s"] * len(row))
        with connections["loans"].cursor() as cursor:
            cursor.execute(
                f'INSERT INTO "request_document" ({columns}) VALUES ({placeholders})',
                list(row.values()),
            )
        return doc_id
