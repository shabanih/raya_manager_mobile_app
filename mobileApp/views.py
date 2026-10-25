import json
import logging
import secrets
from collections import OrderedDict
from datetime import date

import jdatetime
from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum, ProtectedError, Prefetch
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from django.utils.dateparse import parse_date
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser

import requests

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.shortcuts import render, get_object_or_404

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password

from admin_panel.forms import FixChargeForm, AreaChargeForm, PersonChargeForm, FixAreaChargeForm, FixPersonChargeForm, \
    PersonAreaChargeForm, PersonAreaFixChargeForm, VariableFixChargeForm, CivilForm
from admin_panel.services.calculators import CALCULATORS, BaseCalculator
from admin_panel.services.utils import (
    get_next_financial_document_number
)

from rest_framework import status, serializers
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.views import APIView
from rest_framework.response import Response

from absharProject import settings
from admin_panel.models import UnifiedCharge, Fund, Announcement, CivilManage, CivilInstallment, SewageManage, \
    SewageInstallment, MessageReadStatus, MessageToUser, AnnouncementDocument, SmsManagement, SmsCredit, BankFund, \
    FixCharge, AreaCharge, Subscription, PersonCharge, FixAreaCharge, FixPersonCharge, ChargeByPersonArea, \
    ChargeByFixPersonArea, ChargeFixVariable, ChargeCalculation, Expense, Maintenance, ChargeCalculationItem, \
    ChargeAllocation, CivilDocument
from middleAdmin_panel.services.bank_services import BankTransactionService, validate_bank_transaction_date
from notifications.models import SupportUser, SupportMessage, Notification, SupportFile, AdminTicketFile, \
    AdminTicketMessage, AdminTicket, MiddleAdminNotification
from notifications.services.sms_service import SmsService, normalize_mobile
from polls_app.models import Poll, Vote, Choice, Question
from user_app.models import Unit, HousePaymentGateway, Renter, Bank, MyHouse, UserPayMoney, UnitResidenceHistory
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
    ManagerBankTransferListSerializer, ManagerBankTransferSerializer, ManagerBankSerializer, ManagerPollListSerializer,
    ManagerPollWriteSerializer, ManagerPollDetailSerializer, SupportTicketListSerializer, SupportTicketDetailSerializer,
    UserSupportTicketListSerializer, UserSupportTicketCreateSerializer, UserSupportTicketDetailSerializer,
    AdminTicketDetailSerializer, AdminTicketCreateSerializer, AdminTicketListSerializer,
    AdminTicketMessageCreateSerializer, ManagerUnitSerializer, ManagerRenterSerializer, ManagerChargeHomeCardSerializer,

)

