import django_filters
from django import forms
from django.db.models import Q
from django.db.utils import Error as DatabaseError

from .status import STATUS_CHOICES


def _distinct_choices(model, column):
    def choices():
        try:
            values = (
                model.objects.order_by(column)
                .values_list(column, flat=True)
                .distinct()
            )
            return [(v, v) for v in values if v]
        except DatabaseError:
            return []

    return choices


class LoanRequestFilter(django_filters.FilterSet):
    q = django_filters.CharFilter(
        method="search",
        label="Search",
        widget=forms.TextInput(
            attrs={"placeholder": "Reference, name, BVN, NIN, phone, email..."}
        ),
    )

    status = django_filters.ChoiceFilter(
        choices=STATUS_CHOICES, empty_label="All statuses", label="Status"
    )

    created_from = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__gte",
        label="Created from",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    created_to = django_filters.DateFilter(
        field_name="created_at",
        lookup_expr="date__lte",
        label="Created to",
        widget=forms.DateInput(attrs={"type": "date"}),
    )

    amount_min = django_filters.NumberFilter(
        field_name="loan_amount", lookup_expr="gte", label="Amount from"
    )
    amount_max = django_filters.NumberFilter(
        field_name="loan_amount", lookup_expr="lte", label="Amount to"
    )

    account_officer = django_filters.CharFilter(
        lookup_expr="icontains", label="Account officer"
    )
    state = django_filters.CharFilter(lookup_expr="iexact", label="State")

    is_legacy = django_filters.BooleanFilter(
        label="Legacy record",
        widget=forms.Select(choices=[("", "All records"), ("false", "Current"), ("true", "Legacy")]),
    )

    sort = django_filters.OrderingFilter(
        fields=(
            "created_at",
            "reference_no",
            "first_name",
            "loan_amount",
            "status",
            "account_officer",
        )
    )

    class Meta:
        fields = []

    def search(self, queryset, name, value):
        value = value.strip()
        if not value:
            return queryset

        last_name_field = self.Meta.model.LAST_NAME_FIELD
        terms = (
            Q(reference_no__icontains=value)
            | Q(first_name__icontains=value)
            | Q(**{f"{last_name_field}__icontains": value})
            | Q(email__icontains=value)
            | Q(phone__icontains=value)
            | Q(account_officer__icontains=value)
            | Q(loan_purpose__icontains=value)
        )
        if value.isdigit():
            terms = terms | Q(bvn=value) | Q(nin=value)

        if hasattr(self.Meta.model, "middle_name"):
            terms = terms | Q(middle_name__icontains=value)

        return queryset.filter(terms)


def filter_for(model):
    return type(
        f"{model.__name__}Filter",
        (LoanRequestFilter,),
        {"Meta": type("Meta", (LoanRequestFilter.Meta,), {"model": model, "fields": []})},
    )
