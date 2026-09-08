"""The derivation in Python and the derivation in SQL must agree.

This is the most important test in the suite. Status is displayed from a
database annotation but computed in Python wherever a single object is in hand,
and the dashboard totals are aggregated in SQL. If the two derivations ever
disagree, the stat tiles stop reconciling with the rows beneath them and the
discrepancy looks like a database fault rather than a code one.

Both come from STATUS_RULES in loans/status.py, so they should agree by
construction. This proves it over every combination of the six flags rather
than trusting the construction.
"""

from itertools import product

from loans.models import CashbackRequest
from loans.status import PENDING, STATUS_RULES, derive_status

from .base import SPINE_FLAGS, LoanDataTestCase


class StatusDerivationTests(LoanDataTestCase):
    def test_sql_and_python_agree_on_every_flag_combination(self):
        combinations = list(product([False, True], repeat=len(SPINE_FLAGS)))
        for index, flags in enumerate(combinations, start=1):
            self.make_loan(pk=index, **dict(zip(SPINE_FLAGS, flags)))

        rows = CashbackRequest.objects.all().order_by("id")
        self.assertEqual(rows.count(), len(combinations), "fixture did not load")

        for loan in rows:
            with self.subTest(**{f: getattr(loan, f) for f in SPINE_FLAGS}):
                self.assertEqual(
                    loan.status,
                    derive_status(loan),
                    "SQL annotation and Python derivation disagree",
                )

    def test_precedence_follows_status_rules_order(self):
        """The first flag set wins, top to bottom of STATUS_RULES."""
        for position, (code, field, _label) in enumerate(STATUS_RULES):
            # Set this flag and every lower-precedence one; the higher-
            # precedence flags stay false, so this code should win.
            flags = {f: False for f in SPINE_FLAGS}
            for _c, lower_field, _l in STATUS_RULES[position:]:
                flags[lower_field] = True
            pk = 100 + position
            self.make_loan(pk=pk, **flags)
            loan = CashbackRequest.objects.get(pk=pk)
            with self.subTest(status=code):
                self.assertEqual(loan.status, code)
                self.assertEqual(derive_status(loan), code)

    def test_no_flags_is_pending(self):
        self.make_loan(pk=200)
        loan = CashbackRequest.objects.get(pk=200)
        self.assertEqual(loan.status, PENDING)
        self.assertEqual(derive_status(loan), PENDING)

    def test_status_is_filterable_and_countable_in_sql(self):
        self.make_loan(pk=301, disbursed=True)
        self.make_loan(pk=302, disbursed=True)
        self.make_loan(pk=303, rejected=True)
        self.make_loan(pk=304)

        self.assertEqual(CashbackRequest.objects.filter(status="DISBURSED").count(), 2)
        self.assertEqual(CashbackRequest.objects.filter(status="REJECTED").count(), 1)
        self.assertEqual(CashbackRequest.objects.filter(status=PENDING).count(), 1)
