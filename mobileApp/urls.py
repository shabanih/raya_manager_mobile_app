from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, DashboardView, ManualChargePaymentView, OnlineChargePaymentView, \
    ChargePaymentMethodsView, MobileChargeListView, MobileChargeDetailView, MobilePaymentHistoryView, \
    MobileAnnouncementListView, MobilePollListView, MobilePollDetailView, MobilePollVoteView, ChargePaymentBanksView, \
    CivilChargeListAPIView, CivilChargeInstallmentsAPIView, CivilChargePaymentMethodsView, ManualCivilPaymentView, \
    ManualSewagePaymentView, SewageChargePaymentMethodsView, SewageChargeInstallmentsAPIView, SewageChargeListAPIView, \
    MessageListAPIView, MessageDetailAPIView, MessageReadAPIView, UserPayMoneyListCreateView, \
    UserPayMoneyPaymentMethodsView, ManualUserPayMoneyPaymentView

urlpatterns = [
    path(
        'auth/login/',
        LoginView.as_view(),
        name='api_login'
    ),

    path(
        'auth/me/',
        MeView.as_view(),
        name='api_me'
    ),
    path(
        'auth/refresh/',
        TokenRefreshView.as_view(),
        name='api_token_refresh'
    ),
    # path(
    #     'charges/',
    #     MyChargesView.as_view(),
    #     name='my_charges'
    # ),
    path(
        'dashboard/',
        DashboardView.as_view(),
        name='api_dashboard'
    ),
    path(
        'charges/<int:charge_id>/payment/manual/',
        ManualChargePaymentView.as_view(),
        name='mobile_manual_charge_payment'
    ),
    path(
        'charges/<int:charge_id>/payment/online/',
        OnlineChargePaymentView.as_view(),
        name='online_charge_payment'
    ),
    path(
        'charges/<int:charge_id>/payment-banks/',
        ChargePaymentBanksView.as_view(),
        name='charge-payment-banks',
    ),
    path(
        'charges/<int:charge_id>/payment-methods/',
        ChargePaymentMethodsView.as_view(),
        name='charge_payment_methods'
    ),
    path(
        'charges/',
        MobileChargeListView.as_view(),
        name='mobile_charge_list'
    ),
    path(
        'charges/<int:charge_id>/',
        MobileChargeDetailView.as_view(),
        name='mobile_charge_detail'
    ),
    path(
        'payments/history/',
        MobilePaymentHistoryView.as_view(),
        name='mobile_payment_history'
    ),
    path(
        'announcements/',
        MobileAnnouncementListView.as_view(),
        name='mobile_announcements'
    ),
    path(
        'polls/',
        MobilePollListView.as_view(),
        name='mobile_poll_list'
        ),

    path(
        'polls/<int:pk>/',
        MobilePollDetailView.as_view(),
        name='mobile_poll_detail'
    ),

    path(
        'polls/<int:pk>/vote/',
        MobilePollVoteView.as_view(),
        name='mobile_poll_vote'
    ),
    # شارژهای عمرانی ساختمان
    path(
        'civil-charges/',
        CivilChargeListAPIView.as_view(),
        name='api-civil-charge-list',
    ),

    # اقساط یک شارژ عمرانی
    path(
        'civil-charges/<int:civil_id>/installments/',
        CivilChargeInstallmentsAPIView.as_view(),
        name='api-civil-charge-installments',
    ),

    path(
        'civil-installments/<int:installment_id>/payment-methods/',
        CivilChargePaymentMethodsView.as_view(),
        name='api-civil-installment-payment-methods',
    ),

    path(
        'civil-installments/<int:installment_id>/manual-payment/',
        ManualCivilPaymentView.as_view(),
        name='api-civil-installment-manual-payment',
    ),

    # فاضلاب ساختمان
    path(
        'sewage-charges/',
        SewageChargeListAPIView.as_view(),
        name='api-sewage-charge-list',
    ),

    # اقساط فاضلاب
    path(
        'sewage-charges/<int:sewage_id>/installments/',
        SewageChargeInstallmentsAPIView.as_view(),
        name='api-sewage-charge-installments',
    ),

    path(
        'sewage-installments/<int:installment_id>/payment-methods/',
        SewageChargePaymentMethodsView.as_view(),
        name='api-sewage-installment-payment-methods',
    ),

    path(
        'sewage-installments/<int:installment_id>/manual-payment/',
        ManualSewagePaymentView.as_view(),
        name='api-sewage-installment-manual-payment',
    ),

    path(
        'messages/',
        MessageListAPIView.as_view(),
        name='mobile-message-list',
    ),

    path(
        'messages/<int:message_id>/',
        MessageDetailAPIView.as_view(),
        name='mobile-message-detail',
    ),

    path(
        'messages/<int:message_id>/read/',
        MessageReadAPIView.as_view(),
        name='mobile-message-read',
    ),

    path(
        'user-payments/',
        UserPayMoneyListCreateView.as_view(),
        name='user-payments',
    ),
    path(
        'user-payments/<int:payment_id>/payment-methods/',
        UserPayMoneyPaymentMethodsView.as_view(),
        name='user-payments-payment-methods',
    ),
    path(
        'user-payments/<int:payment_id>/manual-payment/',
        ManualUserPayMoneyPaymentView.as_view(),
        name='user-payments-manual-payment',
    ),
]