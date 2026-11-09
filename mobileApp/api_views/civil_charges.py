"""Civil Charges API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class CivilChargeListAPIView(APIView):
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
            CivilManage.objects.filter(
                house=house,
                is_active=True,
            )
            .annotate(
                sent_units_count=Count(
                    'installments__unit',
                    filter=Q(
                        installments__send_notification=True
                    ),
                    distinct=True,
                ),
            )
            .filter(
                sent_units_count__gt=0
            )
            .order_by('id')
        )

        serializer = CivilManageSerializer(
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
class CivilChargeInstallmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, civil_id):

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
            civil = CivilManage.objects.get(
                id=civil_id,
                house=house,
                is_active=True,
            )
        except CivilManage.DoesNotExist:

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
            CivilInstallment.objects.filter(
                civil_manage=civil,
                unit=unit,
            )
            .select_related(
                'unit',
                'civil_manage',
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

        serializer = CivilInstallmentSerializer(
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

                'civil': {
                    'id': civil.id,
                    'name': civil.name,
                    'amount': civil.amount,
                    'prepayment': civil.prepayment,
                    'installment_count': civil.installment_count,
                    'first_due_date': civil.first_due_date,
                    'details': civil.details,
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
class CivilChargePaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, installment_id):

        installment = (
            CivilInstallment.objects
            .filter(
                id=installment_id,
                civil_manage__is_active=True,
            )
            .select_related(
                'unit',
                'house',
                'civil_manage',
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
                    'civil_id': installment.civil_manage_id,
                    'civil_name': installment.civil_manage.name,
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
class ManualCivilPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, installment_id):

        serializer = ManualCivilPaymentSerializer(
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
            CivilInstallment.objects
            .select_for_update()
            .select_related(
                'unit',
                'house',
                'civil_manage',
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

                    'civil_id': (
                        installment.civil_manage_id
                    ),

                    'civil_name': (
                        installment.civil_manage.name
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
def civil_normalize_digits(value):
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
def civil_parse_date(value):
    """
    ورودی قابل قبول:
    2026-10-22
    1405-07-30
    تاریخ با ارقام فارسی
    """
    if not value:
        return None

    value = civil_normalize_digits(value)

    try:
        year, month, day = map(int, value.split("-"))

        if 1200 <= year <= 1600:
            jalali_date = jdatetime.date(year, month, day)
            return jalali_date.togregorian()

        if 1900 <= year <= 2200:
            return date(year, month, day)

    except (ValueError, TypeError):
        return None

    return None
def civil_get_eligible_units(civil, user):
    """واحدهای فعال و مشمول بر اساس unit_scope؛ معیار سکونت فقط status_residence است."""
    units = Unit.objects.filter(
        is_active=True,
        user__manager=user,
        myhouse=civil.house,
    )
    if civil.unit_scope == "occupied":
        units = units.filter(status_residence="occupied")
    elif civil.unit_scope == "vacant":
        units = units.filter(status_residence="empty")
    return units.order_by("unit")
def civil_get_unit_scope_display(unit_scope):
    return {
        "all": "همه واحدها",
        "occupied": "واحدهای ساکن‌دار",
        "vacant": "واحدهای خالی",
    }.get(unit_scope, "نامشخص")
def civil_prepare_installments(civil, user):
    """اقساط را برای واحدهای مشمول ایجاد می‌کند؛ اعلان ارسال نمی‌کند."""
    units = list(civil_get_eligible_units(civil, user))
    count = len(units)
    if count == 0:
        raise ValueError("هیچ واحد فعالی در محدوده انتخاب‌شده برای شارژ وجود ندارد.")

    total = int(civil.amount or 0)
    prepayment_total = int(civil.prepayment or 0)
    installment_count = int(civil.installment_count or 0)
    if total <= 0:
        raise ValueError("مبلغ شارژ باید بیشتر از صفر باشد.")
    if prepayment_total < 0 or prepayment_total > total:
        raise ValueError("مبلغ پیش‌پرداخت معتبر نیست.")
    if installment_count < 0:
        raise ValueError("تعداد اقساط نمی‌تواند منفی باشد.")
    if installment_count == 0 and prepayment_total not in (0, total):
        raise ValueError(
            "برای مبلغ باقی‌مانده، تعداد اقساط باید بیشتر از صفر باشد؛ برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید.")

    # تقسیم باقیمانده نیز حفظ می‌شود تا مجموع سهم واحدها دقیقاً برابر مبلغ کل باشد.
    total_base, total_extra = divmod(total, count)
    pre_base, pre_extra = divmod(prepayment_total, count)
    base_date = civil.first_due_date or timezone.localdate()
    created_units = 0
    created_rows = 0

    with transaction.atomic():
        for index, unit in enumerate(units):
            existing = CivilInstallment.objects.filter(civil_manage=civil, unit=unit)
            if existing.exists():
                continue

            unit_total = total_base + (1 if index < total_extra else 0)
            unit_prepayment = pre_base + (1 if index < pre_extra else 0)
            remaining = unit_total - unit_prepayment
            if remaining < 0:
                raise ValueError("پیش‌پرداخت هر واحد نمی‌تواند از سهم شارژ آن بیشتر باشد.")

            rows = []
            if installment_count == 0 and unit_prepayment == 0:
                rows.append(CivilInstallment(
                    civil_manage=civil, house=civil.house, unit=unit,
                    installment_number=1, amount=unit_total,
                    prepayment_per_unit=0, due_date=base_date,
                    financial_document_number=get_next_financial_document_number(civil.house),
                    send_notification=False, send_notification_date=None,
                ))
            else:
                if unit_prepayment > 0:
                    rows.append(CivilInstallment(
                        civil_manage=civil, house=civil.house, unit=unit,
                        installment_number=0, amount=unit_prepayment,
                        prepayment_per_unit=unit_prepayment, due_date=base_date,
                        financial_document_number=get_next_financial_document_number(civil.house),
                        send_notification=False, send_notification_date=None,
                    ))
                if remaining > 0:
                    if installment_count <= 0:
                        raise ValueError("تعداد اقساط برای مبلغ باقی‌مانده معتبر نیست.")
                    regular, extra = divmod(remaining, installment_count)
                    for number in range(1, installment_count + 1):
                        installment_amount = regular + (1 if number <= extra else 0)
                        rows.append(CivilInstallment(
                            civil_manage=civil, house=civil.house, unit=unit,
                            installment_number=number, amount=installment_amount,
                            prepayment_per_unit=0,
                            due_date=base_date + relativedelta(months=number),
                            financial_document_number=get_next_financial_document_number(civil.house),
                            send_notification=False, send_notification_date=None,
                        ))
            if rows:
                CivilInstallment.objects.bulk_create(rows)
                created_units += 1
                created_rows += len(rows)

    return {
        "eligible_unit_count": count,
        "created_units_count": created_units,
        "created_installments_count": created_rows,
        "share_per_unit": total // count,
        "prepayment_per_unit": prepayment_total // count,
        "installment_amount_per_unit": (
                (total - prepayment_total) // count // installment_count) if installment_count else 0,
    }
def civil_serialize(civil, request):
    documents = []

    for doc in civil.civil_documents.all():
        if doc.document:
            documents.append({
                "id": doc.id,
                "url": request.build_absolute_uri(doc.document.url),
                "uploaded_at": doc.uploaded_at.isoformat(),
            })

    eligible_count = civil_get_eligible_units(civil, civil.user).count()
    return {
        "id": civil.id,
        "name": civil.name,
        "amount": civil.amount,
        "prepayment": civil.prepayment,
        "installment_count": civil.installment_count,
        "unit_scope": civil.unit_scope,
        "unit_scope_display": civil_get_unit_scope_display(civil.unit_scope),
        "first_due_date": civil.first_due_date.isoformat() if civil.first_due_date else None,
        "details": civil.details or "",
        "is_active": civil.is_active,
        "created_at": civil.created_at.isoformat(),
        "documents": documents,
        "sent_units_count": civil.count_sent_units(),
        "fully_paid_units_count": civil.count_fully_paid_units(),
        "eligible_unit_count": eligible_count,
        # برای سازگاری با نسخه فعلی اپ حفظ شده است.
        "total_unit_count": eligible_count,
        "is_sent": civil.count_sent_units() > 0,
    }
def get_deleted_document_ids(request):
    """
    دریافت شناسه مدارک حذف‌شده از درخواست Multipart.
    فرمت‌های قابل قبول:
    [1, 2]
    "1,2"
    ["1", "2"]
    """

    try:
        if hasattr(request.data, "getlist"):
            values = request.data.getlist("deleted_document_ids")
        else:
            values = request.data.get("deleted_document_ids", [])

        if not values:
            return []

        # اگر چند مقدار جداگانه ارسال شده باشد
        if isinstance(values, list) and len(values) > 1:
            raw_ids = values
        else:
            raw = values[0] if isinstance(values, list) else values

            if raw in (None, ""):
                return []

            if isinstance(raw, list):
                raw_ids = raw
            else:
                raw = str(raw).strip()

                try:
                    parsed = json.loads(raw)
                    raw_ids = parsed if isinstance(parsed, list) else [parsed]
                except (json.JSONDecodeError, TypeError):
                    raw_ids = raw.split(",")

        result = []

        for value in raw_ids:
            if value in (None, ""):
                continue

            document_id = int(value)

            if document_id <= 0:
                raise ValueError

            if document_id not in result:
                result.append(document_id)

        return result

    except (ValueError, TypeError):
        raise ValueError("شناسه مدارک حذف‌شده معتبر نیست.")
class ManagerCivilChargesAPIView(APIView):
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

        civils = (
            CivilManage.objects.filter(
                user=request.user,
                house=house,
            )
            .prefetch_related("civil_documents")
            .order_by("-created_at")
        )

        return Response({
            "success": True,
            "count": civils.count(),
            "results": [
                civil_serialize(civil, request)
                for civil in civils
            ],
        }, status=status.HTTP_200_OK)

    def post(self, request):
        house = self.get_house(request)
        if not house:
            return Response({"success": False, "message": "ساختمان فعالی برای مدیر پیدا نشد."},
                            status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist("document")
        if len(files) > 2:
            return Response({"success": False, "message": "حداکثر دو فایل مجاز است."},
                            status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        parsed_date = civil_parse_date(data.get("first_due_date"))
        if not parsed_date:
            return Response({"success": False, "message": "تاریخ اولین سررسید معتبر نیست.",
                             "errors": {"first_due_date": ["تاریخ را به صورت YYYY-MM-DD وارد کنید."]}},
                            status=status.HTTP_400_BAD_REQUEST)
        data["first_due_date"] = jdatetime.date.fromgregorian(date=parsed_date).strftime("%Y-%m-%d")
        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0
        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = CivilForm(data=data, files=request.FILES)
        if not form.is_valid():
            return Response(
                {"success": False, "message": "اطلاعات شارژ عمرانی معتبر نیست.", "errors": form.errors.get_json_data()},
                status=status.HTTP_400_BAD_REQUEST)

        amount = form.cleaned_data["amount"]
        prepayment = form.cleaned_data.get("prepayment") or 0
        installment_count = form.cleaned_data.get("installment_count") or 0
        if amount <= 0:
            return Response({"success": False, "message": "مبلغ شارژ باید بیشتر از صفر باشد."},
                            status=status.HTTP_400_BAD_REQUEST)
        if prepayment < 0 or prepayment > amount:
            return Response({"success": False, "message": "پیش‌پرداخت باید بین صفر و مبلغ شارژ باشد."},
                            status=status.HTTP_400_BAD_REQUEST)
        if installment_count < 0:
            return Response({"success": False, "message": "تعداد اقساط نمی‌تواند منفی باشد."},
                            status=status.HTTP_400_BAD_REQUEST)
        if installment_count == 0 and prepayment not in (0, amount):
            return Response({"success": False,
                             "message": "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر وارد کنید؛ برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                civil = form.save(commit=False)
                civil.user = request.user
                civil.house = house
                civil.prepayment = prepayment
                civil.installment_count = installment_count
                civil.save()
                for uploaded_file in files:
                    CivilDocument.objects.create(civil=civil, document=uploaded_file)
                calculation = civil_prepare_installments(civil, request.user)
        except ValueError as exc:
            return Response({"success": False, "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Creating civil charge/installments failed")
            return Response({"success": False, "message": "ثبت شارژ و محاسبه اقساط انجام نشد."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = civil_serialize(civil, request)
        result["calculation"] = calculation
        return Response({"success": True, "message": "شارژ عمرانی ثبت و اقساط آن محاسبه شد.", "result": result},
                        status=status.HTTP_201_CREATED)
class ManagerCivilChargeDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_civil(self, request, civil_id):
        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None

        return (
            CivilManage.objects.filter(
                id=civil_id,
                user=request.user,
                house=house,
            )
            .prefetch_related("civil_documents")
            .first()
        )

    # =====================================================
    # دریافت جزئیات شارژ عمرانی
    # =====================================================

    def get(self, request, civil_id):
        civil = self.get_civil(request, civil_id)

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return Response({
            "success": True,
            "result": civil_serialize(civil, request),
        }, status=status.HTTP_200_OK)

    # =====================================================
    # ویرایش شارژ عمرانی و مدیریت مدارک
    # =====================================================

    def put(self, request, civil_id):
        civil = self.get_civil(request, civil_id)

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        existing = CivilInstallment.objects.filter(
            civil_manage=civil
        )

        if existing.filter(send_notification=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این شارژ قبلاً اعلان شده است و برای جلوگیری "
                    "از تغییر سوابق، قابل ویرایش نیست."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        if existing.filter(is_paid=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این شارژ دارای قسط پرداخت‌شده است و امکان "
                    "بازسازی اقساط آن وجود ندارد."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        # فایل‌های جدید
        files = request.FILES.getlist("document")

        # شناسه مدارک قبلی که مدیر قصد حذف آن‌ها را دارد
        try:
            deleted_ids = get_deleted_document_ids(request)
        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        # فقط مدارک متعلق به همین شارژ قابل حذف هستند
        documents_to_delete = list(
            civil.civil_documents.filter(
                id__in=deleted_ids
            )
        )

        valid_deleted_ids = {
            doc.id for doc in documents_to_delete
        }

        if valid_deleted_ids != set(deleted_ids):
            return Response({
                "success": False,
                "message": "بعضی از مدارک انتخاب‌شده معتبر نیستند.",
            }, status=status.HTTP_400_BAD_REQUEST)

        # حداکثر دو مدرک در مجموع
        current_documents_count = civil.civil_documents.count()

        remaining_documents_count = (
            current_documents_count - len(documents_to_delete)
        )

        total_documents_count = (
            remaining_documents_count + len(files)
        )

        if total_documents_count > 2:
            return Response({
                "success": False,
                "message": "حداکثر دو تصویر برای هر شارژ عمرانی مجاز است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        # =================================================
        # اعتبارسنجی اطلاعات فرم
        # =================================================

        data = QueryDict('', mutable=True)

        for key in request.data:
            values = request.data.getlist(key)

            for value in values:
                data.appendlist(key, value)

        raw_date = data.get("first_due_date")

        if raw_date:
            parsed_date = civil_parse_date(raw_date)

            if not parsed_date:
                return Response({
                    "success": False,
                    "message": "تاریخ اولین سررسید معتبر نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            data["first_due_date"] = (
                jdatetime.date
                .fromgregorian(date=parsed_date)
                .strftime("%Y-%m-%d")
            )

        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0

        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = CivilForm(
            data=data,
            files=request.FILES,
            instance=civil,
        )

        if not form.is_valid():
            return Response({
                "success": False,
                "message": "اطلاعات شارژ عمرانی معتبر نیست.",
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
                "message": "مبلغ شارژ باید بیشتر از صفر باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if prepayment < 0 or prepayment > amount:
            return Response({
                "success": False,
                "message": "پیش‌پرداخت باید بین صفر و مبلغ شارژ باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if installment_count < 0:
            return Response({
                "success": False,
                "message": "تعداد اقساط نمی‌تواند منفی باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if installment_count == 0 and prepayment not in (0, amount):
            return Response({
                "success": False,
                "message": (
                    "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر "
                    "وارد کنید؛ برای پرداخت یکجا پیش‌پرداخت و تعداد "
                    "اقساط را صفر بگذارید."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        # =================================================
        # ذخیره تغییرات
        # =================================================

        try:
            with transaction.atomic():

                # حذف اقساط قبلیِ ارسال‌نشده و پرداخت‌نشده
                CivilInstallment.objects.filter(
                    civil_manage=civil,
                    send_notification=False,
                    is_paid=False,
                ).delete()

                # حذف رکورد مدارک انتخاب‌شده
                for doc in documents_to_delete:
                    if doc.document:
                        storage = doc.document.storage
                        file_name = doc.document.name

                        def delete_file_after_commit(
                            storage=storage,
                            file_name=file_name,
                        ):
                            try:
                                storage.delete(file_name)
                            except Exception:
                                logger.exception(
                                    "Deleting civil document file failed: %s",
                                    file_name,
                                )

                        transaction.on_commit(
                            delete_file_after_commit
                        )

                    doc.delete()

                # ذخیره اطلاعات شارژ
                civil = form.save(commit=False)
                civil.prepayment = prepayment
                civil.installment_count = installment_count
                civil.save()

                # ذخیره تصاویر جدید
                for uploaded_file in files:
                    CivilDocument.objects.create(
                        civil=civil,
                        document=uploaded_file,
                    )

                # محاسبه مجدد اقساط
                calculation = civil_prepare_installments(
                    civil,
                    request.user,
                )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception:
            logger.exception(
                "Updating civil charge/installments failed"
            )

            return Response({
                "success": False,
                "message": "ویرایش شارژ و محاسبه مجدد اقساط انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = civil_serialize(civil, request)
        result["calculation"] = calculation

        return Response({
            "success": True,
            "message": "شارژ عمرانی و مدارک آن با موفقیت ویرایش شدند.",
            "result": result,
        }, status=status.HTTP_200_OK)

    # =====================================================
    # حذف کامل شارژ عمرانی
    # =====================================================

    def delete(self, request, civil_id):
        civil = self.get_civil(request, civil_id)

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        installments = CivilInstallment.objects.filter(
            civil_manage=civil
        )

        if installments.filter(is_paid=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این شارژ دارای قسط پرداخت‌شده است "
                    "و امکان حذف آن وجود ندارد."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        if installments.filter(send_notification=True).exists():
            return Response({
                "success": False,
                "message": (
                    "این شارژ برای واحدها ارسال شده است؛ "
                    "ابتدا وضعیت ارسال آن را بررسی کنید."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            civil.delete()

        except Exception:
            logger.exception("Deleting civil charge failed")

            return Response({
                "success": False,
                "message": "حذف شارژ عمرانی انجام نشد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "شارژ عمرانی حذف شد.",
        }, status=status.HTTP_200_OK)
class ManagerCivilChargeUnitsAPIView(APIView):
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

    def get(self, request, civil_id):
        civil = CivilManage.objects.filter(
            id=civil_id,
            user=request.user,
        ).first()

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        units = civil_get_eligible_units(civil, request.user).prefetch_related(
            Prefetch(
                "renters",
                queryset=Renter.objects.filter(renter_is_active=True),
                to_attr="active_renters_for_charge",
            )
        )

        results = []
        for unit in units:
            installment_rows = list(CivilInstallment.objects.filter(
                civil_manage=civil, unit=unit
            ).order_by("installment_number"))
            resident_info = self._get_unit_resident_info(unit)
            results.append({
                "id": unit.id,
                "unit": str(unit.unit),
                "resident_type": resident_info["resident_type"],
                "resident_name": resident_info["resident_name"],
                "people_count": resident_info["people_count"],
                "sent": any(item.send_notification for item in installment_rows),
                "has_paid_installment": any(item.is_paid for item in installment_rows),
                "installments": [
                    {
                        "id": item.id,
                        "installment_number": item.installment_number,
                        "amount": item.amount,
                        "due_date": item.due_date.isoformat() if item.due_date else None,
                        "send_notification": item.send_notification,
                        "is_paid": item.is_paid,
                    }
                    for item in installment_rows
                ],
            })

        return Response({
            "success": True,
            "civil_id": civil.id,
            "count": len(results),
            "results": results,
        })
class ManagerSendCivilChargeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, civil_id):
        civil = CivilManage.objects.filter(id=civil_id, user=request.user).first()
        if not civil:
            return Response({"success": False, "message": "شارژ عمرانی پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)

        raw_ids = request.data.get("unit_ids", [])
        if isinstance(raw_ids, str):
            try:
                raw_ids = json.loads(raw_ids)
            except (ValueError, TypeError):
                raw_ids = [item.strip() for item in raw_ids.split(",") if item.strip()]
        if not isinstance(raw_ids, list):
            raw_ids = []
        all_requested = str(request.data.get("all_units", "")).lower() in ("true", "1", "yes")
        units_qs = civil_get_eligible_units(civil, request.user)
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
            return Response({"success": False, "message": "هیچ واحد معتبری در محدوده این شارژ انتخاب نشده است."},
                            status=status.HTTP_400_BAD_REQUEST)

        sent_count = 0
        already_sent_count = 0
        paid_count = 0
        missing_count = 0
        try:
            with transaction.atomic():
                for unit in units:
                    installments = CivilInstallment.objects.filter(civil_manage=civil, unit=unit)
                    if not installments.exists():
                        missing_count += 1
                        continue
                    if installments.filter(send_notification=True).exists():
                        already_sent_count += 1
                        continue
                    if installments.filter(is_paid=True).exists():
                        paid_count += 1
                        continue
                    updated = installments.filter(send_notification=False).update(
                        send_notification=True,
                        send_notification_date=date.today(),
                    )
                    if updated:
                        sent_count += 1
        except Exception:
            import logging
            logging.getLogger(__name__).exception("Updating civil installment notification status failed")
            return Response({"success": False, "message": "ثبت وضعیت ارسال شارژ انجام نشد."},
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "وضعیت اعلان شارژ عمرانی ثبت شد.",
            "civil_id": civil.id,
            "sent_units_count": sent_count,
            "already_sent_units_count": already_sent_count,
            "missing_installments_count": missing_count,
            "skipped_paid_units_count": paid_count,
        }, status=status.HTTP_200_OK)
class ManagerCancelCivilChargeAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, civil_id):
        civil = CivilManage.objects.filter(
            id=civil_id,
            user=request.user,
        ).first()

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
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

        units_qs = Unit.objects.filter(
            is_active=True,
            user__manager=request.user,
        )

        if civil.house:
            units_qs = units_qs.filter(myhouse=civil.house)

        if all_units_requested:
            units = list(units_qs.order_by("unit"))
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
                ).order_by("unit")
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
                    installments = CivilInstallment.objects.filter(
                        civil_manage=civil,
                        unit=unit,
                        send_notification=True,
                    )

                    if not installments.exists():
                        skipped_unsent_units_count += 1
                        continue

                    # اگر هر قسطی پرداخت شده باشد، اعلان این واحد
                    # به‌طور کامل دست‌نخورده باقی می‌ماند.
                    if CivilInstallment.objects.filter(
                            civil_manage=civil,
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
                "Cancelling civil charge notifications failed"
            )

            return Response({
                "success": False,
                "message": "هنگام لغو اعلان شارژ خطایی رخ داد.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            "success": True,
            "message": "عملیات لغو اعلان شارژ عمرانی انجام شد.",
            "civil_id": civil.id,
            "cancelled_units_count": cancelled_units_count,
            "cancelled_installments_count": cancelled_installments_count,
            "skipped_paid_units_count": skipped_paid_units_count,
            "skipped_unsent_units_count": skipped_unsent_units_count,
        })
class ManagerMonthlyChargesAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        return MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

    def get(self, request):
        house = self.get_house(request)

        if not house:
            return Response(
                {
                    "success": False,
                    "message": "ساختمان فعالی برای مدیر پیدا نشد.",
                    "results": [],
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        charges = (
            UnifiedCharge.objects
            .filter(
                house=house,
                send_notification=True,
                send_notification_date__isnull=False,
                unit__isnull=False,
                content_type__isnull=False,
                object_id__isnull=False,
            )
            .exclude(charge_type="expense_charge")
            .select_related("unit", "content_type")
            .order_by("-created_at", "-id")
        )

        # گروه‌بندی رکوردهای واحدها بر اساس شارژ اصلی
        grouped = OrderedDict()

        for charge in charges:
            key = (
                charge.content_type_id,
                charge.object_id,
            )

            if key not in grouped:
                grouped[key] = {
                    "content_type": charge.content_type,
                    "object_id": charge.object_id,
                    "title": (
                            charge.title
                            or charge.details
                            or charge.get_charge_type_display()
                    ),
                    "charge_type": charge.charge_type,
                    "charge_type_display": (
                        charge.get_charge_type_display()
                    ),
                    "payment_deadline_date": (
                        charge.payment_deadline_date
                    ),
                    "created_at": charge.created_at,
                    "total_count": 0,
                    "notified_count": 0,
                    "paid_count": 0,
                    "unit_ids": set(),
                }

            item = grouped[key]

            # شمارش واحدهای یکتا
            if charge.unit_id not in item["unit_ids"]:
                item["unit_ids"].add(charge.unit_id)
                item["total_count"] += 1

                if (
                        charge.send_notification
                        and charge.send_notification_date
                ):
                    item["notified_count"] += 1

                if charge.is_paid:
                    item["paid_count"] += 1

        results = []

        for item in grouped.values():
            content_type = item["content_type"]

            results.append({
                "id": item["object_id"],
                "app_label": content_type.app_label,
                "model_name": content_type.model,
                "title": item["title"],
                "charge_type": item["charge_type"],
                "charge_type_display": item["charge_type_display"],
                "total_count": item["total_count"],
                "notified_count": item["notified_count"],
                "paid_count": item["paid_count"],
                "payment_deadline_date": (
                    item["payment_deadline_date"].isoformat()
                    if item["payment_deadline_date"]
                    else None
                ),
                "created_at": item["created_at"].isoformat(),
            })

        results.sort(
            key=lambda item: item["created_at"],
            reverse=True,
        )

        return Response({
            "success": True,
            "house_id": house.id,
            "count": len(results),
            "results": results,
        })
class ManagerMonthlyChargeUnitsAPIView(APIView):
    """
    دریافت واحدهای اعلان‌شده مربوط به یک شارژ اصلی.
    همراه با اطلاعات مالک/مستأجر فعال و مبالغ قابل نمایش.
    """
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        return MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

    def get_resident_info(self, unit):
        """
        اگر مستأجر فعال وجود داشته باشد، اطلاعات او را برمی‌گرداند؛
        در غیر این صورت اطلاعات مالک واحد نمایش داده می‌شود.
        """
        renter = unit.get_active_renter()

        if renter:
            return {
                "resident_type": "renter",
                "resident_type_display": "مستأجر",
                "resident_name": (
                        getattr(renter, "renter_name", "") or
                        getattr(
                            getattr(renter, "user", None),
                            "get_full_name",
                            lambda: "",
                        )() or
                        "نامشخص"
                ),
            }

        owner_name = (
                getattr(unit, "owner_name", "") or
                getattr(
                    getattr(unit, "user", None),
                    "get_full_name",
                    lambda: "",
                )() or
                "نامشخص"
        )

        return {
            "resident_type": "owner",
            "resident_type_display": "مالک",
            "resident_name": owner_name,
        }

    def get(self, request, app_label, model_name, charge_id):
        house = self.get_house(request)

        if not house:
            return Response(
                {
                    "success": False,
                    "message": "ساختمان فعالی پیدا نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        allowed_models = {
            model._meta.model_name: model
            for model in [
                FixCharge,
                AreaCharge,
                PersonCharge,
                FixPersonCharge,
                FixAreaCharge,
                ChargeByPersonArea,
                ChargeByFixPersonArea,
                ChargeFixVariable,
                ChargeCalculation,
            ]
        }

        model = allowed_models.get(model_name.lower())

        if not model or model._meta.app_label != app_label:
            return Response(
                {
                    "success": False,
                    "message": "نوع شارژ معتبر نیست.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # بررسی مالکیت شارژ توسط مدیر
        if model is ChargeCalculation:
            charge = get_object_or_404(
                model,
                pk=charge_id,
                created_by=request.user,
            )
        else:
            charge = get_object_or_404(
                model,
                pk=charge_id,
                user=request.user,
            )

        content_type = ContentType.objects.get_for_model(model)

        unified_charges = (
            UnifiedCharge.objects.filter(
                house=house,
                content_type=content_type,
                object_id=charge.id,
                unit__isnull=False,
                send_notification=True,
                send_notification_date__isnull=False,
            )
            .select_related(
                "unit",
                "unit__user",
            )
            .order_by("unit__unit", "id")
        )

        results = []

        for item in unified_charges:
            unit = item.unit

            resident = self.get_resident_info(unit)

            amount = item.amount or 0
            base_charge = item.base_charge or 0
            other_cost = item.other_cost_amount or 0
            civil = item.civil or 0
            penalty = item.penalty_amount or 0

            # مبلغ پایه قابل پرداخت، بدون احتساب جریمه
            charge_amount = (
                                item.total_charge_month
                                if item.total_charge_month is not None
                                else amount
                            ) or 0

            # مبلغ قابل پرداخت با احتساب جریمه
            payable_amount = charge_amount + penalty

            results.append({
                # شناسه رکورد شارژ این واحد در UnifiedCharge
                "unified_charge_id": item.id,

                # برای سازگاری با کدهای قبلی Flutter حفظ شود
                "id": item.id,

                # شناسه واحد در مدل Unit
                "unit_id": unit.id,

                # مالک یا مستأجر فعال
                **resident,

                "unit_display": (
                    f"واحد {unit.unit} - "
                    f"{resident['resident_type_display']}: "
                    f"{resident['resident_name']}"
                ),

                "title": (
                        item.title
                        or item.details
                        or getattr(charge, "name", "")
                        or ""
                ),

                "charge_type": item.charge_type,

                # مبالغ
                "amount": amount,
                "base_charge": base_charge,
                "other_cost_amount": other_cost,
                "civil": civil,
                "penalty_amount": penalty,
                "total_charge_month": charge_amount,
                "payable_amount": payable_amount,

                # وضعیت پرداخت
                "is_paid": item.is_paid,
                "payment_pending": item.payment_pending,
                # "payment_date": (
                #     item.payment_date.isoformat()
                #     if item.payment_date else None
                # ),

                # مهلت و تاریخ اعلام
                "payment_deadline_date": (
                    item.payment_deadline_date.isoformat()
                    if item.payment_deadline_date else None
                ),
                "send_notification_date": (
                    item.send_notification_date.isoformat()
                    if item.send_notification_date else None
                ),

                # شماره سند
                "financial_document_number": (
                    item.financial_document_number
                ),
                "bank_name": (
                    str(item.bank)
                    if item.bank_id
                    else None
                ),
                "payment_date": (
                    item.payment_date.isoformat()
                    if item.is_paid and item.payment_date
                    else None
                ),
                "transaction_reference": (
                    item.transaction_reference
                    if item.is_paid
                    else None
                ),
            })

        return Response({
            "success": True,
            "charge_id": charge.id,
            "app_label": content_type.app_label,
            "model_name": content_type.model,
            "charge_name": getattr(charge, "name", "") or "",
            "count": len(results),
            "results": results,
        })
class ManagerMonthlyChargePaymentAPIView(APIView):
    """
    GET:
        دریافت حساب‌های بانکی فعال ساختمان برای پرداخت شارژ.

    POST:
        ثبت پرداخت شارژ، سند صندوق و تراکنش بانکی.
    """
    permission_classes = [IsAuthenticated]

    def get_charge(self, request, charge_id):
        """
        فقط شارژی را برمی‌گرداند که متعلق به ساختمان مدیر باشد.
        """
        house = getattr(request.user, "house", None)

        if not house:
            house = (
                MyHouse.objects.filter(
                    user=request.user,
                    is_active=True,
                ).first()
            )

        if not house:
            return None, None

        charge = (
            UnifiedCharge.objects
            .filter(
                pk=charge_id,
                house=house,
            )
            .select_related("unit", "house")
            .first()
        )

        return house, charge

    def get(self, request, charge_id):
        house, charge = self.get_charge(request, charge_id)

        if not house or not charge:
            return Response(
                {
                    "success": False,
                    "message": "شارژ یا ساختمان معتبر پیدا نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if charge.is_paid:
            return Response(
                {
                    "success": False,
                    "message": "این شارژ قبلاً پرداخت شده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        banks = Bank.objects.filter(
            house=house,
            is_active=True,
        ).order_by("-is_default", "bank_name")

        return Response({
            "success": True,
            "charge_id": charge.pk,
            "amount": charge.total_charge_month or 0,
            "banks": [
                {
                    "id": bank.pk,
                    "bank_name": bank.bank_name,
                    "account_no": bank.account_no,
                    "is_default": bank.is_default,
                    # "label": (
                    #     f"{bank.bank_name} - {bank.account_no}"
                    # ),
                }
                for bank in banks
            ],
        })

    def post(self, request, charge_id):
        house, charge = self.get_charge(request, charge_id)

        if not house or not charge:
            return Response(
                {
                    "success": False,
                    "message": "شارژ یا ساختمان معتبر پیدا نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        bank_id = request.data.get("bank_id")
        raw_date = request.data.get("payment_date")
        raw_reference = request.data.get("transaction_reference")

        if not bank_id:
            return Response(
                {
                    "success": False,
                    "message": "حساب بانکی را انتخاب کنید.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            bank_id = int(bank_id)
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "message": "شناسه حساب بانکی معتبر نیست.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank = Bank.objects.filter(
            pk=bank_id,
            house=house,
            is_active=True,
        ).first()

        if not bank:
            return Response(
                {
                    "success": False,
                    "message": "حساب بانکی معتبر یا فعالی برای این ساختمان پیدا نشد.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # تاریخ ارسالی باید میلادی و با قالب YYYY-MM-DD باشد.
        if raw_date:
            payment_date = parse_date(str(raw_date))
            if not payment_date:
                return Response(
                    {
                        "success": False,
                        "message": "تاریخ پرداخت معتبر نیست؛ قالب YYYY-MM-DD ارسال کنید.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            payment_date = date.today()

        if payment_date > date.today():
            return Response(
                {
                    "success": False,
                    "message": "تاریخ پرداخت نمی‌تواند از امروز بیشتر باشد.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        transaction_reference = None

        if raw_reference not in (None, ""):
            try:
                transaction_reference = int(raw_reference)
                if transaction_reference < 0:
                    raise ValueError
            except (TypeError, ValueError):
                return Response(
                    {
                        "success": False,
                        "message": "کد پیگیری باید عددی و نامنفی باشد.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

        try:
            with transaction.atomic():
                # قفل شارژ برای جلوگیری از ثبت هم‌زمان پرداخت تکراری
                unified_charge = (
                    UnifiedCharge.objects
                    .select_for_update()
                    .filter(
                        pk=charge_id,
                        house=house,
                    )
                    .select_related("unit", "house")
                    .first()
                )

                if not unified_charge:
                    return Response(
                        {
                            "success": False,
                            "message": "شارژ پیدا نشد.",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if unified_charge.is_paid:
                    return Response(
                        {
                            "success": False,
                            "message": "این شارژ قبلاً پرداخت شده است.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # بررسی مجدد حساب بانکی داخل تراکنش
                bank = (
                    Bank.objects
                    .filter(
                        pk=bank_id,
                        house=house,
                        is_active=True,
                    )
                    .first()
                )

                if not bank:
                    return Response(
                        {
                            "success": False,
                            "message": "حساب بانکی دیگر فعال یا معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # اعتبارسنجی تاریخ افتتاح حساب
                validate_bank_transaction_date(
                    bank,
                    payment_date,
                )

                unified_charge.bank = bank
                unified_charge.payment_date = payment_date
                unified_charge.transaction_reference = (
                    transaction_reference
                )
                unified_charge.is_paid = True
                unified_charge.payment_gateway = "پرداخت الکترونیک"

                # محاسبه جریمه مطابق منطق فعلی پروژه
                unified_charge.update_penalty(save=False)
                unified_charge.save()

                unit = unified_charge.unit

                if not unit:
                    raise ValidationError(
                        "واحد مرتبط با این شارژ مشخص نیست."
                    )

                active_renter = (
                    unit.renters
                    .filter(renter_is_active=True)
                    .first()
                )

                if active_renter:
                    payer_type = "renter"
                    payer_renter = active_renter
                    payer_person_name = (
                            active_renter.renter_name or ""
                    ).strip()
                else:
                    payer_type = "owner"
                    payer_renter = None
                    payer_person_name = (
                            unit.owner_name or ""
                    ).strip()

                if not payer_person_name:
                    raise ValidationError(
                        "نام مالک یا مستأجر پرداخت‌کننده مشخص نیست."
                    )

                payer_name_snapshot = (
                    f"واحد {unit.unit} - {payer_person_name}"
                )

                payment_description = (
                    f"پرداخت شارژ ماهانه: "
                    f"{(unified_charge.title or '')[:50]}"
                )

                payment_amount = Decimal(
                    str(unified_charge.total_charge_month or 0)
                )

                if payment_amount <= 0:
                    raise ValidationError(
                        "مبلغ شارژ برای ثبت پرداخت معتبر نیست."
                    )

                unified_ct = ContentType.objects.get_for_model(
                    UnifiedCharge
                )

                # سند صندوق مطابق ویوی فعلی
                Fund.objects.create(
                    content_type=unified_ct,
                    object_id=unified_charge.pk,
                    bank=bank,
                    unit=unit,
                    house=unified_charge.house,
                    payer_type=payer_type,
                    payer_renter=payer_renter,
                    payer_name=payer_name_snapshot,
                    debtor_amount=payment_amount,
                    amount=payment_amount,
                    creditor_amount=0,
                    financial_document_number=(
                        unified_charge.financial_document_number
                    ),
                    user=request.user,
                    payment_date=unified_charge.payment_date,
                    payment_description=payment_description,
                    transaction_no=(
                        unified_charge.transaction_reference
                    ),
                    payment_gateway="پرداخت الکترونیک",
                )

                # BankTransactionService خودش BankFund می‌سازد.
                # عمداً BankFund.objects.create را دوباره اجرا نمی‌کنیم.
                BankTransactionService.deposit(
                    user=request.user,
                    bank=bank,
                    unit=unit,
                    amount=payment_amount,
                    description=payment_description,
                    payer_type=payer_type,
                    payer_renter=payer_renter,
                    payer_name=payer_person_name,
                    content_object=unit,
                    payment_date=unified_charge.payment_date,
                    transaction_no=(
                        unified_charge.transaction_reference
                    ),
                    gateway="پرداخت الکترونیک",
                    house=unified_charge.house,
                    financial_document_number=(
                        unified_charge.financial_document_number
                    ),
                )

            return Response({
                "success": True,
                "message": "پرداخت شارژ با موفقیت ثبت شد.",
                "charge_id": unified_charge.pk,
                "is_paid": True,
                "payment_date": (
                    unified_charge.payment_date.isoformat()
                    if unified_charge.payment_date else None
                ),
                "financial_document_number": (
                    unified_charge.financial_document_number
                ),
                "amount": str(payment_amount),
            })

        except ValidationError as exc:
            logger.warning(
                "اعتبارسنجی پرداخت شارژ ناموفق بود؛ charge_id=%s",
                charge_id,
            )

            errors = getattr(exc, "messages", [str(exc)])

            return Response(
                {
                    "success": False,
                    "message": " ".join(errors),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                "خطا در ثبت پرداخت شارژ؛ charge_id=%s",
                charge_id,
            )

            return Response(
                {
                    "success": False,
                    "message": "ثبت پرداخت انجام نشد؛ اسناد مالی بررسی شوند.",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
class ManagerMonthlyChargeCancelPaymentAPIView(APIView):
    """
    POST:
        لغو پرداخت شارژ ماهانه مدیر،
        حذف سند صندوق و تراکنش بانکی مربوط،
        بازمحاسبه موجودی بانک و صندوق.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, charge_id):
        house = getattr(request.user, "house", None)

        if not house:
            house = MyHouse.objects.filter(
                user=request.user,
                is_active=True,
            ).first()

        if not house:
            return Response({
                "success": False,
                "message": "ساختمان مدیر مشخص نیست.",
            }, status=status.HTTP_404_NOT_FOUND)

        try:
            with transaction.atomic():
                charge = (
                    UnifiedCharge.objects
                    .select_for_update()
                    .select_related("unit", "house", "bank")
                    .filter(
                        pk=charge_id,
                        house=house,
                        is_paid=True,
                    )
                    .first()
                )

                if not charge:
                    return Response({
                        "success": False,
                        "message": "شارژ پرداخت‌شده‌ای با این شناسه پیدا نشد.",
                    }, status=status.HTTP_404_NOT_FOUND)

                if not charge.unit:
                    raise ValidationError(
                        "واحد مرتبط با شارژ مشخص نیست."
                    )

                if not charge.financial_document_number:
                    raise ValidationError(
                        "شماره سند مالی شارژ مشخص نیست؛ لغو انجام نشد."
                    )

                # ۱. پیدا کردن سند صندوق
                unified_ct = ContentType.objects.get_for_model(
                    UnifiedCharge
                )

                funds = Fund.objects.filter(
                    content_type=unified_ct,
                    object_id=charge.pk,
                    house=house,
                )

                if funds.count() != 1:
                    raise ValidationError(
                        "سند صندوق دقیقاً یک مورد نیست؛ لغو انجام نشد."
                    )

                fund = funds.select_for_update().get()
                fund_doc_number = fund.doc_number

                # ۲. پیدا کردن تراکنش بانکی متناظر
                unit_ct = ContentType.objects.get_for_model(
                    charge.unit
                )

                bank_funds = BankFund.objects.filter(
                    content_type=unit_ct,
                    object_id=charge.unit.pk,
                    house=house,
                    bank=charge.bank,
                    financial_document_number=(
                        charge.financial_document_number
                    ),
                    transaction_type="deposit",
                    amount=Decimal(
                        str(charge.total_charge_month or 0)
                    ),
                )

                if bank_funds.count() != 1:
                    raise ValidationError(
                        "تراکنش بانکی متناظر دقیقاً یک مورد نیست؛ "
                        "برای جلوگیری از تغییر اشتباه موجودی، لغو انجام نشد."
                    )

                bank_fund = bank_funds.select_for_update().get()
                bank = bank_fund.bank

                # ۳. حذف تراکنش بانکی و محاسبه مجدد موجودی
                bank_fund.delete()
                recalculate_bank_balance(bank)

                # ۴. حذف سند صندوق و محاسبه مجدد
                fund.delete()

                next_fund = (
                    Fund.objects
                    .filter(
                        doc_number__gt=fund_doc_number,
                        house=house,
                    )
                    .order_by("doc_number")
                    .first()
                )

                if next_fund:
                    Fund.recalc_final_amounts_from(next_fund)

                # ۵. برگرداندن شارژ به حالت پرداخت‌نشده
                charge.is_paid = False
                charge.payment_gateway = None
                charge.payment_date = None
                charge.transaction_reference = None
                charge.bank = None

                update_fields = [
                    "is_paid",
                    "payment_gateway",
                    "payment_date",
                    "transaction_reference",
                    "bank",
                ]

                if hasattr(charge, "payment_pending"):
                    charge.payment_pending = False
                    update_fields.append("payment_pending")

                charge.save(update_fields=update_fields)

            return Response({
                "success": True,
                "message": "پرداخت شارژ لغو شد و اسناد مالی اصلاح شدند.",
                "charge_id": charge.pk,
                "is_paid": False,
            })

        except ValidationError as exc:
            errors = getattr(exc, "messages", [str(exc)])

            return Response({
                "success": False,
                "message": " ".join(errors),
            }, status=status.HTTP_400_BAD_REQUEST)

        except Exception:
            logger.exception(
                "خطا در لغو پرداخت شارژ ماهانه؛ charge_id=%s",
                charge_id,
            )

            return Response({
                "success": False,
                "message": "لغو پرداخت انجام نشد؛ اسناد مالی بررسی شوند.",
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
def civil_api_error(message, status=400):
    return Response(
        {
            "success": False,
            "message": message,
        },
        status=status,
    )
def civil_get_manager_house(user):
    """
    ساختمان مرتبط با مدیر.
    اگر مدیر در پروژه چند ساختمان دارد، این تابع باید مطابق
    سازوکار انتخاب ساختمان در Raya Charge تنظیم شود.
    """
    return MyHouse.objects.filter(user=user).first()
def civil_get_manager_charge(user, civil_id):
    return CivilManage.objects.filter(
        pk=civil_id,
        user=user,
        house__isnull=False,
    ).first()
def civil_get_manager_unit(user, unit_id, house=None):
    units = Unit.objects.filter(
        pk=unit_id,
        user__manager=user,
        is_active=True,
    )

    if house is not None:
        units = units.filter(myhouse=house)

    return units.first()
def civil_installment_total(civil, unit):
    return CivilInstallment.objects.filter(
        civil_manage=civil,
        unit=unit,
    ).count()
def civil_installment_is_previous_paid(installment):
    """
    اجازه پرداخت قسط بعدی فقط در صورت پرداخت قسط قبلی.
    قسط شماره صفر پیش‌پرداخت است.
    """
    if installment.installment_number == 0:
        return True

    previous = CivilInstallment.objects.filter(
        civil_manage=installment.civil_manage,
        unit=installment.unit,
        installment_number=installment.installment_number - 1,
    ).first()

    return previous is None or previous.is_paid
def civil_serialize_installment(installment):
    return {
        "id": installment.id,
        "civil_id": installment.civil_manage_id,
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
                and civil_installment_is_previous_paid(installment)
        ),
    }
class ManagerCivilChargesListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return civil_api_error(
                "شما اجازه دسترسی به این بخش را ندارید.",
                403,
            )

        charges = CivilManage.objects.filter(
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
            return civil_api_error("شماره صفحه یا اندازه صفحه معتبر نیست.")

        total = charges.count()
        start = (page - 1) * page_size

        results = []

        for civil in charges[start:start + page_size]:
            installments = CivilInstallment.objects.filter(
                civil_manage=civil,
            )

            results.append({
                "id": civil.id,
                "name": civil.name,
                "amount": civil.amount,
                "prepayment": civil.prepayment,
                "installment_count": civil.installment_count,
                "first_due_date": (
                    civil.first_due_date.isoformat()
                    if civil.first_due_date else None
                ),
                "details": civil.details or "",
                "created_at": (
                    civil.created_at.isoformat()
                    if civil.created_at else None
                ),
                "is_active": civil.is_active,
                "unit_count": installments.values(
                    "unit_id"
                ).distinct().count(),
                "paid_installment_count": installments.filter(
                    is_paid=True
                ).count(),
                "unpaid_installment_count": installments.filter(
                    is_paid=False
                ).count(),
            })

        return Response({
            "success": True,
            "count": total,
            "page": page,
            "page_size": page_size,
            "results": results,
        })
class ManagerCivilChargeUnitsListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, civil_id):
        civil = civil_get_manager_charge(request.user, civil_id)

        if not civil:
            return civil_api_error("شارژ عمرانی پیدا نشد.", 404)

        # فقط واحدهایی که برای همین شارژ، قسط ارسال‌شده دارند
        unit_ids = (
            CivilInstallment.objects.filter(
                civil_manage=civil,
                send_notification=True,
                unit__isnull=False,
                unit__is_active=True,
                unit__user__manager=request.user,
                unit__myhouse=civil.house,
            )
            .values_list("unit_id", flat=True)
            .distinct()
        )

        units = Unit.objects.filter(
            id__in=unit_ids,
            is_active=True,
            user__manager=request.user,
            myhouse=civil.house,
        ).order_by("unit")

        # جست‌وجو بر اساس شماره واحد، مالک یا مستأجر فعال
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
            # دریافت تمام رکوردهای ارسال‌شده برای این واحد
            all_installments = list(
                CivilInstallment.objects.filter(
                    civil_manage=civil,
                    unit=unit,
                    send_notification=True,
                ).order_by("installment_number", "id")
            )

            # قسط شماره صفر، رکورد پیش‌پرداخت است
            prepayment_installments = [
                item
                for item in all_installments
                if item.installment_number == 0
            ]

            # اقساط ماهانه؛ بدون قسط شماره صفر
            installments = [
                item
                for item in all_installments
                if item.installment_number > 0
            ]

            # مبلغ پیش‌پرداخت از رکورد شماره صفر
            prepayment = next(
                (
                    item.amount or item.prepayment_per_unit or 0
                    for item in prepayment_installments
                ),
                0,
            )

            # در نبود رکورد شماره صفر، از مبلغ پروژه استفاده می‌شود
            if not prepayment:
                prepayment = civil.prepayment or 0

            # وضعیت پرداخت پیش‌پرداخت
            prepayment_is_paid = any(
                item.is_paid
                for item in prepayment_installments
            )

            # اقساط ماهانه پرداخت‌شده
            paid_installments = [
                item
                for item in installments
                if item.is_paid
            ]

            # اقساط ماهانه پرداخت‌نشده
            unpaid_installments = [
                item
                for item in installments
                if not item.is_paid
            ]

            # تعداد اقساط شامل پیش‌پرداخت، در صورت وجود رکورد آن
            has_prepayment_installment = bool(
                prepayment_installments
            )

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

            unpaid_count = (
                    len(unpaid_installments)
                    + (
                        1
                        if has_prepayment_installment
                           and not prepayment_is_paid
                        else 0
                    )
            )

            # مجموع مبلغ اقساط ماهانه؛ بدون پیش‌پرداخت
            installments_total_amount = sum(
                item.amount or 0
                for item in installments
            )

            # مبلغ کل سهم واحد = پیش‌پرداخت + اقساط ماهانه
            total_charge_amount = (
                    prepayment + installments_total_amount
            )

            # مبلغ پرداخت‌شده شامل پیش‌پرداخت پرداخت‌شده
            paid_amount = sum(
                item.amount or 0
                for item in paid_installments
            )

            if has_prepayment_installment and prepayment_is_paid:
                paid_amount += prepayment

            # مبلغ پرداخت‌نشده شامل پیش‌پرداخت پرداخت‌نشده
            unpaid_amount = sum(
                item.amount or 0
                for item in unpaid_installments
            )

            if (
                    has_prepayment_installment
                    and not prepayment_is_paid
            ):
                unpaid_amount += prepayment

            # اطلاعات مالک یا مستأجر فعال
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

                # اطلاعات مالک
                "owner_name": unit.owner_name or "",
                "owner_mobile": unit.owner_mobile or "",

                # اطلاعات ساکن فعلی
                "resident_type": resident_type,
                "resident_type_display": resident_type_display,
                "resident_name": resident_name,
                "active_tenant_name": active_tenant_name,

                # مبالغ مالی
                "prepayment": prepayment,
                "installments_total_amount": (
                    installments_total_amount
                ),
                "amount": total_charge_amount,
                "total_charge_amount": total_charge_amount,
                "paid_amount": paid_amount,
                "unpaid_amount": unpaid_amount,
                "remaining_installments_amount": unpaid_amount,

                # تعداد اقساط با احتساب پیش‌پرداخت
                "paid_count": paid_count,
                "total_installments": total_installments,
                "unpaid_count": unpaid_count,

                # جزئیات فقط اقساط ماهانه
                "installments": [
                    civil_serialize_installment(item)
                    for item in installments
                ],
            })

        return Response({
            "success": True,
            "civil_id": civil.id,
            "civil_name": civil.name,
            "count": len(results),
            "results": results,
        })
class ManagerCivilUnitInstallmentsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, civil_id, unit_id):
        civil = civil_get_manager_charge(request.user, civil_id)

        if not civil:
            return civil_api_error("شارژ عمرانی پیدا نشد.", 404)

        unit = civil_get_manager_unit(
            request.user,
            unit_id,
            house=civil.house,
        )

        if not unit:
            return civil_api_error("واحد پیدا نشد.", 404)

        installments = CivilInstallment.objects.filter(
            civil_manage=civil,
            unit=unit,
        ).order_by("installment_number")

        return Response({
            "success": True,
            "civil": {
                "id": civil.id,
                "name": civil.name,
            },
            "unit": {
                "id": unit.id,
                "unit": unit.unit,
                "owner_name": unit.owner_name or "",
            },
            "count": installments.count(),
            "paid_count": installments.filter(is_paid=True).count(),
            "unpaid_count": installments.filter(is_paid=False).count(),
            "results": [
                civil_serialize_installment(item)
                for item in installments
            ],
        })
class ManagerCivilInstallmentPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, installment_id):
        installment = CivilInstallment.objects.filter(
            pk=installment_id,
            civil_manage__user=request.user,
            civil_manage__house__isnull=False,
            unit__user__manager=request.user,
        ).select_related(
            "civil_manage",
            "unit",
            "civil_manage__house",
        ).first()

        if not installment:
            return civil_api_error("قسط پیدا نشد.", 404)

        if not installment.send_notification:
            return civil_api_error(
                "این قسط هنوز برای واحد ارسال نشده است."
            )

        if installment.is_paid:
            return civil_api_error("این قسط قبلاً پرداخت شده است.")

        if not civil_installment_is_previous_paid(installment):
            return civil_api_error("ابتدا باید قسط قبلی پرداخت شود.")

        banks = Bank.objects.filter(
            is_active=True,
            house=installment.civil_manage.house,
        ).order_by("-is_default", "bank_name")

        return Response({
            "success": True,
            "installment": civil_serialize_installment(installment),
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
            return civil_api_error("دسترسی غیرمجاز.", 403)

        # همه کنترل‌های دسترسی باید قبل از تغییر مالی انجام شوند.
        installment = CivilInstallment.objects.filter(
            pk=installment_id,
            civil_manage__user=user,
            civil_manage__house__isnull=False,
            unit__user__manager=user,
        ).select_related(
            "civil_manage",
            "unit",
            "civil_manage__house",
        ).first()

        if not installment:
            return civil_api_error("قسط پیدا نشد.", 404)

        if not installment.send_notification:
            return civil_api_error(
                "این قسط برای واحد ارسال نشده است."
            )

        try:
            bank_id = int(request.data.get("bank_id"))
        except (ValueError, TypeError):
            return civil_api_error("حساب بانکی معتبر انتخاب کنید.")

        bank = Bank.objects.filter(
            pk=bank_id,
            house=installment.civil_manage.house,
            is_active=True,
        ).first()

        if not bank:
            return civil_api_error(
                "حساب بانکی معتبر برای این ساختمان پیدا نشد."
            )

        raw_date = request.data.get("payment_date")

        if raw_date:
            try:
                payment_date = datetime.date.fromisoformat(str(raw_date)[:10])
            except (ValueError, TypeError):
                return civil_api_error(
                    "تاریخ پرداخت باید به قالب YYYY-MM-DD باشد."
                )
        else:
            payment_date = date.today()

        if payment_date > date.today():
            return civil_api_error(
                "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
            )

        transaction_reference = str(
            request.data.get("transaction_reference") or ""
        ).strip()

        if len(transaction_reference) > 20:
            return civil_api_error(
                "شماره پیگیری نمی‌تواند بیشتر از ۲۰ کاراکتر باشد."
            )

        # بررسی تاریخ افتتاح حساب، مطابق فرم وب
        try:
            validate_bank_transaction_date(bank, payment_date)
        except Exception as exc:
            return civil_api_error(str(exc))

        with transaction.atomic():
            # قفل رکورد برای جلوگیری از ثبت هم‌زمان پرداخت
            installment = CivilInstallment.objects.select_for_update().filter(
                pk=installment_id,
                civil_manage__user=user,
                unit__user__manager=user,
            ).first()

            if not installment:
                return civil_api_error("قسط پیدا نشد.", 404)

            if installment.is_paid:
                return civil_api_error(
                    "این قسط قبلاً پرداخت شده است."
                )

            if installment.payment_pending:
                return civil_api_error(
                    "این قسط در انتظار تأیید پرداخت است."
                )

            if not civil_installment_is_previous_paid(installment):
                return civil_api_error(
                    "ابتدا باید قسط قبلی پرداخت شود."
                )

            content_type = ContentType.objects.get_for_model(
                CivilInstallment
            )

            # جلوگیری از ایجاد پرداخت مالی تکراری
            existing_fund = Fund.objects.filter(
                content_type=content_type,
                object_id=installment.pk,
            ).exists()

            if existing_fund:
                return civil_api_error(
                    "برای این قسط سند مالی وجود دارد؛ "
                    "ابتدا وضعیت آن را بررسی کنید."
                )

            unit = installment.unit
            house = installment.civil_manage.house

            owner_name = (unit.owner_name or "").strip()
            payer_name_snapshot = (
                f"واحد {unit.unit} - {owner_name}"
                if owner_name
                else f"واحد {unit.unit}"
            )

            payment_description = (
                f"پرداخت شارژ عمرانی: "
                f"{(installment.civil_manage.name or '')[:50]}"
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

            # مطابق منطق مالی موجود در ویوی وب
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
            "message": "پرداخت با موفقیت ثبت شد.",
            "installment": civil_serialize_installment(installment),
        })
class ManagerCivilInstallmentCancelPaymentAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, installment_id):
        user = request.user

        if not getattr(user, "is_middle_admin", False):
            return civil_api_error("دسترسی غیرمجاز.", 403)

        with transaction.atomic():
            installment = (
                CivilInstallment.objects
                .select_for_update()
                .filter(
                    pk=installment_id,
                    civil_manage__user=user,
                    unit__user__manager=user,
                )
                .select_related(
                    "civil_manage",
                    "unit",
                    "civil_manage__house",
                )
                .first()
            )

            if not installment:
                return civil_api_error("قسط پیدا نشد.", 404)

            if not installment.is_paid:
                return civil_api_error("این قسط قبلاً پرداخت نشده است.")

            content_type = ContentType.objects.get_for_model(
                CivilInstallment
            )

            fund = Fund.objects.filter(
                content_type=content_type,
                object_id=installment.id,
            ).first()

            if not fund:
                return civil_api_error(
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

                bank.save(update_fields=["current_balance"])
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
            "installment": civil_serialize_installment(installment),
        })
