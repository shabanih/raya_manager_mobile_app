"""Dashboards API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class MeView(APIView):
    authentication_classes = [
        JWTAuthentication,
    ]

    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        user = request.user

        # =====================================================
        # تشخیص نوع کاربر
        # =====================================================

        is_middle_admin = getattr(
            user,
            'is_middle_admin',
            False
        )

        is_unit = getattr(
            user,
            'is_unit',
            False
        )

        # =====================================================
        # اطلاعات پایه کاربر
        # =====================================================

        user_data = {
            'id': user.id,
            'username': user.username,
            'full_name': getattr(
                user,
                'full_name',
                ''
            ),
            'mobile': getattr(
                user,
                'mobile',
                ''
            ),
            'user_type': (
                'manager'
                if is_middle_admin
                else 'resident'
            ),
            'is_middle_admin': is_middle_admin,
            'is_unit': is_unit,
        }

        # =====================================================
        # اطلاعات واحدها
        # =====================================================

        units_data = []

        house_data = {}

        # =====================================================
        # ساکن
        #
        # ساکن می‌تواند:
        #
        # 1. مالک واحد باشد
        # 2. مستأجر واحد باشد
        # =====================================================

        if is_unit:

            # =================================================
            # واحدهای مالک
            # =================================================

            owner_units = (
                Unit.objects
                .filter(
                    user=user,
                    is_active=True
                )
                .select_related('myhouse')
            )

            # =================================================
            # واحدهای مستأجر
            # =================================================

            renter_units = (
                Unit.objects
                .filter(
                    renters__user=user,
                    renters__renter_is_active=True,
                    is_active=True
                )
                .select_related('myhouse')
            )

            # =================================================
            # ترکیب مالک + مستأجر
            # =================================================

            units = (
                    owner_units |
                    renter_units
            ).distinct().order_by('unit')

            # =================================================
            # ساخت اطلاعات واحد
            # =================================================

            for unit in units:

                # ---------------------------------------------
                # آیا این کاربر در این واحد مستأجر است؟
                # ---------------------------------------------

                active_renter = (
                    unit.renters
                    .filter(
                        user=user,
                        renter_is_active=True
                    )
                    .first()
                )

                is_renter = (
                        active_renter is not None
                )

                # ---------------------------------------------
                # نام مالک
                # ---------------------------------------------

                owner_name = (
                        unit.owner_name or ''
                )

                # ---------------------------------------------
                # موبایل مالک
                # ---------------------------------------------

                owner_mobile = (
                        unit.owner_mobile or ''
                )

                # ---------------------------------------------
                # اطلاعات مستأجر
                # ---------------------------------------------

                renter_name = ''

                renter_mobile = ''

                if active_renter:
                    renter_name = (
                            active_renter.renter_name
                            or getattr(
                        active_renter.user,
                        'full_name',
                        ''
                    )
                            or ''
                    )

                    renter_mobile = (
                            active_renter.renter_mobile
                            or getattr(
                        active_renter.user,
                        'mobile',
                        ''
                    )
                            or ''
                    )

                # =================================================
                # اطلاعات واحد
                # =================================================

                units_data.append({

                    'id': unit.id,

                    'unit': unit.unit,

                    'floor_number':
                        unit.floor_number,

                    'area':
                        str(unit.area)
                        if unit.area is not None
                        else '',

                    'bedrooms_count':
                        unit.bedrooms_count,

                    'parking_number':
                        unit.parking_number,

                    'parking_place':
                        unit.parking_place,

                    'unit_phone':
                        unit.unit_phone,

                    # ---------------------------------------------
                    # وضعیت مالک / مستأجر برای کاربر فعلی
                    # ---------------------------------------------

                    'is_renter':
                        is_renter,

                    # ---------------------------------------------
                    # اطلاعات مالک
                    # ---------------------------------------------

                    'owner_name':
                        owner_name,

                    'owner_mobile':
                        owner_mobile,

                    # ---------------------------------------------
                    # اطلاعات مستأجر
                    # ---------------------------------------------

                    'renter_name':
                        renter_name,

                    'renter_mobile':
                        renter_mobile,

                    # ---------------------------------------------
                    # تعداد ساکنین
                    # ---------------------------------------------

                    'people_count':
                        unit.people_count or 0,

                    # ---------------------------------------------
                    # وضعیت سکونت
                    # ---------------------------------------------

                    'status_residence':
                        unit.status_residence or '',

                    # ---------------------------------------------
                    # ساختمان
                    # ---------------------------------------------

                    'house_id':
                        unit.myhouse_id,

                    'house_name':
                        (
                            unit.myhouse.name
                            if unit.myhouse
                            else ''
                        ),
                })

                # =================================================
                # ساختمان واحد
                # =================================================

                if unit.myhouse and not house_data:
                    house = unit.myhouse

                    house_data = {

                        'id':
                            house.id,

                        'name':
                            house.name,

                        'floor_counts':
                            house.floor_counts,

                        'unit_counts':
                            house.unit_counts,

                        'phone':
                            house.phone,

                        'user_type':
                            house.user_type or '',

                        'city':
                            house.city or '',

                        'address':
                            house.address,

                        'subdomain':
                            house.subdomain or '',
                    }

        # =====================================================
        # اگر کاربر مدیر است
        # =====================================================

        elif is_middle_admin:

            house = (
                MyHouse.objects
                .filter(
                    user=user,
                    is_active=True
                )
                .order_by('-created_at')
                .first()
            )

            if house:
                house_data = {

                    'id':
                        house.id,

                    'name':
                        house.name,

                    'floor_counts':
                        house.floor_counts,

                    'unit_counts':
                        house.unit_counts,

                    'phone':
                        house.phone,

                    'user_type':
                        house.user_type or '',

                    'city':
                        house.city or '',

                    'address':
                        house.address,

                    'subdomain':
                        house.subdomain or '',
                }


        # =====================================================
        # پاسخ نهایی
        # =====================================================

        return Response({

            'success':
                True,

            'user':
                user_data,

            'house':
                house_data,

            'units':
                units_data,
        })
class ManagerDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        # =========================================================
        # فقط مدیر ساختمان
        # =========================================================
        if not user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =========================================================
        # ساختمان مدیر
        # =========================================================
        house = MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # =========================================================
        # واحدهای ساختمان
        # =========================================================
        units = Unit.objects.filter(
            myhouse=house,
            is_active=True
        )

        units_count = units.count()

        # =========================================================
        # تعداد ساکنین
        # =========================================================
        residents_count = house.residents.filter(
            is_active=True
        ).count()

        # =========================================================
        # شارژهای ساختمان
        # =========================================================
        charges = UnifiedCharge.objects.filter(
            house=house,
            unit__is_active=True
        )

        total_charges = charges.count()

        paid_charges = charges.filter(
            is_paid=True
        )

        unpaid_charges = charges.filter(
            is_paid=False,
            payment_pending=False
        )

        pending_charges = charges.filter(
            payment_pending=True
        )

        paid_count = paid_charges.count()
        unpaid_count = unpaid_charges.count()
        pending_count = pending_charges.count()

        # =========================================================
        # مبلغ بدهی
        # =========================================================
        total_debt = sum(
            (
                    charge.total_payable_with_previous or 0
            )
            for charge in unpaid_charges
        )

        # =========================================================
        # مبلغ پرداخت شده
        # =========================================================
        total_paid = (
                paid_charges.aggregate(
                    total=Sum('total_charge_month')
                )['total'] or 0
        )

        # =========================================================
        # موجودی صندوق
        #
        # همان منطق داشبورد اصلی:
        #
        # موجودی = دریافتی - پرداختی
        # =========================================================

        fund_totals = (
            Fund.objects
            .filter(
                user=user
            )
            .aggregate(
                total_income=Sum('debtor_amount'),
                total_expense=Sum('creditor_amount')
            )
        )

        total_fund_income = (
                fund_totals['total_income'] or 0
        )

        total_fund_expense = (
                fund_totals['total_expense'] or 0
        )

        fund_balance = (
                total_fund_income -
                total_fund_expense
        )

        # =========================================================
        # اعتبار خریداری شده پیامک
        #
        # فقط پرداخت‌های موفق
        # =========================================================
        middle_current_credit = (
                SmsCredit.objects
                .filter(
                    user=user,
                    is_paid=True
                )
                .aggregate(
                    total=Sum('amount')
                )['total']
                or Decimal('0')
        )

        # =========================================================
        # آخرین شارژ
        # =========================================================
        latest_charge = charges.order_by(
            '-created_at'
        ).first()

        latest_charge_data = None

        if latest_charge:
            latest_charge_data = {
                'id': latest_charge.id,

                'unit_id': latest_charge.unit_id,

                'unit': (
                    latest_charge.unit.unit
                    if latest_charge.unit
                    else None
                ),

                'base_charge': (
                        latest_charge.base_charge or 0
                ),

                'penalty': (
                        latest_charge.penalty_amount or 0
                ),

                'payable': (
                        latest_charge.total_payable_with_previous or 0
                ),

                'is_paid': latest_charge.is_paid,

                'payment_date': (
                    latest_charge.payment_date
                    if latest_charge.payment_date
                    else None
                ),

                'created_at': (
                    latest_charge.created_at
                    if latest_charge.created_at
                    else None
                ),
            }

        # =========================================================
        # اطلاعات واحدها
        # =========================================================
        units_data = []

        for unit in units.order_by('unit'):
            unit_charges = charges.filter(
                unit=unit
            )

            unit_paid = unit_charges.filter(
                is_paid=True
            ).count()

            unit_unpaid = unit_charges.filter(
                is_paid=False,
                payment_pending=False
            ).count()

            unit_pending = unit_charges.filter(
                payment_pending=True
            ).count()

            unit_debt = sum(
                (
                        charge.total_payable_with_previous or 0
                )
                for charge in unit_charges.filter(
                    is_paid=False
                )
            )

            units_data.append(
                {
                    'id': unit.id,
                    'unit': unit.unit,
                    'floor_number': unit.floor_number,
                    'area': unit.area,
                    'bedrooms_count': unit.bedrooms_count,

                    'charges_count': unit_charges.count(),

                    'paid_count': unit_paid,

                    'unpaid_count': unit_unpaid,

                    'pending_count': unit_pending,

                    'debt': unit_debt,

                    'sms_credit': middle_current_credit,
                }
            )

        # =========================================================
        # Response
        # =========================================================
        return Response(
            {
                'success': True,

                # =================================================
                # User
                # =================================================
                'user': {
                    'id': user.id,
                    'full_name': user.full_name,
                    'username': user.username,
                    'mobile': user.mobile,
                    'is_middle_admin': True,
                    'is_unit': user.is_unit,
                    'user_type': 'manager',
                },

                # =================================================
                # House
                # =================================================
                'house': {
                    'id': house.id,
                    'name': house.name,
                    'subdomain': house.subdomain,
                    'city': house.city,
                    'address': house.address,
                    'floor_counts': house.floor_counts,
                    'unit_counts': house.unit_counts,
                },

                # =================================================
                # Statistics
                # =================================================
                'statistics': {

                    # -------------------------------
                    # واحدها
                    # -------------------------------
                    'units_count': units_count,

                    'residents_count': residents_count,

                    # -------------------------------
                    # شارژ
                    # -------------------------------
                    'total_charges': total_charges,

                    'paid_charges': paid_count,

                    'unpaid_charges': unpaid_count,

                    'pending_charges': pending_count,

                    'total_debt': total_debt,

                    'total_paid': total_paid,

                    # -------------------------------
                    # صندوق
                    # -------------------------------
                    'fund_income': total_fund_income,

                    'fund_expense': total_fund_expense,

                    'fund_balance': fund_balance,

                    # -------------------------------
                    # پیامک
                    # -------------------------------
                    'sms_credit': middle_current_credit,

                    # -------------------------------
                    # مقادیر عمومی
                    # -------------------------------
                    'total_income': 0,

                    'total_expense': 0,

                    'balance': fund_balance,
                },

                # =================================================
                # Units
                # =================================================
                'units': units_data,

                # =================================================
                # Latest Charge
                # =================================================
                'latest_charge': latest_charge_data,
            }
        )
class DashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        # =====================================================
        # 1. واحدهای مالک
        # =====================================================

        owner_units = Unit.objects.filter(
            user=user,
            is_active=True
        ).select_related(
            'myhouse'
        )

        # =====================================================
        # 2. واحدهای مستأجر فعال
        # =====================================================

        renter_units = Unit.objects.filter(
            renters__user=user,
            renters__renter_is_active=True,
            is_active=True
        ).select_related(
            'myhouse'
        )

        # =====================================================
        # 3. ترکیب واحدهای مالک و مستأجر
        # =====================================================

        units = (
                owner_units | renter_units
        ).distinct()


        # =====================================================
        # 4. شارژهای مربوط به واحدهای کاربر
        # =====================================================

        charges = UnifiedCharge.objects.filter(
            unit__in=units,
            unit__is_active=True,
            send_notification=True
        ).select_related(
            'unit',
            'house'
        )

        # =====================================================
        # 5. به‌روزرسانی جریمه شارژهای پرداخت نشده
        # =====================================================

        for charge in charges:

            # فقط شارژهایی که کاملاً پرداخت نشده‌اند
            # جریمه آن‌ها بررسی می‌شود
            if not charge.is_paid:
                charge.update_penalty()

        # =====================================================
        # 6. دریافت مجدد شارژها
        # =====================================================

        charges = UnifiedCharge.objects.filter(
            unit__in=units,
            unit__is_active=True,
            send_notification=True
        ).select_related(
            'unit',
            'house'
        )

        # =====================================================
        # 7. تفکیک وضعیت شارژها
        # =====================================================

        # -----------------------------------------------------
        # پرداخت شده
        #
        # is_paid = True
        # -----------------------------------------------------

        paid_charges = charges.filter(
            is_paid=True,
            send_notification=True,
        )

        # -----------------------------------------------------
        # در انتظار تأیید
        #
        # is_paid = False
        # payment_pending = True
        # -----------------------------------------------------

        pending_charges = charges.filter(
            is_paid=False,
            payment_pending=True,
            send_notification=True
        )

        # -----------------------------------------------------
        # پرداخت نشده واقعی
        #
        # is_paid = False
        # payment_pending = False
        # -----------------------------------------------------

        unpaid_charges = charges.filter(
            is_paid=False,
            payment_pending=False,
            send_notification=True
        )

        # =====================================================
        # 8. تعداد شارژها
        # =====================================================

        total_charges = charges.count()

        paid_count = paid_charges.count()

        pending_count = pending_charges.count()

        unpaid_count = unpaid_charges.count()

        # =====================================================
        # 9. مجموع بدهی
        #
        # فقط شارژهای:
        #
        # is_paid=False
        # payment_pending=False
        #
        # محاسبه می‌شوند.
        #
        # شارژهای Pending بدهی محسوب نمی‌شوند.
        # =====================================================

        total_debt = sum(
            (
                charge.total_charge_month
                if charge.total_charge_month is not None
                else charge.amount
                if charge.amount is not None
                else 0
            )
            for charge in unpaid_charges
        )

        # =====================================================
        # 10. مجموع پرداختی
        #
        # فقط شارژهای قطعی پرداخت شده
        #
        # is_paid=True
        # =====================================================

        total_paid = (
                paid_charges.aggregate(
                    total=Sum('total_charge_month')
                )['total']
                or 0
        )

        # =====================================================
        # 11. آخرین شارژ
        # =====================================================

        latest_charge = charges.order_by(
            '-created_at'
        ).first()

        # =====================================================
        # 12. اطلاعات واحدها
        # =====================================================

        units_data = []

        for unit in units:
            # -------------------------------------------------
            # آیا کاربر مستأجر فعال این واحد است؟
            # -------------------------------------------------

            is_renter = unit.renters.filter(
                user=user,
                renter_is_active=True
            ).exists()

            units_data.append({

                'id': unit.id,

                'unit_number': unit.unit,

                'house_id': unit.myhouse_id,

                'house_name': (
                    unit.myhouse.name
                    if unit.myhouse
                    else None
                ),

                'is_renter': is_renter,
            })

        # =====================================================
        # 13. اطلاعات آخرین شارژ
        # =====================================================

        latest_charge_data = None

        if latest_charge:
            latest_charge_data = {

                'id': latest_charge.id,

                'title': latest_charge.title,

                'unit_id': latest_charge.unit_id,

                'unit_number': (
                    latest_charge.unit.unit
                    if latest_charge.unit
                    else None
                ),

                'house_id': (
                    latest_charge.house_id
                    if latest_charge.house
                    else None
                ),

                'house_name': (
                    latest_charge.house.name
                    if latest_charge.house
                    else None
                ),

                # -------------------------------------------------
                # مبلغ پایه
                # -------------------------------------------------

                'base_charge': (
                        latest_charge.base_charge or 0
                ),

                # -------------------------------------------------
                # مبلغ جریمه
                # -------------------------------------------------

                'penalty_amount': (
                        latest_charge.penalty_amount or 0
                ),

                # -------------------------------------------------
                # مبلغ شارژ ماه
                # -------------------------------------------------

                'total_charge_month': (
                        latest_charge.total_charge_month
                        or latest_charge.amount
                        or 0
                ),

                # -------------------------------------------------
                # مبلغ قابل پرداخت با بدهی‌های قبلی
                # -------------------------------------------------

                'payable_amount': (
                        latest_charge.total_payable_with_previous
                        or 0
                ),

                # -------------------------------------------------
                # وضعیت پرداخت
                # -------------------------------------------------

                'is_paid': latest_charge.is_paid,

                'payment_pending': (
                    latest_charge.payment_pending
                ),

                # -------------------------------------------------
                # تاریخ سررسید
                # -------------------------------------------------

                'payment_deadline_date': (
                    latest_charge.payment_deadline_date
                    if latest_charge.payment_deadline_date
                    else None
                ),

                # -------------------------------------------------
                # تاریخ پرداخت
                # -------------------------------------------------

                'payment_date': (
                    latest_charge.payment_date
                    if latest_charge.payment_date
                    else None
                ),

                # -------------------------------------------------
                # تاریخ ایجاد
                # -------------------------------------------------

                'created_at': (
                    latest_charge.created_at
                    if latest_charge.created_at
                    else None
                ),
            }


        # =====================================================
        # 15. پاسخ API
        # =====================================================

        return Response({

            'success': True,

            # =================================================
            # اطلاعات کاربر
            # =================================================

            'user': {

                'id': user.id,

                'full_name': user.full_name,

                'username': user.username,

                'mobile': user.mobile,
            },

            # =================================================
            # اطلاعات واحدها
            # =================================================

            'units': units_data,

            # =================================================
            # آمار Dashboard
            # =================================================

            'statistics': {

                'total_charges': total_charges,

                'paid_count': paid_count,

                'unpaid_count': unpaid_count,

                'pending_count': pending_count,

                'total_debt': total_debt,

                'total_paid': total_paid,
            },

            # =================================================
            # آخرین شارژ
            # =================================================

            'latest_charge': latest_charge_data,
        })
