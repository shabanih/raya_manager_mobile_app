"""App API views.
Extracted from the original mobileApp/views.py.
"""
from .common import *  # noqa: F401,F403

class ContactUsCreateAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        subject = request.data.get('subject', '').strip()
        message = request.data.get('message', '').strip()

        if not subject:
            return Response({
                'success': False,
                'message': 'موضوع پیشنهاد را وارد کنید.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not message:
            return Response({
                'success': False,
                'message': 'متن پیشنهاد را وارد کنید.'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(message) > 360:
            return Response({
                'success': False,
                'message': 'متن پیشنهاد حداکثر باید ۳۶۰ کاراکتر باشد.'
            }, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        contact = ContactUs.objects.create(
            name=user.get_full_name() or str(user),
            mobile=user.mobile,
            subject=subject,
            message=message,
        )

        return Response({
            'success': True,
            'message': 'پیشنهاد شما با موفقیت ثبت شد.',
            'id': contact.id,
        }, status=status.HTTP_201_CREATED)
class LatestAppVersionAPIView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        version = AppVersion.objects.filter(
            is_active=True
        ).order_by('-created_at').first()

        if not version:
            return Response({
                'success': False,
                'message': 'هیچ نسخه فعالی ثبت نشده است.'
            }, status=404)

        return Response({
            'success': True,
            'version': version.version,
            'download_url': version.download_url,
            'force_update': version.force_update,
            'release_notes': version.release_notes,
            'created_at': version.created_at,
        })
class AppInstallationAPIView(APIView):
    """
    ثبت نصب و به‌روزرسانی آخرین فعالیت اپلیکیشن
    """

    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]

    def post(self, request):

        installation_id = request.data.get('installation_id')
        app_version = request.data.get('app_version', '')
        platform = request.data.get('platform', 'Android')
        device_name = request.data.get('device_name', '')

        if not installation_id:
            return Response(
                {
                    'success': False,
                    'message': 'شناسه نصب ارسال نشده است.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # اعتبارسنجی UUID
        try:
            installation_id = uuid.UUID(str(installation_id))
        except (ValueError, TypeError, AttributeError):
            return Response(
                {
                    'success': False,
                    'message': 'شناسه نصب معتبر نیست.'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            installation, created = AppInstallation.objects.get_or_create(
                installation_id=installation_id,
                defaults={
                    'app_version': app_version,
                    'platform': platform,
                    'device_name': device_name,
                    'user': (
                        request.user
                        if request.user.is_authenticated
                        else None
                    ),
                    'is_active': True,
                }
            )

            if not created:
                installation.app_version = app_version
                installation.platform = platform
                installation.device_name = device_name
                installation.is_active = True

                # فقط در صورت ورود کاربر، نصب به او متصل شود
                if request.user.is_authenticated:
                    installation.user = request.user

                installation.save()

            return Response(
                {
                    'success': True,
                    'message': 'اطلاعات نصب با موفقیت ثبت شد.',
                    'created': created,
                    'installation_id': str(installation.installation_id),
                },
                status=status.HTTP_200_OK
            )

        except Exception:
            logging.exception(
                'App installation registration failed'
            )

            return Response(
                {
                    'success': False,
                    'message': 'خطا در ثبت اطلاعات نصب.'
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
