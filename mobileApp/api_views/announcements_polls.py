"""Announcements Polls API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
class MobilePollListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):

        user = request.user

        # -------------------------------------------------
        # مجتمع کاربر
        # -------------------------------------------------

        user_house = user.house

        if not user_house:


            return Response({
                'success': False,
                'message': 'مجتمع کاربر مشخص نیست.',
                'polls': [],
            })

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



        # -------------------------------------------------
        # اگر کاربر نه مالک است نه مستاجر
        # -------------------------------------------------

        if not is_owner and not is_renter:


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
