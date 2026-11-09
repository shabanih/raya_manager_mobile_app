"""Resident Charges API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ChargePaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, charge_id):

        # =====================================================
        # پیدا کردن شارژ
        # =====================================================

        charge = UnifiedCharge.objects.filter(
            id=charge_id,
            send_notification=True,
        ).select_related(
            'unit',
            'house',
        ).first()

        if not charge:
            return Response(
                {
                    'success': False,
                    'message': 'شارژ مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =====================================================
        # واحد شارژ
        # =====================================================

        unit = charge.unit

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد مربوط به این شارژ پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =====================================================
        # بررسی مالک
        # =====================================================

        is_owner = (
                unit.user_id == request.user.id
        )

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
                    'message': 'این شارژ متعلق به شما نیست.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # اگر شارژ قبلاً پرداخت شده
        # =====================================================

        if charge.is_paid:
            return Response(
                {
                    'success': False,
                    'status': 'paid',
                    'message': 'این شارژ قبلاً پرداخت شده است.',
                    'is_paid': True,
                    'payment_pending': False,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if charge.payment_pending:
            return Response(
                {
                    'success': False,
                    'status': 'pending',
                    'message': (
                        'درخواست پرداخت این شارژ قبلاً ثبت شده '
                        'و در انتظار تأیید مدیر ساختمان است.'
                    ),
                    'is_paid': False,
                    'payment_pending': True,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # درگاه پرداخت
        # =====================================================

        gateway = HousePaymentGateway.objects.filter(
            house=charge.house,
            is_active=True
        ).first()

        # =====================================================
        # حساب‌های بانکی فعال ساختمان
        # =====================================================

        banks = Bank.objects.filter(
            house=charge.house,
            is_active=True
        ).order_by(
            '-is_default',
            'bank_name'
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'success': True,

                'charge': {
                    'id': charge.id,
                    'title': charge.title,
                    'amount': charge.total_charge_month,
                    'is_paid': charge.is_paid,
                },

                'payment_banks': [
                    {
                        'id': bank.id,
                        'bank_name': bank.bank_name,
                        'account_no': bank.account_no,
                        'account_holder_name': bank.account_holder_name,
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
                            'واریز مبلغ شارژ به حساب ساختمان و ثبت کد پیگیری'
                            if banks.exists()
                            else 'حساب بانکی برای ساختمان ثبت نشده است.'
                        )
                    },

                    {
                        'type': 'online',
                        'title': 'پرداخت اینترنتی',
                        'available': gateway is not None,
                        'gateway': (
                            gateway.gateway_type
                            if gateway
                            else None
                        ),
                        'description': (
                            'پرداخت از طریق درگاه بانکی'
                            if gateway
                            else 'درگاه پرداخت برای ساختمان شما ثبت نشده است.'
                        )
                    }
                ]
            },
            status=status.HTTP_200_OK
        )
class ManualChargePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, charge_id):

        # =====================================================
        # اعتبارسنجی
        # =====================================================

        serializer = ManualChargePaymentSerializer(
            data=request.data,
            context={
                'request': request,
                'charge_id': charge_id,
            }
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # اطلاعات
        # =====================================================

        charge = serializer.validated_data['charge']
        bank = serializer.validated_data['bank']

        transaction_reference = (
            serializer.validated_data['transaction_reference']
        )

        payment_date = (
            serializer.validated_data['payment_date']
        )

        # =====================================================
        # قفل رکورد شارژ
        #
        # جلوگیری از ثبت همزمان دو درخواست پرداخت
        # =====================================================

        charge = (
            UnifiedCharge.objects
            .select_for_update()
            .select_related(
                'unit',
                'house',
                'bank',
            )
            .get(pk=charge.pk)
        )

        # =====================================================
        # بررسی مالکیت شارژ
        #
        # مالک واحد یا مستأجر فعال
        # =====================================================

        has_access = UnifiedCharge.objects.filter(
            Q(
                unit__user=request.user
            )
            |
            Q(
                unit__renters__user=request.user,
                unit__renters__renter_is_active=True,
            ),
            pk=charge.id,
            unit__is_active=True,
        ).exists()

        if not has_access:
            return Response(
                {
                    'success': False,
                    'message': 'این شارژ متعلق به شما نیست.',
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # شارژ قبلاً پرداخت شده
        # =====================================================

        if charge.is_paid:
            return Response(
                {
                    'success': False,
                    'message': 'این شارژ قبلاً پرداخت شده است.',
                    'is_paid': True,
                    'payment_pending': False,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # قبلاً درخواست پرداخت ثبت شده
        # =====================================================

        if charge.payment_pending:
            return Response(
                {
                    'success': False,
                    'message': (
                        'درخواست پرداخت این شارژ قبلاً ثبت شده '
                        'و در انتظار تأیید مدیر ساختمان است.'
                    ),
                    'is_paid': False,
                    'payment_pending': True,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # بروزرسانی جریمه
        # =====================================================

        charge.update_penalty(save=False)

        # =====================================================
        # مبلغ نهایی
        # =====================================================

        amount = (
                charge.total_charge_month
                or charge.amount
                or 0
        )

        if amount <= 0:
            return Response(
                {
                    'success': False,
                    'message': 'مبلغ شارژ معتبر نیست.',
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # ثبت اطلاعات پرداخت
        # =====================================================

        charge.bank = bank

        charge.transaction_reference = (
            transaction_reference
        )

        charge.payment_date = payment_date

        charge.payment_gateway = 'کارت به کارت'

        # بسیار مهم:
        # هنوز مدیر پرداخت را تأیید نکرده
        charge.is_paid = False

        # درخواست پرداخت ثبت شده
        charge.payment_pending = True

        charge.payment_submitted_at = timezone.now()

        # =====================================================
        # ذخیره
        # =====================================================

        charge.save(
            update_fields=[
                'bank',
                'transaction_reference',
                'payment_date',
                'payment_gateway',
                'is_paid',
                'payment_pending',
                'payment_submitted_at',
                'penalty_amount',
                'total_charge_month',
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

                'charge': {
                    'id': charge.id,

                    'title': charge.title,

                    'unit_id': charge.unit_id,

                    'unit_number': (
                        getattr(
                            charge.unit,
                            'unit',
                            None
                        )
                        if charge.unit
                        else None
                    ),

                    'amount': (
                            charge.total_charge_month
                            or amount
                    ),

                    'transaction_reference': (
                        charge.transaction_reference
                    ),

                    'payment_date': (
                        charge.payment_date
                    ),

                    'payment_gateway': (
                        charge.payment_gateway
                    ),

                    # هنوز تأیید نشده
                    'is_paid': False,

                    # در انتظار تأیید مدیر
                    'payment_pending': True,

                    'payment_submitted_at': (
                        charge.payment_submitted_at
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
            status=status.HTTP_200_OK
        )
class ChargePaymentBanksView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, charge_id):

        # =====================================================
        # پیدا کردن شارژ
        # =====================================================

        charge = UnifiedCharge.objects.filter(
            id=charge_id,
            is_paid=False,
            send_notification=True,
        ).select_related(
            'house',
            'unit',
        ).first()

        if not charge:
            return Response(
                {
                    'success': False,
                    'message': 'شارژ مورد نظر پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی واحد
        # =====================================================

        unit = charge.unit

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد مربوط به شارژ پیدا نشد.',
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # آیا کاربر مالک واحد است؟
        # =====================================================

        is_owner = (
                unit.user_id == request.user.id
        )

        # =====================================================
        # آیا کاربر مستأجر فعال واحد است؟
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
                    'message': 'این شارژ متعلق به شما نیست.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # بانک‌های ساختمان
        #
        # نکته مهم:
        # بانک متعلق به ساختمان/مدیر است، نه مستأجر.
        # بنابراین نباید user=request.user بگذاریم.
        # =====================================================

        banks = Bank.objects.filter(
            house=charge.house,
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

                'banks': [
                    {
                        'id': bank.id,
                        'bank_name': bank.bank_name,
                        'account_no': bank.account_no,
                        'account_holder_name':
                            bank.account_holder_name,
                        'sheba_number':
                            bank.sheba_number,
                        'cart_number':
                            bank.cart_number,
                        'is_default':
                            bank.is_default,
                    }
                    for bank in banks
                ],
            },
            status=status.HTTP_200_OK,
        )
class OnlineChargePaymentView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, charge_id):

        # =============================
        # پیدا کردن شارژ
        # =============================

        charge = UnifiedCharge.objects.filter(
            id=charge_id,
            user=request.user,
            is_paid=False,
            send_notification=True
        ).select_related(
            'unit',
            'house'
        ).first()

        if not charge:
            return Response(
                {
                    'success': False,
                    'message': 'شارژ مورد نظر پیدا نشد یا متعلق به شما نیست.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =============================
        # بروزرسانی جریمه
        # =============================

        charge.update_penalty(save=True)

        amount = (
                charge.total_charge_month
                or charge.amount
                or 0
        )

        if amount <= 0:
            return Response(
                {
                    'success': False,
                    'message': 'مبلغ شارژ معتبر نیست.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =============================
        # پیدا کردن درگاه ساختمان
        # =============================

        gateway = HousePaymentGateway.objects.filter(
            house=charge.house,
            is_active=True
        ).first()

        # هیچ درگاهی ثبت نشده
        if not gateway:
            return Response(
                {
                    'success': False,
                    'gateway_available': False,
                    'message': 'درگاه پرداخت برای ساختمان شما ثبت نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =============================
        # اطلاعات درگاه
        # =============================

        gateway_type = gateway.gateway_type
        merchant_id = gateway.merchant_id

        # merchant_id خالی
        if not merchant_id:
            return Response(
                {
                    'success': False,
                    'gateway_available': False,
                    'message': 'اطلاعات درگاه پرداخت ساختمان کامل نیست.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =============================
        # زرین پال
        # =============================

        if gateway_type == HousePaymentGateway.GatewayType.ZARINPAL:

            amount_rial = int(amount) * 10

            callback_url = (
                f"{settings.CallbackURLCharge}"
                f"?charge_id={charge.id}"
            )

            req_data = {
                'merchant_id': merchant_id,
                'amount': amount_rial,
                'callback_url': callback_url,
                'description': f'پرداخت {charge.title}',
            }

            headers = {
                'accept': 'application/json',
                'content-type': 'application/json'
            }

            try:

                req = requests.post(
                    settings.ZP_API_REQUEST,
                    json=req_data,
                    headers=headers,
                    timeout=15
                )

                response_data = req.json()

            except requests.RequestException:

                return Response(
                    {
                        'success': False,
                        'gateway': gateway_type,
                        'message': 'ارتباط با درگاه پرداخت برقرار نشد.'
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )

            except ValueError:

                return Response(
                    {
                        'success': False,
                        'gateway': gateway_type,
                        'message': 'پاسخ نامعتبر از درگاه دریافت شد.'
                    },
                    status=status.HTTP_502_BAD_GATEWAY
                )

            # =============================
            # موفقیت
            # =============================

            if (
                    req.status_code == 200
                    and response_data.get('data')
                    and response_data['data'].get('authority')
            ):
                authority = response_data['data']['authority']

                payment_url = (
                    f"{settings.ZP_API_STARTPAY}"
                    f"{authority}"
                )

                return Response(
                    {
                        'success': True,
                        'gateway': gateway_type,
                        'charge_id': charge.id,
                        'amount': amount,
                        'payment_url': payment_url
                    },
                    status=status.HTTP_200_OK
                )

            # =============================
            # خطای درگاه
            # =============================

            errors = response_data.get('errors', {})

            return Response(
                {
                    'success': False,
                    'gateway': gateway_type,
                    'message': 'خطا در ایجاد تراکنش درگاه.',
                    'error_code': errors.get('code'),
                    'error_message': errors.get('message')
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =============================
        # درگاه‌های آینده
        # =============================

        return Response(
            {
                'success': False,
                'gateway': gateway_type,
                'message': 'این نوع درگاه هنوز پیاده‌سازی نشده است.'
            },
            status=status.HTTP_501_NOT_IMPLEMENTED
        )
class MobileChargeListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # =====================================================
        # پیدا کردن واحدهایی که کاربر مالک آنهاست
        # =====================================================

        owner_unit_ids = Unit.objects.filter(
            user=user,
            is_active=True,
        ).values_list(
            'id',
            flat=True
        )

        # =====================================================
        # پیدا کردن واحدهایی که کاربر مستأجر فعال آنهاست
        # =====================================================

        renter_unit_ids = Renter.objects.filter(
            user=user,
            renter_is_active=True,
            unit__isnull=False,
            unit__is_active=True,
        ).values_list(
            'unit_id',
            flat=True
        )

        # =====================================================
        # ترکیب واحدهای مالک + مستأجر
        # =====================================================

        unit_ids = set(owner_unit_ids) | set(renter_unit_ids)

        # اگر کاربر هیچ واحدی نداشت
        if not unit_ids:
            return Response(
                {
                    'success': True,
                    'count': 0,
                    'charges': []
                },
                status=status.HTTP_200_OK
            )

        # =====================================================
        # دریافت شارژهای این واحدها
        # =====================================================

        charges = UnifiedCharge.objects.filter(
            unit_id__in=unit_ids,
            unit__is_active=True,
            send_notification=True,
        ).select_related(
            'unit',
            'house',
        ).order_by(
            '-created_at'
        )

        data = []

        for charge in charges:
            # بروزرسانی جریمه
            charge.update_penalty()

            serializer = MobileChargeListSerializer(
                charge,
                context={
                    'request': request,
                }
            )

            data.append(serializer.data)

        return Response(
            {
                'success': True,
                'count': len(data),
                'charges': data
            },
            status=status.HTTP_200_OK
        )
class MobileChargeDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, charge_id):
        charge = UnifiedCharge.objects.filter(
            id=charge_id,
            unit__user=request.user,
            unit__is_active=True,
            send_notification=True,
        ).select_related(
            'unit',
            'house'
        ).first()

        if not charge:
            return Response(
                {
                    'success': False,
                    'message': 'شارژ مورد نظر پیدا نشد یا متعلق به شما نیست.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        charge.update_penalty()

        return Response(
            {
                'success': True,
                'charge': MobileChargeDetailSerializer(
                    charge
                ).data
            },
            status=status.HTTP_200_OK
        )
class MobilePaymentHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user


        # =====================================================
        # واحدهای مالک
        # =====================================================

        owner_units = list(
            Unit.objects.filter(
                user=user
            ).values_list(
                "id",
                flat=True
            )
        )



        # =====================================================
        # واحدهای مستأجر
        # =====================================================

        renter_units = list(
            Unit.objects.filter(
                renters__user=user,
                renters__renter_is_active=True,
            ).values_list(
                "id",
                flat=True
            ).distinct()
        )



        # =====================================================
        # مجموع واحدهای کاربر
        # =====================================================

        unit_ids = list(
            set(owner_units + renter_units)
        )



        if not unit_ids:
            return Response({
                "success": True,
                "count": 0,
                "payments": [],
            })

        # =====================================================
        # تراکنش‌ها
        #
        # مهم:
        # 1. فقط واحدهای متعلق به کاربر
        # 2. فقط Fundهای متعلق به خود کاربر
        # 3. هیچ فیلتر is_paid نداریم
        # =====================================================

        payments = Fund.objects.filter(
            unit_id__in=unit_ids,
        ).select_related(
            "unit",
            "unit__myhouse",
        ).order_by(
            "-payment_date",
            "-id"
        )


        result = []

        for fund in payments:



            # -------------------------------------------------
            # اطلاعات واحد
            # -------------------------------------------------

            unit_number = None
            house_name = None

            if fund.unit:
                unit_number = fund.unit.unit

                if fund.unit.myhouse:
                    house_name = fund.unit.myhouse.name

            # -------------------------------------------------
            # نوع پرداخت کننده
            # -------------------------------------------------

            payer_type = None
            payer_display_name = None

            if fund.unit:

                # ---------------------------------------------
                # مالک
                # ---------------------------------------------

                if fund.unit.user_id == user.id:

                    payer_type = "owner"

                    payer_display_name = (
                            fund.unit.owner_name
                            or fund.payer_name
                            or ""
                    )

                # ---------------------------------------------
                # مستأجر
                # ---------------------------------------------

                else:

                    renter = fund.unit.renters.filter(
                        user=user,
                        renter_is_active=True,
                    ).first()

                    if renter:
                        payer_type = "renter"

                        payer_display_name = (
                                renter.renter_name
                                or fund.payer_name
                                or ""
                        )

            # -------------------------------------------------
            # نام پرداخت کننده
            # -------------------------------------------------

            payer_name = None

            if unit_number is not None:

                if payer_display_name:

                    payer_name = (
                        f"واحد {unit_number} - "
                        f"{payer_display_name}"
                    )

                else:

                    payer_name = (
                        f"واحد {unit_number}"
                    )

            # -------------------------------------------------
            # خروجی
            # -------------------------------------------------

            result.append({

                "id": fund.id,

                "doc_number": getattr(
                    fund,
                    "doc_number",
                    fund.id
                ),

                "amount": str(
                    getattr(
                        fund,
                        "amount",
                        0
                    ) or 0
                ),

                "debtor_amount": str(
                    getattr(
                        fund,
                        "debtor_amount",
                        0
                    ) or 0
                ),

                "creditor_amount": str(
                    getattr(
                        fund,
                        "creditor_amount",
                        0
                    ) or 0
                ),

                "payment_date": (
                    fund.payment_date.isoformat()
                    if fund.payment_date
                    else None
                ),

                "transaction_no": getattr(
                    fund,
                    "transaction_no",
                    None
                ),

                "payment_description": (
                        getattr(
                            fund,
                            "payment_description",
                            ""
                        ) or ""
                ),

                "payer_name": payer_name,

                "receiver_name": getattr(
                    fund,
                    "receiver_name",
                    None
                ),

                "is_initial": bool(
                    getattr(
                        fund,
                        "is_initial",
                        False
                    )
                ),

                "is_received_money": bool(
                    getattr(
                        fund,
                        "is_received_money",
                        False
                    )
                ),

                "is_paid_money": bool(
                    getattr(
                        fund,
                        "is_paid_money",
                        False
                    )
                ),

                # فقط مقدار را برمی‌گردانیم
                # هیچ فیلتری روی is_paid نداریم
                "is_paid": bool(
                    getattr(
                        fund,
                        "is_paid",
                        False
                    )
                ),

                "unit_number": unit_number,

                "house_name": house_name,

                "payer_type": payer_type,

                "created_at": (
                    fund.created_at.isoformat()
                    if fund.created_at
                    else None
                ),
            })



        return Response({
            "success": True,
            "count": len(result),
            "payments": result,
        })
