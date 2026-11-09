"""Reports API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ManagerFundTurnoverAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # =========================================
        # تعداد رکوردهای درخواستی
        # =========================================

        try:
            limit = int(request.query_params.get('limit', 20))
        except (TypeError, ValueError):
            limit = 20

        if limit not in [10, 20, 30]:
            limit = 20

        # =========================================
        # ساختمان‌های متعلق به مدیر
        # =========================================

        houses = MyHouse.objects.filter(
            user=request.user,
            is_active=True
        )

        house_ids = list(
            houses.values_list('id', flat=True)
        )

        if not house_ids:
            return Response({
                'success': True,
                'summary': {
                    'total_debtor': 0,
                    'total_creditor': 0,
                    'balance': 0,
                },
                'limit': limit,
                'count': 0,
                'results': [],
            })

        # =========================================
        # گردش‌های صندوق
        # =========================================

        funds = Fund.objects.filter(
            house_id__in=house_ids
        ).select_related(
            'house',
            'unit',
            'bank',
            'payer_renter',
            'receiver_renter',
            'payer_third_party',
            'receiver_third_party',
            'content_type',
        )

        # =========================================
        # خلاصه مالی کل صندوق
        # =========================================

        totals = funds.aggregate(
            total_debtor=Sum('debtor_amount'),
            total_creditor=Sum('creditor_amount'),
        )

        total_debtor = (
                totals['total_debtor'] or Decimal('0')
        )

        total_creditor = (
                totals['total_creditor'] or Decimal('0')
        )

        # مانده نهایی هر ساختمان
        # چون doc_number در هر ساختمان مستقل است،
        # مانده آخرین سند هر ساختمان را جداگانه می‌گیریم.

        balance = Decimal('0')

        for house_id in house_ids:

            last_fund = (
                funds.filter(
                    house_id=house_id
                )
                .order_by('-doc_number', '-pk')
                .first()
            )

            if last_fund and last_fund.final_amount is not None:
                balance += last_fund.final_amount

        # =========================================
        # آخرین گردش‌ها
        # =========================================

        latest_funds = (
            funds
            .order_by(
                '-payment_date',
                '-doc_number',
                '-pk'
            )[:limit]
        )

        results = []

        for fund in latest_funds:
            results.append({

                'id': fund.id,

                'doc_number': fund.doc_number,

                'financial_document_number':
                    fund.financial_document_number,

                'payment_date': (
                    fund.payment_date.isoformat()
                    if fund.payment_date else None
                ),

                'payment_description':
                    fund.payment_description or '',

                'payer': fund.get_payer_display(),

                'receiver': fund.get_receiver_display(),

                'amount': str(
                    fund.amount or Decimal('0')
                ),

                'debtor_amount': str(
                    fund.debtor_amount or Decimal('0')
                ),

                'creditor_amount': str(
                    fund.creditor_amount or Decimal('0')
                ),

                'final_amount': str(
                    fund.final_amount or Decimal('0')
                ),

                'bank_display': (
                    f'{fund.bank.bank_name} - {fund.bank.account_no}'
                    if fund.bank else ''
                ),

                'transaction_no':
                    fund.transaction_no or '',

                'detail':
                    fund.payment_description or '',

                'house_name': (
                    fund.house.name
                    if fund.house else ''
                ),

                'is_initial': fund.is_initial,

            })

        # =========================================
        # پاسخ نهایی
        # =========================================

        return Response({

            'success': True,

            'summary': {

                'total_debtor': str(total_debtor),

                'total_creditor': str(total_creditor),

                'balance': str(balance),

            },

            'limit': limit,

            'count': len(results),

            'results': results,

        }, status=status.HTTP_200_OK)
def get_manager_debtor_units(user, query='', resident_type='all'):
    # =====================================================
    # شارژهای ماهیانه پرداخت نشده
    # =====================================================

    charges = (
        UnifiedCharge.objects
        .filter(
            is_paid=False,
            payment_pending=False,
            unit__isnull=False,
            user=user,
            send_notification=True,
        )
        .select_related(
            'unit',
            'unit__myhouse',
        )
        .order_by('-created_at')
    )

    # =====================================================
    # اقساط عمرانی
    # =====================================================

    civil_installments = (
        CivilInstallment.objects
        .filter(
            is_paid=False,
            payment_pending=False,
            unit__isnull=False,
            send_notification=True,
            civil_manage__user=user,
        )
        .select_related(
            'unit',
            'civil_manage',
        )
    )

    # =====================================================
    # اقساط فاضلاب
    # =====================================================

    sewage_installments = (
        SewageInstallment.objects
        .filter(
            is_paid=False,
            payment_pending=False,
            unit__isnull=False,
            send_notification=True,
            sewage_manage__user=user,
        )
        .select_related(
            'unit',
            'sewage_manage',
        )
    )

    # =====================================================
    # جستجو
    # =====================================================

    if query:
        search_filter = (
                Q(unit__unit__icontains=query)
                | Q(unit__owner_name__icontains=query)
                | Q(unit__renters__renter_name__icontains=query)
        )

        charges = charges.filter(search_filter).distinct()

        civil_installments = (
            civil_installments
            .filter(search_filter)
            .distinct()
        )

        sewage_installments = (
            sewage_installments
            .filter(search_filter)
            .distinct()
        )

    # =====================================================
    # به‌روزرسانی جریمه شارژ ماهیانه
    # =====================================================

    for charge in charges:
        charge.update_penalty()

        charge.save(
            update_fields=[
                'total_charge_month',
                'penalty_amount',
            ]
        )

    # =====================================================
    # ساخت اطلاعات بدهکارها
    # =====================================================

    debtors = defaultdict(
        lambda: {
            'unit_id': None,
            'unit_number': '',
            'debtor_id': None,
            'debtor_type': '',
            'debtor_name': '',
            'monthly_debt': 0,
            'civil_debt': 0,
            'sewage_debt': 0,
            'total_debt': 0,
            'monthly_count': 0,
            'civil_count': 0,
            'sewage_count': 0,
        }
    )

    # =====================================================
    # مالک
    # =====================================================

    def get_owner_data(unit):

        key = (
            unit.id,
            'owner',
            unit.user_id,
        )

        data = debtors[key]

        data['unit_id'] = unit.id
        data['unit_number'] = str(unit.unit)
        data['debtor_id'] = unit.user_id
        data['debtor_type'] = 'owner'

        data['debtor_name'] = (
                unit.owner_name or 'نام مالک ثبت نشده'
        )

        return data

    # =====================================================
    # مستأجر
    # =====================================================

    def get_renter_data(unit, renter):

        key = (
            unit.id,
            'renter',
            renter.id,
        )

        data = debtors[key]

        data['unit_id'] = unit.id
        data['unit_number'] = str(unit.unit)
        data['debtor_id'] = renter.id
        data['debtor_type'] = 'renter'

        data['debtor_name'] = (
                renter.renter_name or 'نام مستأجر ثبت نشده'
        )

        return data

    # =====================================================
    # شارژ ماهیانه
    # =====================================================

    for charge in charges:

        unit = charge.unit

        if not unit:
            continue

        renter = (
            unit.renters
            .filter(renter_is_active=True)
            .first()
        )

        if renter:

            data = get_renter_data(unit, renter)

        else:

            data = get_owner_data(unit)

        data['monthly_debt'] += (
                charge.total_charge_month or 0
        )

        data['monthly_count'] += 1

    # =====================================================
    # اقساط عمرانی - مالک
    # =====================================================

    for installment in civil_installments:

        unit = installment.unit

        if not unit:
            continue

        data = get_owner_data(unit)

        data['civil_debt'] += installment.amount or 0

        data['civil_count'] += 1

    # =====================================================
    # اقساط فاضلاب - مالک
    # =====================================================

    for installment in sewage_installments:

        unit = installment.unit

        if not unit:
            continue

        data = get_owner_data(unit)

        data['sewage_debt'] += installment.amount or 0

        data['sewage_count'] += 1

    # =====================================================
    # محاسبه جمع بدهی
    # =====================================================

    results = []

    for data in debtors.values():

        data['total_debt'] = (
                data['monthly_debt']
                + data['civil_debt']
                + data['sewage_debt']
        )

        if data['total_debt'] <= 0:
            continue

        if resident_type == 'owner' and data['debtor_type'] != 'owner':
            continue

        if resident_type == 'renter' and data['debtor_type'] != 'renter':
            continue

        data['id'] = (
            f"{data['unit_id']}_"
            f"{data['debtor_type']}_"
            f"{data['debtor_id']}"
        )

        results.append(data)

    # =====================================================
    # مرتب‌سازی
    # =====================================================

    results.sort(
        key=lambda x: (
            x['unit_id'],
            0 if x['debtor_type'] == 'owner' else 1,
        )
    )

    return results
class ManagerDebtorUnitsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        query = request.query_params.get('q', '').strip()

        resident_type = request.query_params.get(
            'resident_type',
            'all',
        ).strip()

        if resident_type not in ['all', 'owner', 'renter']:
            resident_type = 'all'

        try:
            limit = int(
                request.query_params.get('limit', 100)
            )
        except (TypeError, ValueError):
            limit = 100

        limit = max(1, min(limit, 200))

        results = get_manager_debtor_units(
            user=request.user,
            query=query,
            resident_type=resident_type,
        )

        total_debt = sum(
            item['total_debt']
            for item in results
        )

        return Response({
            'success': True,
            'count': len(results),
            'limit': limit,
            'total_debt': total_debt,
            'results': results[:limit],
        })
class ManagerDebtorHistoryAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, unit_id, debtor_type, debtor_id):

        if debtor_type not in ['owner', 'renter']:
            return Response(
                {
                    'success': False,
                    'message': 'نوع ساکن معتبر نیست.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =================================================
        # شارژهای ماهیانه
        # =================================================

        charges = (
            UnifiedCharge.objects
            .filter(
                user=request.user,
                unit_id=unit_id,
                is_paid=False,
                send_notification=True,
                payment_pending=False,
            )
            .select_related('unit')
            .order_by('-created_at')
        )

        # =================================================
        # اقساط عمرانی
        # =================================================

        civil_installments = (
            CivilInstallment.objects
            .filter(
                civil_manage__user=request.user,
                unit_id=unit_id,
                is_paid=False,
                send_notification=True,
                payment_pending=False,
            )
            .select_related('civil_manage', 'unit')
            .order_by('installment_number')
        )

        # =================================================
        # اقساط فاضلاب
        # =================================================

        sewage_installments = (
            SewageInstallment.objects
            .filter(
                sewage_manage__user=request.user,
                unit_id=unit_id,
                is_paid=False,
                send_notification=True,
                payment_pending=False,
            )
            .select_related('sewage_manage', 'unit')
            .order_by('installment_number')
        )

        # =================================================
        # تعیین واحد از روی سوابق بدهی
        # =================================================

        unit = Unit.objects.filter(
            id=unit_id,
            user__manager=request.user,
            is_active=True,
        ).first()

        if unit is None:
            return Response(
                {
                    'success': False,
                    'message': 'واحد پیدا نشد یا دسترسی به آن ندارید.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        # =================================================
        # تشخیص مالک / مستأجر
        # =================================================

        renter = None

        if debtor_type == 'owner':

            if unit.user_id != debtor_id:
                return Response(
                    {
                        'success': False,
                        'message': 'اطلاعات مالک معتبر نیست.',
                    },
                    status=status.HTTP_403_FORBIDDEN,
                )

            debtor_name = (
                    unit.owner_name or 'نام مالک ثبت نشده'
            )

        else:

            renter = unit.renters.filter(
                id=debtor_id,
                renter_is_active=True,
            ).first()

            if renter is None:
                return Response(
                    {
                        'success': False,
                        'message': 'مستأجر فعال پیدا نشد.',
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            debtor_name = (
                    renter.renter_name or 'نام مستأجر ثبت نشده'
            )

        # =================================================
        # سوابق شارژ ماهیانه
        # =================================================

        monthly_history = []

        if debtor_type == 'renter':

            charges = charges.filter(
                unit__renters__id=debtor_id,
                unit__renters__renter_is_active=True,
            ).distinct()

        else:

            charges = charges.exclude(
                unit__renters__renter_is_active=True,
            )

        for charge in charges:
            charge.update_penalty()

            monthly_history.append({
                'id': charge.id,
                'type': 'monthly',
                'title': charge.title or 'شارژ ماهیانه',
                'description': charge.details or '',
                'amount': charge.total_charge_month or 0,
                'base_charge': charge.base_charge or 0,
                'penalty_amount': charge.penalty_amount or 0,
                'payment_deadline_date': (
                    charge.payment_deadline_date.isoformat()
                    if charge.payment_deadline_date else None
                ),
                'created_at': (
                    charge.created_at.isoformat()
                    if charge.created_at else None
                ),
                'financial_document_number': (
                    charge.financial_document_number
                ),
            })

        # =================================================
        # سوابق عمرانی - فقط مالک
        # =================================================

        civil_history = []

        if debtor_type == 'owner':

            for installment in civil_installments:
                civil_history.append({
                    'id': installment.id,
                    'type': 'civil',
                    'title': (
                        installment.civil_manage.name
                    ),
                    'installment_number': (
                        installment.installment_number
                    ),
                    'amount': installment.amount or 0,
                    'due_date': (
                        installment.due_date.isoformat()
                        if installment.due_date else None
                    ),
                    'financial_document_number': (
                        installment.financial_document_number
                    ),
                })

        # =================================================
        # سوابق فاضلاب - فقط مالک
        # =================================================

        sewage_history = []

        if debtor_type == 'owner':

            for installment in sewage_installments:
                sewage_history.append({
                    'id': installment.id,
                    'type': 'sewage',
                    'title': (
                        installment.sewage_manage.name
                    ),
                    'installment_number': (
                        installment.installment_number
                    ),
                    'amount': installment.amount or 0,
                    'due_date': (
                        installment.due_date.isoformat()
                        if installment.due_date else None
                    ),
                    'financial_document_number': (
                        installment.financial_document_number
                    ),
                })

        # =================================================
        # جمع مبالغ
        # =================================================

        monthly_total = sum(
            item['amount'] for item in monthly_history
        )

        civil_total = sum(
            item['amount'] for item in civil_history
        )

        sewage_total = sum(
            item['amount'] for item in sewage_history
        )

        return Response({
            'success': True,

            'unit': {
                'id': unit.id,
                'number': str(unit.unit),
            },

            'debtor': {
                'id': debtor_id,
                'type': debtor_type,
                'name': debtor_name,
            },

            'summary': {
                'monthly_debt': monthly_total,
                'civil_debt': civil_total,
                'sewage_debt': sewage_total,
                'total_debt': (
                        monthly_total
                        + civil_total
                        + sewage_total
                ),
            },

            'history': {
                'monthly': monthly_history,
                'civil': civil_history,
                'sewage': sewage_history,
            },
        })
class ManagerCreditorUnitsAPIView(APIView):
    from reports.views import UnitReportsTurnOver
    permission_classes = [IsAuthenticated]

    # =====================================================
    # بررسی دسترسی مدیر
    # =====================================================

    def check_manager(self, request):

        if not request.user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        return None

    # =====================================================
    # کاربران تحت مدیریت
    # =====================================================

    def get_managed_users(self, user):

        return User.objects.filter(
            Q(manager=user) |
            Q(pk=user.pk)
        )

    # =====================================================
    # واحدهای تحت مدیریت
    # =====================================================

    def get_managed_units(self, user):

        return Unit.objects.filter(
            is_active=True,
            user__in=self.get_managed_users(user)
        ).distinct().order_by('unit')

    # =====================================================
    # دریافت پارامترهای درخواست
    # =====================================================

    def get_request_filters(self, request):

        query = request.query_params.get('q', '').strip()

        resident_type = request.query_params.get(
            'resident_type',
            'all'
        ).strip().lower()

        if resident_type not in ['all', 'owner', 'renter']:
            resident_type = 'all'

        try:
            limit = int(request.query_params.get('limit', 100))
        except (TypeError, ValueError):
            limit = 100

        if limit < 1:
            limit = 100

        # جلوگیری از دریافت تعداد بسیار زیاد
        limit = min(limit, 500)

        return query, resident_type, limit

    # =====================================================
    # دریافت فهرست بستانکاران
    # =====================================================

    def get(self, request):

        error = self.check_manager(request)

        if error:
            return error

        query, resident_type, limit = self.get_request_filters(
            request
        )

        # =================================================
        # ساخت گزارش گردش مالی
        # =================================================
        from reports.views import UnitReportsTurnOver
        report = UnitReportsTurnOver()
        report.request = request

        units = self.get_managed_units(request.user)

        # =================================================
        # دریافت مستأجران فعال
        # =================================================

        renters = Renter.objects.filter(
            unit__in=units,
            renter_is_active=True
        ).select_related(
            'unit'
        )

        # دسته‌بندی مستأجران بر اساس واحد
        renters_by_unit = {}

        for renter in renters:
            renters_by_unit.setdefault(
                renter.unit_id,
                []
            ).append(renter)

        # =================================================
        # متغیرهای محاسبات
        # =================================================

        results = []

        total_creditor_amount = Decimal('0')

        # =================================================
        # بررسی واحدها
        # =================================================

        for unit in units:

            # =============================================
            # محاسبه حساب مالک
            # =============================================

            if resident_type in ['all', 'owner']:

                (
                    owner_unit,
                    _,
                    owner_transactions,
                    owner_label
                ) = report.get_resident_transactions(
                    'owner',
                    unit.pk
                )

                (
                    _,
                    owner_debtor,
                    owner_creditor,
                    owner_balance
                ) = report.calculate_running_balance(
                    owner_transactions
                )

                # فقط مالک بستانکار
                if owner_balance < Decimal('0'):
                    creditor_amount = abs(owner_balance)

                    results.append({

                        'unit_id': unit.pk,

                        'unit_number': str(unit.unit),

                        'resident_type': 'owner',

                        'resident_id': unit.pk,

                        'resident_name': (
                                unit.owner_name or 'بدون نام مالک'
                        ).strip(),

                        'resident_label': owner_label,

                        'balance': str(owner_balance),

                        'creditor_amount': str(creditor_amount),

                    })

            # =============================================
            # محاسبه حساب مستأجران
            # =============================================

            if resident_type in ['all', 'renter']:

                unit_renters = renters_by_unit.get(
                    unit.pk,
                    []
                )

                for renter in unit_renters:

                    (
                        renter_unit,
                        _,
                        renter_transactions,
                        renter_label
                    ) = report.get_resident_transactions(
                        'renter',
                        renter.pk
                    )

                    (
                        _,
                        renter_debtor,
                        renter_creditor,
                        renter_balance
                    ) = report.calculate_running_balance(
                        renter_transactions
                    )

                    # فقط مستأجر بستانکار
                    if renter_balance < Decimal('0'):
                        creditor_amount = abs(renter_balance)

                        results.append({

                            'unit_id': unit.pk,

                            'unit_number': str(unit.unit),

                            'resident_type': 'renter',

                            'resident_id': renter.pk,

                            'resident_name': (
                                    renter.renter_name or 'بدون نام مستأجر'
                            ).strip(),

                            'resident_label': renter_label,

                            'balance': str(renter_balance),

                            'creditor_amount': str(creditor_amount),

                        })

        # =================================================
        # مرتب‌سازی نتایج
        # =================================================

        results.sort(
            key=lambda item: (
                item['unit_number'],
                0 if item['resident_type'] == 'owner' else 1
            )
        )

        # =================================================
        # اعمال جستجو
        # =================================================

        if query:
            normalized_query = query.casefold()

            results = [
                item
                for item in results
                if (
                        normalized_query in item['unit_number'].casefold()
                        or normalized_query in item['resident_name'].casefold()
                        or normalized_query in item['resident_label'].casefold()
                )
            ]

        # =================================================
        # محاسبه تعداد و مجموع بستانکاری
        # قبل از اعمال limit
        # =================================================

        total_creditors = len(results)

        total_creditor_amount = sum(
            (
                Decimal(item['creditor_amount'])
                for item in results
            ),
            Decimal('0')
        )

        # =================================================
        # اعمال محدودیت تعداد نتایج
        # =================================================

        paginated_results = results[:limit]

        # =================================================
        # پاسخ نهایی
        # =================================================

        return Response(
            {
                'success': True,

                'total_creditors': total_creditors,

                'total_creditor_amount': str(
                    total_creditor_amount
                ),

                'limit': limit,

                'results': paginated_results,
            },
            status=status.HTTP_200_OK
        )
