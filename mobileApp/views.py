import json

from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.utils import timezone
from decimal import Decimal

import requests

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import render, get_object_or_404

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from admin_panel.services.utils import (
    get_next_financial_document_number
)
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response

from absharProject import settings
from admin_panel.models import UnifiedCharge, Fund, Announcement, CivilManage, CivilInstallment, SewageManage, \
    SewageInstallment, MessageReadStatus, MessageToUser, AnnouncementDocument, SmsManagement, SmsCredit, BankFund
from middleAdmin_panel.services.bank_services import BankTransactionService
from payment_app.views import CallbackURLCharge, ZP_API_REQUEST, ZP_API_STARTPAY
from polls_app.models import Poll, Vote, Choice, Question
from user_app.models import Unit, HousePaymentGateway, Renter, Bank, MyHouse, UserPayMoney
from .serializers import (
    LoginSerializer,
    UserMeSerializer,
    HouseMeSerializer,
    UnitMeSerializer, ManualChargePaymentSerializer, MobileChargeListSerializer, MobileChargeDetailSerializer,
    MobilePaymentHistorySerializer, MobileAnnouncementSerializer, PollListSerializer, PollDetailSerializer,
    CivilManageSerializer, CivilInstallmentSerializer, ManualCivilPaymentSerializer, SewageManageSerializer,
    SewageInstallmentSerializer, ManualSewagePaymentSerializer, MessageToUserSerializer, UserPayMoneySerializer,
    CreateUserPayMoneySerializer, ManualUserPayMoneyPaymentSerializer, ManagerAnnouncementSerializer,
    ManagerMessageUnitSerializer, ManagerMessageListSerializer, ManagerMessageDetailSerializer,
    ManagerBankTransferListSerializer, ManagerBankTransferSerializer, ManagerBankSerializer,
)

