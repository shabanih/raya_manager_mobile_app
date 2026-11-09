"""Support API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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

        ALLOWED_IMAGE_EXTENSIONS = {
            '.jpg',
            '.jpeg',
            '.png',
            '.webp',
            '.gif',
        }

        for uploaded_file in uploaded_files:

            # بررسی پسوند فایل
            extension = os.path.splitext(
                uploaded_file.name
            )[1].lower()

            if extension not in ALLOWED_IMAGE_EXTENSIONS:
                return Response({
                    'success': False,
                    'message': 'فرمت فایل تصویری پشتیبانی نمی‌شود.',
                }, status=status.HTTP_400_BAD_REQUEST)

            # بررسی واقعی بودن تصویر
            try:
                from PIL import Image
                image = Image.open(uploaded_file)
                image.verify()

            except (UnidentifiedImageError, OSError, ValueError):
                return Response({
                    'success': False,
                    'message': 'فایل انتخاب‌شده یک تصویر معتبر نیست.',
                }, status=status.HTTP_400_BAD_REQUEST)

            # آماده‌سازی مجدد فایل پس از verify
            uploaded_file.seek(0)

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
