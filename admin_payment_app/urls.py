from django.conf import settings
from django.conf.urls.static import static
from django.urls import path
from admin_payment_app import views

urlpatterns = [
    path('sms-pay/request/', views.request_sms_pay, name='request_sms_pay'),
    path('verify-sms-pay/', views.verify_sms_credit_pay, name='verify_sms_pay'),

    path('subscription/pay/request/', views.request_subscription_pay, name='request_subscription_pay'),
    path('verify-subscription-pay/', views.verify_subscription_pay, name='verify_subscription_pay'),

    path(
        'request-subscription-by-user/<int:user_id>/',
        views.request_subscription_pay_by_user,
        name='request_subscription_pay_by_user'
    ),

    # callback درگاه پرداخت
    path(
        'verify-subscription-by-user/',
        views.verify_subscription_pay_by_user,
        name='verify_subscription_pay_by_user'
    ),

]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