User = get_user_model()


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(
            data=request.data
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعات ورود نامعتبر است.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        username = serializer.validated_data['username']
        password = serializer.validated_data['password']

        # =========================================================
        # مدیر یا ساکن
        # =========================================================
        user = User.objects.filter(
            username=username,
            is_active=True
        ).filter(
            Q(is_middle_admin=True) |
            Q(is_unit=True)
        ).first()

        if not user:
            return Response(
                {
                    'success': False,
                    'message': 'نام کاربری یا رمز عبور اشتباه است.'
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # =========================================================
        # بررسی رمز
        # =========================================================
        if not check_password(
                password,
                user.password
        ):
            return Response(
                {
                    'success': False,
                    'message': 'نام کاربری یا رمز عبور اشتباه است.'
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # =========================================================
        # تعیین نوع کاربر
        # =========================================================
        if user.is_middle_admin:

            user_type = 'manager'

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
                    status=status.HTTP_403_FORBIDDEN
                )

        elif user.is_unit:

            user_type = 'resident'

            house = user.house

        else:

            return Response(
                {
                    'success': False,
                    'message': 'نوع کاربر معتبر نیست.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =========================================================
        # JWT
        # =========================================================
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                'success': True,
                'message': 'ورود با موفقیت انجام شد.',

                'access': str(
                    refresh.access_token
                ),

                'refresh': str(
                    refresh
                ),

                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'mobile': user.mobile,

                    'user_type': user_type,

                    'is_middle_admin': user.is_middle_admin,
                    'is_unit': user.is_unit,

                    'house_id': (
                        house.id
                        if house
                        else None
                    ),

                    'house_name': (
                        house.name
                        if house
                        else None
                    ),

                    'house': (
                        {
                            'id': house.id,
                            'name': house.name,
                            'subdomain': house.subdomain,
                            'city': house.city,
                        }
                        if house
                        else None
                    ),
                }
            },
            status=status.HTTP_200_OK
        )


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
        # Debug
        # =====================================================

        print(
            '================ ME DEBUG ================'
        )

        print(
            'USER ID:',
            user.id
        )

        print(
            'IS UNIT:',
            is_unit
        )

        print(
            'IS MIDDLE ADMIN:',
            is_middle_admin
        )

        print(
            'HOUSE:',
            house_data
        )

        print(
            'UNITS:',
            units_data
        )

        print(
            '==========================================='
        )

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

        # print(
        #     "🔥🔥🔥 DASHBOARD VIEW CALLED 🔥🔥🔥",
        #     flush=True
        # )

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

        print(
            '================ DASHBOARD DEBUG ================',
            flush=True
        )

        print(
            'USER ID:',
            user.id,
            flush=True
        )

        print(
            'USER MOBILE:',
            user.mobile,
            flush=True
        )

        print(
            'OWNER UNITS:',
            list(
                owner_units.values(
                    'id',
                    'unit',
                    'user_id',
                    'myhouse_id'
                )
            ),
            flush=True
        )

        print(
            'RENTER UNITS:',
            list(
                renter_units.values(
                    'id',
                    'unit',
                    'user_id',
                    'myhouse_id'
                )
            ),
            flush=True
        )

        print(
            'ALL UNITS:',
            list(
                units.values(
                    'id',
                    'unit',
                    'user_id',
                    'myhouse_id'
                )
            ),
            flush=True
        )

        print(
            '==================================================',
            flush=True
        )

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
        # 14. Debug
        # =====================================================

        # print(
        #     "==========================================",
        #     flush=True
        # )

        # print(
        #     "🔥 DASHBOARD STATISTICS",
        #     flush=True
        # )

        # print(
        #     f"USER ID: {user.id}",
        #     flush=True
        # )

        # print(
        #     f"USERNAME: {user.username}",
        #     flush=True
        # )

        # print(
        #     f"TOTAL CHARGES: {total_charges}",
        #     flush=True
        # )

        # print(
        #     f"PAID: {paid_count}",
        #     flush=True
        # )

        # print(
        #     f"UNPAID: {unpaid_count}",
        #     flush=True
        # )

        # print(
        #     f"PENDING: {pending_count}",
        #     flush=True
        # )

        # print(
        #     f"TOTAL PAID: {total_paid}",
        #     flush=True
        # )

        # print(
        #     f"TOTAL DEBT: {total_debt}",
        #     flush=True
        # )

        # print(
        #     "==========================================",
        #     flush=True
        # )
        print(
            "CHART DATA:",
            {
                "total": total_charges,
                "paid": paid_count,
                "unpaid": unpaid_count,
                "pending": pending_count,
            },
            flush=True
        )

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

        # print("==============================================")
        # print("PAYMENT HISTORY DEBUG")
        # print("USER ID:", user.id)
        # print("USERNAME:", user.username)
        # print("FULL NAME:", user.full_name)
        # print("MOBILE:", user.mobile)
        # print("==============================================")

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

        print("OWNER UNIT IDS:", owner_units)

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

        print("RENTER UNIT IDS:", renter_units)

        # =====================================================
        # مجموع واحدهای کاربر
        # =====================================================

        unit_ids = list(
            set(owner_units + renter_units)
        )

        print("FINAL UNIT IDS:", unit_ids)

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
        print("PAYMENT COUNT:", payments.count())

        result = []

        for fund in payments:

            # print(
            #     f"FUND: {fund.id} | "
            #     f"UNIT: {fund.unit_id} | "
            #     f"FUND USER: {fund.user_id} | "
            #     f"REQUEST USER: {user.id} | "
            #     f"AMOUNT: {fund.amount} | "
            #     f"DESCRIPTION: {fund.payment_description}"
            # )

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

        print("FINAL PAYMENT COUNT:", len(result))

        return Response({
            "success": True,
            "count": len(result),
            "payments": result,
        })


class MobileAnnouncementListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # -------------------------------------------------
        # بررسی ساختمان کاربر
        # -------------------------------------------------

        house = getattr(user, 'house', None)

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'ساختمان کاربر مشخص نیست.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # فقط ۵ اطلاعیه فعال و جدیدتر
        # -------------------------------------------------

        announcements = (
            Announcement.objects
            .filter(
                house=house,
                is_active=True
            )
            .prefetch_related('documents')
            .order_by('-created_at')[:5]
        )

        serializer = MobileAnnouncementSerializer(
            announcements,
            many=True,
            context={'request': request}
        )

        return Response(
            {
                'success': True,
                'count': len(serializer.data),
                'announcements': serializer.data
            },
            status=status.HTTP_200_OK
        )


# =====================================================
# لیست نظرسنجی‌های فعال
# =====================================================
class MobilePollListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        now = timezone.now()

        user_house = request.user.house

        if not user_house:
            return Response({
                'success': False,
                'message': 'مجتمع کاربر مشخص نیست.',
                'polls': [],
            })

        polls = Poll.objects.filter(
            house=user_house,
            is_active=True,
            start_date__lte=now,
            end_date__gte=now,
        ).order_by('-created_at')

        serializer = PollListSerializer(
            polls,
            many=True,
            context={'request': request},
        )

        return Response({
            'success': True,
            'count': polls.count(),
            'polls': serializer.data,
        })


class MobilePollDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        now = timezone.now()

        # print("\n================ POLL DETAIL DEBUG ================")
        # print("USER:", request.user)
        # print("USER ID:", request.user.id)
        # print("USER HOUSE:", request.user.house)
        # print("USER HOUSE ID:", request.user.house_id)
        # print("POLL ID:", pk)
        # print("NOW:", now)

        try:
            poll = Poll.objects.select_related(
                'house'
            ).get(id=pk)

        except Poll.DoesNotExist:
            print("POLL FOUND: NO")

            return Response(
                {
                    'success': False,
                    'message': 'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # print("POLL FOUND:", poll.id)
        # print("POLL HOUSE:", poll.house)
        # print("POLL HOUSE ID:", poll.house_id)
        # print("ACTIVE:", poll.is_active)
        # print("START:", poll.start_date)
        # print("END:", poll.end_date)

        # -----------------------------------------
        # بررسی مجتمع
        # -----------------------------------------

        house_match = (
                request.user.house_id == poll.house_id
        )

        print("HOUSE MATCH:", house_match)

        if not house_match:
            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی برای مجتمع شما فعال نیست.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------
        # بررسی فعال بودن
        # -----------------------------------------

        if not poll.is_active:
            print("POLL ACTIVE: FALSE")

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی غیرفعال شده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------
        # بررسی تاریخ شروع
        # -----------------------------------------

        start_ok = poll.start_date <= now

        print("START OK:", start_ok)

        if not start_ok:
            return Response(
                {
                    'success': False,
                    'message':
                        'زمان شروع این نظرسنجی فرا نرسیده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------
        # بررسی تاریخ پایان
        # -----------------------------------------

        end_ok = poll.end_date >= now

        print("END OK:", end_ok)

        if not end_ok:
            return Response(
                {
                    'success': False,
                    'message':
                        'زمان این نظرسنجی به پایان رسیده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------
        # Serializer
        # -----------------------------------------

        serializer = PollDetailSerializer(
            poll,
            context={
                'request': request,
            }
        )

        print("POLL DETAIL SUCCESS")

        return Response({
            'success': True,
            'poll': serializer.data,
        })


class MobilePollVoteView(APIView):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, pk):

        now = timezone.now()

        print()
        print("================ POLL VOTE DEBUG ================")
        print("USER:", request.user)
        print("USER ID:", request.user.id)
        print(
            "USER HOUSE:",
            request.user.house
        )
        print(
            "USER HOUSE ID:",
            request.user.house_id
        )
        print("REQUEST HOUSE:", getattr(request, 'house', None))
        print(
            "REQUEST HOUSE ID:",
            getattr(
                getattr(request, 'house', None),
                'id',
                None
            )
        )
        print("POLL ID:", pk)
        print("NOW:", now)

        # =====================================================
        # مجتمع کاربر
        # =====================================================

        house = request.user.house

        if house is None:
            return Response(
                {
                    'success': False,
                    'message':
                        'مجتمع کاربر مشخص نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(
            "FINAL HOUSE:",
            house
        )
        print(
            "FINAL HOUSE ID:",
            house.id
        )

        # =====================================================
        # پیدا کردن نظرسنجی
        # =====================================================

        try:

            poll = Poll.objects.get(
                id=pk
            )

        except Poll.DoesNotExist:

            print("POLL NOT FOUND")

            return Response(
                {
                    'success': False,
                    'message':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        print(
            "POLL FOUND:",
            poll.id
        )
        print(
            "POLL HOUSE:",
            poll.house
        )
        print(
            "POLL HOUSE ID:",
            poll.house_id
        )
        print(
            "POLL ACTIVE:",
            poll.is_active
        )
        print(
            "POLL START:",
            poll.start_date
        )
        print(
            "POLL END:",
            poll.end_date
        )

        # =====================================================
        # بررسی مجتمع
        # =====================================================

        if poll.house_id != house.id:
            print(
                "HOUSE MATCH: FALSE"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی برای مجتمع شما فعال نیست.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        print(
            "HOUSE MATCH: TRUE"
        )

        # =====================================================
        # بررسی فعال بودن
        # =====================================================

        if not poll.is_active:
            print(
                "POLL ACTIVE: FALSE"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی غیرفعال است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی تاریخ شروع
        # =====================================================

        if poll.start_date > now:
            print(
                "START DATE: NOT STARTED"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'زمان شروع این نظرسنجی فرا نرسیده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # بررسی تاریخ پایان
        # =====================================================

        if poll.end_date < now:
            print(
                "END DATE: EXPIRED"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'زمان این نظرسنجی به پایان رسیده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(
            "POLL DATE: OK"
        )

        # =====================================================
        # پیدا کردن واحد کاربر
        # =====================================================

        unit = Unit.objects.filter(
            Q(user=request.user) |
            Q(renters__user=request.user, renters__renter_is_active=True
              ), myhouse=house, is_active=True, ).distinct().first()

        print(
            "USER UNIT:",
            unit
        )

        print(
            "USER UNIT ID:",
            getattr(unit, 'id', None)
        )

        if unit is None:
            return Response(
                {
                    'success': False,
                    'message':
                        'واحدی برای کاربر شما در این مجتمع پیدا نشد.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # بررسی رأی قبلی
        # =====================================================

        already_voted = Vote.objects.filter(
            poll=poll,
            user=request.user,
        ).exists()

        print(
            "ALREADY VOTED:",
            already_voted
        )

        if already_voted:
            return Response(
                {
                    'success': False,
                    'message':
                        'شما قبلاً در این نظرسنجی رأی داده‌اید.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # دریافت پاسخ‌ها
        # =====================================================

        answers = request.data.get(
            'answers'
        )

        print(
            "ANSWERS:",
            answers
        )

        if not isinstance(answers, list):
            return Response(
                {
                    'success': False,
                    'message':
                        'اطلاعات رأی نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not answers:
            return Response(
                {
                    'success': False,
                    'message':
                        'حداقل یک پاسخ باید انتخاب شود.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # بررسی سؤال‌ها و گزینه‌ها
        # =====================================================

        poll_questions = {
            question.id: question
            for question in Question.objects.filter(
                poll=poll
            )
        }

        processed_questions = set()

        for answer in answers:

            question_id = answer.get(
                'question_id'
            )

            choice_ids = answer.get(
                'choice_ids',
                []
            )

            if not question_id:
                return Response(
                    {
                        'success': False,
                        'message':
                            'شناسه سؤال نامعتبر است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:

                question_id = int(
                    question_id
                )

            except (TypeError, ValueError):

                return Response(
                    {
                        'success': False,
                        'message':
                            'شناسه سؤال نامعتبر است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if question_id in processed_questions:
                return Response(
                    {
                        'success': False,
                        'message':
                            'برای یک سؤال چند پاسخ ارسال شده است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            processed_questions.add(
                question_id
            )

            question = poll_questions.get(
                question_id
            )

            if question is None:
                return Response(
                    {
                        'success': False,
                        'message':
                            'سؤال متعلق به این نظرسنجی نیست.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not isinstance(
                    choice_ids,
                    list
            ):
                return Response(
                    {
                        'success': False,
                        'message':
                            'گزینه‌های انتخابی نامعتبر هستند.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # تعداد انتخاب
            # -------------------------------------------------

            if question.question_type in [
                'yesno',
                'single',
            ]:

                if len(choice_ids) != 1:
                    return Response(
                        {
                            'success': False,
                            'message':
                                'برای این سؤال باید یک گزینه انتخاب شود.'
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            elif question.question_type == 'multi':

                if len(choice_ids) < 1:
                    return Response(
                        {
                            'success': False,
                            'message':
                                'حداقل یک گزینه را انتخاب کنید.'
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            # -------------------------------------------------
            # جلوگیری از ID تکراری
            # -------------------------------------------------

            if len(choice_ids) != len(
                    set(choice_ids)
            ):
                return Response(
                    {
                        'success': False,
                        'message':
                            'یک گزینه بیش از یک بار انتخاب شده است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # گزینه‌ها
            # -------------------------------------------------

            choices = Choice.objects.filter(
                question=question,
                id__in=choice_ids,
            )

            if choices.count() != len(
                    choice_ids
            ):
                return Response(
                    {
                        'success': False,
                        'message':
                            'یکی از گزینه‌های انتخابی نامعتبر است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # ثبت رأی
            # -------------------------------------------------

            for choice in choices:
                Vote.objects.create(
                    poll=poll,
                    question=question,
                    choice=choice,
                    unit=unit,
                    user=request.user,
                )

        # =====================================================
        # بررسی اینکه همه سؤال‌ها پاسخ داده شده‌اند
        # =====================================================

        total_questions = Question.objects.filter(
            poll=poll
        ).count()

        answered_questions = len(
            processed_questions
        )

        print(
            "TOTAL QUESTIONS:",
            total_questions
        )

        print(
            "ANSWERED QUESTIONS:",
            answered_questions
        )

        if answered_questions != total_questions:
            # چون transaction.atomic داریم،
            # رأی‌های ایجادشده rollback می‌شوند.
            from django.db import transaction
            transaction.set_rollback(True)

            return Response(
                {
                    'success': False,
                    'message':
                        'لطفاً به همه سؤال‌ها پاسخ دهید.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(
            "VOTE SUCCESS"
        )

        print(
            "================================================"
        )

        return Response(
            {
                'success': True,
                'message':
                    'رأی شما با موفقیت ثبت شد.'
            },
            status=status.HTTP_200_OK,
        )


# Civil Views
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


# Sewage Views
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


# ============================ Message To User =================================


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


# Pay Money

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


# ================ Manager Views ========================

class ManagerAnnouncementListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, user):
        return MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

    # =====================================================
    # لیست اطلاعیه‌های مدیر
    # =====================================================

    def get(self, request):

        user = request.user

        if not user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        house = self.get_house(user)

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        announcements = (
            Announcement.objects
            .filter(
                user=user,
                house=house
            )
            .prefetch_related('documents')
            .order_by('-created_at')
        )

        serializer = ManagerAnnouncementSerializer(
            announcements,
            many=True,
            context={'request': request}
        )

        return Response(
            {
                'success': True,
                'count': len(serializer.data),
                'announcements': serializer.data
            },
            status=status.HTTP_200_OK
        )

    # =====================================================
    # ایجاد اطلاعیه
    # =====================================================

    @transaction.atomic
    def post(self, request):

        user = request.user

        if not user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        house = self.get_house(user)

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        title = request.data.get('title')

        if not title or not str(title).strip():
            return Response(
                {
                    'success': False,
                    'message': 'متن اطلاعیه الزامی است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        show_in_marquee = (
                str(request.data.get('show_in_marquee', 'false')).lower()
                in ['true', '1', 'yes', 'on']
        )

        announcement = Announcement.objects.create(
            user=user,
            house=house,
            title=title,
            show_in_marquee=show_in_marquee,
            is_active=True
        )

        # =================================================
        # دریافت چند فایل
        # =================================================

        files = request.FILES.getlist('documents')

        for uploaded_file in files:
            AnnouncementDocument.objects.create(
                announcement=announcement,
                document=uploaded_file
            )

        serializer = ManagerAnnouncementSerializer(
            announcement,
            context={'request': request}
        )

        return Response(
            {
                'success': True,
                'message': 'اطلاعیه با موفقیت ثبت شد.',
                'announcement': serializer.data
            },
            status=status.HTTP_201_CREATED
        )


class ManagerAnnouncementDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, user):
        return MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

    def get_announcement(self, request, pk):

        house = self.get_house(request.user)

        if not house:
            return None, None

        announcement = (
            Announcement.objects
            .filter(
                id=pk,
                user=request.user,
                house=house
            )
            .prefetch_related('documents')
            .first()
        )

        return announcement, house

    # =====================================================
    # ویرایش
    # =====================================================

    @transaction.atomic
    def put(self, request, pk):

        user = request.user

        if not user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        announcement, house = self.get_announcement(
            request,
            pk
        )

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if not announcement:
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعیه مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        title = request.data.get(
            'title',
            announcement.title
        )

        if not title or not str(title).strip():
            return Response(
                {
                    'success': False,
                    'message': 'متن اطلاعیه الزامی است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        announcement.title = title

        if 'show_in_marquee' in request.data:
            announcement.show_in_marquee = (
                    str(
                        request.data.get('show_in_marquee')
                    ).lower()
                    in ['true', '1', 'yes', 'on']
            )

        if 'is_active' in request.data:
            announcement.is_active = (
                    str(
                        request.data.get('is_active')
                    ).lower()
                    in ['true', '1', 'yes', 'on']
            )

        announcement.save()

        # ================================================
        # فایل‌های جدید
        # ================================================

        files = request.FILES.getlist('documents')

        for uploaded_file in files:
            AnnouncementDocument.objects.create(
                announcement=announcement,
                document=uploaded_file
            )

        serializer = ManagerAnnouncementSerializer(
            announcement,
            context={'request': request}
        )

        return Response(
            {
                'success': True,
                'message': 'اطلاعیه با موفقیت ویرایش شد.',
                'announcement': serializer.data
            },
            status=status.HTTP_200_OK
        )

    # =====================================================
    # حذف
    # =====================================================

    @transaction.atomic
    def delete(self, request, pk):

        user = request.user

        if not user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        announcement, house = self.get_announcement(
            request,
            pk
        )

        if not house:
            return Response(
                {
                    'success': False,
                    'message': 'برای این مدیر ساختمان فعالی ثبت نشده است.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        if not announcement:
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعیه مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        announcement.delete()

        return Response(
            {
                'success': True,
                'message': 'اطلاعیه با موفقیت حذف شد.'
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# Manager Message Helpers
# ============================================================

def get_manager_message_house(user):
    """
    ساختمان اصلی مدیر
    """

    return MyHouse.objects.filter(
        user=user
    ).first()


def get_manager_message_units(user):
    """
    واحدهای متعلق به ساختمان مدیر

    شامل:
    - واحدهایی که مستقیماً متعلق به مدیر هستند
    - واحدهای کاربران تحت مدیریت مدیر
    """

    house = get_manager_message_house(user)

    if not house:
        return Unit.objects.none()

    managed_users = user.managed_users.all()

    return (
        Unit.objects
        .filter(
            Q(user=user) |
            Q(user__in=managed_users),
            myhouse=house,
            is_active=True,
        )
        .select_related('user')
        .prefetch_related(
            'renters'
        )
        .order_by('unit')
    )


class ManagerMessageUnitsAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def get(self, request):

        user = request.user

        # =====================================================
        # فقط مدیر ساختمان
        # =====================================================

        if not getattr(
            user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # واحدهای مجاز مدیر
        # =====================================================

        units = (
            get_manager_message_units(user)
            .select_related('user')
            .prefetch_related(
                'renters'
            )
        )

        recipients = []

        # =====================================================
        # ساخت لیست گیرندگان
        #
        # هر مالک و مستأجر یک ردیف مستقل است.
        # =====================================================

        for unit in units:

            # =================================================
            # مالک
            # =================================================

            owner_user = unit.user

            owner_mobile = (
                unit.owner_mobile
                or (
                    owner_user.mobile
                    if owner_user
                    else ''
                )
                or ''
            )

            owner_mobile = str(
                owner_mobile
            ).strip()

            owner_name = (
                unit.owner_name
                or (
                    owner_user.full_name
                    if owner_user
                    else ''
                )
                or (
                    owner_user.username
                    if owner_user
                    else ''
                )
                or ''
            )

            owner_name = str(
                owner_name
            ).strip()

            # فقط گیرنده‌ای که نام و موبایل دارد
            if (
                owner_user
                and owner_name
                and owner_mobile
            ):

                unit._recipient_type = 'owner'

                # برای Serializer
                unit._active_renter = None

                serializer = ManagerMessageUnitSerializer(
                    unit,
                    context={
                        'request': request
                    }
                )

                recipients.append(
                    serializer.data
                )

            # =================================================
            # مستأجر فعال
            # =================================================

            renter = (
                unit.renters
                .filter(
                    renter_is_active=True
                )
                .select_related('user')
                .first()
            )

            if renter:

                renter_user = renter.user

                renter_mobile = (
                    renter.renter_mobile
                    or (
                        renter_user.mobile
                        if renter_user
                        else ''
                    )
                    or ''
                )

                renter_mobile = str(
                    renter_mobile
                ).strip()

                renter_name = (
                    renter.renter_name
                    or (
                        renter_user.full_name
                        if renter_user
                        else ''
                    )
                    or (
                        renter_user.username
                        if renter_user
                        else ''
                    )
                    or ''
                )

                renter_name = str(
                    renter_name
                ).strip()

                if (
                    renter_user
                    and renter_name
                    and renter_mobile
                ):

                    unit._recipient_type = 'renter'
                    unit._active_renter = renter

                    serializer = ManagerMessageUnitSerializer(
                        unit,
                        context={
                            'request': request
                        }
                    )

                    recipients.append(
                        serializer.data
                    )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'count': len(recipients),
                'results': recipients,
            },
            status=status.HTTP_200_OK
        )


class ManagerMessageListCreateAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    # =========================================================
    # GET
    #
    # تمام پیام‌های مدیر را نمایش می‌دهد:
    #
    # - پیام‌های آماده ارسال
    # - پیام‌های ارسال شده
    #
    # فقط یک لیست داریم.
    # =========================================================

    def get(self, request):

        user = request.user

        # =====================================================
        # فقط مدیر ساختمان
        # =====================================================

        if not getattr(
            user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # جستجو
        # =====================================================

        query = request.GET.get(
            'q',
            ''
        ).strip()

        # =====================================================
        # تمام پیام‌های مدیر
        #
        # مهم:
        # send_notification اینجا فیلتر نمی‌شود.
        #
        # چون پیام‌های ارسال‌شده هم باید در لیست باقی بمانند.
        # =====================================================

        queryset = (
            MessageToUser.objects
            .filter(
                user=user,
                is_active=True,
            )
            .order_by(
                '-created_at'
            )
        )

        # =====================================================
        # جستجو در عنوان و متن
        # =====================================================

        if query:

            queryset = queryset.filter(
                Q(title__icontains=query) |
                Q(message__icontains=query)
            )

        # =====================================================
        # Serializer
        # =====================================================

        serializer = ManagerMessageListSerializer(
            queryset,
            many=True,
            context={
                'request': request
            }
        )

        # =====================================================
        # پاسخ
        # =====================================================

        return Response(
            {
                'count': queryset.count(),
                'results': serializer.data,
            },
            status=status.HTTP_200_OK
        )

    # =========================================================
    # POST
    #
    # ایجاد پیام جدید
    #
    # پیام در ابتدا فقط ذخیره می‌شود.
    # هنوز ارسال نشده است.
    # =========================================================

    def post(self, request):

        user = request.user

        # =====================================================
        # فقط مدیر ساختمان
        # =====================================================

        if not getattr(
            user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # عنوان
        # =====================================================

        title = str(
            request.data.get(
                'title',
                ''
            )
        ).strip()

        # =====================================================
        # متن پیام
        # =====================================================

        message_text = str(
            request.data.get(
                'message',
                ''
            )
        ).strip()

        # =====================================================
        # اعتبارسنجی عنوان
        # =====================================================

        if not title:

            return Response(
                {
                    'detail': (
                        'عنوان پیام الزامی است.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # اعتبارسنجی متن
        # =====================================================

        if not message_text:

            return Response(
                {
                    'detail': (
                        'متن پیام الزامی است.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # ایجاد پیام
        #
        # پیام هنوز ارسال نشده.
        # =====================================================

        message = MessageToUser.objects.create(
            user=user,
            title=title,
            message=message_text,
            send_notification=False,
            send_notification_date=None,
            is_active=True,
        )

        # =====================================================
        # Serializer
        # =====================================================

        serializer = ManagerMessageDetailSerializer(
            message,
            context={
                'request': request
            }
        )

        return Response(
            {
                'detail': (
                    'پیام با موفقیت ذخیره شد.'
                ),
                'message': serializer.data,
            },
            status=status.HTTP_201_CREATED
        )


class ManagerMessageDetailAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    # =========================================================
    # دریافت پیام متعلق به مدیر
    # =========================================================

    def get_message(
        self,
        request,
        pk
    ):

        return get_object_or_404(
            MessageToUser,
            id=pk,
            user=request.user,
            is_active=True,
        )

    # =========================================================
    # GET
    #
    # مشاهده جزئیات پیام
    #
    # هم برای پیام ارسال نشده
    # هم برای پیام ارسال شده
    # =========================================================

    def get(
        self,
        request,
        pk
    ):

        if not getattr(
            request.user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        message = self.get_message(
            request,
            pk
        )

        serializer = ManagerMessageDetailSerializer(
            message,
            context={
                'request': request
            }
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    # =========================================================
    # PATCH
    #
    # فقط پیام ارسال نشده قابل ویرایش است.
    # =========================================================

    def patch(
        self,
        request,
        pk
    ):

        if not getattr(
            request.user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        message = self.get_message(
            request,
            pk
        )

        # =====================================================
        # پیام ارسال شده قابل ویرایش نیست
        # =====================================================

        if message.send_notification:

            return Response(
                {
                    'detail': (
                        'پیام ارسال شده قابل ویرایش نیست.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # عنوان
        # =====================================================

        if 'title' in request.data:

            title = str(
                request.data.get(
                    'title',
                    ''
                )
            ).strip()

            if not title:

                return Response(
                    {
                        'detail': (
                            'عنوان پیام الزامی است.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            message.title = title

        # =====================================================
        # متن
        # =====================================================

        if 'message' in request.data:

            message_text = str(
                request.data.get(
                    'message',
                    ''
                )
            ).strip()

            if not message_text:

                return Response(
                    {
                        'detail': (
                            'متن پیام الزامی است.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            message.message = message_text

        # =====================================================
        # اگر هیچ فیلدی برای تغییر ارسال نشده
        # =====================================================

        if (
            'title' not in request.data
            and
            'message' not in request.data
        ):
            return Response(
                {
                    'detail': (
                        'اطلاعاتی برای ویرایش ارسال نشده است.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # ذخیره
        # =====================================================

        message.save(
            update_fields=[
                'title',
                'message',
            ]
        )

        # =====================================================
        # پاسخ
        # =====================================================

        serializer = ManagerMessageDetailSerializer(
            message,
            context={
                'request': request
            }
        )

        return Response(
            {
                'detail': (
                    'پیام با موفقیت ویرایش شد.'
                ),
                'message': serializer.data,
            },
            status=status.HTTP_200_OK
        )

    # =========================================================
    # DELETE
    #
    # فقط پیام ارسال نشده قابل حذف است.
    # =========================================================

    def delete(
        self,
        request,
        pk
    ):

        if not getattr(
            request.user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        message = self.get_message(
            request,
            pk
        )

        # =====================================================
        # پیام ارسال شده قابل حذف نیست
        # =====================================================

        if message.send_notification:

            return Response(
                {
                    'detail': (
                        'پیام ارسال شده قابل حذف نیست.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        message.delete()

        return Response(
            {
                'detail': (
                    'پیام با موفقیت حذف شد.'
                )
            },
            status=status.HTTP_200_OK
        )


class ManagerMessageSendAPIView(APIView):

    permission_classes = [
        IsAuthenticated
    ]

    def post(self, request, pk):

        user = request.user

        # =====================================================
        # فقط مدیر ساختمان
        # =====================================================

        if not getattr(
            user,
            'is_middle_admin',
            False
        ):
            return Response(
                {
                    'detail': (
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                    )
                },
                status=status.HTTP_403_FORBIDDEN
            )

        # =====================================================
        # پیام
        # =====================================================

        message = get_object_or_404(
            MessageToUser,
            id=pk,
            user=user,
            is_active=True,
        )

        # =====================================================
        # پیام قبلاً ارسال شده
        # =====================================================

        if message.send_notification:
            return Response(
                {
                    'detail': 'این پیام قبلاً ارسال شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # نوع ارسال
        # =====================================================

        send_to_all = request.data.get(
            'all',
            False
        )

        recipients_data = request.data.get(
            'recipients',
            []
        )

        if isinstance(
            send_to_all,
            str
        ):
            send_to_all = (
                send_to_all.lower()
                in [
                    'true',
                    '1',
                    'yes',
                    'all',
                ]
            )

        if not isinstance(
            recipients_data,
            list
        ):
            recipients_data = []

        # =====================================================
        # واحدهای مجاز مدیر
        # =====================================================

        allowed_units = (
            get_manager_message_units(user)
            .select_related('user')
            .prefetch_related(
                'renters'
            )
        )

        allowed_units_map = {
            unit.id: unit
            for unit in allowed_units
        }

        # =====================================================
        # گیرندگان نهایی
        #
        # هر گیرنده:
        #
        # unit + type + recipient
        #
        # مالک و مستأجر کاملاً مستقل هستند.
        # =====================================================

        recipient_items = []

        # =====================================================
        # ارسال به همه
        # =====================================================

        if send_to_all:

            for unit in allowed_units:

                # =================================================
                # مالک
                # =================================================

                owner_user = unit.user

                owner_mobile = (
                    unit.owner_mobile
                    or (
                        getattr(
                            owner_user,
                            'mobile',
                            ''
                        )
                        if owner_user
                        else ''
                    )
                    or ''
                )

                owner_mobile = str(
                    owner_mobile
                ).strip()

                if (
                    owner_user
                    and owner_mobile
                ):

                    recipient_items.append(
                        {
                            'unit': unit,
                            'type': 'owner',
                            'recipient': owner_user,
                            'mobile': owner_mobile,
                        }
                    )

                # =================================================
                # مستأجر فعال
                # =================================================

                renter = (
                    unit.renters
                    .filter(
                        renter_is_active=True
                    )
                    .select_related('user')
                    .first()
                )

                if renter:

                    renter_user = renter.user

                    renter_mobile = (
                        renter.renter_mobile
                        or (
                            getattr(
                                renter_user,
                                'mobile',
                                ''
                            )
                            if renter_user
                            else ''
                        )
                        or ''
                    )

                    renter_mobile = str(
                        renter_mobile
                    ).strip()

                    if (
                        renter_user
                        and renter_mobile
                    ):

                        recipient_items.append(
                            {
                                'unit': unit,
                                'type': 'renter',
                                'recipient': renter_user,
                                'mobile': renter_mobile,
                            }
                        )

        # =====================================================
        # ارسال انتخابی
        # =====================================================

        else:

            if not recipients_data:
                return Response(
                    {
                        'detail': (
                            'حداقل یک گیرنده باید انتخاب شود.'
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )

            processed_keys = set()

            for item in recipients_data:

                if not isinstance(
                    item,
                    dict
                ):
                    continue

                raw_unit_id = item.get(
                    'unit_id'
                )

                recipient_type = str(
                    item.get(
                        'type',
                        ''
                    )
                ).strip().lower()

                try:
                    unit_id = int(
                        raw_unit_id
                    )
                except (
                    TypeError,
                    ValueError
                ):
                    continue

                if recipient_type not in [
                    'owner',
                    'renter',
                ]:
                    continue

                # ---------------------------------------------
                # هر واحد + نوع گیرنده فقط یک بار
                # ---------------------------------------------

                key = (
                    unit_id,
                    recipient_type
                )

                if key in processed_keys:
                    continue

                processed_keys.add(key)

                unit = allowed_units_map.get(
                    unit_id
                )

                if not unit:
                    continue

                # =================================================
                # مالک
                # =================================================

                if recipient_type == 'owner':

                    recipient = unit.user

                    if not recipient:
                        continue

                    mobile = (
                        unit.owner_mobile
                        or getattr(
                            recipient,
                            'mobile',
                            ''
                        )
                        or ''
                    )

                    mobile = str(
                        mobile
                    ).strip()

                    if not mobile:
                        continue

                    recipient_items.append(
                        {
                            'unit': unit,
                            'type': 'owner',
                            'recipient': recipient,
                            'mobile': mobile,
                        }
                    )

                # =================================================
                # مستأجر
                # =================================================

                elif recipient_type == 'renter':

                    renter = (
                        unit.renters
                        .filter(
                            renter_is_active=True
                        )
                        .select_related('user')
                        .first()
                    )

                    if not renter:
                        continue

                    recipient = renter.user

                    if not recipient:
                        continue

                    mobile = (
                        renter.renter_mobile
                        or getattr(
                            recipient,
                            'mobile',
                            ''
                        )
                        or ''
                    )

                    mobile = str(
                        mobile
                    ).strip()

                    if not mobile:
                        continue

                    recipient_items.append(
                        {
                            'unit': unit,
                            'type': 'renter',
                            'recipient': recipient,
                            'mobile': mobile,
                        }
                    )

        # =====================================================
        # هیچ گیرنده‌ای پیدا نشد
        # =====================================================

        if not recipient_items:

            return Response(
                {
                    'detail': (
                        'هیچ گیرنده معتبری برای ارسال پیام '
                        'پیدا نشد. گیرنده باید دارای شماره موبایل '
                        'باشد.'
                    )
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # =====================================================
        # حذف تکراری واقعی
        #
        # نکته:
        # دیگر فقط recipient.id ملاک نیست.
        #
        # مالک و مستأجر مستقل هستند:
        #
        # (unit_id, owner)
        # (unit_id, renter)
        # =====================================================

        unique_items = {}

        for item in recipient_items:

            key = (
                item['unit'].id,
                item['type'],
            )

            unique_items[key] = item

        recipient_items = list(
            unique_items.values()
        )

        # =====================================================
        # ثبت ارسال
        # =====================================================

        with transaction.atomic():

            # -------------------------------------------------
            # واحدهای پیام
            # -------------------------------------------------

            unique_units = {
                item['unit'].id: item['unit']
                for item in recipient_items
            }

            message.notified_units.set(
                list(
                    unique_units.values()
                )
            )

            # -------------------------------------------------
            # وضعیت خواندن گیرندگان
            # -------------------------------------------------

            for item in recipient_items:

                MessageReadStatus.objects.update_or_create(
                    message=message,
                    recipient=item['recipient'],
                    defaults={
                        'unit': item['unit'],
                        'is_read': False,
                        'read_at': None,
                    }
                )

            # -------------------------------------------------
            # ثبت وضعیت ارسال
            # -------------------------------------------------

            message.send_notification = True

            message.send_notification_date = (
                timezone.now()
            )

            message.save(
                update_fields=[
                    'send_notification',
                    'send_notification_date',
                ]
            )

        # =====================================================
        # Serializer
        # =====================================================

        serializer = ManagerMessageDetailSerializer(
            message,
            context={
                'request': request
            }
        )

        return Response(
            {
                'detail': (
                    f'پیام برای {len(recipient_items)} '
                    f'گیرنده ارسال شد.'
                ),

                'recipient_count': len(
                    recipient_items
                ),

                'message': serializer.data,
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# ===================== Manager Banks ========================
# ============================================================
class ManagerHouseListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        houses = MyHouse.objects.filter(
            Q(user=user) | Q(user__manager=user),
            is_active=True
        ).order_by('name', 'id')

        result = []

        for house in houses:
            result.append({
                'id': house.id,
                'name': house.name,
            })

        return Response(result)

class ManagerBankListCreateView(APIView):
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
        ).select_related('house').order_by('-create_at', '-id')

        serializer = ManagerBankSerializer(
            banks,
            many=True,
            context={'request': request}
        )

        return Response(serializer.data)

    @transaction.atomic
    def post(self, request):
        user = request.user

        accessible_houses = self.get_accessible_houses(user)

        serializer = ManagerBankSerializer(
            data=request.data,
            context={
                'request': request,
                'accessible_houses': accessible_houses,
            }
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        house = data['house']
        initial_fund = data.get('initial_fund') or Decimal('0')

        # بانک ابتدا با موجودی صفر ایجاد می‌شود.
        # موجودی اولیه فقط یک بار توسط deposit اضافه خواهد شد.
        bank = Bank.objects.create(
            user=user,
            house=house,
            bank_name=data['bank_name'],
            account_no=data['account_no'],
            account_holder_name=data['account_holder_name'],
            sheba_number=data['sheba_number'],
            cart_number=data['cart_number'],
            initial_fund=initial_fund,
            current_balance=Decimal('0'),
            is_default=data.get('is_default', False),
            is_gateway=data.get('is_gateway', False),
            create_at=data['create_at'],
            is_active=data.get('is_active', True),
        )

        # اگر موجودی اولیه وجود داشته باشد،
        # آن را به عنوان افتتاحیه ثبت می‌کنیم.
        if initial_fund > 0:

            financial_document_number = (
                get_next_financial_document_number(house)
            )

            bank.financial_document_number = financial_document_number
            bank.save(
                update_fields=['financial_document_number']
            )

            # Fund افتتاحیه
            content_type = ContentType.objects.get_for_model(bank)

            Fund.objects.create(
                user=user,
                house=house,
                bank=bank,
                amount=initial_fund,
                debtor_amount=initial_fund,
                creditor_amount=Decimal('0'),
                final_amount=initial_fund,
                payment_date=bank.create_at,
                payment_description='افتتاح حساب',
                is_initial=True,
                financial_document_number=financial_document_number,
                content_type=content_type,
                object_id=bank.pk,
                payer_name=user.full_name,
                payment_gateway='افتتاحیه',
                receiver_name=bank.account_holder_name,
            )

            # BankFund افتتاحیه
            BankTransactionService.deposit(
                user=user,
                bank=bank,
                unit=None,
                amount=initial_fund,
                description='افتتاح حساب',
                content_object=bank,
                payment_date=bank.create_at,
                gateway=' افتتاحیه',
                house=house,
                financial_document_number=financial_document_number,
            )

        output_serializer = ManagerBankSerializer(
            bank,
            context={'request': request}
        )

        return Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED
        )


class ManagerBankDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_accessible_houses(self, user):
        return MyHouse.objects.filter(
            Q(user=user) | Q(user__manager=user),
            is_active=True
        )

    def get_bank(self, request, pk):
        accessible_houses = self.get_accessible_houses(request.user)

        return get_object_or_404(
            Bank.objects.select_related('house'),
            pk=pk,
            user=request.user,
            house__in=accessible_houses
        )

    def get(self, request, pk):
        bank = self.get_bank(request, pk)

        serializer = ManagerBankSerializer(
            bank,
            context={'request': request}
        )

        return Response(serializer.data)

    @transaction.atomic
    def patch(self, request, pk):
        user = request.user
        bank = self.get_bank(request, pk)

        serializer = ManagerBankSerializer(
            bank,
            data=request.data,
            partial=True,
            context={
                'request': request,
                'accessible_houses': self.get_accessible_houses(user),
            }
        )

        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        old_initial_fund = Decimal(
            bank.initial_fund or 0
        )

        new_initial_fund = Decimal(
            data.get(
                'initial_fund',
                bank.initial_fund or 0
            ) or 0
        )

        if new_initial_fund < 0:
            return Response(
                {
                    'detail': 'موجودی اولیه نمی‌تواند منفی باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        new_house = data.get('house', bank.house)

        if not new_house:
            return Response(
                {
                    'detail': 'ساختمان حساب بانکی مشخص نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # -----------------------------------------
        # تغییرات معمولی مشخصات بانک
        # -----------------------------------------

        bank.bank_name = data.get(
            'bank_name',
            bank.bank_name
        )

        bank.account_no = data.get(
            'account_no',
            bank.account_no
        )

        bank.account_holder_name = data.get(
            'account_holder_name',
            bank.account_holder_name
        )

        bank.sheba_number = data.get(
            'sheba_number',
            bank.sheba_number
        )

        bank.cart_number = data.get(
            'cart_number',
            bank.cart_number
        )

        bank.is_default = data.get(
            'is_default',
            bank.is_default
        )

        bank.is_gateway = data.get(
            'is_gateway',
            bank.is_gateway
        )

        bank.is_active = data.get(
            'is_active',
            bank.is_active
        )

        bank.create_at = data.get(
            'create_at',
            bank.create_at
        )

        bank.house = new_house

        # -----------------------------------------
        # تغییر موجودی اولیه
        # -----------------------------------------

        if new_initial_fund != old_initial_fund:

            # اگر تراکنش واقعی بعد از افتتاحیه وجود داشته باشد،
            # فقط رکورد افتتاحیه را تغییر می‌دهیم.
            opening_fund = Fund.objects.filter(
                bank=bank,
                is_initial=True
            ).first()

            opening_bank_fund = BankFund.objects.filter(
                bank=bank,
                payment_description='افتتاح حساب',
                transaction_type='deposit'
            ).order_by('id').first()

            # -------------------------------
            # قبلاً صفر بوده -> الان مثبت
            # -------------------------------

            if old_initial_fund == 0 and new_initial_fund > 0:

                financial_document_number = (
                    get_next_financial_document_number(new_house)
                )

                bank.financial_document_number = (
                    financial_document_number
                )

                bank.initial_fund = new_initial_fund

                # موجودی فعلی را بر اساس مقدار قبلی نگه نمی‌داریم
                # و فقط مبلغ افتتاحیه را اضافه می‌کنیم.
                bank.current_balance = (
                    Decimal(bank.current_balance or 0)
                    + new_initial_fund
                )

                bank.save()

                content_type = ContentType.objects.get_for_model(bank)

                Fund.objects.create(
                    user=user,
                    house=new_house,
                    bank=bank,
                    amount=new_initial_fund,
                    debtor_amount=new_initial_fund,
                    creditor_amount=Decimal('0'),
                    final_amount=new_initial_fund,
                    payment_date=bank.create_at,
                    payment_description='افتتاح حساب',
                    is_initial=True,
                    financial_document_number=financial_document_number,
                    content_type=content_type,
                    object_id=bank.pk,
                    payer_name=user.full_name,
                    receiver_name=bank.account_holder_name,
                )

                BankTransactionService.deposit(
                    user=user,
                    bank=bank,
                    unit=None,
                    amount=new_initial_fund,
                    description='افتتاح حساب',
                    content_object=bank,
                    payment_date=bank.create_at,
                    gateway='افتتاح حساب',
                    house=new_house,
                    financial_document_number=financial_document_number,
                )

            # -------------------------------
            # قبلاً مثبت بوده -> الان صفر
            # -------------------------------

            elif old_initial_fund > 0 and new_initial_fund == 0:

                difference = old_initial_fund

                if opening_bank_fund:
                    opening_bank_fund.delete()

                if opening_fund:
                    opening_fund.delete()

                bank.initial_fund = Decimal('0')
                bank.current_balance = (
                    Decimal(bank.current_balance or 0)
                    - difference
                )

                if bank.current_balance < 0:
                    bank.current_balance = Decimal('0')

                bank.financial_document_number = None

                bank.save()

            # -------------------------------
            # مثبت -> مثبت
            # -------------------------------

            else:

                difference = (
                    new_initial_fund - old_initial_fund
                )

                bank.initial_fund = new_initial_fund

                if opening_fund:
                    opening_fund.amount = new_initial_fund
                    opening_fund.debtor_amount = new_initial_fund
                    opening_fund.final_amount = new_initial_fund
                    opening_fund.house = new_house
                    opening_fund.payment_date = bank.create_at
                    opening_fund.receiver_name = (
                        bank.account_holder_name
                    )
                    opening_fund.save()

                if opening_bank_fund:
                    opening_bank_fund.amount = new_initial_fund
                    opening_bank_fund.house = new_house
                    opening_bank_fund.payment_date = bank.create_at
                    opening_bank_fund.balance_after = (
                        Decimal(bank.current_balance or 0)
                        + difference
                    )
                    opening_bank_fund.save()

                bank.current_balance = (
                    Decimal(bank.current_balance or 0)
                    + difference
                )

                bank.save()

        else:
            bank.initial_fund = new_initial_fund
            bank.save()

        output_serializer = ManagerBankSerializer(
            bank,
            context={'request': request}
        )

        return Response(output_serializer.data)

    @transaction.atomic
    def delete(self, request, pk):
        bank = self.get_bank(request, pk)

        # مطابق رفتار نسخه وب:
        # اگر گردش مالی Fund وجود داشته باشد حذف ممنوع است.
        has_fund = Fund.objects.filter(
            bank=bank
        ).exists()

        if has_fund:
            return Response(
                {
                    'detail':
                        'به دلیل وجود گردش مالی، امکان حذف این حساب بانکی وجود ندارد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        bank.delete()

        return Response(
            {
                'detail': 'حساب بانکی با موفقیت حذف گردید.'
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# =================== Bank Transfers =========================
# ============================================================


class ManagerBankTransferListCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_accessible_houses(self, user):
        return MyHouse.objects.filter(
            Q(user=user) | Q(user__manager=user),
            is_active=True
        )

    def get_user_banks(self, user):
        accessible_houses = self.get_accessible_houses(user)

        return Bank.objects.filter(
            user=user,
            is_active=True,
            house__in=accessible_houses
        ).select_related('house')

    def get(self, request):
        user = request.user

        banks = self.get_user_banks(user)

        bank_ids = list(
            banks.values_list('id', flat=True)
        )

        transfers = BankFund.objects.filter(
            user=user,
            transfer_group_id__isnull=False,
            bank_id__in=bank_ids
        ).select_related(
            'bank',
            'to_bank',
            'house'
        ).order_by('-created_at')

        groups = {}

        for item in transfers:

            group_id = str(item.transfer_group_id)

            if group_id not in groups:
                groups[group_id] = {
                    'transfer_group_id': group_id,
                    'withdraw': None,
                    'deposit': None,
                    'created_at': item.created_at,
                }

            if item.transaction_type == 'withdraw':
                groups[group_id]['withdraw'] = item

            elif item.transaction_type == 'deposit':
                groups[group_id]['deposit'] = item

        result = []

        for group in groups.values():

            withdraw = group['withdraw']
            deposit = group['deposit']

            if not withdraw or not deposit:
                continue

            result.append({
                'id': withdraw.id,

                'transfer_group_id':
                    group['transfer_group_id'],

                'from_bank_id':
                    withdraw.bank_id,

                'from_bank_name':
                    withdraw.bank.bank_name
                    if withdraw.bank else None,

                'to_bank_id':
                    deposit.bank_id,

                'to_bank_name':
                    deposit.bank.bank_name
                    if deposit.bank else None,

                'amount':
                    str(withdraw.amount or 0),

                'transaction_no':
                    withdraw.transaction_no,

                'payment_date':
                    withdraw.payment_date,

                'payment_description':
                    withdraw.payment_description or '',

                'created_at':
                    group['created_at'],

                'financial_document_number':
                    withdraw.financial_document_number,
            })

        return Response(result)

    @transaction.atomic
    def post(self, request):

        user = request.user

        serializer = ManagerBankTransferSerializer(
            data=request.data,
            context={'request': request}
        )

        serializer.is_valid(
            raise_exception=True
        )

        data = serializer.validated_data

        # ---------------------------------------------------------
        # دریافت ID بانک‌های مبدأ و مقصد
        # ---------------------------------------------------------

        from_bank_id = data['from_bank']
        to_bank_id = data['to_bank']

        # اگر serializer آبجکت Bank برگرداند،
        # این بخش همچنان درست کار می‌کند.
        if isinstance(from_bank_id, Bank):
            from_bank_id = from_bank_id.id

        if isinstance(to_bank_id, Bank):
            to_bank_id = to_bank_id.id

        # ---------------------------------------------------------
        # بانک‌های قابل دسترسی مدیر
        # ---------------------------------------------------------

        accessible_banks = self.get_user_banks(user)

        try:

            from_bank = accessible_banks.get(
                pk=from_bank_id
            )

        except Bank.DoesNotExist:

            return Response(
                {
                    'detail':
                        'حساب بانکی مبدأ معتبر نیست یا دسترسی به آن ندارید.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:

            to_bank = accessible_banks.get(
                pk=to_bank_id
            )

        except Bank.DoesNotExist:

            return Response(
                {
                    'detail':
                        'حساب بانکی مقصد معتبر نیست یا دسترسی به آن ندارید.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # ---------------------------------------------------------
        # مبدأ و مقصد نباید یکی باشند
        # ---------------------------------------------------------

        if from_bank.id == to_bank.id:

            return Response(
                {
                    'detail':
                        'حساب مبدأ و مقصد نمی‌توانند یکسان باشند.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        amount = data['amount']

        # ---------------------------------------------------------
        # شرح انتقال - اختیاری
        #
        # توجه:
        # نام فیلد Serializer برابر description است.
        # ---------------------------------------------------------

        payment_description = (
            data.get('description') or ''
        ).strip()

        # ---------------------------------------------------------
        # انجام انتقال
        # ---------------------------------------------------------

        try:

            BankTransactionService.transfer(
                user=user,

                from_bank=from_bank,

                to_bank=to_bank,

                amount=amount,

                unit=None,

                # شرحی که مدیر وارد کرده
                # اگر خالی باشد، خالی ذخیره می‌شود.
                description=payment_description,

                transaction_no=data.get(
                    'transaction_reference'
                ),

                payment_date=data['payment_date'],

                house=from_bank.house,
            )

        except ValueError as e:

            return Response(
                {
                    'detail': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            {
                'detail':
                    'انتقال وجه با موفقیت انجام شد.'
            },
            status=status.HTTP_201_CREATED
        )


# ============================================================
# ================= Cancel Bank Transfer ====================
# ============================================================


class ManagerBankTransferDeleteView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def delete(self, request, pk):

        user = request.user

        record = get_object_or_404(
            BankFund.objects.select_related(
                'bank',
                'to_bank'
            ),
            pk=pk,
            user=user,
            transfer_group_id__isnull=False
        )

        group_id = record.transfer_group_id

        transfer_records = list(
            BankFund.objects.filter(
                user=user,
                transfer_group_id=group_id
            ).select_related('bank')
        )

        if not transfer_records:
            return Response(
                {
                    'detail': 'رکورد انتقال پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        bank_ids = {
            item.bank_id
            for item in transfer_records
            if item.bank_id
        }

        # حذف هر دو طرف انتقال
        BankFund.objects.filter(
            user=user,
            transfer_group_id=group_id
        ).delete()

        # -----------------------------------------
        # بازسازی موجودی بانک‌ها
        # -----------------------------------------

        for bank_id in bank_ids:

            bank = Bank.objects.select_for_update().get(
                pk=bank_id
            )

            opening_amount = Decimal(
                bank.initial_fund or 0
            )

            deposits = BankFund.objects.filter(
                bank=bank,
                transaction_type='deposit'
            ).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            withdrawals = BankFund.objects.filter(
                bank=bank,
                transaction_type='withdraw'
            ).aggregate(
                total=Sum('amount')
            )['total'] or Decimal('0')

            # چون opening_amount داخل BankFund افتتاحیه هم هست،
            # آن را از جمع depositها کم می‌کنیم تا دوباره شمرده نشود.
            opening_bank_fund = BankFund.objects.filter(
                bank=bank,
                transaction_type='deposit',
                payment_description='افتتاح حساب'
            ).first()

            if opening_bank_fund:
                deposits_without_opening = (
                    deposits -
                    Decimal(opening_bank_fund.amount or 0)
                )
            else:
                deposits_without_opening = deposits

            new_balance = (
                opening_amount
                + deposits_without_opening
                - withdrawals
            )

            if new_balance < 0:
                new_balance = Decimal('0')

            bank.current_balance = new_balance

            bank.save(
                update_fields=['current_balance']
            )

        return Response(
            {
                'detail': 'انتقال با موفقیت لغو شد.'
            },
            status=status.HTTP_200_OK
        )
