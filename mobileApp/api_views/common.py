"""Shared imports and module-level constants for mobile API views.
Generated from the original views.py; keep imports here to avoid duplication.
"""
import datetime
import json
import logging
import os
import secrets
import uuid
from collections import OrderedDict, defaultdict
from datetime import date
import jdatetime
from PIL import UnidentifiedImageError
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, EmptyPage
from django.db.models import Count, Q, Sum, ProtectedError, Prefetch, F
from django.http import QueryDict
from django.utils import timezone
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.parsers import JSONParser, MultiPartParser, FormParser
import requests
from django.contrib.contenttypes.models import ContentType
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from admin_panel.forms import FixChargeForm, AreaChargeForm, PersonChargeForm, FixAreaChargeForm, FixPersonChargeForm, \
    PersonAreaChargeForm, PersonAreaFixChargeForm, VariableFixChargeForm, CivilForm, SewageForm
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
    ChargeAllocation, CivilDocument, ExpenseCategory, ExpenseDocument, ThirdParty, Income, IncomeCategory, \
    IncomeDocument, ReceiveMoney, ReceiveDocument, PayDocument, PayMoney, MaintenanceDocument, Property, \
    PropertyDocument, SewageDocument, AdminFund, MiddleMessageReadStatus, AdminMessageToMiddle, SubscriptionPlan, \
    AppVersion, AppInstallation
from home.models import ContactUs
from middleAdmin_panel.services.bank_balance_service import recalculate_bank_balance
from middleAdmin_panel.services.bank_services import BankTransactionService, validate_bank_transaction_date
from notifications.models import SupportUser, SupportMessage, Notification, SupportFile, AdminTicketFile, \
    AdminTicketMessage, AdminTicket, MiddleAdminNotification
from notifications.services.sms_service import SmsService, normalize_mobile
from polls_app.models import Poll, Vote, Choice, Question
from user_app.models import Unit, HousePaymentGateway, Renter, Bank, MyHouse, UserPayMoney, UnitResidenceHistory
from ..serializers import (
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
    ManagerThirdPartySerializer, ManagerAdminFundSerializer, ManagerAdminMessageSerializer, ContactUsSerializer,

)
from django.core.exceptions import ValidationError as DjangoValidationError

User = get_user_model()
logger = logging.getLogger(__name__)
VALID_BASES = {"equal", "area", "person"}
VALID_SCOPES = {"all", "occupied", "vacant", "selected"}
