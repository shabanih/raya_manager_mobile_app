"""Finance API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ManagerFinancialCommonMixin:
    """
    توابع مشترک عملیات مالی مدیر ساختمان.

    کلاس استفاده‌کننده باید متد get_house(request) داشته باشد
    و خروجی آن به صورت (house, error) باشد.
    """

    def get_manager_banks_response(self, request):
        """
        دریافت حساب‌های بانکی فعال ساختمان مدیر.
        """
        house, error = self.get_house(request)

        if error:
            return error

        banks = Bank.objects.filter(
            user=request.user,
            house=house,
            is_active=True,
        ).order_by("-is_default", "bank_name")

        return Response({
            "success": True,
            "results": [
                {
                    "id": bank.id,
                    "bank_name": bank.bank_name,
                    "account_no": bank.account_no,
                    "account_holder_name": bank.account_holder_name,
                    "is_default": bank.is_default,
                    "current_balance": str(
                        bank.current_balance or 0
                    ),
                }
                for bank in banks
            ],
        })

    def get_manager_payers_response(self, request):
        """
        دریافت مالک، مستأجر یا شخص ثالث ساختمان مدیر.

        پارامترها:
            type=owner|renter|other
            search=عبارت جست‌وجو
            limit=تعداد نتایج (۱ تا ۱۰۰)
        """
        house, error = self.get_house(request)

        if error:
            return error

        payer_type = (
                request.query_params.get("type") or ""
        ).strip().lower()

        query = (
                request.query_params.get("search") or ""
        ).strip()

        try:
            limit = min(
                max(
                    int(request.query_params.get("limit", 30)),
                    1,
                ),
                100,
            )
        except (TypeError, ValueError):
            limit = 30

        managed_users = User.objects.filter(
            Q(manager=request.user) | Q(pk=request.user.pk)
        )

        # -----------------------------------------------------
        # مالک
        # -----------------------------------------------------
        if payer_type == "owner":
            units = Unit.objects.filter(
                user__in=managed_users,
                myhouse=house,
                is_active=True,
            ).exclude(
                Q(owner_name__isnull=True)
                | Q(owner_name__exact="")
            )

            if query:
                units = units.filter(
                    Q(owner_name__icontains=query)
                    | Q(unit__icontains=query)
                    | Q(owner_mobile__icontains=query)
                )

            units = units.order_by("unit", "id")[:limit]

            results = [
                {
                    "id": unit.id,
                    "unit_id": unit.id,
                    "name": (unit.owner_name or "").strip(),
                    "unit": unit.unit,
                    "mobile": unit.owner_mobile or "",
                    "label": (
                        f"واحد {unit.unit} - "
                        f"مالک: {(unit.owner_name or '').strip()}"
                    ),
                }
                for unit in units
            ]

        # -----------------------------------------------------
        # مستأجر
        # -----------------------------------------------------
        elif payer_type == "renter":
            renters = Renter.objects.filter(
                unit__user__in=managed_users,
                unit__myhouse=house,
                unit__is_active=True,
                renter_is_active=True,
            ).filter(
                Q(renter_name__isnull=False)
            ).exclude(
                renter_name__exact=""
            ).select_related(
                "unit"
            ).order_by(
                "unit__unit", "id"
            )

            if query:
                renters = renters.filter(
                    Q(renter_name__icontains=query)
                    | Q(renter_mobile__icontains=query)
                    | Q(unit__unit__icontains=query)
                )

            renters = renters[:limit]

            results = [
                {
                    "id": renter.id,
                    "unit_id": renter.unit_id,
                    "name": (renter.renter_name or "").strip(),
                    "unit": renter.unit.unit,
                    "mobile": renter.renter_mobile or "",
                    "label": (
                        f"واحد {renter.unit.unit} - "
                        f"مستأجر: "
                        f"{(renter.renter_name or '').strip()}"
                    ),
                }
                for renter in renters
            ]

        # -----------------------------------------------------
        # شخص ثالث
        # -----------------------------------------------------
        elif payer_type == "other":
            third_parties = ThirdParty.objects.filter(
                house=house,
                is_active=True,
            )

            if query:
                third_parties = third_parties.filter(
                    Q(name__icontains=query)
                    | Q(mobile__icontains=query)
                )

            third_parties = third_parties.order_by(
                "name", "id"
            )[:limit]

            results = [
                {
                    "id": person.id,
                    "name": person.name or "",
                    "mobile": person.mobile or "",
                    "label": person.name or "",
                }
                for person in third_parties
            ]

        else:
            return Response(
                {
                    "success": False,
                    "message": "نوع شخص معتبر نیست.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            "success": True,
            "results": results,
        })
class ManagerExpenseBaseAPIView(ManagerFinancialCommonMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response(
                {
                    "success": False,
                    "message": "شما دسترسی مدیر ساختمان را ندارید.",
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response(
                {
                    "success": False,
                    "message": "ساختمان فعالی برای شما یافت نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        return house, None

    @staticmethod
    def normalize_digits(value):
        """تبدیل ارقام فارسی و عربی به انگلیسی."""
        if value is None:
            return value

        value = str(value)

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )

        return value.translate(translation).replace(",", "").replace("٬", "")


    @staticmethod
    def category_queryset(user):
        return ExpenseCategory.objects.filter(
            user=user,
            is_active=True,
        )

    @staticmethod
    def expense_queryset(user, house):
        return Expense.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "category",
            "unit",
            "bank",
            "receiver_renter",
            "receiver_third_party",
        ).prefetch_related("documents")

    @staticmethod
    def serialize_category(category):
        return {
            "id": category.id,
            "title": category.title,
            "is_default": category.is_default,
            "is_active": category.is_active,
        }

    @staticmethod
    def serialize_expense(expense):
        bank = getattr(expense, "bank", None)

        return {
            "id": expense.id,
            "bank_id": expense.bank_id,
            "bank_name": (
                getattr(bank, "bank_name", None) if bank else None
            ),
            "account_no": (
                getattr(bank, "account_no", None) if bank else None
            ),
            "receiver_type": expense.receiver_type or "",
            "receiver_renter_id": expense.receiver_renter_id,
            "receiver_third_party_id": expense.receiver_third_party_id,
            "receiver_name": expense.receiver_name or "",
            "unit_id": expense.unit_id,
            "category_id": expense.category_id,
            "category": expense.category.title if expense.category else None,
            "description": expense.description or "",
            "details": expense.details or "",
            "amount": str(expense.amount),
            "date": expense.date.isoformat() if expense.date else None,
            "doc_no": expense.doc_no or "",
            "financial_document_number": expense.financial_document_number,
            "is_paid": expense.is_paid,
            "payment_date": (
                expense.payment_date.isoformat()
                if expense.payment_date else None
            ),
            "transaction_reference": expense.transaction_reference or "",
            "documents": [
                {
                    "id": document.id,
                    "url": (
                        document.document.url
                        if document.document else None
                    ),
                }
                for document in expense.documents.all()
            ],
        }

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("مبلغ هزینه معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("مبلغ هزینه باید بیشتر از صفر باشد.")

        return amount

    def parse_expense_date(self, value):
        value = self.normalize_digits(value)
        parsed = parse_date(value) if value else None

        if not parsed:
            raise ValueError(
                "تاریخ نامعتبر است؛ تاریخ را به شکل YYYY-MM-DD ارسال کنید."
            )

        return parsed

    def get_category(self, user, category_id):
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise ValueError("سرفصل هزینه معتبر نیست.")

        category = self.category_queryset(user).filter(
            pk=category_id
        ).first()

        if not category:
            raise ValueError("سرفصل هزینه یافت نشد یا غیرفعال است.")

        return category

    @staticmethod
    def get_uploaded_documents(request):
        # هر دو قالب documents و document پشتیبانی می‌شوند.
        files = request.FILES.getlist("documents")
        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError("حداکثر دو مدرک برای هر هزینه مجاز است.")

        return files
class ManagerExpenseCategoriesAPIView(ManagerExpenseBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        categories = self.category_queryset(request.user).order_by(
            "-is_default", "title"
        )

        return Response({
            "success": True,
            "results": [
                self.serialize_category(category)
                for category in categories
            ],
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        title = (request.data.get("title") or "").strip()

        if not title:
            return Response(
                {"success": False, "message": "عنوان سرفصل الزامی است."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        duplicate = ExpenseCategory.objects.filter(
            user=request.user,
            title__iexact=title,
            is_active=True,
        ).exists()

        if duplicate:
            return Response(
                {
                    "success": False,
                    "message": "این سرفصل قبلاً ثبت شده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        category = ExpenseCategory.objects.create(
            user=request.user,
            title=title,
            is_active=True,
            is_default=False,
        )

        return Response(
            {
                "success": True,
                "message": "سرفصل هزینه با موفقیت ثبت شد.",
                "category": self.serialize_category(category),
            },
            status=status.HTTP_201_CREATED,
        )
class ManagerExpenseCategoryDetailAPIView(ManagerExpenseBaseAPIView):

    def get_category(self, request, pk):
        return get_object_or_404(
            ExpenseCategory,
            pk=pk,
            user=request.user,
            is_default=False,
        )

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        category = self.get_category(request, pk)

        title = request.data.get("title")
        if title is not None:
            title = title.strip()

            if not title:
                return Response(
                    {
                        "success": False,
                        "message": "عنوان سرفصل نمی‌تواند خالی باشد.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            duplicate = ExpenseCategory.objects.filter(
                user=request.user,
                title__iexact=title,
                is_active=True,
            ).exclude(pk=category.pk).exists()

            if duplicate:
                return Response(
                    {
                        "success": False,
                        "message": "سرفصلی با این عنوان وجود دارد.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            category.title = title

        if "is_active" in request.data:
            raw_active = request.data.get("is_active")

            if raw_active not in (True, False, "true", "false", 1, 0):
                return Response(
                    {
                        "success": False,
                        "message": "مقدار is_active معتبر نیست.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            category.is_active = raw_active in (True, "true", 1)

        category.save()

        return Response({
            "success": True,
            "message": "سرفصل با موفقیت ویرایش شد.",
            "category": self.serialize_category(category),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        category = self.get_category(request, pk)

        has_expenses = Expense.objects.filter(
            category=category
        ).exists()

        if Expense.objects.filter(category=category).exists():
            return Response(
                {
                    "success": False,
                    "message": "این سرفصل در ثبت هزینه استفاده شده است و امکان حذف آن وجود ندارد."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if has_expenses:
            category.is_active = False
            category.save(update_fields=["is_active"])

            message = (
                "سرفصل غیرفعال شد؛ سوابق هزینه‌های وابسته حفظ شدند."
            )
        else:
            category.delete()
            message = "سرفصل با موفقیت حذف شد."

        return Response({
            "success": True,
            "message": message,
        })
class ManagerExpenseAPIView(ManagerExpenseBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        expenses = self.expense_queryset(request.user, house)

        payment_status = request.query_params.get("payment_status")
        if payment_status == "paid":
            expenses = expenses.filter(is_paid=True)
        elif payment_status == "unpaid":
            expenses = expenses.filter(is_paid=False)

        category_id = request.query_params.get("category_id")
        if category_id:
            expenses = expenses.filter(category_id=category_id)

        expenses = expenses.order_by("-date", "-id")

        return Response({
            "success": True,
            "results": [
                self.serialize_expense(expense)
                for expense in expenses
            ],
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            category = self.get_category(
                request.user,
                request.data.get("category_id"),
            )
            amount = self.parse_amount(request.data.get("amount"))
            expense_date = self.parse_expense_date(
                request.data.get("date")
            )
            documents = self.get_uploaded_documents(request)

        except ValueError as exc:
            return Response(
                {"success": False, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        description = (request.data.get("description") or "").strip()
        details = (request.data.get("details") or "").strip()
        doc_no_value = request.data.get('doc_no')
        if doc_no_value is not None:
            doc_no_value = str(doc_no_value).strip()

        if not doc_no_value:
            doc_no_value = None

        if not description:
            return Response(
                {
                    "success": False,
                    "message": "شرح هزینه الزامی است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            expense = Expense.objects.create(
                user=request.user,
                house=house,
                category=category,
                amount=amount,
                date=expense_date,
                description=description,
                details=details,
                doc_no=doc_no_value,
                is_paid=False,
                is_active=True,
            )

            expense.financial_document_number = (
                get_next_financial_document_number(house)
            )
            expense.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                ExpenseDocument.objects.create(
                    expense=expense,
                    document=uploaded_file,
                )

        expense = self.expense_queryset(
            request.user, house
        ).get(pk=expense.pk)

        return Response(
            {
                "success": True,
                "message": "هزینه با موفقیت ثبت شد.",
                "expense": self.serialize_expense(expense),
            },
            status=status.HTTP_201_CREATED,
        )
class ManagerExpenseDetailAPIView(ManagerExpenseBaseAPIView):

    def get_expense(self, request, house, pk):
        return get_object_or_404(
            self.expense_queryset(request.user, house),
            pk=pk,
        )

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        expense = self.get_expense(request, house, pk)

        if expense.is_paid:
            return Response(
                {
                    "success": False,
                    "message": (
                        "هزینه پرداخت شده است؛ ابتدا باید پرداخت "
                        "از مسیر مالی معتبر لغو شود."
                    ),
                },
                status=status.HTTP_409_CONFLICT,
            )

        try:
            category = None
            if "category_id" in request.data:
                category = self.get_category(
                    request.user,
                    request.data.get("category_id"),
                )

            amount = None
            if "amount" in request.data:
                amount = self.parse_amount(request.data.get("amount"))

            expense_date = None
            if "date" in request.data:
                expense_date = self.parse_expense_date(
                    request.data.get("date")
                )

            new_documents = self.get_uploaded_documents(request)

        except ValueError as exc:
            return Response(
                {"success": False, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if len(expense.documents.all()) + len(new_documents) > 2:
            return Response(
                {
                    "success": False,
                    "message": (
                        "مجموع مدارک هزینه نمی‌تواند بیشتر از دو فایل باشد."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            if category is not None:
                expense.category = category

            if amount is not None:
                expense.amount = amount

            if expense_date is not None:
                expense.date = expense_date

            if "description" in request.data:
                description = (
                        request.data.get("description") or ""
                ).strip()

                if not description:
                    return Response(
                        {
                            "success": False,
                            "message": "شرح هزینه نمی‌تواند خالی باشد.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                expense.description = description

            if "details" in request.data:
                expense.details = (
                        request.data.get("details") or ""
                ).strip()

            if "doc_no" in request.data:
                expense.doc_no = (
                        request.data.get("doc_no") or ""
                ).strip()

            # شماره سند مالی عمداً تغییر داده نمی‌شود.
            expense.save()

            for uploaded_file in new_documents:
                ExpenseDocument.objects.create(
                    expense=expense,
                    document=uploaded_file,
                )

        expense = self.expense_queryset(
            request.user, house
        ).get(pk=expense.pk)

        return Response({
            "success": True,
            "message": "هزینه با موفقیت ویرایش شد.",
            "expense": self.serialize_expense(expense),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            expense = self.get_expense(
                request, house, pk
            )

            if expense.is_paid:
                return Response({
                    "success": False,
                    "message": "هزینه پرداخت‌شده قابل حذف نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            expense.delete()

        return Response({
            "success": True,
            "message": "هزینه با موفقیت حذف شد.",
        })

class ManagerExpenseDocumentAPIView(ManagerExpenseBaseAPIView):

    def get_expense(self, request, house, pk):
        return get_object_or_404(
            self.expense_queryset(request.user, house),
            pk=pk,
        )

    def delete(self, request, pk, document_id):
        house, error = self.get_house(request)
        if error:
            return error

        expense = self.get_expense(request, house, pk)

        if expense.is_paid:
            return Response(
                {
                    "success": False,
                    "message": "پیوست هزینه پرداخت‌شده قابل حذف نیست.",
                },
                status=status.HTTP_409_CONFLICT,
            )

        document = expense.documents.filter(
            pk=document_id
        ).first()

        if not document:
            return Response(
                {
                    "success": False,
                    "message": "فایل پیوست یافت نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        with transaction.atomic():
            file_name = (
                document.document.name
                if document.document
                else None
            )

            if file_name:
                transaction.on_commit(
                    lambda: document.document.storage.delete(file_name)
                )

            document.delete()

        return Response({
            "success": True,
            "message": "فایل پیوست با موفقیت حذف شد.",
        })
class ManagerExpensePayAPIView(ManagerExpenseBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        print("PAYMENT DEBUG USER:", request.user.id)
        print("PAYMENT DEBUG HOUSE:", house.id)
        print("PAYMENT DEBUG RENTER:", request.data.get("receiver_renter_id"))

        renter_id = request.data.get("receiver_renter_id")

        print(
            "RENTER MATCH WITHOUT FILTERS:",
            Renter.objects.filter(pk=renter_id).values(
                "id",
                "user_id",
                "myhouse_id",
                "unit_id",
                "renter_is_active",
                "unit__myhouse_id",
                "unit__is_active",
            ).first()
        )

        try:
            payment_date = self.parse_expense_date(
                request.data.get("payment_date")
            )
            if payment_date.date() > date.today() if hasattr(payment_date, "date") else payment_date > date.today():
                return Response(
                    {
                        "success": False,
                        "message": "تاریخ پرداخت نمی‌تواند بعد از تاریخ امروز باشد.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
        except ValueError as exc:
            return Response(
                {"success": False, "message": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank_id = request.data.get("bank_id")
        receiver_type = (
                request.data.get("receiver_type") or ""
        ).strip()

        if not bank_id:
            return Response({
                "success": False,
                "message": "انتخاب حساب بانکی الزامی است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if receiver_type not in ("owner", "renter", "other"):
            return Response({
                "success": False,
                "message": "نوع دریافت‌کننده معتبر نیست.",
            }, status=status.HTTP_400_BAD_REQUEST)

        bank = Bank.objects.filter(
            pk=bank_id,
            user=request.user,
            house=house,
            is_active=True,
        ).first()

        if not bank:
            return Response({
                "success": False,
                "message": "حساب بانکی انتخاب‌شده معتبر نیست.",
            }, status=status.HTTP_400_BAD_REQUEST)

        receiver_name = ""
        receiver_renter = None
        receiver_third_party = None
        unit = None

        if receiver_type == "owner":
            unit_id = request.data.get("unit_id")

            unit = Unit.objects.filter(
                pk=unit_id,
                myhouse=house,
                is_active=True,
            ).first()

            if not unit:
                return Response({
                    "success": False,
                    "message": "واحد انتخاب‌شده معتبر نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            receiver_name = (unit.owner_name or "").strip()

            if not receiver_name:
                return Response({
                    "success": False,
                    "message": "نام مالک این واحد ثبت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            print("RECEIVER TYPE:", receiver_type)
            print("UNIT ID RECEIVED:", request.data.get("unit_id"))
            print("REQUEST USER ID:", request.user.id)
            print("HOUSE ID:", house.id)

            unit_id = request.data.get("unit_id")

            print(
                "UNIT DATA:",
                Unit.objects.filter(pk=unit_id).values(
                    "id",
                    "user_id",
                    "myhouse_id",
                    "is_active",
                    "owner_name",
                ).first()
            )



        elif receiver_type == "renter":

            renter_id = request.data.get("receiver_renter_id")

            receiver_renter = Renter.objects.filter(

                pk=renter_id,

                myhouse=house,

                unit__myhouse=house,

                renter_is_active=True,

                unit__is_active=True,

            ).select_related("unit").first()

            if not receiver_renter:
                return Response({

                    "success": False,

                    "message": "مستأجر فعال معتبری در این ساختمان یافت نشد.",

                }, status=status.HTTP_400_BAD_REQUEST)

            unit = receiver_renter.unit

            receiver_name = (

                    receiver_renter.renter_name or ""

            ).strip()

            if not receiver_name:
                return Response({

                    "success": False,

                    "message": "نام مستأجر مشخص نیست.",

                }, status=status.HTTP_400_BAD_REQUEST)

        else:
            third_party_id = request.data.get(
                "receiver_third_party_id"
            )

            receiver_third_party = ThirdParty.objects.filter(
                pk=third_party_id,
                house=house,
                is_active=True,
            ).first()

            if not receiver_third_party:
                return Response({
                    "success": False,
                    "message": "شخص ثالث معتبر یافت نشد.",
                }, status=status.HTTP_400_BAD_REQUEST)

            receiver_name = (
                    receiver_third_party.name or ""
            ).strip()

            if not receiver_name:
                return Response({
                    "success": False,
                    "message": "نام شخص ثالث مشخص نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

        transaction_reference = (
                request.data.get("transaction_reference") or ""
        ).strip()

        if len(transaction_reference) > 15:
            return Response({
                "success": False,
                "message": (
                    "کد پیگیری حداکثر می‌تواند ۱۵ کاراکتر باشد."
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                expense = self.expense_queryset(
                    request.user, house
                ).select_for_update().filter(pk=pk).first()

                if not expense:
                    return Response({
                        "success": False,
                        "message": "هزینه یافت نشد.",
                    }, status=status.HTTP_404_NOT_FOUND)

                if expense.is_paid:
                    return Response({
                        "success": False,
                        "message": "این هزینه قبلاً پرداخت شده است.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                expense_ct = ContentType.objects.get_for_model(
                    expense
                )

                # وجود برداشت قبلی برای همین هزینه را بررسی می‌کنیم.
                previous_withdrawal = BankFund.objects.filter(
                    content_type=expense_ct,
                    object_id=expense.pk,
                    transaction_type="withdraw",
                ).exists()

                if previous_withdrawal:
                    return Response({
                        "success": False,
                        "message": (
                            "برای این هزینه قبلاً برداشت بانکی ثبت شده است. "
                            "ابتدا سوابق مالی آن را بررسی کنید."
                        ),
                    }, status=status.HTTP_400_BAD_REQUEST)

                amount = Decimal(str(expense.amount or 0))

                if amount <= 0:
                    return Response({
                        "success": False,
                        "message": "مبلغ هزینه باید بیشتر از صفر باشد.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                fund = BankTransactionService.withdraw(
                    user=request.user,
                    bank=bank,
                    unit=unit,
                    amount=amount,
                    description=(
                                    f"پرداخت هزینه شماره {expense.doc_no}: "
                                    f"{expense.description}"
                                )[:500],
                    content_object=expense,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    receiver_type=receiver_type,
                    receiver_renter=receiver_renter,
                    receiver_name=receiver_name,
                    receiver_third_party=receiver_third_party,
                    house=house,
                    gateway="پرداخت هزینه",
                )

                expense.bank = bank
                expense.payment_date = payment_date
                expense.transaction_reference = (
                        transaction_reference or None
                )
                expense.receiver_type = receiver_type
                expense.receiver_name = receiver_name
                expense.receiver_renter = receiver_renter
                expense.receiver_third_party = receiver_third_party

                # واحد فقط در صورت مشخص بودن گیرنده به‌روزرسانی شود.
                if unit is not None:
                    expense.unit = unit

                expense.is_paid = True

                expense.save(update_fields=[
                    "bank",
                    "payment_date",
                    "transaction_reference",
                    "receiver_type",
                    "receiver_name",
                    "receiver_renter",
                    "receiver_third_party",
                    "unit",
                    "is_paid",
                ])

        except ValidationError as exc:
            return Response({
                "success": False,
                "message": (
                    exc.messages[0]
                    if getattr(exc, "messages", None)
                    else str(exc)
                ),
            }, status=status.HTTP_400_BAD_REQUEST)

        expense = self.expense_queryset(
            request.user, house
        ).get(pk=pk)

        return Response({
            "success": True,
            "message": "پرداخت هزینه با موفقیت ثبت شد.",
            "expense": self.serialize_expense(expense),
        })
class ManagerExpenseBanksAPIView(ManagerExpenseBaseAPIView):

    def get(self, request):
        return self.get_manager_banks_response(request)
class ManagerExpenseReceiversAPIView(ManagerExpenseBaseAPIView):

    def get(self, request):
        return self.get_manager_payers_response(request)
class ManagerExpenseCancelPayAPIView(APIView):

    @transaction.atomic
    def post(self, request, pk, *args, **kwargs):
        # هزینه را قفل می‌کنیم تا پرداخت هم‌زمان تغییر نکند.
        expense = (
            Expense.objects
            .select_for_update()
            .filter(pk=pk)
            .first()
        )

        if expense is None:
            return Response(
                {
                    "success": False,
                    "message": "هزینه پیدا نشد.",
                },
                status=status.HTTP_404_NOT_FOUND,
            )

        if not expense.is_paid:
            return Response(
                {
                    "success": False,
                    "message": "این هزینه قبلاً پرداخت نشده است.",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        expense_ct = ContentType.objects.get_for_model(expense)

        # فقط برداشت اصلی مربوط به همین هزینه.
        original_fund = (
            BankFund.objects
            .select_for_update()
            .filter(
                content_type=expense_ct,
                object_id=expense.pk,
                transaction_type="withdraw",
                is_paid=True,
            )
            .order_by("-pk")
            .first()
        )

        if original_fund is None:
            return Response(
                {
                    "success": False,
                    "message": (
                        "برداشت بانکی مربوط به این هزینه پیدا نشد؛ "
                        "سوابق مالی را بررسی کنید."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # جلوگیری از حذف اشتباه برداشت‌های انتقالی.
        if getattr(original_fund, "transfer_group_id", None):
            return Response(
                {
                    "success": False,
                    "message": (
                        "این تراکنش به انتقال بانکی مرتبط است "
                        "و لغو خودکار آن مجاز نیست."
                    ),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank = original_fund.bank

        # در این قسمت باید مجوز دسترسی مدیر به همین ساختمان
        # و حساب بانکی را مطابق ساختار فعلی پروژه بررسی کنی.

        # برداشت اصلی حذف می‌شود؛ واریز جبرانی ثبت نمی‌کنیم.
        original_fund.delete()

        # محاسبه مجدد موجودی بانک پس از حذف برداشت.
        recalculate_bank_balance(bank)

        # بازگرداندن وضعیت هزینه به پرداخت‌نشده.
        expense.is_paid = False

        # پاک کردن اطلاعات پرداخت در صورت وجود این فیلدها.
        if hasattr(expense, "bank"):
            expense.bank = None

        if hasattr(expense, "payment_date"):
            expense.payment_date = None

        if hasattr(expense, "transaction_reference"):
            expense.transaction_reference = None

        if hasattr(expense, "receiver"):
            expense.receiver = None

        if hasattr(expense, "receiver_name"):
            expense.receiver_name = ""

        expense.save()

        return Response(
            {
                "success": True,
                "message": (
                    "پرداخت هزینه لغو شد و برداشت بانکی حذف گردید. "
                    "اکنون امکان پرداخت مجدد وجود دارد."
                ),
            },
            status=status.HTTP_200_OK,
        )
class ManagerIncomeBaseAPIView(ManagerFinancialCommonMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response({
                "success": False,
                "message": "شما دسترسی مدیر ساختمان را ندارید.",
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response({
                "success": False,
                "message": "ساختمان فعالی برای شما یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return house, None

    @staticmethod
    def normalize_digits(value):
        if value is None:
            return value

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )
        return (
            str(value)
            .translate(translation)
            .replace(",", "")
            .replace("٬", "")
        )

    @staticmethod
    def category_queryset(user):
        return IncomeCategory.objects.filter(
            Q(user=user) | Q(user__isnull=True),
            is_active=True,
        ).distinct()

    @staticmethod
    def income_queryset(user, house):
        return Income.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "category",
            "unit",
            "bank",
            "payer_renter",
            "payer_third_party",
        ).prefetch_related("documents")

    def get_income(self, request, house, pk, lock=False):
        queryset = Income.objects.filter(
            pk=pk,
            user=request.user,
            house=house,
            is_active=True,
        )

        if lock:
            queryset = queryset.select_for_update()

        income = queryset.first()

        if not income:
            return None, Response({
                "success": False,
                "message": "درآمد موردنظر یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return income, None

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("مبلغ درآمد معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("مبلغ درآمد باید بیشتر از صفر باشد.")

        if amount != amount.to_integral_value():
            raise ValueError("مبلغ درآمد باید عدد صحیح باشد.")

        return amount

    def parse_date_value(self, value, label="تاریخ"):
        value = self.normalize_digits(value)
        parsed = parse_date(value) if value else None

        if not parsed:
            raise ValueError(
                f"{label} نامعتبر است؛ قالب YYYY-MM-DD را ارسال کنید."
            )

        return parsed

    def get_category(self, user, category_id):
        try:
            category_id = int(category_id)
        except (TypeError, ValueError):
            raise ValueError("سرفصل درآمد معتبر نیست.")

        category = self.category_queryset(user).filter(
            pk=category_id
        ).first()

        if not category:
            raise ValueError("سرفصل درآمد یافت نشد یا غیرفعال است.")

        return category

    @staticmethod
    def get_uploaded_documents(request):
        files = request.FILES.getlist("documents")

        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError("حداکثر دو مدرک برای هر درآمد مجاز است.")

        return files

    @staticmethod
    def serialize_category(category):
        return {
            "id": category.id,
            "subject": category.subject,
            "is_active": category.is_active,
        }

    @staticmethod
    def serialize_income(income):
        bank = income.bank

        return {
            "id": income.id,
            "bank_id": income.bank_id,
            "bank_name": getattr(bank, "bank_name", None) if bank else None,
            "account_no": getattr(bank, "account_no", None) if bank else None,
            "payer_type": income.payer_type or "",
            "payer_renter_id": income.payer_renter_id,
            "payer_third_party_id": income.payer_third_party_id,
            "payer_name": income.payer_name or "",
            "unit_id": income.unit_id,
            "category_id": income.category_id,
            "category": income.category.subject if income.category else None,
            "description": income.description or "",
            "details": income.details or "",
            "amount": str(income.amount or 0),
            "doc_date": (
                income.doc_date.isoformat() if income.doc_date else None
            ),
            "doc_number": income.doc_number,
            "financial_document_number": income.financial_document_number,
            "is_paid": income.is_paid,
            "payment_date": (
                income.payment_date.isoformat()
                if income.payment_date else None
            ),
            "transaction_reference": income.transaction_reference or "",
            "documents": [
                {
                    "id": document.id,
                    "url": (
                        document.document.url
                        if document.document else None
                    ),
                }
                for document in income.documents.all()
            ],
        }

    def validate_payer(self, request, house, data):
        """
        اعتبارسنجی اختیاری پرداخت‌کننده درآمد.
        """
        payer_type = (data.get("payer_type") or "").strip()

        # در ثبت یا ویرایش درآمد، انتخاب پرداخت‌کننده اختیاری است.
        if not payer_type:
            return {
                "unit": None,
                "payer_type": "",
                "payer_renter": None,
                "payer_third_party": None,
                "payer_name": "",
            }

        unit = None
        payer_renter = None
        payer_third_party = None
        payer_name = ""

        if payer_type not in ("owner", "renter", "other"):
            raise ValueError("نوع پرداخت‌کننده نامعتبر است.")

        if payer_type == "owner":
            try:
                unit_id = int(data.get("unit_id"))
            except (TypeError, ValueError):
                raise ValueError("واحد مالک معتبر نیست.")

            unit = Unit.objects.filter(
                pk=unit_id,
                myhouse=house,
                is_active=True,
                user__manager=request.user,
            ).first()

            if not unit:
                raise ValueError("واحد مالک یافت نشد.")

            payer_name = (unit.owner_name or "").strip()
            if not payer_name:
                raise ValueError("نام مالک این واحد مشخص نیست.")

        elif payer_type == "renter":
            try:
                renter_id = int(data.get("payer_renter_id"))
            except (TypeError, ValueError):
                raise ValueError("مستأجر انتخاب‌شده معتبر نیست.")

            payer_renter = Renter.objects.select_related("unit").filter(
                pk=renter_id,
                renter_is_active=True,
                unit__myhouse=house,
                unit__is_active=True,
                unit__user__manager=request.user,
            ).first()

            if not payer_renter or not payer_renter.unit:
                raise ValueError("مستأجر فعال این ساختمان یافت نشد.")

            unit = payer_renter.unit
            payer_name = (payer_renter.renter_name or "").strip()

            if not payer_name:
                raise ValueError("نام مستأجر مشخص نیست.")

        elif payer_type == "other":
            try:
                third_party_id = int(data.get("payer_third_party_id"))
            except (TypeError, ValueError):
                raise ValueError("شخص ثالث را انتخاب کنید.")

            payer_third_party = ThirdParty.objects.filter(
                pk=third_party_id,
                house=house,
                is_active=True,
            ).first()

            if not payer_third_party:
                raise ValueError("شخص ثالث فعال این ساختمان یافت نشد.")

            payer_name = (payer_third_party.name or "").strip()

            if not payer_name:
                raise ValueError("نام شخص ثالث مشخص نیست.")

            unit = None

        return {
            "unit": unit,
            "payer_type": payer_type,
            "payer_renter": payer_renter,
            "payer_third_party": payer_third_party,
            "payer_name": payer_name,
        }
class ManagerIncomeCategoriesAPIView(ManagerIncomeBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        categories = self.category_queryset(request.user).order_by("subject")

        return Response({
            "success": True,
            "results": [
                self.serialize_category(item)
                for item in categories
            ],
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        subject = str(request.data.get("subject") or "").strip()

        if not subject:
            return Response({
                "success": False,
                "message": "نام سرفصل الزامی است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(subject) > 100:
            return Response({
                "success": False,
                "message": "نام سرفصل نباید بیشتر از ۱۰۰ کاراکتر باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        category = IncomeCategory.objects.create(
            user=request.user,
            subject=subject,
            is_active=True,
        )

        return Response({
            "success": True,
            "message": "سرفصل درآمد ایجاد شد.",
            "result": self.serialize_category(category),
        }, status=status.HTTP_201_CREATED)
class ManagerIncomeCategoryDetailAPIView(ManagerIncomeBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        category = IncomeCategory.objects.filter(
            pk=pk,
            user=request.user,
            is_active=True,
        ).first()

        if not category:
            return Response({
                "success": False,
                "message": "سرفصل اختصاصی یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        subject = str(request.data.get("subject") or "").strip()

        if not subject:
            return Response({
                "success": False,
                "message": "نام سرفصل الزامی است.",
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(subject) > 100:
            return Response({
                "success": False,
                "message": "نام سرفصل نباید بیشتر از ۱۰۰ کاراکتر باشد.",
            }, status=status.HTTP_400_BAD_REQUEST)

        category.subject = subject
        category.save(update_fields=["subject"])

        return Response({
            "success": True,
            "message": "سرفصل درآمد ویرایش شد.",
            "result": self.serialize_category(category),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        category = IncomeCategory.objects.filter(
            pk=pk,
            user=request.user,
            is_active=True,
        ).first()
        if Income.objects.filter(category=category).exists():
            return Response(
                {
                    "success": False,
                    "message": "این سرفصل در ثبت درآمد استفاده شده است و امکان حذف آن وجود ندارد."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not category:
            return Response({
                "success": False,
                "message": "سرفصل اختصاصی یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        if Income.objects.filter(
                category=category,
                is_active=True,
        ).exists():
            category.is_active = False
            category.save(update_fields=["is_active"])
            message = "سرفصل استفاده‌شده غیرفعال شد."
        else:
            category.delete()
            message = "سرفصل حذف شد."

        return Response({
            "success": True,
            "message": message,
        })
class ManagerIncomeAPIView(ManagerIncomeBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        queryset = self.income_queryset(request.user, house)

        payment_status = request.query_params.get("payment_status")
        category_id = request.query_params.get("category_id")

        if payment_status == "paid":
            queryset = queryset.filter(is_paid=True)
        elif payment_status == "unpaid":
            queryset = queryset.filter(is_paid=False)

        if category_id:
            queryset = queryset.filter(category_id=category_id)

        results = [
            self.serialize_income(item)
            for item in queryset.order_by("-created_at")
        ]

        return Response({
            "success": True,
            "count": len(results),
            "results": results,
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            amount = self.parse_amount(request.data.get("amount"))

            doc_date = self.parse_date_value(
                request.data.get("doc_date"),
                "تاریخ سند",
            )

            category = self.get_category(
                request.user,
                request.data.get("category_id"),
            )

            documents = self.get_uploaded_documents(request)

            description = str(
                request.data.get("description") or ""
            ).strip()

            details = str(
                request.data.get("details") or ""
            ).strip()

            if not description:
                raise ValueError("شرح درآمد الزامی است.")

            if len(description) > 4000:
                raise ValueError(
                    "شرح درآمد نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
                )

            doc_number_raw = self.normalize_digits(
                request.data.get("doc_number")
            )

            doc_number = None

            if doc_number_raw not in (None, ""):
                try:
                    doc_number = int(doc_number_raw)
                except (TypeError, ValueError):
                    raise ValueError("شماره سند معتبر نیست.")

            # انتخاب پرداخت‌کننده هنگام ثبت درآمد الزامی نیست.
            payer = self.validate_payer(
                request,
                house,
                request.data,
            )

        except ValueError as exc:
            return Response(
                {
                    "success": False,
                    "message": str(exc),
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            # ابتدا درآمد ایجاد می‌شود.
            income = Income.objects.create(
                user=request.user,
                house=house,
                category=category,
                doc_date=doc_date,
                doc_number=doc_number,
                description=description,
                details=details,
                amount=amount,
                is_paid=False,
                unit=payer["unit"],
                payer_type=payer["payer_type"],
                payer_renter=payer["payer_renter"],
                payer_third_party=payer["payer_third_party"],
                payer_name=payer["payer_name"],
            )

            # مانند ثبت هزینه، شماره سند مالی تولید و ذخیره می‌شود.
            income.financial_document_number = (
                get_next_financial_document_number(house)
            )

            income.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                IncomeDocument.objects.create(
                    income=income,
                    document=uploaded_file,
                )

        income = self.income_queryset(
            request.user,
            house,
        ).get(pk=income.pk)

        return Response(
            {
                "success": True,
                "message": "درآمد با شماره سند مالی ثبت شد.",
                "result": self.serialize_income(income),
            },
            status=status.HTTP_201_CREATED,
        )
class ManagerIncomeDetailAPIView(ManagerIncomeBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            with transaction.atomic():
                income, error = self.get_income(
                    request, house, pk, lock=True
                )
                if error:
                    return error

                if income.is_paid:
                    return Response({
                        "success": False,
                        "message": "درآمد دریافت‌شده قابل ویرایش نیست.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                data = request.data

                if "amount" in data:
                    income.amount = self.parse_amount(data.get("amount"))

                if "doc_date" in data:
                    income.doc_date = self.parse_date_value(
                        data.get("doc_date"), "تاریخ سند"
                    )

                if "category_id" in data:
                    income.category = self.get_category(
                        request.user, data.get("category_id")
                    )

                if "description" in data:
                    description = str(data.get("description") or "").strip()
                    if not description:
                        raise ValueError("شرح درآمد الزامی است.")
                    if len(description) > 4000:
                        raise ValueError("شرح درآمد بیش از حد طولانی است.")
                    income.description = description

                if "details" in data:
                    income.details = str(data.get("details") or "").strip()

                if "doc_number" in data:
                    raw_number = self.normalize_digits(data.get("doc_number"))
                    if raw_number in (None, ""):
                        income.doc_number = None
                    else:
                        try:
                            income.doc_number = int(raw_number)
                        except (TypeError, ValueError):
                            raise ValueError("شماره سند معتبر نیست.")

                if any(key in data for key in (
                        "payer_type",
                        "unit_id",
                        "payer_renter_id",
                        "payer_third_party_id",
                )):
                    payer = self.validate_payer(request, house, data)
                    income.unit = payer["unit"]
                    income.payer_type = payer["payer_type"]
                    income.payer_renter = payer["payer_renter"]
                    income.payer_third_party = payer["payer_third_party"]
                    income.payer_name = payer["payer_name"]

                income.save()

                for uploaded_file in self.get_uploaded_documents(request):
                    if income.documents.count() >= 2:
                        raise ValueError(
                            "هر درآمد حداکثر می‌تواند دو مدرک داشته باشد."
                        )
                    IncomeDocument.objects.create(
                        income=income,
                        document=uploaded_file,
                    )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        income = self.income_queryset(
            request.user, house
        ).get(pk=income.pk)

        return Response({
            "success": True,
            "message": "درآمد ویرایش شد.",
            "result": self.serialize_income(income),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            income, error = self.get_income(
                request, house, pk, lock=True
            )
            if error:
                return error

            if income.is_paid:
                return Response({
                    "success": False,
                    "message": "درآمد دریافت‌شده قابل حذف نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            income.delete()

        return Response({
            "success": True,
            "message": "درآمد با موفقیت حذف شد.",
        })
class ManagerIncomePayAPIView(ManagerIncomeBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        # -----------------------------------------------------
        # اعتبارسنجی اطلاعات اولیه پرداخت
        # -----------------------------------------------------
        try:
            payment_date = self.parse_date_value(
                request.data.get("payment_date"),
                "تاریخ دریافت وجه",
            )
            if payment_date.date() > date.today() if hasattr(payment_date, "date") else payment_date > date.today():
                return Response(
                    {
                        "success": False,
                        "message": "تاریخ پرداخت نمی‌تواند بعد از تاریخ امروز باشد.",
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            bank_id = request.data.get("bank_id")
            if not bank_id:
                raise ValueError("انتخاب حساب بانکی الزامی است.")

            bank = Bank.objects.filter(
                pk=bank_id,
                user=request.user,
                house=house,
                is_active=True,
            ).first()

            if not bank:
                raise ValueError("حساب بانکی فعال یافت نشد.")

            transaction_reference = str(
                request.data.get("transaction_reference") or ""
            ).strip()

            if len(transaction_reference) > 20:
                raise ValueError(
                    "شماره پیگیری نباید بیشتر از ۲۰ کاراکتر باشد."
                )

            # پرداخت‌کننده در زمان دریافت وجه انتخاب می‌شود.
            payer_type = str(
                request.data.get("payer_type") or ""
            ).strip()

            if payer_type not in ("owner", "renter", "other"):
                raise ValueError("نوع پرداخت‌کننده معتبر نیست.")

            payer_renter = None
            payer_third_party = None
            payer_name = ""
            payer_unit = None

            # -------------------------------------------------
            # پرداخت‌کننده: مالک
            # -------------------------------------------------
            if payer_type == "owner":
                unit_id = request.data.get("unit_id")

                payer_unit = Unit.objects.filter(
                    pk=unit_id,
                    myhouse=house,
                    is_active=True,
                ).first()

                if not payer_unit:
                    raise ValueError(
                        "واحد پرداخت‌کننده معتبر نیست."
                    )

                payer_name = (
                        payer_unit.owner_name or ""
                ).strip()

                if not payer_name:
                    raise ValueError(
                        "نام مالک این واحد ثبت نشده است."
                    )

            # -------------------------------------------------
            # پرداخت‌کننده: مستأجر
            # -------------------------------------------------
            elif payer_type == "renter":
                renter_id = request.data.get("payer_renter_id")

                payer_renter = Renter.objects.filter(
                    pk=renter_id,
                    myhouse=house,
                    unit__myhouse=house,
                    renter_is_active=True,
                    unit__is_active=True,
                ).select_related("unit").first()

                if not payer_renter:
                    raise ValueError(
                        "مستأجر فعال معتبری در این ساختمان یافت نشد."
                    )

                payer_unit = payer_renter.unit
                payer_name = (
                        payer_renter.renter_name or ""
                ).strip()

                if not payer_name:
                    raise ValueError("نام مستأجر مشخص نیست.")

            # -------------------------------------------------
            # پرداخت‌کننده: شخص ثالث
            # -------------------------------------------------
            elif payer_type == "other":
                third_party_id = request.data.get(
                    "payer_third_party_id"
                )

                payer_third_party = ThirdParty.objects.filter(
                    pk=third_party_id,
                    house=house,
                    is_active=True,
                ).first()

                if not payer_third_party:
                    raise ValueError(
                        "شخص ثالث معتبری یافت نشد."
                    )

                payer_name = (
                        payer_third_party.name or ""
                ).strip()

                if not payer_name:
                    raise ValueError(
                        "نام شخص ثالث مشخص نیست."
                    )

        except (ValueError, TypeError, ValidationError) as exc:
            messages = getattr(exc, "messages", None)
            message = messages[0] if messages else str(exc)

            return Response(
                {
                    "success": False,
                    "message": message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        # -----------------------------------------------------
        # ثبت پرداخت به صورت اتمیک
        # -----------------------------------------------------
        try:
            with transaction.atomic():
                income = Income.objects.select_for_update().filter(
                    pk=pk,
                    user=request.user,
                    house=house,
                    is_active=True,
                ).first()

                if not income:
                    return Response(
                        {
                            "success": False,
                            "message": "درآمد موردنظر یافت نشد.",
                        },
                        status=status.HTTP_404_NOT_FOUND,
                    )

                if income.is_paid:
                    return Response(
                        {
                            "success": False,
                            "message": "این درآمد قبلاً دریافت شده است.",
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                amount = Decimal(str(income.amount or 0))

                if amount <= 0:
                    raise ValueError(
                        "مبلغ درآمد باید بیشتر از صفر باشد."
                    )

                content_type = ContentType.objects.get_for_model(
                    Income
                )

                previous_deposit = BankFund.objects.filter(
                    content_type=content_type,
                    object_id=income.pk,
                    transaction_type="deposit",
                ).exists()

                if previous_deposit:
                    return Response(
                        {
                            "success": False,
                            "message": (
                                "برای این درآمد قبلاً تراکنش بانکی "
                                "ثبت شده است. ابتدا سوابق مالی را بررسی کنید."
                            ),
                        },
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                fund = BankTransactionService.deposit(
                    user=request.user,
                    bank=bank,
                    unit=payer_unit,
                    amount=amount,
                    description=(
                                    f"دریافت درآمد شماره {income.doc_number}: "
                                    f"{income.description}"
                                )[:500],
                    content_object=income,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    payer_type=payer_type,
                    payer_renter=payer_renter,
                    payer_name=payer_name,
                    payer_third_party=payer_third_party,
                    house=house,
                    gateway="دریافت درآمد",
                    financial_document_number=(
                        income.financial_document_number
                    ),
                )

                # ذخیره اطلاعات پرداخت روی خود درآمد
                income.bank = bank
                income.payment_date = payment_date
                income.transaction_reference = (
                        transaction_reference or None
                )
                income.is_paid = True
                income.payer_type = payer_type
                income.payer_renter = payer_renter
                income.payer_name = payer_name
                income.payer_third_party = payer_third_party

                # برای شخص ثالث، واحد پرداخت‌کننده None است.
                income.unit = payer_unit

                income.save(
                    update_fields=[
                        "bank",
                        "payment_date",
                        "transaction_reference",
                        "is_paid",
                        "payer_type",
                        "payer_renter",
                        "payer_name",
                        "payer_third_party",
                        "unit",
                    ]
                )

        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", None)
            message = messages[0] if messages else str(exc)

            return Response(
                {
                    "success": False,
                    "message": message,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        updated_income = self.income_queryset(
            request.user,
            house,
        ).get(pk=income.pk)

        return Response(
            {
                "success": True,
                "message": (
                    "دریافت وجه ثبت شد و موجودی بانک به‌روزرسانی شد."
                ),
                "bank_fund_id": fund.pk,
                "result": self.serialize_income(updated_income),
            }
        )
class ManagerIncomeBanksAPIView(ManagerIncomeBaseAPIView):

    def get(self, request):
        return self.get_manager_banks_response(request)
class ManagerIncomePayersAPIView(ManagerIncomeBaseAPIView):

    def get(self, request):
        return self.get_manager_payers_response(request)
class ManagerIncomeCancelPayAPIView(ManagerIncomeBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            income = Income.objects.select_for_update().filter(
                pk=pk,
                user=request.user,
                house=house,
                is_active=True,
            ).first()

            if not income:
                return Response({
                    "success": False,
                    "message": "درآمد موردنظر یافت نشد.",
                }, status=status.HTTP_404_NOT_FOUND)

            if not income.is_paid:
                return Response({
                    "success": False,
                    "message": "این درآمد هنوز دریافت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            content_type = ContentType.objects.get_for_model(Income)

            fund = BankFund.objects.select_for_update().filter(
                content_type=content_type,
                object_id=income.pk,
                transaction_type="deposit",
                is_paid=True,
            ).first()

            if not fund:
                return Response({
                    "success": False,
                    "message": "تراکنش بانکی مربوط به این درآمد پیدا نشد.",
                }, status=status.HTTP_404_NOT_FOUND)

            if fund.transfer_group_id:
                return Response({
                    "success": False,
                    "message": (
                        "این تراکنش بخشی از انتقال بانکی است و "
                        "از این مسیر قابل لغو نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            bank = fund.bank

            # فقط تراکنش متعلق به همین درآمد و همین ساختمان حذف می‌شود.
            fund.delete()

            if bank:
                recalculate_bank_balance(bank)

            income.bank = None
            income.payment_date = None
            income.transaction_reference = ""
            income.is_paid = False

            # پاک کردن اطلاعات پرداخت‌کننده
            income.payer_type = ""
            income.payer_name = ""
            income.payer_renter = None
            income.payer_third_party = None
            income.unit = None

            income.save(update_fields=[
                "bank",
                "payment_date",
                "transaction_reference",
                "is_paid",
                "payer_type",
                "payer_name",
                "payer_renter",
                "payer_third_party",
                "unit",
            ])

        return Response({
            "success": True,
            "message": "دریافت وجه لغو شد و موجودی بانک مجدداً محاسبه شد.",
            "result": self.serialize_income(
                self.income_queryset(request.user, house).get(pk=income.pk)
            ),
        })
class ManagerReceivableBaseAPIView(ManagerFinancialCommonMixin, APIView, ):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response({
                "success": False,
                "message": "شما دسترسی مدیر ساختمان را ندارید.",
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response({
                "success": False,
                "message": "ساختمان فعالی برای شما یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return house, None

    @staticmethod
    def normalize_digits(value):
        if value is None:
            return value

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )

        return (
            str(value)
            .translate(translation)
            .replace(",", "")
            .replace("٬", "")
        )

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("مبلغ سند دریافتنی معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError(
                "مبلغ سند دریافتنی باید بیشتر از صفر باشد."
            )

        if amount != amount.to_integral_value():
            raise ValueError("مبلغ باید عدد صحیح باشد.")

        return amount

    def parse_date_value(self, value, label="تاریخ"):
        value = self.normalize_digits(value)
        parsed = parse_date(value) if value else None

        if not parsed:
            raise ValueError(
                f"{label} نامعتبر است؛ قالب YYYY-MM-DD را ارسال کنید."
            )

        return parsed

    @staticmethod
    def get_uploaded_documents(request):
        files = request.FILES.getlist("documents")

        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError(
                "حداکثر دو مدرک برای هر سند دریافتنی مجاز است."
            )

        return files

    @staticmethod
    def receivable_queryset(user, house):
        return ReceiveMoney.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "bank",
            "unit",
            "payer_renter",
            "payer_third_party",
        ).prefetch_related("documents")

    def get_receivable(self, request, house, pk, lock=False):
        queryset = ReceiveMoney.objects.filter(
            pk=pk,
            user=request.user,
            house=house,
            is_active=True,
        )

        if lock:
            queryset = queryset.select_for_update()

        obj = queryset.first()

        if not obj:
            return None, Response({
                "success": False,
                "message": "سند دریافتنی موردنظر یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return obj, None

    def serialize_receivable(self, obj, request):
        bank = obj.bank

        return {
            "id": obj.id,
            "bank_id": obj.bank_id,
            "bank_name": getattr(bank, "bank_name", None) if bank else None,
            "account_no": getattr(bank, "account_no", None) if bank else None,
            "payer_type": obj.payer_type or "",
            "payer_renter_id": obj.payer_renter_id,
            "payer_third_party_id": obj.payer_third_party_id,
            "payer_name": obj.payer_name or "",
            "unit_id": obj.unit_id,
            "description": obj.description or "",
            "details": obj.details or "",
            "amount": str(obj.amount or 0),
            "doc_date": obj.doc_date.isoformat() if obj.doc_date else None,
            "doc_number": obj.doc_number,
            "financial_document_number": obj.financial_document_number,
            "is_received_money": obj.is_received_money,
            "is_paid": obj.is_paid,
            "payment_date": obj.payment_date.isoformat() if obj.payment_date else None,
            "transaction_reference": obj.transaction_reference or "",
            "documents": [
                {
                    "id": document.id,
                    "url": request.build_absolute_uri(document.document.url)
                    if document.document else None,
                }
                for document in obj.documents.all()
            ],
        }

    def validate_payer(self, request, house, data):
        payer_type = (data.get("payer_type") or "").strip()

        # پرداخت‌کننده هنگام ایجاد سند اختیاری است.
        if not payer_type:
            return {
                "unit": None,
                "payer_type": "",
                "payer_renter": None,
                "payer_third_party": None,
                "payer_name": "",
            }

        if payer_type not in ("owner", "renter", "other"):
            raise ValueError("نوع پرداخت‌کننده نامعتبر است.")

        unit = None
        payer_renter = None
        payer_third_party = None
        payer_name = ""

        if payer_type == "owner":
            try:
                unit_id = int(data.get("unit_id"))
            except (TypeError, ValueError):
                raise ValueError("واحد مالک معتبر نیست.")

            unit = Unit.objects.filter(
                pk=unit_id,
                myhouse=house,
                is_active=True,
                user__manager=request.user,
            ).first()

            if not unit:
                raise ValueError("واحد مالک یافت نشد.")

            payer_name = (unit.owner_name or "").strip()

            if not payer_name:
                raise ValueError(
                    "نام مالک این واحد مشخص نیست."
                )

        elif payer_type == "renter":
            try:
                renter_id = int(data.get("payer_renter_id"))
            except (TypeError, ValueError):
                raise ValueError("مستأجر انتخاب‌شده معتبر نیست.")

            payer_renter = Renter.objects.select_related(
                "unit"
            ).filter(
                pk=renter_id,
                renter_is_active=True,
                unit__myhouse=house,
                unit__is_active=True,
                unit__user__manager=request.user,
            ).first()

            if not payer_renter or not payer_renter.unit:
                raise ValueError(
                    "مستأجر فعال این ساختمان یافت نشد."
                )

            unit = payer_renter.unit
            payer_name = (
                    payer_renter.renter_name or ""
            ).strip()

            if not payer_name:
                raise ValueError("نام مستأجر مشخص نیست.")

        else:
            try:
                third_party_id = int(
                    data.get("payer_third_party_id")
                )
            except (TypeError, ValueError):
                raise ValueError("شخص ثالث را انتخاب کنید.")

            payer_third_party = ThirdParty.objects.filter(
                pk=third_party_id,
                house=house,
                is_active=True,
            ).first()

            if not payer_third_party:
                raise ValueError(
                    "شخص ثالث فعال این ساختمان یافت نشد."
                )

            payer_name = (
                    payer_third_party.name or ""
            ).strip()

            if not payer_name:
                raise ValueError(
                    "نام شخص ثالث مشخص نیست."
                )

        return {
            "unit": unit,
            "payer_type": payer_type,
            "payer_renter": payer_renter,
            "payer_third_party": payer_third_party,
            "payer_name": payer_name,
        }
class ManagerReceivableAPIView(ManagerReceivableBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        queryset = self.receivable_queryset(
            request.user, house
        )

        payment_status = request.query_params.get(
            "payment_status"
        )

        if payment_status == "paid":
            queryset = queryset.filter(
                is_received_money=True,
                is_paid=True,
            )
        elif payment_status == "unpaid":
            queryset = queryset.filter(
                is_received_money=False,
                is_paid=False,
            )

        results = [
            self.serialize_receivable(item, request)
            for item in queryset.order_by("-created_at")
        ]

        return Response({
            "success": True,
            "count": len(results),
            "results": results,
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            amount = self.parse_amount(
                request.data.get("amount")
            )

            doc_date = self.parse_date_value(
                request.data.get("doc_date"),
                "تاریخ سند",
            )

            documents = self.get_uploaded_documents(request)

            description = str(
                request.data.get("description") or ""
            ).strip()

            details = str(
                request.data.get("details") or ""
            ).strip()

            if not description:
                raise ValueError(
                    "شرح سند دریافتنی الزامی است."
                )

            if len(description) > 4000:
                raise ValueError(
                    "شرح سند نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
                )

            raw_number = self.normalize_digits(
                request.data.get("doc_number")
            )

            doc_number = None

            if raw_number not in (None, ""):
                try:
                    doc_number = int(raw_number)
                except (TypeError, ValueError):
                    raise ValueError("شماره سند معتبر نیست.")

            payer = self.validate_payer(
                request, house, request.data
            )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            obj = ReceiveMoney.objects.create(
                user=request.user,
                house=house,
                doc_date=doc_date,
                doc_number=doc_number,
                description=description,
                details=details,
                amount=amount,
                is_received_money=False,
                is_paid=False,
                unit=payer["unit"],
                payer_type=payer["payer_type"],
                payer_renter=payer["payer_renter"],
                payer_third_party=payer["payer_third_party"],
                payer_name=payer["payer_name"],
            )

            obj.financial_document_number = (
                get_next_financial_document_number(house)
            )

            obj.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                ReceiveDocument.objects.create(
                    receive=obj,
                    document=uploaded_file,
                )

        obj = self.receivable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "سند دریافتنی با موفقیت ثبت شد.",
            "result": self.serialize_receivable(obj, request),
        }, status=status.HTTP_201_CREATED)
class ManagerReceivableDetailAPIView(ManagerReceivableBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            with transaction.atomic():
                obj, error = self.get_receivable(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_received_money or obj.is_paid:
                    return Response({
                        "success": False,
                        "message": (
                            "سند دریافت‌شده قابل ویرایش نیست."
                        ),
                    }, status=status.HTTP_400_BAD_REQUEST)

                data = request.data

                if "amount" in data:
                    obj.amount = self.parse_amount(
                        data.get("amount")
                    )

                if "doc_date" in data:
                    obj.doc_date = self.parse_date_value(
                        data.get("doc_date"), "تاریخ سند"
                    )

                if "description" in data:
                    description = str(
                        data.get("description") or ""
                    ).strip()

                    if not description:
                        raise ValueError(
                            "شرح سند دریافتنی الزامی است."
                        )

                    if len(description) > 4000:
                        raise ValueError(
                            "شرح سند نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
                        )

                    obj.description = description

                if "details" in data:
                    obj.details = str(
                        data.get("details") or ""
                    ).strip()

                if "doc_number" in data:
                    raw_number = self.normalize_digits(
                        data.get("doc_number")
                    )

                    if raw_number in (None, ""):
                        obj.doc_number = None
                    else:
                        try:
                            obj.doc_number = int(raw_number)
                        except (TypeError, ValueError):
                            raise ValueError(
                                "شماره سند معتبر نیست."
                            )

                payer_fields = (
                    "payer_type",
                    "unit_id",
                    "payer_renter_id",
                    "payer_third_party_id",
                )

                if any(key in data for key in payer_fields):
                    payer = self.validate_payer(
                        request, house, data
                    )

                    obj.unit = payer["unit"]
                    obj.payer_type = payer["payer_type"]
                    obj.payer_renter = payer["payer_renter"]
                    obj.payer_third_party = (
                        payer["payer_third_party"]
                    )
                    obj.payer_name = payer["payer_name"]

                # دریافت شناسه پیوست‌هایی که باید حذف شوند
                raw_deleted_ids = data.get("deleted_document_ids", "[]")

                try:
                    if isinstance(raw_deleted_ids, str):
                        deleted_ids = json.loads(raw_deleted_ids)
                    else:
                        deleted_ids = raw_deleted_ids

                    if not isinstance(deleted_ids, list):
                        raise ValueError()

                    deleted_ids = list({
                        int(doc_id)
                        for doc_id in deleted_ids
                    })

                    if any(doc_id <= 0 for doc_id in deleted_ids):
                        raise ValueError()

                except (TypeError, ValueError, json.JSONDecodeError):
                    raise ValueError("شناسه پیوست‌های قابل حذف نامعتبر است.")

                # فقط پیوست‌های متعلق به همین سند قابل حذف هستند
                documents_to_delete = obj.documents.filter(
                    id__in=deleted_ids
                )

                if documents_to_delete.count() != len(deleted_ids):
                    raise ValueError(
                        "بعضی از پیوست‌های انتخاب‌شده معتبر نیستند."
                    )

                # فایل‌های جدید
                new_files = self.get_uploaded_documents(request)

                # تعداد پیوست‌های باقی‌مانده پس از حذف
                remaining_count = (
                        obj.documents.count() - len(deleted_ids)
                )

                if remaining_count + len(new_files) > 2:
                    raise ValueError(
                        "هر سند دریافتنی حداکثر دو مدرک دارد."
                    )

                # ذخیره اطلاعات سند
                obj.save()

                # حذف پیوست‌های انتخاب‌شده
                documents_to_delete.delete()

                # افزودن پیوست‌های جدید
                for uploaded_file in new_files:
                    ReceiveDocument.objects.create(
                        receive=obj,
                        document=uploaded_file,
                    )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.receivable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "سند دریافتنی ویرایش شد.",
            "result": self.serialize_receivable(obj, request),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_receivable(
                request, house, pk, lock=True
            )

            if error:
                return error

            if obj.is_received_money or obj.is_paid:
                return Response({
                    "success": False,
                    "message": (
                        "سند دریافت‌شده قابل حذف نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            obj.delete()

        return Response({
            "success": True,
            "message": "سند دریافتنی حذف شد.",
        })
class ManagerReceivableReceiveAPIView(ManagerReceivableBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            payment_date = self.parse_date_value(
                request.data.get("payment_date"),
                "تاریخ دریافت وجه",
            )

            if payment_date > date.today():
                raise ValueError(
                    "تاریخ دریافت وجه نمی‌تواند بعد از امروز باشد."
                )

            bank_id = request.data.get("bank_id")

            if not bank_id:
                raise ValueError(
                    "انتخاب حساب بانکی الزامی است."
                )

            bank = Bank.objects.filter(
                pk=bank_id,
                user=request.user,
                house=house,
                is_active=True,
            ).first()

            if not bank:
                raise ValueError(
                    "حساب بانکی فعال یافت نشد."
                )

            transaction_reference = str(
                request.data.get("transaction_reference") or ""
            ).strip()

            if len(transaction_reference) > 20:
                raise ValueError(
                    "شماره پیگیری نباید بیشتر از ۲۰ کاراکتر باشد."
                )

            payer_type = str(
                request.data.get("payer_type") or ""
            ).strip()

            if payer_type not in ("owner", "renter", "other"):
                raise ValueError(
                    "نوع پرداخت‌کننده معتبر نیست."
                )

            payer = self.validate_payer(
                request, house, request.data
            )

            if not payer["payer_type"]:
                raise ValueError(
                    "انتخاب پرداخت‌کننده الزامی است."
                )

        except (ValueError, TypeError, ValidationError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                obj, error = self.get_receivable(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_received_money or obj.is_paid:
                    return Response({
                        "success": False,
                        "message": (
                            "این سند قبلاً دریافت شده است."
                        ),
                    }, status=status.HTTP_400_BAD_REQUEST)

                amount = Decimal(str(obj.amount or 0))

                if amount <= 0:
                    raise ValueError(
                        "مبلغ سند باید بیشتر از صفر باشد."
                    )

                content_type = ContentType.objects.get_for_model(
                    ReceiveMoney
                )

                previous_deposit = BankFund.objects.filter(
                    content_type=content_type,
                    object_id=obj.pk,
                    transaction_type="deposit",
                ).exists()

                if previous_deposit:
                    raise ValueError(
                        "برای این سند قبلاً تراکنش بانکی ثبت شده است؛ "
                        "سوابق مالی را بررسی کنید."
                    )

                fund = BankTransactionService.deposit(
                    user=request.user,
                    bank=bank,
                    unit=payer["unit"],
                    amount=amount,
                    description=(
                                    f"دریافت سند شماره {obj.doc_number}: "
                                    f"{obj.description}"
                                )[:500],
                    content_object=obj,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    payer_type=payer["payer_type"],
                    payer_renter=payer["payer_renter"],
                    payer_name=payer["payer_name"],
                    payer_third_party=payer["payer_third_party"],
                    house=house,
                    gateway="دریافت سند دریافتنی",
                    financial_document_number=(
                        obj.financial_document_number
                    ),
                )

                obj.bank = bank
                obj.payment_date = payment_date
                obj.transaction_reference = (
                        transaction_reference or None
                )

                obj.payer_type = payer["payer_type"]
                obj.payer_renter = payer["payer_renter"]
                obj.payer_third_party = (
                    payer["payer_third_party"]
                )
                obj.payer_name = payer["payer_name"]
                obj.unit = payer["unit"]

                obj.is_received_money = True
                obj.is_paid = True

                obj.save(update_fields=[
                    "bank",
                    "payment_date",
                    "transaction_reference",
                    "payer_type",
                    "payer_renter",
                    "payer_third_party",
                    "payer_name",
                    "unit",
                    "is_received_money",
                    "is_paid",
                ])

        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.receivable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "دریافت وجه ثبت شد و موجودی بانک به‌روزرسانی شد.",
            "bank_fund_id": fund.pk,
            "result": self.serialize_receivable(obj, request),
        })
class ManagerReceivableCancelReceiveAPIView(ManagerReceivableBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_receivable(
                request, house, pk, lock=True
            )

            if error:
                return error

            if not obj.is_received_money and not obj.is_paid:
                return Response({
                    "success": False,
                    "message": "این سند هنوز دریافت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            content_type = ContentType.objects.get_for_model(
                ReceiveMoney
            )

            fund = BankFund.objects.select_for_update().filter(
                content_type=content_type,
                object_id=obj.pk,
                transaction_type="deposit",
                is_paid=True,
            ).first()

            if not fund:
                return Response({
                    "success": False,
                    "message": (
                        "تراکنش بانکی مربوط به این سند پیدا نشد."
                    ),
                }, status=status.HTTP_404_NOT_FOUND)

            if fund.transfer_group_id:
                return Response({
                    "success": False,
                    "message": (
                        "این تراکنش بخشی از انتقال بانکی است "
                        "و از این مسیر قابل لغو نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            bank = fund.bank

            fund.delete()

            if bank:
                recalculate_bank_balance(bank)

            obj.bank = None
            obj.payment_date = None
            obj.transaction_reference = ""
            obj.is_received_money = False
            obj.is_paid = False

            obj.save(update_fields=[
                "bank",
                "payment_date",
                "transaction_reference",
                "is_received_money",
                "is_paid",
            ])

        obj = self.receivable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": (
                "دریافت وجه لغو شد و موجودی بانک مجدداً محاسبه شد."
            ),
            "result": self.serialize_receivable(obj, request),
        })
class ManagerReceivableBanksAPIView(ManagerReceivableBaseAPIView):
    def get(self, request):
        return self.get_manager_banks_response(request)
class ManagerReceivablePayersAPIView(ManagerReceivableBaseAPIView):
    def get(self, request):
        return self.get_manager_payers_response(request)
class ManagerPayableBaseAPIView(ManagerFinancialCommonMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response({
                "success": False,
                "message": "شما دسترسی مدیر ساختمان را ندارید.",
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response({
                "success": False,
                "message": "ساختمان فعالی برای شما یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return house, None

    @staticmethod
    def normalize_digits(value):
        if value is None:
            return value

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )

        return (
            str(value)
            .translate(translation)
            .replace(",", "")
            .replace("٬", "")
        )

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("مبلغ سند پرداختنی معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("مبلغ سند باید بیشتر از صفر باشد.")

        if amount != amount.to_integral_value():
            raise ValueError("مبلغ باید عدد صحیح باشد.")

        return amount

    def parse_date_value(self, value, label="تاریخ"):
        value = self.normalize_digits(value)
        parsed = parse_date(value) if value else None

        if not parsed:
            raise ValueError(
                f"{label} نامعتبر است؛ قالب YYYY-MM-DD را ارسال کنید."
            )

        return parsed

    @staticmethod
    def get_uploaded_documents(request):
        files = request.FILES.getlist("documents")

        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError(
                "حداکثر دو مدرک برای هر سند پرداختنی مجاز است."
            )

        return files

    @staticmethod
    def payable_queryset(user, house):
        return PayMoney.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "bank",
            "unit",
            "receiver_renter",
            "receiver_third_party",
        ).prefetch_related("documents")

    def get_payable(self, request, house, pk, lock=False):
        queryset = PayMoney.objects.filter(
            pk=pk,
            user=request.user,
            house=house,
            is_active=True,
        )

        if lock:
            queryset = queryset.select_for_update()

        obj = queryset.first()

        if not obj:
            return None, Response({
                "success": False,
                "message": "سند پرداختنی موردنظر یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return obj, None

    @staticmethod
    def serialize_payable(obj):
        bank = obj.bank

        return {
            "id": obj.id,
            "bank_id": obj.bank_id,
            "bank_name": (
                getattr(bank, "bank_name", None)
                if bank else None
            ),
            "account_no": (
                getattr(bank, "account_no", None)
                if bank else None
            ),
            "receiver_type": obj.receiver_type or "",
            "receiver_renter_id": obj.receiver_renter_id,
            "receiver_third_party_id": obj.receiver_third_party_id,
            "receiver_name": obj.receiver_name or "",
            "unit_id": obj.unit_id,
            "description": obj.description or "",
            "details": obj.details or "",
            "amount": str(obj.amount or 0),
            "document_date": (
                obj.document_date.isoformat()
                if obj.document_date else None
            ),
            "document_number": obj.document_number,
            "financial_document_number": (
                obj.financial_document_number
            ),
            "is_paid_money": obj.is_paid_money,
            "is_paid": obj.is_paid,
            "payment_date": (
                obj.payment_date.isoformat()
                if obj.payment_date else None
            ),
            "transaction_reference": (
                    obj.transaction_reference or ""
            ),
            "documents": [
                {
                    "id": document.id,
                    "url": (
                        document.document.url
                        if document.document else None
                    ),
                }
                for document in obj.documents.all()
            ],
        }

    def validate_receiver(self, request, house, data):
        receiver_type = (
                data.get("receiver_type") or ""
        ).strip()

        if not receiver_type:
            return {
                "unit": None,
                "receiver_type": "",
                "receiver_renter": None,
                "receiver_third_party": None,
                "receiver_name": "",
            }

        if receiver_type not in ("owner", "renter", "other"):
            raise ValueError("نوع دریافت‌کننده نامعتبر است.")

        unit = None
        receiver_renter = None
        receiver_third_party = None
        receiver_name = ""

        if receiver_type == "owner":
            try:
                unit_id = int(data.get("unit_id"))
            except (TypeError, ValueError):
                raise ValueError("واحد مالک معتبر نیست.")

            unit = Unit.objects.filter(
                pk=unit_id,
                myhouse=house,
                is_active=True,
                user__manager=request.user,
            ).first()

            if not unit:
                raise ValueError("واحد مالک یافت نشد.")

            receiver_name = (unit.owner_name or "").strip()

            if not receiver_name:
                raise ValueError("نام مالک این واحد مشخص نیست.")

        elif receiver_type == "renter":
            try:
                renter_id = int(data.get("receiver_renter_id"))
            except (TypeError, ValueError):
                raise ValueError("مستأجر انتخاب‌شده معتبر نیست.")

            receiver_renter = Renter.objects.select_related(
                "unit"
            ).filter(
                pk=renter_id,
                renter_is_active=True,
                unit__myhouse=house,
                unit__is_active=True,
                unit__user__manager=request.user,
            ).first()

            if not receiver_renter or not receiver_renter.unit:
                raise ValueError(
                    "مستأجر فعال این ساختمان یافت نشد."
                )

            unit = receiver_renter.unit
            receiver_name = (
                    receiver_renter.renter_name or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام مستأجر مشخص نیست.")

        else:
            try:
                third_party_id = int(
                    data.get("receiver_third_party_id")
                )
            except (TypeError, ValueError):
                raise ValueError("شخص ثالث را انتخاب کنید.")

            receiver_third_party = ThirdParty.objects.filter(
                pk=third_party_id,
                house=house,
                is_active=True,
            ).first()

            if not receiver_third_party:
                raise ValueError(
                    "شخص ثالث فعال این ساختمان یافت نشد."
                )

            receiver_name = (
                    receiver_third_party.name or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام شخص ثالث مشخص نیست.")

        return {
            "unit": unit,
            "receiver_type": receiver_type,
            "receiver_renter": receiver_renter,
            "receiver_third_party": receiver_third_party,
            "receiver_name": receiver_name,
        }
class ManagerPayableAPIView(ManagerPayableBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        queryset = self.payable_queryset(request.user, house)

        payment_status = request.query_params.get("payment_status")

        if payment_status == "paid":
            queryset = queryset.filter(is_paid=True)
        elif payment_status == "unpaid":
            queryset = queryset.filter(is_paid=False)

        results = [
            self.serialize_payable(item)
            for item in queryset.order_by("-created_at")
        ]

        return Response({
            "success": True,
            "count": len(results),
            "results": results,
        })

    def post(self, request):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            amount = self.parse_amount(
                request.data.get("amount")
            )

            document_date = self.parse_date_value(
                request.data.get("document_date"),
                "تاریخ سند",
            )

            documents = self.get_uploaded_documents(request)

            description = str(
                request.data.get("description") or ""
            ).strip()

            details = str(
                request.data.get("details") or ""
            ).strip()

            if not description:
                raise ValueError("شرح سند پرداختنی الزامی است.")

            if len(description) > 4000:
                raise ValueError(
                    "شرح سند نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
                )

            raw_number = self.normalize_digits(
                request.data.get("document_number")
            )

            document_number = None

            if raw_number not in (None, ""):
                try:
                    document_number = int(raw_number)
                except (TypeError, ValueError):
                    raise ValueError("شماره سند معتبر نیست.")

            receiver = self.validate_receiver(
                request, house, request.data
            )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            obj = PayMoney.objects.create(
                user=request.user,
                house=house,
                document_date=document_date,
                document_number=document_number,
                description=description,
                details=details,
                amount=amount,
                is_paid_money=False,
                is_paid=False,
                unit=receiver["unit"],
                receiver_type=receiver["receiver_type"],
                receiver_renter=receiver["receiver_renter"],
                receiver_third_party=(
                    receiver["receiver_third_party"]
                ),
                receiver_name=receiver["receiver_name"],
            )

            obj.financial_document_number = (
                get_next_financial_document_number(house)
            )

            obj.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                PayDocument.objects.create(
                    payment=obj,
                    document=uploaded_file,
                )

        obj = self.payable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "سند پرداختنی با موفقیت ثبت شد.",
            "result": self.serialize_payable(obj),
        }, status=status.HTTP_201_CREATED)
class ManagerPayableDetailAPIView(ManagerPayableBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            with transaction.atomic():
                obj, error = self.get_payable(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid_money or obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "سند پرداخت‌شده قابل ویرایش نیست.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                data = request.data

                if "amount" in data:
                    obj.amount = self.parse_amount(data.get("amount"))

                if "document_date" in data:
                    obj.document_date = self.parse_date_value(
                        data.get("document_date"), "تاریخ سند"
                    )

                if "description" in data:
                    description = str(
                        data.get("description") or ""
                    ).strip()

                    if not description:
                        raise ValueError(
                            "شرح سند پرداختنی الزامی است."
                        )

                    if len(description) > 4000:
                        raise ValueError(
                            "شرح سند نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
                        )

                    obj.description = description

                if "details" in data:
                    obj.details = str(
                        data.get("details") or ""
                    ).strip()

                if "document_number" in data:
                    raw_number = self.normalize_digits(
                        data.get("document_number")
                    )

                    if raw_number in (None, ""):
                        obj.document_number = None
                    else:
                        try:
                            obj.document_number = int(raw_number)
                        except (TypeError, ValueError):
                            raise ValueError(
                                "شماره سند معتبر نیست."
                            )

                receiver_fields = (
                    "receiver_type",
                    "unit_id",
                    "receiver_renter_id",
                    "receiver_third_party_id",
                )

                if any(key in data for key in receiver_fields):
                    receiver = self.validate_receiver(
                        request, house, data
                    )

                    obj.unit = receiver["unit"]
                    obj.receiver_type = receiver["receiver_type"]
                    obj.receiver_renter = receiver["receiver_renter"]
                    obj.receiver_third_party = (
                        receiver["receiver_third_party"]
                    )
                    obj.receiver_name = receiver["receiver_name"]

                new_files = self.get_uploaded_documents(request)

                if obj.documents.count() + len(new_files) > 2:
                    raise ValueError(
                        "هر سند پرداختنی حداکثر دو مدرک دارد."
                    )

                obj.save()

                for uploaded_file in new_files:
                    PayDocument.objects.create(
                        payment=obj,
                        document=uploaded_file,
                    )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.payable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "سند پرداختنی ویرایش شد.",
            "result": self.serialize_payable(obj),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_payable(
                request, house, pk, lock=True
            )

            if error:
                return error

            if obj.is_paid_money or obj.is_paid:
                return Response({
                    "success": False,
                    "message": "سند پرداخت‌شده قابل حذف نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            obj.delete()

        return Response({
            "success": True,
            "message": "سند پرداختنی حذف شد.",
        })
class ManagerPayablePayAPIView(ManagerPayableBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        try:
            payment_date = self.parse_date_value(
                request.data.get("payment_date"),
                "تاریخ پرداخت",
            )

            if payment_date > date.today():
                raise ValueError(
                    "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
                )

            bank_id = request.data.get("bank_id")
            if not bank_id:
                raise ValueError(
                    "انتخاب حساب بانکی الزامی است."
                )

            bank = Bank.objects.filter(
                pk=bank_id,
                user=request.user,
                house=house,
                is_active=True,
            ).first()

            if not bank:
                raise ValueError(
                    "حساب بانکی فعال یافت نشد."
                )

            transaction_reference = str(
                request.data.get("transaction_reference") or ""
            ).strip()

            if len(transaction_reference) > 20:
                raise ValueError(
                    "شماره پیگیری نباید بیشتر از ۲۰ کاراکتر باشد."
                )

        except (ValueError, TypeError, ValidationError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                obj, error = self.get_payable(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid_money or obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "این سند قبلاً پرداخت شده است.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                amount = Decimal(str(obj.amount or 0))

                if amount <= 0:
                    raise ValueError(
                        "مبلغ سند باید بیشتر از صفر باشد."
                    )

                content_type = ContentType.objects.get_for_model(
                    PayMoney
                )

                previous_withdrawal = BankFund.objects.filter(
                    content_type=content_type,
                    object_id=obj.pk,
                    transaction_type="withdraw",
                    is_paid=True,
                ).exists()

                if previous_withdrawal:
                    raise ValueError(
                        "برای این سند قبلاً برداشت بانکی ثبت شده است؛ "
                        "سوابق مالی را بررسی کنید."
                    )

                receiver = self.validate_receiver(
                    request,
                    house,
                    {
                        "receiver_type": (
                                request.data.get("receiver_type")
                                or obj.receiver_type
                        ),
                        "unit_id": (
                                request.data.get("unit_id")
                                or obj.unit_id
                        ),
                        "receiver_renter_id": (
                                request.data.get("receiver_renter_id")
                                or obj.receiver_renter_id
                        ),
                        "receiver_third_party_id": (
                                request.data.get("receiver_third_party_id")
                                or obj.receiver_third_party_id
                        ),
                    },
                )

                fund = BankTransactionService.withdraw(
                    user=request.user,
                    bank=bank,
                    unit=receiver["unit"],
                    amount=amount,
                    description=(
                                    f"پرداخت سند شماره {obj.document_number}: "
                                    f"{obj.description}"
                                )[:500],
                    content_object=obj,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    receiver_type=receiver["receiver_type"],
                    receiver_renter=receiver["receiver_renter"],
                    receiver_name=receiver["receiver_name"],
                    receiver_third_party=(
                        receiver["receiver_third_party"]
                    ),
                    house=house,
                    gateway="پرداخت سند پرداختنی",
                    financial_document_number=(
                        obj.financial_document_number
                    ),
                )

                obj.bank = bank
                obj.payment_date = payment_date
                obj.transaction_reference = (
                        transaction_reference or None
                )
                obj.receiver_type = receiver["receiver_type"]
                obj.receiver_renter = receiver["receiver_renter"]
                obj.receiver_third_party = (
                    receiver["receiver_third_party"]
                )
                obj.receiver_name = receiver["receiver_name"]
                obj.unit = receiver["unit"]
                obj.is_paid_money = True
                obj.is_paid = True

                obj.save(update_fields=[
                    "bank",
                    "payment_date",
                    "transaction_reference",
                    "receiver_type",
                    "receiver_renter",
                    "receiver_third_party",
                    "receiver_name",
                    "unit",
                    "is_paid_money",
                    "is_paid",
                ])

        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.payable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "پرداخت سند ثبت شد و موجودی بانک به‌روزرسانی شد.",
            "bank_fund_id": fund.pk,
            "result": self.serialize_payable(obj),
        })
class ManagerPayableCancelPayAPIView(ManagerPayableBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)
        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_payable(
                request, house, pk, lock=True
            )

            if error:
                return error

            if not obj.is_paid_money and not obj.is_paid:
                return Response({
                    "success": False,
                    "message": "این سند هنوز پرداخت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            content_type = ContentType.objects.get_for_model(
                PayMoney
            )

            fund = BankFund.objects.select_for_update().filter(
                content_type=content_type,
                object_id=obj.pk,
                transaction_type="withdraw",
                is_paid=True,
            ).first()

            if not fund:
                return Response({
                    "success": False,
                    "message": (
                        "تراکنش برداشت مربوط به این سند پیدا نشد."
                    ),
                }, status=status.HTTP_404_NOT_FOUND)

            if fund.transfer_group_id:
                return Response({
                    "success": False,
                    "message": (
                        "این تراکنش بخشی از انتقال بانکی است "
                        "و از این مسیر قابل لغو نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            bank = fund.bank

            fund.delete()

            if bank:
                recalculate_bank_balance(bank)

            obj.bank = None
            obj.payment_date = None
            obj.transaction_reference = ""
            obj.is_paid_money = False
            obj.is_paid = False

            obj.save(update_fields=[
                "bank",
                "payment_date",
                "transaction_reference",
                "is_paid_money",
                "is_paid",
            ])

        obj = self.payable_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": (
                "پرداخت سند لغو شد و موجودی بانک مجدداً محاسبه شد."
            ),
            "result": self.serialize_payable(obj),
        })
class ManagerPayableBanksAPIView(ManagerPayableBaseAPIView):

    def get(self, request):
        return self.get_manager_banks_response(request)
class ManagerPayableReceiversAPIView(ManagerPayableBaseAPIView):

    def get(self, request):
        return self.get_manager_payers_response(request)
class ManagerMaintenanceBaseAPIView(ManagerFinancialCommonMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response({
                "success": False,
                "message": "شما دسترسی مدیر ساختمان را ندارید.",
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response({
                "success": False,
                "message": "ساختمان فعالی برای شما یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return house, None

    @staticmethod
    def normalize_digits(value):
        if value is None:
            return value

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )

        return (
            str(value)
            .translate(translation)
            .replace(",", "")
            .replace("٬", "")
        )

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("مبلغ تعمیر معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("مبلغ تعمیر باید بیشتر از صفر باشد.")

        if amount != amount.to_integral_value():
            raise ValueError("مبلغ باید عدد صحیح باشد.")

        return int(amount)

    def parse_date_value(self, value, label="تاریخ"):
        value = self.normalize_digits(value)
        parsed = parse_date(value) if value else None

        if not parsed:
            raise ValueError(
                f"{label} نامعتبر است؛ قالب YYYY-MM-DD را ارسال کنید."
            )

        return parsed

    @staticmethod
    def get_uploaded_documents(request):
        files = request.FILES.getlist("documents")

        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError(
                "حداکثر دو مدرک برای هر تعمیر مجاز است."
            )

        return files

    @staticmethod
    def maintenance_queryset(user, house):
        return Maintenance.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "bank",
            "unit",
            "receiver_renter",
            "receiver_third_party",
        ).prefetch_related("documents")

    def get_maintenance(self, request, house, pk, lock=False):
        queryset = Maintenance.objects.filter(
            pk=pk,
            user=request.user,
            house=house,
            is_active=True,
        )

        if lock:
            queryset = queryset.select_for_update()

        obj = queryset.first()

        if not obj:
            return None, Response({
                "success": False,
                "message": "رکورد تعمیر و نگهداری یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return obj, None

    @staticmethod
    def serialize_maintenance(obj):
        bank = obj.bank

        return {
            "id": obj.id,

            "bank_id": obj.bank_id,
            "bank_name": (
                getattr(bank, "bank_name", None)
                if bank else None
            ),
            "account_no": (
                getattr(bank, "account_no", None)
                if bank else None
            ),

            "house_id": obj.house_id,
            "unit_id": obj.unit_id,

            "receiver_type": obj.receiver_type or "",
            "receiver_renter_id": obj.receiver_renter_id,
            "receiver_third_party_id": (
                obj.receiver_third_party_id
            ),
            "receiver_name": obj.receiver_name or "",

            "expert_name": obj.expert_name or "",
            "maintenance_description": (
                    obj.maintenance_description or ""
            ),

            "maintenance_start_date": (
                obj.maintenance_start_date.isoformat()
                if obj.maintenance_start_date else None
            ),

            "maintenance_end_date": (
                obj.maintenance_end_date.isoformat()
                if obj.maintenance_end_date else None
            ),

            "maintenance_price": str(
                obj.maintenance_price or 0
            ),

            "maintenance_status": (
                    obj.maintenance_status or ""
            ),

            "service_company": obj.service_company or "",

            "maintenance_document_no": (
                    obj.maintenance_document_no or ""
            ),

            "financial_document_number": (
                obj.financial_document_number
            ),

            "details": obj.details or "",

            "is_paid": obj.is_paid,

            "payment_date": (
                obj.payment_date.isoformat()
                if obj.payment_date else None
            ),

            "transaction_reference": (
                    obj.transaction_reference or ""
            ),

            "documents": [
                {
                    "id": document.id,
                    "url": (
                        document.document.url
                        if document.document else None
                    ),
                }
                for document in obj.documents.all()
            ],
        }

    def validate_receiver(self, request, house, data):
        receiver_type = (
                data.get("receiver_type") or ""
        ).strip()

        if not receiver_type:
            return {
                "unit": None,
                "receiver_type": "",
                "receiver_renter": None,
                "receiver_third_party": None,
                "receiver_name": "",
            }

        if receiver_type not in ("owner", "renter", "other"):
            raise ValueError("نوع دریافت‌کننده نامعتبر است.")

        unit = None
        receiver_renter = None
        receiver_third_party = None
        receiver_name = ""

        if receiver_type == "owner":
            try:
                unit_id = int(data.get("unit_id"))
            except (TypeError, ValueError):
                raise ValueError("واحد مالک معتبر نیست.")

            unit = Unit.objects.filter(
                pk=unit_id,
                myhouse=house,
                is_active=True,
                user__manager=request.user,
            ).first()

            if not unit:
                raise ValueError("واحد مالک یافت نشد.")

            receiver_name = (
                    unit.owner_name or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام مالک این واحد مشخص نیست.")

        elif receiver_type == "renter":
            try:
                renter_id = int(
                    data.get("receiver_renter_id")
                )
            except (TypeError, ValueError):
                raise ValueError("مستأجر انتخاب‌شده معتبر نیست.")

            receiver_renter = Renter.objects.select_related(
                "unit"
            ).filter(
                pk=renter_id,
                renter_is_active=True,
                unit__myhouse=house,
                unit__is_active=True,
                unit__user__manager=request.user,
            ).first()

            if not receiver_renter or not receiver_renter.unit:
                raise ValueError(
                    "مستأجر فعال این ساختمان یافت نشد."
                )

            unit = receiver_renter.unit

            receiver_name = (
                    receiver_renter.renter_name or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام مستأجر مشخص نیست.")

        else:
            try:
                third_party_id = int(
                    data.get("receiver_third_party_id")
                )
            except (TypeError, ValueError):
                raise ValueError("شخص ثالث را انتخاب کنید.")

            receiver_third_party = ThirdParty.objects.filter(
                pk=third_party_id,
                house=house,
                is_active=True,
            ).first()

            if not receiver_third_party:
                raise ValueError(
                    "شخص ثالث فعال این ساختمان یافت نشد."
                )

            receiver_name = (
                    receiver_third_party.name or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام شخص ثالث مشخص نیست.")

        return {
            "unit": unit,
            "receiver_type": receiver_type,
            "receiver_renter": receiver_renter,
            "receiver_third_party": receiver_third_party,
            "receiver_name": receiver_name,
        }

    def validate_maintenance_data(self, data):
        expert_name = str(
            data.get("expert_name") or ""
        ).strip()

        description = str(
            data.get("maintenance_description") or ""
        ).strip()

        maintenance_status = str(
            data.get("maintenance_status") or ""
        ).strip()

        service_company = str(
            data.get("service_company") or ""
        ).strip()

        if not expert_name:
            raise ValueError("نام کارشناس الزامی است.")

        if not description:
            raise ValueError("شرح تعمیر و نگهداری الزامی است.")

        if len(description) > 1000:
            raise ValueError(
                "شرح تعمیر نباید بیشتر از ۱۰۰۰ کاراکتر باشد."
            )

        if not maintenance_status:
            raise ValueError("وضعیت تعمیر الزامی است.")

        if not service_company:
            raise ValueError("نام شرکت خدماتی الزامی است.")

        if len(expert_name) > 200:
            raise ValueError("نام کارشناس بیش از حد مجاز است.")

        if len(service_company) > 200:
            raise ValueError("نام شرکت خدماتی بیش از حد مجاز است.")

        start_date = self.parse_date_value(
            data.get("maintenance_start_date"),
            "تاریخ شروع تعمیر",
        )

        end_date = self.parse_date_value(
            data.get("maintenance_end_date"),
            "تاریخ پایان تعمیر",
        )

        if end_date < start_date:
            raise ValueError(
                "تاریخ پایان تعمیر نمی‌تواند قبل از تاریخ شروع باشد."
            )

        amount = self.parse_amount(
            data.get("maintenance_price")
        )

        document_no = str(
            self.normalize_digits(
                data.get("maintenance_document_no") or ""
            )
        ).strip()

        if len(document_no) > 100:
            raise ValueError("شماره سند تعمیر بیش از حد مجاز است.")

        details = str(data.get("details") or "").strip()

        if len(details) > 4000:
            raise ValueError(
                "توضیحات نباید بیشتر از ۴۰۰۰ کاراکتر باشد."
            )

        return {
            "expert_name": expert_name,
            "maintenance_description": description,
            "maintenance_start_date": start_date,
            "maintenance_end_date": end_date,
            "maintenance_price": amount,
            "maintenance_status": maintenance_status,
            "service_company": service_company,
            "maintenance_document_no": document_no or None,
            "details": details or None,
        }
class ManagerMaintenanceAPIView(ManagerMaintenanceBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)

        if error:
            return error

        queryset = self.maintenance_queryset(
            request.user, house
        )

        payment_status = request.query_params.get(
            "payment_status"
        )

        if payment_status == "paid":
            queryset = queryset.filter(is_paid=True)

        elif payment_status == "unpaid":
            queryset = queryset.filter(is_paid=False)

        results = [
            self.serialize_maintenance(item)
            for item in queryset.order_by("-created_at")
        ]

        return Response({
            "success": True,
            "count": len(results),
            "results": results,
        })

    def post(self, request):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            data = self.validate_maintenance_data(request.data)

            documents = self.get_uploaded_documents(request)

            receiver = self.validate_receiver(
                request, house, request.data
            )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            obj = Maintenance.objects.create(
                user=request.user,
                house=house,

                **data,

                unit=receiver["unit"],
                receiver_type=receiver["receiver_type"],
                receiver_renter=receiver["receiver_renter"],
                receiver_third_party=(
                    receiver["receiver_third_party"]
                ),
                receiver_name=receiver["receiver_name"],

                is_paid=False,
                is_active=True,
            )

            obj.financial_document_number = (
                get_next_financial_document_number(house)
            )

            obj.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                MaintenanceDocument.objects.create(
                    maintenance=obj,
                    document=uploaded_file,
                )

        obj = self.maintenance_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "تعمیر و نگهداری با موفقیت ثبت شد.",
            "result": self.serialize_maintenance(obj),
        }, status=status.HTTP_201_CREATED)
class ManagerMaintenanceDetailAPIView(ManagerMaintenanceBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            with transaction.atomic():
                obj, error = self.get_maintenance(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "تعمیر پرداخت‌شده قابل ویرایش نیست.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                data = self.validate_maintenance_data({
                    **{
                        "expert_name": obj.expert_name,
                        "maintenance_description": (
                            obj.maintenance_description
                        ),
                        "maintenance_start_date": (
                            obj.maintenance_start_date.isoformat()
                        ),
                        "maintenance_end_date": (
                            obj.maintenance_end_date.isoformat()
                        ),
                        "maintenance_price": obj.maintenance_price,
                        "maintenance_status": obj.maintenance_status,
                        "service_company": obj.service_company,
                        "maintenance_document_no": (
                                obj.maintenance_document_no or ""
                        ),
                        "details": obj.details or "",
                    },
                    **request.data,
                })

                receiver_fields = (
                    "receiver_type",
                    "unit_id",
                    "receiver_renter_id",
                    "receiver_third_party_id",
                )

                if any(key in request.data for key in receiver_fields):
                    receiver = self.validate_receiver(
                        request, house, {
                            "receiver_type": (
                                    request.data.get("receiver_type")
                                    or ""
                            ),
                            "unit_id": request.data.get("unit_id"),
                            "receiver_renter_id": (
                                request.data.get("receiver_renter_id")
                            ),
                            "receiver_third_party_id": (
                                request.data.get(
                                    "receiver_third_party_id"
                                )
                            ),
                        }
                    )

                    obj.unit = receiver["unit"]
                    obj.receiver_type = receiver["receiver_type"]
                    obj.receiver_renter = receiver["receiver_renter"]
                    obj.receiver_third_party = (
                        receiver["receiver_third_party"]
                    )
                    obj.receiver_name = receiver["receiver_name"]

                new_files = self.get_uploaded_documents(request)

                if obj.documents.count() + len(new_files) > 2:
                    raise ValueError(
                        "هر تعمیر حداکثر دو مدرک دارد."
                    )

                for field, value in data.items():
                    setattr(obj, field, value)

                obj.save()

                for uploaded_file in new_files:
                    MaintenanceDocument.objects.create(
                        maintenance=obj,
                        document=uploaded_file,
                    )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.maintenance_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "تعمیر و نگهداری ویرایش شد.",
            "result": self.serialize_maintenance(obj),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_maintenance(
                request, house, pk, lock=True
            )

            if error:
                return error

            if obj.is_paid:
                return Response({
                    "success": False,
                    "message": "تعمیر پرداخت‌شده قابل حذف نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            obj.delete()

        return Response({
            "success": True,
            "message": "تعمیر و نگهداری با موفقیت حذف شد.",
        })
class ManagerMaintenancePayAPIView(ManagerMaintenanceBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            payment_date = self.parse_date_value(
                request.data.get("payment_date"),
                "تاریخ پرداخت",
            )

            if payment_date > date.today():
                raise ValueError(
                    "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
                )

            bank_id = request.data.get("bank_id")

            if not bank_id:
                raise ValueError("انتخاب حساب بانکی الزامی است.")

            bank = Bank.objects.filter(
                pk=bank_id,
                user=request.user,
                house=house,
                is_active=True,
            ).first()

            if not bank:
                raise ValueError("حساب بانکی فعال یافت نشد.")

            transaction_reference = str(
                request.data.get("transaction_reference") or ""
            ).strip()

            if len(transaction_reference) > 20:
                raise ValueError(
                    "شماره پیگیری نباید بیشتر از ۲۰ کاراکتر باشد."
                )

        except (ValueError, TypeError, ValidationError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            with transaction.atomic():
                obj, error = self.get_maintenance(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "این تعمیر قبلاً پرداخت شده است.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                amount = Decimal(
                    str(obj.maintenance_price or 0)
                )

                if amount <= 0:
                    raise ValueError(
                        "مبلغ تعمیر باید بیشتر از صفر باشد."
                    )

                content_type = ContentType.objects.get_for_model(
                    Maintenance
                )

                previous_withdrawal = BankFund.objects.filter(
                    content_type=content_type,
                    object_id=obj.pk,
                    transaction_type="withdraw",
                    is_paid=True,
                ).exists()

                if previous_withdrawal:
                    raise ValueError(
                        "برای این تعمیر قبلاً برداشت بانکی ثبت شده است؛ "
                        "سوابق مالی را بررسی کنید."
                    )

                receiver = self.validate_receiver(
                    request,
                    house,
                    {
                        "receiver_type": (
                                request.data.get("receiver_type")
                                or obj.receiver_type
                        ),
                        "unit_id": (
                                request.data.get("unit_id")
                                or obj.unit_id
                        ),
                        "receiver_renter_id": (
                                request.data.get("receiver_renter_id")
                                or obj.receiver_renter_id
                        ),
                        "receiver_third_party_id": (
                                request.data.get(
                                    "receiver_third_party_id"
                                )
                                or obj.receiver_third_party_id
                        ),
                    },
                )

                fund = BankTransactionService.withdraw(
                    user=request.user,
                    bank=bank,
                    unit=receiver["unit"],
                    amount=amount,
                    description=(
                                    f"پرداخت تعمیر و نگهداری: "
                                    f"{obj.maintenance_description}"
                                )[:500],
                    content_object=obj,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    receiver_type=receiver["receiver_type"],
                    receiver_renter=receiver["receiver_renter"],
                    receiver_name=receiver["receiver_name"],
                    receiver_third_party=(
                        receiver["receiver_third_party"]
                    ),
                    house=house,
                    gateway="پرداخت تعمیر و نگهداری",
                    financial_document_number=(
                        obj.financial_document_number
                    ),
                )

                obj.bank = bank
                obj.payment_date = payment_date
                obj.transaction_reference = (
                        transaction_reference or None
                )

                obj.receiver_type = receiver["receiver_type"]
                obj.receiver_renter = receiver["receiver_renter"]
                obj.receiver_third_party = (
                    receiver["receiver_third_party"]
                )
                obj.receiver_name = receiver["receiver_name"]
                obj.unit = receiver["unit"]

                obj.is_paid = True

                obj.save(update_fields=[
                    "bank",
                    "payment_date",
                    "transaction_reference",
                    "receiver_type",
                    "receiver_renter",
                    "receiver_third_party",
                    "receiver_name",
                    "unit",
                    "is_paid",
                ])

        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.maintenance_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "پرداخت تعمیر ثبت شد و موجودی بانک به‌روزرسانی شد.",
            "bank_fund_id": fund.pk,
            "result": self.serialize_maintenance(obj),
        })
class ManagerMaintenanceCancelPayAPIView(ManagerMaintenanceBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_maintenance(
                request, house, pk, lock=True
            )

            if error:
                return error

            if not obj.is_paid:
                return Response({
                    "success": False,
                    "message": "این تعمیر هنوز پرداخت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            content_type = ContentType.objects.get_for_model(
                Maintenance
            )

            fund = BankFund.objects.select_for_update().filter(
                content_type=content_type,
                object_id=obj.pk,
                transaction_type="withdraw",
                is_paid=True,
            ).first()

            if not fund:
                return Response({
                    "success": False,
                    "message": (
                        "تراکنش برداشت مربوط به این تعمیر پیدا نشد."
                    ),
                }, status=status.HTTP_404_NOT_FOUND)

            if fund.transfer_group_id:
                return Response({
                    "success": False,
                    "message": (
                        "این تراکنش بخشی از انتقال بانکی است "
                        "و از این مسیر قابل لغو نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            bank = fund.bank

            fund.delete()

            if bank:
                recalculate_bank_balance(bank)

            obj.bank = None
            obj.payment_date = None
            obj.transaction_reference = ""
            obj.is_paid = False

            obj.save(update_fields=[
                "bank",
                "payment_date",
                "transaction_reference",
                "is_paid",
            ])

        obj = self.maintenance_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": (
                "پرداخت تعمیر لغو شد و موجودی بانک مجدداً محاسبه شد."
            ),
            "result": self.serialize_maintenance(obj),
        })
class ManagerMaintenanceBanksAPIView(ManagerMaintenanceBaseAPIView):
    def get(self, request):
        return self.get_manager_banks_response(request)
class ManagerMaintenanceReceiversAPIView(ManagerMaintenanceBaseAPIView):
    def get(self, request):
        return self.get_manager_payers_response(request)
class ManagerPropertyBaseAPIView(ManagerFinancialCommonMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get_house(self, request):
        if not getattr(request.user, "is_middle_admin", False):
            return None, Response({
                "success": False,
                "message": "شما دسترسی مدیر ساختمان را ندارید.",
            }, status=status.HTTP_403_FORBIDDEN)

        house = MyHouse.objects.filter(
            user=request.user,
            is_active=True,
        ).first()

        if not house:
            return None, Response({
                "success": False,
                "message": "ساختمان فعالی برای شما یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return house, None

    @staticmethod
    def normalize_digits(value):
        if value is None:
            return value

        # تبدیل لیست به مقدار واقعی
        if isinstance(value, (list, tuple)):
            value = value[-1] if value else ""

        translation = str.maketrans(
            "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
            "01234567890123456789",
        )

        return (
            str(value)
            .translate(translation)
            .replace(",", "")
            .replace("٬", "")
            .strip()
        )

    @staticmethod
    def normalize_request_data(data):
        result = {}

        for key in data.keys():
            value = data.get(key)

            if isinstance(value, (list, tuple)):
                value = value[-1] if value else ""

            result[key] = value

        return result

    def parse_amount(self, value):
        try:
            amount = Decimal(self.normalize_digits(value))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("ارزش اموال معتبر نیست.")

        if not amount.is_finite() or amount <= 0:
            raise ValueError("ارزش اموال باید بیشتر از صفر باشد.")

        if amount != amount.to_integral_value():
            raise ValueError("ارزش اموال باید عدد صحیح باشد.")

        return int(amount)

    def parse_date_value(self, value, label="تاریخ", required=False):
        value = self.normalize_digits(value)

        if not value:
            if required:
                raise ValueError(f"{label} الزامی است.")
            return None

        parsed = parse_date(value)

        if not parsed:
            raise ValueError(
                f"{label} نامعتبر است؛ قالب YYYY-MM-DD را ارسال کنید."
            )

        return parsed

    @staticmethod
    def get_uploaded_documents(request):
        files = request.FILES.getlist("documents")

        if not files:
            files = request.FILES.getlist("document")

        if len(files) > 2:
            raise ValueError("حداکثر دو مدرک برای هر اموال مجاز است.")

        return files

    @staticmethod
    def property_queryset(user, house):
        return Property.objects.filter(
            user=user,
            house=house,
            is_active=True,
        ).select_related(
            "bank",
            "house",
        ).prefetch_related("documents")

    def get_property(self, request, house, pk, lock=False):
        queryset = Property.objects.filter(
            pk=pk,
            user=request.user,
            house=house,
            is_active=True,
        )

        if lock:
            queryset = queryset.select_for_update()

        obj = queryset.first()

        if not obj:
            return None, Response({
                "success": False,
                "message": "اموال موردنظر یافت نشد.",
            }, status=status.HTTP_404_NOT_FOUND)

        return obj, None

    @staticmethod
    def serialize_property(obj):
        bank = obj.bank

        return {
            "id": obj.id,

            "house_id": obj.house_id,

            "bank_id": obj.bank_id,
            "bank_name": (
                getattr(bank, "bank_name", None)
                if bank else None
            ),
            "account_no": (
                getattr(bank, "account_no", None)
                if bank else None
            ),

            "receiver_name": obj.receiver_name or "",
            "company_name": obj.company_name or "",

            "document_number": obj.document_number,

            "financial_document_number": (
                obj.financial_document_number
            ),

            "count": obj.count,
            "property_name": obj.property_name or "",
            "property_unit": obj.property_unit or "",
            "property_location": obj.property_location or "",
            "property_code": obj.property_code or "",

            "property_price": str(obj.property_price or 0),

            "details": obj.details or "",

            "property_purchase_date": (
                obj.property_purchase_date.isoformat()
                if obj.property_purchase_date else None
            ),

            "is_paid": obj.is_paid,

            "payment_date": (
                obj.payment_date.isoformat()
                if obj.payment_date else None
            ),

            "transaction_reference": (
                    obj.transaction_reference or ""
            ),

            "is_active": obj.is_active,

            "created_at": (
                obj.created_at.isoformat()
                if obj.created_at else None
            ),

            "documents": [
                {
                    "id": document.id,
                    "url": (
                        document.document.url
                        if document.document else None
                    ),
                }
                for document in obj.documents.all()
            ],
        }

    def validate_property_data(self, data):
        company_name = str(
            data.get("company_name") or ""
        ).strip()

        property_name = str(
            data.get("property_name") or ""
        ).strip()

        property_unit = str(
            data.get("property_unit") or ""
        ).strip()

        property_location = str(
            data.get("property_location") or ""
        ).strip()

        property_code = str(
            data.get("property_code") or ""
        ).strip()

        details = str(
            data.get("details") or ""
        ).strip()

        if not property_name:
            raise ValueError("نام اموال الزامی است.")

        if not property_unit:
            raise ValueError("واحد مربوط به اموال الزامی است.")

        if not property_location:
            raise ValueError("آدرس محل نگهداری اموال الزامی است.")

        if not property_code:
            raise ValueError("کد اموال الزامی است.")

        if len(company_name) > 200:
            raise ValueError("نام فروشنده بیش از حد مجاز است.")

        if len(property_name) > 400:
            raise ValueError("نام اموال نباید بیشتر از ۴۰۰ کاراکتر باشد.")

        if len(property_unit) > 3000:
            raise ValueError("واحد اموال بیش از حد مجاز است.")

        if len(property_location) > 400:
            raise ValueError("آدرس اموال بیش از حد مجاز است.")

        if len(property_code) > 200:
            raise ValueError("کد اموال بیش از حد مجاز است.")

        if len(details) > 4000:
            raise ValueError("توضیحات بیش از حد مجاز است.")

        # اعتبارسنجی تعداد
        try:
            raw_count = self.normalize_digits(data.get("count"))

            if raw_count in (None, ""):
                raise ValueError

            count_decimal = Decimal(raw_count)

            if (
                    not count_decimal.is_finite()
                    or count_decimal != count_decimal.to_integral_value()
            ):
                raise ValueError

            count = int(count_decimal)

        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("تعداد اموال معتبر نیست.")

        if count <= 0:
            raise ValueError("تعداد اموال باید بیشتر از صفر باشد.")

        # اعتبارسنجی ارزش مال
        amount = self.parse_amount(
            data.get("property_price")
        )

        # اعتبارسنجی شماره سند
        try:
            document_number = int(
                self.normalize_digits(data.get("document_number"))
            )
        except (TypeError, ValueError):
            raise ValueError("شماره سند معتبر نیست.")

        if document_number <= 0:
            raise ValueError("شماره سند باید بیشتر از صفر باشد.")

        # اعتبارسنجی تاریخ خرید
        purchase_date = self.parse_date_value(
            data.get("property_purchase_date"),
            "تاریخ خرید",
        )

        return {
            "company_name": company_name or None,
            "document_number": document_number,
            "count": count,
            "property_name": property_name,
            "property_unit": property_unit,
            "property_location": property_location,
            "property_code": property_code,
            "property_price": amount,
            "details": details or None,
            "property_purchase_date": purchase_date,
        }
class ManagerPropertyAPIView(ManagerPropertyBaseAPIView):

    def get(self, request):
        house, error = self.get_house(request)

        if error:
            return error

        queryset = self.property_queryset(
            request.user, house
        )

        payment_status = request.query_params.get(
            "payment_status"
        )

        if payment_status == "paid":
            queryset = queryset.filter(is_paid=True)

        elif payment_status == "unpaid":
            queryset = queryset.filter(is_paid=False)

        results = [
            self.serialize_property(item)
            for item in queryset.order_by("-created_at")
        ]

        return Response({
            "success": True,
            "count": len(results),
            "results": results,
        })

    def post(self, request):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            normalized_data = self.normalize_request_data(request.data)

            data = self.validate_property_data(normalized_data)
            documents = self.get_uploaded_documents(request)

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        with transaction.atomic():
            obj = Property.objects.create(
                user=request.user,
                house=house,
                **data,
                is_paid=False,
                is_active=True,
            )

            obj.financial_document_number = (
                get_next_financial_document_number(house)
            )

            obj.save(
                update_fields=["financial_document_number"]
            )

            for uploaded_file in documents:
                PropertyDocument.objects.create(
                    property=obj,
                    document=uploaded_file,
                )

        obj = self.property_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "اموال با موفقیت ثبت شد.",
            "result": self.serialize_property(obj),
        }, status=status.HTTP_201_CREATED)
class ManagerPropertyDetailAPIView(ManagerPropertyBaseAPIView):

    def patch(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            with transaction.atomic():
                obj, error = self.get_property(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "اموال پرداخت‌شده قابل ویرایش نیست.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                old_data = {
                    "receiver_name": obj.receiver_name,
                    "company_name": obj.company_name or "",
                    "document_number": obj.document_number,
                    "count": obj.count,
                    "property_name": obj.property_name,
                    "property_unit": obj.property_unit,
                    "property_location": obj.property_location,
                    "property_code": obj.property_code,
                    "property_price": obj.property_price,
                    "details": obj.details or "",
                    "property_purchase_date": (
                        obj.property_purchase_date.isoformat()
                        if obj.property_purchase_date else ""
                    ),
                }

                request_data = self.normalize_request_data(request.data)

                merged_data = {
                    **old_data,
                    **request_data,
                }

                data = self.validate_property_data(merged_data)

                new_files = self.get_uploaded_documents(request)

                if obj.documents.count() + len(new_files) > 2:
                    raise ValueError(
                        "هر اموال حداکثر دو مدرک می‌تواند داشته باشد."
                    )

                for field, value in data.items():
                    setattr(obj, field, value)

                obj.save()

                for uploaded_file in new_files:
                    PropertyDocument.objects.create(
                        property=obj,
                        document=uploaded_file,
                    )

        except ValueError as exc:
            return Response({
                "success": False,
                "message": str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.property_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "اموال با موفقیت ویرایش شد.",
            "result": self.serialize_property(obj),
        })

    def delete(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_property(
                request, house, pk, lock=True
            )

            if error:
                return error

            if obj.is_paid:
                return Response({
                    "success": False,
                    "message": "اموال پرداخت‌شده قابل حذف نیست.",
                }, status=status.HTTP_400_BAD_REQUEST)

            obj.delete()

        return Response({
            "success": True,
            "message": "اموال با موفقیت حذف شد.",
        })
class ManagerPropertyPayAPIView(ManagerPropertyBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        try:
            payment_date = self.parse_date_value(
                request.data.get("payment_date"),
                "تاریخ پرداخت",
                required=True,
            )

            if payment_date > date.today():
                raise ValueError(
                    "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
                )

            bank_id = request.data.get("bank_id")

            if not bank_id:
                raise ValueError("انتخاب حساب بانکی الزامی است.")

            receiver_name = str(
                request.data.get("receiver_name") or ""
            ).strip()

            if not receiver_name:
                raise ValueError("نام دریافت‌کننده الزامی است.")

            if len(receiver_name) > 200:
                raise ValueError(
                    "نام دریافت‌کننده نباید بیشتر از ۲۰۰ کاراکتر باشد."
                )

            transaction_reference = str(
                self.normalize_digits(
                    request.data.get("transaction_reference") or ""
                )
            ).strip()

            if len(transaction_reference) > 20:
                raise ValueError(
                    "شماره پیگیری نباید بیشتر از ۲۰ کاراکتر باشد."
                )

            with transaction.atomic():

                obj, error = self.get_property(
                    request, house, pk, lock=True
                )

                if error:
                    return error

                if obj.is_paid:
                    return Response({
                        "success": False,
                        "message": "این اموال قبلاً پرداخت شده است.",
                    }, status=status.HTTP_400_BAD_REQUEST)

                if (
                        obj.property_purchase_date
                        and payment_date < obj.property_purchase_date
                ):
                    raise ValueError(
                        "تاریخ پرداخت نمی‌تواند قبل از تاریخ خرید اموال باشد."
                    )

                amount = Decimal(
                    str(obj.property_price or 0)
                )

                if amount <= 0:
                    raise ValueError(
                        "ارزش اموال باید بیشتر از صفر باشد."
                    )

                bank = Bank.objects.select_for_update().filter(
                    pk=bank_id,
                    user=request.user,
                    house=house,
                    is_active=True,
                ).first()

                if not bank:
                    raise ValueError("حساب بانکی فعال یافت نشد.")

                content_type = ContentType.objects.get_for_model(
                    Property
                )

                previous_withdrawal = BankFund.objects.filter(
                    content_type=content_type,
                    object_id=obj.pk,
                    transaction_type="withdraw",
                    is_paid=True,
                ).exists()

                if previous_withdrawal:
                    raise ValueError(
                        "برای این اموال قبلاً برداشت بانکی ثبت شده است؛ "
                        "سوابق مالی را بررسی کنید."
                    )

                fund = BankTransactionService.withdraw(
                    user=request.user,
                    bank=bank,
                    unit=None,
                    amount=amount,
                    description=(
                                    f"پرداخت بابت خرید اموال: {obj.property_name}"
                                )[:500],
                    content_object=obj,
                    payment_date=payment_date,
                    transaction_no=transaction_reference or None,
                    receiver_name=receiver_name,
                    house=house,
                    gateway="پرداخت خرید اموال",
                    financial_document_number=(
                        obj.financial_document_number
                    ),
                )

                obj.bank = bank
                obj.payment_date = payment_date
                obj.receiver_name = receiver_name
                obj.transaction_reference = (
                        transaction_reference or None
                )
                obj.is_paid = True

                obj.save(update_fields=[
                    "bank",
                    "payment_date",
                    "receiver_name",
                    "transaction_reference",
                    "is_paid",
                ])

        except (ValidationError, ValueError, TypeError) as exc:
            messages = getattr(exc, "messages", None)

            return Response({
                "success": False,
                "message": messages[0] if messages else str(exc),
            }, status=status.HTTP_400_BAD_REQUEST)

        obj = self.property_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": "پرداخت اموال ثبت شد و موجودی بانک به‌روزرسانی شد.",
            "bank_fund_id": fund.pk,
            "result": self.serialize_property(obj),
        })
class ManagerPropertyCancelPayAPIView(ManagerPropertyBaseAPIView):

    def post(self, request, pk):
        house, error = self.get_house(request)

        if error:
            return error

        with transaction.atomic():
            obj, error = self.get_property(
                request, house, pk, lock=True
            )

            if error:
                return error

            if not obj.is_paid:
                return Response({
                    "success": False,
                    "message": "این اموال هنوز پرداخت نشده است.",
                }, status=status.HTTP_400_BAD_REQUEST)

            content_type = ContentType.objects.get_for_model(
                Property
            )

            fund = BankFund.objects.select_for_update().filter(
                content_type=content_type,
                object_id=obj.pk,
                transaction_type="withdraw",
                is_paid=True,
            ).first()

            if not fund:
                return Response({
                    "success": False,
                    "message": (
                        "تراکنش برداشت مربوط به این اموال پیدا نشد."
                    ),
                }, status=status.HTTP_404_NOT_FOUND)

            if fund.transfer_group_id:
                return Response({
                    "success": False,
                    "message": (
                        "این تراکنش بخشی از انتقال بانکی است "
                        "و از این مسیر قابل لغو نیست."
                    ),
                }, status=status.HTTP_400_BAD_REQUEST)

            bank = fund.bank

            fund.delete()

            if bank:
                recalculate_bank_balance(bank)

            obj.bank = None
            obj.payment_date = None
            obj.transaction_reference = ""
            obj.receiver_name = ""
            obj.is_paid = False

            obj.save(update_fields=[
                "bank",
                "payment_date",
                "receiver_name",
                "transaction_reference",
                "is_paid",
            ])

        obj = self.property_queryset(
            request.user, house
        ).get(pk=obj.pk)

        return Response({
            "success": True,
            "message": (
                "پرداخت اموال لغو شد و موجودی بانک مجدداً محاسبه شد."
            ),
            "result": self.serialize_property(obj),
        })
class ManagerPropertyBanksAPIView(ManagerPropertyBaseAPIView):

    def get(self, request):
        return self.get_manager_banks_response(request)
