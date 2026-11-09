"""Sewage Charges API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class SewageChargeListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # ============================================
        # پیدا کردن ساختمان کاربر
        # ============================================

        house = (
            MyHouse.objects.filter(
                Q(units__user=request.user) |
                Q(
                    units__renters__user=request.user,
                    units__renters__renter_is_active=True,
                )
            )
            .distinct()
            .order_by('-created_at')
            .first()
        )

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'ساختمان کاربر پیدا نشد.',
                    'charges': [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ============================================
        # پیدا کردن واحد کاربر
        # ============================================

        unit = (
            Unit.objects.filter(
                Q(user=request.user) |
                Q(
                    renters__user=request.user,
                    renters__renter_is_active=True,
                ),
                myhouse=house,
            )
            .distinct()
            .first()
        )

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد کاربر پیدا نشد.',
                    'charges': [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ============================================
        # شارژهای عمرانی
        # ============================================

        charges = (
            SewageManage.objects.filter(
                house=house,
                is_active=True,
            )
            .annotate(
                sent_units_count=Count(
                    'sewage_installments__unit',
                    filter=Q(
                        sewage_installments__send_notification=True
                    ),
                    distinct=True,
                ),
            )
            .filter(
                sent_units_count__gt=0
            )
            .order_by('id')
        )

        serializer = SewageManageSerializer(
            charges,
            many=True,
            context={
                'unit': unit,
            },
        )

        return Response(
            {
                'success': True,
                'house_id': house.id,
                'unit_id': unit.id,
                'charges': serializer.data,
            },
            status=status.HTTP_200_OK,
        )
class SewageChargeInstallmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, sewage_id):

        # ============================================
        # ساختمان و واحد کاربر
        # ============================================

        house = (
            MyHouse.objects.filter(
                Q(units__user=request.user) |
                Q(
                    units__renters__user=request.user,
                    units__renters__renter_is_active=True,
                )
            )
            .distinct()
            .first()
        )

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'ساختمان پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        unit = (
            Unit.objects.filter(
                Q(user=request.user) |
                Q(
                    renters__user=request.user,
                    renters__renter_is_active=True,
                ),
                myhouse=house,
            )
            .distinct()
            .first()
        )

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ============================================
        # شارژ عمرانی
        # ============================================

        try:
            sewage = SewageManage.objects.get(
                id=sewage_id,
                house=house,
                is_active=True,
            )
        except SewageManage.DoesNotExist:

            return Response(
                {
                    'success': False,
                    'message': 'شارژ عمرانی پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # ============================================
        # اقساط واحد
        # ============================================

        installments = list(
            SewageInstallment.objects.filter(
                sewage_manage=sewage,
                unit=unit,
            )
            .select_related(
                'unit',
                'sewage_manage',
                'bank',
            )
            .order_by(
                'installment_number'
            )
        )

        # ============================================
        # اولین قسط پرداخت نشده
        # ============================================

        first_unpaid_found = False

        for installment in installments:

            installment.can_pay = False

            if (
                    not installment.is_paid
                    and not installment.payment_pending
                    and not first_unpaid_found
            ):
                installment.can_pay = True
                first_unpaid_found = True

        # ============================================
        # Serializer
        # ============================================

        serializer = SewageInstallmentSerializer(
            installments,
            many=True,
        )

        data = serializer.data

        # اضافه کردن can_pay
        for index, item in enumerate(data):
            item['can_pay'] = installments[index].can_pay

        return Response(
            {
                'success': True,

                'sewage': {
                    'id': sewage.id,
                    'name': sewage.name,
                    'amount': sewage.amount,
                    'prepayment': sewage.prepayment,
                    'installment_count': sewage.installment_count,
                    'first_due_date': sewage.first_due_date,
                    'details': sewage.details,
                },

                'unit': {
                    'id': unit.id,
                    'unit_number': getattr(
                        unit,
                        'unit_number',
                        None,
                    ),
                },

                'installments': data,
            },
            status=status.HTTP_200_OK,
        )
class SewageChargePaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, installment_id):

        installment = (
            SewageInstallment.objects
            .filter(
                id=installment_id,
                sewage_manage__is_active=True,
            )
            .select_related(
                'unit',
                'house',
                'sewage_manage',
            )
            .first()
        )

        if not installment:
            return Response(
                {
                    'success': False,
                    'message': 'قسط شارژ عمرانی پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        unit = installment.unit

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد مربوط به این قسط پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی مالک
        # =====================================================

        is_owner = unit.user_id == request.user.id

        # =====================================================
        # بررسی مستأجر فعال
        # =====================================================

        is_active_renter = Renter.objects.filter(
            unit=unit,
            user=request.user,
            renter_is_active=True,
        ).exists()

        # =====================================================
        # بررسی دسترسی
        # =====================================================

        if not is_owner and not is_active_renter:
            return Response(
                {
                    'success': False,
                    'message': 'این قسط متعلق به شما نیست.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # پرداخت شده
        # =====================================================

        if installment.is_paid:
            return Response(
                {
                    'success': False,
                    'status': 'paid',
                    'message': 'این قسط قبلاً پرداخت شده است.',
                    'is_paid': True,
                    'payment_pending': False,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # در انتظار تأیید
        # =====================================================

        if installment.payment_pending:
            return Response(
                {
                    'success': False,
                    'status': 'pending',
                    'message': (
                        'درخواست پرداخت این قسط قبلاً ثبت شده '
                        'و در انتظار تأیید مدیر ساختمان است.'
                    ),
                    'is_paid': False,
                    'payment_pending': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # حساب‌های بانکی
        # =====================================================

        banks = Bank.objects.filter(
            house=installment.house,
            is_active=True,
        ).order_by(
            '-is_default',
            'bank_name',
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'success': True,

                'installment': {
                    'id': installment.id,
                    'sewage_id': installment.sewage_manage_id,
                    'sewage_name': installment.sewage_manage.name,
                    'installment_number': installment.installment_number,
                    'amount': installment.amount,
                    'prepayment_per_unit': (
                        installment.prepayment_per_unit
                    ),
                    'due_date': installment.due_date,
                    'is_paid': installment.is_paid,
                    'payment_pending': (
                        installment.payment_pending
                    ),
                },

                'payment_banks': [
                    {
                        'id': bank.id,
                        'bank_name': bank.bank_name,
                        'account_no': bank.account_no,
                        'account_holder_name': (
                            bank.account_holder_name
                        ),
                        'sheba_number': bank.sheba_number,
                        'cart_number': bank.cart_number,
                        'is_default': bank.is_default,
                    }
                    for bank in banks
                ],

                'payment_methods': [
                    {
                        'type': 'manual',
                        'title': 'کارت به کارت',
                        'available': banks.exists(),
                        'description': (
                            'واریز مبلغ قسط به حساب ساختمان '
                            'و ثبت کد پیگیری'
                            if banks.exists()
                            else
                            'حساب بانکی برای ساختمان ثبت نشده است.'
                        ),
                    },
                ],
            },
            status=status.HTTP_200_OK,
        )
class ManualSewagePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, installment_id):

        serializer = ManualSewagePaymentSerializer(
            data=request.data,
            context={
                'request': request,
                'installment_id': installment_id,
            },
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        installment = serializer.validated_data[
            'installment'
        ]

        bank = serializer.validated_data[
            'bank'
        ]

        transaction_reference = (
            serializer.validated_data[
                'transaction_reference'
            ]
        )

        payment_date = (
            serializer.validated_data[
                'payment_date'
            ]
        )

        # =====================================================
        # قفل قسط
        # =====================================================

        installment = (
            SewageInstallment.objects
            .select_for_update()
            .select_related(
                'unit',
                'house',
                'sewage_manage',
            )
            .get(
                pk=installment.pk
            )
        )

        # =====================================================
        # بررسی نهایی
        # =====================================================

        if installment.is_paid:
            return Response(
                {
                    'success': False,
                    'message': 'این قسط قبلاً پرداخت شده است.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if installment.payment_pending:
            return Response(
                {
                    'success': False,
                    'message': (
                        'درخواست پرداخت این قسط قبلاً ثبت شده '
                        'و در انتظار تأیید مدیر ساختمان است.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # ثبت پرداخت
        # =====================================================

        installment.bank = bank

        installment.transaction_reference = (
            transaction_reference
        )

        installment.payment_date = payment_date

        installment.payment_gateway = 'کارت به کارت'

        # هنوز تأیید مدیر نشده
        installment.is_paid = False

        # درخواست ثبت شده
        installment.payment_pending = True

        installment.payment_submitted_at = timezone.now()

        installment.save(
            update_fields=[
                'bank',
                'transaction_reference',
                'payment_date',
                'payment_gateway',
                'is_paid',
                'payment_pending',
                'payment_submitted_at',
            ]
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'success': True,

                'message': (
                    'درخواست پرداخت با موفقیت ثبت شد '
                    'و در انتظار تأیید مدیر ساختمان است.'
                ),

                'installment': {
                    'id': installment.id,

                    'sewage_id': (
                        installment.sewage_manage_id
                    ),

                    'sewage_name': (
                        installment.sewage_manage.name
                    ),

                    'unit_id': (
                        installment.unit_id
                    ),

                    'installment_number': (
                        installment.installment_number
                    ),

                    'amount': (
                        installment.amount
                    ),

                    'transaction_reference': (
                        installment.transaction_reference
                    ),

                    'payment_date': (
                        installment.payment_date
                    ),

                    'payment_gateway': (
                        installment.payment_gateway
                    ),

                    'is_paid': False,

                    'payment_pending': True,

                    'payment_submitted_at': (
                        installment.payment_submitted_at
                    ),
                },

                'bank': {
                    'id': bank.id,
                    'bank_name': bank.bank_name,
                    'account_holder_name': (
                        bank.account_holder_name
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )
def sewage_normalize_digits(value):
    if value is None:
        return value

    value = str(value)

    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    arabic_digits = "٠١٢٣٤٥٦٧٨٩"

    for index, digit in enumerate(persian_digits):
        value = value.replace(digit, str(index))

    for index, digit in enumerate(arabic_digits):
        value = value.replace(digit, str(index))

    return value.strip()
def sewage_parse_date(value):
    if not value:
        return None

    value = sewage_normalize_digits(value)

    try:
        year, month, day = map(int, value.split("-"))

        if 1200 <= year <= 1600:
            return jdatetime.date(
                year, month, day
            ).togregorian()

        if 1900 <= year <= 2200:
            return date(year, month, day)

    except (ValueError, TypeError):
        return None

    return None
def sewage_get_eligible_units(sewage, user):
    """
    تمام واحدهای فعال ساختمان مرتبط با هزینه فاضلاب.
    """
    units = Unit.objects.filter(
        is_active=True,
        user__manager=user,
        myhouse=sewage.house,
    )

    return units.order_by("unit")
def sewage_get_unit_count(sewage):
    return sewage_get_eligible_units(
        sewage, sewage.user
    ).count()
def sewage_count_fully_paid_units(sewage):
    unit_ids = (
        SewageInstallment.objects.filter(
            sewage_manage=sewage,
            unit__isnull=False,
        )
        .values_list("unit_id", flat=True)
        .distinct()
    )

    count = 0

    for unit_id in unit_ids:
        installments = SewageInstallment.objects.filter(
            sewage_manage=sewage,
            unit_id=unit_id,
        )

        if installments.exists() and not installments.filter(
                is_paid=False
        ).exists():
            count += 1

    return count
def sewage_prepare_installments(sewage, user):
    """
    ایجاد پیش‌پرداخت و اقساط برای تمام واحدهای فعال ساختمان.
    در این مرحله هیچ اعلانی ارسال نمی‌شود.
    """

    units = list(
        sewage_get_eligible_units(sewage, user)
    )

    count = len(units)

    if count == 0:
        raise ValueError(
            "هیچ واحد فعالی برای ثبت هزینه فاضلاب پیدا نشد."
        )

    total = int(sewage.amount or 0)
    prepayment_total = int(sewage.prepayment or 0)
    installment_count = int(sewage.installment_count or 0)

    if total <= 0:
        raise ValueError(
            "مبلغ هزینه فاضلاب باید بیشتر از صفر باشد."
        )

    if prepayment_total < 0 or prepayment_total > total:
        raise ValueError(
            "مبلغ پیش‌پرداخت معتبر نیست."
        )

    if installment_count < 0:
        raise ValueError(
            "تعداد اقساط نمی‌تواند منفی باشد."
        )

    if (
            installment_count == 0
            and prepayment_total not in (0, total)
    ):
        raise ValueError(
            "برای مبلغ باقی‌مانده، تعداد اقساط باید بیشتر از صفر باشد؛ "
            "برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."
        )

    total_base, total_extra = divmod(total, count)
    pre_base, pre_extra = divmod(prepayment_total, count)

    base_date = sewage.first_due_date or timezone.localdate()

    created_units = 0
    created_rows = 0

    with transaction.atomic():

        for index, unit in enumerate(units):

            existing = SewageInstallment.objects.filter(
                sewage_manage=sewage,
                unit=unit,
            )

            if existing.exists():
                continue

            unit_total = total_base + (
                1 if index < total_extra else 0
            )

            unit_prepayment = pre_base + (
                1 if index < pre_extra else 0
            )

            remaining = unit_total - unit_prepayment

            if remaining < 0:
                raise ValueError(
                    "پیش‌پرداخت هر واحد نمی‌تواند از سهم هزینه آن بیشتر باشد."
                )

            rows = []

            # پرداخت یکجا بدون پیش‌پرداخت
            if installment_count == 0 and unit_prepayment == 0:

                rows.append(
                    SewageInstallment(
                        sewage_manage=sewage,
                        house=sewage.house,
                        unit=unit,
                        installment_number=1,
                        amount=unit_total,
                        prepayment_per_unit=0,
                        due_date=base_date,
                        financial_document_number=(
                            get_next_financial_document_number(
                                sewage.house
                            )
                        ),
                        send_notification=False,
                        send_notification_date=None,
                    )
                )

            else:

                # پیش‌پرداخت
                if unit_prepayment > 0:
                    rows.append(
                        SewageInstallment(
                            sewage_manage=sewage,
                            house=sewage.house,
                            unit=unit,
                            installment_number=0,
                            amount=unit_prepayment,
                            prepayment_per_unit=unit_prepayment,
                            due_date=base_date,
                            financial_document_number=(
                                get_next_financial_document_number(
                                    sewage.house
                                )
                            ),
                            send_notification=False,
                            send_notification_date=None,
                        )
                    )

                # اقساط باقی‌مانده
                if remaining > 0:

                    if installment_count <= 0:
                        raise ValueError(
                            "تعداد اقساط برای مبلغ باقی‌مانده معتبر نیست."
                        )

                    regular, extra = divmod(
                        remaining,
                        installment_count,
                    )

                    for number in range(
                            1,
                            installment_count + 1,
                    ):
                        installment_amount = regular + (
                            1 if number <= extra else 0
                        )

                        rows.append(
                            SewageInstallment(
                                sewage_manage=sewage,
                                house=sewage.house,
                                unit=unit,
                                installment_number=number,
                                amount=installment_amount,
                                prepayment_per_unit=0,
                                due_date=(
                                        base_date
                                        + relativedelta(months=number)
                                ),
                                financial_document_number=(
                                    get_next_financial_document_number(
                                        sewage.house
                                    )
                                ),
                                send_notification=False,
                                send_notification_date=None,
                            )
                        )

            if rows:
                SewageInstallment.objects.bulk_create(rows)
                created_units += 1
                created_rows += len(rows)

    return {
        "eligible_unit_count": count,
        "created_units_count": created_units,
        "created_installments_count": created_rows,
        "share_per_unit": total // count,
        "prepayment_per_unit": prepayment_total // count,
        "installment_amount_per_unit": (
            (total - prepayment_total) // count // installment_count
            if installment_count else 0
        ),
    }
def sewage_serialize(sewage, request):
    documents = []

    for doc in sewage.sewage_documents.all():
        if doc.document:
            documents.append({
                "id": doc.id,
                "url": request.build_absolute_uri(
                    doc.document.url
                ),
                "uploaded_at": doc.uploaded_at.isoformat(),
            })

    eligible_count = sewage_get_eligible_units(
        sewage, sewage.user
    ).count()

    sent_count = sewage.count_sent_units()

    return {
        "id": sewage.id,
        "name": sewage.name,
        "amount": sewage.amount,
        "prepayment": sewage.prepayment,
        "installment_count": sewage.installment_count,
        "first_due_date": (
            sewage.first_due_date.isoformat()
            if sewage.first_due_date else None
        ),
        "details": sewage.details or "",
        "is_active": sewage.is_active,
        "created_at": sewage.created_at.isoformat(),
        "documents": documents,
        "sent_units_count": sent_count,
        "fully_paid_units_count": (
            sewage_count_fully_paid_units(sewage)
        ),
        "eligible_unit_count": eligible_count,
        "total_unit_count": eligible_count,
        "is_sent": sent_count > 0,
    }
class ManagerSewageChargesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        return MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

    def get(self, request):
        house = self.get_house(request)

        if not house:
            return Response({
                "success": False,
                "message": "ساختمان فعالی برای مدیر پیدا نشد.",
                "results": [],
            }, status=status.HTTP_400_BAD_REQUEST)

        sewages = (
            SewageManage.objects.filter(
                user=request.user,
                house=house,
            )
            .prefetch_related("sewage_documents")
            .order_by("-created_at")
        )

        return Response({
            "success": True,
            "count": sewages.count(),
            "results": [
                sewage_serialize(item, request)
                for item in sewages
            ],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        house = self.get_house(request)

        if not house:
            return Response({
                "success": False,
                "message": "ساختمان فعالی برای مدیر پیدا نشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist("document")

        if len(files) > 2:
            return Response({
                "success": False,
                "message": "حداکثر دو فایل مجاز است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()

        parsed_date = sewage_parse_date(
            data.get("first_due_date")
        )

        if not parsed_date:
            return Response({
                "success": False,
                "message": "تاریخ اولین سررسید معتبر نیست.",
                "errors": {
                    "first_due_date": [
                        "تاریخ را به صورت YYYY-MM-DD وارد کنید."
                    ]
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        data["first_due_date"] = (
            jdatetime.date.fromgregorian(
                date=parsed_date
            ).strftime("%Y-%m-%d")
        )

        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0

        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = SewageForm(
            data=data,
            files=request.FILES,
        )

        if not form.is_valid():
            return Response({
                "success": False,
                "message": "اطلاعات هزینه فاضلاب معتبر نیست.",
                "errors": form.errors.get_json_data(),
            }, status=status.HTTP_400_BAD_REQUEST)

        amount = form.cleaned_data["amount"]
        prepayment = form.cleaned_data.get("prepayment") or 0
        installment_count = (
                form.cleaned_data.get("installment_count") or 0
        )

        if amount <= 0:
            return Response({
                "success": False,
                "message": "مبلغ هزینه فاضلاب باید بیشتر از صفر باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if prepayment < 0 or prepayment > amount:
            return Response({
                "success": False,
                "message": "پیش‌پرداخت باید بین صفر و مبلغ کل باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if installment_count < 0:
            return Response({
                "success": False,
                "message": "تعداد اقساط نمی‌تواند منفی باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if (
                installment_count == 0
                and prepayment not in (0, amount)
        ):
            return Response({
                "success": False,
                "message": (
                    "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر وارد کنید؛ "
                    "برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():

                sewage = form.save(commit=False)
                sewage.user = request.user
                sewage.house = house
                sewage.prepayment = prepayment
                sewage.installment_count = installment_count
                sewage.save()

                for uploaded_file in files:
                    SewageDocument.objects.create(
                        sewage=sewage,
                        document=uploaded_file,
                    )

                calculation = sewage_prepare_installments(
                    sewage,
                    request.user,
                )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Creating sewage/installments failed"
            )

            return Response({
                "success": False,
                "message": "ثبت هزینه فاضلاب و محاسبه اقساط انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = sewage_serialize(sewage, request)
        result["calculation"] = calculation

        return Response({
            "success": True,
            "message": "هزینه فاضلاب ثبت و اقساط آن محاسبه شد.",
            "result": result,
        }, status=status.HTTP_201_CREATED)
class ManagerSewageChargeDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_sewage(self, request, sewage_id):
        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None

        return SewageManage.objects.filter(
            id=sewage_id,
            user=request.user,
            house=house,
        ).prefetch_related("sewage_documents").first()

    def put(self, request, sewage_id):
        sewage = self.get_sewage(request, sewage_id)

        if not sewage:
            return Response({
                "success": False,
                "message": "هزینه فاضلاب پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        existing = SewageInstallment.objects.filter(
            sewage_manage=sewage
        )

        if existing.filter(send_notification=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این هزینه قبلاً اعلان شده است و برای جلوگیری "
                    "از تغییر سوابق، قابل ویرایش نیست."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        if existing.filter(is_paid=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این هزینه دارای قسط پرداخت‌شده است و امکان "
                    "بازسازی اقساط آن وجود ندارد."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist("document")

        if len(files) > 2:
            return Response({
                "success": False,
                "message": "حداکثر دو فایل جدید مجاز است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        raw_date = data.get("first_due_date")

        if raw_date:
            parsed_date = sewage_parse_date(raw_date)

            if not parsed_date:
                return Response({
                    "success": False,
                    "message": "تاریخ اولین سررسید معتبر نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            data["first_due_date"] = (
                jdatetime.date.fromgregorian(
                    date=parsed_date
                ).strftime("%Y-%m-%d")
            )

        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0

        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = SewageForm(
            data=data,
            files=request.FILES,
            instance=sewage,
        )

        if not form.is_valid():
            return Response({
                "success": False,
                "message": "اطلاعات هزینه فاضلاب معتبر نیست.",
                "errors": form.errors.get_json_data(),
            }, status=status.HTTP_400_BAD_REQUEST)

        amount = form.cleaned_data["amount"]
        prepayment = form.cleaned_data.get("prepayment") or 0
        installment_count = (
                form.cleaned_data.get("installment_count") or 0
        )

        if amount <= 0:
            return Response({
                "success": False,
                "message": "مبلغ هزینه فاضلاب باید بیشتر از صفر باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if prepayment < 0 or prepayment > amount:
            return Response({
                "success": False,
                "message": "پیش‌پرداخت باید بین صفر و مبلغ کل باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if installment_count < 0:
            return Response({
                "success": False,
                "message": "تعداد اقساط نمی‌تواند منفی باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if (
                installment_count == 0
                and prepayment not in (0, amount)
        ):
            return Response({
                "success": False,
                "message": (
                    "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر وارد کنید؛ "
                    "برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():

                SewageInstallment.objects.filter(
                    sewage_manage=sewage,
                    send_notification=False,
                    is_paid=False,
                ).delete()

                sewage = form.save(commit=False)
                sewage.prepayment = prepayment
                sewage.installment_count = installment_count
                sewage.save()

                for uploaded_file in files:
                    SewageDocument.objects.create(
                        sewage=sewage,
                        document=uploaded_file,
                    )

                calculation = sewage_prepare_installments(
                    sewage,
                    request.user,
                )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Updating sewage/installments failed"
            )

            return Response({
                "success": False,
                "message": "ویرایش هزینه فاضلاب و محاسبه مجدد اقساط انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = sewage_serialize(sewage, request)
        result["calculation"] = calculation

        return Response({
            "success": True,
            "message": "هزینه فاضلاب و اقساط آن ویرایش شدند.",
            "result": result,
        }, status=status.HTTP_200_OK)

    def delete(self, request, sewage_id):
        sewage = self.get_sewage(request, sewage_id)

        if not sewage:
            return Response({
                "success": False,
                "message": "هزینه فاضلاب پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        installments = SewageInstallment.objects.filter(
            sewage_manage=sewage
        )

        if installments.filter(is_paid=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این هزینه دارای قسط پرداخت‌شده است "
                    "و امکان حذف آن وجود ندارد."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        if installments.filter(send_notification=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این هزینه برای واحدها ارسال شده است؛ "
                    "ابتدا وضعیت ارسال آن را بررسی کنید."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            sewage.delete()

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Deleting sewage failed"
            )

            return Response({
                "success": False,
                "message": "حذف هزینه فاضلاب انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "هزینه فاضلاب حذف شد.",
        }, status=status.HTTP_200_OK)
class ManagerSewageChargeUnitsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def _get_unit_resident_info(self, unit):
        owner_name = str(
            getattr(unit, "owner_name", "") or ""
        ).strip()

        return {
            "resident_type": "owner" if owner_name else "empty",
            "resident_name": owner_name,
            "people_count": max(
                int(getattr(unit, "owner_people_count", 0) or 0),
                0,
            ),
        }

    def get(self, request, sewage_id):
        sewage = SewageManage.objects.filter(
            id=sewage_id,
            user=request.user,
            house__is_active=True,
        ).first()

        if not sewage:
            return Response({
                "success": False,
                "message": "هزینه فاضلاب پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        units = sewage_get_eligible_units(
            sewage,
            request.user,
        ).prefetch_related(
            Prefetch(
                "renters",
                queryset=Renter.objects.filter(
                    renter_is_active=True
                ),
                to_attr="active_renters_for_charge",
            )
        )

        results = []

        for unit in units:
            installment_rows = list(
                SewageInstallment.objects.filter(
                    sewage_manage=sewage,
                    unit=unit,
                ).order_by("installment_number")
            )

            resident_info = self._get_unit_resident_info(unit)

            results.append({
                "id": unit.id,
                "unit": str(unit.unit),
                "resident_type": resident_info["resident_type"],
                "resident_name": resident_info["resident_name"],
                "people_count": resident_info["people_count"],
                "sent": any(
                    item.send_notification
                    for item in installment_rows
                ),
                "has_paid_installment": any(
                    item.is_paid
                    for item in installment_rows
                ),
                "installments": [
                    {
                        "id": item.id,
                        "installment_number": item.installment_number,
                        "amount": item.amount,
                        "due_date": (
                            item.due_date.isoformat()
                            if item.due_date else None
                        ),
                        "send_notification": item.send_notification,
                        "is_paid": item.is_paid,
                    }
                    for item in installment_rows
                ],
            })

        return Response({
            "success": True,
            "sewage_id": sewage.id,
            "count": len(results),
            "results": results,
        }, status=status.HTTP_200_OK)
class ManagerSendSewageChargeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, sewage_id):
        sewage = SewageManage.objects.filter(
            id=sewage_id,
            user=request.user,
            house__is_active=True,
        ).first()

        if not sewage:
            return Response({
                "success": False,
                "message": "هزینه فاضلاب پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        raw_ids = request.data.get("unit_ids", [])

        if isinstance(raw_ids, str):
            try:
                raw_ids = json.loads(raw_ids)
            except (ValueError, TypeError):
                raw_ids = [
                    item.strip()
                    for item in raw_ids.split(",")
                    if item.strip()
                ]

        if not isinstance(raw_ids, list):
            raw_ids = []

        all_requested = str(
            request.data.get("all_units", "")
        ).lower() in ("true", "1", "yes")

        units_qs = sewage_get_eligible_units(
            sewage,
            request.user,
        )

        if all_requested:
            units = list(units_qs)
        else:
            ids = []

            for value in raw_ids:
                try:
                    ids.append(int(value))
                except (TypeError, ValueError):
                    continue

            units = list(units_qs.filter(id__in=ids))

        if not units:
            return Response({
                "success": False,
                "message": "هیچ واحد معتبری انتخاب نشده است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        sent_count = 0
        already_sent_count = 0
        paid_count = 0
        missing_count = 0

        try:
            with transaction.atomic():

                for unit in units:
                    installments = SewageInstallment.objects.filter(
                        sewage_manage=sewage,
                        unit=unit,
                    )

                    if not installments.exists():
                        missing_count += 1
                        continue

                    if installments.filter(
                            send_notification=True
                    ).exists():
                        already_sent_count += 1
                        continue

                    if installments.filter(is_paid=True).exists():
                        paid_count += 1
                        continue

                    updated = installments.filter(
                        send_notification=False
                    ).update(
                        send_notification=True,
                        send_notification_date=date.today(),
                    )

                    if updated:
                        sent_count += 1

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Updating sewage notification status failed"
            )

            return Response({
                "success": False,
                "message": "ثبت وضعیت ارسال هزینه فاضلاب انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "وضعیت اعلان هزینه فاضلاب ثبت شد.",
            "sewage_id": sewage.id,
            "sent_units_count": sent_count,
            "already_sent_units_count": already_sent_count,
            "missing_installments_count": missing_count,
            "skipped_paid_units_count": paid_count,
        }, status=status.HTTP_200_OK)
class ManagerCancelSewageChargeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, sewage_id):
        sewage = SewageManage.objects.filter(
            id=sewage_id,
            user=request.user,
            house__is_active=True,
        ).first()

        if not sewage:
            return Response({
                "success": False,
                "message": "هزینه فاضلاب پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        raw_ids = request.data.get("unit_ids", [])

        if isinstance(raw_ids, str):
            try:
                raw_ids = json.loads(raw_ids)
            except (ValueError, TypeError):
                raw_ids = [
                    item.strip()
                    for item in raw_ids.split(",")
                    if item.strip()
                ]

        if not isinstance(raw_ids, list):
            raw_ids = []

        all_units_requested = str(
            request.data.get("all_units", "")
        ).lower() in ("true", "1", "yes")

        units_qs = sewage_get_eligible_units(
            sewage,
            request.user,
        )

        if all_units_requested:
            units = list(units_qs)
        else:
            valid_ids = []

            for unit_id in raw_ids:
                try:
                    valid_ids.append(int(unit_id))
                except (TypeError, ValueError):
                    continue

            units = list(
                units_qs.filter(
                    id__in=valid_ids
                )
            )

        if not units:
            return Response({
                "success": False,
                "message": "هیچ واحد معتبری انتخاب نشده است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        cancelled_units_count = 0
        cancelled_installments_count = 0
        skipped_paid_units_count = 0
        skipped_unsent_units_count = 0

        try:
            with transaction.atomic():

                for unit in units:
                    installments = SewageInstallment.objects.filter(
                        sewage_manage=sewage,
                        unit=unit,
                        send_notification=True,
                    )

                    if not installments.exists():
                        skipped_unsent_units_count += 1
                        continue

                    # اگر هر قسطی پرداخت شده باشد، اعلان این واحد لغو نمی‌شود.
                    if SewageInstallment.objects.filter(
                            sewage_manage=sewage,
                            unit=unit,
                            is_paid=True,
                    ).exists():
                        skipped_paid_units_count += 1
                        continue

                    updated_count = installments.update(
                        send_notification=False,
                        send_notification_date=None,
                    )

                    if updated_count:
                        cancelled_units_count += 1
                        cancelled_installments_count += updated_count

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "Cancelling sewage notifications failed"
            )

            return Response({
                "success": False,
                "message": "هنگام لغو اعلان هزینه فاضلاب خطایی رخ داد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "عملیات لغو اعلان هزینه فاضلاب انجام شد.",
            "sewage_id": sewage.id,
            "cancelled_units_count": cancelled_units_count,
            "cancelled_installments_count": cancelled_installments_count,
            "skipped_paid_units_count": skipped_paid_units_count,
            "skipped_unsent_units_count": skipped_unsent_units_count,
        }, status=status.HTTP_200_OK)
class ManagerThirdPartyListCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # =====================================================
    # دریافت ساختمان فعال مدیر
    # =====================================================

    def get_house(self, user):
        return MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

    # =====================================================
    # بررسی دسترسی مدیر و ساختمان
    # =====================================================

    def check_manager(self, request):

        if not request.user.is_middle_admin:
            return None, Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        house = self.get_house(request.user)

        if not house:
            return None, Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return house, None

    # =====================================================
    # تبدیل مقدار فعال / غیرفعال
    # =====================================================

    def parse_boolean(self, value):

        if isinstance(value, bool):
            return value

        value = str(value).strip().lower()

        if value in ['true', '1', 'yes', 'on']:
            return True

        if value in ['false', '0', 'no', 'off']:
            return False

        return None

    # =====================================================
    # دریافت فهرست اشخاص ثالث
    # =====================================================

    def get(self, request):

        house, error = self.check_manager(request)

        if error:
            return error

        third_parties = ThirdParty.objects.filter(
            house=house
        ).order_by('name')

        serializer = ManagerThirdPartySerializer(
            third_parties,
            many=True
        )

        return Response(
            {
                'success': True,
                'count': len(serializer.data),
                'results': serializer.data
            },
            status=status.HTTP_200_OK
        )

    # =====================================================
    # ایجاد شخص ثالث
    # =====================================================

    @transaction.atomic
    def post(self, request):

        house, error = self.check_manager(request)

        if error:
            return error

        name = str(
            request.data.get('name', '') or ''
        ).strip()

        person_type = str(
            request.data.get('person_type', 'person') or 'person'
        ).strip()

        mobile = str(
            request.data.get('mobile', '') or ''
        ).strip()

        description = str(
            request.data.get('description', '') or ''
        ).strip()

        is_active_value = request.data.get(
            'is_active',
            True
        )

        is_active = self.parse_boolean(is_active_value)

        # اعتبارسنجی نام
        if not name:
            return Response(
                {
                    'success': False,
                    'message': 'نام شخص یا مجموعه الزامی است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(name) > 200:
            return Response(
                {
                    'success': False,
                    'message': 'نام نمی‌تواند بیشتر از ۲۰۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی نوع شخص
        if person_type not in ['person', 'company']:
            return Response(
                {
                    'success': False,
                    'message': 'نوع شخص نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی شماره تماس
        if len(mobile) > 20:
            return Response(
                {
                    'success': False,
                    'message': 'شماره تماس نمی‌تواند بیشتر از ۲۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی توضیحات
        if len(description) > 500:
            return Response(
                {
                    'success': False,
                    'message': 'توضیحات نمی‌تواند بیشتر از ۵۰۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی وضعیت
        if is_active is None:
            return Response(
                {
                    'success': False,
                    'message': 'وضعیت فعال یا غیرفعال نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # بررسی نام تکراری در همین ساختمان
        if ThirdParty.objects.filter(
                house=house,
                name=name
        ).exists():
            return Response(
                {
                    'success': False,
                    'message': 'شخص یا مجموعه‌ای با این نام قبلاً در این ساختمان ثبت شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # استفاده از atomic داخلی برای مدیریت IntegrityError
            with transaction.atomic():

                third_party = ThirdParty.objects.create(
                    house=house,
                    name=name,
                    person_type=person_type,
                    mobile=mobile or None,
                    description=description or None,
                    is_active=is_active
                )

        except IntegrityError:
            return Response(
                {
                    'success': False,
                    'message': 'شخص یا مجموعه‌ای با این نام قبلاً در این ساختمان ثبت شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ManagerThirdPartySerializer(
            third_party
        )

        return Response(
            {
                'success': True,
                'message': 'شخص ثالث با موفقیت ثبت شد.',
                'third_party': serializer.data
            },
            status=status.HTTP_201_CREATED
        )
class ManagerThirdPartyDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    # =====================================================
    # دریافت ساختمان فعال مدیر
    # =====================================================

    def get_house(self, user):
        return MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

    # =====================================================
    # بررسی دسترسی
    # =====================================================

    def check_manager(self, request):

        if not request.user.is_middle_admin:
            return None, Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        house = self.get_house(request.user)

        if not house:
            return None, Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        return house, None

    # =====================================================
    # دریافت شخص ثالث متعلق به ساختمان مدیر
    # =====================================================

    def get_third_party(self, house, pk):

        return ThirdParty.objects.filter(
            id=pk,
            house=house
        ).first()

    # =====================================================
    # تبدیل مقدار فعال / غیرفعال
    # =====================================================

    def parse_boolean(self, value):

        if isinstance(value, bool):
            return value

        value = str(value).strip().lower()

        if value in ['true', '1', 'yes', 'on']:
            return True

        if value in ['false', '0', 'no', 'off']:
            return False

        return None

    # =====================================================
    # ویرایش شخص ثالث
    # =====================================================

    @transaction.atomic
    def put(self, request, pk):

        house, error = self.check_manager(request)

        if error:
            return error

        third_party = self.get_third_party(
            house,
            pk
        )

        if not third_party:
            return Response(
                {
                    'success': False,
                    'message': 'شخص ثالث مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        name = str(
            request.data.get(
                'name',
                third_party.name
            ) or ''
        ).strip()

        person_type = str(
            request.data.get(
                'person_type',
                third_party.person_type
            ) or ''
        ).strip()

        mobile = str(
            request.data.get(
                'mobile',
                third_party.mobile or ''
            ) or ''
        ).strip()

        description = str(
            request.data.get(
                'description',
                third_party.description or ''
            ) or ''
        ).strip()

        # اعتبارسنجی نام
        if not name:
            return Response(
                {
                    'success': False,
                    'message': 'نام شخص یا مجموعه الزامی است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if len(name) > 200:
            return Response(
                {
                    'success': False,
                    'message': 'نام نمی‌تواند بیشتر از ۲۰۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی نوع شخص
        if person_type not in ['person', 'company']:
            return Response(
                {
                    'success': False,
                    'message': 'نوع شخص نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی شماره تماس
        if len(mobile) > 20:
            return Response(
                {
                    'success': False,
                    'message': 'شماره تماس نمی‌تواند بیشتر از ۲۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی توضیحات
        if len(description) > 500:
            return Response(
                {
                    'success': False,
                    'message': 'توضیحات نمی‌تواند بیشتر از ۵۰۰ کاراکتر باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # بررسی نام تکراری در همان ساختمان
        duplicate = ThirdParty.objects.filter(
            house=house,
            name=name
        ).exclude(
            id=third_party.id
        ).exists()

        if duplicate:
            return Response(
                {
                    'success': False,
                    'message': 'شخص یا مجموعه دیگری با این نام در این ساختمان ثبت شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # بررسی وضعیت فعال / غیرفعال
        if 'is_active' in request.data:

            is_active = self.parse_boolean(
                request.data.get('is_active')
            )

            if is_active is None:
                return Response(
                    {
                        'success': False,
                        'message': 'وضعیت فعال یا غیرفعال نامعتبر است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            third_party.is_active = is_active

        try:
            with transaction.atomic():

                third_party.name = name
                third_party.person_type = person_type
                third_party.mobile = mobile or None
                third_party.description = description or None

                third_party.save()

        except IntegrityError:
            return Response(
                {
                    'success': False,
                    'message': 'شخص یا مجموعه‌ای با این نام در این ساختمان ثبت شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ManagerThirdPartySerializer(
            third_party
        )

        return Response(
            {
                'success': True,
                'message': 'اطلاعات شخص ثالث با موفقیت ویرایش شد.',
                'third_party': serializer.data
            },
            status=status.HTTP_200_OK
        )

    # =====================================================
    # حذف شخص ثالث
    # =====================================================

    @transaction.atomic
    def delete(self, request, pk):

        house, error = self.check_manager(request)

        if error:
            return error

        third_party = self.get_third_party(
            house,
            pk
        )

        if not third_party:
            return Response(
                {
                    'success': False,
                    'message': 'شخص ثالث مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        used_in_documents = []

        # بررسی تمام مدل‌های پروژه
        for model in apps.get_models():

            if model == ThirdParty:
                continue

            for field in model._meta.get_fields():

                # فقط ForeignKeyهای واقعی به ThirdParty
                if not getattr(field, 'many_to_one', False):
                    continue

                if getattr(field, 'related_model', None) != ThirdParty:
                    continue

                # بررسی وجود رکورد مرتبط
                exists = model.objects.filter(
                    **{
                        field.attname: third_party.id
                    }
                ).exists()

                if exists:
                    used_in_documents.append(
                        str(model._meta.verbose_name)
                    )
                    break

        # جلوگیری از حذف شخص ثالث استفاده‌شده
        if used_in_documents:
            return Response(
                {
                    'success': False,
                    'message': (
                        'این شخص ثالث در اسناد مالی استفاده شده است '
                        'و امکان حذف آن وجود ندارد.'
                    ),
                    'used_in_documents': list(
                        set(used_in_documents)
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        third_party.delete()

        return Response(
            {
                'success': True,
                'message': 'شخص ثالث با موفقیت حذف شد.'
            },
            status=status.HTTP_200_OK
        )
def sewage_api_error(message, status=400):
    return Response(
        {
            "success": False,
            "message": message,
        },
        status=status,
    )
def sewage_get_manager_charge(user, sewage_id):
    return SewageManage.objects.filter(
        pk=sewage_id,
        user=user,
        house__isnull=False,
    ).first()
def sewage_get_manager_unit(user, unit_id, house=None):
    units = Unit.objects.filter(
        pk=unit_id,
        user__manager=user,
        is_active=True,
    )

    if house is not None:
        units = units.filter(myhouse=house)

    return units.first()
def sewage_installment_is_previous_paid(installment):
    """
    قسط شماره صفر پیش‌پرداخت است.
    پرداخت اقساط بعدی فقط بعد از پرداخت قسط قبلی مجاز است.
    """
    if installment.installment_number == 0:
        return True

    previous = SewageInstallment.objects.filter(
        sewage_manage=installment.sewage_manage,
        unit=installment.unit,
        installment_number=installment.installment_number - 1,
    ).first()

    return previous is None or previous.is_paid
def sewage_serialize_installment(installment):
    return {
        "id": installment.id,
        "sewage_id": installment.sewage_manage_id,
        "unit_id": installment.unit_id,
        "installment_number": installment.installment_number,
        "amount": installment.amount,
        "prepayment_per_unit": installment.prepayment_per_unit,
        "due_date": (
            installment.due_date.isoformat()
            if installment.due_date else None
        ),
        "is_paid": installment.is_paid,
        "payment_pending": installment.payment_pending,
        "payment_date": (
            installment.payment_date.isoformat()
            if installment.payment_date else None
        ),
        "transaction_reference": (
            str(installment.transaction_reference)
            if installment.transaction_reference is not None else ""
        ),
        "send_notification": installment.send_notification,
        "can_pay": (
                not installment.is_paid
                and not installment.payment_pending
                and sewage_installment_is_previous_paid(installment)
        ),
    }
class ManagerSewageChargesListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return sewage_api_error(
                "شما اجازه دسترسی به این بخش را ندارید.",
                403,
            )

        charges = SewageManage.objects.filter(
            user=user,
            house__isnull=False,
        ).order_by("-created_at")

        search = request.query_params.get("q", "").strip()

        if search:
            query = (
                    Q(name__icontains=search)
                    | Q(details__icontains=search)
            )

            if search.isdigit():
                query |= (
                        Q(amount__icontains=search)
                        | Q(prepayment__icontains=search)
                        | Q(installment_count__icontains=search)
                )

            charges = charges.filter(query)

        try:
            page = max(int(request.query_params.get("page", 1)), 1)
            page_size = min(
                max(int(request.query_params.get("page_size", 20)), 1),
                100,
            )
        except (ValueError, TypeError):
            return sewage_api_error(
                "شماره صفحه یا اندازه صفحه معتبر نیست."
            )

        total = charges.count()
        start = (page - 1) * page_size

        results = []

        for sewage in charges[start:start + page_size]:
            installments = SewageInstallment.objects.filter(
                sewage_manage=sewage,
            )

            results.append({
                "id": sewage.id,
                "name": sewage.name,
                "amount": sewage.amount,
                "prepayment": sewage.prepayment,
                "installment_count": sewage.installment_count,
                "first_due_date": (
                    sewage.first_due_date.isoformat()
                    if sewage.first_due_date else None
                ),
                "details": sewage.details or "",
                "created_at": (
                    sewage.created_at.isoformat()
                    if sewage.created_at else None
                ),
                "is_active": sewage.is_active,

                "unit_count": installments.values(
                    "unit_id"
                ).distinct().count(),

                "paid_installment_count": installments.filter(
                    is_paid=True
                ).count(),

                "unpaid_installment_count": installments.filter(
                    is_paid=False
                ).count(),

                "pending_installment_count": installments.filter(
                    payment_pending=True,
                    is_paid=False,
                ).count(),
            })

        return Response({
            "success": True,
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": results,
        })
class ManagerSewageChargeUnitsListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, sewage_id):
        sewage = sewage_get_manager_charge(
            request.user,
            sewage_id,
        )

        if not sewage:
            return sewage_api_error(
                "هزینه فاضلاب پیدا نشد.",
                404,
            )

        unit_ids = (
            SewageInstallment.objects.filter(
                sewage_manage=sewage,
                send_notification=True,
                unit__isnull=False,
                unit__is_active=True,
                unit__user__manager=request.user,
                unit__myhouse=sewage.house,
            )
            .values_list("unit_id", flat=True)
            .distinct()
        )

        units = Unit.objects.filter(
            id__in=unit_ids,
            is_active=True,
            user__manager=request.user,
            myhouse=sewage.house,
        ).order_by("unit")

        search = request.query_params.get("q", "").strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(owner_mobile__icontains=search)
                | Q(
                    renters__renter_name__icontains=search,
                    renters__renter_is_active=True,
                )
            ).distinct()

        results = []

        for unit in units:
            all_installments = list(
                SewageInstallment.objects.filter(
                    sewage_manage=sewage,
                    unit=unit,
                    send_notification=True,
                ).order_by("installment_number", "id")
            )

            prepayment_installments = [
                item for item in all_installments
                if item.installment_number == 0
            ]

            installments = [
                item for item in all_installments
                if item.installment_number > 0
            ]

            prepayment = next(
                (
                    item.amount or item.prepayment_per_unit or 0
                    for item in prepayment_installments
                ),
                0,
            )

            if not prepayment:
                prepayment = sewage.prepayment or 0

            has_prepayment_installment = bool(
                prepayment_installments
            )

            prepayment_is_paid = any(
                item.is_paid
                for item in prepayment_installments
            )

            paid_installments = [
                item for item in installments
                if item.is_paid
            ]

            unpaid_installments = [
                item for item in installments
                if not item.is_paid
            ]

            installments_total_amount = sum(
                item.amount or 0
                for item in installments
            )

            total_charge_amount = (
                    prepayment + installments_total_amount
            )

            paid_amount = sum(
                item.amount or 0
                for item in paid_installments
            )

            unpaid_amount = sum(
                item.amount or 0
                for item in unpaid_installments
            )

            if has_prepayment_installment:
                if prepayment_is_paid:
                    paid_amount += prepayment
                else:
                    unpaid_amount += prepayment

            total_installments = (
                    len(installments)
                    + (1 if has_prepayment_installment else 0)
            )

            paid_count = (
                    len(paid_installments)
                    + (
                        1
                        if has_prepayment_installment
                           and prepayment_is_paid
                        else 0
                    )
            )

            unpaid_count = total_installments - paid_count

            active_renter = unit.get_active_renter()

            if active_renter:
                resident_type = "renter"
                resident_type_display = "مستأجر"
                resident_name = (
                        active_renter.renter_name or "نامشخص"
                )
                active_tenant_name = (
                        active_renter.renter_name or ""
                )
            else:
                resident_type = "owner"
                resident_type_display = "مالک"
                resident_name = unit.owner_name or "نامشخص"
                active_tenant_name = ""

            results.append({
                "id": unit.id,
                "unit": unit.unit,

                "owner_name": unit.owner_name or "",
                "owner_mobile": unit.owner_mobile or "",

                "resident_type": resident_type,
                "resident_type_display": resident_type_display,
                "resident_name": resident_name,
                "active_tenant_name": active_tenant_name,

                "prepayment": prepayment,
                "installments_total_amount": (
                    installments_total_amount
                ),
                "amount": total_charge_amount,
                "total_charge_amount": total_charge_amount,
                "paid_amount": paid_amount,
                "unpaid_amount": unpaid_amount,
                "remaining_installments_amount": unpaid_amount,

                "paid_count": paid_count,
                "total_installments": total_installments,
                "unpaid_count": unpaid_count,

                "installments": [
                    sewage_serialize_installment(item)
                    for item in installments
                ],
            })

        return Response({
            "success": True,
            "sewage_id": sewage.id,
            "sewage_name": sewage.name,
            "count": len(results),
            "results": results,
        })
class ManagerSewageUnitInstallmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, sewage_id, unit_id):
        sewage = sewage_get_manager_charge(
            request.user,
            sewage_id,
        )

        if not sewage:
            return sewage_api_error(
                "هزینه فاضلاب پیدا نشد.",
                404,
            )

        unit = sewage_get_manager_unit(
            request.user,
            unit_id,
            house=sewage.house,
        )

        if not unit:
            return sewage_api_error(
                "واحد پیدا نشد.",
                404,
            )

        installments = SewageInstallment.objects.filter(
            sewage_manage=sewage,
            unit=unit,
            send_notification=True,
        ).order_by("installment_number", "id")

        return Response({
            "success": True,
            "sewage": {
                "id": sewage.id,
                "name": sewage.name,
            },
            "unit": {
                "id": unit.id,
                "unit": unit.unit,
                "owner_name": unit.owner_name or "",
            },
            "count": installments.count(),
            "paid_count": installments.filter(
                is_paid=True
            ).count(),
            "unpaid_count": installments.filter(
                is_paid=False
            ).count(),
            "results": [
                sewage_serialize_installment(item)
                for item in installments
            ],
        })
class ManagerSewageInstallmentPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, installment_id):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return sewage_api_error(
                "دسترسی غیرمجاز.",
                403,
            )

        installment = SewageInstallment.objects.filter(
            pk=installment_id,
            sewage_manage__user=user,
            sewage_manage__house__isnull=False,
            unit__user__manager=user,
            unit__myhouse=F("sewage_manage__house"),
        ).select_related(
            "sewage_manage",
            "unit",
            "sewage_manage__house",
        ).first()

        if not installment:
            return sewage_api_error(
                "قسط فاضلاب پیدا نشد.",
                404,
            )

        if not installment.send_notification:
            return sewage_api_error(
                "این قسط هنوز برای واحد ارسال نشده است."
            )

        if installment.is_paid:
            return sewage_api_error(
                "این قسط قبلاً پرداخت شده است."
            )

        if installment.payment_pending:
            return sewage_api_error(
                "این قسط در انتظار تأیید پرداخت است."
            )

        if not sewage_installment_is_previous_paid(installment):
            return sewage_api_error(
                "ابتدا باید قسط قبلی پرداخت شود."
            )

        banks = Bank.objects.filter(
            is_active=True,
            house=installment.sewage_manage.house,
        ).order_by("-is_default", "bank_name")

        return Response({
            "success": True,
            "installment": sewage_serialize_installment(
                installment
            ),
            "banks": [
                {
                    "id": bank.pk,
                    "bank_name": bank.bank_name,
                    "account_no": bank.account_no,
                    "cart_number": bank.cart_number,
                    "is_default": bank.is_default,
                }
                for bank in banks
            ],
        })

    def post(self, request, installment_id):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return sewage_api_error(
                "دسترسی غیرمجاز.",
                403,
            )

        installment = SewageInstallment.objects.filter(
            pk=installment_id,
            sewage_manage__user=user,
            sewage_manage__house__isnull=False,
            unit__user__manager=user,
            unit__myhouse=F("sewage_manage__house"),
        ).select_related(
            "sewage_manage",
            "unit",
            "sewage_manage__house",
        ).first()

        if not installment:
            return sewage_api_error(
                "قسط فاضلاب پیدا نشد.",
                404,
            )

        if not installment.send_notification:
            return sewage_api_error(
                "این قسط برای واحد ارسال نشده است."
            )

        try:
            bank_id = int(request.data.get("bank_id"))
        except (ValueError, TypeError):
            return sewage_api_error(
                "حساب بانکی معتبر انتخاب کنید."
            )

        bank = Bank.objects.filter(
            pk=bank_id,
            house=installment.sewage_manage.house,
            is_active=True,
        ).first()

        if not bank:
            return sewage_api_error(
                "حساب بانکی معتبر برای این ساختمان پیدا نشد."
            )

        raw_date = request.data.get("payment_date")

        if raw_date:
            try:
                payment_date = datetime.date.fromisoformat(
                    str(raw_date)[:10]
                )
            except (ValueError, TypeError):
                return sewage_api_error(
                    "تاریخ پرداخت باید به قالب YYYY-MM-DD باشد."
                )
        else:
            payment_date = date.today()

        if payment_date > date.today():
            return sewage_api_error(
                "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
            )

        transaction_reference = str(
            request.data.get("transaction_reference") or ""
        ).strip()

        if len(transaction_reference) > 20:
            return sewage_api_error(
                "شماره پیگیری نمی‌تواند بیشتر از ۲۰ کاراکتر باشد."
            )

        try:
            validate_bank_transaction_date(
                bank,
                payment_date,
            )
        except Exception as exc:
            return sewage_api_error(str(exc))

        with transaction.atomic():

            installment = (
                SewageInstallment.objects
                .select_for_update()
                .filter(
                    pk=installment_id,
                    sewage_manage__user=user,
                    sewage_manage__house__isnull=False,
                    unit__user__manager=user,
                    unit__myhouse=F("sewage_manage__house"),
                )
                .select_related(
                    "sewage_manage",
                    "unit",
                    "sewage_manage__house",
                )
                .first()
            )

            if not installment:
                return sewage_api_error(
                    "قسط پیدا نشد.",
                    404,
                )

            if installment.is_paid:
                return sewage_api_error(
                    "این قسط قبلاً پرداخت شده است."
                )

            if installment.payment_pending:
                return sewage_api_error(
                    "این قسط در انتظار تأیید پرداخت است."
                )

            if not installment.send_notification:
                return sewage_api_error(
                    "این قسط برای واحد ارسال نشده است."
                )

            if not sewage_installment_is_previous_paid(
                    installment
            ):
                return sewage_api_error(
                    "ابتدا باید قسط قبلی پرداخت شود."
                )

            # کنترل حساب بانکی در داخل تراکنش
            bank = Bank.objects.filter(
                pk=bank_id,
                house=installment.sewage_manage.house,
                is_active=True,
            ).first()

            if not bank:
                return sewage_api_error(
                    "حساب بانکی معتبر پیدا نشد."
                )

            content_type = ContentType.objects.get_for_model(
                SewageInstallment
            )

            existing_fund = Fund.objects.filter(
                content_type=content_type,
                object_id=installment.pk,
            ).exists()

            if existing_fund:
                return sewage_api_error(
                    "برای این قسط سند مالی وجود دارد؛ "
                    "ابتدا وضعیت آن را بررسی کنید."
                )

            unit = installment.unit
            house = installment.sewage_manage.house

            owner_name = (
                    unit.owner_name or ""
            ).strip()

            payer_name_snapshot = (
                f"واحد {unit.unit} - {owner_name}"
                if owner_name
                else f"واحد {unit.unit}"
            )

            payment_description = (
                f"پرداخت هزینه فاضلاب: "
                f"{(installment.sewage_manage.name or '')[:50]}"
            )

            installment.bank = bank
            installment.is_paid = True
            installment.payment_date = payment_date
            installment.transaction_reference = (
                    transaction_reference or None
            )
            installment.payment_gateway = "پرداخت الکترونیک"
            installment.payment_pending = False

            installment.save(update_fields=[
                "bank",
                "is_paid",
                "payment_date",
                "transaction_reference",
                "payment_gateway",
                "payment_pending",
            ])

            Fund.objects.create(
                content_type=content_type,
                object_id=installment.id,
                unit=unit,
                house=house,
                bank=bank,
                payer_type="owner",
                payer_renter=None,
                payer_name=payer_name_snapshot,
                debtor_amount=installment.amount,
                amount=installment.amount,
                creditor_amount=0,
                user=user,
                is_paid=True,
                payment_date=installment.payment_date,
                payment_description=payment_description,
                transaction_no=installment.transaction_reference,
                financial_document_number=(
                    installment.financial_document_number
                ),
                payment_gateway="پرداخت الکترونیک",
            )

            BankTransactionService.deposit(
                user=user,
                bank=bank,
                unit=unit,
                amount=Decimal(installment.amount),
                description=payment_description,
                payer_type="owner",
                payer_renter=None,
                payer_name=owner_name or None,
                content_object=installment,
                payment_date=installment.payment_date,
                financial_document_number=(
                    installment.financial_document_number
                ),
                transaction_no=installment.transaction_reference,
                gateway="پرداخت الکترونیک",
                house=house,
            )

        return Response({
            "success": True,
            "message": "پرداخت هزینه فاضلاب با موفقیت ثبت شد.",
            "installment": sewage_serialize_installment(
                installment
            ),
        })
class ManagerSewageInstallmentCancelPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, installment_id):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return sewage_api_error(
                "دسترسی غیرمجاز.",
                403,
            )

        with transaction.atomic():
            installment = (
                SewageInstallment.objects
                .select_for_update()
                .filter(
                    pk=installment_id,
                    sewage_manage__user=user,
                    sewage_manage__house__isnull=False,
                    unit__user__manager=user,
                    unit__myhouse=F("sewage_manage__house"),
                )
                .select_related(
                    "sewage_manage",
                    "unit",
                    "sewage_manage__house",
                )
                .first()
            )

            if not installment:
                return sewage_api_error(
                    "قسط فاضلاب پیدا نشد.",
                    404,
                )

            if not installment.is_paid:
                return sewage_api_error(
                    "این قسط پرداخت نشده است."
                )

            content_type = ContentType.objects.get_for_model(
                SewageInstallment
            )

            fund = Fund.objects.filter(
                content_type=content_type,
                object_id=installment.id,
            ).first()

            if not fund:
                return sewage_api_error(
                    "سند مالی مرتبط با این پرداخت پیدا نشد."
                )

            bank_fund = BankFund.objects.filter(
                content_type=content_type,
                object_id=installment.id,
            ).select_related("bank").first()

            if bank_fund:
                bank = bank_fund.bank
                amount = bank_fund.amount or 0

                if bank_fund.transaction_type == "deposit":
                    bank.current_balance -= amount
                else:
                    bank.current_balance += amount

                bank.save(
                    update_fields=["current_balance"]
                )

                bank_fund.delete()

            fund_doc_number = fund.doc_number
            fund.delete()

            next_fund = (
                Fund.objects
                .filter(doc_number__gt=fund_doc_number)
                .order_by("doc_number")
                .first()
            )

            if next_fund:
                Fund.recalc_final_amounts_from(next_fund)

            installment.is_paid = False
            installment.bank = None
            installment.transaction_reference = None
            installment.payment_date = None
            installment.payment_gateway = None
            installment.payment_pending = False

            installment.save(update_fields=[
                "is_paid",
                "bank",
                "transaction_reference",
                "payment_date",
                "payment_gateway",
                "payment_pending",
            ])

        return Response({
            "success": True,
            "message": "پرداخت لغو شد و وضعیت مالی اصلاح شد.",
            "installment": sewage_serialize_installment(
                installment
            ),
        })
