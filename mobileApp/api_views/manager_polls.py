"""Manager Polls API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
