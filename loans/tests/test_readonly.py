from django.db import connections
from django.test import TestCase

from loans.models import CashbackRequest, CashForCarRequest, PublicSectorRequest
from loans.routers import LoansRouter, ReadOnlyDatabaseError

PRODUCT_MODELS = [CashbackRequest, CashForCarRequest, PublicSectorRequest]


class ReadOnlyRouterTests(TestCase):
    databases = {"default"}

    def test_write_to_any_loan_model_raises(self):
        router = LoansRouter()
        for model in PRODUCT_MODELS:
            with self.subTest(model=model.__name__):
                with self.assertRaises(ReadOnlyDatabaseError):
                    router.db_for_write(model)

    def test_saving_a_loan_raises(self):
        with self.assertRaises(ReadOnlyDatabaseError):
            CashbackRequest(reference_no="X-1").save()

    def test_deleting_a_loan_raises(self):
        with self.assertRaises(ReadOnlyDatabaseError):
            CashbackRequest(pk=1).delete()

    def test_reads_are_routed_to_the_loans_connection(self):
        router = LoansRouter()
        for model in PRODUCT_MODELS:
            self.assertEqual(router.db_for_read(model), "loans")

    def test_no_migration_may_run_against_the_loans_connection(self):
        router = LoansRouter()
        self.assertIs(router.allow_migrate("loans", "loans"), False)
        self.assertIs(router.allow_migrate("loans", "auth"), False)
        self.assertIs(router.allow_migrate("default", "loans"), False)

    def test_django_owns_no_tables_in_the_loan_database(self):
        self.assertIn("sqlite", connections["default"].settings_dict["ENGINE"])
        self.assertNotEqual(
            connections["loans"].settings_dict["NAME"],
            connections["default"].settings_dict["NAME"],
        )


class UnmanagedModelTests(TestCase):
    databases = {"default"}

    def test_every_loan_model_is_unmanaged(self):
        for model in PRODUCT_MODELS:
            with self.subTest(model=model.__name__):
                self.assertFalse(
                    model._meta.managed,
                    f"{model.__name__} is managed - Django could alter the real table",
                )

    def test_password_hash_is_not_mapped(self):
        from loans.models import Admin

        self.assertNotIn(
            "password_hash",
            [f.name for f in Admin._meta.fields],
            "a reporting portal must not be able to read password hashes",
        )
