"""Payments Messages API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class MessageListAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # ==========================================
        # واحدهای کاربر
        # ==========================================

        units = Unit.objects.filter(
            is_active=True
        ).filter(
            Q(user=user) |
            Q(
                renters__user=user,
                renters__renter_is_active=True
            )
        ).distinct()

        unit_ids = list(
            units.values_list(
                'id',
                flat=True
            )
        )

        # ==========================================
        # پیام‌های مربوط به واحدهای کاربر
        # ==========================================

        messages = MessageToUser.objects.filter(
            notified_units__in=unit_ids,
            is_active=True
        ).distinct().order_by(
            '-created_at'
        )

        # ==========================================
        # وضعیت خواندن پیام‌ها
        # ==========================================

        read_statuses = MessageReadStatus.objects.filter(
            message__in=messages,
            unit_id__in=unit_ids
        )

        message_read_status = {}

        for read_status in read_statuses:

            message_id = read_status.message_id

            if message_id not in message_read_status:
                message_read_status[message_id] = {
                    'is_read': False,
                    'read_at': None,
                }

            if read_status.is_read:

                message_read_status[message_id][
                    'is_read'
                ] = True

                if read_status.read_at:

                    current_read_at = (
                        message_read_status[message_id][
                            'read_at'
                        ]
                    )

                    if (
                            current_read_at is None
                            or read_status.read_at < current_read_at
                    ):
                        message_read_status[message_id][
                            'read_at'
                        ] = read_status.read_at

        # ==========================================
        # Serializer
        # ==========================================

        serializer = MessageToUserSerializer(
            messages,
            many=True,
            context={
                'request': request,
                'message_read_status':
                    message_read_status,
            }
        )

        # ==========================================
        # تعداد خوانده نشده
        # ==========================================

        unread_count = sum(
            1
            for message in messages
            if not message_read_status.get(
                message.id,
                {}
            ).get(
                'is_read',
                False
            )
        )

        return Response({
            'success': True,
            'count': messages.count(),
            'unread_count': unread_count,
            'messages': serializer.data,
        })
class MessageDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, message_id):

        user = request.user

        # ==========================================
        # واحدهای کاربر
        # ==========================================

        units = Unit.objects.filter(
            is_active=True
        ).filter(
            Q(user=user) |
            Q(
                renters__user=user,
                renters__renter_is_active=True
            )
        ).distinct()

        unit_ids = list(
            units.values_list(
                'id',
                flat=True
            )
        )

        # ==========================================
        # پیام
        # ==========================================

        message = (
            MessageToUser.objects
            .filter(
                id=message_id,
                notified_units__in=unit_ids,
                is_active=True
            )
            .distinct()
            .first()
        )

        if not message:
            return Response(
                {
                    'success': False,
                    'message':
                        'پیام مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ==========================================
        # وضعیت خواندن
        # ==========================================

        read_statuses = (
            MessageReadStatus.objects.filter(
                message=message,
                unit_id__in=unit_ids
            )
        )

        is_read = False
        read_at = None

        for item in read_statuses:

            if item.is_read:

                is_read = True

                if item.read_at:

                    if (
                            read_at is None
                            or item.read_at < read_at
                    ):
                        read_at = item.read_at

        serializer = MessageToUserSerializer(
            message,
            context={
                'request': request,
                'message_read_status': {
                    message.id: {
                        'is_read': is_read,
                        'read_at': read_at,
                    }
                }
            }
        )

        return Response({
            'success': True,
            'message': serializer.data,
        })
class MessageReadAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):

        user = request.user

        # ==========================================
        # واحدهای کاربر
        # ==========================================

        units = Unit.objects.filter(
            is_active=True
        ).filter(
            Q(user=user) |
            Q(
                renters__user=user,
                renters__renter_is_active=True
            )
        ).distinct()

        # ==========================================
        # پیام
        # ==========================================

        message = (
            MessageToUser.objects
            .filter(
                id=message_id,
                notified_units__in=units,
                is_active=True
            )
            .distinct()
            .first()
        )

        if not message:
            return Response(
                {
                    'success': False,
                    'message':
                        'پیام مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        now = timezone.now()

        updated = []

        # ==========================================
        # ثبت Read برای واحدهای مربوطه
        # ==========================================

        for unit in units:

            if not message.notified_units.filter(
                    id=unit.id
            ).exists():
                continue

            read_status, created = (
                MessageReadStatus.objects.get_or_create(
                    message=message,
                    unit=unit,
                    defaults={
                        'is_read': True,
                        'read_at': now,
                    }
                )
            )

            if not created and not read_status.is_read:
                read_status.is_read = True
                read_status.read_at = now

                read_status.save(
                    update_fields=[
                        'is_read',
                        'read_at',
                    ]
                )

            updated.append(unit.id)

        return Response({
            'success': True,
            'message': 'پیام خوانده شد.',
            'message_id': message.id,
            'read_at': now,
            'units': updated,
        })
class UserPayMoneyListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_user_units(self, user):

        owner_units = Unit.objects.filter(
            user=user,
            is_active=True,
        )

        renter_units = Unit.objects.filter(
            renters__user=user,
            renters__renter_is_active=True,
            is_active=True,
        )

        return (
                owner_units | renter_units
        ).distinct()

    def get(self, request):

        user = request.user

        units = self.get_user_units(user)

        payments = UserPayMoney.objects.filter(
            user=user,
            unit__in=units,
            is_active=True,
        ).select_related(
            'unit',
            'house',
            'bank',
        ).prefetch_related(
            'documents',
        ).order_by(
            '-created_at'
        )

        serializer = UserPayMoneySerializer(
            payments,
            many=True,
            context={
                'request': request,
            }
        )

        return Response(
            {
                'success': True,
                'count': payments.count(),
                'payments': serializer.data,
            },
            status=status.HTTP_200_OK,
        )

    @transaction.atomic
    def post(self, request):

        user = request.user

        serializer = CreateUserPayMoneySerializer(
            data=request.data
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # واحدهای کاربر
        # =====================================================

        units = self.get_user_units(user)

        unit = units.select_related(
            'myhouse'
        ).first()

        if not unit:
            return Response(
                {
                    'success': False,
                    'message': (
                        'برای کاربر شما واحد فعالی پیدا نشد.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # ساختمان
        # =====================================================

        house = unit.myhouse

        if not house:
            return Response(
                {
                    'success': False,
                    'message': (
                        'ساختمان مربوط به واحد پیدا نشد.'
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # ایجاد کمک
        # =====================================================

        payment = UserPayMoney.objects.create(
            user=user,
            unit=unit,
            house=house,

            amount=serializer.validated_data[
                'amount'
            ],

            description=serializer.validated_data[
                'description'
            ],

            register_date=serializer.validated_data[
                'register_date'
            ],

            details=serializer.validated_data.get(
                'details'
            ),

            payer_name=serializer.validated_data.get(
                'payer_name'
            ),

            is_paid=False,
            is_active=True,
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'success': True,

                'message': (
                    'کمک شما با موفقیت ثبت شد.'
                ),

                'payment': UserPayMoneySerializer(
                    payment,
                    context={
                        'request': request,
                    }
                ).data,
            },
            status=status.HTTP_201_CREATED,
        )
class UserPayMoneyPaymentMethodsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):

        user = request.user

        # =====================================================
        # پیدا کردن کمک
        # =====================================================

        payment = UserPayMoney.objects.filter(
            id=payment_id,
            user=user,
            is_active=True,
        ).select_related(
            'unit',
            'house',
        ).first()

        if not payment:
            return Response(
                {
                    'success': False,
                    'message': (
                        'کمک مورد نظر پیدا نشد یا متعلق به شما نیست.'
                    ),
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی واحد
        # =====================================================

        if not payment.unit:
            return Response(
                {
                    'success': False,
                    'message': 'واحد مربوط به این کمک مشخص نیست.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # بررسی دسترسی کاربر
        #
        # مالک واحد
        # =====================================================

        is_owner = (
                payment.unit.user_id == user.id
        )

        # =====================================================
        # مستأجر فعال
        # =====================================================

        is_active_renter = Renter.objects.filter(
            unit=payment.unit,
            user=user,
            renter_is_active=True,
        ).exists()

        # =====================================================
        # بررسی دسترسی
        # =====================================================

        if not is_owner and not is_active_renter:
            return Response(
                {
                    'success': False,
                    'message': (
                        'این کمک متعلق به شما نیست.'
                    ),
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # قبلاً پرداخت شده
        # =====================================================

        if payment.is_paid:
            return Response(
                {
                    'success': False,
                    'status': 'paid',
                    'message': (
                        'این کمک قبلاً پرداخت شده است.'
                    ),
                    'is_paid': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # درگاه پرداخت ساختمان
        # =====================================================

        gateway = HousePaymentGateway.objects.filter(
            house=payment.house,
            is_active=True,
        ).first()

        # =====================================================
        # حساب‌های بانکی ساختمان
        # =====================================================

        banks = Bank.objects.filter(
            house=payment.house,
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

                'payment': {
                    'id': payment.id,

                    'amount': payment.amount,

                    'description': payment.description,

                    'register_date': (
                        payment.register_date
                    ),

                    'is_paid': payment.is_paid,
                },

                'payment_banks': [
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

                'payment_methods': [

                    {
                        'type': 'manual',

                        'title': 'کارت به کارت',

                        'available': banks.exists(),

                        'description': (
                            'واریز مبلغ کمک به حساب ساختمان '
                            'و ثبت کد پیگیری'
                            if banks.exists()
                            else
                            'حساب بانکی برای ساختمان ثبت نشده است.'
                        ),
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
                            else
                            'درگاه پرداخت برای ساختمان شما ثبت نشده است.'
                        ),
                    },
                ],
            },
            status=status.HTTP_200_OK,
        )
class ManualUserPayMoneyPaymentView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, payment_id):

        serializer = ManualUserPayMoneyPaymentSerializer(
            data=request.data,
            context={
                'request': request,
                'payment_id': payment_id,
            }
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        payment = serializer.validated_data['payment']
        bank = serializer.validated_data['bank']

        transaction_reference = (
            serializer.validated_data['transaction_reference']
        )

        payment_date = (
            serializer.validated_data['payment_date']
        )

        # =====================================================
        # قفل رکورد
        # =====================================================

        payment = (
            UserPayMoney.objects
            .select_for_update()
            .select_related(
                'unit',
                'house',
            )
            .get(pk=payment.pk)
        )

        # =====================================================
        # بررسی پرداخت قبلی
        # =====================================================

        if payment.is_paid:
            return Response(
                {
                    'success': False,
                    'message': 'این کمک قبلاً پرداخت شده است.',
                    'is_paid': True,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # اطلاعات پرداخت
        # =====================================================

        payment.bank = bank

        payment.transaction_reference = (
            transaction_reference
        )

        payment.payment_date = payment_date

        payment.payment_gateway = 'کارت به کارت'

        # پرداخت قطعی است
        payment.is_paid = True

        payment.save(
            update_fields=[
                'bank',
                'transaction_reference',
                'payment_date',
                'payment_gateway',
                'is_paid',
            ]
        )

        # =====================================================
        # ثبت Fund
        # =====================================================

        content_type = ContentType.objects.get_for_model(
            UserPayMoney
        )

        fund = Fund.objects.create(

            content_type=content_type,

            object_id=payment.id,

            unit=payment.unit,

            house=payment.house,

            bank=bank,

            debtor_amount=payment.amount,

            amount=payment.amount,

            creditor_amount=0,

            user=request.user,

            payer_name=(
                payment.unit.get_label
                if payment.unit
                else payment.payer_name
            ),

            payment_date=payment.payment_date,

            payment_description=(
                f"پرداخت به ساختمان: "
                f"{(payment.description or '')[:50]}"
            ),
            is_paid=True,

            transaction_no=(
                payment.transaction_reference
            ),

            payment_gateway='کارت به کارت',
        )

        # =====================================================
        # ثبت تراکنش بانکی
        # =====================================================

        BankTransactionService.deposit(
            user=request.user,

            bank=payment.bank,

            unit=payment.unit,

            amount=Decimal(payment.amount),

            description=(
                f"پرداخت به ساختمان: "
                f"{(payment.description or '')[:50]}"
            ),

            content_object=payment.unit,

            payment_date=payment.payment_date,

            transaction_no=payment.transaction_reference,

            gateway='کارت به کارت',

            house=payment.house,
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'success': True,

                'message': (
                    'پرداخت کمک با موفقیت ثبت شد.'
                ),

                'payment': {
                    'id': payment.id,

                    'amount': payment.amount,

                    'description': payment.description,

                    'payment_date': (
                        payment.payment_date
                    ),

                    'transaction_reference': (
                        payment.transaction_reference
                    ),

                    'payment_gateway': (
                        payment.payment_gateway
                    ),

                    'is_paid': payment.is_paid,
                },

                'fund': {
                    'id': fund.id,

                    'amount': fund.amount,

                    'payment_date': (
                        fund.payment_date
                    ),

                    'transaction_no': (
                        fund.transaction_no
                    ),

                    'payment_description': (
                        fund.payment_description
                    ),
                },

                'bank': {
                    'id': bank.id,

                    'bank_name': bank.bank_name,

                    'account_holder_name': (
                        bank.account_holder_name
                    ),

                    'cart_number': (
                        bank.cart_number
                    ),
                },
            },
            status=status.HTTP_200_OK,
        )
