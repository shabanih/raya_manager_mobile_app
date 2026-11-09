"""Authentication API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

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
