"""Manager Communications API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
                    ).lower() in ['true', '1', 'yes', 'on']
            )

        if 'is_active' in request.data:
            announcement.is_active = (
                    str(
                        request.data.get('is_active')
                    ).lower() in ['true', '1', 'yes', 'on']
            )

        announcement.save()

        # ================================================
        # حذف فایل‌های قبلی
        # ================================================

        deleted_ids = request.data.get(
            'deleted_document_ids',
            ''
        )

        if isinstance(deleted_ids, str):
            deleted_ids = [
                item.strip()
                for item in deleted_ids.split(',')
                if item.strip()
            ]

        elif isinstance(deleted_ids, list):
            deleted_ids = [
                str(item).strip()
                for item in deleted_ids
                if str(item).strip()
            ]

        if deleted_ids:
            documents = AnnouncementDocument.objects.filter(
                announcement=announcement,
                id__in=deleted_ids
            )

            for document in documents:
                if document.document:
                    document.document.delete(save=False)

                document.delete()

        # ================================================
        # اضافه کردن فایل‌های جدید
        # ================================================

        files = request.FILES.getlist('documents')

        for uploaded_file in files:
            AnnouncementDocument.objects.create(
                announcement=announcement,
                document=uploaded_file
            )

        # ================================================
        # پاسخ نهایی
        # ================================================

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
                gateway='افتتاحیه',
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
