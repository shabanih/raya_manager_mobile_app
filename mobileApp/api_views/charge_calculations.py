"""Charge Calculations API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
