"""Bank Reports API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ManagerBankReportListView(APIView):
    """
    فهرست حساب‌های بانکی برای گزارش بانک‌ها
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_accessible_houses(self, user):
        return MyHouse.objects.filter(
            Q(user=user) | Q(user__manager=user),
            is_active=True
        )

    def get(self, request):
        user = request.user

        accessible_houses = self.get_accessible_houses(user)

        banks = Bank.objects.filter(
            user=user,
            is_active=True,
            house__in=accessible_houses
        ).select_related(
            'house'
        ).order_by(
            'bank_name', 'id'
        )

        result = []

        for bank in banks:
            balance = bank.get_current_balance()

            result.append({
                'id': bank.id,
                'bank_name': bank.bank_name,
                'account_holder_name': bank.account_holder_name,
                'account_no': bank.account_no,
                'current_balance': str(balance or Decimal('0')),
                'house_id': bank.house_id,
                'house_name': bank.house.name if bank.house else '',
            })

        return Response(result)
class ManagerBankReportTransactionsView(APIView):
    """
    گردش مالی یک حساب بانکی
    دریافت آخرین ۱۰، ۲۰ یا ۳۰ تراکنش بدون صفحه‌بندی
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    LIMIT_CHOICES = (10, 20, 30)

    def get_accessible_houses(self, user):
        return MyHouse.objects.filter(
            Q(user=user) | Q(user__manager=user),
            is_active=True
        )

    def get_bank(self, request, pk):
        accessible_houses = self.get_accessible_houses(
            request.user
        )

        return get_object_or_404(
            Bank.objects.select_related('house'),
            pk=pk,
            user=request.user,
            is_active=True,
            house__in=accessible_houses
        )

    def get(self, request, pk):
        bank = self.get_bank(request, pk)

        # -----------------------------------------
        # تعداد آخرین تراکنش‌ها
        # -----------------------------------------

        try:
            limit = int(
                request.query_params.get('limit', 10)
            )
        except (TypeError, ValueError):
            limit = 10

        if limit not in self.LIMIT_CHOICES:
            return Response(
                {
                    'detail': 'تعداد تراکنش‌ها باید ۱۰، ۲۰ یا ۳۰ باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # -----------------------------------------
        # دریافت آخرین تراکنش‌های بانک
        # -----------------------------------------

        transactions = BankFund.objects.filter(
            bank=bank,
            is_paid=True
        ).select_related(
            'unit',
            'payer_renter',
            'receiver_renter',
            'payer_third_party',
            'receiver_third_party',
            'content_type',
        ).order_by(
            '-payment_date',
            '-created_at',
            '-id'
        )[:limit]

        items = []

        for fund in transactions:

            # ---------------------------------
            # عنوان نوع تراکنش
            # ---------------------------------

            if fund.transaction_type == 'deposit':
                transaction_label = 'واریز'
                direction = 'debit'

            elif fund.transaction_type == 'withdraw':
                transaction_label = 'برداشت'
                direction = 'credit'

            elif fund.transaction_type == 'transfer':
                transaction_label = 'انتقال'
                direction = (
                    'credit'
                    if fund.to_bank_id
                    else 'debit'
                )

            else:
                transaction_label = 'نامشخص'
                direction = 'debit'

            # ---------------------------------
            # در وجه
            # ---------------------------------

            receiver = fund.get_receiver_display()

            if not receiver or receiver == '-':
                receiver = fund.get_payer_display()

            # ---------------------------------
            # اطلاعات تراکنش
            # ---------------------------------

            items.append({
                'id': fund.id,

                'financial_document_number': (
                    fund.financial_document_number
                ),

                'payment_date': (
                    fund.payment_date.isoformat()
                    if fund.payment_date else None
                ),

                'payment_description': (
                    fund.payment_description or ''
                ),

                'receiver_name': receiver or '-',

                'amount': str(
                    fund.amount or Decimal('0')
                ),

                'transaction_type': fund.transaction_type,

                'transaction_label': transaction_label,

                'direction': direction,

                'balance_after': str(
                    fund.balance_after or Decimal('0')
                ),

                'transfer_group_id': (
                    str(fund.transfer_group_id)
                    if fund.transfer_group_id else None
                ),
            })

        # -----------------------------------------
        # پاسخ نهایی
        # -----------------------------------------

        return Response({
            'bank': {
                'id': bank.id,
                'bank_name': bank.bank_name,
                'account_holder_name': bank.account_holder_name,
                'account_no': bank.account_no,
            },

            'current_balance': str(
                bank.get_current_balance() or Decimal('0')
            ),

            'limit': limit,

            'results': items,
        })
