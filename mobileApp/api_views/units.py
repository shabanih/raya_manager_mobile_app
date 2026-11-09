"""Units API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403


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
            .order_by('unit')
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
