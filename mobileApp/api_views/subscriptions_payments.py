"""Subscriptions Payments API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ManagerUserPayMoneyListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # =========================================
        # ساختمان مدیر
        # =========================================

        house = MyHouse.objects.filter(
            user=request.user
        ).first()

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'ساختمانی برای مدیر پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =========================================
        # فهرست کمک‌های ثبت‌شده در ساختمان
        # =========================================

        payments = (
            UserPayMoney.objects
            .filter(house=house)
            .select_related(
                'user',
                'unit',
                'unit__user',
                'bank',
                'house',
            )
            .prefetch_related(
                'documents',
            )
            .order_by('-created_at', '-id')
        )

        # =========================================
        # محاسبات آماری
        # =========================================

        statistics = payments.aggregate(
            total_amount=Sum('amount'),
        )

        total_count = payments.count()

        # =========================================
        # سریالایزر
        # =========================================

        serializer = UserPayMoneySerializer(
            payments,
            many=True,
            context={
                'request': request,
            }
        )

        # =========================================
        # پاسخ
        # =========================================

        return Response(
            {
                'success': True,
                'house_id': house.id,

                'statistics': {
                    'total_count': total_count,
                    'total_amount': statistics['total_amount'] or 0,
                },

                'payments': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
class ManagerAdminFundListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = request.user

        # دریافت ساختمان مدیر
        house = MyHouse.objects.filter(
            user=manager
        ).first()

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'ساختمانی برای مدیر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # دریافت تمام تراکنش‌های مدیر
        funds = (
            AdminFund.objects
            .filter(user=manager)
            .select_related(
                'user',
                'house',
                'bank',
                'content_type',
            )
            .order_by('-payment_date', '-id')
        )

        # آمار کلی
        total_count = funds.count()

        paid_funds = funds.filter(is_paid=True)

        paid_count = paid_funds.count()

        total_amount = paid_funds.aggregate(
            total=Sum('amount')
        )['total'] or 0

        # نوع تراکنش‌ها
        sms_content_type = ContentType.objects.get_for_model(
            SmsCredit
        )

        subscription_content_type = ContentType.objects.get_for_model(
            Subscription
        )

        sms_funds = paid_funds.filter(
            content_type=sms_content_type
        )

        subscription_funds = paid_funds.filter(
            content_type=subscription_content_type
        )

        sms_statistics = sms_funds.aggregate(
            count=Count('id'),
            amount=Sum('amount')
        )

        subscription_statistics = subscription_funds.aggregate(
            count=Count('id'),
            amount=Sum('amount')
        )

        serializer = ManagerAdminFundSerializer(
            funds,
            many=True,
            context={'request': request}
        )

        return Response(
            {
                'success': True,
                'house_id': house.id,
                'house_name': house.name,

                'statistics': {
                    'total_count': total_count,
                    'paid_count': paid_count,
                    'unpaid_count': 0,
                    'total_amount': total_amount,

                    'sms_credit': {
                        'count': sms_statistics['count'] or 0,
                        'amount': sms_statistics['amount'] or 0,
                    },

                    'subscription': {
                        'count': subscription_statistics['count'] or 0,
                        'amount': subscription_statistics['amount'] or 0,
                    },
                },

                'transactions': serializer.data,
            },
            status=status.HTTP_200_OK
        )
class ManagerAdminMessageListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        manager = request.user

        read_statuses = MiddleMessageReadStatus.objects.filter(
            user=manager
        )

        messages = AdminMessageToMiddle.objects.filter(
            middleAdmins=manager,
            is_active=True,
        ).select_related(
            'sender'
        ).prefetch_related(
            Prefetch(
                'read_statuses',
                queryset=read_statuses,
                to_attr='user_read_statuses'
            )
        ).order_by('-created_at', '-id').distinct()

        # اتصال وضعیت خواندن مخصوص همین مدیر
        for message in messages:
            statuses = message.user_read_statuses
            message.current_user_read_status = (
                statuses[0] if statuses else None
            )

        unread_count = sum(
            1 for message in messages
            if not (
                    message.current_user_read_status
                    and message.current_user_read_status.is_read
            )
        )

        read_count = len(messages) - unread_count

        selected_status = request.query_params.get('status', 'all')

        if selected_status == 'unread':
            messages = [
                message for message in messages
                if not (
                        message.current_user_read_status
                        and message.current_user_read_status.is_read
                )
            ]

        elif selected_status == 'read':
            messages = [
                message for message in messages
                if (
                        message.current_user_read_status
                        and message.current_user_read_status.is_read
                )
            ]

        serializer = ManagerAdminMessageSerializer(
            messages,
            many=True
        )

        return Response({
            'success': True,
            'statistics': {
                'total_count': read_count + unread_count,
                'read_count': read_count,
                'unread_count': unread_count,
            },
            'messages': serializer.data,
        }, status=status.HTTP_200_OK)
class ManagerAdminMessageMarkReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        message = AdminMessageToMiddle.objects.filter(
            id=pk,
            middleAdmins=request.user,
            is_active=True,
        ).first()

        if not message:
            return Response({
                'success': False,
                'message': 'پیام موردنظر پیدا نشد.'
            }, status=status.HTTP_404_NOT_FOUND)

        read_status, created = MiddleMessageReadStatus.objects.get_or_create(
            message=message,
            user=request.user,
            defaults={
                'is_read': True,
                'read_at': timezone.now(),
            }
        )

        if not read_status.is_read:
            read_status.is_read = True
            read_status.read_at = timezone.now()
            read_status.save(update_fields=['is_read', 'read_at'])

        return Response({
            'success': True,
            'message': 'پیام با موفقیت خوانده شد.',
            'is_read': True,
            'read_at': read_status.read_at,
        }, status=status.HTTP_200_OK)
class ManagerSubscriptionAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # فقط مدیر ساختمان
        if not getattr(request.user, 'is_middle_admin', False):
            return Response({
                'success': False,
                'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
            }, status=status.HTTP_403_FORBIDDEN)

        # دریافت ساختمان مدیر
        house = MyHouse.objects.filter(
            user=request.user
        ).first()

        if not house:
            return Response({
                'success': True,
                'has_house': False,
                'has_subscription': False,
                'subscription': None,
                'message': 'ساختمانی برای این مدیر ثبت نشده است.'
            }, status=status.HTTP_200_OK)

        now = timezone.now()

        # ابتدا اشتراک فعال
        subscription = Subscription.objects.filter(
            user=request.user,
            house=house,
            is_paid=True,
            status='active',
            end_date__gte=now,
        ).select_related(
            'plan'
        ).order_by(
            '-end_date',
            '-created_at'
        ).first()

        # در صورت نبود اشتراک فعال، آخرین اشتراک پرداخت‌شده
        if not subscription:
            subscription = Subscription.objects.filter(
                user=request.user,
                house=house,
                is_paid=True,
            ).select_related(
                'plan'
            ).order_by(
                '-created_at'
            ).first()

        if not subscription:
            return Response({
                'success': True,
                'has_house': True,
                'has_subscription': False,
                'house': {
                    'id': house.id,
                    'name': house.name,
                },
                'subscription': None,
                'message': 'برای این ساختمان اشتراکی ثبت نشده است.'
            }, status=status.HTTP_200_OK)

        # اطلاعات روزهای اشتراک
        total_days = max(0, subscription.total_days)
        days_remaining = max(0, subscription.days_remaining)

        if total_days > 0:
            remaining_percent = round(
                (days_remaining / total_days) * 100
            )
        else:
            remaining_percent = 0

        remaining_percent = max(
            0,
            min(100, remaining_percent)
        )

        elapsed_percent = 100 - remaining_percent
        elapsed_days = max(
            0,
            total_days - days_remaining
        )

        # وضعیت اشتراک
        if (
                subscription.status == 'active'
                and subscription.end_date >= now
        ):
            subscription_status = 'active'
            status_label = 'فعال'
        else:
            subscription_status = 'expired'
            status_label = 'منقضی شده'

        plan = subscription.plan

        return Response({
            'success': True,
            'has_house': True,
            'has_subscription': True,

            'house': {
                'id': house.id,
                'name': house.name,
            },

            'subscription': {
                'id': subscription.id,

                'status': subscription_status,
                'status_label': status_label,

                'plan': {
                    'id': plan.id if plan else None,
                    'duration': plan.duration if plan else None,
                    'price_per_unit': (
                        str(plan.price_per_unit)
                        if plan else None
                    ),
                },

                'units_count': subscription.units_count,

                'total_amount': str(
                    subscription.total_amount or 0
                ),

                'discount_amount': str(
                    subscription.discount_amount or 0
                ),

                'final_amount': str(
                    subscription.final_amount or 0
                ),

                'is_trial': subscription.is_trial,

                'start_date': (
                    subscription.start_date.isoformat()
                    if subscription.start_date else None
                ),

                'end_date': (
                    subscription.end_date.isoformat()
                    if subscription.end_date else None
                ),

                'payment_date': (
                    subscription.payment_date.isoformat()
                    if subscription.payment_date else None
                ),

                'days_remaining': days_remaining,
                'total_days': total_days,
                'elapsed_days': elapsed_days,

                'remaining_percent': remaining_percent,
                'elapsed_percent': elapsed_percent,
            }
        }, status=status.HTTP_200_OK)
def get_payment_payer_info(unit, allow_renter=False):
    """
    تشخیص پرداخت‌کننده و آماده‌سازی اطلاعات برای Fund و BankFund.
    """

    if not unit:
        raise DjangoValidationError('واحد پرداخت‌کننده مشخص نیست.')

    # پرداخت توسط مستأجر فعال
    if allow_renter:
        renter = Renter.objects.filter(
            unit=unit,
            renter_is_active=True
        ).exclude(
            renter_name__isnull=True
        ).exclude(
            renter_name__exact=''
        ).order_by('-id').first()

        if renter:
            person_name = renter.renter_name.strip()

            return (
                'renter',
                renter,
                person_name,
                f'واحد {unit.unit} - مستأجر: {person_name}'
            )

    # در غیر این صورت پرداخت‌کننده مالک است
    owner_name = (unit.owner_name or '').strip()

    if not owner_name:
        raise DjangoValidationError(
            'نام مالک این واحد مشخص نیست.'
        )

    return (
        'owner',
        None,
        owner_name,
        f'واحد {unit.unit} - مالک: {owner_name}'
    )
class ManagerPendingPaymentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        manager = request.user
        house = getattr(manager, 'house', None)

        if not house:
            return Response({
                'success': False,
                'message': 'ساختمان برای مدیر تعریف نشده است.'
            }, status=status.HTTP_400_BAD_REQUEST)

        payment_type = (
                request.query_params.get('type') or ''
        ).strip().lower()

        if payment_type not in ['', 'monthly', 'civil', 'sewage']:
            return Response({
                'success': False,
                'message': 'نوع پرداخت نامعتبر است.'
            }, status=status.HTTP_400_BAD_REQUEST)

        payments = []

        # ==========================================
        # شارژ ماهیانه
        # ==========================================

        if payment_type in ['', 'monthly']:

            monthly_qs = UnifiedCharge.objects.filter(
                unit__myhouse=house,
                payment_pending=True,
                is_paid=False
            ).select_related(
                'unit',
                'house',
                'bank'
            ).order_by('-payment_submitted_at', '-id')

            for charge in monthly_qs:
                unit = charge.unit

                payments.append({
                    'payment_id': charge.pk,
                    'payment_type': 'monthly',
                    'payment_type_display': 'شارژ ماهیانه',
                    'title': charge.title or 'شارژ ماهیانه',

                    'unit_id': unit.pk if unit else None,
                    'unit_number': str(unit.unit) if unit else '-',
                    'owner_name': unit.owner_name if unit else '-',

                    'amount': str(
                        charge.total_charge_month
                        or charge.amount
                        or Decimal('0')
                    ),

                    'bank_name': str(charge.bank) if charge.bank else '-',

                    'transaction_reference': (
                            charge.transaction_reference or ''
                    ),

                    'payment_submitted_at': (
                        charge.payment_submitted_at.isoformat()
                        if charge.payment_submitted_at else None
                    ),
                })

        # ==========================================
        # شارژ عمرانی
        # ==========================================

        if payment_type in ['', 'civil']:

            civil_qs = CivilInstallment.objects.filter(
                unit__myhouse=house,
                payment_pending=True,
                is_paid=False
            ).select_related(
                'unit',
                'house',
                'bank',
                'civil_manage'
            ).order_by('-payment_submitted_at', '-id')

            for installment in civil_qs:
                unit = installment.unit

                payments.append({
                    'payment_id': installment.pk,
                    'payment_type': 'civil',
                    'payment_type_display': 'شارژ عمرانی',

                    'title': (
                        installment.civil_manage.name
                        if installment.civil_manage
                        else 'شارژ عمرانی'
                    ),

                    'installment_number': installment.installment_number,

                    'unit_id': unit.pk if unit else None,
                    'unit_number': str(unit.unit) if unit else '-',
                    'owner_name': unit.owner_name if unit else '-',

                    'amount': str(installment.amount or 0),

                    'bank_name': (
                        str(installment.bank)
                        if installment.bank else '-'
                    ),

                    'transaction_reference': (
                            installment.transaction_reference or ''
                    ),

                    'payment_submitted_at': (
                        installment.payment_submitted_at.isoformat()
                        if installment.payment_submitted_at else None
                    ),
                })

        # ==========================================
        # هزینه فاضلاب
        # ==========================================

        if payment_type in ['', 'sewage']:

            sewage_qs = SewageInstallment.objects.filter(
                unit__myhouse=house,
                payment_pending=True,
                is_paid=False
            ).select_related(
                'unit',
                'house',
                'bank',
                'sewage_manage'
            ).order_by('-payment_submitted_at', '-id')

            for installment in sewage_qs:
                unit = installment.unit

                payments.append({
                    'payment_id': installment.pk,
                    'payment_type': 'sewage',
                    'payment_type_display': 'هزینه فاضلاب',

                    'title': (
                        installment.sewage_manage.name
                        if installment.sewage_manage
                        else 'هزینه فاضلاب'
                    ),

                    'installment_number': installment.installment_number,

                    'unit_id': unit.pk if unit else None,
                    'unit_number': str(unit.unit) if unit else '-',
                    'owner_name': unit.owner_name if unit else '-',

                    'amount': str(installment.amount or 0),

                    'bank_name': (
                        str(installment.bank)
                        if installment.bank else '-'
                    ),

                    'transaction_reference': (
                            installment.transaction_reference or ''
                    ),

                    'payment_submitted_at': (
                        installment.payment_submitted_at.isoformat()
                        if installment.payment_submitted_at else None
                    ),
                })

        # ==========================================
        # مرتب‌سازی کلی
        # ==========================================

        payments.sort(
            key=lambda item: item['payment_submitted_at'] or '',
            reverse=True
        )

        return Response({
            'success': True,

            'statistics': {
                'total': len(payments),

                'monthly': sum(
                    p['payment_type'] == 'monthly'
                    for p in payments
                ),

                'civil': sum(
                    p['payment_type'] == 'civil'
                    for p in payments
                ),

                'sewage': sum(
                    p['payment_type'] == 'sewage'
                    for p in payments
                ),
            },

            'payments': payments,

        }, status=status.HTTP_200_OK)
class ManagerApprovePaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):
        manager = request.user
        house = getattr(manager, "house", None)

        if not house:
            return Response(
                {
                    "success": False,
                    "message": "ساختمان مدیر مشخص نیست."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_type = request.data.get("payment_type")
        payment_id = request.data.get("payment_id")

        if payment_type not in ("monthly", "civil", "sewage"):
            return Response(
                {
                    "success": False,
                    "message": "نوع پرداخت معتبر نیست."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not payment_id:
            return Response(
                {
                    "success": False,
                    "message": "شناسه پرداخت ارسال نشده است."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 1. دریافت قسط بر اساس نوع پرداخت
        # --------------------------------------------------

        try:
            if payment_type == "monthly":
                payment = (
                    UnifiedCharge.objects
                    .select_for_update()
                    .select_related("unit", "bank")
                    .get(
                        pk=payment_id,
                        unit__myhouse=house,
                        payment_pending=True,
                        is_paid=False,
                    )
                )

                amount = Decimal(
                    payment.total_charge_month or 0
                )

                title = "پرداخت شارژ ماهانه"
                allow_renter = True

            elif payment_type == "civil":
                payment = (
                    CivilInstallment.objects
                    .select_for_update()
                    .select_related("unit", "bank")
                    .get(
                        pk=payment_id,
                        unit__myhouse=house,
                        payment_pending=True,
                        is_paid=False,
                    )
                )

                amount = Decimal(payment.amount or 0)

                title = "پرداخت شارژ عمرانی"
                allow_renter = False

            else:
                payment = (
                    SewageInstallment.objects
                    .select_for_update()
                    .select_related("unit", "bank")
                    .get(
                        pk=payment_id,
                        unit__myhouse=house,
                        payment_pending=True,
                        is_paid=False,
                    )
                )

                amount = Decimal(payment.amount or 0)

                title = "پرداخت شارژ فاضلاب"
                allow_renter = False

        except (
            UnifiedCharge.DoesNotExist,
            CivilInstallment.DoesNotExist,
            SewageInstallment.DoesNotExist,
        ):
            return Response(
                {
                    "success": False,
                    "message": (
                        "پرداخت موردنظر پیدا نشد یا قبلاً تأیید شده است."
                    )
                },
                status=status.HTTP_404_NOT_FOUND
            )

        except (InvalidOperation, TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "message": "مبلغ پرداخت معتبر نیست."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 2. اعتبارسنجی واحد و بانک
        # --------------------------------------------------

        unit = payment.unit
        bank = payment.bank

        if not unit:
            return Response(
                {
                    "success": False,
                    "message": "واحد مربوط به پرداخت مشخص نیست."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not bank:
            return Response(
                {
                    "success": False,
                    "message": "حساب بانکی مربوط به پرداخت مشخص نیست."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        payment_house = unit.myhouse

        if payment_house != house:
            return Response(
                {
                    "success": False,
                    "message": "این پرداخت متعلق به ساختمان شما نیست."
                },
                status=status.HTTP_403_FORBIDDEN
            )

        if amount <= 0:
            return Response(
                {
                    "success": False,
                    "message": "مبلغ پرداخت باید بیشتر از صفر باشد."
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 3. شماره سند مالی از خود قسط خوانده می‌شود
        # --------------------------------------------------

        financial_document_number = (
            payment.financial_document_number
        )

        if not financial_document_number:
            return Response(
                {
                    "success": False,
                    "message": (
                        "شماره سند مالی برای این قسط ثبت نشده است. "
                        "ابتدا اطلاعات قسط را بررسی کنید."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 4. بررسی اطلاعات پرداخت‌کننده
        # --------------------------------------------------

        try:
            (
                payer_type,
                payer_renter,
                payer_person_name,
                payer_name_snapshot,
            ) = get_payment_payer_info(
                unit,
                allow_renter=allow_renter
            )

        except DjangoValidationError as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": (
                        "خطا در دریافت اطلاعات پرداخت‌کننده: "
                        f"{str(exc)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 5. بررسی سوابق مالی قبلی
        # --------------------------------------------------

        # عمداً از حالت پیش‌فرض get_for_model استفاده شده
        # تا ContentType با BankTransactionService یکسان باشد.
        content_type = ContentType.objects.get_for_model(payment)

        fund_record = Fund.objects.filter(
            content_type=content_type,
            object_id=payment.pk,
        ).first()

        bank_fund_record = BankFund.objects.filter(
            content_type=content_type,
            object_id=payment.pk,
            transaction_type="deposit",
        ).first()

        # هر دو سابقه وجود دارند؛ ثبت مجدد ممنوع است.
        if fund_record and bank_fund_record:
            return Response(
                {
                    "success": False,
                    "message": (
                        "برای این پرداخت قبلاً سابقه مالی ثبت شده است. "
                        "لطفاً گردش مالی را بررسی کنید."
                    ),
                    "fund_id": fund_record.pk,
                    "bank_fund_id": bank_fund_record.pk,
                    "financial_document_number": (
                        payment.financial_document_number
                    ),
                },
                status=status.HTTP_409_CONFLICT
            )

        # فقط یکی از سوابق وجود دارد؛ وضعیت ناسازگار است.
        if fund_record or bank_fund_record:
            return Response(
                {
                    "success": False,
                    "message": (
                        "سوابق مالی این پرداخت ناقص است. "
                        "یکی از رکوردهای صندوق یا بانک وجود دارد. "
                        "برای جلوگیری از ثبت تکراری، عملیات انجام نشد."
                    ),
                    "fund_id": (
                        fund_record.pk if fund_record else None
                    ),
                    "bank_fund_id": (
                        bank_fund_record.pk
                        if bank_fund_record else None
                    ),
                    "financial_document_number": (
                        payment.financial_document_number
                    ),
                },
                status=status.HTTP_409_CONFLICT
            )

        # --------------------------------------------------
        # 6. ثبت واریز در بانک
        # --------------------------------------------------

        payment_date = timezone.now().date()
        gateway = "پرداخت الکترونیک"

        transaction_no = getattr(
            payment,
            "transaction_reference",
            None
        )

        description = f"{title}: {payment}"

        try:
            bank_fund = BankTransactionService.deposit(
                user=manager,
                bank=bank,
                unit=unit,
                amount=amount,
                description=description,
                content_object=payment,
                payment_date=payment_date,
                transaction_no=transaction_no,
                gateway=gateway,
                house=payment_house,
                payer_type=payer_type,
                payer_renter=payer_renter,
                payer_name=payer_name_snapshot,

                # مهم:
                # شماره سند از قسط موجود گرفته می‌شود.
                # سرویس نباید شماره جدید بسازد.
                financial_document_number=financial_document_number,
            )

        except DjangoValidationError as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        except Exception as exc:
            return Response(
                {
                    "success": False,
                    "message": (
                        "خطا در ثبت گردش بانکی: "
                        f"{str(exc)}"
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # --------------------------------------------------
        # 7. کنترل شماره سند ثبت‌شده در BankFund
        # --------------------------------------------------

        if (
            bank_fund.financial_document_number
            != financial_document_number
        ):
            raise DjangoValidationError(
                "شماره سند ثبت‌شده در بانک با شماره سند قسط مطابقت ندارد."
            )

        # --------------------------------------------------
        # 8. ثبت در صندوق
        # --------------------------------------------------

        fund = Fund.objects.create(
            user=manager,
            content_type=content_type,
            object_id=payment.pk,
            unit=unit,
            house=payment_house,
            bank=bank,

            financial_document_number=financial_document_number,

            amount=amount,
            debtor_amount=amount,
            creditor_amount=Decimal("0"),

            payment_date=payment_date,
            transaction_no=transaction_no,
            payment_description=description,
            is_paid=True,
        )

        # --------------------------------------------------
        # 9. تغییر وضعیت قسط پس از ثبت سوابق مالی
        # --------------------------------------------------

        payment.is_paid = True
        payment.payment_pending = False
        payment.payment_date = payment_date
        payment.payment_gateway = gateway

        payment.save(
            update_fields=[
                "is_paid",
                "payment_pending",
                "payment_date",
                "payment_gateway",
            ]
        )

        # --------------------------------------------------
        # 10. پاسخ موفقیت
        # --------------------------------------------------

        return Response(
            {
                "success": True,
                "message": "پرداخت با موفقیت تأیید شد.",
                "data": {
                    "payment_id": payment.pk,
                    "payment_type": payment_type,
                    "amount": str(amount),
                    "unit_id": unit.pk,
                    "fund_id": fund.pk,
                    "bank_fund_id": bank_fund.pk,
                    "financial_document_number": (
                        financial_document_number
                    ),
                    "is_paid": payment.is_paid,
                    "payment_pending": payment.payment_pending,
                }
            },
            status=status.HTTP_200_OK
        )