User = get_user_model()


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):

        serializer = LoginSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعات ورود نامعتبر است.',
                    'errors': serializer.errors,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # دریافت شماره موبایل به جای username
        mobile = serializer.validated_data['mobile']
        password = serializer.validated_data['password']

        # =====================================================
        # پیدا کردن مدیر یا ساکن بر اساس شماره موبایل
        # =====================================================
        user = User.objects.filter(
            mobile=mobile,
            is_active=True
        ).filter(
            Q(is_middle_admin=True) |
            Q(is_unit=True)
        ).first()

        if not user or not check_password(password, user.password):
            return Response(
                {
                    'success': False,
                    'message': 'شماره موبایل یا رمز عبور اشتباه است.'
                },
                status=status.HTTP_401_UNAUTHORIZED
            )

        # =====================================================
        # تعیین نوع کاربر و ساختمان
        # =====================================================
        house = None

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

        # =====================================================
        # تولید JWT
        # =====================================================
        refresh = RefreshToken.for_user(user)

        return Response(
            {
                'success': True,
                'message': 'ورود با موفقیت انجام شد.',

                'access': str(refresh.access_token),
                'refresh': str(refresh),

                'user': {
                    'id': user.id,
                    'username': user.username,
                    'full_name': user.full_name,
                    'mobile': user.mobile,

                    'user_type': user_type,

                    'is_middle_admin': user.is_middle_admin,
                    'is_unit': user.is_unit,

                    'house_id': house.id if house else None,
                    'house_name': house.name if house else None,

                    'house': (
                        {
                            'id': house.id,
                            'name': house.name,
                            'subdomain': house.subdomain,
                            'city': house.city,
                        }
                        if house else None
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
        print()
        print("=============== MOBILE POLL LIST ===============")

        user = request.user

        print("USER:", user)
        print("USER ID:", user.id)

        # -------------------------------------------------
        # مجتمع کاربر
        # -------------------------------------------------

        user_house = user.house

        if not user_house:
            print("NO HOUSE")

            return Response({
                'success': False,
                'message': 'مجتمع کاربر مشخص نیست.',
                'polls': [],
            })

        print("HOUSE:", user_house)
        print("HOUSE ID:", user_house.id)

        # -------------------------------------------------
        # بررسی مالک بودن
        # -------------------------------------------------

        is_owner = Unit.objects.filter(
            myhouse=user_house,
            user=user,
            is_active=True,
        ).exists()

        # -------------------------------------------------
        # بررسی مستاجر بودن
        # -------------------------------------------------

        is_renter = Renter.objects.filter(
            unit__myhouse=user_house,
            unit__is_active=True,
            user=user,
            renter_is_active=True,
        ).exists()

        print("IS OWNER:", is_owner)
        print("IS RENTER:", is_renter)

        # -------------------------------------------------
        # اگر کاربر نه مالک است نه مستاجر
        # -------------------------------------------------

        if not is_owner and not is_renter:
            print("USER IS NOT ELIGIBLE FOR ANY POLL")

            return Response({
                'success': True,
                'count': 0,
                'polls': [],
            })

        # -------------------------------------------------
        # دریافت تمام نظرسنجی‌های فعال مجتمع
        #
        # نکته مهم:
        # اینجا دیگر start_date و end_date فیلتر نمی‌شوند.
        # بنابراین نظرسنجی آینده هم در لیست دیده می‌شود.
        # -------------------------------------------------

        polls = Poll.objects.filter(
            house=user_house,
            is_active=True,
        ).order_by('-created_at')

        print()
        print("=============== ALL ACTIVE HOUSE POLLS ===============")

        for poll in polls:
            print(
                "POLL ID:",
                poll.id,
                "| TITLE:",
                poll.title,
                "| TYPE:",
                repr(poll.participant_type),
                "| ACTIVE:",
                poll.is_active,
                "| START:",
                poll.start_date,
                "| END:",
                poll.end_date,
            )

        print("=======================================================")

        # -------------------------------------------------
        # فیلتر بر اساس نوع شرکت‌کننده
        # -------------------------------------------------

        eligible_polls = []

        for poll in polls:

            participant_type = (
                    poll.participant_type or 'all'
            ).strip().lower()

            # ---------------------------------------------
            # همه مالکین و مستاجرین
            # ---------------------------------------------

            if participant_type == 'all':

                if is_owner or is_renter:
                    eligible_polls.append(poll)

            # ---------------------------------------------
            # فقط مالکین
            # ---------------------------------------------

            elif participant_type == 'owners':

                if is_owner:
                    eligible_polls.append(poll)

            # ---------------------------------------------
            # فقط مستاجرین
            # ---------------------------------------------

            elif participant_type == 'renters':

                if is_renter:
                    eligible_polls.append(poll)

            # ---------------------------------------------
            # نوع نامعتبر
            # ---------------------------------------------

            else:
                print(
                    "INVALID PARTICIPANT TYPE:",
                    poll.id,
                    repr(poll.participant_type)
                )

        # -------------------------------------------------
        # نمایش نظرسنجی‌های مجاز
        # -------------------------------------------------

        print()
        print("=============== ELIGIBLE POLLS ===============")

        for poll in eligible_polls:
            participant_type = (
                    poll.participant_type or 'all'
            ).strip().lower()

            print(
                "POLL ID:",
                poll.id,
                "| TITLE:",
                poll.title,
                "| TYPE:",
                participant_type,
                "| START:",
                poll.start_date,
                "| END:",
                poll.end_date,
            )

        print(
            "TOTAL ELIGIBLE POLLS:",
            len(eligible_polls)
        )

        print("===============================================")

        # -------------------------------------------------
        # Serializer
        # -------------------------------------------------

        serializer = PollListSerializer(
            eligible_polls,
            many=True,
            context={
                'request': request,
            },
        )

        return Response({
            'success': True,
            'count': len(eligible_polls),
            'polls': serializer.data,
        })


class MobilePollDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):

        now = timezone.now()

        print()
        print("=============== MOBILE POLL DETAIL ===============")
        print("USER:", request.user)
        print("USER ID:", request.user.id)
        print("POLL ID:", pk)

        # =====================================================
        # مجتمع کاربر
        # =====================================================

        user_house = request.user.house

        if not user_house:
            return Response(
                {
                    'success': False,
                    'message':
                        'مجتمع کاربر مشخص نیست.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print(
            "USER HOUSE:",
            user_house
        )

        print(
            "USER HOUSE ID:",
            user_house.id
        )

        # =====================================================
        # پیدا کردن نظرسنجی
        # =====================================================

        try:

            poll = Poll.objects.select_related(
                'house'
            ).get(
                id=pk
            )

        except Poll.DoesNotExist:

            print("POLL FOUND: NO")

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
            "POLL HOUSE ID:",
            poll.house_id
        )

        print(
            "POLL ACTIVE:",
            poll.is_active
        )

        print(
            "POLL PARTICIPANT TYPE:",
            poll.participant_type
        )

        # =====================================================
        # بررسی مجتمع
        # =====================================================

        if poll.house_id != user_house.id:
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
                        'این نظرسنجی غیرفعال شده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی تاریخ شروع
        # =====================================================

        if poll.start_date > now:
            print(
                "POLL NOT STARTED"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'زمان شروع این نظرسنجی فرا نرسیده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی تاریخ پایان
        # =====================================================

        if poll.end_date < now:
            print(
                "POLL EXPIRED"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'زمان این نظرسنجی به پایان رسیده است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # تشخیص مالک فعال
        # =====================================================

        is_owner = Unit.objects.filter(
            myhouse=user_house,
            user=request.user,
            is_active=True,
        ).exists()

        print(
            "IS OWNER:",
            is_owner
        )

        # =====================================================
        # تشخیص مستأجر فعال
        # =====================================================

        is_renter = Renter.objects.filter(
            myhouse=user_house,
            unit__myhouse=user_house,
            unit__is_active=True,
            user=request.user,
            renter_is_active=True,
        ).exists()

        print(
            "IS RENTER:",
            is_renter
        )

        # =====================================================
        # کاربر باید مالک یا مستأجر فعال باشد
        # =====================================================

        if not is_owner and not is_renter:
            print(
                "USER IS NOT OWNER OR RENTER"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'شما مالک یا مستأجر فعال این مجتمع نیستید.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # بررسی participant_type
        # =====================================================

        participant_type = (
                poll.participant_type or 'all'
        ).strip().lower()

        print(
            "PARTICIPANT TYPE:",
            participant_type
        )

        # =====================================================
        # بررسی معتبر بودن participant_type
        # =====================================================

        if participant_type not in [
            'all',
            'owners',
            'renters',
        ]:
            print(
                "INVALID PARTICIPANT TYPE"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'نوع شرکت‌کنندگان این نظرسنجی نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # فقط مالکین
        # =====================================================

        if (
                participant_type == 'owners'
                and not is_owner
        ):
            print(
                "ACCESS DENIED - OWNERS ONLY"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی فقط برای مالکین فعال است.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # فقط مستأجرین
        # =====================================================

        if (
                participant_type == 'renters'
                and not is_renter
        ):
            print(
                "ACCESS DENIED - RENTERS ONLY"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی فقط برای مستأجرین فعال است.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        print(
            "PARTICIPANT ACCESS: OK"
        )

        # =====================================================
        # Serializer
        # =====================================================

        serializer = PollDetailSerializer(
            poll,
            context={
                'request': request,
            }
        )

        print(
            "POLL DETAIL SUCCESS"
        )

        print(
            "================================================"
        )

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
        print("USER HOUSE:", request.user.house)
        print("USER HOUSE ID:", request.user.house_id)
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
                    'message': 'مجتمع کاربر مشخص نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print("FINAL HOUSE:", house)
        print("FINAL HOUSE ID:", house.id)

        # =====================================================
        # پیدا کردن نظرسنجی
        # =====================================================

        try:
            poll = Poll.objects.get(id=pk)

        except Poll.DoesNotExist:

            print("POLL NOT FOUND")

            return Response(
                {
                    'success': False,
                    'message': 'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        print("POLL FOUND:", poll.id)
        print("POLL HOUSE:", poll.house)
        print("POLL HOUSE ID:", poll.house_id)
        print("POLL ACTIVE:", poll.is_active)
        print("POLL START:", poll.start_date)
        print("POLL END:", poll.end_date)
        print(
            "POLL PARTICIPANT TYPE:",
            poll.participant_type
        )

        # =====================================================
        # بررسی مجتمع
        # =====================================================

        if poll.house_id != house.id:
            print("HOUSE MATCH: FALSE")

            return Response(
                {
                    'success': False,
                    'message': 'این نظرسنجی برای مجتمع شما فعال نیست.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        print("HOUSE MATCH: TRUE")

        # =====================================================
        # بررسی فعال بودن
        # =====================================================

        if not poll.is_active:
            print("POLL ACTIVE: FALSE")

            return Response(
                {
                    'success': False,
                    'message': 'این نظرسنجی غیرفعال است.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        # =====================================================
        # بررسی تاریخ شروع
        # =====================================================

        if poll.start_date > now:
            print("START DATE: NOT STARTED")

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
            print("END DATE: EXPIRED")

            return Response(
                {
                    'success': False,
                    'message':
                        'زمان این نظرسنجی به پایان رسیده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print("POLL DATE: OK")

        # =====================================================
        # تشخیص مالک بودن کاربر
        # =====================================================

        owner_unit = Unit.objects.filter(
            myhouse=house,
            user=request.user,
            is_active=True,
        ).first()

        is_owner = owner_unit is not None

        print("IS OWNER:", is_owner)
        print(
            "OWNER UNIT:",
            owner_unit
        )
        print(
            "OWNER UNIT ID:",
            getattr(owner_unit, 'id', None)
        )

        # =====================================================
        # تشخیص مستأجر بودن کاربر
        # =====================================================

        active_renter = Renter.objects.filter(
            myhouse=house,
            unit__myhouse=house,
            unit__is_active=True,
            user=request.user,
            renter_is_active=True,
        ).select_related(
            'unit'
        ).first()

        is_renter = active_renter is not None

        print("IS RENTER:", is_renter)
        print(
            "ACTIVE RENTER:",
            active_renter
        )
        print(
            "RENTER UNIT ID:",
            getattr(
                active_renter,
                'unit_id',
                None
            )
        )

        # =====================================================
        # کاربر باید مالک یا مستأجر فعال باشد
        # =====================================================

        if not is_owner and not is_renter:
            print("USER IS NOT OWNER OR RENTER")

            return Response(
                {
                    'success': False,
                    'message':
                        'شما در این مجتمع مالک یا مستأجر فعال نیستید.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # =====================================================
        # بررسی نوع شرکت‌کنندگان نظرسنجی
        # =====================================================

        participant_type = (
                poll.participant_type or 'all'
        ).strip().lower()

        print(
            "FINAL PARTICIPANT TYPE:",
            participant_type
        )

        # -----------------------------------------------------
        # فقط مالکین
        # -----------------------------------------------------

        if participant_type == 'owners' and not is_owner:
            print(
                "ACCESS DENIED: POLL IS FOR OWNERS ONLY"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی فقط برای مالکین فعال است.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -----------------------------------------------------
        # فقط مستأجرین
        # -----------------------------------------------------

        if participant_type == 'renters' and not is_renter:
            print(
                "ACCESS DENIED: POLL IS FOR RENTERS ONLY"
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'این نظرسنجی فقط برای مستأجرین فعال است.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -----------------------------------------------------
        # مقدار نامعتبر participant_type
        # -----------------------------------------------------

        if participant_type not in [
            'all',
            'owners',
            'renters',
        ]:
            print(
                "INVALID PARTICIPANT TYPE:",
                participant_type
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'نوع شرکت‌کنندگان این نظرسنجی نامعتبر است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print("PARTICIPANT ACCESS: OK")

        # =====================================================
        # تعیین واحد معتبر برای ثبت رأی
        # =====================================================

        if is_owner and participant_type in [
            'all',
            'owners',
        ]:

            unit = owner_unit

        elif is_renter and participant_type in [
            'all',
            'renters',
        ]:

            unit = active_renter.unit

        else:

            return Response(
                {
                    'success': False,
                    'message':
                        'واحد مجاز برای ثبت رأی پیدا نشد.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # بررسی نهایی واحد
        # =====================================================

        if unit is None:
            print("UNIT NOT FOUND")

            return Response(
                {
                    'success': False,
                    'message':
                        'واحدی برای کاربر شما در این مجتمع پیدا نشد.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        print("FINAL USER UNIT:", unit)
        print("FINAL USER UNIT ID:", unit.id)

        # =====================================================
        # جلوگیری از رأی مجدد
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

        answers = request.data.get('answers')

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
        # سؤال‌های نظرسنجی
        # =====================================================

        poll_questions = {
            question.id: question
            for question in Question.objects.filter(
                poll=poll
            )
        }

        processed_questions = set()

        # =====================================================
        # پردازش پاسخ‌ها
        # =====================================================

        for answer in answers:

            if not isinstance(answer, dict):
                return Response(
                    {
                        'success': False,
                        'message':
                            'ساختار پاسخ نامعتبر است.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # شناسه سؤال
            # -------------------------------------------------

            question_id = answer.get(
                'question_id'
            )

            # -------------------------------------------------
            # شناسه گزینه‌ها
            # -------------------------------------------------

            choice_ids = answer.get(
                'choice_ids',
                []
            )

            # -------------------------------------------------
            # بررسی شناسه سؤال
            # -------------------------------------------------

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

            # -------------------------------------------------
            # سؤال تکراری
            # -------------------------------------------------

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

            # -------------------------------------------------
            # پیدا کردن سؤال
            # -------------------------------------------------

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

            # -------------------------------------------------
            # بررسی لیست گزینه‌ها
            # -------------------------------------------------

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
            # تبدیل ID گزینه‌ها به عدد
            # -------------------------------------------------

            normalized_choice_ids = []

            for choice_id in choice_ids:

                try:

                    normalized_choice_ids.append(
                        int(choice_id)
                    )

                except (TypeError, ValueError):

                    return Response(
                        {
                            'success': False,
                            'message':
                                'شناسه یکی از گزینه‌ها نامعتبر است.'
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

            choice_ids = normalized_choice_ids

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
            # نوع سؤال نامعتبر
            # -------------------------------------------------

            else:

                return Response(
                    {
                        'success': False,
                        'message':
                            'نوع سؤال نامعتبر است.'
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
            # جلوگیری از انتخاب خالی
            # -------------------------------------------------

            if not choice_ids:
                return Response(
                    {
                        'success': False,
                        'message':
                            'حداقل یک گزینه باید انتخاب شود.'
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # -------------------------------------------------
            # بررسی گزینه‌ها
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
        # بررسی پاسخ همه سؤال‌ها
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
            transaction.set_rollback(
                True
            )

            return Response(
                {
                    'success': False,
                    'message':
                        'لطفاً به همه سؤال‌ها پاسخ دهید.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =====================================================
        # رأی با موفقیت ثبت شد
        # =====================================================

        print("VOTE SUCCESS")
        print("================================================")

        return Response(
            {
                'success': True,
                'message':
                    'رأی شما با موفقیت ثبت شد.'
            },
            status=status.HTTP_200_OK,
        )


# =====================================================
# لیست شارژهای عمرانی
# =====================================================
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
    authentication_classes = [
        JWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    # =====================================================
    # ساختمان‌های قابل دسترسی مدیر
    # =====================================================

    def get_accessible_houses(self, user):

        return MyHouse.objects.filter(
            Q(user=user) |
            Q(user__manager=user),
            is_active=True
        )

    # =====================================================
    # حساب‌های بانکی قابل دسترسی
    # =====================================================

    def get_user_banks(self, user):

        accessible_houses = (
            self.get_accessible_houses(user)
        )

        return (
            Bank.objects
            .filter(
                user=user,
                is_active=True,
                house__in=accessible_houses
            )
            .select_related('house')
        )

    # =====================================================
    # GET
    # =====================================================

    def get(self, request):

        user = request.user

        banks = self.get_user_banks(user)

        bank_ids = list(
            banks.values_list(
                'id',
                flat=True
            )
        )

        transfers = (
            BankFund.objects
            .filter(
                user=user,
                transfer_group_id__isnull=False,
                bank_id__in=bank_ids
            )
            .select_related(
                'bank',
                'to_bank',
                'house'
            )
            .order_by('-created_at')
        )

        groups = {}

        for item in transfers:

            group_id = str(
                item.transfer_group_id
            )

            if group_id not in groups:
                groups[group_id] = {
                    'transfer_group_id':
                        group_id,

                    'withdraw':
                        None,

                    'deposit':
                        None,

                    'created_at':
                        item.created_at,
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

                'id':
                    withdraw.id,

                'transfer_group_id':
                    group['transfer_group_id'],

                # -----------------------------------------
                # بانک مبدأ
                # -----------------------------------------

                'from_bank_id':
                    withdraw.bank_id,

                'from_bank_name':
                    (
                        withdraw.bank.bank_name
                        if withdraw.bank
                        else None
                    ),

                # -----------------------------------------
                # بانک مقصد
                # -----------------------------------------

                'to_bank_id':
                    deposit.bank_id,

                'to_bank_name':
                    (
                        deposit.bank.bank_name
                        if deposit.bank
                        else None
                    ),

                # -----------------------------------------
                # مبلغ
                # -----------------------------------------

                'amount':
                    str(
                        withdraw.amount or 0
                    ),

                # -----------------------------------------
                # شماره تراکنش
                # -----------------------------------------

                'transaction_no':
                    withdraw.transaction_no,

                # -----------------------------------------
                # تاریخ
                # -----------------------------------------

                'payment_date':
                    withdraw.payment_date,

                # -----------------------------------------
                # شرح
                # -----------------------------------------

                'payment_description':
                    withdraw.payment_description or '',

                # -----------------------------------------
                # تاریخ ایجاد
                # -----------------------------------------

                'created_at':
                    group['created_at'],

                # -----------------------------------------
                # سند مالی
                # -----------------------------------------

                'financial_document_number':
                    withdraw.financial_document_number,
            })

        return Response(
            result,
            status=status.HTTP_200_OK
        )

    # =====================================================
    # POST
    # =====================================================

    @transaction.atomic
    def post(self, request):

        user = request.user

        serializer = (
            ManagerBankTransferSerializer(
                data=request.data,
                context={
                    'request': request
                }
            )
        )

        serializer.is_valid(
            raise_exception=True
        )

        data = serializer.validated_data

        from_bank = data.get(
            'from_bank_obj'
        )

        to_bank = data.get(
            'to_bank_obj'
        )

        if not from_bank or not to_bank:
            return Response(
                {
                    'detail':
                        'حساب‌های بانکی معتبر نیستند.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # -------------------------------------------------
        # شرح انتقال
        # -------------------------------------------------

        payment_description = (
                data.get('description') or ''
        ).strip()

        # -------------------------------------------------
        # انتقال
        # -------------------------------------------------

        try:

            BankTransactionService.transfer(

                user=user,

                from_bank=from_bank,

                to_bank=to_bank,

                amount=data['amount'],

                unit=None,

                description=payment_description,

                transaction_no=data.get(
                    'transaction_reference'
                ),

                payment_date=data[
                    'payment_date'
                ],

                house=from_bank.house,
            )

        except ValueError as e:

            return Response(
                {
                    'detail':
                        str(e)
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


# ============================================================
# =================== Polls =========================
# ============================================================

class ManagerPollBaseView(APIView):
    authentication_classes = [
        JWTAuthentication
    ]

    permission_classes = [
        IsAuthenticated
    ]

    def get_house(self, user):

        return MyHouse.objects.filter(
            user=user,
            is_active=True
        ).first()

    def get_poll(self, user, poll_id):

        house = self.get_house(user)

        if not house:
            return None

        return (
            Poll.objects
            .filter(
                id=poll_id,
                house=house
            )
            .prefetch_related(
                'questions__choices'
            )
            .first()
        )

    def check_manager(self, request):

        if not request.user.is_authenticated:
            return False

        if not request.user.is_middle_admin:
            return False

        return True

    # ========================================================
    # تعداد مالکین فعال
    # ========================================================

    def get_active_owner_count(self, house):

        return house.units.filter(
            is_active=True
        ).count()

    # ========================================================
    # تعداد مستاجرین فعال
    # ========================================================

    def get_active_renter_count(self, house):

        return Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True
        ).count()

    # ========================================================
    # تعداد افراد مجاز به شرکت
    # ========================================================

    def get_eligible_counts(self, poll):

        house = poll.house

        owner_count = self.get_active_owner_count(
            house
        )

        renter_count = self.get_active_renter_count(
            house
        )

        if poll.participant_type == 'owners':

            eligible_count = owner_count

        elif poll.participant_type == 'renters':

            eligible_count = renter_count

        else:

            eligible_count = (
                    owner_count +
                    renter_count
            )

        return {
            'owner_count': owner_count,
            'renter_count': renter_count,
            'eligible_count': eligible_count,
        }

    # ========================================================
    # بررسی مجاز بودن کاربر برای شرکت در نظرسنجی
    # ========================================================

    def is_user_eligible_for_poll(
            self,
            poll,
            user
    ):

        if not user or not user.is_authenticated:
            return False

        house = poll.house

        # ---------------------------------------------
        # واحد فعال متعلق به کاربر
        # ---------------------------------------------

        owner_unit_exists = house.units.filter(
            user=user,
            is_active=True
        ).exists()

        # ---------------------------------------------
        # مستاجر فعال
        # ---------------------------------------------

        renter_exists = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            user=user,
            renter_is_active=True
        ).exists()

        # ---------------------------------------------
        # همه
        # ---------------------------------------------

        if poll.participant_type == 'all':
            return (
                    owner_unit_exists or
                    renter_exists
            )

        # ---------------------------------------------
        # فقط مالکین
        # ---------------------------------------------

        if poll.participant_type == 'owners':
            return owner_unit_exists

        # ---------------------------------------------
        # فقط مستاجرین
        # ---------------------------------------------

        if poll.participant_type == 'renters':
            return renter_exists

        return False


# ============================================================
# LIST + CREATE
# ============================================================

class ManagerPollListCreateView(
    ManagerPollBaseView
):

    def get(self, request):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        house = self.get_house(
            request.user
        )

        if not house:
            return Response(
                {
                    'detail':
                        'ساختمان فعال پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        polls = (
            Poll.objects
            .filter(
                house=house
            )
            .order_by('-created_at')
        )

        search = (
            request.GET.get(
                'search',
                ''
            ).strip()
        )

        if search:
            polls = polls.filter(
                Q(title__icontains=search)
                |
                Q(description__icontains=search)
            )

        serializer = ManagerPollListSerializer(
            polls,
            many=True
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    @transaction.atomic
    def post(self, request):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = ManagerPollWriteSerializer(
            data=request.data,
            context={
                'request': request
            }
        )

        serializer.is_valid(
            raise_exception=True
        )

        poll = serializer.save()

        result_serializer = (
            ManagerPollDetailSerializer(
                poll
            )
        )

        return Response(
            result_serializer.data,
            status=status.HTTP_201_CREATED
        )


# ============================================================
# DETAIL + UPDATE + DELETE
# ============================================================

class ManagerPollDetailView(
    ManagerPollBaseView
):

    def get(self, request, poll_id):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        poll = self.get_poll(
            request.user,
            poll_id
        )

        if not poll:
            return Response(
                {
                    'detail':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = ManagerPollDetailSerializer(
            poll
        )

        return Response(
            serializer.data,
            status=status.HTTP_200_OK
        )

    @transaction.atomic
    def put(self, request, poll_id):

        return self._update(
            request,
            poll_id,
            partial=False
        )

    @transaction.atomic
    def patch(self, request, poll_id):

        return self._update(
            request,
            poll_id,
            partial=True
        )

    def _update(
            self,
            request,
            poll_id,
            partial=False
    ):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        poll = self.get_poll(
            request.user,
            poll_id
        )

        if not poll:
            return Response(
                {
                    'detail':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ====================================================
        # قانون اصلی:
        # نظرسنجی دارای پاسخ قابل ویرایش نیست.
        # ====================================================

        has_votes = Vote.objects.filter(
            poll=poll
        ).exists()

        if has_votes:
            return Response(
                {
                    'detail':
                        'این نظرسنجی دارای پاسخ است و قابل ویرایش نیست.',
                    'has_votes': True,
                    'can_edit': False,
                    'can_delete': False,
                    'can_deactivate': True,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = ManagerPollWriteSerializer(
            poll,
            data=request.data,
            partial=partial,
            context={
                'request': request
            }
        )

        serializer.is_valid(
            raise_exception=True
        )

        poll = serializer.save()

        result_serializer = (
            ManagerPollDetailSerializer(
                poll
            )
        )

        return Response(
            result_serializer.data,
            status=status.HTTP_200_OK
        )

    # ========================================================
    # DELETE
    # ========================================================

    @transaction.atomic
    def delete(self, request, poll_id):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        poll = self.get_poll(
            request.user,
            poll_id
        )

        if not poll:
            return Response(
                {
                    'detail':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        has_votes = Vote.objects.filter(
            poll=poll
        ).exists()

        if has_votes:
            return Response(
                {
                    'detail':
                        'این نظرسنجی دارای پاسخ است و حذف آن امکان‌پذیر نیست.',
                    'has_votes': True,
                    'can_edit': False,
                    'can_delete': False,
                    'can_deactivate': True,
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        poll.delete()

        return Response(
            {
                'detail':
                    'نظرسنجی با موفقیت حذف شد.'
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# ACTIVATE / DEACTIVATE
# ============================================================

class ManagerPollToggleActiveView(
    ManagerPollBaseView
):

    @transaction.atomic
    def patch(self, request, poll_id):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        poll = self.get_poll(
            request.user,
            poll_id
        )

        if not poll:
            return Response(
                {
                    'detail':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        is_active = request.data.get(
            'is_active'
        )

        if is_active is None:
            return Response(
                {
                    'detail':
                        'مقدار is_active ارسال نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        if not isinstance(
                is_active,
                bool
        ):
            return Response(
                {
                    'detail':
                        'مقدار is_active باید true یا false باشد.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        poll.is_active = is_active
        poll.save(
            update_fields=[
                'is_active'
            ]
        )

        return Response(
            {
                'detail':
                    (
                        'نظرسنجی فعال شد.'
                        if is_active
                        else
                        'نظرسنجی غیرفعال شد.'
                    ),
                'is_active':
                    poll.is_active,
            },
            status=status.HTTP_200_OK
        )


# ============================================================
# RESULTS
# ============================================================

class ManagerPollResultsView(
    ManagerPollBaseView
):

    def get(self, request, poll_id):

        if not self.check_manager(request):
            return Response(
                {
                    'detail':
                        'دسترسی فقط برای مدیر ساختمان مجاز است.'
                },
                status=status.HTTP_403_FORBIDDEN
            )

        poll = self.get_poll(
            request.user,
            poll_id
        )

        if not poll:
            return Response(
                {
                    'detail':
                        'نظرسنجی پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND
            )

        # ====================================================
        # افراد مجاز
        # ====================================================

        eligible_data = self.get_eligible_counts(
            poll
        )

        owner_count = eligible_data[
            'owner_count'
        ]

        renter_count = eligible_data[
            'renter_count'
        ]

        eligible_users = eligible_data[
            'eligible_count'
        ]

        # ====================================================
        # شرکت کنندگان
        # ====================================================

        participants = (
            Vote.objects
            .filter(
                poll=poll
            )
            .values(
                'user'
            )
            .distinct()
            .count()
        )

        # ====================================================
        # عدم شرکت
        # ====================================================

        not_participated = max(
            eligible_users - participants,
            0
        )

        # ====================================================
        # درصد مشارکت
        # ====================================================

        if eligible_users:

            participation_percentage = round(
                (
                        participants /
                        eligible_users
                ) * 100,
                1
            )

        else:

            participation_percentage = 0

        # ====================================================
        # نتایج سوالات
        # ====================================================

        questions_result = []

        questions = (
            poll.questions
            .prefetch_related(
                'choices'
            )
            .order_by(
                'order'
            )
        )

        for question in questions:

            question_participants = (
                Vote.objects
                .filter(
                    question=question
                )
                .values(
                    'user'
                )
                .distinct()
                .count()
            )

            choices_result = []

            for choice in question.choices.all():

                vote_count = (
                    Vote.objects
                    .filter(
                        choice=choice
                    )
                    .count()
                )

                if question_participants:

                    percentage = round(
                        (
                                vote_count /
                                question_participants
                        ) * 100,
                        1
                    )

                else:

                    percentage = 0

                choices_result.append({
                    'id':
                        choice.id,

                    'title':
                        choice.title,

                    'vote_count':
                        vote_count,

                    'percentage':
                        percentage,
                })

            questions_result.append({

                'id':
                    question.id,

                'title':
                    question.title,

                'question_type':
                    question.question_type,

                'order':
                    question.order,

                'participant_count':
                    question_participants,

                'choices':
                    choices_result,
            })

        # ====================================================
        # Response
        # ====================================================

        return Response(
            {

                'poll': {

                    'id':
                        poll.id,

                    'title':
                        poll.title,

                    'description':
                        poll.description,

                    'start_date':
                        poll.start_date,

                    'end_date':
                        poll.end_date,

                    'is_active':
                        poll.is_active,

                    'participant_type':
                        poll.participant_type,
                },

                'participation': {

                    'owner_count':
                        owner_count,

                    'renter_count':
                        renter_count,

                    'eligible_count':
                        eligible_users,

                    'participant_count':
                        participants,

                    'not_participated_count':
                        not_participated,

                    'percentage':
                        participation_percentage,
                },

                'questions':
                    questions_result,
            },

            status=status.HTTP_200_OK
        )


# ============================================================
# TICKET TO USER
# ============================================================
class MobileSupportTicketCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request):

        user = request.user

        subject = request.data.get('subject')
        message = request.data.get('message')
        is_call = request.data.get('is_call', False)

        if not subject:
            return Response({
                'success': False,
                'message': 'عنوان تیکت الزامی است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        if not message:
            return Response({
                'success': False,
                'message': 'متن پیام الزامی است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # تبدیل is_call به boolean
        # -------------------------------------------------

        if isinstance(is_call, str):
            is_call = is_call.lower() in [
                'true',
                '1',
                'yes',
                'on',
            ]

        # -------------------------------------------------
        # پیدا کردن مجتمع کاربر
        # -------------------------------------------------

        house = getattr(user, 'house', None)

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع کاربر مشخص نیست.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # ایجاد تیکت
        # -------------------------------------------------

        ticket = SupportUser.objects.create(
            user=user,
            subject=subject,
            message=message,
            is_sent=True,
            is_read=False,
            is_call=is_call,
            is_closed=False,
            is_answer=False,
            is_waiting=True,
        )

        # -------------------------------------------------
        # پیام اولیه
        # -------------------------------------------------

        support_message = SupportMessage.objects.create(
            support_user=ticket,
            sender=user,
            message=message,
            is_read=False,
        )

        # -------------------------------------------------
        # پیدا کردن مدیران ساختمان
        #
        # مدیرانی که MyHouse مربوط به آنهاست
        # -------------------------------------------------

        managers = User.objects.filter(
            is_middle_admin=True,
            myhouse__id=house.id,
        ).distinct()

        # -------------------------------------------------
        # Notification برای مدیر
        # -------------------------------------------------

        notifications = []

        for manager in managers:
            notifications.append(
                Notification(
                    user=manager,
                    ticket=ticket,
                    title='تیکت جدید',
                    message=(
                        f'تیکت جدید با شماره '
                        f'{ticket.ticket_no} برای شما ارسال شد.'
                    ),
                    link=f'/support/tickets/{ticket.id}/',
                    is_read=False,
                )
            )

        if notifications:
            Notification.objects.bulk_create(
                notifications
            )

        return Response({
            'success': True,
            'message': 'تیکت با موفقیت ارسال شد.',
            'ticket': {
                'id': ticket.id,
                'ticket_no': ticket.ticket_no,
                'subject': ticket.subject,
                'is_call': ticket.is_call,
                'created_at': ticket.created_at,
            }
        }, status=status.HTTP_201_CREATED)


class MobileSupportTicketListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        tickets = (
            SupportUser.objects
            .filter(user=user)
            .prefetch_related(
                'messages__sender',
                'messages__attachments',
            )
            .order_by('-updated_at')
        )

        serializer = SupportTicketListSerializer(
            tickets,
            many=True,
            context={
                'request': request
            }
        )

        return Response({
            'success': True,
            'count': tickets.count(),
            'tickets': serializer.data,
        })


class MobileSupportTicketDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):
        ticket = (
            SupportUser.objects
            .filter(
                id=ticket_id,
                user=request.user,
            )
            .prefetch_related(
                'messages__sender',
                'messages__attachments',
                'files',
            )
            .first()
        )

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # -------------------------------------------------
        # پیام‌های مدیر را خوانده‌شده کن
        # -------------------------------------------------

        ticket.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).update(
            is_read=True
        )

        # Notification مربوط به این تیکت نیز خوانده شود
        Notification.objects.filter(
            user=request.user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True
        )

        serializer = SupportTicketDetailSerializer(
            ticket,
            context={
                'request': request
            }
        )

        return Response({
            'success': True,
            'ticket': serializer.data,
        })


class MobileSupportTicketMessageView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, ticket_id):

        ticket = SupportUser.objects.filter(
            id=ticket_id,
            user=request.user,
        ).first()

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_closed:
            return Response({
                'success': False,
                'message': 'این تیکت بسته شده است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        message = request.data.get('message')

        if not message:
            return Response({
                'success': False,
                'message': 'متن پیام الزامی است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        support_message = SupportMessage.objects.create(
            support_user=ticket,
            sender=request.user,
            message=message,
            is_read=False,
        )

        # -------------------------------------------------
        # وضعیت تیکت
        # -------------------------------------------------

        ticket.is_answer = True
        ticket.is_waiting = True
        ticket.is_read = False
        ticket.updated_at = timezone.now()
        ticket.save(
            update_fields=[
                'is_answer',
                'is_waiting',
                'is_read',
                'updated_at',
            ]
        )

        # -------------------------------------------------
        # پیدا کردن مجتمع
        # -------------------------------------------------

        house = getattr(
            request.user,
            'house',
            None
        )

        if house:

            managers = User.objects.filter(
                is_middle_admin=True,
                myhouse__id=house.id,
            ).distinct()

            notifications = []

            for manager in managers:
                notifications.append(
                    Notification(
                        user=manager,
                        ticket=ticket,
                        title='پاسخ جدید به تیکت',
                        message=(
                            f'در تیکت شماره '
                            f'{ticket.ticket_no} پیام جدیدی دریافت شد.'
                        ),
                        link=f'/support/tickets/{ticket.id}/',
                        is_read=False,
                    )
                )

            if notifications:
                Notification.objects.bulk_create(
                    notifications
                )

        return Response({
            'success': True,
            'message': 'پیام شما ارسال شد.',
            'message_id': support_message.id,
        }, status=status.HTTP_201_CREATED)


class MobileSupportTicketCloseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):

        ticket = SupportUser.objects.filter(
            id=ticket_id,
            user=request.user,
        ).first()

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_closed:
            return Response({
                'success': False,
                'message': 'این تیکت قبلاً بسته شده است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        ticket.is_closed = True
        ticket.is_waiting = False
        ticket.save(
            update_fields=[
                'is_closed',
                'is_waiting',
                'updated_at',
            ]
        )

        return Response({
            'success': True,
            'message': 'تیکت بسته شد.',
        })


# ============================================================
# Resident TICKET
# ============================================================

def notify_managers_about_ticket(ticket, title, message):
    """
    پیدا کردن مدیران مجتمع مربوط به ساکن و ایجاد Notification
    برای آنها.

    ساکن می‌تواند:
    - مالک واحد باشد
    - مستاجر فعال واحد باشد
    """

    resident = ticket.user

    # --------------------------------------------------------
    # مجتمع‌هایی که ساکن مالک واحد آنهاست
    # --------------------------------------------------------

    owner_house_ids = Unit.objects.filter(
        user=resident,
        is_active=True,
    ).values_list(
        'myhouse_id',
        flat=True,
    )

    # --------------------------------------------------------
    # مجتمع‌هایی که ساکن مستاجر فعال آنهاست
    # --------------------------------------------------------

    renter_house_ids = Renter.objects.filter(
        user=resident,
        unit__is_active=True,
        renter_is_active=True,
    ).values_list(
        'unit__myhouse_id',
        flat=True,
    )

    # --------------------------------------------------------
    # تمام مجتمع‌های مرتبط با ساکن
    # --------------------------------------------------------

    house_ids = set(owner_house_ids) | set(renter_house_ids)

    if not house_ids:
        return 0

    # --------------------------------------------------------
    # مدیران مجتمع
    # --------------------------------------------------------

    manager_user_ids = (
        MyHouse.objects
        .filter(
            id__in=house_ids,
            is_active=True,
        )
        .exclude(
            user_id=resident.id,
        )
        .values_list(
            'user_id',
            flat=True,
        )
        .distinct()
    )

    manager_user_ids = list(manager_user_ids)

    if not manager_user_ids:
        return 0

    # --------------------------------------------------------
    # ایجاد Notification برای مدیران
    # --------------------------------------------------------

    notifications = []

    for manager_user_id in manager_user_ids:
        notifications.append(
            Notification(
                user_id=manager_user_id,
                ticket=ticket,
                title=title,
                message=message,
                link=f'/support/tickets/{ticket.id}/',
                is_read=False,
            )
        )

    Notification.objects.bulk_create(
        notifications
    )

    return len(notifications)


def get_user_ticket(user, ticket_id):
    return get_object_or_404(
        SupportUser.objects
        .select_related('user')
        .prefetch_related(
            'files',
            'messages__sender',
            'messages__attachments',
        ),
        id=ticket_id,
        user=user,
    )


# =========================================================
# لیست تیکت‌ها + ایجاد تیکت
# =========================================================

class UserSupportTicketListCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        JSONParser,
        MultiPartParser,
        FormParser,
    ]

    # -----------------------------------------------------
    # GET
    # -----------------------------------------------------

    def get(self, request):
        tickets = (
            SupportUser.objects
            .filter(user=request.user)
            .prefetch_related(
                'messages__sender'
            )
            .order_by(
                '-updated_at'
            )
        )

        serializer = UserSupportTicketListSerializer(
            tickets,
            many=True,
            context={
                'request': request,
            },
        )

        return Response({
            'success': True,
            'tickets': serializer.data,
        })

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    # -----------------------------------------------------
    # POST
    # -----------------------------------------------------

    @transaction.atomic
    def post(self, request):
        serializer = UserSupportTicketCreateSerializer(
            data=request.data
        )

        serializer.is_valid(
            raise_exception=True
        )

        ticket = serializer.save(
            user=request.user,
            is_sent=True,
            is_read=False,
            is_answer=False,
            is_waiting=False,
            is_closed=False,
        )

        # =================================================
        # پیام اولیه
        # =================================================

        support_message = SupportMessage.objects.create(
            support_user=ticket,
            sender=request.user,
            message=ticket.message,
            is_read=True,
        )

        # =================================================
        # فایل
        # =================================================

        uploaded_file = request.FILES.get('file')

        if uploaded_file:
            support_file = SupportFile.objects.create(
                support_user=ticket,
                file=uploaded_file,
            )

            support_message.attachments.add(
                support_file
            )

        # =================================================
        # Notification برای مدیر مجتمع
        # =================================================

        notify_managers_about_ticket(
            ticket=ticket,
            title='تیکت جدید',
            message=(
                f'ساکن یک تیکت جدید با شماره '
                f'{ticket.ticket_no} ایجاد کرده است.'
            ),
        )

        # =================================================
        # پاسخ
        # =================================================

        response_serializer = (
            UserSupportTicketDetailSerializer(
                ticket,
                context={
                    'request': request,
                },
            )
        )

        return Response(
            {
                'success': True,
                'message': 'تیکت با موفقیت ایجاد شد.',
                'ticket': response_serializer.data,
            },
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# جزئیات تیکت
# =========================================================

class UserSupportTicketDetailView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request, ticket_id):
        print(
            '========================================'
        )
        print(
            '🔥🔥🔥 DETAIL VIEW CALLED 🔥🔥🔥'
        )
        print(
            'TICKET ID:',
            ticket_id
        )
        print(
            'URL:',
            request.path
        )
        print(
            '========================================'
        )

        ticket = get_user_ticket(
            request.user,
            ticket_id,
        )

        # =================================================
        # پیام‌های مدیر خوانده شده‌اند
        # =================================================

        ticket.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).update(
            is_read=True
        )

        # =================================================
        # Notificationهای مربوط به این تیکت
        # =================================================

        Notification.objects.filter(
            user=request.user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True
        )

        serializer = UserSupportTicketDetailSerializer(
            ticket,
            context={
                'request': request,
            },
        )

        print(
            '🔥 DETAIL SERIALIZER DATA:',
            serializer.data,
        )

        return Response({
            'success': True,
            'ticket': serializer.data,
        })


# =========================================================
# ارسال پیام
# =========================================================

class UserSupportTicketMessageView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
    ]

    @transaction.atomic
    def post(self, request, ticket_id):

        ticket = get_user_ticket(
            request.user,
            ticket_id,
        )

        # =================================================
        # تیکت بسته شده
        # =================================================

        if ticket.is_closed:
            return Response(
                {
                    'success': False,
                    'message':
                        'این تیکت بسته شده است.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =================================================
        # متن پیام
        # =================================================

        message_text = (
                request.data.get('message') or ''
        )

        message_text = str(
            message_text
        ).strip()

        # =================================================
        # فایل
        # =================================================

        uploaded_file = request.FILES.get(
            'file'
        )

        # =================================================
        # حداقل متن یا فایل باید وجود داشته باشد
        # =================================================

        if not message_text and not uploaded_file:
            return Response(
                {
                    'success': False,
                    'message':
                        'متن پیام یا فایل را وارد کنید.',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # =================================================
        # ایجاد پیام
        # =================================================

        message = SupportMessage.objects.create(
            support_user=ticket,
            sender=request.user,
            message=message_text,
            is_read=True,
        )

        # =================================================
        # فایل
        # =================================================

        if uploaded_file:

            content_type = getattr(
                uploaded_file,
                'content_type',
                '',
            )

            if not content_type.startswith(
                    'image/'
            ):
                return Response(
                    {
                        'success': False,
                        'message':
                            'فقط فایل‌های تصویری قابل ارسال هستند.',
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            support_file = SupportFile.objects.create(
                support_user=ticket,
                file=uploaded_file,
            )

            message.attachments.add(
                support_file
            )

        # =================================================
        # وضعیت تیکت
        #
        # وقتی ساکن پیام می‌فرستد:
        # تیکت دوباره منتظر پاسخ مدیر است.
        # =================================================

        ticket.is_waiting = False
        ticket.is_answer = False
        ticket.is_sent = True
        ticket.is_closed = False

        # بسیار مهم:
        # برای مدیر یعنی پیام جدید خوانده نشده است.
        ticket.is_read = False

        ticket.save(
            update_fields=[
                'is_waiting',
                'is_answer',
                'is_sent',
                'is_closed',
                'is_read',
                'updated_at',
            ]
        )

        # =================================================
        # Notification برای مدیر مجتمع
        # =================================================

        notify_managers_about_ticket(
            ticket=ticket,
            title='پیام جدید در تیکت',
            message=(
                f'ساکن در تیکت شماره '
                f'{ticket.ticket_no} '
                f'پیام جدیدی ارسال کرده است.'
            ),
        )

        # =================================================
        # پاسخ
        # =================================================

        return Response(
            {
                'success': True,
                'message':
                    'پیام با موفقیت ارسال شد.',
                'message_id': message.id,
            },
            status=status.HTTP_201_CREATED,
        )


# =========================================================
# بستن تیکت توسط ساکن
# =========================================================

class UserSupportTicketCloseView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(self, request, ticket_id):
        ticket = get_user_ticket(
            request.user,
            ticket_id,
        )

        if ticket.is_closed:
            return Response(
                {
                    'success': True,
                    'message':
                        'تیکت قبلاً بسته شده است.',
                }
            )

        ticket.is_closed = True
        ticket.is_waiting = False

        ticket.save(
            update_fields=[
                'is_closed',
                'is_waiting',
                'updated_at',
            ]
        )

        return Response({
            'success': True,
            'message':
                'تیکت با موفقیت بسته شد.',
        })


# =========================================================
# علامت‌گذاری پیام‌های مدیر به عنوان خوانده‌شده
# =========================================================

class UserSupportTicketReadView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def post(self, request, ticket_id):
        ticket = get_user_ticket(
            request.user,
            ticket_id,
        )

        count = ticket.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).update(
            is_read=True
        )

        Notification.objects.filter(
            user=request.user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True
        )

        return Response({
            'success': True,
            'marked_count': count,
        })


class UserSupportUnreadCountView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        count = Notification.objects.filter(
            user=request.user,
            ticket__isnull=False,
            is_read=False,
        ).count()

        return Response({
            'success': True,
            'unread_count': count,
        })


# ============================================================
# MANAGER TICKET
# ============================================================

class ManagerSupportTicketListView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):

        # -------------------------------------------------
        # بررسی مدیر ساختمان
        # -------------------------------------------------

        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز است.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # مجتمع مدیر
        # -------------------------------------------------

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع فعال برای مدیر پیدا نشد.',
                'tickets': [],
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # کاربران مالک واحدهای فعال
        # -------------------------------------------------

        owner_user_ids = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        # -------------------------------------------------
        # کاربران مستاجر فعال
        # -------------------------------------------------

        renter_user_ids = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        # -------------------------------------------------
        # تمام کاربران مجاز مجتمع
        # -------------------------------------------------

        resident_user_ids = set(
            owner_user_ids
        ) | set(
            renter_user_ids
        )

        # -------------------------------------------------
        # تیکت‌های این مجتمع
        # -------------------------------------------------

        tickets = (
            SupportUser.objects
            .filter(
                user_id__in=resident_user_ids,
                is_sent=True,
            )
            .select_related('user')
            .prefetch_related(
                'messages__sender',
                'messages__attachments',
            )
            .order_by('-updated_at')
        )

        serializer = SupportTicketListSerializer(
            tickets,
            many=True,
            context={
                'request': request,
            }
        )

        return Response({
            'success': True,
            'count': tickets.count(),
            'tickets': serializer.data,
        })


class ManagerSupportTicketDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):

        # -------------------------------------------------
        # بررسی مدیر
        # -------------------------------------------------

        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز است.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # مجتمع مدیر
        # -------------------------------------------------

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع فعال برای مدیر پیدا نشد.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # پیدا کردن مالکین فعال
        # -------------------------------------------------

        owner_user_ids = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        # -------------------------------------------------
        # پیدا کردن مستاجرین فعال
        # -------------------------------------------------

        renter_user_ids = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        resident_user_ids = set(
            owner_user_ids
        ) | set(
            renter_user_ids
        )

        # -------------------------------------------------
        # تیکت
        # -------------------------------------------------

        ticket = (
            SupportUser.objects
            .filter(
                id=ticket_id,
                user_id__in=resident_user_ids,
                is_sent=True,
            )
            .select_related('user')
            .prefetch_related(
                'messages__sender',
                'messages__attachments',
                'files',
            )
            .first()
        )

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # -------------------------------------------------
        # پیام‌های ساکن خوانده‌شده شوند
        # -------------------------------------------------

        ticket.messages.filter(
            is_read=False
        ).exclude(
            sender=request.user
        ).update(
            is_read=True
        )

        # -------------------------------------------------
        # Notificationهای این تیکت برای مدیر خوانده شود
        # -------------------------------------------------

        Notification.objects.filter(
            user=request.user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True
        )

        # -------------------------------------------------
        # پاسخ
        # -------------------------------------------------

        serializer = SupportTicketDetailSerializer(
            ticket,
            context={
                'request': request,
            }
        )

        return Response({
            'success': True,
            'ticket': serializer.data,
        })


class ManagerSupportTicketMessageView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, ticket_id):

        # -------------------------------------------------
        # بررسی مدیر
        # -------------------------------------------------

        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز است.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # مجتمع مدیر
        # -------------------------------------------------

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع فعال برای مدیر پیدا نشد.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # کاربران مجاز مجتمع
        # -------------------------------------------------

        owner_user_ids = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        renter_user_ids = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        resident_user_ids = set(
            owner_user_ids
        ) | set(
            renter_user_ids
        )

        # -------------------------------------------------
        # تیکت
        # -------------------------------------------------

        ticket = (
            SupportUser.objects
            .filter(
                id=ticket_id,
                user_id__in=resident_user_ids,
                is_sent=True,
            )
            .select_related('user')
            .first()
        )

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # -------------------------------------------------
        # تیکت بسته شده؟
        # -------------------------------------------------

        if ticket.is_closed:
            return Response({
                'success': False,
                'message': 'این تیکت بسته شده است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # متن پاسخ
        # -------------------------------------------------

        message = request.data.get('message')

        # -------------------------------------------------
        # فایل‌ها
        # -------------------------------------------------

        uploaded_files = request.FILES.getlist('files')

        # -------------------------------------------------
        # حداقل متن یا فایل باید وجود داشته باشد
        # -------------------------------------------------

        if (
                not message
                or not str(message).strip()
        ) and not uploaded_files:
            return Response({
                'success': False,
                'message': 'متن پاسخ یا فایل پیوست الزامی است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # ایجاد پیام
        # -------------------------------------------------

        support_message = SupportMessage.objects.create(
            support_user=ticket,
            sender=request.user,
            message=message or '',
            is_read=False,
        )

        # -------------------------------------------------
        # ذخیره فایل‌ها
        # -------------------------------------------------

        created_files = []

        for uploaded_file in uploaded_files:

            # فقط تصویر چون SupportFile از ImageField استفاده می‌کند
            content_type = getattr(
                uploaded_file,
                'content_type',
                ''
            )

            if not content_type.startswith('image/'):
                transaction.set_rollback(True)

                return Response({
                    'success': False,
                    'message': (
                        'فقط فایل‌های تصویری قابل ارسال هستند.'
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            support_file = SupportFile.objects.create(
                support_user=ticket,
                file=uploaded_file,
            )

            support_message.attachments.add(
                support_file
            )

            created_files.append(
                support_file.id
            )

        # -------------------------------------------------
        # وضعیت تیکت
        #
        # بعد از پاسخ مدیر:
        # تیکت منتظر پاسخ ساکن است.
        # -------------------------------------------------

        ticket.is_answer = True
        ticket.is_waiting = False
        ticket.is_read = True

        ticket.save(
            update_fields=[
                'is_answer',
                'is_waiting',
                'is_read',
                'updated_at',
            ]
        )

        # -------------------------------------------------
        # Notification برای ساکن
        # -------------------------------------------------

        Notification.objects.create(
            user=ticket.user,
            ticket=ticket,
            title='پاسخ جدید به تیکت',
            message=(
                f'مدیر ساختمان به تیکت شماره '
                f'{ticket.ticket_no} پاسخ داده است.'
            ),
            link=f'/support/tickets/{ticket.id}/',
            is_read=False,
        )

        # -------------------------------------------------
        # پاسخ
        # -------------------------------------------------

        return Response({
            'success': True,
            'message': 'پاسخ با موفقیت ارسال شد.',
            'message_id': support_message.id,
            'file_ids': created_files,
        }, status=status.HTTP_201_CREATED)


class ManagerSupportTicketWaitingView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):

        # -------------------------------------------------
        # بررسی مدیر
        # -------------------------------------------------

        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز است.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # مجتمع مدیر
        # -------------------------------------------------

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع فعال برای مدیر پیدا نشد.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # کاربران مجاز مجتمع
        # -------------------------------------------------

        owner_user_ids = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        renter_user_ids = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        resident_user_ids = set(
            owner_user_ids
        ) | set(
            renter_user_ids
        )

        # -------------------------------------------------
        # تیکت
        # -------------------------------------------------

        ticket = SupportUser.objects.filter(
            id=ticket_id,
            user_id__in=resident_user_ids,
            is_sent=True,
        ).first()

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # -------------------------------------------------
        # تیکت بسته شده؟
        # -------------------------------------------------

        if ticket.is_closed:
            return Response({
                'success': False,
                'message': 'این تیکت بسته شده است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # در حال بررسی
        # -------------------------------------------------

        ticket.is_waiting = True
        ticket.is_answer = False

        ticket.save(
            update_fields=[
                'is_waiting',
                'is_answer',
                'updated_at',
            ]
        )

        # -------------------------------------------------
        # اطلاع به ساکن
        # -------------------------------------------------

        Notification.objects.create(
            user=ticket.user,
            ticket=ticket,
            title='تیکت در حال بررسی است',
            message=(
                f'تیکت شماره {ticket.ticket_no} '
                f'توسط مدیر ساختمان در حال بررسی است.'
            ),
            link=f'/support/tickets/{ticket.id}/',
            is_read=False,
        )

        return Response({
            'success': True,
            'message': 'تیکت در حال بررسی قرار گرفت.',
        })


class ManagerSupportTicketCloseView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, ticket_id):

        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز است.',
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return Response({
                'success': False,
                'message': 'مجتمع فعال برای مدیر پیدا نشد.',
            }, status=status.HTTP_400_BAD_REQUEST)

        owner_user_ids = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        renter_user_ids = Renter.objects.filter(
            unit__myhouse=house,
            unit__is_active=True,
            renter_is_active=True,
        ).values_list(
            'user_id',
            flat=True
        )

        resident_user_ids = set(
            owner_user_ids
        ) | set(
            renter_user_ids
        )

        ticket = SupportUser.objects.filter(
            id=ticket_id,
            user_id__in=resident_user_ids,
            is_sent=True,
        ).first()

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        if ticket.is_closed:
            return Response({
                'success': False,
                'message': 'این تیکت قبلاً بسته شده است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        ticket.is_closed = True
        ticket.is_waiting = False

        ticket.save(
            update_fields=[
                'is_closed',
                'is_waiting',
                'updated_at',
            ]
        )

        # اطلاع به ساکن
        Notification.objects.create(
            user=ticket.user,
            ticket=ticket,
            title='تیکت بسته شد',
            message=(
                f'تیکت شماره {ticket.ticket_no} '
                f'توسط مدیر ساختمان بسته شد.'
            ),
            link=f'/support/tickets/{ticket.id}/',
            is_read=False,
        )

        return Response({
            'success': True,
            'message': 'تیکت با موفقیت بسته شد.',
        })


class ManagerSupportUnreadCountView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        if not request.user.is_middle_admin:
            return Response(
                {
                    'success': False,
                    'message': 'شما اجازه دسترسی ندارید.',
                },
                status=403,
            )

        count = Notification.objects.filter(
            user=request.user,
            ticket__isnull=False,
            is_read=False,
        ).count()

        return Response({
            'success': True,
            'unread_count': count,
        })


# ============================================================
# Admin TICKET
# ============================================================

def get_manager_admin_ticket(user, ticket_id):
    if not getattr(user, 'is_middle_admin', False):
        return None

    try:
        return (
            AdminTicket.objects
            .select_related(
                'user',
                'house',
                'middle_admin',
            )
            .prefetch_related(
                'files_ticket',
                'messages__sender',
                'messages__attachments',
            )
            .get(
                id=ticket_id,
                user=user,
            )
        )

    except AdminTicket.DoesNotExist:
        return None


def create_middle_admin_notification(
        user,
        ticket,
        title,
        message,
):
    if not user:
        return None

    return MiddleAdminNotification.objects.create(
        user=user,
        ticket=ticket,
        title=title,
        message=message or '',
        link=str(ticket.id),
        is_read=False,
    )


class ManagerAdminSupportTicketListView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    def get(self, request):
        if not getattr(
                request.user,
                'is_middle_admin',
                False,
        ):
            return Response(
                {
                    'message':
                        'دسترسی به پشتیبانی سامانه ندارید.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        tickets = (
            AdminTicket.objects
            .filter(
                user=request.user,
                is_sent=True,
            )
            .select_related(
                'user',
                'house',
                'middle_admin',
            )
            .prefetch_related(
                'messages__sender',
            )
            .order_by(
                '-updated_at',
                '-created_at',
            )
        )

        serializer = AdminTicketListSerializer(
            tickets,
            many=True,
            context={
                'request': request,
            },
        )

        return Response(
            {
                'tickets': serializer.data,
            }
        )


class ManagerAdminSupportTicketCreateView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    parser_classes = [
        MultiPartParser,
        FormParser,
        JSONParser,
    ]

    @transaction.atomic
    def post(self, request):

        if not getattr(
                request.user,
                'is_middle_admin',
                False,
        ):
            return Response(
                {
                    'message':
                        'فقط مدیر ساختمان می‌تواند تیکت ایجاد کند.'
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # -------------------------------------------------
        # ساختمان مدیر
        # -------------------------------------------------

        house = (
            MyHouse.objects
            .filter(
                user=request.user,
                is_active=True,
            )
            .order_by('-created_at')
            .first()
        )

        if not house:
            return Response(
                {
                    'message':
                        'ساختمان فعالی برای مدیر پیدا نشد.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = AdminTicketCreateSerializer(
            data=request.data,
            context={
                'request': request,
            },
        )

        serializer.is_valid(
            raise_exception=True,
        )

        subject = (
                serializer.validated_data.get(
                    'subject'
                )
                or ''
        ).strip()

        message = (
                serializer.validated_data.get(
                    'message'
                )
                or ''
        ).strip()

        # -------------------------------------------------
        # ادمین سامانه
        # -------------------------------------------------

        admin_user = (
            User.objects
            .filter(
                is_superuser=True,
                is_active=True,
            )
            .order_by('id')
            .first()
        )

        if not admin_user:
            return Response(
                {
                    'message':
                        'ادمین سامانه برای دریافت تیکت پیدا نشد.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -------------------------------------------------
        # ایجاد تیکت
        # -------------------------------------------------

        ticket = AdminTicket.objects.create(
            user=request.user,
            middle_admin=admin_user,
            house=house,
            subject=subject,
            message=message,

            is_sent=True,
            is_read=True,
            is_call=False,
            is_closed=False,
            is_answer=False,
            is_waiting=False,
        )

        # -------------------------------------------------
        # پیام اولیه
        # -------------------------------------------------

        ticket_message = AdminTicketMessage.objects.create(
            ticket=ticket,
            sender=request.user,
            message=message,
            is_read=True,
        )

        # -------------------------------------------------
        # فایل‌های اولیه
        # -------------------------------------------------

        files = request.FILES.getlist('files')

        for uploaded_file in files:
            AdminTicketFile.objects.create(
                ticket=ticket,
                file=uploaded_file,
            )

        # -------------------------------------------------
        # اعلان برای ادمین
        # -------------------------------------------------

        create_middle_admin_notification(
            user=admin_user,
            ticket=ticket,
            title='تیکت جدید مدیر ساختمان',
            message=message,
        )

        return Response(
            {
                'message':
                    'تیکت با موفقیت ثبت شد.',

                'ticket_id':
                    ticket.id,

                'ticket_no':
                    ticket.ticket_no,

                'message_id':
                    ticket_message.id,
            },
            status=status.HTTP_201_CREATED,
        )


class ManagerAdminSupportTicketDetailView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, ticket_id):

        user = request.user

        # -------------------------------------------------
        # فقط مدیر ساختمان
        # -------------------------------------------------

        if not user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'شما دسترسی مشاهده این تیکت را ندارید.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # تیکت فقط متعلق به همین مدیر باشد
        # -------------------------------------------------

        ticket = (
            AdminTicket.objects
            .select_related(
                'user',
                'house',
                'middle_admin',
            )
            .filter(
                id=ticket_id,
                user=user,
                is_sent=True,
            )
            .prefetch_related(
                'files_ticket',
                'messages__sender',
                'messages__attachments',
            )
            .first()
        )

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # =================================================
        # پیام‌های ادمین خوانده شوند
        # =================================================

        ticket.messages.filter(
            is_read=False
        ).exclude(
            sender=user
        ).update(
            is_read=True
        )

        # =================================================
        # Notificationهای این تیکت برای مدیر
        # خوانده‌شده شوند
        # =================================================

        MiddleAdminNotification.objects.filter(
            user=user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True
        )

        # =================================================
        # Serializer
        # =================================================

        serializer = AdminTicketDetailSerializer(
            ticket,
            context={
                'request': request,
            }
        )

        return Response({
            'success': True,
            'ticket': serializer.data,
        }, status=status.HTTP_200_OK)


class ManagerAdminSupportTicketMessageView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def post(self, request, ticket_id):

        user = request.user

        # -------------------------------------------------
        # فقط مدیر ساختمان
        # -------------------------------------------------

        if not user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'شما دسترسی ارسال پیام ندارید.',
            }, status=status.HTTP_403_FORBIDDEN)

        # -------------------------------------------------
        # پیدا کردن تیکت
        # -------------------------------------------------

        ticket = (
            AdminTicket.objects
            .select_related(
                'user',
                'house',
            )
            .filter(
                id=ticket_id,
                user=user,
                is_sent=True,
            )
            .first()
        )

        if not ticket:
            return Response({
                'success': False,
                'message': 'تیکت مورد نظر پیدا نشد.',
            }, status=status.HTTP_404_NOT_FOUND)

        # -------------------------------------------------
        # دریافت پیام
        # -------------------------------------------------

        message = request.data.get('message', '')

        if message is None:
            message = ''

        message = str(message).strip()

        # -------------------------------------------------
        # فایل‌ها
        # -------------------------------------------------

        uploaded_files = request.FILES.getlist('files')

        if not message and not uploaded_files:
            return Response({
                'success': False,
                'message': 'متن پیام یا فایل الزامی است.',
            }, status=status.HTTP_400_BAD_REQUEST)

        # -------------------------------------------------
        # ایجاد پیام
        # -------------------------------------------------

        ticket_message = AdminTicketMessage.objects.create(
            ticket=ticket,
            sender=user,
            message=message,
            is_read=False,
        )

        # -------------------------------------------------
        # ذخیره فایل‌ها
        # -------------------------------------------------

        created_files = []

        for uploaded_file in uploaded_files:
            ticket_file = AdminTicketFile.objects.create(
                ticket=ticket,
                file=uploaded_file,
            )

            ticket_message.attachments.add(
                ticket_file
            )

            created_files.append(ticket_file)

        # -------------------------------------------------
        # وضعیت تیکت
        #
        # وقتی مدیر پیام می‌فرستد:
        # منتظر پاسخ ادمین
        # -------------------------------------------------

        ticket.is_closed = False
        ticket.is_waiting = False
        ticket.is_answer = False

        ticket.save(
            update_fields=[
                'is_closed',
                'is_waiting',
                'is_answer',
                'updated_at',
            ]
        )

        # =================================================
        # پیدا کردن ادمین سامانه
        # =================================================

        admins = User.objects.filter(
            is_superuser=True,
            is_active=True,
        )

        # =================================================
        # ایجاد Notification برای ادمین
        # =================================================

        notifications = []

        for admin in admins:
            notifications.append(
                MiddleAdminNotification(
                    user=admin,
                    ticket=ticket,
                    title='پیام جدید مدیر ساختمان',
                    message=(
                        f'مدیر ساختمان برای تیکت '
                        f'{ticket.ticket_no} پیام جدید ارسال کرده است.'
                    ),
                    link=str(ticket.id),
                    is_read=False,
                )
            )

        if notifications:
            MiddleAdminNotification.objects.bulk_create(
                notifications
            )

        # -------------------------------------------------
        # پاسخ
        # -------------------------------------------------

        return Response({
            'success': True,
            'message': 'پیام با موفقیت ارسال شد.',
            'ticket_id': ticket.id,
            'message_id': ticket_message.id,
            'notification_count': len(notifications),
        }, status=status.HTTP_201_CREATED)


class ManagerAdminSupportTicketCloseView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(self, request, ticket_id):

        ticket = get_manager_admin_ticket(
            request.user,
            ticket_id,
        )

        if not ticket:
            return Response(
                {
                    'message':
                        'تیکت مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if ticket.is_closed:
            return Response(
                {
                    'message':
                        'تیکت قبلاً بسته شده است.'
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        ticket.is_closed = True
        ticket.is_waiting = False

        ticket.save(
            update_fields=[
                'is_closed',
                'is_waiting',
                'updated_at',
            ]
        )

        # -------------------------------------------------
        # اطلاع به ادمین
        # -------------------------------------------------

        if ticket.middle_admin:
            create_middle_admin_notification(
                user=ticket.middle_admin,
                ticket=ticket,
                title='تیکت بسته شد',
                message='مدیر ساختمان تیکت را بسته است.',
            )

        return Response(
            {
                'message':
                    'تیکت با موفقیت بسته شد.'
            }
        )


class ManagerAdminSupportTicketReadView(APIView):
    permission_classes = [
        IsAuthenticated,
    ]

    @transaction.atomic
    def post(self, request, ticket_id):
        ticket = get_manager_admin_ticket(
            request.user,
            ticket_id,
        )

        if not ticket:
            return Response(
                {
                    'message':
                        'تیکت مورد نظر پیدا نشد.'
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        AdminTicketMessage.objects.filter(
            ticket=ticket,
            sender__is_superuser=True,
            is_read=False,
        ).update(
            is_read=True,
        )

        MiddleAdminNotification.objects.filter(
            user=request.user,
            ticket=ticket,
            is_read=False,
        ).update(
            is_read=True,
        )

        return Response(
            {
                'message':
                    'پیام‌ها به عنوان خوانده شده ثبت شدند.'
            }
        )


# =========================================================
# تعداد پیام‌های جدید مدیر
# =========================================================

class ManagerAdminSupportUnreadCountView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        if not request.user.is_middle_admin:
            return Response({
                'success': False,
                'message': 'دسترسی غیرمجاز.',
            }, status=status.HTTP_403_FORBIDDEN)

        unread_count = MiddleAdminNotification.objects.filter(
            user=request.user,
            ticket__isnull=False,
            is_read=False,
        ).count()

        return Response({
            'success': True,
            'unread_count': unread_count,
        })


# ================== Unit Views ========================

logger = logging.getLogger(__name__)


class ManagerUnitBaseView(APIView):
    permission_classes = [IsAuthenticated]

    def error(self, message, status_code=status.HTTP_400_BAD_REQUEST):
        return Response(
            {
                'success': False,
                'message': message,
                'data': None,
            },
            status=status_code,
        )

    def success(
            self,
            message,
            data=None,
            status_code=status.HTTP_200_OK,
    ):
        return Response(
            {
                'success': True,
                'message': message,
                'data': data,
            },
            status=status_code,
        )

    def get_house(self, request):
        if not request.user.is_middle_admin:
            return None

        return MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

    def get_unit(self, request, unit_id):
        house = self.get_house(request)

        if house is None:
            return None, None

        unit = Unit.objects.filter(
            pk=unit_id,
            myhouse=house,
        ).select_related(
            'user',
            'myhouse',
        ).first()

        return house, unit

    def get_manager_owner_user(
            self,
            request,
            mobile,
            full_name,
            house,
            current_owner=None,
    ):
        """
        پیدا کردن حساب مالک یا ایجاد حساب جدید.
        حساب شخص دیگری نباید بازنویسی شود.
        """

        owner_user = User.objects.filter(
            mobile=mobile,
        ).first()

        if owner_user:
            is_current_owner = (
                    current_owner is not None
                    and owner_user.pk == current_owner.pk
            )

            is_manager_resident = (
                    owner_user.pk == request.user.pk
                    and owner_user.is_resident
            )

            if not is_current_owner and not is_manager_resident:
                raise ValueError(
                    'این شماره موبایل قبلاً به کاربر دیگری تعلق دارد.'
                )

            owner_user.full_name = full_name
            owner_user.is_active = True
            owner_user.is_unit = True
            owner_user.house = house

            if owner_user.pk != request.user.pk:
                owner_user.manager = request.user

            owner_user.save(
                update_fields=[
                    'full_name',
                    'is_active',
                    'is_unit',
                    'house',
                    'manager',
                ]
            )

            return owner_user

        return User.objects.create(
            mobile=mobile,
            username=mobile,
            full_name=full_name,
            house=house,
            manager=request.user,
            is_active=True,
            is_unit=True,
        )

    @staticmethod
    def set_password_if_provided(user, password):
        if password:
            user.set_password(password)
            user.save(update_fields=['password'])

    @staticmethod
    def unit_data(unit):
        # دریافت مستأجر فعال این واحد
        active_renter = unit.renters.filter(
            renter_is_active=True
        ).order_by('-id').first()

        # دریافت سوابق مستأجران
        renters = unit.renters.all().order_by('-id')

        return {
            'id': unit.pk,
            'unit': unit.unit,
            'is_active': unit.is_active,
            'floor_number': unit.floor_number,
            'area': str(unit.area or 0),
            'bedrooms_count': unit.bedrooms_count,
            'unit_phone': unit.unit_phone,
            'parking_number': unit.parking_number,
            'parking_place': unit.parking_place,
            'extra_parking_first': unit.extra_parking_first,
            'extra_parking_second': unit.extra_parking_second,

            # اطلاعات مالک
            'owner_name': unit.owner_name,
            'owner_mobile': unit.owner_mobile,
            'owner_national_code': unit.owner_national_code,
            'owner_people_count': unit.owner_people_count,

            # وضعیت واحد
            'people_count': unit.people_count,
            'is_renter': bool(active_renter),
            'myhouse_id': unit.myhouse_id,

            # مستأجر فعال
            'active_renter': (
                ManagerUnitBaseView.renter_data(active_renter)
                if active_renter else None
            ),
            'purchase_date': (
                unit.purchase_date.isoformat()
                if unit.purchase_date else None
            ),
            'owner_details': unit.owner_details,

            # سوابق مستأجران
            'renters': [
                ManagerUnitBaseView.renter_data(renter)
                for renter in renters
            ],
        }

    @staticmethod
    def renter_data(renter):
        return {
            'id': renter.pk,
            'unit_id': renter.unit_id,
            'renter_name': renter.renter_name,
            'renter_mobile': renter.renter_mobile,
            'renter_national_code': renter.renter_national_code,
            'renter_people_count': renter.renter_people_count,
            'start_date': (
                renter.start_date.isoformat()
                if renter.start_date else None
            ),
            'end_date': (
                renter.end_date.isoformat()
                if renter.end_date else None
            ),
            'contract_number': renter.contract_number,
            'estate_name': renter.estate_name,
            'renter_details': renter.renter_details,
            'renter_is_active': renter.renter_is_active,
        }

    @staticmethod
    def sync_owner_history(unit, changed_by):
        from datetime import date
        from django.utils import timezone

        # دریافت تاریخ امروز بدون وابستگی به localtime
        today = date.today()

        histories = UnitResidenceHistory.objects.filter(
            unit=unit,
            resident_type='owner',
            to_date__isnull=True,
        ).order_by('-id')

        current = histories.first()

        if (
                current
                and current.name == (unit.owner_name or '')
                and current.mobile == (unit.owner_mobile or '')
        ):
            current.people_count = int(unit.owner_people_count or 0)
            current.save(update_fields=['people_count'])
            return

        histories.update(to_date=today)

        UnitResidenceHistory.objects.create(
            unit=unit,
            resident_type='owner',
            name=unit.owner_name or '',
            mobile=unit.owner_mobile or '',
            people_count=int(unit.owner_people_count or 0),
            from_date=today,
            changed_by=changed_by,
        )


class ManagerUnitListAPIView(ManagerUnitBaseView):
    """
    فهرست واحدهای ساختمان مدیر
    GET /api/manager/units/

    Query params:
        search: جست‌وجو
        resident_type: all / owner / renter
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        # -----------------------------------------
        # بررسی مدیر و ساختمان فعال
        # -----------------------------------------
        if not getattr(request.user, 'is_middle_admin', False):
            return self.error(
                'شما اجازه دسترسی به این بخش را ندارید.',
                status.HTTP_403_FORBIDDEN,
            )

        house = self.get_house(request)

        if not house:
            return self.error(
                'ساختمان فعال برای مدیر پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        # -----------------------------------------
        # دریافت واحدهای فعال ساختمان
        # -----------------------------------------
        active_renters = (
            Renter.objects
            .filter(renter_is_active=True)
            .order_by('-id')
        )

        units = (
            Unit.objects
            .filter(
                myhouse=house,
            )
            .select_related('user', 'myhouse')
            .prefetch_related(
                Prefetch(
                    'renters',
                    queryset=active_renters,
                    to_attr='active_renters_list',
                )
            )
            .order_by('floor_number', 'unit')
        )

        # -----------------------------------------
        # جست‌وجو
        # -----------------------------------------
        search = request.query_params.get(
            'search', ''
        ).strip()

        if search:
            search_query = Q(owner_name__icontains=search)

            search_query |= Q(owner_mobile__icontains=search)

            search_query |= Q(unit_phone__icontains=search)

            # جست‌وجو بر اساس شماره واحد
            if search.isdigit():
                search_query |= Q(unit=int(search))

            # جست‌وجو در نام و موبایل مستأجر
            search_query |= Q(
                renters__renter_is_active=True
            ) & (
                                    Q(renters__renter_name__icontains=search)
                                    | Q(renters__renter_mobile__icontains=search)
                            )

            units = units.filter(
                search_query
            ).distinct()

        # -----------------------------------------
        # فیلتر نوع سکونت
        # -----------------------------------------
        resident_type = request.query_params.get(
            'resident_type', 'all'
        ).strip().lower()

        if resident_type == 'owner':
            # واحدهایی که مستأجر فعال ندارند
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == 'renter':
            # واحدهایی که مستأجر فعال دارند
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type != 'all':
            return self.error(
                'نوع فیلتر سکونت معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        # -----------------------------------------
        # ساخت پاسخ
        # -----------------------------------------
        results = []

        for unit in units:
            active_renters_for_unit = getattr(
                unit,
                'active_renters_list',
                [],
            )

            renter = (
                active_renters_for_unit[0]
                if active_renters_for_unit
                else None
            )

            # اطلاعات مالک
            owner_data = {
                'name': unit.owner_name or '',
                'mobile': unit.owner_mobile or '',
                'national_code': (
                        unit.owner_national_code or ''
                ),
                'people_count': (
                        unit.owner_people_count or 0
                ),
            }

            # اطلاعات مستأجر فعال
            active_renter_data = (
                self.renter_data(renter)
                if renter
                else None
            )

            if active_renter_data:
                # برای هماهنگی با Flutter
                active_renter_data['name'] = (
                        renter.renter_name or ''
                )
                active_renter_data['mobile'] = (
                        renter.renter_mobile or ''
                )

            # اطلاعات اصلی واحد
            item = self.unit_data(unit)

            # ساختار سازگار با صفحه Flutter
            # ساختار سازگار با صفحه Flutter
            item.update({
                'owner': owner_data,
                'active_renter': active_renter_data,
                'has_active_renter': renter is not None,
                'is_renter': renter is not None,

            })

            results.append(item)

        return self.success(
            'فهرست واحدها با موفقیت دریافت شد.',
            {
                'count': len(results),
                'results': results,
            },
        )


class ManagerUnitCreateAPIView(ManagerUnitBaseView):

    def post(self, request):
        house = self.get_house(request)

        if house is None:
            return self.error(
                'ساختمان فعال یا دسترسی مدیر پیدا نشد.',
                status.HTTP_403_FORBIDDEN,
            )

        serializer = ManagerUnitSerializer(data=request.data)

        if not serializer.is_valid():
            return self.error(
                'اطلاعات فرم معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        required_fields = [
            'unit',
            'floor_number',
            'area',
            'bedrooms_count',
            'owner_name',
            'owner_mobile',
        ]

        missing = [
            field for field in required_fields
            if field not in data
        ]

        if missing:
            return self.error(
                'اطلاعات ضروری وارد نشده است.',
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():

                subscription = Subscription.objects.filter(
                    user=request.user,
                ).order_by('-created_at').first()

                if subscription is None:
                    return self.error(
                        'اشتراکی برای مدیر پیدا نشد.',
                        status.HTTP_400_BAD_REQUEST,
                    )

                # برای حفظ رفتار ویوی فعلی:
                # آخرین اشتراک مدیر بررسی می‌شود.
                current_count = Unit.objects.filter(
                    myhouse=house,
                ).count()

                if current_count >= subscription.units_count:
                    return self.error(
                        f'ظرفیت اشتراک شما '
                        f'{subscription.units_count} واحد است.',
                        status.HTTP_400_BAD_REQUEST,
                    )

                owner_name = data['owner_name']
                owner_mobile = data['owner_mobile']

                owner_user = self.get_manager_owner_user(
                    request=request,
                    mobile=owner_mobile,
                    full_name=owner_name,
                    house=house,
                )

                self.set_password_if_provided(
                    owner_user,
                    data.get('owner_password'),
                )

                unit_fields = [
                    'unit',
                    'floor_number',
                    'area',
                    'bedrooms_count',
                    'unit_phone',
                    'parking_number',
                    'parking_place',
                    'extra_parking_first',
                    'extra_parking_second',
                    'unit_details',
                    'owner_name',
                    'owner_mobile',
                    'owner_national_code',
                    'purchase_date',
                    'owner_people_count',
                    'owner_details',
                    'status_residence',
                ]

                unit_values = {
                    field: data[field]
                    for field in unit_fields
                    if field in data
                }

                unit = Unit(
                    **unit_values,
                    user=owner_user,
                    myhouse=house,
                    is_renter=False,
                    people_count=int(
                        data.get('owner_people_count') or 0
                    ),
                )

                unit.save()

                # Unit.save() در زمان ایجاد، سابقه مالک را می‌سازد.
                return self.success(
                    'واحد و مالک با موفقیت ثبت شدند.',
                    self.unit_data(unit),
                    status.HTTP_201_CREATED,
                )

        except ValueError as exc:
            return self.error(str(exc))

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Manager unit create failed'
            )
            return self.error(
                'خطا در ثبت واحد و مالک.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerUnitDetailAPIView(ManagerUnitBaseView):

    def get(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'ساختمان برای مدیر پیدا نشد یا دسترسی مجاز نیست.',
                status_code=status.HTTP_403_FORBIDDEN
            )

        if unit is None:
            return self.error(
                'واحد موردنظر پیدا نشد.',
                status_code=status.HTTP_404_NOT_FOUND
            )

        return self.success(
            'اطلاعات واحد با موفقیت دریافت شد.',
            self.unit_data(unit)
        )


class ManagerUnitUpdateAPIView(ManagerUnitBaseView):
    # فقط مشخصات خود واحد؛ بدون اطلاعات مالک و مستأجر
    EDITABLE_FIELDS = (
        'unit',
        'floor_number',
        'area',
        'bedrooms_count',
        'unit_phone',
        'parking_number',
        'parking_place',
        'extra_parking_first',
        'extra_parking_second',
        'unit_details',
    )

    def patch(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        # فقط فیلدهای مجاز از درخواست دریافت می‌شوند.
        # فیلدهای مالک، مستأجر، تاریخ خرید و رمز نادیده گرفته می‌شوند.
        submitted_data = {
            field: request.data[field]
            for field in self.EDITABLE_FIELDS
            if field in request.data
        }

        if not submitted_data:
            return self.error(
                'هیچ فیلد مجازی برای ویرایش ارسال نشده است.',
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = ManagerUnitSerializer(
            instance=unit,
            data=submitted_data,
            partial=True,
        )

        if not serializer.is_valid():
            return self.error(
                'اطلاعات فرم معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        # کنترل نهایی فیلدها؛ فقط همین ستون‌ها مجازند.
        data = {
            field: value
            for field, value in data.items()
            if field in self.EDITABLE_FIELDS
        }

        if not data:
            return self.error(
                'اطلاعات قابل ویرایشی دریافت نشد.',
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():

                # قفل رکورد برای جلوگیری از تداخل ویرایش‌ها
                locked_unit = (
                    Unit.objects
                    .select_for_update()
                    .filter(
                        pk=unit.pk,
                        myhouse=house,
                    )
                    .first()
                )

                if locked_unit is None:
                    return self.error(
                        'واحد پیدا نشد یا دسترسی به آن وجود ندارد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                # فقط ستون‌های مشخصات واحد به‌روزرسانی می‌شوند.
                # عمداً Unit.save() و سیگنال‌های ذخیره اجرا نمی‌شوند.
                updated_count = (
                    Unit.objects
                    .filter(
                        pk=locked_unit.pk,
                        myhouse=house,
                    )
                    .update(**data)
                )

                if updated_count == 0:
                    return self.error(
                        'تغییری در اطلاعات واحد ذخیره نشد.',
                        status.HTTP_400_BAD_REQUEST,
                    )

                # دریافت اطلاعات تازه از دیتابیس
                locked_unit.refresh_from_db()

                # ساخت پاسخ نیز داخل try قرار دارد تا خطاهای
                # احتمالی unit_data در لاگ ثبت شوند.
                response_data = self.unit_data(locked_unit)

                return self.success(
                    'مشخصات واحد با موفقیت ویرایش شد.',
                    response_data,
                )

        except Exception:
            # traceback کامل در لاگ Django ثبت می‌شود.
            logger.exception(
                'خطا هنگام ویرایش مشخصات واحد؛ unit_id=%s',
                unit_id,
            )

            return Response(
                {
                    'success': False,
                    'message': (
                        'هنگام ذخیره مشخصات واحد خطایی رخ داد. '
                        'جزئیات خطا در لاگ سرور ثبت شده است.'
                    ),
                    'data': None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerUnitOwnerUpdateAPIView(ManagerUnitBaseView):
    """
    ویرایش اطلاعات مالک واحد.
    تغییر مشخصات مالک مستقل از تغییر شماره موبایل است.
    """

    OWNER_EDITABLE_FIELDS = (
        'owner_name',
        'owner_mobile',
        'owner_national_code',
        'owner_people_count',
        'owner_details',
        'purchase_date',
    )

    @staticmethod
    def _normalize_mobile(value):
        import re

        value = str(value or '').strip()

        translation = str.maketrans(
            '۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩',
            '01234567890123456789',
        )
        value = value.translate(translation)

        return re.sub(r'\D', '', value)

    def post(self, request, unit_id):
        """
        ثبت مالک جدید برای واحد، با امکان جایگزینی مالک قبلی.
        """

        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        submitted_data = {
            field: request.data[field]
            for field in self.OWNER_EDITABLE_FIELDS
            if field in request.data
        }

        owner_password = str(
            request.data.get('owner_password') or ''
        ).strip()

        owner_name = str(
            submitted_data.get('owner_name') or ''
        ).strip()

        owner_mobile = str(
            submitted_data.get('owner_mobile') or ''
        ).strip()

        if not owner_name or not self._normalize_mobile(owner_mobile):
            return self.error(
                'نام و شماره موبایل مالک الزامی است.',
                status.HTTP_400_BAD_REQUEST,
            )

        if not owner_password:
            return self.error(
                'رمز عبور مالک جدید را وارد کنید.',
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = ManagerUnitSerializer(
            instance=unit,
            data=submitted_data,
            partial=True,
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعات مالک معتبر نیست.',
                    'errors': serializer.errors,
                    'data': None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        owner_data = {
            field: value
            for field, value in serializer.validated_data.items()
            if field in self.OWNER_EDITABLE_FIELDS
        }

        owner_name = str(
            owner_data.get('owner_name', owner_name) or ''
        ).strip()

        owner_mobile = str(
            owner_data.get('owner_mobile', owner_mobile) or ''
        ).strip()

        try:
            with transaction.atomic():
                locked_unit = (
                    Unit.objects
                    .select_for_update()
                    .filter(
                        pk=unit.pk,
                        myhouse=house,
                    )
                    .first()
                )

                if locked_unit is None:
                    return self.error(
                        'واحد پیدا نشد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                old_owner_user = locked_unit.user

                # گرفتن یا ایجاد حساب کاربری مالک جدید.
                # شماره متعلق به حساب نامرتبط نباید تصاحب شود.
                owner_user = self.get_manager_owner_user(
                    request=request,
                    mobile=owner_mobile,
                    full_name=owner_name,
                    house=house,
                    current_owner=old_owner_user,
                )

                self.set_password_if_provided(
                    owner_user,
                    owner_password,
                )

                # بستن سابقه مالک قبلی پیش از تغییر اطلاعات واحد
                today = date.today()

                UnitResidenceHistory.objects.filter(
                    unit=locked_unit,
                    resident_type='owner',
                    to_date__isnull=True,
                ).update(to_date=today)

                # ذخیره اطلاعات مالک جدید
                db_updates = dict(owner_data)
                db_updates['user_id'] = owner_user.pk

                Unit.objects.filter(
                    pk=locked_unit.pk,
                    myhouse=house,
                ).update(**db_updates)

                locked_unit.refresh_from_db()

                # ثبت سابقه مالک جدید
                UnitResidenceHistory.objects.create(
                    unit=locked_unit,
                    resident_type='owner',
                    name=locked_unit.owner_name or '',
                    mobile=locked_unit.owner_mobile or '',
                    people_count=int(
                        locked_unit.owner_people_count or 0
                    ),
                    from_date=today,
                    changed_by=request.user,
                )

                return self.success(
                    'مالک جدید با موفقیت ثبت شد.',
                    self.unit_data(locked_unit),
                    status_code=status.HTTP_201_CREATED,
                )

        except ValueError as exc:
            logger.exception(
                'خطا هنگام افزودن مالک؛ unit_id=%s',
                unit_id,
            )

            return self.error(
                str(exc),
                status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                'خطا هنگام افزودن مالک؛ unit_id=%s',
                unit_id,
            )

            return Response(
                {
                    'success': False,
                    'message': 'هنگام افزودن مالک خطایی رخ داد.',
                    'data': None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        submitted_data = {
            field: request.data[field]
            for field in self.OWNER_EDITABLE_FIELDS
            if field in request.data
        }

        owner_password = str(
            request.data.get('owner_password') or ''
        ).strip()

        if not submitted_data and not owner_password:
            return self.error(
                'اطلاعاتی برای ویرایش مالک ارسال نشده است.',
                status.HTTP_400_BAD_REQUEST,
            )

        serializer = ManagerUnitSerializer(
            instance=unit,
            data=submitted_data,
            partial=True,
        )

        if not serializer.is_valid():
            return Response(
                {
                    'success': False,
                    'message': 'اطلاعات مالک معتبر نیست.',
                    'errors': serializer.errors,
                    'data': None,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        owner_data = {
            field: value
            for field, value in data.items()
            if field in self.OWNER_EDITABLE_FIELDS
        }

        try:
            with transaction.atomic():

                locked_unit = (
                    Unit.objects
                    .select_for_update()
                    .filter(
                        pk=unit.pk,
                        myhouse=house,
                    )
                    .first()
                )

                if locked_unit is None:
                    return self.error(
                        'واحد پیدا نشد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                old_owner_user = locked_unit.user

                old_owner_name = (
                        locked_unit.owner_name or ''
                ).strip()

                old_owner_mobile = self._normalize_mobile(
                    locked_unit.owner_mobile
                )

                owner_name = str(
                    owner_data.get(
                        'owner_name',
                        locked_unit.owner_name or '',
                    ) or ''
                ).strip()

                owner_mobile = str(
                    owner_data.get(
                        'owner_mobile',
                        locked_unit.owner_mobile or '',
                    ) or ''
                ).strip()

                normalized_new_mobile = self._normalize_mobile(
                    owner_mobile
                )

                name_changed = (
                        owner_name != old_owner_name
                )

                mobile_changed = (
                        normalized_new_mobile != old_owner_mobile
                )

                # فقط فیلدهای مجاز مالک ذخیره می‌شوند.
                update_fields = dict(owner_data)

                # بررسی حساب کاربری فقط هنگام تغییر شماره موبایل
                if mobile_changed:
                    if not owner_name or not normalized_new_mobile:
                        return self.error(
                            'نام و شماره موبایل مالک الزامی است.',
                            status.HTTP_400_BAD_REQUEST,
                        )

                    owner_user = self.get_manager_owner_user(
                        request=request,
                        mobile=owner_mobile,
                        full_name=owner_name,
                        house=house,
                        current_owner=old_owner_user,
                    )

                    update_fields['user'] = owner_user
                    locked_unit.user = owner_user

                elif name_changed and old_owner_user is not None:
                    # تغییر نام حساب مالک فعلی بدون تغییر موبایل
                    old_owner_user.full_name = owner_name
                    old_owner_user.save(
                        update_fields=['full_name']
                    )

                # تغییر رمز عبور فقط در صورت ارسال رمز جدید
                if owner_password:
                    password_user = (
                        locked_unit.user
                        if mobile_changed
                        else old_owner_user
                    )

                    if password_user is None:
                        return self.error(
                            'برای این واحد حساب کاربری مالک ثبت نشده است.',
                            status.HTTP_400_BAD_REQUEST,
                        )

                    self.set_password_if_provided(
                        password_user,
                        owner_password,
                    )

                # ذخیره تمام فیلدهای ارسالی، حتی اگر مقدارشان
                # با مقدار فعلی برابر باشد.
                if update_fields:
                    db_updates = {}

                    for field, value in update_fields.items():
                        if field == 'user':
                            db_updates['user_id'] = (
                                value.pk if value else None
                            )
                        else:
                            db_updates[field] = value

                    Unit.objects.filter(
                        pk=locked_unit.pk,
                        myhouse=house,
                    ).update(**db_updates)

                locked_unit.refresh_from_db()

                self.sync_owner_history(
                    locked_unit,
                    request.user,
                )

                return self.success(
                    'اطلاعات مالک با موفقیت ذخیره شد.',
                    self.unit_data(locked_unit),
                )

        except ValueError as exc:
            logger.exception(
                'خطای اعتبارسنجی هنگام ویرایش مالک؛ unit_id=%s',
                unit_id,
            )

            return self.error(
                str(exc),
                status.HTTP_400_BAD_REQUEST,
            )

        except Exception:
            logger.exception(
                'خطا هنگام ویرایش مالک؛ unit_id=%s',
                unit_id,
            )

            return Response(
                {
                    'success': False,
                    'message': (
                        'هنگام ویرایش مالک خطایی رخ داد. '
                        'جزئیات در لاگ Django ثبت شده است.'
                    ),
                    'data': None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerUnitStatusAPIView(ManagerUnitBaseView):

    def post(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        is_active = request.data.get('is_active')

        # فقط مقدار بولی واقعی پذیرفته شود.
        if not isinstance(is_active, bool):
            return self.error(
                'وضعیت فعال بودن واحد معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                locked_unit = (
                    Unit.objects
                    .select_for_update()
                    .filter(
                        pk=unit_id,
                        myhouse=house,
                    )
                    .first()
                )

                if locked_unit is None:
                    return self.error(
                        'واحد پیدا نشد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                # عمداً save مدل اجرا نمی‌شود تا منطق تاریخچه
                # مالک و مستأجر به اشتباه اجرا نشود.
                Unit.objects.filter(
                    pk=locked_unit.pk,
                    myhouse=house,
                ).update(is_active=is_active)

                return self.success(
                    (
                        'واحد با موفقیت فعال شد.'
                        if is_active
                        else 'واحد با موفقیت غیرفعال شد.'
                    ),
                    {
                        'unit_id': locked_unit.pk,
                        'unit': locked_unit.unit,
                        'is_active': is_active,
                    },
                )

        except Exception:
            logger.exception(
                'خطا در تغییر وضعیت واحد؛ unit_id=%s',
                unit_id,
            )

            return Response(
                {
                    'success': False,
                    'message': 'تغییر وضعیت واحد انجام نشد.',
                    'data': None,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerUnitRentersAPIView(ManagerUnitBaseView):

    def get(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        renters = unit.renters.select_related(
            'user',
        ).order_by(
            '-renter_is_active',
            '-start_date',
            '-created_at',
        )

        active_renter = renters.filter(
            renter_is_active=True,
        ).first()

        return self.success(
            'فهرست مستأجران دریافت شد.',
            {
                'unit': self.unit_data(unit),
                'active_renter': (
                    self.renter_data(active_renter)
                    if active_renter else None
                ),
                'renters': [
                    self.renter_data(renter)
                    for renter in renters
                ],
            },
        )

    def post(self, request, unit_id):
        house, unit = self.get_unit(request, unit_id)

        if house is None:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if unit is None:
            return self.error(
                'واحد پیدا نشد.',
                status.HTTP_404_NOT_FOUND,
            )

        serializer = ManagerRenterSerializer(
            data=request.data,
        )

        if not serializer.is_valid():
            return self.error(
                'اطلاعات مستأجر معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data

        required_fields = [
            'renter_name',
            'renter_mobile',
        ]

        if any(field not in data for field in required_fields):
            return self.error(
                'نام و شماره موبایل مستأجر الزامی است.',
            )

        start_date = data.get('start_date') or date.today()
        end_date = data.get('end_date')

        if end_date and end_date < start_date:
            return self.error(
                'تاریخ پایان اجاره نمی‌تواند قبل از تاریخ شروع باشد.',
            )

        try:
            with transaction.atomic():

                # قفل کردن واحد برای جلوگیری از ثبت هم‌زمان مستأجر
                unit = Unit.objects.select_for_update().get(
                    pk=unit.pk,
                    myhouse=house,
                )

                mobile = data['renter_mobile']

                # جلوگیری از ثبت یک شماره به‌عنوان مستأجر فعال
                # در واحد دیگر
                if Renter.objects.filter(
                        user__mobile=mobile,
                        renter_is_active=True,
                ).exclude(
                    unit=unit,
                ).exists():
                    return self.error(
                        'این شماره در واحد دیگری مستأجر فعال است.',
                    )

                # پیدا کردن حساب کاربری با شماره موبایل
                renter_user = User.objects.filter(
                    mobile=mobile,
                ).first()

                if renter_user:
                    # حساب مالک یا کاربر دیگر را بازنویسی نکن
                    same_unit_history = Renter.objects.filter(
                        unit=unit,
                        user=renter_user,
                    ).exists()

                    if not same_unit_history:
                        return self.error(
                            'این شماره موبایل قبلاً به کاربر دیگری تعلق دارد.',
                        )

                    renter_user.full_name = data['renter_name']
                    renter_user.is_active = True
                    renter_user.is_unit = True
                    renter_user.house = house

                    if renter_user.pk != request.user.pk:
                        renter_user.manager = request.user

                    renter_user.save(
                        update_fields=[
                            'full_name',
                            'is_active',
                            'is_unit',
                            'house',
                            'manager',
                        ]
                    )

                else:
                    renter_user = User.objects.create(
                        mobile=mobile,
                        username=mobile,
                        full_name=data['renter_name'],
                        house=house,
                        manager=request.user,
                        is_active=True,
                        is_unit=True,
                    )

                # تنظیم رمز عبور، در صورت ارسال
                password = data.get('renter_password')

                if password:
                    self.set_password_if_provided(
                        renter_user,
                        password,
                    )

                # تاریخ شروع سکونت مستأجر جدید
                today = date.today()

                # بستن مستأجران فعال قبلی همین واحد
                old_renters = list(
                    Renter.objects.select_for_update().filter(
                        unit=unit,
                        renter_is_active=True,
                    )
                )

                for old_renter in old_renters:
                    old_renter.renter_is_active = False

                    # اگر تاریخ پایان قبلاً تعیین نشده، تاریخ پایان
                    # را یک روز قبل از شروع مستأجر جدید قرار بده
                    old_renter.end_date = (
                            old_renter.end_date
                            or (start_date - timezone.timedelta(days=1))
                    )

                    old_renter.save(
                        update_fields=[
                            'renter_is_active',
                            'end_date',
                        ]
                    )

                    # بستن تاریخچه باز مستأجر قبلی
                    UnitResidenceHistory.objects.filter(
                        unit=unit,
                        renter=old_renter,
                        to_date__isnull=True,
                    ).update(
                        to_date=start_date - timezone.timedelta(days=1),
                    )

                # بستن تاریخچه باز مالک همان واحد
                UnitResidenceHistory.objects.filter(
                    unit=unit,
                    resident_type='owner',
                    to_date__isnull=True,
                ).update(
                    to_date=start_date - timezone.timedelta(days=1),
                )

                # ساخت مستأجر جدید
                renter = Renter.objects.create(
                    unit=unit,
                    myhouse=house,
                    user=renter_user,
                    renter_name=data['renter_name'],
                    renter_mobile=mobile,
                    renter_national_code=data.get(
                        'renter_national_code'
                    ),
                    renter_people_count=data.get(
                        'renter_people_count'
                    ),
                    start_date=start_date,
                    end_date=end_date,
                    contract_number=data.get(
                        'contract_number'
                    ),
                    estate_name=data.get('estate_name'),
                    renter_details=data.get('renter_details'),
                    renter_is_active=True,
                )

                # ایجاد تاریخچه سکونت مستأجر جدید
                UnitResidenceHistory.objects.create(
                    unit=unit,
                    resident_type='renter',
                    renter=renter,
                    name=renter.renter_name or '',
                    mobile=renter.renter_mobile or '',
                    people_count=int(
                        renter.renter_people_count or 0
                    ),
                    from_date=start_date,
                    to_date=None,
                    changed_by=request.user,
                )

                # به‌روزرسانی وضعیت و تعداد ساکنان واحد
                unit.is_renter = True

                try:
                    unit.people_count = int(
                        renter.renter_people_count or 0
                    )
                except (ValueError, TypeError):
                    unit.people_count = 0

                unit.save(
                    update_fields=[
                        'is_renter',
                        'people_count',
                    ]
                )

                return self.success(
                    'مستأجر با موفقیت ثبت شد.',
                    {
                        'unit': self.unit_data(unit),
                        'renter': self.renter_data(renter),
                    },
                    status.HTTP_201_CREATED,
                )

        except Exception:
            import logging

            logging.getLogger(__name__).exception(
                'Manager renter create failed'
            )

            return self.error(
                'خطا در ثبت مستأجر.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerRenterDeactivateAPIView(ManagerUnitBaseView):

    def patch(self, request, renter_id):
        if not request.user.is_middle_admin:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        try:
            with transaction.atomic():

                # ابتدا مستأجر را پیدا می‌کنیم
                renter = Renter.objects.select_related(
                    'unit',
                    'unit__myhouse',
                ).filter(
                    pk=renter_id,
                    unit__myhouse__user=request.user,
                    unit__myhouse__is_active=True,
                ).first()

                if renter is None:
                    return self.error(
                        'مستأجر پیدا نشد یا دسترسی ندارید.',
                        status.HTTP_404_NOT_FOUND,
                    )

                # قفل واحد برای جلوگیری از تغییر هم‌زمان
                unit = Unit.objects.select_for_update().filter(
                    pk=renter.unit_id,
                    myhouse__user=request.user,
                    myhouse__is_active=True,
                ).first()

                if unit is None:
                    return self.error(
                        'واحد پیدا نشد یا دسترسی ندارید.',
                        status.HTTP_404_NOT_FOUND,
                    )

                renter = Renter.objects.select_for_update().filter(
                    pk=renter_id,
                    unit=unit,
                ).first()

                if renter is None:
                    return self.error(
                        'مستأجر پیدا نشد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                if not renter.renter_is_active:
                    return self.success(
                        'این مستأجر قبلاً غیرفعال شده است.',
                        {
                            'renter': self.renter_data(renter),
                        },
                    )

                today = date.today()

                # غیرفعال کردن مستأجر
                renter.renter_is_active = False
                renter.end_date = renter.end_date or today

                renter.save(update_fields=[
                    'renter_is_active',
                    'end_date',
                ])

                # بستن سابقه باز همین مستأجر
                UnitResidenceHistory.objects.filter(
                    unit=unit,
                    renter=renter,
                    resident_type='renter',
                    to_date__isnull=True,
                ).update(
                    to_date=today,
                )

                # بررسی مستأجر فعال دیگر
                another_active_renter = Renter.objects.filter(
                    unit=unit,
                    renter_is_active=True,
                ).exclude(
                    pk=renter.pk,
                ).exists()

                owner_history_activated = False

                if not another_active_renter:

                    # بازگشت واحد به وضعیت مالک
                    unit.is_renter = False
                    unit.people_count = unit.owner_people_count or 0

                    unit.save(update_fields=[
                        'is_renter',
                        'people_count',
                    ])

                    # بررسی سابقه باز مالک
                    active_owner_history = (
                        UnitResidenceHistory.objects.filter(
                            unit=unit,
                            resident_type='owner',
                            to_date__isnull=True,
                        ).first()
                    )

                    if active_owner_history is None:
                        # استفاده از آخرین اطلاعات ثبت‌شده مالک
                        latest_owner_history = (
                            UnitResidenceHistory.objects.filter(
                                unit=unit,
                                resident_type='owner',
                            ).order_by(
                                '-from_date',
                                '-pk',
                            ).first()
                        )

                        owner_name = (
                                getattr(unit, 'owner_name', None)
                                or getattr(
                            latest_owner_history,
                            'name',
                            '',
                        )
                                or ''
                        )

                        owner_mobile = (
                                getattr(unit, 'owner_mobile', None)
                                or getattr(
                            latest_owner_history,
                            'mobile',
                            '',
                        )
                                or ''
                        )

                        # ایجاد دوره جدید سکونت مالک
                        UnitResidenceHistory.objects.create(
                            unit=unit,
                            resident_type='owner',
                            name=owner_name,
                            mobile=owner_mobile,
                            people_count=(
                                    unit.owner_people_count or 0
                            ),
                            renter=None,
                            from_date=today,
                            to_date=None,
                            changed_by=request.user,
                        )

                    owner_history_activated = True

                return self.success(
                    'مستأجر غیرفعال شد و سوابق سکونت به‌روزرسانی شد.',
                    {
                        'renter': self.renter_data(renter),
                        'unit_id': unit.pk,
                        'owner_history_activated': (
                            owner_history_activated
                        ),
                    },
                )

        except Exception:
            logger.exception(
                'Manager renter deactivate failed: renter_id=%s',
                renter_id,
            )

            return self.error(
                'خطا در غیرفعال‌سازی مستأجر.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerRenterActivateAPIView(ManagerUnitBaseView):

    def patch(self, request, renter_id):
        if not request.user.is_middle_admin:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        try:
            with transaction.atomic():

                renter = Renter.objects.select_related(
                    'unit',
                    'unit__myhouse',
                ).filter(
                    pk=renter_id,
                    unit__myhouse__user=request.user,
                    unit__myhouse__is_active=True,
                ).first()

                if renter is None:
                    return self.error(
                        'مستأجر پیدا نشد یا دسترسی ندارید.',
                        status.HTTP_404_NOT_FOUND,
                    )

                unit = Unit.objects.select_for_update().filter(
                    pk=renter.unit_id,
                    myhouse__user=request.user,
                    myhouse__is_active=True,
                ).first()

                if unit is None:
                    return self.error(
                        'واحد پیدا نشد یا دسترسی ندارید.',
                        status.HTTP_404_NOT_FOUND,
                    )

                renter = Renter.objects.select_for_update().filter(
                    pk=renter_id,
                    unit=unit,
                ).first()

                if renter is None:
                    return self.error(
                        'مستأجر پیدا نشد.',
                        status.HTTP_404_NOT_FOUND,
                    )

                if renter.renter_is_active:
                    return self.success(
                        'این مستأجر از قبل فعال است.',
                        {
                            'renter': self.renter_data(renter),
                        },
                    )

                # واحد نباید مستأجر فعال دیگری داشته باشد
                another_active_renter = Renter.objects.filter(
                    unit=unit,
                    renter_is_active=True,
                ).exclude(
                    pk=renter.pk,
                ).exists()

                if another_active_renter:
                    return self.error(
                        'این واحد مستأجر فعال دیگری دارد. '
                        'ابتدا مستأجر فعلی را غیرفعال کنید.',
                        status.HTTP_400_BAD_REQUEST,
                    )

                today = date.today()

                # بستن سابقه فعال مالک
                UnitResidenceHistory.objects.filter(
                    unit=unit,
                    resident_type='owner',
                    to_date__isnull=True,
                ).update(
                    to_date=today,
                )

                # جلوگیری از باقی ماندن سابقه باز قبلی همین مستأجر
                UnitResidenceHistory.objects.filter(
                    unit=unit,
                    renter=renter,
                    resident_type='renter',
                    to_date__isnull=True,
                ).update(
                    to_date=today,
                )

                # فعال کردن مجدد مستأجر
                renter.renter_is_active = True
                renter.start_date = today
                renter.end_date = None

                renter.save(update_fields=[
                    'renter_is_active',
                    'start_date',
                    'end_date',
                ])

                # تبدیل تعداد نفرات متنی به عدد
                try:
                    people_count = int(
                        renter.renter_people_count or 0
                    )
                except (TypeError, ValueError):
                    people_count = 0

                # ایجاد دوره جدید سکونت مستأجر
                UnitResidenceHistory.objects.create(
                    unit=unit,
                    resident_type='renter',
                    name=renter.renter_name or '',
                    mobile=renter.renter_mobile or '',
                    people_count=people_count,
                    renter=renter,
                    from_date=today,
                    to_date=None,
                    changed_by=request.user,
                )

                # به‌روزرسانی وضعیت واحد
                unit.is_renter = True
                unit.people_count = people_count

                unit.save(update_fields=[
                    'is_renter',
                    'people_count',
                ])

                return self.success(
                    'مستأجر فعال شد و سابقه مالک بسته شد.',
                    {
                        'renter': self.renter_data(renter),
                        'unit_id': unit.pk,
                        'owner_history_closed': True,
                    },
                )

        except Exception:
            logger.exception(
                'Manager renter activate failed: renter_id=%s',
                renter_id,
            )

            return self.error(
                'خطا در فعال‌سازی مستأجر.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerRenterDeleteAPIView(ManagerUnitBaseView):

    def delete(self, request, renter_id):
        if not request.user.is_middle_admin:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        renter = Renter.objects.select_related(
            'unit',
            'unit__myhouse',
        ).filter(
            pk=renter_id,
            unit__myhouse__user=request.user,
            unit__myhouse__is_active=True,
        ).first()

        if renter is None:
            return self.error(
                'مستأجر پیدا نشد یا قبلاً حذف شده است.',
                status.HTTP_404_NOT_FOUND,
            )

        today = date.today()

        try:
            with transaction.atomic():
                renter = Renter.objects.select_for_update().get(
                    pk=renter.pk,
                )

                unit = Unit.objects.select_for_update().get(
                    pk=renter.unit_id,
                    myhouse__user=request.user,
                    myhouse__is_active=True,
                )

                # بستن تاریخچه باز، بدون حذف رکورد تاریخچه
                UnitResidenceHistory.objects.filter(
                    unit=unit,
                    renter=renter,
                    to_date__isnull=True,
                ).update(to_date=today)

                renter.renter_is_active = False
                renter.end_date = renter.end_date or today

                renter.save(update_fields=[
                    'renter_is_active',
                    'end_date',
                ])

                another_active_renter = Renter.objects.filter(
                    unit=unit,
                    renter_is_active=True,
                ).exists()

                if not another_active_renter:
                    unit.is_renter = False
                    unit.people_count = unit.owner_people_count or 0

                    unit.save(update_fields=[
                        'is_renter',
                        'people_count',
                    ])

                return self.success(
                    'مستأجر با موفقیت حذف نرم شد.',
                    {
                        'renter_id': renter.pk,
                    },
                )

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Manager renter soft delete failed'
            )
            return self.error(
                'خطا در حذف مستأجر.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerRenterUpdateAPIView(ManagerUnitBaseView):

    def patch(self, request, renter_id):
        renter = Renter.objects.select_related(
            'unit',
            'unit__myhouse',
            'user',
        ).filter(
            pk=renter_id,
            renter_is_active=True,
            unit__myhouse__user=request.user,
            unit__myhouse__is_active=True,
        ).first()

        if not request.user.is_middle_admin:
            return self.error(
                'دسترسی مدیر معتبر نیست.',
                status.HTTP_403_FORBIDDEN,
            )

        if renter is None:
            return self.error(
                'مستأجر فعال پیدا نشد یا دسترسی به آن ندارید.',
                status.HTTP_404_NOT_FOUND,
            )

        serializer = ManagerRenterSerializer(
            data=request.data,
            partial=True,
        )

        if not serializer.is_valid():
            return self.error(
                'اطلاعات مستأجر معتبر نیست.',
                status.HTTP_400_BAD_REQUEST,
            )

        data = serializer.validated_data
        unit = renter.unit
        house = unit.myhouse

        try:
            with transaction.atomic():

                renter = Renter.objects.select_for_update().get(
                    pk=renter.pk,
                    unit__myhouse=house,
                    renter_is_active=True,
                )

                old_mobile = renter.user.mobile

                new_mobile = data.get(
                    'renter_mobile',
                    renter.renter_mobile,
                )

                new_name = data.get(
                    'renter_name',
                    renter.renter_name,
                )

                renter_user = renter.user

                if new_mobile != old_mobile:
                    other_user = User.objects.filter(
                        mobile=new_mobile,
                    ).exclude(
                        pk=renter_user.pk,
                    ).first()

                    if other_user:
                        return self.error(
                            'شماره موبایل به کاربر دیگری تعلق دارد.',
                        )

                if Renter.objects.filter(
                        user__mobile=new_mobile,
                        renter_is_active=True,
                ).exclude(
                    pk=renter.pk,
                ).exclude(
                    unit=unit,
                ).exists():
                    return self.error(
                        'این شماره در واحد دیگری مستأجر فعال است.',
                    )

                renter_user.mobile = new_mobile
                renter_user.username = new_mobile
                renter_user.full_name = new_name or renter_user.full_name
                renter_user.house = house
                renter_user.is_active = True
                renter_user.is_unit = True

                if renter_user.pk != request.user.pk:
                    renter_user.manager = request.user

                if data.get('renter_password'):
                    renter_user.set_password(
                        data['renter_password']
                    )

                renter_user.save()

                editable_fields = [
                    'renter_name',
                    'renter_mobile',
                    'renter_national_code',
                    'renter_people_count',
                    'start_date',
                    'end_date',
                    'contract_number',
                    'estate_name',
                    'renter_details',
                ]

                for field in editable_fields:
                    if field in data:
                        setattr(renter, field, data[field])

                if (
                        renter.start_date
                        and renter.end_date
                        and renter.end_date < renter.start_date
                ):
                    return self.error(
                        'تاریخ پایان اجاره نمی‌تواند قبل از تاریخ شروع باشد.',
                    )

                renter.save()

                # تاریخچه باز همین مستأجر را به‌روز می‌کنیم.
                history = UnitResidenceHistory.objects.filter(
                    unit=unit,
                    renter=renter,
                    to_date__isnull=True,
                ).order_by('-id').first()

                if history is None:
                    history = UnitResidenceHistory.objects.create(
                        unit=unit,
                        resident_type='renter',
                        renter=renter,
                        name=renter.renter_name or '',
                        mobile=renter.renter_mobile or '',
                        people_count=int(
                            renter.renter_people_count or 0
                        ),
                        from_date=(
                                renter.start_date
                                or timezone.localdate()
                        ),
                        to_date=None,
                        changed_by=request.user,
                    )
                else:
                    history.name = renter.renter_name or ''
                    history.mobile = renter.renter_mobile or ''
                    history.people_count = int(
                        renter.renter_people_count or 0
                    )
                    history.from_date = (
                            renter.start_date
                            or history.from_date
                    )
                    history.save(
                        update_fields=[
                            'name',
                            'mobile',
                            'people_count',
                            'from_date',
                        ]
                    )

                try:
                    unit.people_count = int(
                        renter.renter_people_count or 0
                    )
                except (ValueError, TypeError):
                    unit.people_count = 0

                unit.is_renter = True
                unit.save(
                    update_fields=[
                        'is_renter',
                        'people_count',
                    ]
                )

                return self.success(
                    'اطلاعات مستأجر فعال با موفقیت ویرایش شد.',
                    {
                        'unit': self.unit_data(unit),
                        'renter': self.renter_data(renter),
                    },
                )

        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                'Manager renter update failed'
            )
            return self.error(
                'خطا در ویرایش مستأجر.',
                status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


# ================ Charge Management ============================

class ManagerChargeHomeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # فقط مدیران مجاز به استفاده از این API هستند.
        if not getattr(request.user, 'is_middle_admin', False):
            return Response(
                {
                    'success': False,
                    'message': 'شما مجاز به دسترسی به مدیریت شارژها نیستید.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        cards = [
            {
                'key': 'monthly',
                'title': 'شارژ ماهانه',
                'description': 'ایجاد و مدیریت شارژهای ماهانه ساختمان',
                'icon': 'calendar_month',
            },
            {
                'key': 'civil',
                'title': 'شارژ عمرانی',
                'description': 'مدیریت هزینه‌ها و شارژهای عمرانی',
                'icon': 'construction',
            },
            {
                'key': 'my_charges',
                'title': 'شارژهای من',
                'description': 'مشاهده و پیگیری شارژهای ثبت‌شده توسط شما',
                'icon': 'receipt_long',
            },
        ]

        serializer = ManagerChargeHomeCardSerializer(
            cards,
            many=True,
        )

        return Response({
            'success': True,
            'count': len(serializer.data),
            'results': serializer.data,
        })


class ManagerChargeMethodsAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        print(
            "CHARGE METHODS API:",
            "user_id=", user.pk,
            "username=", user.get_username(),
            "is_middle_admin=", getattr(user, "is_middle_admin", False),
            "methods=", list(
                user.charge_methods.values_list("id", flat=True)
            ),
        )

        if not getattr(user, 'is_middle_admin', False):
            return Response(
                {
                    'success': False,
                    'message': 'شما مجاز به دسترسی نیستید.',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        methods = user.charge_methods.filter(
            is_active=True
        ).values('id', 'name')

        return Response({
            'success': True,
            'results': list(methods),
        })


class ManagerFixedChargeCreateView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        manager = request.user

        # 1. بررسی نقش مدیر
        if not getattr(manager, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه ثبت شارژ را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 2. دریافت ساختمان مدیر
        house = getattr(manager, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمانی برای مدیر تعریف نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 3. اعتبارسنجی اطلاعات فرم موجود
        form = FixChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {"errors": form.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 4. دریافت واحدهای فعال همین ساختمان
        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان پیدا نشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 5. دریافت محاسبه‌گر شارژ واحدی
        calculator = CALCULATORS.get("fix")

        if calculator is None:
            return Response(
                {"detail": "محاسبه‌گر شارژ واحدی تعریف نشده است."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        try:
            with transaction.atomic():

                # ذخیره مدل اصلی شارژ
                fix_charge = form.save(commit=False)
                fix_charge.user = manager
                fix_charge.charge_type = "fix"
                fix_charge.unit_count = units.count()
                fix_charge.save()

                content_type = ContentType.objects.get_for_model(
                    FixCharge
                )

                civil_amount = fix_charge.civil or 0
                other_amount = fix_charge.other_cost_amount or 0
                penalty_percent = (
                        fix_charge.payment_penalty_amount or 0
                )

                unified_charges = []

                for unit in units.iterator():
                    base_amount = calculator.calculate(
                        unit,
                        fix_charge,
                    )

                    total_amount = (
                            base_amount
                            + civil_amount
                            + other_amount
                    )

                    unified_charges.append(
                        UnifiedCharge(
                            user=manager,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            charge_type="fix",
                            amount=base_amount,
                            base_charge=total_amount,
                            civil=civil_amount,
                            payment_token=secrets.token_urlsafe(12),
                            other_cost_amount=other_amount,
                            penalty_percent=penalty_percent,
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=fix_charge.details or "",
                            title=fix_charge.name or "شارژ ثابت",
                            send_notification=False,
                            send_notification_date=None,
                            payment_deadline_date=(
                                fix_charge.payment_deadline
                            ),
                            content_type=content_type,
                            object_id=fix_charge.pk,
                        )
                    )

                UnifiedCharge.objects.bulk_create(
                    unified_charges,
                    batch_size=500,
                )

            return Response(
                {
                    "success": True,
                    "message": "شارژ واحدی با موفقیت ثبت شد.",
                    "charge": {
                        "id": fix_charge.pk,
                        "name": fix_charge.name,
                        "charge_type": "fix",
                        "unit_count": len(unified_charges),
                        "fix_amount": fix_charge.fix_amount,
                        "civil": civil_amount,
                        "other_cost_amount": other_amount,
                        "payment_deadline": (
                            fix_charge.payment_deadline.isoformat()
                            if fix_charge.payment_deadline
                            else None
                        ),
                        "total_per_unit": (
                                (fix_charge.fix_amount or 0)
                                + civil_amount
                                + other_amount
                        ),
                        "notification_sent": False,
                    },
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            # جزئیات خطای داخلی را در پاسخ عمومی افشا نمی‌کنیم.
            # خطا باید در لاگ سرور ثبت شود.
            import logging
            logging.getLogger(__name__).exception(
                "Failed to create manager fixed charge"
            )

            return Response(
                {"detail": "ثبت شارژ انجام نشد. خطای سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixedChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    # --------------------------------------------------
    # ساختمان و دسترسی مدیر
    # --------------------------------------------------

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None

        return getattr(request.user, "house", None)

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return FixCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_active_units(self, house):
        return Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(FixCharge)

    # --------------------------------------------------
    # وضعیت اطلاعیه
    # --------------------------------------------------

    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # خروجی JSON
    # --------------------------------------------------

    def serialize_charge(self, charge):
        content_type = self.get_content_type()

        related = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
        )

        # تعداد کل واحدهایی که برای این شارژ رکورد دارند
        unit_count = (
            related
            .values("unit_id")
            .distinct()
            .count()
        )

        # تعداد واحدهایی که اعلان شارژ برای آن‌ها ارسال شده
        notified_units_count = (
            related
            .filter(send_notification=True)
            .values("unit_id")
            .distinct()
            .count()
        )

        notified = notified_units_count > 0

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "fix",

            "fix_amount": charge.fix_amount or 0,

            # تعداد کل واحدها
            "unit_count": unit_count,

            # تعداد واحدهای اعلام‌شده
            "notified_units_count": notified_units_count,

            # آیا برای حداقل یک واحد اعلان ارسال شده؟
            "send_notification": notified,

            "other_cost_amount": (
                    charge.other_cost_amount or 0
            ),

            "payment_penalty_amount": (
                    charge.payment_penalty_amount or 0
            ),

            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline
                else None
            ),

            "details": charge.details or "",

            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at
                else None
            ),

            "can_edit": not notified,

            "can_delete": (
                    not notified
                    and not related.filter(is_paid=True).exists()
            ),
        }

    # --------------------------------------------------
    # ذخیره یا همگام‌سازی UnifiedChargeها
    # --------------------------------------------------

    def sync_unified_charges(self, request, charge, units, civil_amount=0):
        from django.db import transaction

        content_type = self.get_content_type()

        calculator = CALCULATORS.get("fix")
        if calculator is None:
            raise ValueError("محاسبه‌گر شارژ واحدی تعریف نشده است.")

        other_amount = charge.other_cost_amount or 0
        penalty_percent = charge.payment_penalty_amount or 0

        with transaction.atomic():
            for unit in units.iterator():
                base_amount = calculator.calculate(unit, charge) or 0
                total_amount = base_amount + civil_amount + other_amount

                lookup = {
                    "user": request.user,
                    "unit": unit,
                    "content_type": content_type,
                    "object_id": charge.pk,
                }

                defaults = {
                    "house": unit.myhouse,
                    "bank": None,
                    "charge_type": "fix",
                    "amount": base_amount,
                    "base_charge": total_amount,
                    "civil": civil_amount,
                    "other_cost_amount": other_amount,
                    "penalty_percent": penalty_percent,
                    "penalty_amount": 0,
                    "total_charge_month": total_amount,
                    "details": charge.details or "",
                    "title": charge.name or "شارژ واحدی",
                    "payment_deadline_date": charge.payment_deadline,
                }

                unified_charge = UnifiedCharge.objects.filter(
                    **lookup
                ).first()

                if unified_charge:
                    # اگر رکورد وجود دارد، توکن پرداخت و وضعیت پرداخت
                    # آن را تغییر نمی‌دهیم.
                    for field, value in defaults.items():
                        setattr(unified_charge, field, value)

                    unified_charge.save()

                else:
                    # برای رکورد جدید، توکن یکتا ایجاد می‌کنیم.
                    UnifiedCharge.objects.create(
                        **lookup,
                        **defaults,
                        payment_token=secrets.token_urlsafe(12),
                        send_notification=False,
                    )

    # --------------------------------------------------
    # GET: فهرست شارژهای واحدی
    # --------------------------------------------------

    def get(self, request, pk=None):
        print("FIXED CHARGE GET CALLED")
        print("USER ID:", request.user.id)
        print("PK:", pk)
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ موردنظر پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = (
            FixCharge.objects
            .filter(user=request.user)
            .annotate(
                total_units=Count(
                    "unified_charges__unit",
                    distinct=True,
                ),
                notified_count=Count(
                    "unified_charges",
                    filter=Q(
                        unified_charges__send_notification=True
                    ),
                    distinct=True,
                ),
            )
            .order_by("-created_at")
        )

        results = [self.serialize_charge(c) for c in charges]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: افزودن شارژ واحدی
    # --------------------------------------------------

    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای افزودن شارژ، مسیر بدون شناسه را استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        house = self.get_house(request)
        units = self.get_active_units(house)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = FixChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.unit_count = units.count()
                charge.save()

                # civil در مدل BaseCharge ارسالی وجود ندارد؛
                # فعلاً مقدار فرم غیرفعال را می‌خوانیم.
                civil_amount = form.cleaned_data.get("civil") or 0

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                    civil_amount=civil_amount,
                )

            return Response(
                {
                    "detail": "شارژ واحدی با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("خطا در ثبت شارژ واحدی")
            return Response(
                {"detail": "ثبت شارژ انجام نشد. گزارش خطای سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش شارژ واحدی
    # --------------------------------------------------

    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixCharge.objects
                    .select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ موردنظر پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # بررسی مجدد در سمت سرور
                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "این شارژ اطلاعیه ارسال‌شده دارد "
                                "و قابل ویرایش نیست."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                house = self.get_house(request)
                units = self.get_active_units(house)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                # ModelForm برای PATCH به داده‌های اجباری نیاز دارد.
                # فیلدهای ارسال‌نشده از اطلاعات فعلی تکمیل می‌شوند.
                data = request.data.copy()

                current_values = {
                    "name": charge.name or "",
                    "fix_amount": charge.fix_amount or 0,
                    "details": charge.details or "",
                    "payment_penalty_amount": (
                            charge.payment_penalty_amount or 0
                    ),
                    "other_cost_amount": charge.other_cost_amount or 0,
                }

                for field, value in current_values.items():
                    if field not in data:
                        data[field] = value

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        jalali_deadline = jdatetime.date.fromgregorian(
                            date=charge.payment_deadline
                        )
                        data["payment_deadline"] = (
                            jalali_deadline.strftime("%Y/%m/%d")
                        )

                form = FixChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [str(error) for error in errors]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save(commit=False)
                charge.unit_count = units.count()
                charge.save()

                civil_amount = form.cleaned_data.get("civil") or 0

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                    civil_amount=civil_amount,
                )

            return Response({
                "detail": "شارژ واحدی با موفقیت ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception("خطا در ویرایش شارژ واحدی")
            return Response(
                {"detail": "ویرایش شارژ انجام نشد. گزارش خطای سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف شارژ واحدی
    # --------------------------------------------------

    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixCharge.objects
                    .select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ موردنظر پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # اولویت با قانون ممنوعیت حذف پس از ارسال اطلاعیه است.
                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ اطلاعیه صادر شده است؛ "
                                "بنابراین امکان حذف آن وجود ندارد."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ پرداخت ثبت شده است؛ "
                                "امکان حذف آن وجود ندارد."
                            ),
                            "code": "charge_already_paid",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ واحدی"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد.",
            })

        except ProtectedError:
            return Response(
                {"detail": "به دلیل وابستگی‌های مالی، حذف این شارژ ممکن نیست."},
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception("خطا در حذف شارژ واحدی")
            return Response(
                {"detail": "حذف شارژ انجام نشد. گزارش خطای سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixedChargeUnitsAPIView(APIView):
    """
    GET /api/manager/charges/fixed/<pk>/units/
    فهرست واحدهای فعال ساختمان به همراه وضعیت ارسال شارژ و پیامک.
    """

    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        return MyHouse.objects.filter(
            user=request.user
        ).first()

    def get_charge(self, request, pk):
        return FixCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_units_queryset(self, request, house):
        units = Unit.objects.filter(
            Q(user=request.user) |
            Q(user__manager=request.user),
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get(
            "search", ""
        ).strip()

        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search) |
                Q(owner_name__icontains=search) |
                Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(
                status_residence="empty"
            )

        return units.order_by("unit")

    def get(self, request, pk):
        house = self.get_house(request)
        charge = self.get_charge(request, pk)

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        content_type = ContentType.objects.get_for_model(
            FixCharge
        )

        units = self.get_units_queryset(request, house)

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        results = []

        for unit in units:
            uc = charge_by_unit.get(unit.pk)

            renter = unit.renters.filter(
                renter_is_active=True
            ).first()

            # وضعیت واقعی پیامک از رکورد UnifiedCharge
            send_sms = bool(
                uc and uc.send_sms
            )

            send_sms_date = (
                uc.send_sms_date.isoformat()
                if uc and uc.send_sms_date
                else None
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),

                "owner_name": unit.owner_name or "",

                "renter_name": (
                    renter.renter_name if renter else ""
                ),

                "resident_type": (
                    "renter" if renter
                    else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),

                # اعلان سیستمی
                "is_notified": bool(
                    uc and uc.send_notification
                ),

                # وضعیت پیامک
                "send_sms": send_sms,
                "send_sms_date": send_sms_date,

                # وضعیت پرداخت
                "is_paid": bool(
                    uc and uc.is_paid
                ),

                # مبلغ شارژ
                "current_charge": str(
                    uc.total_charge_month
                    if uc
                    else (
                            (charge.fix_amount or Decimal("0")) +
                            (getattr(charge, "civil", 0) or Decimal("0")) +
                            (charge.other_cost_amount or Decimal("0"))
                    )
                ),

                # شماره سند مالی
                "financial_document_number": (
                    uc.financial_document_number
                    if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name,
            "fix_amount": str(charge.fix_amount or 0),

            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),

            "count": len(results),
            "results": results,
        })


class ManagerFixedChargeSendAPIView(APIView):
    """
    POST /api/manager/charges/fixed/<pk>/units/send/

    ارسال سیستمی:
    {
        "unit_ids": [1, 2, 3],
        "send_sms": false
    }

    ارسال سیستمی و پیامکی:
    {
        "unit_ids": [1, 2, 3],
        "send_sms": true
    }
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        logger = logging.getLogger(__name__)

        # ---------------------------------------
        # 1. بررسی ساختمان و شارژ
        # ---------------------------------------
        house = MyHouse.objects.filter(
            user=request.user
        ).first()

        charge = FixCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # ---------------------------------------
        # 2. اعتبارسنجی واحدها
        # ---------------------------------------
        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------
        # 3. روش ارسال
        # ---------------------------------------
        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "روش ارسال پیامک معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_units = Unit.objects.filter(
            Q(user=request.user)
            | Q(user__manager=request.user),
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {
            unit.pk: unit for unit in valid_units
        }

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail":
                        "برخی واحدها نامعتبرند یا به ساختمان شما تعلق ندارند."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ---------------------------------------
        # 4. بررسی ماشین حساب شارژ
        # ---------------------------------------
        calculator = CALCULATORS.get(charge.charge_type)

        if not calculator:
            return Response(
                {
                    "detail":
                        "نوع محاسبه این شارژ پشتیبانی نمی‌شود."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixCharge
        )

        charges_to_notify = []

        # ---------------------------------------
        # 5. ثبت شارژهای سیستمی
        # ---------------------------------------
        try:
            with transaction.atomic():

                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    uc = (
                        UnifiedCharge.objects
                        .select_for_update()
                        .filter(
                            content_type=content_type,
                            object_id=charge.pk,
                            unit=unit,
                        )
                        .first()
                    )

                    if uc is None:
                        base_amount = calculator.calculate(
                            unit, charge
                        )

                        civil_amount = (
                                getattr(charge, "civil", 0)
                                or Decimal("0")
                        )

                        other_amount = (
                                getattr(
                                    charge,
                                    "other_cost_amount",
                                    0,
                                )
                                or Decimal("0")
                        )

                        total = (
                                base_amount
                                + civil_amount
                                + other_amount
                        )

                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=(
                                document_number
                            ),
                            amount=base_amount,
                            charge_type=charge.charge_type,
                            base_charge=total,
                            main_charge=charge,
                            penalty_percent=(
                                charge.payment_penalty_amount
                            ),
                            civil=civil_amount,
                            other_cost_amount=other_amount,
                            penalty_amount=0,
                            total_charge_month=total,
                            details=charge.details or "",
                            title=charge.name,
                            send_notification=False,
                            send_notification_date=None,
                            payment_deadline_date=(
                                charge.payment_deadline
                            ),
                            content_type=content_type,
                            object_id=charge.pk,
                            payment_token=(
                                secrets.token_urlsafe(12)
                            ),
                        )

                        uc.save()

                    elif not uc.financial_document_number:
                        # فقط شماره سند مفقود تکمیل شود.
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    # فقط وضعیت اعلان سیستمی تغییر می‌کند.
                    # اطلاعات مالی و پرداخت دست‌نخورده می‌مانند.
                    uc.send_notification = True
                    uc.send_notification_date = (
                        timezone.now().date()
                    )

                    uc.save(
                        update_fields=[
                            "send_notification",
                            "send_notification_date",
                        ]
                    )

                    charges_to_notify.append(uc)

        except Exception:
            logger.exception(
                "Error creating fixed unified charges"
            )

            return Response(
                {
                    "detail":
                        "ثبت ارسال شارژ انجام نشد. گزارش سرور را بررسی کنید."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # ---------------------------------------
        # 6. فقط ارسال سیستمی؛ بدون پیامک
        # ---------------------------------------
        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(charges_to_notify),
                "sms_requested": False,
                "sms_sent": False,
                "detail":
                    "اطلاع‌رسانی سیستمی شارژ برای واحدهای انتخاب‌شده ثبت شد.",
            })

        # ---------------------------------------
        # 7. پیدا کردن واحدهای دارای موبایل معتبر
        # ---------------------------------------
        sms_eligible_charges = [
            uc
            for uc in charges_to_notify
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(charges_to_notify),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail":
                    "اعلان سیستمی ثبت شد، اما شماره موبایل معتبر برای ارسال پیامک پیدا نشد.",
            })

        # ---------------------------------------
        # 8. ارسال پیامک با سرویس موجود پروژه
        # ---------------------------------------
        try:
            from django.conf import settings

            unit_sms_price = Decimal(
                str(settings.SMS_PRICE)
            )

            def save_sms_metadata(
                    total_sms,
                    total_price,
            ):
                """
                این callback فقط در مسیر موفقیت سرویس
                فراخوانی می‌شود.
                """

                if total_sms <= 0:
                    return

                # هزینه کل را به نسبت تعداد گیرندگان
                # بین شارژهای پیامک‌شده تقسیم می‌کنیم.
                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = (
                        timezone.now().date()
                    )
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = (
                        per_charge_price
                    )

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "Fixed charge SMS sending failed"
            )

            # شارژ سیستمی قبلاً ثبت شده است؛
            # خطای پیامک نباید سابقه مالی را حذف کند.
            return Response({
                "ok": True,
                "sent_count": len(charges_to_notify),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail":
                    "اعلان سیستمی ثبت شد، اما هنگام ارسال پیامک خطا رخ داد. گزارش سرور را بررسی کنید.",
            })

        # ---------------------------------------
        # 9. نتیجه نهایی
        # ---------------------------------------
        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(charges_to_notify),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان سیستمی ثبت شد؛ ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(charges_to_notify),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(
                sms_result.total_price
            ),
            "detail":
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد.",
        })


class ManagerFixedChargeCancelAPIView(APIView):
    """
    POST /api/manager/charges/fixed/<pk>/units/cancel/

    JSON:
    {"unit_ids": [1, 2, 3]}

    رکورد مالی حذف نمی‌شود؛ وضعیت پرداخت، شماره سند،
    مبلغ و اطلاعات پرداخت تغییر نمی‌کنند.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        house = MyHouse.objects.filter(
            user=request.user
        ).first()

        charge = FixCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}
        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                Q(user=request.user) |
                Q(user__manager=request.user),
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixCharge
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
            )

            cancelled_count = qs.filter(
                Q(send_notification=True) | Q(send_sms=True)
            ).update(
                send_notification=False,
                send_notification_date=None,
                send_sms=False,
                send_sms_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اطلاع‌رسانی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Area Charge ========================
class ManagerAreaChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def normalize_api_deadline(self, data):
        import datetime
        import re
        import jdatetime

        data = data.copy()

        value = str(data.get("payment_deadline") or "").strip()

        if not value:
            return data

        # ارقام فارسی و عربی به انگلیسی تبدیل شوند
        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )
        value = value.translate(translation)

        # تاریخ شمسی با قالب YYYY-MM-DD یا YYYY/MM/DD
        jalali_match = re.fullmatch(
            r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
            value,
        )

        if jalali_match:
            year, month, day = map(int, jalali_match.groups())

            # سال‌های شمسی
            if 1200 <= year <= 1600:
                try:
                    jalali_date = jdatetime.date(year, month, day)

                    data["payment_deadline"] = (
                        jalali_date.strftime("%Y-%m-%d")
                    )
                    return data

                except ValueError:
                    # تاریخ نامعتبر را بدون تبدیل رها می‌کنیم
                    data["payment_deadline"] = value
                    return data

            # سال‌های میلادی
            if 1900 <= year <= 2200:
                try:
                    gregorian_date = datetime.date(year, month, day)

                    jalali_date = jdatetime.date.fromgregorian(
                        date=gregorian_date
                    )

                    data["payment_deadline"] = (
                        jalali_date.strftime("%Y-%m-%d")
                    )
                    return data

                except ValueError:
                    data["payment_deadline"] = value
                    return data

        # تاریخ نامشخص را دست‌کاری نکن
        data["payment_deadline"] = value
        return data

    # --------------------------------------------------
    # ساختمان و دسترسی مدیر
    # --------------------------------------------------

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None

        return getattr(request.user, "house", None)

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return AreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_active_units(self, house):
        return Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(AreaCharge)

    # --------------------------------------------------
    # بررسی وضعیت اعلان و پرداخت
    # --------------------------------------------------

    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ یک واحد
    # --------------------------------------------------

    def calculate_unit_amount(self, unit, charge):
        area = getattr(unit, "area", None)

        if area is None:
            raise ValueError(
                f"متراژ واحد {unit.pk} مشخص نشده است."
            )

        area_amount = Decimal(str(charge.area_amount or 0))
        unit_area = Decimal(str(area))

        base_amount = unit_area * area_amount

        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        total_amount = base_amount + other_amount

        return base_amount, other_amount, total_amount

    # --------------------------------------------------
    # خروجی JSON
    # --------------------------------------------------

    def serialize_charge(self, charge):
        content_type = self.get_content_type()

        related = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
        )

        unit_count = (
            related.values("unit_id").distinct().count()
        )

        notified_units_count = (
            related.filter(
                send_notification=True
            ).values("unit_id").distinct().count()
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "area",
            "area_amount": charge.area_amount or 0,
            "total_area": charge.total_area or 0,
            "unit_count": unit_count,
            "notified_units_count": notified_units_count,
            "send_notification": notified_units_count > 0,
            "other_cost_amount": charge.other_cost_amount or 0,
            "payment_penalty_amount": (
                    charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),
            "can_edit": not self.has_notification(charge),
            "can_delete": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
        }

    # --------------------------------------------------
    # ساخت یا همگام‌سازی UnifiedCharge
    # --------------------------------------------------

    def sync_unified_charges(
            self,
            request,
            charge,
            units,
    ):
        content_type = self.get_content_type()

        with transaction.atomic():
            for unit in units.iterator():
                base_amount, other_amount, total_amount = (
                    self.calculate_unit_amount(unit, charge)
                )

                lookup = {
                    "user": request.user,
                    "unit": unit,
                    "content_type": content_type,
                    "object_id": charge.pk,
                }

                unified_charge = (
                    UnifiedCharge.objects.select_for_update()
                    .filter(**lookup)
                    .first()
                )

                if unified_charge:
                    # شارژ دارای پرداخت را بازنویسی نمی‌کنیم.
                    if unified_charge.is_paid:
                        continue

                    # پس از ارسال اعلان، مبلغ و اطلاعات مالی
                    # رکورد قبلی را تغییر نمی‌دهیم.
                    if unified_charge.send_notification:
                        continue

                    unified_charge.house = unit.myhouse
                    unified_charge.charge_type = "area"
                    unified_charge.amount = base_amount
                    unified_charge.base_charge = total_amount
                    unified_charge.other_cost_amount = other_amount
                    unified_charge.penalty_percent = (
                            charge.payment_penalty_amount or 0
                    )
                    unified_charge.penalty_amount = 0
                    unified_charge.total_charge_month = total_amount
                    unified_charge.details = charge.details or ""
                    unified_charge.title = charge.name or "شارژ متراژی"
                    unified_charge.payment_deadline_date = (
                        charge.payment_deadline
                    )

                    # عمداً فیلد civil را تغییر نمی‌دهیم.
                    # توکن پرداخت، شماره سند و وضعیت پیامک حفظ می‌شوند.
                    unified_charge.save()

                else:
                    UnifiedCharge.objects.create(
                        **lookup,
                        house=unit.myhouse,
                        bank=None,
                        charge_type="area",
                        amount=base_amount,
                        base_charge=total_amount,
                        other_cost_amount=other_amount,
                        penalty_percent=(
                                charge.payment_penalty_amount or 0
                        ),
                        penalty_amount=0,
                        total_charge_month=total_amount,
                        details=charge.details or "",
                        title=charge.name or "شارژ متراژی",
                        payment_deadline_date=charge.payment_deadline,
                        payment_token=secrets.token_urlsafe(12),
                        send_notification=False,
                    )

    # --------------------------------------------------
    # GET: فهرست و جزئیات
    # --------------------------------------------------

    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ متراژی پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = (
            AreaCharge.objects
            .filter(user=request.user)
            .order_by("-created_at")
        )

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد شارژ متراژی
    # --------------------------------------------------

    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای ایجاد شارژ از مسیر بدون شناسه استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        house = self.get_house(request)
        units = self.get_active_units(house)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form_data = self.normalize_api_deadline(request.data)

        print(
            "AREA DATE RECEIVED:",
            request.data.get("payment_deadline")
        )

        print(
            "AREA DATE NORMALIZED:",
            form_data.get("payment_deadline")
        )

        form = AreaChargeForm(data=form_data)

        if not form.is_valid():
            print("AREA FORM ERRORS:", form.errors)
            print("AREA FORM DATA:", form.data)

            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.unit_count = units.count()

                # مجموع متراژ واحدهای فعال
                total_area = Decimal("0")

                for unit in units.iterator():
                    area = getattr(unit, "area", None)

                    if area is None:
                        raise ValueError(
                            f"متراژ واحد {unit.pk} مشخص نشده است."
                        )

                    total_area += Decimal(str(area))

                charge.total_area = total_area
                charge.save()

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                )

            return Response(
                {
                    "detail": "شارژ متراژی با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("خطا در ثبت شارژ متراژی")

            return Response(
                {
                    "detail": (
                        "ثبت شارژ انجام نشد. "
                        "گزارش خطای سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش شارژ متراژی
    # --------------------------------------------------

    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    AreaCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ اعلان ارسال شده "
                                "و امکان ویرایش وجود ندارد."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ پرداخت ثبت شده "
                                "و امکان ویرایش وجود ندارد."
                            ),
                            "code": "charge_already_paid",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                house = self.get_house(request)
                units = self.get_active_units(house)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                data = request.data.copy()

                current_values = {
                    "name": charge.name or "",
                    "area_amount": charge.area_amount or 0,
                    "details": charge.details or "",
                    "payment_penalty_amount": (
                            charge.payment_penalty_amount or 0
                    ),
                    "other_cost_amount": (
                            charge.other_cost_amount or 0
                    ),
                }

                for field, value in current_values.items():
                    if field not in data:
                        data[field] = value

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        jalali_deadline = jdatetime.date.fromgregorian(
                            date=charge.payment_deadline
                        )
                        data["payment_deadline"] = (
                            jalali_deadline.strftime("%Y-%m-%d")
                        )

                form = AreaChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [str(error) for error in errors]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save(commit=False)
                charge.unit_count = units.count()

                total_area = Decimal("0")

                for unit in units.iterator():
                    area = getattr(unit, "area", None)

                    if area is None:
                        raise ValueError(
                            f"متراژ واحد {unit.pk} مشخص نشده است."
                        )

                    total_area += Decimal(str(area))

                charge.total_area = total_area
                charge.save()

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                )

            return Response({
                "detail": "شارژ متراژی با موفقیت ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception("خطا در ویرایش شارژ متراژی")

            return Response(
                {"detail": "ویرایش شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف شارژ متراژی
    # --------------------------------------------------

    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    AreaCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ اعلان ارسال شده "
                                "و امکان حذف وجود ندارد."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ پرداخت ثبت شده "
                                "و امکان حذف وجود ندارد."
                            ),
                            "code": "charge_already_paid",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ متراژی"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "به دلیل وابستگی‌های مالی، "
                        "حذف این شارژ امکان‌پذیر نیست."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception("خطا در حذف شارژ متراژی")

            return Response(
                {"detail": "حذف شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerAreaChargeUnitsAPIView(APIView):
    """
    GET /api/manager/charges/area/<pk>/units/
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = AreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            AreaCharge
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)

            renter = unit.renters.filter(
                renter_is_active=True
            ).first()

            area = getattr(unit, "area", None)

            base_amount = (
                    Decimal(str(area or 0))
                    * Decimal(str(charge.area_amount or 0))
            )

            other_amount = Decimal(
                str(charge.other_cost_amount or 0)
            )

            calculated_total = base_amount + other_amount

            # اگر سند ثبت شده است، مبلغ ذخیره‌شده را نمایش بده.
            current_amount = (
                uc.total_charge_month
                if uc
                else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(area if area is not None else ""),
                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": (
                    "renter" if renter
                    else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),

                "is_notified": bool(
                    uc and uc.send_notification
                ),

                "send_sms": bool(uc and uc.send_sms),

                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date
                    else None
                ),

                "is_paid": bool(uc and uc.is_paid),

                "current_charge": str(current_amount),

                "financial_document_number": (
                    uc.financial_document_number
                    if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name,
            "charge_type": "area",
            "area_amount": str(charge.area_amount or 0),
            "total_area": str(charge.total_area or 0),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "count": len(results),
            "results": results,
        })


class ManagerAreaChargeSendAPIView(APIView):
    """
    POST /api/manager/charges/area/<pk>/units/send/

    {
        "unit_ids": [1, 2, 3],
        "send_sms": true
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        charge = AreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail":
                        "برخی واحدها نامعتبرند یا به ساختمان شما تعلق ندارند."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            AreaCharge
        )

        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    area = getattr(unit, "area", None)

                    if area is None:
                        raise ValueError(
                            f"متراژ واحد {unit.pk} مشخص نشده است."
                        )

                    base_amount = (
                            Decimal(str(area))
                            * Decimal(str(charge.area_amount or 0))
                    )

                    other_amount = Decimal(
                        str(charge.other_cost_amount or 0)
                    )

                    total_amount = base_amount + other_amount

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(
                            content_type=content_type,
                            object_id=charge.pk,
                            unit=unit,
                        )
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            content_type=content_type,
                            object_id=charge.pk,
                            charge_type="area",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ متراژی",
                            payment_deadline_date=charge.payment_deadline,
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    # سند پرداخت‌شده نباید از نو محاسبه شود.
                    if uc.is_paid:
                        notified_charges.append(uc)
                        continue

                    # مبلغ و مشخصات مالی سند موجود حفظ می‌شود.
                    uc.send_notification = True
                    uc.send_notification_date = (
                        timezone.now().date()
                    )
                    uc.save(
                        update_fields=[
                            "send_notification",
                            "send_notification_date",
                        ]
                    )

                    notified_charges.append(uc)

        except Exception:
            logger.exception(
                "خطا در ثبت اعلان شارژ متراژی"
            )

            return Response(
                {
                    "detail":
                        "ثبت اعلان انجام نشد. گزارش خطای سرور را بررسی کنید."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی شارژ ثبت شد.",
            })

        sms_eligible_charges = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail":
                    "اعلان ثبت شد، اما شماره موبایل معتبری برای پیامک وجود ندارد.",
            })

        try:
            from django.conf import settings

            unit_sms_price = Decimal(
                str(settings.SMS_PRICE)
            )

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = (
                        timezone.now().date()
                    )
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "خطا در ارسال پیامک شارژ متراژی"
            )

            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail":
                    "اعلان سیستمی ثبت شد، اما ارسال پیامک با خطا مواجه شد.",
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail":
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد.",
        })


class ManagerAreaChargeCancelAPIView(APIView):
    """
    POST /api/manager/charges/area/<pk>/units/cancel/

    {
        "unit_ids": [1, 2, 3]
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        charge = AreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            AreaCharge
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Person Charge ========================
class ManagerPersonChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    # --------------------------------------------------
    # نرمال‌سازی تاریخ شمسی و میلادی
    # --------------------------------------------------
    def normalize_api_deadline(self, data):
        import datetime
        import re
        import jdatetime

        data = data.copy()
        value = str(data.get("payment_deadline") or "").strip()

        if not value:
            return data

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )
        value = value.translate(translation)

        match = re.fullmatch(
            r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})",
            value,
        )

        if match:
            year, month, day = map(int, match.groups())

            # تاریخ شمسی
            if 1200 <= year <= 1600:
                try:
                    jalali_date = jdatetime.date(year, month, day)
                    data["payment_deadline"] = jalali_date.strftime(
                        "%Y-%m-%d"
                    )
                    return data
                except ValueError:
                    data["payment_deadline"] = value
                    return data

            # تاریخ میلادی؛ تبدیل به رشته شمسی برای فرم
            if 1900 <= year <= 2200:
                try:
                    gregorian_date = datetime.date(year, month, day)
                    jalali_date = jdatetime.date.fromgregorian(
                        date=gregorian_date
                    )
                    data["payment_deadline"] = jalali_date.strftime(
                        "%Y-%m-%d"
                    )
                    return data
                except ValueError:
                    data["payment_deadline"] = value
                    return data

        data["payment_deadline"] = value
        return data

    # --------------------------------------------------
    # دسترسی مدیر و ساختمان
    # --------------------------------------------------
    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None

        return getattr(request.user, "house", None)

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return PersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_active_units(self, house):
        return Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(PersonCharge)

    # --------------------------------------------------
    # بررسی اعلان و پرداخت
    # --------------------------------------------------
    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ شارژ هر واحد
    # --------------------------------------------------
    def calculate_unit_amount(self, unit, charge):
        people_count = int(unit.people_count or 0)

        if people_count < 0:
            raise ValueError(
                f"تعداد نفرات واحد {unit.pk} معتبر نیست."
            )

        person_amount = Decimal(
            str(charge.person_amount or 0)
        )

        base_amount = Decimal(people_count) * person_amount

        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        total_amount = base_amount + other_amount

        return base_amount, other_amount, total_amount

    # --------------------------------------------------
    # محاسبه مجموع نفرات واحدهای فعال
    # --------------------------------------------------
    def calculate_total_people(self, units):
        return sum(
            int(unit.people_count or 0)
            for unit in units.iterator()
        )

    # --------------------------------------------------
    # خروجی JSON
    # --------------------------------------------------
    def serialize_charge(self, charge):
        content_type = self.get_content_type()

        related = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
        )

        unit_count = related.values("unit_id").distinct().count()

        notified_units_count = (
            related.filter(
                send_notification=True
            ).values("unit_id").distinct().count()
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "person",
            "person_amount": charge.person_amount or 0,
            "total_people": charge.total_people or 0,
            "unit_count": unit_count,
            "notified_units_count": notified_units_count,
            "send_notification": notified_units_count > 0,
            "other_cost_amount": charge.other_cost_amount or 0,
            "payment_penalty_amount": (
                    charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),
            "can_edit": not self.has_notification(charge),
            "can_delete": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
        }

    # --------------------------------------------------
    # ایجاد یا همگام‌سازی UnifiedCharge
    # --------------------------------------------------
    def sync_unified_charges(self, request, charge, units):
        content_type = self.get_content_type()

        with transaction.atomic():
            for unit in units.iterator():
                base_amount, other_amount, total_amount = (
                    self.calculate_unit_amount(unit, charge)
                )

                lookup = {
                    "user": request.user,
                    "unit": unit,
                    "content_type": content_type,
                    "object_id": charge.pk,
                }

                unified_charge = (
                    UnifiedCharge.objects.select_for_update()
                    .filter(**lookup)
                    .first()
                )

                if unified_charge:
                    # سند پرداخت‌شده را تغییر نده
                    if unified_charge.is_paid:
                        continue

                    # سند دارای اعلان را تغییر نده
                    if unified_charge.send_notification:
                        continue

                    unified_charge.house = unit.myhouse
                    unified_charge.charge_type = "person"
                    unified_charge.amount = base_amount
                    unified_charge.base_charge = total_amount
                    unified_charge.other_cost_amount = other_amount
                    unified_charge.penalty_percent = (
                            charge.payment_penalty_amount or 0
                    )
                    unified_charge.penalty_amount = 0
                    unified_charge.total_charge_month = total_amount
                    unified_charge.details = charge.details or ""
                    unified_charge.title = (
                            charge.name or "شارژ نفری"
                    )
                    unified_charge.payment_deadline_date = (
                        charge.payment_deadline
                    )

                    # شماره سند، توکن و اطلاعات پیامک حفظ می‌شوند.
                    unified_charge.save()

                else:
                    UnifiedCharge.objects.create(
                        **lookup,
                        house=unit.myhouse,
                        bank=None,
                        charge_type="person",
                        amount=base_amount,
                        base_charge=total_amount,
                        other_cost_amount=other_amount,
                        penalty_percent=(
                                charge.payment_penalty_amount or 0
                        ),
                        penalty_amount=0,
                        total_charge_month=total_amount,
                        details=charge.details or "",
                        title=charge.name or "شارژ نفری",
                        payment_deadline_date=charge.payment_deadline,
                        payment_token=secrets.token_urlsafe(12),
                        send_notification=False,
                    )

    # --------------------------------------------------
    # GET: فهرست و جزئیات
    # --------------------------------------------------
    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ نفری پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = (
            PersonCharge.objects
            .filter(user=request.user)
            .order_by("-created_at")
        )

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد شارژ نفری
    # --------------------------------------------------
    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {
                    "detail":
                        "برای ایجاد شارژ از مسیر بدون شناسه استفاده کنید."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        house = self.get_house(request)
        units = self.get_active_units(house)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form_data = self.normalize_api_deadline(request.data)
        form = PersonChargeForm(data=form_data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.unit_count = units.count()
                charge.total_people = self.calculate_total_people(
                    units
                )
                charge.save()

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                )

            return Response(
                {
                    "detail": "شارژ نفری با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("خطا در ثبت شارژ نفری")

            return Response(
                {
                    "detail": (
                        "ثبت شارژ انجام نشد. "
                        "گزارش خطای سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش شارژ نفری
    # --------------------------------------------------
    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    PersonCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ اعلان ارسال شده "
                                "و امکان ویرایش وجود ندارد."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ پرداخت ثبت شده "
                                "و امکان ویرایش وجود ندارد."
                            ),
                            "code": "charge_already_paid",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                house = self.get_house(request)
                units = self.get_active_units(house)

                if not units.exists():
                    return Response(
                        {
                            "detail":
                                "هیچ واحد فعالی در ساختمان وجود ندارد."
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                data = request.data.copy()

                current_values = {
                    "name": charge.name or "",
                    "person_amount": charge.person_amount or 0,
                    "details": charge.details or "",
                    "payment_penalty_amount": (
                            charge.payment_penalty_amount or 0
                    ),
                    "other_cost_amount": (
                            charge.other_cost_amount or 0
                    ),
                }

                for field, value in current_values.items():
                    if field not in data:
                        data[field] = value

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        jalali_deadline = (
                            jdatetime.date.fromgregorian(
                                date=charge.payment_deadline
                            )
                        )
                        data["payment_deadline"] = (
                            jalali_deadline.strftime("%Y-%m-%d")
                        )

                data = self.normalize_api_deadline(data)

                form = PersonChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [
                                    str(error) for error in errors
                                ]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save(commit=False)
                charge.unit_count = units.count()
                charge.total_people = self.calculate_total_people(
                    units
                )
                charge.save()

                self.sync_unified_charges(
                    request=request,
                    charge=charge,
                    units=units,
                )

            return Response({
                "detail": "شارژ نفری با موفقیت ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception("خطا در ویرایش شارژ نفری")

            return Response(
                {
                    "detail":
                        "ویرایش شارژ انجام نشد. گزارش سرور را بررسی کنید."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف شارژ نفری
    # --------------------------------------------------
    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    PersonCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ اعلان ارسال شده "
                                "و امکان حذف وجود ندارد."
                            ),
                            "code": "charge_already_notified",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                if self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "برای این شارژ پرداخت ثبت شده "
                                "و امکان حذف وجود ندارد."
                            ),
                            "code": "charge_already_paid",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ نفری"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "به دلیل وابستگی‌های مالی، "
                        "حذف این شارژ امکان‌پذیر نیست."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception("خطا در حذف شارژ نفری")

            return Response(
                {
                    "detail":
                        "حذف شارژ انجام نشد. گزارش سرور را بررسی کنید."
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerPersonChargeUnitsAPIView(APIView):
    """
    GET /api/manager/charges/person/<pk>/units/
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = PersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            PersonCharge
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)

            renter = unit.renters.filter(
                renter_is_active=True
            ).first()

            people_count = int(unit.people_count or 0)

            base_amount = (
                    Decimal(people_count)
                    * Decimal(str(charge.person_amount or 0))
            )

            other_amount = Decimal(
                str(charge.other_cost_amount or 0)
            )

            calculated_total = base_amount + other_amount

            # سند موجود باشد، مبلغ ذخیره‌شده نمایش داده می‌شود.
            current_amount = (
                uc.total_charge_month
                if uc else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "people_count": people_count,
                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": (
                    "renter" if renter
                    else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),
                "is_notified": bool(
                    uc and uc.send_notification
                ),
                "send_sms": bool(
                    uc and uc.send_sms
                ),
                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date
                    else None
                ),
                "is_paid": bool(
                    uc and uc.is_paid
                ),
                "current_charge": str(current_amount),
                "financial_document_number": (
                    uc.financial_document_number if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name,
            "charge_type": "person",
            "person_amount": str(charge.person_amount or 0),
            "total_people": str(charge.total_people or 0),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "count": len(results),
            "results": results,
        })


class ManagerPersonChargeSendAPIView(APIView):
    """
    POST /api/manager/charges/person/<pk>/units/send/

    {
        "unit_ids": [1, 2, 3],
        "send_sms": true
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        charge = PersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail": (
                        "برخی واحدها نامعتبرند یا "
                        "به ساختمان شما تعلق ندارند."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            PersonCharge
        )

        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    base_amount, other_amount, total_amount = (
                        self._calculate_unit_amount(unit, charge)
                    )

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(
                            content_type=content_type,
                            object_id=charge.pk,
                            unit=unit,
                        )
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            content_type=content_type,
                            object_id=charge.pk,
                            charge_type="person",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ نفری",
                            payment_deadline_date=charge.payment_deadline,
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )
                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    # مبلغ سند پرداخت‌شده را تغییر نده.
                    if uc.is_paid:
                        notified_charges.append(uc)
                        continue

                    # مبالغ سند موجود را در زمان ارسال اعلان
                    # بازنویسی نمی‌کنیم.
                    uc.send_notification = True
                    uc.send_notification_date = timezone.now().date()
                    uc.save(
                        update_fields=[
                            "send_notification",
                            "send_notification_date",
                        ]
                    )

                    notified_charges.append(uc)

        except Exception:
            logger.exception("خطا در ثبت اعلان شارژ نفری")

            return Response(
                {
                    "detail": (
                        "ثبت اعلان انجام نشد. "
                        "گزارش خطای سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی شارژ نفری ثبت شد.",
            })

        sms_eligible_charges = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            from django.conf import settings

            unit_sms_price = Decimal(
                str(settings.SMS_PRICE)
            )

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = timezone.now().date()
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception("خطا در ارسال پیامک شارژ نفری")

            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان سیستمی ثبت شد، اما "
                    "ارسال پیامک با خطا مواجه شد."
                ),
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": (
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد."
            ),
        })

    def _calculate_unit_amount(self, unit, charge):
        people_count = int(unit.people_count or 0)

        if people_count < 0:
            raise ValueError(
                f"تعداد نفرات واحد {unit.pk} معتبر نیست."
            )

        base_amount = (
                Decimal(people_count)
                * Decimal(str(charge.person_amount or 0))
        )

        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        return base_amount, other_amount, base_amount + other_amount


class ManagerPersonChargeCancelAPIView(APIView):
    """
    POST /api/manager/charges/person/<pk>/units/cancel/

    {
        "unit_ids": [1, 2, 3]
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        charge = PersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not house or not charge:
            return Response(
                {"detail": "شارژ یا ساختمان پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            PersonCharge
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Fix Area Charge ========================
class ManagerFixAreaChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    # --------------------------------------------------
    # دسترسی مدیر
    # --------------------------------------------------

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return FixAreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_units(self, request):
        return Unit.objects.filter(
            myhouse=request.user.house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(FixAreaCharge)

    # --------------------------------------------------
    # اعلان و پرداخت
    # --------------------------------------------------

    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ واحد
    # --------------------------------------------------

    def calculate_unit_amount(self, unit, charge):
        area = getattr(unit, "area", None)

        if area is None:
            raise ValueError(
                f"متراژ واحد {unit.pk} مشخص نشده است."
            )

        fixed_amount = Decimal(
            str(charge.fix_charge_amount or 0)
        )

        area_amount = Decimal(
            str(charge.area_amount or 0)
        )

        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        area_total = Decimal(str(area)) * area_amount

        base_amount = fixed_amount + area_total
        total_amount = base_amount + other_amount

        return base_amount, other_amount, total_amount

    # --------------------------------------------------
    # محاسبه مجموع متراژ و تعداد واحد
    # --------------------------------------------------

    def update_charge_totals(self, charge, units):
        total_area = Decimal("0")
        unit_count = 0

        for unit in units.iterator():
            area = getattr(unit, "area", None)

            if area is None:
                raise ValueError(
                    f"متراژ واحد {unit.pk} مشخص نشده است."
                )

            total_area += Decimal(str(area))
            unit_count += 1

        charge.total_area = total_area

        # در صورت وجود این فیلد در مدل:
        if hasattr(charge, "unit_count"):
            charge.unit_count = unit_count

        charge.save()

    # --------------------------------------------------
    # همگام‌سازی اسناد مالی واحدها
    # --------------------------------------------------

    def sync_unified_charges(self, request, charge, units):
        content_type = self.get_content_type()

        for unit in units.iterator():
            base_amount, other_amount, total_amount = (
                self.calculate_unit_amount(unit, charge)
            )

            lookup = {
                "user": request.user,
                "unit": unit,
                "content_type": content_type,
                "object_id": charge.pk,
            }

            uc = (
                UnifiedCharge.objects.select_for_update()
                .filter(**lookup)
                .first()
            )

            if uc:
                # سند پرداخت‌شده یا اعلام‌شده تغییر نکند.
                if uc.is_paid or uc.send_notification:
                    continue

                uc.house = unit.myhouse
                uc.charge_type = "fix_area"
                uc.amount = base_amount
                uc.base_charge = total_amount
                uc.other_cost_amount = other_amount
                uc.penalty_percent = (
                        charge.payment_penalty_amount or 0
                )
                uc.penalty_amount = 0
                uc.total_charge_month = total_amount
                uc.details = charge.details or ""
                uc.title = charge.name or "شارژ ثابت و متراژی"
                uc.payment_deadline_date = charge.payment_deadline

                uc.save()

            else:
                UnifiedCharge.objects.create(
                    **lookup,
                    house=unit.myhouse,
                    bank=None,
                    charge_type="fix_area",
                    amount=base_amount,
                    base_charge=total_amount,
                    other_cost_amount=other_amount,
                    penalty_percent=(
                            charge.payment_penalty_amount or 0
                    ),
                    penalty_amount=0,
                    total_charge_month=total_amount,
                    details=charge.details or "",
                    title=charge.name or "شارژ ثابت و متراژی",
                    payment_deadline_date=charge.payment_deadline,
                    payment_token=secrets.token_urlsafe(12),
                    send_notification=False,
                )

    # --------------------------------------------------
    # خروجی API
    # --------------------------------------------------

    def serialize_charge(self, charge):
        related = UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "fix_area",
            "fix_charge_amount": str(
                charge.fix_charge_amount or 0
            ),
            "area_amount": str(charge.area_amount or 0),
            "total_area": str(charge.total_area or 0),
            "unit_count": related.values(
                "unit_id"
            ).distinct().count(),
            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "payment_penalty_amount": str(
                charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if getattr(charge, "created_at", None)
                else None
            ),
            "can_edit": not self.has_notification(charge)
                        and not self.has_payment(charge),
            "can_delete": not self.has_notification(charge)
                          and not self.has_payment(charge),
        }

    # --------------------------------------------------
    # GET: فهرست و جزئیات
    # --------------------------------------------------

    def get(self, request, pk=None):
        denied = self.check_manager(request)

        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = FixAreaCharge.objects.filter(
            user=request.user,
        ).order_by("-created_at")

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد
    # --------------------------------------------------

    def post(self, request, pk=None):
        denied = self.check_manager(request)

        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای ایجاد از مسیر بدون شناسه استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = self.get_units(request)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = FixAreaChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response(
                {
                    "detail": "شارژ ثابت و متراژی با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception(
                "خطا در ایجاد FixAreaCharge"
            )

            return Response(
                {"detail": "ثبت شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش
    # --------------------------------------------------

    def patch(self, request, pk=None):
        denied = self.check_manager(request)

        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixAreaCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge) or self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "ویرایش این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                data = request.data.copy()

                # مقادیر ارسال‌نشده در PATCH حفظ شوند.
                for field in (
                        "name",
                        "fix_charge_amount",
                        "area_amount",
                        "details",
                        "payment_penalty_amount",
                        "other_cost_amount",
                ):
                    if field not in data:
                        value = getattr(charge, field, None)
                        data[field] = "" if value is None else value

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        data["payment_deadline"] = (
                            charge.payment_deadline.strftime("%Y-%m-%d")
                        )

                form = FixAreaChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [str(error) for error in errors]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save(commit=False)
                units = self.get_units(request)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response({
                "detail": "شارژ ثابت و متراژی ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception(
                "خطا در ویرایش FixAreaCharge"
            )

            return Response(
                {"detail": "ویرایش شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف
    # --------------------------------------------------

    def delete(self, request, pk=None):
        denied = self.check_manager(request)

        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixAreaCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if self.has_notification(charge) or self.has_payment(charge):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "حذف این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ ثابت و متراژی"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {"detail": "به دلیل وابستگی‌های مالی، حذف شارژ ممکن نیست."},
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception(
                "خطا در حذف FixAreaCharge"
            )

            return Response(
                {"detail": "حذف شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixAreaChargeUnitsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixAreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            FixAreaCharge
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)

            renter = unit.renters.filter(
                renter_is_active=True
            ).first()

            area = getattr(unit, "area", None)

            fixed_amount = Decimal(
                str(charge.fix_charge_amount or 0)
            )

            area_amount = Decimal(
                str(charge.area_amount or 0)
            )

            other_amount = Decimal(
                str(charge.other_cost_amount or 0)
            )

            area_total = (
                    Decimal(str(area or 0)) * area_amount
            )

            calculated_total = (
                    fixed_amount + area_total + other_amount
            )

            current_amount = (
                uc.total_charge_month
                if uc else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(area if area is not None else ""),
                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": (
                    "renter" if renter else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),
                "is_notified": bool(
                    uc and uc.send_notification
                ),
                "send_sms": bool(
                    uc and uc.send_sms
                ),
                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date else None
                ),
                "is_paid": bool(uc and uc.is_paid),
                "current_charge": str(current_amount),
                "financial_document_number": (
                    uc.financial_document_number if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name,
            "charge_type": "fix_area",
            "fix_charge_amount": str(
                charge.fix_charge_amount or 0
            ),
            "area_amount": str(charge.area_amount or 0),
            "total_area": str(charge.total_area or 0),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "count": len(results),
            "results": results,
        })


class ManagerFixAreaChargeSendAPIView(APIView):
    """
    POST /api/manager/charges/fix-area/<pk>/units/send/

    {
        "unit_ids": [1, 2, 3],
        "send_sms": true
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixAreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail": (
                        "برخی واحدها نامعتبرند یا به ساختمان شما "
                        "تعلق ندارند."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixAreaCharge
        )

        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    area = getattr(unit, "area", None)

                    if area is None:
                        raise ValueError(
                            f"متراژ واحد {unit.pk} مشخص نشده است."
                        )

                    fixed_amount = Decimal(
                        str(charge.fix_charge_amount or 0)
                    )

                    area_amount = Decimal(
                        str(charge.area_amount or 0)
                    )

                    other_amount = Decimal(
                        str(charge.other_cost_amount or 0)
                    )

                    base_amount = (
                            fixed_amount
                            + Decimal(str(area)) * area_amount
                    )

                    total_amount = base_amount + other_amount

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(
                            user=request.user,
                            unit=unit,
                            content_type=content_type,
                            object_id=charge.pk,
                        )
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            content_type=content_type,
                            object_id=charge.pk,
                            charge_type="fix_area",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ ثابت و متراژی",
                            payment_deadline_date=charge.payment_deadline,
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    # پرداخت‌شده نباید دوباره مطالبه شود.
                    if uc.is_paid:
                        continue

                    # اعلان قبلی دوباره تاریخ‌گذاری نمی‌شود.
                    if not uc.send_notification:
                        uc.send_notification = True
                        uc.send_notification_date = (
                            timezone.now().date()
                        )

                        uc.save(
                            update_fields=[
                                "send_notification",
                                "send_notification_date",
                            ]
                        )

                    notified_charges.append(uc)

        except Exception:
            logger.exception(
                "خطا در ثبت اعلان FixAreaCharge"
            )

            return Response(
                {
                    "detail": (
                        "ثبت اعلان انجام نشد. "
                        "گزارش خطای سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی ثبت شد.",
            })

        sms_eligible_charges = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            from django.conf import settings

            unit_sms_price = Decimal(
                str(settings.SMS_PRICE)
            )

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = (
                        timezone.now().date()
                    )
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "خطا در ارسال پیامک FixAreaCharge"
            )

            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان سیستمی ثبت شد، اما ارسال پیامک "
                    "با خطا مواجه شد."
                ),
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": (
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد."
            ),
        })


class ManagerFixAreaChargeCancelAPIView(APIView):
    """
    POST /api/manager/charges/fix-area/<pk>/units/cancel/

    {
        "unit_ids": [1, 2, 3]
    }
    """

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixAreaCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixAreaCharge
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
                user=request.user,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Fix Person Charge ========================

class ManagerFixPersonChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return FixPersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_units(self, request):
        return Unit.objects.filter(
            myhouse=request.user.house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(FixPersonCharge)

    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ هر واحد
    # --------------------------------------------------
    def calculate_unit_amount(self, unit, charge):
        people = getattr(unit, "people_count", 0) or 0

        fixed_amount = Decimal(
            str(charge.fix_charge_amount or 0)
        )
        person_amount = Decimal(
            str(charge.person_amount or 0)
        )
        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        base_amount = (
                fixed_amount
                + Decimal(str(people)) * person_amount
        )

        total_amount = base_amount + other_amount

        return base_amount, other_amount, total_amount

    # --------------------------------------------------
    # به‌روزرسانی مجموع تعداد نفرات و واحدها
    # --------------------------------------------------
    def update_charge_totals(self, charge, units):
        total_people = 0
        unit_count = 0

        for unit in units.iterator():
            people = getattr(unit, "people_count", 0) or 0

            total_people += int(people)
            unit_count += 1

        charge.total_people = total_people
        charge.unit_count = unit_count
        charge.save()

    # --------------------------------------------------
    # همگام‌سازی اسناد مالی
    # --------------------------------------------------
    def sync_unified_charges(self, request, charge, units):
        content_type = self.get_content_type()

        for unit in units.iterator():
            base_amount, other_amount, total_amount = (
                self.calculate_unit_amount(unit, charge)
            )

            lookup = {
                "user": request.user,
                "unit": unit,
                "content_type": content_type,
                "object_id": charge.pk,
            }

            uc = (
                UnifiedCharge.objects.select_for_update()
                .filter(**lookup)
                .first()
            )

            values = {
                "house": unit.myhouse,
                "charge_type": "fix_person",
                "amount": base_amount,
                "base_charge": total_amount,
                "other_cost_amount": other_amount,
                "penalty_percent": (
                        charge.payment_penalty_amount or 0
                ),
                "penalty_amount": 0,
                "total_charge_month": total_amount,
                "details": charge.details or "",
                "title": charge.name or "شارژ ثابت و نفری",
                "payment_deadline_date": charge.payment_deadline,
            }

            if uc:
                if uc.is_paid or uc.send_notification:
                    continue

                for field, value in values.items():
                    setattr(uc, field, value)

                uc.save()
            else:
                UnifiedCharge.objects.create(
                    **lookup,
                    **values,
                    bank=None,
                    payment_token=secrets.token_urlsafe(12),
                    send_notification=False,
                )

    # --------------------------------------------------
    # خروجی شارژ
    # --------------------------------------------------
    def serialize_charge(self, charge):
        related = UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "fix_person",
            "fix_charge_amount": str(
                charge.fix_charge_amount or 0
            ),
            "person_amount": str(
                charge.person_amount or 0
            ),
            "total_people": charge.total_people or 0,
            "unit_count": related.values(
                "unit_id"
            ).distinct().count(),
            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "payment_penalty_amount": str(
                charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),
            "can_edit": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
            "can_delete": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
        }

    # --------------------------------------------------
    # GET
    # --------------------------------------------------
    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ نفری پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = FixPersonCharge.objects.filter(
            user=request.user
        ).order_by("-created_at")

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد
    # --------------------------------------------------
    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای ایجاد از مسیر بدون شناسه استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = self.get_units(request)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = FixPersonChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.save()

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response(
                {
                    "detail": "شارژ ثابت و نفری با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception("خطا در ایجاد FixPersonCharge")
            return Response(
                {"detail": "ثبت شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش
    # --------------------------------------------------
    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixPersonCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "ویرایش این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                data = request.data.copy()

                for field in (
                        "name",
                        "person_amount",
                        "fix_charge_amount",
                        "details",
                        "payment_penalty_amount",
                        "other_cost_amount",
                        "civil",
                ):
                    if field not in data:
                        value = getattr(charge, field, None)
                        data[field] = "" if value is None else value

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        data["payment_deadline"] = (
                            charge.payment_deadline.strftime("%Y-%m-%d")
                        )

                form = FixPersonChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [str(error) for error in errors]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save()
                units = self.get_units(request)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response({
                "detail": "شارژ ثابت و نفری ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception("خطا در ویرایش FixPersonCharge")
            return Response(
                {"detail": "ویرایش شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE
    # --------------------------------------------------
    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    FixPersonCharge.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "حذف این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ ثابت و نفری"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {"detail": "به دلیل وابستگی‌های مالی، حذف شارژ ممکن نیست."},
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception("خطا در حذف FixPersonCharge")
            return Response(
                {"detail": "حذف شارژ انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixPersonChargeUnitsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixPersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )
        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()
        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            FixPersonCharge
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)
            renter = unit.get_active_renter()
            people = int(unit.people_count or 0)

            fixed_amount = Decimal(
                str(charge.fix_charge_amount or 0)
            )
            person_amount = Decimal(
                str(charge.person_amount or 0)
            )
            other_amount = Decimal(
                str(charge.other_cost_amount or 0)
            )

            base_amount = (
                    fixed_amount
                    + Decimal(people) * person_amount
            )
            calculated_total = base_amount + other_amount

            current_amount = (
                uc.total_charge_month
                if uc else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(unit.area or 0),
                "people_count": people,
                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": (
                    "renter" if renter else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),
                "fix_charge_amount": str(fixed_amount),
                "person_amount": str(person_amount),
                "base_amount": str(base_amount),
                "other_cost_amount": str(other_amount),
                "calculated_total": str(calculated_total),
                "is_notified": bool(
                    uc and uc.send_notification
                ),
                "send_sms": bool(uc and uc.send_sms),
                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date else None
                ),
                "is_paid": bool(uc and uc.is_paid),
                "current_charge": str(current_amount),
                "financial_document_number": (
                    uc.financial_document_number if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name,
            "charge_type": "fix_person",
            "fix_charge_amount": str(
                charge.fix_charge_amount or 0
            ),
            "person_amount": str(charge.person_amount or 0),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "total_people": charge.total_people or 0,
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "count": len(results),
            "results": results,
        })


class ManagerFixPersonChargeSendAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixPersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}
            if any(value <= 0 for value in selected_ids):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)
        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {"detail": "برخی واحدها نامعتبرند یا به ساختمان شما تعلق ندارند."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixPersonCharge
        )
        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]
                    people = int(unit.people_count or 0)

                    fixed_amount = Decimal(
                        str(charge.fix_charge_amount or 0)
                    )
                    person_amount = Decimal(
                        str(charge.person_amount or 0)
                    )
                    other_amount = Decimal(
                        str(charge.other_cost_amount or 0)
                    )

                    base_amount = (
                            fixed_amount
                            + Decimal(people) * person_amount
                    )
                    total_amount = base_amount + other_amount

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(
                            user=request.user,
                            unit=unit,
                            content_type=content_type,
                            object_id=charge.pk,
                        )
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            content_type=content_type,
                            object_id=charge.pk,
                            charge_type="fix_person",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ ثابت و نفری",
                            payment_deadline_date=charge.payment_deadline,
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )
                        uc.save(
                            update_fields=["financial_document_number"]
                        )

                    if uc.is_paid:
                        continue

                    if not uc.send_notification:
                        uc.send_notification = True
                        uc.send_notification_date = timezone.now().date()
                        uc.save(
                            update_fields=[
                                "send_notification",
                                "send_notification_date",
                            ]
                        )

                    notified_charges.append(uc)

        except Exception:
            logger.exception("خطا در ثبت اعلان FixPersonCharge")
            return Response(
                {"detail": "ثبت اعلان انجام نشد. گزارش سرور را بررسی کنید."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی ثبت شد.",
            })

        sms_eligible_charges = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            unit_sms_price = Decimal(str(settings.SMS_PRICE))

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price)) / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = timezone.now().date()
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception("خطا در ارسال پیامک FixPersonCharge")
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": "اعلان ثبت شد، اما ارسال پیامک با خطا مواجه شد.",
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد.",
        })


class ManagerFixPersonChargeCancelAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = FixPersonCharge.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}
            if any(value <= 0 for value in selected_ids):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            FixPersonCharge
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
                user=request.user,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Area Person Charge ========================

class ManagerPersonAreaChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return ChargeByPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_units(self, request):
        return Unit.objects.filter(
            myhouse=request.user.house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(
            ChargeByPersonArea
        )

    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ هر واحد
    # --------------------------------------------------
    def calculate_unit_amount(self, unit, charge):
        area = Decimal(str(unit.area or 0))
        people = int(unit.people_count or 0)

        area_amount = Decimal(str(charge.area_amount or 0))
        person_amount = Decimal(str(charge.person_amount or 0))
        other_amount = Decimal(str(charge.other_cost_amount or 0))

        area_total = area * area_amount
        person_total = Decimal(people) * person_amount

        base_amount = area_total + person_total
        total_amount = base_amount + other_amount

        return base_amount, other_amount, total_amount

    # --------------------------------------------------
    # به‌روزرسانی مجموع متراژ، نفرات و واحدها
    # --------------------------------------------------
    def update_charge_totals(self, charge, units):
        total_area = Decimal("0")
        total_people = 0
        unit_count = 0

        for unit in units.iterator():
            total_area += Decimal(str(unit.area or 0))
            total_people += int(unit.people_count or 0)
            unit_count += 1

        charge.total_area = total_area
        charge.total_people = total_people
        charge.unit_count = unit_count

        charge.save(update_fields=[
            "total_area",
            "total_people",
            "unit_count",
        ])

    # --------------------------------------------------
    # همگام‌سازی اسناد مالی
    # --------------------------------------------------
    def sync_unified_charges(self, request, charge, units):
        content_type = self.get_content_type()

        for unit in units.iterator():
            base_amount, other_amount, total_amount = (
                self.calculate_unit_amount(unit, charge)
            )

            lookup = {
                "user": request.user,
                "unit": unit,
                "content_type": content_type,
                "object_id": charge.pk,
            }

            uc = (
                UnifiedCharge.objects.select_for_update()
                .filter(**lookup)
                .first()
            )

            values = {
                "house": unit.myhouse,
                "charge_type": "person_area",
                "amount": base_amount,
                "base_charge": total_amount,
                "other_cost_amount": other_amount,
                "penalty_percent": (
                        charge.payment_penalty_amount or 0
                ),
                "penalty_amount": 0,
                "total_charge_month": total_amount,
                "details": charge.details or "",
                "title": charge.name or "شارژ نفری متراژی",
                "payment_deadline_date": charge.payment_deadline,
            }

            if uc:
                # اسناد پرداخت‌شده یا اعلان‌شده تغییر نکنند.
                if uc.is_paid or uc.send_notification:
                    continue

                for field, value in values.items():
                    setattr(uc, field, value)

                uc.save()
            else:
                UnifiedCharge.objects.create(
                    **lookup,
                    **values,
                    bank=None,
                    payment_token=secrets.token_urlsafe(12),
                    send_notification=False,
                )

    # --------------------------------------------------
    # خروجی شارژ
    # --------------------------------------------------
    def serialize_charge(self, charge):
        related = UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "person_area",
            "area_amount": str(charge.area_amount or 0),
            "person_amount": str(charge.person_amount or 0),
            "total_area": str(charge.total_area or 0),
            "total_people": charge.total_people or 0,
            "unit_count": related.values(
                "unit_id"
            ).distinct().count(),
            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "civil": str(charge.civil or 0),
            "payment_penalty_amount": str(
                charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),
            "can_edit": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
            "can_delete": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
        }

    # --------------------------------------------------
    # GET: فهرست یا جزئیات
    # --------------------------------------------------
    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ نفری متراژی پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = ChargeByPersonArea.objects.filter(
            user=request.user
        ).order_by("-created_at")

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد شارژ
    # --------------------------------------------------
    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای ایجاد از مسیر بدون شناسه استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = self.get_units(request)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = PersonAreaChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.save()

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response(
                {
                    "detail": "شارژ نفری متراژی با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception(
                "خطا در ایجاد ChargeByPersonArea"
            )
            return Response(
                {
                    "detail": (
                        "ثبت شارژ انجام نشد. گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش شارژ
    # --------------------------------------------------
    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeByPersonArea.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "ویرایش این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                data = request.data.copy()

                for field in (
                        "name",
                        "area_amount",
                        "person_amount",
                        "details",
                        "payment_penalty_amount",
                        "other_cost_amount",
                        "civil",
                ):
                    if field not in data:
                        value = getattr(charge, field, None)
                        data[field] = (
                            "" if value is None else value
                        )

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        data["payment_deadline"] = (
                            charge.payment_deadline.strftime(
                                "%Y-%m-%d"
                            )
                        )

                form = PersonAreaChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [
                                    str(error)
                                    for error in errors
                                ]
                                for key, errors
                                in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save()
                units = self.get_units(request)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response({
                "detail": "شارژ نفری متراژی ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception(
                "خطا در ویرایش ChargeByPersonArea"
            )
            return Response(
                {
                    "detail": (
                        "ویرایش شارژ انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف شارژ
    # --------------------------------------------------
    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeByPersonArea.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ نفری متراژی پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "حذف این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = charge.name or "شارژ نفری متراژی"
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "به دلیل وابستگی‌های مالی، حذف شارژ ممکن نیست."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception(
                "خطا در حذف ChargeByPersonArea"
            )
            return Response(
                {
                    "detail": (
                        "حذف شارژ انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerPersonAreaChargeUnitsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ نفری متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )
        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()
        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            ChargeByPersonArea
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item for item in existing
        }

        area_amount = Decimal(str(charge.area_amount or 0))
        person_amount = Decimal(str(charge.person_amount or 0))
        other_amount = Decimal(str(charge.other_cost_amount or 0))

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)
            renter = unit.get_active_renter()
            people = int(unit.people_count or 0)
            area = Decimal(str(unit.area or 0))

            area_total = area * area_amount
            person_total = Decimal(people) * person_amount
            base_amount = area_total + person_total
            calculated_total = base_amount + other_amount

            current_amount = (
                uc.total_charge_month
                if uc else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(area),
                "people_count": people,
                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": (
                    "renter" if renter else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),
                "area_amount": str(area_amount),
                "person_amount": str(person_amount),
                "area_total": str(area_total),
                "person_total": str(person_total),
                "base_amount": str(base_amount),
                "other_cost_amount": str(other_amount),
                "calculated_total": str(calculated_total),
                "is_notified": bool(
                    uc and uc.send_notification
                ),
                "send_sms": bool(uc and uc.send_sms),
                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date else None
                ),
                "is_paid": bool(uc and uc.is_paid),
                "current_charge": str(current_amount),
                "financial_document_number": (
                    uc.financial_document_number if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name or "",
            "charge_type": "person_area",
            "area_amount": str(area_amount),
            "person_amount": str(person_amount),
            "other_cost_amount": str(other_amount),
            "total_area": str(charge.total_area or 0),
            "total_people": charge.total_people or 0,
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "count": len(results),
            "results": results,
        })


class ManagerPersonAreaChargeSendAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ نفری متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}
            if any(value <= 0 for value in selected_ids):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)
        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail": (
                        "برخی واحدها نامعتبرند یا به ساختمان "
                        "شما تعلق ندارند."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeByPersonArea
        )
        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]
                    people = int(unit.people_count or 0)
                    area = Decimal(str(unit.area or 0))

                    area_amount = Decimal(
                        str(charge.area_amount or 0)
                    )
                    person_amount = Decimal(
                        str(charge.person_amount or 0)
                    )
                    other_amount = Decimal(
                        str(charge.other_cost_amount or 0)
                    )

                    base_amount = (
                            area * area_amount
                            + Decimal(people) * person_amount
                    )
                    total_amount = base_amount + other_amount

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(
                            user=request.user,
                            unit=unit,
                            content_type=content_type,
                            object_id=charge.pk,
                        )
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            user=request.user,
                            unit=unit,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            content_type=content_type,
                            object_id=charge.pk,
                            charge_type="person_area",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ نفری متراژی",
                            payment_deadline_date=charge.payment_deadline,
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )
                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    if uc.is_paid:
                        continue

                    if not uc.send_notification:
                        uc.send_notification = True
                        uc.send_notification_date = (
                            timezone.now().date()
                        )
                        uc.save(update_fields=[
                            "send_notification",
                            "send_notification_date",
                        ])

                    notified_charges.append(uc)

        except Exception:
            logger.exception(
                "خطا در ثبت اعلان ChargeByPersonArea"
            )
            return Response(
                {
                    "detail": (
                        "ثبت اعلان انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی ثبت شد.",
            })

        sms_eligible_charges = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            unit_sms_price = Decimal(str(settings.SMS_PRICE))

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = (
                        timezone.now().date()
                    )
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "خطا در ارسال پیامک ChargeByPersonArea"
            )
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما ارسال پیامک با خطا مواجه شد."
                ),
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": (
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد."
            ),
        })


class ManagerPersonAreaChargeCancelAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)
        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ نفری متراژی پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])
        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}
            if any(value <= 0 for value in selected_ids):
                raise ValueError
        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeByPersonArea
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                user=request.user,
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Fix Area Person Charge ========================


class ManagerFixPersonAreaChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    # --------------------------------------------------
    # بررسی دسترسی مدیر
    # --------------------------------------------------
    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    # --------------------------------------------------
    # دریافت شارژ متعلق به مدیر جاری
    # --------------------------------------------------
    def get_charge(self, request, pk):
        return ChargeByFixPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    # --------------------------------------------------
    # دریافت واحدهای فعال ساختمان
    # --------------------------------------------------
    def get_units(self, request):
        return Unit.objects.filter(
            myhouse=request.user.house,
            is_active=True,
        ).distinct()

    # --------------------------------------------------
    # نوع محتوای سند مالی
    # --------------------------------------------------
    def get_content_type(self):
        return ContentType.objects.get_for_model(
            ChargeByFixPersonArea
        )

    # --------------------------------------------------
    # بررسی ارسال اعلان
    # --------------------------------------------------
    def has_notification(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            send_notification=True,
        ).exists()

    # --------------------------------------------------
    # بررسی وجود پرداخت
    # --------------------------------------------------
    def has_payment(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            is_paid=True,
        ).exists()

    # --------------------------------------------------
    # محاسبه مبلغ هر واحد
    # --------------------------------------------------
    def calculate_unit_amount(self, unit, charge):
        area = Decimal(str(unit.area or 0))
        people = int(unit.people_count or 0)

        fix_amount = Decimal(
            str(charge.fix_charge_amount or 0)
        )
        area_amount = Decimal(
            str(charge.area_amount or 0)
        )
        person_amount = Decimal(
            str(charge.person_amount or 0)
        )
        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        area_total = area * area_amount
        person_total = Decimal(people) * person_amount

        base_amount = (
                fix_amount
                + area_total
                + person_total
        )

        total_amount = base_amount + other_amount

        return {
            "fix_amount": fix_amount,
            "area_total": area_total,
            "person_total": person_total,
            "base_amount": base_amount,
            "other_amount": other_amount,
            "total_amount": total_amount,
        }

    # --------------------------------------------------
    # محاسبه مجموع متراژ، نفرات و تعداد واحدها
    # --------------------------------------------------
    def update_charge_totals(self, charge, units):
        total_area = Decimal("0")
        total_people = 0
        unit_count = 0

        for unit in units.iterator():
            total_area += Decimal(str(unit.area or 0))
            total_people += int(unit.people_count or 0)
            unit_count += 1

        charge.total_area = total_area
        charge.total_people = total_people
        charge.unit_count = unit_count

        charge.save(
            update_fields=[
                "total_area",
                "total_people",
                "unit_count",
            ]
        )

    # --------------------------------------------------
    # همگام‌سازی اسناد UnifiedCharge
    # --------------------------------------------------
    def sync_unified_charges(self, request, charge, units):
        content_type = self.get_content_type()

        for unit in units.iterator():
            amounts = self.calculate_unit_amount(unit, charge)

            lookup = {
                "user": request.user,
                "unit": unit,
                "content_type": content_type,
                "object_id": charge.pk,
            }

            uc = (
                UnifiedCharge.objects.select_for_update()
                .filter(**lookup)
                .first()
            )

            values = {
                "house": unit.myhouse,
                "charge_type": "fix_person_area",
                "amount": amounts["base_amount"],
                "base_charge": amounts["total_amount"],
                "other_cost_amount": amounts["other_amount"],
                "penalty_percent": (
                        charge.payment_penalty_amount or 0
                ),
                "penalty_amount": 0,
                "total_charge_month": amounts["total_amount"],
                "details": charge.details or "",
                "title": charge.name or "شارژ ثابت متراژی نفری",
                "payment_deadline_date": charge.payment_deadline,
            }

            if uc:
                # اسناد پرداخت‌شده یا اعلان‌شده تغییر نکنند.
                if uc.is_paid or uc.send_notification:
                    continue

                for field, value in values.items():
                    setattr(uc, field, value)

                uc.save()
            else:
                UnifiedCharge.objects.create(
                    **lookup,
                    **values,
                    bank=None,
                    payment_token=secrets.token_urlsafe(12),
                    send_notification=False,
                )

    # --------------------------------------------------
    # سریال‌سازی خروجی شارژ
    # --------------------------------------------------
    def serialize_charge(self, charge):
        related = UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
        )

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": "fix_person_area",

            "fix_charge_amount": str(
                charge.fix_charge_amount or 0
            ),
            "area_amount": str(
                charge.area_amount or 0
            ),
            "person_amount": str(
                charge.person_amount or 0
            ),

            "total_area": str(
                charge.total_area or 0
            ),
            "total_people": charge.total_people or 0,

            "unit_count": related.values(
                "unit_id"
            ).distinct().count(),

            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),

            "paid_units_count": related.filter(
                is_paid=True
            ).values("unit_id").distinct().count(),

            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "civil": str(charge.civil or 0),
            "payment_penalty_amount": str(
                charge.payment_penalty_amount or 0
            ),

            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),

            "details": charge.details or "",

            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),

            "can_edit": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
            "can_delete": (
                    not self.has_notification(charge)
                    and not self.has_payment(charge)
            ),
        }

    # --------------------------------------------------
    # GET: فهرست یا جزئیات
    # --------------------------------------------------
    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = ChargeByFixPersonArea.objects.filter(
            user=request.user,
        ).order_by("-created_at")

        results = [
            self.serialize_charge(charge)
            for charge in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: ایجاد شارژ
    # --------------------------------------------------
    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {"detail": "برای ایجاد شارژ از مسیر بدون شناسه استفاده کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = self.get_units(request)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = PersonAreaFixChargeForm(data=request.data)

        if not form.is_valid():
            return Response(
                {
                    "detail": "اطلاعات فرم معتبر نیست.",
                    "errors": {
                        key: [str(error) for error in errors]
                        for key, errors in form.errors.items()
                    },
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.save()

                self.update_charge_totals(charge, units)

                self.sync_unified_charges(
                    request,
                    charge,
                    units,
                )

            return Response(
                {
                    "detail": "شارژ ثابت متراژی نفری با موفقیت ثبت شد.",
                    "charge": self.serialize_charge(charge),
                },
                status=status.HTTP_201_CREATED,
            )

        except Exception:
            logger.exception(
                "خطا در ایجاد ChargeByFixPersonArea"
            )

            return Response(
                {
                    "detail": (
                        "ثبت شارژ انجام نشد. گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # PATCH: ویرایش شارژ
    # --------------------------------------------------
    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeByFixPersonArea.objects
                    .select_for_update()
                    .filter(
                        pk=pk,
                        user=request.user,
                    )
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "ویرایش این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                data = request.data.copy()

                for field in (
                        "name",
                        "fix_charge_amount",
                        "area_amount",
                        "person_amount",
                        "details",
                        "payment_penalty_amount",
                        "other_cost_amount",
                        "civil",
                ):
                    if field not in data:
                        value = getattr(charge, field, None)
                        data[field] = (
                            "" if value is None else value
                        )

                if "payment_deadline" not in data:
                    if charge.payment_deadline:
                        data["payment_deadline"] = (
                            charge.payment_deadline.strftime(
                                "%Y-%m-%d"
                            )
                        )

                form = PersonAreaFixChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response(
                        {
                            "detail": "اطلاعات فرم معتبر نیست.",
                            "errors": {
                                key: [
                                    str(error)
                                    for error in errors
                                ]
                                for key, errors in form.errors.items()
                            },
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                charge = form.save()

                units = self.get_units(request)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                self.update_charge_totals(charge, units)

                self.sync_unified_charges(
                    request,
                    charge,
                    units,
                )

            return Response({
                "detail": "شارژ ثابت متراژی نفری با موفقیت ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception(
                "خطا در ویرایش ChargeByFixPersonArea"
            )

            return Response(
                {
                    "detail": (
                        "ویرایش شارژ انجام نشد. گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    # --------------------------------------------------
    # DELETE: حذف شارژ
    # --------------------------------------------------
    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeByFixPersonArea.objects
                    .select_for_update()
                    .filter(
                        pk=pk,
                        user=request.user,
                    )
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "حذف این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                charge_name = (
                        charge.name or "شارژ ثابت متراژی نفری"
                )
                charge.delete()

            return Response({
                "detail": f"{charge_name} با موفقیت حذف شد."
            })

        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "به دلیل وابستگی‌های مالی، حذف شارژ ممکن نیست."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception(
                "خطا در حذف ChargeByFixPersonArea"
            )

            return Response(
                {
                    "detail": (
                        "حذف شارژ انجام نشد. گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixPersonAreaChargeUnitsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByFixPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get(
            "search", ""
        ).strip()

        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(
                status_residence="empty"
            )

        content_type = ContentType.objects.get_for_model(
            ChargeByFixPersonArea
        )

        existing = UnifiedCharge.objects.filter(
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item
            for item in existing
        }

        fix_amount = Decimal(
            str(charge.fix_charge_amount or 0)
        )
        area_amount = Decimal(
            str(charge.area_amount or 0)
        )
        person_amount = Decimal(
            str(charge.person_amount or 0)
        )
        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)
            renter = unit.get_active_renter()

            people = int(unit.people_count or 0)
            area = Decimal(str(unit.area or 0))

            area_total = area * area_amount
            person_total = Decimal(people) * person_amount

            base_amount = (
                    fix_amount
                    + area_total
                    + person_total
            )

            calculated_total = base_amount + other_amount

            current_amount = (
                uc.total_charge_month
                if uc else calculated_total
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(area),
                "people_count": people,

                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),

                "resident_type": (
                    "renter" if renter else (
                        "empty"
                        if unit.status_residence == "empty"
                        else "owner"
                    )
                ),

                "fix_charge_amount": str(fix_amount),
                "area_amount": str(area_amount),
                "person_amount": str(person_amount),

                "area_total": str(area_total),
                "person_total": str(person_total),
                "base_amount": str(base_amount),

                "other_cost_amount": str(other_amount),
                "calculated_total": str(calculated_total),

                "is_notified": bool(
                    uc and uc.send_notification
                ),

                "send_sms": bool(
                    uc and uc.send_sms
                ),

                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date else None
                ),

                "is_paid": bool(
                    uc and uc.is_paid
                ),

                "current_charge": str(current_amount),

                "financial_document_number": (
                    uc.financial_document_number
                    if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name or "",
            "charge_type": "fix_person_area",

            "fix_charge_amount": str(fix_amount),
            "area_amount": str(area_amount),
            "person_amount": str(person_amount),
            "other_cost_amount": str(other_amount),

            "total_area": str(charge.total_area or 0),
            "total_people": charge.total_people or 0,

            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),

            "count": len(results),
            "results": results,
        })


class ManagerFixPersonAreaChargeSendAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByFixPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {
                int(value) for value in raw_ids
            }

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {
            unit.pk: unit
            for unit in units
        }

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail": (
                        "برخی واحدها نامعتبرند یا به ساختمان "
                        "شما تعلق ندارند."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeByFixPersonArea
        )

        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    people = int(unit.people_count or 0)
                    area = Decimal(str(unit.area or 0))

                    fix_amount = Decimal(
                        str(charge.fix_charge_amount or 0)
                    )
                    area_amount = Decimal(
                        str(charge.area_amount or 0)
                    )
                    person_amount = Decimal(
                        str(charge.person_amount or 0)
                    )
                    other_amount = Decimal(
                        str(charge.other_cost_amount or 0)
                    )

                    base_amount = (
                            fix_amount
                            + area * area_amount
                            + Decimal(people) * person_amount
                    )

                    total_amount = (
                            base_amount + other_amount
                    )

                    lookup = {
                        "user": request.user,
                        "unit": unit,
                        "content_type": content_type,
                        "object_id": charge.pk,
                    }

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(**lookup)
                        .first()
                    )

                    if uc is None:
                        document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc = UnifiedCharge.objects.create(
                            **lookup,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=document_number,
                            charge_type="fix_person_area",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=(
                                    charge.name
                                    or "شارژ ثابت متراژی نفری"
                            ),
                            payment_deadline_date=(
                                charge.payment_deadline
                            ),
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )

                        uc.save(
                            update_fields=[
                                "financial_document_number"
                            ]
                        )

                    if uc.is_paid:
                        continue

                    if not uc.send_notification:
                        uc.send_notification = True
                        uc.send_notification_date = (
                            timezone.now().date()
                        )

                        uc.save(
                            update_fields=[
                                "send_notification",
                                "send_notification_date",
                            ]
                        )

                    notified_charges.append(uc)

        except Exception:
            logger.exception(
                "خطا در ثبت اعلان ChargeByFixPersonArea"
            )

            return Response(
                {
                    "detail": (
                        "ثبت اعلان انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی ثبت شد.",
            })

        sms_eligible_charges = [
            uc
            for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible_charges:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            unit_sms_price = Decimal(
                str(settings.SMS_PRICE)
            )

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )

                for sms_charge in sms_eligible_charges:
                    sms_charge.send_sms = True
                    sms_charge.send_sms_date = (
                        timezone.now().date()
                    )
                    sms_charge.sms_count = 1
                    sms_charge.sms_price = unit_sms_price
                    sms_charge.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible_charges,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible_charges,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "خطا در ارسال پیامک ChargeByFixPersonArea"
            )

            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما ارسال پیامک با خطا مواجه شد."
                ),
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + sms_result.message
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": (
                "اعلان سیستمی ثبت شد و پیامک با موفقیت ارسال شد."
            ),
        })


class ManagerFixPersonAreaChargeCancelAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeByFixPersonArea.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت متراژی نفری پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {
                int(value) for value in raw_ids
            }

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            )
            .values_list("id", flat=True)
            .distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeByFixPersonArea
        )

        with transaction.atomic():
            qs = UnifiedCharge.objects.select_for_update().filter(
                user=request.user,
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
            )

            cancelled_count = qs.filter(
                send_notification=True
            ).update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Fix Variable Charge ========================

class ManagerFixVariableChargeAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    CHARGE_TYPE = "fix_variable"

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        if not getattr(request.user, "house", None):
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return None

    def get_charge(self, request, pk):
        return ChargeFixVariable.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

    def get_units(self, request):
        return Unit.objects.filter(
            myhouse=request.user.house,
            is_active=True,
        ).distinct()

    def get_content_type(self):
        return ContentType.objects.get_for_model(
            ChargeFixVariable
        )

    def related_charges(self, charge):
        return UnifiedCharge.objects.filter(
            content_type=self.get_content_type(),
            object_id=charge.pk,
            user=charge.user,
        )

    def has_notification(self, charge):
        return self.related_charges(charge).filter(
            send_notification=True
        ).exists()

    def has_payment(self, charge):
        return self.related_charges(charge).filter(
            is_paid=True
        ).exists()

    def calculate_amounts(self, unit, charge):
        calculator = CALCULATORS["fix_variable"]

        # مبلغ پایه طبق Calculator مرکزی
        base_amount = Decimal(
            str(calculator.calculate(unit, charge) or 0)
        )

        # هزینه اضافی عمومی
        other_amount = Decimal(
            str(getattr(charge, "other_cost_amount", 0) or 0)
        )

        # مبلغ هر پارکینگ اضافه
        parking_rate = Decimal(
            str(getattr(charge, "extra_parking_amount", 0) or 0)
        )

        # تعداد پارکینگ اضافه متعلق به همین واحد
        parking_count = int(
            getattr(unit, "parking_counts", 0) or 0
        )

        # هزینه پارکینگ این واحد
        parking_total = parking_rate * parking_count

        # جمع نهایی
        total_amount = (
                base_amount
                + other_amount
                + parking_total
        )

        return {
            "base_amount": base_amount,
            "other_amount": other_amount,
            "parking_count": parking_count,
            "parking_rate": parking_rate,
            "parking_total": parking_total,
            "total_amount": total_amount,
        }

    def update_charge_totals(self, charge, units):
        total_area = Decimal("0")
        total_people = 0
        unit_count = 0

        for unit in units.iterator():
            total_area += Decimal(str(unit.area or 0))
            total_people += int(unit.people_count or 0)
            unit_count += 1

        charge.total_area = total_area
        charge.total_people = total_people
        charge.unit_count = unit_count

        charge.save(update_fields=[
            "total_area",
            "total_people",
            "unit_count",
        ])

    def sync_unified_charges(self, request, charge, units):
        """
        همگام‌سازی با استفاده از Calculator مرکزی.
        رکورد پرداخت‌شده یا اعلان‌شده تغییر نمی‌کند.
        """
        content_type = self.get_content_type()

        for unit in units.iterator():
            amounts = self.calculate_amounts(unit, charge)

            lookup = {
                "user": request.user,
                "unit": unit,
                "content_type": content_type,
                "object_id": charge.pk,
            }

            uc = (
                UnifiedCharge.objects.select_for_update()
                .filter(**lookup)
                .first()
            )

            values = {
                "house": unit.myhouse,
                "charge_type": "fix_variable",
                "amount": amounts["base_amount"],
                "base_charge": amounts["total_amount"],
                "other_cost_amount": (
                        amounts["other_amount"]
                        + amounts["parking_total"]
                ),
                "penalty_percent": charge.payment_penalty_amount or 0,
                "penalty_amount": 0,
                "total_charge_month": amounts["total_amount"],
                "details": charge.details or "",
                "title": charge.name or "شارژ ثابت و متغیر",
                "payment_deadline_date": charge.payment_deadline,
            }

            if uc:
                if uc.is_paid or uc.send_notification:
                    continue

                for field, value in values.items():
                    setattr(uc, field, value)

                uc.save()
            else:
                UnifiedCharge.objects.create(
                    **lookup,
                    **values,
                    bank=None,
                    payment_token=secrets.token_urlsafe(12),
                    send_notification=False,
                )

    def serialize_charge(self, charge):
        related = self.related_charges(charge)

        return {
            "id": charge.pk,
            "name": charge.name or "",
            "charge_type": self.CHARGE_TYPE,
            "unit_fix_amount": str(
                charge.unit_fix_amount or 0
            ),
            "unit_variable_person_amount": str(
                charge.unit_variable_person_amount or 0
            ),
            "unit_variable_area_amount": str(
                charge.unit_variable_area_amount or 0
            ),
            "extra_parking_amount": str(
                charge.extra_parking_amount or 0
            ),
            "total_area": str(charge.total_area or 0),
            "total_people": charge.total_people or 0,
            "unit_count": related.values(
                "unit_id"
            ).distinct().count(),
            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),
            "paid_units_count": related.filter(
                is_paid=True
            ).values("unit_id").distinct().count(),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "civil": str(charge.civil or 0),
            "payment_penalty_amount": str(
                charge.payment_penalty_amount or 0
            ),
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),
            "details": charge.details or "",
            "created_at": (
                charge.created_at.isoformat()
                if charge.created_at else None
            ),
            "can_edit": not (
                    self.has_notification(charge)
                    or self.has_payment(charge)
            ),
            "can_delete": not (
                    self.has_notification(charge)
                    or self.has_payment(charge)
            ),
        }

    def get(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            charge = self.get_charge(request, pk)

            if not charge:
                return Response(
                    {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                    status=status.HTTP_404_NOT_FOUND,
                )

            return Response(self.serialize_charge(charge))

        charges = ChargeFixVariable.objects.filter(
            user=request.user
        ).order_by("-created_at")

        results = [
            self.serialize_charge(item)
            for item in charges
        ]

        return Response({
            "count": len(results),
            "results": results,
        })

    def post(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is not None:
            return Response(
                {
                    "detail": (
                        "برای ایجاد شارژ از مسیر بدون شناسه "
                        "استفاده کنید."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = self.get_units(request)

        if not units.exists():
            return Response(
                {"detail": "هیچ واحد فعالی در ساختمان وجود ندارد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        form = VariableFixChargeForm(data=request.data)

        if not form.is_valid():
            return Response({
                "detail": "اطلاعات فرم معتبر نیست.",
                "errors": {
                    key: [str(error) for error in errors]
                    for key, errors in form.errors.items()
                },
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                charge = form.save(commit=False)
                charge.user = request.user
                charge.save()

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response({
                "detail": "شارژ ثابت و متغیر با موفقیت ثبت شد.",
                "charge": self.serialize_charge(charge),
            }, status=status.HTTP_201_CREATED)

        except Exception:
            logger.exception("خطا در ایجاد ChargeFixVariable")
            return Response(
                {
                    "detail": (
                        "ثبت شارژ انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def patch(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeFixVariable.objects.select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response({
                        "detail": (
                            "به دلیل ارسال اعلان یا ثبت پرداخت، "
                            "ویرایش این شارژ امکان‌پذیر نیست."
                        ),
                        "code": "charge_locked",
                    }, status=status.HTTP_409_CONFLICT)

                units = self.get_units(request)

                if not units.exists():
                    return Response(
                        {"detail": "هیچ واحد فعالی وجود ندارد."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                data = request.data.copy()

                optional_defaults = {
                    "name": charge.name or "",
                    "unit_fix_amount": charge.unit_fix_amount or 0,
                    "unit_variable_person_amount": (
                            charge.unit_variable_person_amount or 0
                    ),
                    "unit_variable_area_amount": (
                            charge.unit_variable_area_amount or 0
                    ),
                    "extra_parking_amount": (
                            charge.extra_parking_amount or 0
                    ),
                    "details": charge.details or "",
                    "payment_penalty_amount": (
                            charge.payment_penalty_amount or 0
                    ),
                    "other_cost_amount": (
                            charge.other_cost_amount or 0
                    ),
                    "civil": charge.civil or 0,
                }

                for field, default in optional_defaults.items():
                    if field not in data:
                        data[field] = default

                if (
                        "payment_deadline" not in data
                        and charge.payment_deadline
                ):
                    data["payment_deadline"] = (
                        charge.payment_deadline.strftime("%Y-%m-%d")
                    )

                form = VariableFixChargeForm(
                    data=data,
                    instance=charge,
                )

                if not form.is_valid():
                    return Response({
                        "detail": "اطلاعات فرم معتبر نیست.",
                        "errors": {
                            key: [str(error) for error in errors]
                            for key, errors in form.errors.items()
                        },
                    }, status=status.HTTP_400_BAD_REQUEST)

                charge = form.save()

                self.update_charge_totals(charge, units)
                self.sync_unified_charges(
                    request, charge, units
                )

            return Response({
                "detail": "شارژ ثابت و متغیر با موفقیت ویرایش شد.",
                "charge": self.serialize_charge(charge),
            })

        except Exception:
            logger.exception("خطا در ویرایش ChargeFixVariable")
            return Response(
                {
                    "detail": (
                        "ویرایش شارژ انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

    def delete(self, request, pk=None):
        denied = self.check_manager(request)
        if denied:
            return denied

        if pk is None:
            return Response(
                {"detail": "شناسه شارژ ارسال نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                charge = (
                    ChargeFixVariable.objects
                    .select_for_update()
                    .filter(pk=pk, user=request.user)
                    .first()
                )

                if not charge:
                    return Response(
                        {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                        status=status.HTTP_404_NOT_FOUND,
                    )

                # جلوگیری از حذف در صورت اعلان یا پرداخت
                if (
                        self.has_notification(charge)
                        or self.has_payment(charge)
                ):
                    return Response(
                        {
                            "detail": (
                                "به دلیل ارسال اعلان یا ثبت پرداخت، "
                                "حذف این شارژ امکان‌پذیر نیست."
                            ),
                            "code": "charge_locked",
                        },
                        status=status.HTTP_409_CONFLICT,
                    )

                name = charge.name or "شارژ ثابت و متغیر"

                # پیدا کردن رکوردهای مالی مرتبط با همین شارژ
                content_type = ContentType.objects.get_for_model(
                    ChargeFixVariable
                )

                unified_charges = UnifiedCharge.objects.filter(
                    content_type=content_type,
                    object_id=charge.pk,
                )

                # حذف رکوردهای مالی مرتبط
                unified_charges.delete()

                # حذف خود شارژ
                charge.delete()

            return Response({
                "detail": (
                    f"{name} و رکوردهای مالی مرتبط با آن "
                    "با موفقیت حذف شدند."
                )
            })

        except ProtectedError:
            return Response(
                {
                    "detail": (
                        "به دلیل وابستگی‌های مالی، "
                        "حذف شارژ ممکن نیست."
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        except Exception:
            logger.exception("خطا در حذف ChargeFixVariable")
            return Response(
                {
                    "detail": (
                        "حذف شارژ انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ManagerFixVariableChargeUnitsAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeFixVariable.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
        ).distinct()

        search = request.query_params.get("search", "").strip()
        resident_type = request.query_params.get(
            "resident_type", "all"
        ).strip()

        if search:
            units = units.filter(
                Q(unit__icontains=search)
                | Q(owner_name__icontains=search)
                | Q(renters__renter_name__icontains=search)
            ).distinct()

        if resident_type == "owner":
            units = units.exclude(
                renters__renter_is_active=True
            )

        elif resident_type == "renter":
            units = units.filter(
                renters__renter_is_active=True
            ).distinct()

        elif resident_type == "empty":
            units = units.filter(status_residence="empty")

        content_type = ContentType.objects.get_for_model(
            ChargeFixVariable
        )

        existing = UnifiedCharge.objects.filter(
            user=request.user,
            content_type=content_type,
            object_id=charge.pk,
            unit_id__in=units.values("id"),
        ).select_related("unit")

        charge_by_unit = {
            item.unit_id: item
            for item in existing
        }

        # استفاده از Calculator مرکزی
        calculator = CALCULATORS["fix_variable"]

        fixed_amount = Decimal(
            str(charge.unit_fix_amount or 0)
        )
        person_rate = Decimal(
            str(charge.unit_variable_person_amount or 0)
        )
        area_rate = Decimal(
            str(charge.unit_variable_area_amount or 0)
        )
        parking_amount = Decimal(
            str(charge.extra_parking_amount or 0)
        )
        other_amount = Decimal(
            str(charge.other_cost_amount or 0)
        )

        results = []

        for unit in units.order_by("unit"):
            uc = charge_by_unit.get(unit.pk)
            renter = unit.get_active_renter()

            area = Decimal(str(unit.area or 0))
            people = int(unit.people_count or 0)

            # مبلغ پایه از Calculator
            base_amount = Decimal(
                str(calculator.calculate(unit, charge) or 0)
            )

            # هزینه عمومی
            other_amount = Decimal(
                str(charge.other_cost_amount or 0)
            )

            # پارکینگ اختصاصی همین واحد
            parking_count = int(unit.parking_counts or 0)

            parking_total = (
                    parking_amount * parking_count
            )

            person_total = person_rate * people
            area_total = area_rate * area

            # مبلغ نهایی با احتساب پارکینگ
            calculated_total = (
                    base_amount
                    + other_amount
                    + parking_total
            )

            if renter:
                current_resident_type = "renter"
            elif unit.status_residence == "empty":
                current_resident_type = "empty"
            else:
                current_resident_type = "owner"

            print(
                "PAYMENT DEADLINE:",
                charge.payment_deadline
            )

            results.append({
                "id": unit.pk,
                "unit": str(unit.unit),
                "area": str(area),
                "people_count": people,
                "parking_counts": parking_count,

                "owner_name": unit.owner_name or "",
                "renter_name": (
                    renter.renter_name if renter else ""
                ),
                "resident_type": current_resident_type,

                "unit_fix_amount": str(fixed_amount),
                "unit_variable_person_amount": str(person_rate),
                "unit_variable_area_amount": str(area_rate),

                "person_total": str(person_total),
                "area_total": str(area_total),

                # نرخ هر پارکینگ و مبلغ پارکینگ این واحد
                "extra_parking_amount": str(parking_amount),
                "parking_total": str(parking_total),

                "base_amount": str(base_amount),
                "other_cost_amount": str(other_amount),
                "calculated_total": str(calculated_total),

                "is_notified": bool(uc and uc.send_notification),
                "send_sms": bool(uc and uc.send_sms),
                "send_sms_date": (
                    uc.send_sms_date.isoformat()
                    if uc and uc.send_sms_date
                    else None
                ),
                "is_paid": bool(uc and uc.is_paid),

                "current_charge": str(
                    uc.total_charge_month if uc else calculated_total
                ),

                "financial_document_number": (
                    uc.financial_document_number if uc else None
                ),
            })

        return Response({
            "charge_id": charge.pk,
            "charge_name": charge.name or "",
            "charge_type": "fix_variable",
            "unit_fix_amount": str(
                charge.unit_fix_amount or 0
            ),
            "unit_variable_person_amount": str(
                charge.unit_variable_person_amount or 0
            ),
            "unit_variable_area_amount": str(
                charge.unit_variable_area_amount or 0
            ),
            "extra_parking_amount": str(
                charge.extra_parking_amount or 0
            ),
            "other_cost_amount": str(
                charge.other_cost_amount or 0
            ),
            "total_area": str(charge.total_area or 0),
            "total_people": charge.total_people or 0,
            "payment_deadline": (
                charge.payment_deadline.isoformat()
                if charge.payment_deadline else None
            ),

            "count": len(results),
            "results": results,

        })


class ManagerFixVariableChargeSendAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeFixVariable.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "حداقل یک واحد را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        send_sms = request.data.get("send_sms", False)

        if not isinstance(send_sms, bool):
            return Response(
                {"detail": "مقدار send_sms باید بولی باشد."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = Unit.objects.filter(
            myhouse=house,
            is_active=True,
            id__in=selected_ids,
        ).distinct()

        units_by_id = {unit.pk: unit for unit in units}

        if set(units_by_id) != selected_ids:
            return Response(
                {
                    "detail": (
                        "برخی واحدها نامعتبرند یا متعلق "
                        "به ساختمان شما نیستند."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeFixVariable
        )

        calculator = CALCULATORS["fix_variable"]
        notified_charges = []

        try:
            with transaction.atomic():
                for unit_id in sorted(selected_ids):
                    unit = units_by_id[unit_id]

                    # مبلغ پایه از Calculator مرکزی
                    base_amount = Decimal(
                        str(calculator.calculate(unit, charge) or 0)
                    )

                    other_amount = Decimal(
                        str(
                            getattr(
                                charge,
                                "other_cost_amount",
                                0,
                            ) or 0
                        )
                    )

                    total_amount = base_amount + other_amount

                    lookup = {
                        "user": request.user,
                        "unit": unit,
                        "content_type": content_type,
                        "object_id": charge.pk,
                    }

                    uc = (
                        UnifiedCharge.objects.select_for_update()
                        .filter(**lookup)
                        .first()
                    )

                    if uc is None:
                        uc = UnifiedCharge.objects.create(
                            **lookup,
                            house=unit.myhouse,
                            bank=None,
                            financial_document_number=(
                                get_next_financial_document_number(
                                    unit.myhouse
                                )
                            ),
                            charge_type="fix_variable",
                            amount=base_amount,
                            base_charge=total_amount,
                            other_cost_amount=other_amount,
                            penalty_percent=(
                                    charge.payment_penalty_amount or 0
                            ),
                            penalty_amount=0,
                            total_charge_month=total_amount,
                            details=charge.details or "",
                            title=charge.name or "شارژ ثابت و متغیر",
                            payment_deadline_date=(
                                charge.payment_deadline
                            ),
                            payment_token=secrets.token_urlsafe(12),
                            send_notification=False,
                        )

                    elif not uc.financial_document_number:
                        uc.financial_document_number = (
                            get_next_financial_document_number(
                                unit.myhouse
                            )
                        )
                        uc.save(
                            update_fields=["financial_document_number"]
                        )

                    # واحد پرداخت‌شده اعلان جدید دریافت نمی‌کند
                    if uc.is_paid:
                        continue

                    if not uc.send_notification:
                        uc.send_notification = True
                        uc.send_notification_date = (
                            timezone.now().date()
                        )
                        uc.save(update_fields=[
                            "send_notification",
                            "send_notification_date",
                        ])

                    notified_charges.append(uc)

        except Exception:
            logger.exception(
                "خطا در ثبت اعلان ChargeFixVariable"
            )
            return Response(
                {
                    "detail": (
                        "ثبت اعلان انجام نشد. "
                        "گزارش سرور را بررسی کنید."
                    )
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        if not send_sms:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": False,
                "sms_sent": False,
                "detail": "اعلان سیستمی ثبت شد.",
            })

        sms_eligible = [
            uc for uc in notified_charges
            if normalize_mobile(uc.get_mobile())
        ]

        if not sms_eligible:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما شماره موبایل معتبری "
                    "برای پیامک وجود ندارد."
                ),
            })

        try:
            unit_sms_price = Decimal(str(settings.SMS_PRICE))

            def save_sms_metadata(total_sms, total_price):
                if total_sms <= 0:
                    return

                per_charge_price = (
                        Decimal(str(total_price))
                        / Decimal(total_sms)
                )
                sent_date = timezone.now().date()

                for item in sms_eligible:
                    item.send_sms = True
                    item.send_sms_date = sent_date
                    item.sms_count = 1
                    item.sms_price = unit_sms_price
                    item.sms_total_price = per_charge_price

                UnifiedCharge.objects.bulk_update(
                    sms_eligible,
                    [
                        "send_sms",
                        "send_sms_date",
                        "sms_count",
                        "sms_price",
                        "sms_total_price",
                    ],
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_eligible,
                meta_callback=save_sms_metadata,
            )

        except Exception:
            logger.exception(
                "خطا در ارسال پیامک ChargeFixVariable"
            )
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                    "اعلان ثبت شد، اما ارسال پیامک "
                    "با خطا مواجه شد."
                ),
            })

        if not sms_result.success:
            return Response({
                "ok": True,
                "sent_count": len(notified_charges),
                "sms_requested": True,
                "sms_sent": False,
                "sms_sent_count": 0,
                "detail": (
                        "اعلان ثبت شد، اما ارسال پیامک موفق نبود: "
                        + str(sms_result.message)
                ),
            })

        return Response({
            "ok": True,
            "sent_count": len(notified_charges),
            "sms_requested": True,
            "sms_sent": True,
            "sms_sent_count": sms_result.total_sms,
            "sms_total_price": str(sms_result.total_price),
            "detail": (
                "اعلان سیستمی ثبت شد و پیامک "
                "با موفقیت ارسال شد."
            ),
        })


class ManagerFixVariableChargeCancelAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        if not getattr(request.user, "is_middle_admin", False):
            return Response(
                {"detail": "شما اجازه مدیریت شارژها را ندارید."},
                status=status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return Response(
                {"detail": "ساختمان مدیر مشخص نشده است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        charge = ChargeFixVariable.objects.filter(
            pk=pk,
            user=request.user,
        ).first()

        if not charge:
            return Response(
                {"detail": "شارژ ثابت و متغیر پیدا نشد."},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_ids = request.data.get("unit_ids", [])

        if not isinstance(raw_ids, list) or not raw_ids:
            return Response(
                {"detail": "واحدهای موردنظر را انتخاب کنید."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            selected_ids = {int(value) for value in raw_ids}

            if any(value <= 0 for value in selected_ids):
                raise ValueError

        except (TypeError, ValueError):
            return Response(
                {"detail": "شناسه واحدها معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=house,
                is_active=True,
                id__in=selected_ids,
            ).values_list("id", flat=True).distinct()
        )

        if valid_ids != selected_ids:
            return Response(
                {"detail": "یک یا چند واحد معتبر نیست."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        content_type = ContentType.objects.get_for_model(
            ChargeFixVariable
        )

        with transaction.atomic():
            queryset = UnifiedCharge.objects.select_for_update().filter(
                user=request.user,
                content_type=content_type,
                object_id=charge.pk,
                unit_id__in=selected_ids,
                is_paid=False,
                send_notification=True,
            )

            cancelled_count = queryset.update(
                send_notification=False,
                send_notification_date=None,
            )

        return Response({
            "ok": True,
            "cancelled_count": cancelled_count,
            "detail": "اعلان سیستمی واحدهای انتخاب‌شده لغو شد.",
        })


# ============== Expense Charge ========================

VALID_BASES = {"equal", "area", "person"}
VALID_SCOPES = {"all", "occupied", "vacant", "selected"}


def api_error(message, code=status.HTTP_400_BAD_REQUEST, **extra):
    data = {
        "success": False,
        "message": message,
    }
    data.update(extra)

    return Response(data, status=code)


def decimal_value(value):
    try:
        if value is None or value == "":
            return Decimal("0")

        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def money_round(value):
    return int(
        decimal_value(value).quantize(
            Decimal("1"),
            rounding=ROUND_HALF_UP,
        )
    )


def charge_people_count(unit):
    active_renters = getattr(
        unit,
        "active_renters_for_charge",
        None,
    )

    if active_renters is None:
        active_renters = [
            renter
            for renter in unit.renters.all()
            if getattr(
                renter,
                "renter_is_active",
                False,
            )
        ]

    if active_renters:
        return sum(
            max(
                int(
                    getattr(
                        renter,
                        "renter_people_count",
                        0,
                    ) or 0
                ),
                0,
            )
            for renter in active_renters
        )

    if str(
            getattr(unit, "status_residence", "") or ""
    ).strip().lower() == "occupied":
        return max(
            int(
                getattr(
                    unit,
                    "owner_people_count",
                    0,
                ) or 0
            ),
            0,
        )

    return 0


def charge_area_value(unit):
    return decimal_value(getattr(unit, "area", 0))


def charge_is_occupied(unit):
    return getattr(unit, "status_residence", None) == "occupied"


def get_item_participating_units(item, all_units):
    """
    تعیین واحدهای شرکت‌کننده بر اساس محدوده تسهیم هر آیتم.
    """
    if item.allocation_scope == "occupied":
        return [
            unit for unit in all_units
            if charge_is_occupied(unit)
        ]

    if item.allocation_scope == "vacant":
        return [
            unit for unit in all_units
            if not charge_is_occupied(unit)
        ]

    if item.allocation_scope == "selected":
        selected_ids = set(
            item.selected_units.values_list("id", flat=True)
        )

        return [
            unit for unit in all_units
            if unit.id in selected_ids
        ]

    return list(all_units)


def calculate_charge_item_allocations(items, all_units):
    """
    محاسبه سهم هر آیتم برای هر واحد.

    خروجی:
      item_allocations:
          {item_id: {unit_id: Decimal}}

      totals:
          {unit_id: Decimal}

      participating_unit_ids:
          مجموعه واحدهایی که در حداقل یک آیتم شرکت دارند.
    """
    item_allocations = {}
    totals = {
        unit.id: Decimal("0")
        for unit in all_units
    }
    participating_unit_ids = set()

    for item in items:
        participating_units = get_item_participating_units(
            item,
            all_units,
        )

        if not participating_units:
            item_allocations[item.id] = {}
            continue

        amount = decimal_value(item.amount)

        if item.allocation_basis == "area":
            denominator = sum(
                (
                    charge_area_value(unit)
                    for unit in participating_units
                ),
                Decimal("0"),
            )

            if denominator > 0:
                allocations = {
                    unit.id: (
                            amount
                            * charge_area_value(unit)
                            / denominator
                    )
                    for unit in participating_units
                }
            else:
                share = amount / Decimal(len(participating_units))

                allocations = {
                    unit.id: share
                    for unit in participating_units
                }

        elif item.allocation_basis == "person":
            denominator = sum(
                charge_people_count(unit)
                for unit in participating_units
            )

            if denominator > 0:
                allocations = {
                    unit.id: (
                            amount
                            * Decimal(charge_people_count(unit))
                            / Decimal(denominator)
                    )
                    for unit in participating_units
                }
            else:
                share = amount / Decimal(len(participating_units))

                allocations = {
                    unit.id: share
                    for unit in participating_units
                }

        else:
            share = amount / Decimal(len(participating_units))

            allocations = {
                unit.id: share
                for unit in participating_units
            }

        item_allocations[item.id] = allocations

        for unit_id, share in allocations.items():
            participating_unit_ids.add(unit_id)
            totals[unit_id] += share

    return item_allocations, totals, participating_unit_ids


def get_calculation_content_type():
    return ContentType.objects.get_for_model(ChargeCalculation)


def get_calculation_charges(calculation, lock=False):
    """
    تمام رکوردهای شارژ مربوط به یک محاسبه را برمی‌گرداند.
    """
    queryset = UnifiedCharge.objects.filter(
        house=calculation.house,
        content_type=get_calculation_content_type(),
        object_id=calculation.pk,
    )

    if lock:
        queryset = queryset.select_for_update()

    return queryset.order_by("id")


def find_duplicate_charge_units(charges):
    counts = {}

    for charge in charges:
        counts[charge.unit_id] = counts.get(charge.unit_id, 0) + 1

    return sorted(
        unit_id
        for unit_id, count in counts.items()
        if count > 1
    )


class ManagerChargeCalculationBaseAPIView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def check_manager(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, api_error(
                "فقط مدیر ساختمان مجاز به انجام این عملیات است.",
                status.HTTP_403_FORBIDDEN,
            )

        house = getattr(request.user, "house", None)

        if not house:
            return None, api_error(
                "ساختمان مدیر مشخص نیست."
            )

        return house, None

    def get_calculation(self, request, pk):
        house, error = self.check_manager(request)

        if error:
            return None, error

        calculation = ChargeCalculation.objects.filter(
            pk=pk,
            house=house,
        ).first()

        if calculation is None:
            return None, api_error(
                "محاسبه شارژ پیدا نشد.",
                status.HTTP_404_NOT_FOUND,
            )

        return calculation, None

    @staticmethod
    def _serialize_date(value):
        if value is None or value == "":
            return None

        if hasattr(value, "isoformat"):
            return value.isoformat()

        value = str(value).strip()

        return value or None

    def serialize_calculation(self, obj):
        related = get_calculation_charges(obj)

        active_unit_count = Unit.objects.filter(
            myhouse=obj.house,
            is_active=True,
        ).count()

        return {
            "id": obj.id,
            "name": obj.name,

            "start_date": self._serialize_date(obj.start_date),
            "end_date": self._serialize_date(obj.end_date),

            "unit_count": obj.unit_count or 0,
            "total_unit_count": active_unit_count,

            "created_units_count": related.values(
                "unit_id"
            ).distinct().count(),

            "notified_units_count": related.filter(
                send_notification=True
            ).values("unit_id").distinct().count(),

            "sms_sent_units_count": related.filter(
                send_sms=True
            ).values("unit_id").distinct().count(),

            "paid_units_count": related.filter(
                is_paid=True
            ).values("unit_id").distinct().count(),

            "other_cost_amount": obj.other_cost_amount or 0,

            "payment_deadline": self._serialize_date(
                obj.payment_deadline
            ),

            "payment_penalty_amount": (
                    obj.payment_penalty_amount or 0
            ),

            "details": obj.details or "",
            "status": obj.status,
            "is_finalized": bool(obj.is_finalized),

            "created_at": self._serialize_date(obj.created_at),

            "can_edit": obj.can_edit(),
            "can_finalize": obj.can_finalize(),
        }

    def ensure_editable(self, calculation):

        is_notified = UnifiedCharge.objects.filter(
            object_id=calculation.pk,
            content_type=ContentType.objects.get_for_model(calculation),
            send_notification=True,
        ).exists()

        if is_notified:
            return api_error(
                "شارژ اعلان شده و قابل ویرایش نیست.",
                status.HTTP_409_CONFLICT,
            )

        return None

    def ensure_no_protected_charges(self, calculation):
        """
        در صورت وجود شارژ پرداخت‌شده یا اعلان‌شده،
        محاسبه مجدد ممنوع است.
        """
        charges = list(
            get_calculation_charges(
                calculation,
                lock=True,
            )
        )

        duplicates = find_duplicate_charge_units(charges)

        if duplicates:
            return api_error(
                "برای بعضی واحدها رکورد شارژ تکراری وجود دارد؛ "
                "ابتدا باید سوابق مالی بررسی شوند.",
                status.HTTP_409_CONFLICT,
                duplicate_unit_ids=duplicates,
            )

        protected_ids = sorted({
            charge.unit_id
            for charge in charges
            if charge.is_paid or charge.send_notification
        })

        if protected_ids:
            return api_error(
                "برای این محاسبه شارژ پرداخت‌شده یا اعلان‌شده وجود دارد؛ "
                "محاسبه مجدد برای جلوگیری از تغییر سوابق مالی مجاز نیست.",
                status.HTTP_409_CONFLICT,
                protected_unit_ids=protected_ids,
            )

        return None


class ManagerChargeCalculationAPIView(
    ManagerChargeCalculationBaseAPIView
):

    def get(self, request, pk=None):
        house, error = self.check_manager(request)

        if error:
            return error

        if pk is not None:
            calculation, error = self.get_calculation(
                request,
                pk,
            )

            if error:
                return error

            return Response({
                "success": True,
                "result": self.serialize_calculation(calculation),
            })

        queryset = ChargeCalculation.objects.filter(
            house=house,
        ).order_by("-created_at", "-id")

        return Response({
            "success": True,
            "count": queryset.count(),
            "results": [
                self.serialize_calculation(obj)
                for obj in queryset
            ],
        })

    def post(self, request):
        house, error = self.check_manager(request)

        if error:
            return error

        data = request.data

        name = str(data.get("name") or "").strip()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        payment_deadline = data.get("payment_deadline")

        if not name:
            return api_error("عنوان شارژ الزامی است.")

        if not start_date or not end_date:
            return api_error(
                "تاریخ شروع و پایان الزامی است."
            )

        if not payment_deadline or not str(payment_deadline).strip():
            return api_error("مهلت پرداخت الزامی است.")

        try:
            other_cost = int(data.get("other_cost_amount") or 0)
            penalty = int(data.get("payment_penalty_amount") or 0)
        except (TypeError, ValueError):
            return api_error(
                "مقادیر هزینه اضافی یا جریمه معتبر نیستند."
            )

        if other_cost < 0 or penalty < 0:
            return api_error(
                "مبالغ نمی‌توانند منفی باشند."
            )

        try:
            with transaction.atomic():
                calculation = ChargeCalculation.objects.create(
                    house=house,
                    name=name,
                    start_date=start_date,
                    end_date=end_date,
                    created_by=request.user,
                    other_cost_amount=other_cost,
                    payment_deadline=payment_deadline,
                    payment_penalty_amount=penalty,
                    details=data.get("details") or "",
                    status="draft",
                )

            return Response({
                "success": True,
                "message": "محاسبه شارژ ایجاد شد.",
                "result": self.serialize_calculation(calculation),
            }, status=status.HTTP_201_CREATED)

        except (TypeError, ValueError):
            return api_error(
                "مقادیر مبلغ یا تاریخ معتبر نیستند."
            )

    @transaction.atomic
    def patch(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        error = self.ensure_editable(calculation)

        if error:
            return error

        data = request.data

        allowed_fields = (
            "name",
            "start_date",
            "end_date",
            "payment_deadline",
            "details",
        )

        for field in allowed_fields:
            if field in data:
                setattr(
                    calculation,
                    field,
                    data[field] if data[field] != "" else None,
                )

        for field in (
                "other_cost_amount",
                "payment_penalty_amount",
        ):
            if field not in data:
                continue

            try:
                value = int(data[field] or 0)
            except (TypeError, ValueError):
                return api_error(
                    f"مقدار {field} معتبر نیست."
                )

            if value < 0:
                return api_error(
                    f"{field} نمی‌تواند منفی باشد."
                )

            setattr(calculation, field, value)

        if not calculation.name:
            return api_error("نام محاسبه الزامی است.")

        if (
                calculation.start_date
                and calculation.end_date
                and calculation.start_date > calculation.end_date
        ):
            return api_error(
                "تاریخ شروع نمی‌تواند بعد از تاریخ پایان باشد."
            )
        if "payment_deadline" in data:
            payment_deadline = data.get("payment_deadline")

            if not payment_deadline or not str(payment_deadline).strip():
                return api_error("مهلت پرداخت الزامی است.")

        calculation.save()

        return Response({
            "success": True,
            "message": "محاسبه ویرایش شد.",
            "result": self.serialize_calculation(calculation),
        })

    @transaction.atomic
    def delete(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        error = self.ensure_editable(calculation)

        if error:
            return error

        charges = list(
            get_calculation_charges(
                calculation,
                lock=True,
            )
        )

        if any(charge.is_paid for charge in charges):
            return api_error(
                "برای این محاسبه پرداخت ثبت شده و حذف آن مجاز نیست.",
                status.HTTP_409_CONFLICT,
            )

        if any(charge.send_notification for charge in charges):
            return api_error(
                "برای این محاسبه اعلان ثبت شده است؛ "
                "ابتدا اعلان‌ها را لغو کنید.",
                status.HTTP_409_CONFLICT,
            )

        UnifiedCharge.objects.filter(
            house=calculation.house,
            content_type=ContentType.objects.get_for_model(
                calculation,
                for_concrete_model=False,
            ),
            object_id=calculation.pk,
        ).delete()

        calculation.delete()

        return Response({
            "success": True,
            "message": "محاسبه و شارژهای مرتبط حذف شدند.",
        })


class ManagerChargeCalculationItemsAPIView(
    ManagerChargeCalculationBaseAPIView
):
    """
    دریافت و ذخیره آیتم‌های محاسبه شارژ.

    GET:
        همگام‌سازی منابع، گروه‌بندی هزینه‌ها و تعمیرات،
        دریافت واحدها و آیتم‌های محاسبه.

    POST:
        پذیرش ساختار گروهی Flutter یا ساختار items،
        ذخیره تنظیمات تسهیم و ثبت تخصیص‌ها و شارژ واحدها.
    """

    VALID_BASES = {"equal", "area", "person"}
    VALID_SCOPES = {"all", "occupied", "vacant", "selected"}

    # --------------------------------------------------
    # دریافت محاسبه
    # --------------------------------------------------

    def _get_calculation_object(self, request, pk):
        result = self.get_calculation(request, pk)

        if isinstance(result, Response):
            return None, result

        if isinstance(result, tuple):
            if not result:
                return None, Response(
                    {
                        "success": False,
                        "message": "محاسبه شارژ پیدا نشد.",
                    },
                    status=status.HTTP_404_NOT_FOUND,
                )

            calculation = result[0]

            if (
                    len(result) > 1
                    and isinstance(result[1], Response)
            ):
                return None, result[1]
        else:
            calculation = result

        if calculation is None:
            return None, Response(
                {
                    "success": False,
                    "message": "محاسبه شارژ پیدا نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return calculation, None

    # --------------------------------------------------
    # ابزارهای کمکی
    # --------------------------------------------------

    @staticmethod
    def _as_int(value, default=0):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _date_string(value):
        return value.isoformat() if value else None

    @staticmethod
    def _unit_label(unit):
        if unit is None:
            return None
        return str(getattr(unit, "unit", unit.pk))

    def _is_editable(self, calculation):
        return not (
                getattr(calculation, "is_finalized", False)
                or getattr(calculation, "status", "")
                in {"finalized", "cancelled"}
        )

    # --------------------------------------------------
    # همگام‌سازی منابع
    # --------------------------------------------------

    @transaction.atomic
    def _sync_calculation_source_items(self, calculation):
        """
        منابع فعال در بازه محاسبه را اضافه می‌کند.
        آیتم‌های موجود و تنظیمات مدیر حفظ می‌شوند.
        """

        if not self._is_editable(calculation):
            return

        expense_ct = ContentType.objects.get_for_model(
            Expense,
            for_concrete_model=False,
        )
        maintenance_ct = ContentType.objects.get_for_model(
            Maintenance,
            for_concrete_model=False,
        )

        expenses = Expense.objects.filter(
            house=calculation.house,
            is_active=True,
            date__gte=calculation.start_date,
            date__lte=calculation.end_date,
        ).select_related(
            "category",
            "unit",
        ).order_by("date", "pk")

        maintenances = Maintenance.objects.filter(
            house=calculation.house,
            is_active=True,
            maintenance_start_date__lte=calculation.end_date,
            maintenance_end_date__gte=calculation.start_date,
        ).select_related(
            "unit",
        ).order_by("maintenance_start_date", "pk")

        def sync_one(
                content_type,
                source,
                title,
                amount,
                source_date,
                source_unit=None,
        ):
            try:
                amount = int(amount or 0)
            except (TypeError, ValueError):
                return

            if amount < 0:
                return

            ChargeCalculationItem.objects.get_or_create(
                calculation=calculation,
                content_type=content_type,
                object_id=source.pk,
                defaults={
                    "title": str(title or "")[:1000],
                    "amount": amount,
                    "source_date": source_date,
                    "source_unit": source_unit,
                    "allocation_basis": "equal",
                    "allocation_scope": "all",
                    "is_selected": False,
                },
            )

        for expense in expenses:
            sync_one(
                expense_ct,
                expense,
                expense.description or "هزینه",
                expense.amount,
                expense.date,
                expense.unit,
            )

        for maintenance in maintenances:
            sync_one(
                maintenance_ct,
                maintenance,
                maintenance.maintenance_description or "تعمیرات",
                maintenance.maintenance_price,
                maintenance.maintenance_start_date,
                maintenance.unit,
            )

    # --------------------------------------------------
    # ساخت اطلاعات آیتم
    # --------------------------------------------------

    def _serialize_item(self, item):
        source = item.source

        result = {
            "id": item.pk,
            "item_id": item.pk,
            "title": item.title,
            "amount": self._as_int(item.amount),
            "fixed_amount": self._as_int(
                getattr(item, "fixed_amount", 0)
            ),
            "is_selected": bool(item.is_selected),
            "allocation_basis": item.allocation_basis,
            "allocation_scope": item.allocation_scope,
            "selected_unit_ids": list(
                item.selected_units.values_list("pk", flat=True)
            ),
            "source_type": item.source_type,
            "source_name": item.source_name,
            "source_date": self._date_string(item.source_date),
            "is_paid": bool(
                getattr(source, "is_paid", False)
            ) if source is not None else False,
        }

        if isinstance(source, Expense):
            result.update({
                "category_id": source.category_id,
                "category": str(source.category),
                "date": self._date_string(source.date),
                "doc_no": source.doc_no,
                "financial_document_number":
                    source.financial_document_number,
                "unit": self._unit_label(source.unit),
                "unit_id": source.unit_id,
                "receiver_name": (
                    source.get_receiver_display()
                    if hasattr(source, "get_receiver_display")
                    else source.receiver_name
                ),
                "is_active": source.is_active,
                "payment_date": self._date_string(
                    source.payment_date
                ),
            })

        elif isinstance(source, Maintenance):
            result.update({
                "date": self._date_string(
                    source.maintenance_start_date
                ),
                "maintenance_end_date": self._date_string(
                    source.maintenance_end_date
                ),
                "financial_document_number":
                    source.financial_document_number,
                "unit": self._unit_label(source.unit),
                "unit_id": source.unit_id,
                "receiver_name": (
                    source.get_receiver_display()
                    if hasattr(source, "get_receiver_display")
                    else source.receiver_name
                ),
                "is_active": source.is_active,
                "payment_date": self._date_string(
                    source.payment_date
                ),
            })

        return result

    # --------------------------------------------------
    # GET: ساخت گروه‌های مورد انتظار Flutter
    # --------------------------------------------------

    def get(self, request, pk):
        calculation, error_response = (
            self._get_calculation_object(request, pk)
        )

        if error_response:
            return error_response

        self._sync_calculation_source_items(calculation)

        items = list(
            calculation.items
            .all()
            .prefetch_related("selected_units")
            .order_by("pk")
        )

        serialized_items = [
            self._serialize_item(item)
            for item in items
        ]

        expense_groups_by_category = {}
        maintenance_groups = []

        for item, serialized in zip(items, serialized_items):
            source = item.source

            if isinstance(source, Expense):
                category_id = source.category_id
                category_title = str(source.category)

                group_key = (
                    category_id
                    if category_id is not None
                    else f"uncategorized-{item.pk}"
                )

                if group_key not in expense_groups_by_category:
                    expense_groups_by_category[group_key] = {
                        "group_id": (
                            category_id
                            if category_id is not None
                            else item.pk
                        ),
                        "type": "expense",
                        "category_id": category_id,
                        "category": category_title,
                        "title": category_title,
                        "selected": True,
                        "basis": item.allocation_basis,
                        "scope": item.allocation_scope,
                        "selected_unit_ids": list(
                            serialized["selected_unit_ids"]
                        ),
                        "total_amount": 0,
                        "paid_count": 0,
                        "unpaid_count": 0,
                        "inactive_count": 0,
                        "expenses": [],
                    }

                group = expense_groups_by_category[group_key]

                group["expenses"].append(serialized)
                group["total_amount"] += serialized["amount"]

                if not serialized["is_active"]:
                    group["inactive_count"] += 1

                if serialized["is_paid"]:
                    group["paid_count"] += 1
                else:
                    group["unpaid_count"] += 1

            elif isinstance(source, Maintenance):
                maintenance_groups.append({
                    "group_id": item.pk,
                    "item_id": item.pk,
                    "type": "maintenance",
                    "title": source.maintenance_description or item.title,
                    "selected": bool(item.is_selected),
                    "basis": item.allocation_basis,
                    "scope": item.allocation_scope,
                    "selected_unit_ids": list(
                        serialized["selected_unit_ids"]
                    ),
                    "total_amount": serialized["amount"],
                    "amount": serialized["amount"],
                    "date": self._date_string(
                        source.maintenance_start_date
                    ),
                    "maintenance_end_date": self._date_string(
                        source.maintenance_end_date
                    ),
                    "is_paid": bool(source.is_paid),
                    "is_active": bool(source.is_active),
                    "financial_document_number":
                        source.financial_document_number,
                    "unit": self._unit_label(source.unit),
                    "receiver_name": (
                        source.get_receiver_display()
                        if hasattr(source, "get_receiver_display")
                        else source.receiver_name
                    ),
                    "expenses": [serialized],
                })

        expense_groups = list(
            expense_groups_by_category.values()
        )

        # وضعیت انتخاب گروه هزینه:
        # اگر همه آیتم‌های گروه انتخاب شده باشند، گروه انتخاب‌شده است.
        # در صورت وجود انتخاب‌های متفاوت، گروه به‌صورت انتخاب‌نشده
        # نمایش داده می‌شود تا انتخاب گروهی یکدست شود.
        for group in expense_groups:
            group_items = group["expenses"]

            group["selected"] = bool(
                group_items
                and all(
                    item_data["is_selected"]
                    for item_data in group_items
                )
            )

            # در گروه‌های موجود، مبنا و محدوده فقط زمانی یکدست
            # هستند که تمام آیتم‌ها مقدار یکسان داشته باشند.
            if group_items:
                group["basis"] = group_items[0]["allocation_basis"]
                group["scope"] = group_items[0]["allocation_scope"]

                group["selected_unit_ids"] = sorted({
                    unit_id
                    for item_data in group_items
                    for unit_id in item_data["selected_unit_ids"]
                })

        units = Unit.objects.filter(
            myhouse=calculation.house,
            is_active=True,
        ).order_by("pk")

        units_data = [
            {
                "id": unit.pk,
                "unit": self._unit_label(unit),
                "area": str(getattr(unit, "area", 0) or 0),
            }
            for unit in units
        ]

        calculation_data = {
            "id": calculation.pk,
            "name": getattr(calculation, "name", ""),
            "start_date": self._date_string(
                calculation.start_date
            ),
            "payment_deadline": self._date_string(
                calculation.payment_deadline
            ),
            "end_date": self._date_string(
                calculation.end_date
            ),
            "status": getattr(calculation, "status", ""),
            "unit_count": getattr(calculation, "unit_count", 0),
            "other_cost_amount": self._as_int(
                getattr(calculation, "other_cost_amount", 0)
            ),
            "is_finalized": bool(
                getattr(calculation, "is_finalized", False)
            ),
        }

        return Response({
            "success": True,
            "calculation_id": calculation.pk,
            "calculation": calculation_data,
            "expense_groups": expense_groups,
            "maintenance_groups": maintenance_groups,
            "units": units_data,
            "items": serialized_items,
            "selected_items_count": sum(
                1 for item in serialized_items
                if item["is_selected"]
            ),
            "total_items_count": len(serialized_items),
            "can_edit": self._is_editable(calculation),
        })

    # --------------------------------------------------
    # ذخیره واحدهای انتخاب‌شده
    # --------------------------------------------------

    def _save_selected_units(
            self,
            item,
            item_data,
            calculation,
    ):
        if item.allocation_scope != "selected":
            item.selected_units.clear()
            return None

        if "selected_unit_ids" not in item_data:
            return Response(
                {
                    "success": False,
                    "message": (
                        "برای تسهیم بر اساس واحدهای انتخاب‌شده، "
                        "selected_unit_ids الزامی است."
                    ),
                    "item_id": item.pk,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        selected_ids = item_data.get("selected_unit_ids")

        if not isinstance(selected_ids, list):
            return Response(
                {
                    "success": False,
                    "message": (
                        "selected_unit_ids باید آرایه باشد."
                    ),
                    "item_id": item.pk,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            requested_ids = {
                int(unit_id) for unit_id in selected_ids
            }
        except (TypeError, ValueError):
            return Response(
                {
                    "success": False,
                    "message": "شناسه واحد معتبر نیست.",
                    "item_id": item.pk,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not requested_ids:
            return Response(
                {
                    "success": False,
                    "message": "حداقل یک واحد انتخاب کنید.",
                    "item_id": item.pk,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        valid_ids = set(
            Unit.objects.filter(
                myhouse=calculation.house,
                is_active=True,
                pk__in=requested_ids,
            ).values_list("pk", flat=True)
        )

        if valid_ids != requested_ids:
            return Response(
                {
                    "success": False,
                    "message": (
                        "یک یا چند واحد غیرفعال است یا به این "
                        "ساختمان تعلق ندارد."
                    ),
                    "item_id": item.pk,
                    "invalid_unit_ids": sorted(
                        requested_ids - valid_ids
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item.selected_units.set(valid_ids)
        return None

    # --------------------------------------------------
    # ذخیره شارژ واحد
    # --------------------------------------------------

    def _save_unified_charge(
            self,
            request,
            calculation,
            calculation_ct,
            unit,
            base_amount,
            other_cost,
    ):
        total_amount = int(base_amount) + int(other_cost)

        charge = UnifiedCharge.objects.filter(
            house=calculation.house,
            content_type=calculation_ct,
            object_id=calculation.pk,
            unit=unit,
        ).first()

        if charge is not None:
            if charge.is_paid or charge.send_notification:
                return None, Response(
                    {
                        "success": False,
                        "message": (
                            "شارژ این واحد پرداخت یا اعلان شده "
                            "و امکان تغییر آن وجود ندارد."
                        ),
                        "unit_id": unit.pk,
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            charge = UnifiedCharge(
                user=(
                        getattr(calculation, "created_by", None)
                        or request.user
                ),
                unit=unit,
                house=calculation.house,
                content_type=calculation_ct,
                object_id=calculation.pk,
            )

        charge.charge_type = UnifiedCharge.ChargeType.EXPENSE_CHARGE
        charge.amount = total_amount
        charge.base_charge = int(base_amount)
        charge.other_cost_amount = int(other_cost)
        charge.total_charge_month = total_amount

        # عنوان شارژ
        if hasattr(charge, "title"):
            charge.title = "شارژ تسهیم هزینه"

        # درصد جریمه
        if hasattr(charge, "penalty_percent"):
            charge.penalty_percent = getattr(
                calculation, "payment_penalty_amount", 0
            )
        if hasattr(charge, "details"):
            charge.details = getattr(
                calculation, "details", 0
            )

        # تاریخ سررسید
        if hasattr(charge, "payment_deadline_date"):
            charge.payment_deadline_date = getattr(
                calculation, "payment_deadline", None
            )

        # شماره سند مالی: فقط هنگام ایجاد رکورد جدید
        if (
                charge.pk is None
                and hasattr(charge, "financial_document_number")
                and not charge.financial_document_number
        ):
            from admin_panel.services.utils import get_next_financial_document_number
            charge.financial_document_number = (
                get_next_financial_document_number(calculation.house)
            )

        charge.save()

        return charge, None

    # --------------------------------------------------
    # تبدیل payload Flutter به ساختار واحد
    # --------------------------------------------------

    def _normalize_post_groups(self, groups, items_by_id):
        """
        دو ساختار را می‌پذیرد:

        1. ساختار فعلی Flutter:
           type, group_id, selected, basis, scope,
           selected_unit_ids

        2. ساختار قدیمی API:
           allocation_basis, allocation_scope, items
        """

        normalized = []
        seen_item_ids = set()

        for group in groups:
            if not isinstance(group, dict):
                return None, Response(
                    {
                        "success": False,
                        "message": "ساختار یکی از گروه‌ها معتبر نیست.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            # ساختار قبلی API
            if isinstance(group.get("items"), list):
                basis = group.get("allocation_basis", "equal")
                scope = group.get("allocation_scope", "all")
                group_items = group["items"]

            else:
                # ساختار Flutter
                group_type = group.get("type", "expense")
                group_id = group.get("group_id")
                basis = group.get(
                    "basis",
                    group.get("allocation_basis", "equal"),
                )
                scope = group.get(
                    "scope",
                    group.get("allocation_scope", "all"),
                )
                selected = bool(group.get("selected", False))
                selected_unit_ids = group.get(
                    "selected_unit_ids", []
                )

                if basis not in self.VALID_BASES:
                    return None, Response(
                        {
                            "success": False,
                            "message": "مبنای تسهیم معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if scope not in self.VALID_SCOPES:
                    return None, Response(
                        {
                            "success": False,
                            "message": "محدوده تسهیم معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    group_id = int(group_id)
                except (TypeError, ValueError):
                    return None, Response(
                        {
                            "success": False,
                            "message": "شناسه گروه معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if group_type == "maintenance":
                    item_ids = [group_id]
                elif group_type == "expense":
                    # در گروه هزینه، group_id شناسه دسته‌بندی است.
                    # تمام آیتم‌های هزینه متعلق به آن دسته پیدا می‌شوند.
                    item_ids = []

                    for item_id, item in items_by_id.items():
                        source = item.source

                        if not isinstance(source, Expense):
                            continue

                        if source.category_id == group_id:
                            item_ids.append(item_id)

                else:
                    return None, Response(
                        {
                            "success": False,
                            "message": "نوع گروه معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                group_items = [
                    {
                        "id": item_id,
                        "is_selected": selected,
                        "selected_unit_ids": selected_unit_ids,
                    }
                    for item_id in item_ids
                ]

            if basis not in self.VALID_BASES:
                return None, Response(
                    {
                        "success": False,
                        "message": "مبنای تسهیم معتبر نیست.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if scope not in self.VALID_SCOPES:
                return None, Response(
                    {
                        "success": False,
                        "message": "محدوده واحدها معتبر نیست.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            if not isinstance(group_items, list):
                return None, Response(
                    {
                        "success": False,
                        "message": "فهرست آیتم‌های گروه معتبر نیست.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            normalized_group_items = []

            for item_data in group_items:
                if not isinstance(item_data, dict):
                    return None, Response(
                        {
                            "success": False,
                            "message": "ساختار آیتم معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                try:
                    item_id = int(item_data.get("id"))
                except (TypeError, ValueError):
                    return None, Response(
                        {
                            "success": False,
                            "message": "شناسه آیتم معتبر نیست.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if item_id not in items_by_id:
                    return None, Response(
                        {
                            "success": False,
                            "message": (
                                "آیتم متعلق به این محاسبه نیست."
                            ),
                            "item_id": item_id,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if item_id in seen_item_ids:
                    return None, Response(
                        {
                            "success": False,
                            "message": (
                                "یک آیتم در چند گروه تکرار شده است."
                            ),
                            "item_id": item_id,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                seen_item_ids.add(item_id)

                normalized_group_items.append({
                    "id": item_id,
                    "is_selected": item_data.get("is_selected"),
                    "selected_unit_ids": item_data.get(
                        "selected_unit_ids", []
                    ),
                    "has_selected_unit_ids":
                        "selected_unit_ids" in item_data,
                })

            normalized.append({
                "allocation_basis": basis,
                "allocation_scope": scope,
                "items": normalized_group_items,
            })

        return normalized, None

    # --------------------------------------------------
    # POST: ذخیره تنظیمات و محاسبه شارژ
    # --------------------------------------------------

    @transaction.atomic
    def post(self, request, pk):
        calculation, error_response = (
            self._get_calculation_object(request, pk)
        )

        if error_response:
            return error_response

        response = self.ensure_editable(calculation)
        if response:
            return response

        response = self.ensure_no_protected_charges(calculation)
        if response:
            return response

        groups = request.data.get("groups", [])

        if not isinstance(groups, list):
            return Response(
                {
                    "success": False,
                    "message": "ساختار groups معتبر نیست.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        items_by_id = {
            item.pk: item
            for item in calculation.items.all()
        }

        normalized_groups, error_response = (
            self._normalize_post_groups(groups, items_by_id)
        )

        if error_response:
            return error_response

        for group in normalized_groups:
            basis = group["allocation_basis"]
            scope = group["allocation_scope"]

            for item_data in group["items"]:
                item = items_by_id[item_data["id"]]

                item.allocation_basis = basis
                item.allocation_scope = scope

                if item_data["is_selected"] is not None:
                    item.is_selected = bool(
                        item_data["is_selected"]
                    )

                item.save(
                    update_fields=[
                        "allocation_basis",
                        "allocation_scope",
                        "is_selected",
                    ]
                )

                # برای آیتم انتخاب‌نشده نیازی به اعتبارسنجی
                # واحدهای انتخاب‌شده برای محاسبه نیست.
                if item.is_selected:
                    response = self._save_selected_units(
                        item=item,
                        item_data={
                            "selected_unit_ids":
                                item_data["selected_unit_ids"],
                        } if item_data["has_selected_unit_ids"]
                        else {},
                        calculation=calculation,
                    )

                    if response:
                        return response

        selected_items = list(
            calculation.items.filter(is_selected=True)
        )

        if not selected_items:
            return Response(
                {
                    "success": False,
                    "message": (
                        "هیچ آیتمی برای محاسبه انتخاب نشده است."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        units = list(
            Unit.objects.filter(
                myhouse=calculation.house,
                is_active=True,
            ).order_by("pk")
        )

        if not units:
            return Response(
                {
                    "success": False,
                    "message": (
                        "هیچ واحد فعالی در این ساختمان وجود ندارد."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        item_allocations, totals, participating_unit_ids = (
            calculate_charge_item_allocations(
                selected_items,
                units,
            )
        )

        calculation_ct = ContentType.objects.get_for_model(
            calculation,
            for_concrete_model=False,
        )

        other_cost = self._as_int(
            getattr(calculation, "other_cost_amount", 0)
        )

        active_unit_ids = {unit.pk for unit in units}
        units_by_id = {unit.pk: unit for unit in units}

        created_or_updated_charges = 0
        created_or_updated_allocations = 0

        for item in selected_items:
            allocations_for_item = item_allocations.get(
                item.pk, {}
            )

            participating_unit_ids = {
                int(unit_id)
                for unit_id in allocations_for_item
            }

            if item.allocation_scope == "selected":
                selected_ids = set(
                    item.selected_units.values_list(
                        "pk", flat=True
                    )
                )
                participating_unit_ids &= selected_ids

            for unit_id in participating_unit_ids:
                if unit_id not in active_unit_ids:
                    continue

                unit = units_by_id[unit_id]

                try:
                    base_amount = int(
                        Decimal(
                            str(allocations_for_item[unit_id])
                        ).quantize(Decimal("1"))
                    )
                except (
                        InvalidOperation,
                        TypeError,
                        ValueError,
                ):
                    return Response(
                        {
                            "success": False,
                            "message": (
                                "مبلغ تسهیم‌شده معتبر نیست."
                            ),
                            "item_id": item.pk,
                            "unit_id": unit_id,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if base_amount < 0:
                    return Response(
                        {
                            "success": False,
                            "message": "مبلغ شارژ منفی است.",
                            "item_id": item.pk,
                            "unit_id": unit_id,
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                if item.allocation_basis == "area":
                    calculation_value = Decimal(
                        str(getattr(unit, "area", 0) or 0)
                    )
                elif item.allocation_basis == "person":
                    calculation_value = Decimal(
                        str(charge_people_count(unit))
                    )
                else:
                    calculation_value = Decimal("1")

                area_snapshot = (
                    Decimal(
                        str(getattr(unit, "area", 0) or 0)
                    )
                    if item.allocation_basis == "area"
                    else None
                )

                people_snapshot = (
                    charge_people_count(unit)
                    if item.allocation_basis == "person"
                    else None
                )

                allocation, allocation_created = (
                    ChargeAllocation.objects.get_or_create(
                        item=item,
                        unit=unit,
                        defaults={
                            "calculation_value": calculation_value,
                            "area_snapshot": area_snapshot,
                            "people_snapshot": people_snapshot,
                            "amount": base_amount,
                            "exact_amount": Decimal(base_amount),
                        },
                    )
                )

                if not allocation_created:
                    allocation.calculation_value = calculation_value
                    allocation.area_snapshot = area_snapshot
                    allocation.people_snapshot = people_snapshot
                    allocation.amount = base_amount
                    allocation.exact_amount = Decimal(base_amount)

                    allocation.save(
                        update_fields=[
                            "calculation_value",
                            "area_snapshot",
                            "people_snapshot",
                            "amount",
                            "exact_amount",
                        ]
                    )

                created_or_updated_allocations += 1

                charge, error_response = self._save_unified_charge(
                    request=request,
                    calculation=calculation,
                    calculation_ct=calculation_ct,
                    unit=unit,
                    base_amount=base_amount,
                    other_cost=other_cost,
                )

                if error_response:
                    return error_response

                created_or_updated_charges += 1

        # پاک‌سازی تخصیص‌های نامعتبر یا مربوط به آیتم غیرفعال
        for item in calculation.items.all():
            if not item.is_selected:
                item.allocations.all().delete()
                continue

            allocations_for_item = item_allocations.get(
                item.pk, {}
            )

            valid_unit_ids = {
                                 int(unit_id)
                                 for unit_id in allocations_for_item
                             } & active_unit_ids

            if item.allocation_scope == "selected":
                selected_ids = set(
                    item.selected_units.values_list(
                        "pk", flat=True
                    )
                )
                valid_unit_ids &= selected_ids

            item.allocations.exclude(
                unit_id__in=valid_unit_ids
            ).delete()

        calculation.unit_count = len(units)
        update_fields = ["unit_count"]

        if hasattr(calculation, "status"):
            calculation.status = "calculated"
            update_fields.append("status")

        calculation.save(update_fields=update_fields)

        return Response(
            {
                "success": True,
                "message": (
                    "تنظیمات و تسهیم شارژ با موفقیت ذخیره شد."
                ),
                "calculation_id": calculation.pk,
                "unit_count": len(units),
                "selected_items_count": len(selected_items),
                "created_or_updated_charges":
                    created_or_updated_charges,
                "created_or_updated_allocations":
                    created_or_updated_allocations,
            },
            status=status.HTTP_200_OK,
        )


class ManagerChargeCalculationUnitsAPIView(
    ManagerChargeCalculationBaseAPIView
):

    # --------------------------------------------------
    # اطلاعات ساکنان واحد
    # --------------------------------------------------

    def _get_unit_resident_info(self, unit):
        """
        تعیین نوع ساکن، نام ساکن و تعداد نفرات.

        اولویت:
        1. واحد خالی
        2. مستأجران فعال
        3. مالک ساکن
        """

        status_residence = str(
            getattr(unit, "status_residence", "") or ""
        ).strip().lower()

        active_renters = list(
            getattr(unit, "active_renters_for_charge", [])
        )

        # واحد خالی
        if status_residence == "empty":
            return {
                "resident_type": "empty",
                "resident_name": "",
                "people_count": 0,
            }

        # واحد دارای مستأجر فعال
        if active_renters:
            renter_names = [
                str(renter.renter_name).strip()
                for renter in active_renters
                if getattr(renter, "renter_name", None)
                   and str(renter.renter_name).strip()
            ]

            people_count = sum(
                max(
                    int(
                        getattr(
                            renter,
                            "renter_people_count",
                            0,
                        ) or 0
                    ),
                    0,
                )
                for renter in active_renters
            )

            return {
                "resident_type": "renter",
                "resident_name": "، ".join(renter_names),
                "people_count": people_count,
            }

        # مالک ساکن؛ در نبود مستأجر فعال
        if status_residence == "occupied":
            return {
                "resident_type": "owner",
                "resident_name": str(
                    getattr(unit, "owner_name", "") or ""
                ).strip(),
                "people_count": max(
                    int(
                        getattr(
                            unit,
                            "owner_people_count",
                            0,
                        ) or 0
                    ),
                    0,
                ),
            }

        # وضعیت نامشخص را به‌اشتباه مالک یا مستأجر فرض نکن.
        return {
            "resident_type": "empty",
            "resident_name": "",
            "people_count": 0,
        }

    # --------------------------------------------------
    # GET: نمایش سهم و وضعیت مالی واحدها
    # --------------------------------------------------

    def get(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        items = list(
            calculation.items.filter(
                is_selected=True,
            ).prefetch_related(
                "selected_units",
                "allocations",
            )
        )

        all_units = list(
            Unit.objects.filter(
                myhouse=calculation.house,
                is_active=True,
            ).prefetch_related(
                Prefetch(
                    "renters",
                    queryset=Renter.objects.filter(
                        renter_is_active=True,
                    ),
                    to_attr="active_renters_for_charge",
                )
            ).order_by("unit")
        )

        (
            item_allocations,
            totals,
            participating_ids,
        ) = calculate_charge_item_allocations(
            items,
            all_units,
        )

        # --------------------------------------------------
        # سهم‌های ذخیره‌شده
        # --------------------------------------------------

        saved_costs = {}

        for item in items:
            for allocation in item.allocations.all():
                saved_costs[allocation.unit_id] = (
                        saved_costs.get(
                            allocation.unit_id,
                            Decimal("0"),
                        )
                        + decimal_value(allocation.amount)
                )

        has_saved_allocations = any(
            item.allocations.exists()
            for item in items
        )

        if has_saved_allocations:
            unit_costs = saved_costs
        else:
            unit_costs = {
                unit_id: value
                for unit_id, value in totals.items()
                if unit_id in participating_ids
            }

        # --------------------------------------------------
        # رکوردهای مالی
        # --------------------------------------------------

        charges = list(
            get_calculation_charges(calculation)
        )

        duplicates = find_duplicate_charge_units(charges)

        if duplicates:
            return api_error(
                "برای بعضی واحدها رکورد شارژ تکراری وجود دارد؛ "
                "نمایش وضعیت مالی این محاسبه نیازمند بررسی است.",
                status.HTTP_409_CONFLICT,
                duplicate_unit_ids=duplicates,
            )

        charge_by_unit = {
            charge.unit_id: charge
            for charge in charges
        }

        other_cost = int(
            calculation.other_cost_amount or 0
        )

        results = []

        for unit in all_units:

            # واحدهایی که در تسهیم مشارکت ندارند نمایش داده نشوند.
            if unit.id not in participating_ids:
                continue

            resident_info = self._get_unit_resident_info(
                unit
            )

            cost_total = money_round(
                unit_costs.get(
                    unit.id,
                    Decimal("0"),
                )
            )

            # هزینه اضافی برای هر واحد مشارکت‌کننده
            total = cost_total + other_cost

            charge = charge_by_unit.get(unit.id)

            results.append({
                "unit_id": unit.id,
                "unit": str(unit.unit),
                "area": str(unit.area or 0),

                "resident_type": resident_info[
                    "resident_type"
                ],
                "resident_name": resident_info[
                    "resident_name"
                ],
                "people_count": resident_info[
                    "people_count"
                ],

                "cost_total": str(cost_total),
                "other_cost_amount": str(other_cost),
                "total": str(total),

                "is_paid": bool(
                    charge and charge.is_paid
                ),

                "send_notification": bool(
                    charge and charge.send_notification
                ),

                "send_sms": bool(
                    charge and charge.send_sms
                ),

                "financial_document_number": (
                    charge.financial_document_number
                    if charge
                    else None
                ),
            })

        return Response({
            "success": True,

            "calculation": {
                "id": calculation.pk,
                "name": calculation.name,
                "start_date":
                    calculation.start_date,

                "payment_deadline": (
                    calculation.payment_deadline.isoformat()
                    if calculation.payment_deadline
                    else None
                ),
                "end_date": calculation.end_date,

                "details": calculation.details or "",
                "status": calculation.status,
                "other_cost_amount": str(
                    calculation.other_cost_amount or 0
                ),
            },

            "count": len(results),
            "results": results,
        })

    # --------------------------------------------------
    # POST: محاسبه و ذخیره سهم واحدها
    # --------------------------------------------------

    @transaction.atomic
    def post(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        error = self.ensure_editable(calculation)

        if error:
            return error

        error = self.ensure_no_protected_charges(
            calculation
        )

        if error:
            return error

        items = list(
            calculation.items.filter(
                is_selected=True,
            ).select_related(
                "content_type",
            ).prefetch_related(
                "selected_units",
                "allocations",
            )
        )

        if not items:
            return api_error(
                "هیچ هزینه‌ای برای تسهیم انتخاب نشده است."
            )

        all_units = list(
            Unit.objects.filter(
                myhouse=calculation.house,
                is_active=True,
            ).prefetch_related(
                Prefetch(
                    "renters",
                    queryset=Renter.objects.filter(
                        renter_is_active=True,
                    ),
                    to_attr="active_renters_for_charge",
                )
            ).order_by("unit")
        )

        if not all_units:
            return api_error(
                "هیچ واحد فعالی برای محاسبه وجود ندارد."
            )

        (
            item_allocations,
            totals,
            participating_ids,
        ) = calculate_charge_item_allocations(
            items,
            all_units,
        )

        unit_by_id = {
            unit.id: unit
            for unit in all_units
        }

        ct = get_calculation_content_type()

        existing_charges = list(
            UnifiedCharge.objects.select_for_update().filter(
                house=calculation.house,
                content_type=ct,
                object_id=calculation.pk,
            ).order_by("id")
        )

        duplicates = find_duplicate_charge_units(
            existing_charges
        )

        if duplicates:
            return api_error(
                "برای بعضی واحدها چند رکورد شارژ وجود دارد؛ "
                "محاسبه مجدد متوقف شد.",
                status.HTTP_409_CONFLICT,
                duplicate_unit_ids=duplicates,
            )

        existing_by_unit = {
            charge.unit_id: charge
            for charge in existing_charges
        }

        other_cost = int(
            calculation.other_cost_amount or 0
        )

        # --------------------------------------------------
        # ایجاد یا به‌روزرسانی شارژ و تخصیص‌ها
        # --------------------------------------------------

        for unit_id in participating_ids:

            unit = unit_by_id.get(unit_id)

            if unit is None:
                continue

            base_amount = money_round(
                totals.get(
                    unit_id,
                    Decimal("0"),
                )
            )

            total_amount = base_amount + other_cost

            charge = existing_by_unit.get(unit_id)

            if charge and (
                    charge.is_paid
                    or charge.send_notification
            ):
                return api_error(
                    "شارژ یک واحد پرداخت یا اعلان شده است؛ "
                    "محاسبه مجدد متوقف شد.",
                    status.HTTP_409_CONFLICT,
                    protected_unit_ids=[unit_id],
                )

            defaults = {
                "user": request.user,
                "house": calculation.house,
                "unit": unit,

                "charge_type": (
                    UnifiedCharge.ChargeType.EXPENSE_CHARGE
                ),

                "amount": base_amount,
                "base_charge": base_amount,
                "other_cost_amount": other_cost,
                "civil": 0,
                "total_charge_month": total_amount,

                "title": calculation.name,
                "details": calculation.details or "",

                "payment_deadline_date": (
                    calculation.payment_deadline
                ),
                "penalty_amount": (
                    calculation.payment_penalty_amount
                ),

                "payment_pending": False,

                "send_notification": False,
                "send_notification_date": None,

                "content_type": ct,
                "object_id": calculation.pk,
            }

            charge, _ = UnifiedCharge.objects.update_or_create(
                house=calculation.house,
                unit=unit,
                content_type=ct,
                object_id=calculation.pk,
                defaults=defaults,
            )

            # ذخیره تخصیص دقیق هر آیتم
            for item in items:

                item_unit_allocations = item_allocations.get(
                    item.id,
                    {},
                )

                if unit.id not in item_unit_allocations:
                    ChargeAllocation.objects.filter(
                        item=item,
                        unit=unit,
                    ).delete()
                    continue

                exact_share = decimal_value(
                    item_unit_allocations[unit.id]
                )

                ChargeAllocation.objects.update_or_create(
                    item=item,
                    unit=unit,
                    defaults={
                        "calculation_value": exact_share,
                        "area_snapshot": charge_area_value(
                            unit
                        ),
                        "people_snapshot": (
                            charge_people_count(unit)
                        ),
                        "amount": money_round(exact_share),
                        "exact_amount": exact_share,
                    },
                )

        # --------------------------------------------------
        # حذف شارژهای قدیمی واحدهایی که دیگر مشارکت ندارند
        # --------------------------------------------------

        stale_unit_ids = (
                set(existing_by_unit.keys())
                - set(participating_ids)
        )

        for unit_id in stale_unit_ids:
            old_charge = existing_by_unit[unit_id]

            if (
                    old_charge.is_paid
                    or old_charge.send_notification
            ):
                return api_error(
                    "یک واحد قبلی پرداخت یا اعلان شده است؛ "
                    "حذف شارژ آن مجاز نیست.",
                    status.HTTP_409_CONFLICT,
                    protected_unit_ids=[unit_id],
                )

            ChargeAllocation.objects.filter(
                item__calculation=calculation,
                unit_id=unit_id,
            ).delete()

            old_charge.delete()

        # --------------------------------------------------
        # به‌روزرسانی وضعیت محاسبه
        # --------------------------------------------------

        calculation.unit_count = len(participating_ids)
        calculation.status = "calculated"

        calculation.save(
            update_fields=[
                "unit_count",
                "status",
                "updated_at",
            ]
        )

        return Response({
            "success": True,
            "message": (
                "محاسبه و سهم واحدها ذخیره شد. "
                "هیچ اعلان یا پیامکی ارسال نشده است."
            ),
            "count": len(participating_ids),
            "results": [
                {
                    "unit_id": unit_id,
                    "base_amount": money_round(
                        totals.get(
                            unit_id,
                            Decimal("0"),
                        )
                    ),
                    "other_cost_amount": other_cost,
                    "total": (
                            money_round(
                                totals.get(
                                    unit_id,
                                    Decimal("0"),
                                )
                            )
                            + other_cost
                    ),
                }
                for unit_id in sorted(
                    participating_ids
                )
            ],
        })


class ManagerChargeCalculationSendAPIView(
    ManagerChargeCalculationBaseAPIView
):

    @transaction.atomic
    def post(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        if calculation.status not in (
                "draft",
                "calculated",
                "finalized",
        ):
            return api_error(
                "وضعیت فعلی محاسبه اجازه ارسال شارژ را نمی‌دهد.",
                status.HTTP_409_CONFLICT,
            )

        unit_ids = request.data.get("unit_ids")
        send_sms = request.data.get("send_sms", False)

        if isinstance(send_sms, str):
            send_sms = send_sms.strip().lower() in (
                "true",
                "1",
                "yes",
            )

        if not isinstance(unit_ids, list) or not unit_ids:
            return api_error(
                "حداقل یک واحد باید انتخاب شود."
            )

        try:
            unit_ids = list(dict.fromkeys(
                int(value) for value in unit_ids
            ))
        except (TypeError, ValueError):
            return api_error(
                "شناسه واحدها معتبر نیست."
            )

        units = list(
            Unit.objects.filter(
                myhouse=calculation.house,
                is_active=True,
                id__in=unit_ids,
            ).order_by("unit")
        )

        if len(units) != len(unit_ids):
            return api_error(
                "برخی واحدها غیرفعال یا متعلق به ساختمان دیگری هستند."
            )

        items = list(
            calculation.items.filter(
                is_selected=True,
            )
        )

        if not items:
            return api_error(
                "هیچ هزینه‌ای برای تسهیم انتخاب نشده است."
            )

        charges = list(
            get_calculation_charges(
                calculation,
                lock=True,
            )
        )

        duplicates = find_duplicate_charge_units(charges)

        if duplicates:
            return api_error(
                "برای بعضی واحدها رکورد شارژ تکراری وجود دارد.",
                status.HTTP_409_CONFLICT,
                duplicate_unit_ids=duplicates,
            )

        charge_by_unit = {
            charge.unit_id: charge
            for charge in charges
        }

        missing_units = [
            unit_id
            for unit_id in unit_ids
            if unit_id not in charge_by_unit
        ]

        if missing_units:
            return api_error(
                "برای بعضی واحدها هنوز شارژ محاسبه و ذخیره نشده است. "
                "ابتدا محاسبه را ذخیره کنید.",
                status.HTTP_409_CONFLICT,
                missing_unit_ids=missing_units,
            )

        selected_charges = [
            charge_by_unit[unit_id]
            for unit_id in unit_ids
        ]

        paid_ids = [
            charge.unit_id
            for charge in selected_charges
            if charge.is_paid
        ]

        if paid_ids:
            return api_error(
                "برای واحدهای پرداخت‌شده اعلان جدید ارسال نمی‌شود.",
                status.HTTP_409_CONFLICT,
                paid_unit_ids=paid_ids,
            )

        notification_charges = [
            charge
            for charge in selected_charges
            if not charge.send_notification
        ]

        sms_charges = [
            charge
            for charge in selected_charges
            if send_sms and not charge.send_sms
        ]

        if not notification_charges and not sms_charges:
            return Response({
                "success": True,
                "message": "اعلان و پیامک جدیدی برای ارسال وجود ندارد.",
                "created_count": 0,
                "sms_success": None,
            })

        # ثبت شماره سند و اعلان فقط برای شارژهایی که
        # هنوز اعلان نشده‌اند.
        for charge in notification_charges:
            if not charge.financial_document_number:
                charge.financial_document_number = (
                    get_next_financial_document_number(
                        calculation.house
                    )
                )

            charge.send_notification = True
            charge.send_notification_date = date.today()

            charge.save(update_fields=[
                "financial_document_number",
                "send_notification",
                "send_notification_date",
            ])

        sms_success = None
        sms_message = None

        if send_sms and sms_charges:
            def save_sms_metadata(
                    total_sms=0,
                    total_price=0,
            ):
                UnifiedCharge.objects.filter(
                    pk__in=[
                        charge.pk
                        for charge in sms_charges
                    ]
                ).update(
                    send_sms=True,
                    send_sms_date=date.today(),
                    sms_count=total_sms,
                    sms_total_price=total_price,
                )

            sms_result = SmsService.send_for_unified_charges(
                user=request.user,
                unified_charges=sms_charges,
                meta_callback=save_sms_metadata,
            )

            sms_success = bool(sms_result.success)
            sms_message = sms_result.message

            if not sms_success:
                return Response({
                    "success": True,
                    "message": (
                        "اعلان شارژ ثبت شد، اما ارسال پیامک موفق نبود. "
                        "می‌توانید پیامک را مجدداً ارسال کنید."
                    ),
                    "sms_success": False,
                    "sms_message": sms_message,
                    "created_count": len(notification_charges),
                })

        # فقط وقتی تمام شارژهای این محاسبه اعلان شده‌اند،
        # محاسبه نهایی می‌شود.
        remaining_notifications = get_calculation_charges(
            calculation
        ).filter(
            send_notification=False,
            is_paid=False,
        ).exists()

        if not remaining_notifications:
            calculation.status = "finalized"
            calculation.is_finalized = True
            calculation.finalized_at = timezone.now()

            calculation.save(update_fields=[
                "status",
                "is_finalized",
                "finalized_at",
                "updated_at",
            ])

        else:
            calculation.status = "calculated"
            calculation.save(update_fields=[
                "status",
                "updated_at",
            ])

        return Response({
            "success": True,
            "message": (
                "اعلان شارژ ثبت شد."
                if not send_sms
                else "اعلان شارژ ثبت شد و درخواست ارسال پیامک انجام شد."
            ),
            "created_count": len(notification_charges),
            "sms_success": sms_success,
            "sms_message": sms_message,
        })


class ManagerChargeCalculationCancelAPIView(
    ManagerChargeCalculationBaseAPIView
):

    @transaction.atomic
    def post(self, request, pk):
        calculation, error = self.get_calculation(
            request,
            pk,
        )

        if error:
            return error

        unit_ids = request.data.get("unit_ids", [])

        if isinstance(unit_ids, str) and unit_ids == "all":
            unit_ids = ["all"]

        if not isinstance(unit_ids, list):
            return api_error("unit_ids باید آرایه باشد.")

        ct = get_calculation_content_type()

        # تمام شارژهای مربوط به همین محاسبه
        charges = get_calculation_charges(
            calculation
        ).select_for_update()

        # تعیین واحدهای هدف
        if unit_ids == ["all"]:
            target_charges = charges
        else:
            try:
                ids = list(dict.fromkeys(
                    int(value) for value in unit_ids
                ))
            except (TypeError, ValueError):
                return api_error(
                    "شناسه واحدها معتبر نیست."
                )

            if not ids:
                return api_error(
                    "حداقل یک واحد باید انتخاب شود."
                )

            valid_ids = set(
                Unit.objects.filter(
                    myhouse=calculation.house,
                    is_active=True,
                    id__in=ids,
                ).values_list("id", flat=True)
            )

            if valid_ids != set(ids):
                return api_error(
                    "برخی واحدها غیرفعال یا متعلق به ساختمان دیگری هستند."
                )

            target_charges = charges.filter(
                unit_id__in=valid_ids
            )

        # اگر بین شارژهای انتخاب‌شده پرداختی وجود دارد،
        # حذف یا بازنشانی آن‌ها مجاز نیست.
        if target_charges.filter(is_paid=True).exists():
            return api_error(
                "حداقل یکی از واحدهای انتخاب‌شده پرداخت انجام داده است؛ "
                "لغو و حذف شارژ آن واحد امکان‌پذیر نیست.",
                status.HTTP_409_CONFLICT,
            )

        # تعداد رکوردهایی که در این عملیات حذف می‌شوند
        deleted_count = target_charges.count()

        # حذف شارژهای محاسبه‌شده برای واحدهای هدف؛
        # شامل شارژهای اعلان‌شده و اعلان‌نشده
        target_charges.delete()

        # بررسی اینکه آیا هنوز رکورد شارژی برای این محاسبه باقی مانده است
        remaining_charges = get_calculation_charges(
            calculation
        ).exists()

        # فقط وقتی هیچ شارژی باقی نمانده، محاسبه را از ابتدا آماده کن
        if not remaining_charges:
            calculation.is_finalized = False
            calculation.status = "draft"
            calculation.finalized_at = None

            calculation.save(update_fields=[
                "is_finalized",
                "status",
                "finalized_at",
                "updated_at",
            ])

        return Response({
            "success": True,
            "message": (
                "شارژهای انتخاب‌شده حذف شدند. "
                "در صورت حذف تمام شارژهای محاسبه، وضعیت به پیش‌نویس برگشت."
            ),
            "deleted_count": deleted_count,
            "status": calculation.status,
            "is_finalized": calculation.is_finalized,
        })


# ---------------------------------------
# Civil Charge
# ---------------------------------------


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
        raise ValueError("برای مبلغ باقی‌مانده، تعداد اقساط باید بیشتر از صفر باشد؛ برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید.")

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
        "installment_amount_per_unit": ((total - prepayment_total) // count // installment_count) if installment_count else 0,
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
            return Response({"success": False, "message": "ساختمان فعالی برای مدیر پیدا نشد."}, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist("document")
        if len(files) > 2:
            return Response({"success": False, "message": "حداکثر دو فایل مجاز است."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        parsed_date = civil_parse_date(data.get("first_due_date"))
        if not parsed_date:
            return Response({"success": False, "message": "تاریخ اولین سررسید معتبر نیست.", "errors": {"first_due_date": ["تاریخ را به صورت YYYY-MM-DD وارد کنید."]}}, status=status.HTTP_400_BAD_REQUEST)
        data["first_due_date"] = jdatetime.date.fromgregorian(date=parsed_date).strftime("%Y-%m-%d")
        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0
        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = CivilForm(data=data, files=request.FILES)
        if not form.is_valid():
            return Response({"success": False, "message": "اطلاعات شارژ عمرانی معتبر نیست.", "errors": form.errors.get_json_data()}, status=status.HTTP_400_BAD_REQUEST)

        amount = form.cleaned_data["amount"]
        prepayment = form.cleaned_data.get("prepayment") or 0
        installment_count = form.cleaned_data.get("installment_count") or 0
        if amount <= 0:
            return Response({"success": False, "message": "مبلغ شارژ باید بیشتر از صفر باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if prepayment < 0 or prepayment > amount:
            return Response({"success": False, "message": "پیش‌پرداخت باید بین صفر و مبلغ شارژ باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if installment_count < 0:
            return Response({"success": False, "message": "تعداد اقساط نمی‌تواند منفی باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if installment_count == 0 and prepayment not in (0, amount):
            return Response({"success": False, "message": "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر وارد کنید؛ برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."}, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({"success": False, "message": "ثبت شارژ و محاسبه اقساط انجام نشد."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = civil_serialize(civil, request)
        result["calculation"] = calculation
        return Response({"success": True, "message": "شارژ عمرانی ثبت و اقساط آن محاسبه شد.", "result": result}, status=status.HTTP_201_CREATED)


class ManagerCivilChargeDetailAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get_civil(self, request, civil_id):
        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None

        return CivilManage.objects.filter(
            id=civil_id,
            user=request.user,
            house=house,
        ).prefetch_related("civil_documents").first()

    def put(self, request, civil_id):
        civil = self.get_civil(request, civil_id)
        if not civil:
            return Response({"success": False, "message": "شارژ عمرانی پیدا نشد."}, status=status.HTTP_404_NOT_FOUND)

        existing = CivilInstallment.objects.filter(civil_manage=civil)
        if existing.filter(send_notification=True).exists():
            return Response({"success": False, "message": "این شارژ قبلاً اعلان شده است و برای جلوگیری از تغییر سوابق، قابل ویرایش نیست."}, status=status.HTTP_400_BAD_REQUEST)
        if existing.filter(is_paid=True).exists():
            return Response({"success": False, "message": "این شارژ دارای قسط پرداخت‌شده است و امکان بازسازی اقساط آن وجود ندارد."}, status=status.HTTP_400_BAD_REQUEST)

        files = request.FILES.getlist("document")
        if len(files) > 2:
            return Response({"success": False, "message": "حداکثر دو فایل جدید مجاز است."}, status=status.HTTP_400_BAD_REQUEST)

        data = request.data.copy()
        raw_date = data.get("first_due_date")
        if raw_date:
            parsed_date = civil_parse_date(raw_date)
            if not parsed_date:
                return Response({"success": False, "message": "تاریخ اولین سررسید معتبر نیست."}, status=status.HTTP_400_BAD_REQUEST)
            data["first_due_date"] = jdatetime.date.fromgregorian(date=parsed_date).strftime("%Y-%m-%d")
        if data.get("prepayment") in (None, ""):
            data["prepayment"] = 0
        if data.get("installment_count") in (None, ""):
            data["installment_count"] = 0

        form = CivilForm(data=data, files=request.FILES, instance=civil)
        if not form.is_valid():
            return Response({"success": False, "message": "اطلاعات شارژ عمرانی معتبر نیست.", "errors": form.errors.get_json_data()}, status=status.HTTP_400_BAD_REQUEST)

        amount = form.cleaned_data["amount"]
        prepayment = form.cleaned_data.get("prepayment") or 0
        installment_count = form.cleaned_data.get("installment_count") or 0
        if amount <= 0:
            return Response({"success": False, "message": "مبلغ شارژ باید بیشتر از صفر باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if prepayment < 0 or prepayment > amount:
            return Response({"success": False, "message": "پیش‌پرداخت باید بین صفر و مبلغ شارژ باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if installment_count < 0:
            return Response({"success": False, "message": "تعداد اقساط نمی‌تواند منفی باشد."}, status=status.HTTP_400_BAD_REQUEST)
        if installment_count == 0 and prepayment not in (0, amount):
            return Response({"success": False, "message": "برای مبلغ باقی‌مانده، تعداد اقساط را بیشتر از صفر وارد کنید؛ برای پرداخت یکجا پیش‌پرداخت و تعداد اقساط را صفر بگذارید."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                CivilInstallment.objects.filter(civil_manage=civil, send_notification=False, is_paid=False).delete()
                civil = form.save(commit=False)
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
            logging.getLogger(__name__).exception("Updating civil charge/installments failed")
            return Response({"success": False, "message": "ویرایش شارژ و محاسبه مجدد اقساط انجام نشد."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        result = civil_serialize(civil, request)
        result["calculation"] = calculation
        return Response({"success": True, "message": "شارژ عمرانی و اقساط آن ویرایش شدند.", "result": result}, status=status.HTTP_200_OK)

    def delete(self, request, civil_id):
        civil = self.get_civil(request, civil_id)

        if not civil:
            return Response({
                "success": False,
                "message": "شارژ عمرانی پیدا نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        # از حذف سوابق مالی پرداخت‌شده جلوگیری می‌کنیم.
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
            import logging
            logging.getLogger(__name__).exception(
                "Deleting civil charge failed"
            )
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
        status_residence = str(
            getattr(unit, "status_residence", "") or ""
        ).strip().lower()

        active_renters = list(
            getattr(unit, "active_renters_for_charge", [])
        )

        # واحد خالی
        if status_residence == "empty":
            return {
                "resident_type": "empty",
                "resident_name": "",
                "people_count": 0,
            }

        # مستأجر فعال
        if active_renters:
            renter_names = [
                str(renter.renter_name).strip()
                for renter in active_renters
                if getattr(renter, "renter_name", None)
                and str(renter.renter_name).strip()
            ]

            people_count = sum(
                max(
                    int(
                        getattr(renter, "renter_people_count", 0) or 0
                    ),
                    0,
                )
                for renter in active_renters
            )

            return {
                "resident_type": "renter",
                "resident_name": "، ".join(renter_names),
                "people_count": people_count,
            }

        # مالک
        if status_residence == "occupied":
            return {
                "resident_type": "owner",
                "resident_name": str(
                    getattr(unit, "owner_name", "") or ""
                ).strip(),
                "people_count": max(
                    int(getattr(unit, "owner_people_count", 0) or 0),
                    0,
                ),
            }

        return {
            "resident_type": "empty",
            "resident_name": "",
            "people_count": 0,
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
            return Response({"success": False, "message": "هیچ واحد معتبری در محدوده این شارژ انتخاب نشده است."}, status=status.HTTP_400_BAD_REQUEST)

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
            return Response({"success": False, "message": "ثبت وضعیت ارسال شارژ انجام نشد."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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


# =============================================
#             MyCharge
# =============================================

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
                "id": item.id,

                "unit_id": unit.id,
                "unit_number": str(unit.unit),

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
                "payment_date": (
                    item.payment_date.isoformat()
                    if item.payment_date else None
                ),

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
                    "cart_number": bank.cart_number,
                    "is_default": bank.is_default,
                    "label": (
                        f"{bank.bank_name} - {bank.cart_number}"
                        + (" (پیش‌فرض)" if bank.is_default else "")
                    ),
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
            payment_date = timezone.localdate()

        if payment_date > timezone.localdate():
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

                # ------------------------------------------
                # ۱. پیدا کردن سند صندوق
                # ------------------------------------------
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

                # ------------------------------------------
                # ۲. پیدا کردن سند بانکی
                #
                # deposit در این پروژه content_object=unit
                # دریافت می‌کند، نه UnifiedCharge.
                # ------------------------------------------
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

                # ------------------------------------------
                # ۳. حذف اسناد و بازمحاسبه موجودی بانک
                # ------------------------------------------
                bank_fund.delete()

                # از تابع بازمحاسبه خود پروژه استفاده می‌کنیم؛
                # موجودی را مستقیماً کم نمی‌کنیم.
                recalculate_bank_balance(bank)

                # ------------------------------------------
                # ۴. حذف سند صندوق و بازمحاسبه
                # ------------------------------------------
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

                # ------------------------------------------
                # ۵. برگرداندن شارژ به حالت پرداخت‌نشده
                # ------------------------------------------
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
