from django.test import SimpleTestCase

from loans.models import (
    Admin,
    ApprovalAuditLog,
    CashbackRequest,
    CashForCarRequest,
    LoanComment,
    PublicSectorRequest,
    RequestDocument,
)

from .schema_snapshot import INTENTIONALLY_UNMAPPED, MAPPED_TABLES

MODELS = [
    CashbackRequest,
    CashForCarRequest,
    PublicSectorRequest,
    Admin,
    RequestDocument,
    ApprovalAuditLog,
    LoanComment,
]


class SchemaCoverageTests(SimpleTestCase):
    def test_no_model_maps_a_column_the_database_lacks(self):
        for model in MODELS:
            table = model._meta.db_table
            real = set(MAPPED_TABLES[table])
            mapped = {f.attname for f in model._meta.fields}
            with self.subTest(table=table):
                self.assertEqual(
                    mapped - real,
                    set(),
                    f"{model.__name__} maps columns that do not exist in {table}",
                )

    def test_every_database_column_is_mapped_or_explicitly_excused(self):
        for model in MODELS:
            table = model._meta.db_table
            real = set(MAPPED_TABLES[table])
            mapped = {f.attname for f in model._meta.fields}
            excused = set(INTENTIONALLY_UNMAPPED.get(table, {}))
            with self.subTest(table=table):
                self.assertEqual(
                    real - mapped - excused,
                    set(),
                    f"{table} has columns {model.__name__} does not map. Either add "
                    f"them or record the reason in INTENTIONALLY_UNMAPPED.",
                )

    def test_password_hash_is_excused_rather_than_forgotten(self):
        self.assertIn("password_hash", INTENTIONALLY_UNMAPPED["admins"])
        self.assertNotIn("password_hash", {f.attname for f in Admin._meta.fields})


class RequestTypeTests(SimpleTestCase):
    def test_request_type_strings_match_the_live_database(self):
        from loans.models import (
            REQUEST_TYPE_BY_MODEL,
            CashbackRequest,
            CashForCarRequest,
            PublicSectorRequest,
        )

        self.assertEqual(
            REQUEST_TYPE_BY_MODEL,
            {
                CashbackRequest: "cashback",
                CashForCarRequest: "cfc",
                PublicSectorRequest: "psl",
            },
        )

    def test_every_product_has_a_request_type(self):
        from loans.models import PRODUCTS, REQUEST_TYPE_BY_MODEL

        for model in PRODUCTS.values():
            self.assertIn(model, REQUEST_TYPE_BY_MODEL)
