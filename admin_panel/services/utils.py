from django.db import transaction

from admin_panel.models import FinancialDocumentSequence


def get_next_financial_document_number(house):
    if not house:
        raise ValueError(
            'برای ایجاد شماره سند مالی، ساختمان مشخص نشده است.'
        )

    with transaction.atomic():

        sequence, created = (
            FinancialDocumentSequence.objects
            .get_or_create(
                house=house,
                defaults={'last_number': 0}
            )
        )

        # حتماً ردیف شمارنده را قفل می‌کنیم
        sequence = (
            FinancialDocumentSequence.objects
            .select_for_update()
            .get(pk=sequence.pk)
        )

        sequence.last_number += 1
        sequence.save(update_fields=['last_number'])

        return sequence.last_number