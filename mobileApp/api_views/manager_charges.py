"""Manager Charges API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
