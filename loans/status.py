from django.db.models import Case, CharField, Value, When

STATUS_RULES = [
    ("REJECTED", "rejected", "Rejected"),
    ("DISBURSED", "disbursed", "Disbursed"),
    ("CORRECTION_REQUESTED", "correction_requested", "Correction requested"),
    ("CONTROL_APPROVED", "control_approved", "Control approved"),
    ("CREDIT_APPROVED", "credit_approved", "Credit approved"),
    ("REVIEWED", "reviewed", "Reviewed"),
]

PENDING = "PENDING"
PENDING_LABEL = "Pending"

STATUS_CHOICES = [(code, label) for code, _field, label in STATUS_RULES] + [
    (PENDING, PENDING_LABEL)
]
STATUS_LABELS = dict(STATUS_CHOICES)

STATUS_FIELDS = [field for _code, field, _label in STATUS_RULES]

TERMINAL_STATUSES = ["REJECTED", "DISBURSED"]

OPEN_STATUSES = [code for code, _f, _l in STATUS_RULES if code not in TERMINAL_STATUSES] + [
    PENDING
]

PIPELINE_POSITION = {
    PENDING: 0,
    "REVIEWED": 1,
    "CREDIT_APPROVED": 2,
    "CONTROL_APPROVED": 3,
    "DISBURSED": 4,
}
PIPELINE_LENGTH = 4


def status_expression():
    return Case(
        *[
            When(**{field: True}, then=Value(code))
            for code, field, _label in STATUS_RULES
        ],
        default=Value(PENDING),
        output_field=CharField(),
    )


def derive_status(obj):
    for code, field, _label in STATUS_RULES:
        if getattr(obj, field, False):
            return code
    return PENDING


def status_label(code):
    return STATUS_LABELS.get(code, code)
