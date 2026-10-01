from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView

from .views import LoginView, MeView, DashboardView, ManualChargePaymentView, OnlineChargePaymentView, \
    ChargePaymentMethodsView, MobileChargeListView, MobileChargeDetailView, MobilePaymentHistoryView, \
    MobileAnnouncementListView, MobilePollListView, MobilePollDetailView, MobilePollVoteView, ChargePaymentBanksView, \
    CivilChargeListAPIView, CivilChargeInstallmentsAPIView, CivilChargePaymentMethodsView, ManualCivilPaymentView, \
    ManualSewagePaymentView, SewageChargePaymentMethodsView, SewageChargeInstallmentsAPIView, SewageChargeListAPIView, \
    MessageListAPIView, MessageDetailAPIView, MessageReadAPIView, UserPayMoneyListCreateView, \
    UserPayMoneyPaymentMethodsView, ManualUserPayMoneyPaymentView, ManagerDashboardView, \
    ManagerAnnouncementListCreateView, ManagerAnnouncementDetailView, ManagerMessageUnitsAPIView, \
    ManagerMessageListCreateAPIView, ManagerMessageDetailAPIView, ManagerMessageSendAPIView, ManagerBankListCreateView, \
    ManagerBankDetailView, ManagerBankTransferListCreateView, ManagerBankTransferDeleteView, ManagerHouseListView, \
    ManagerPollListCreateView, ManagerPollDetailView, ManagerPollToggleActiveView, ManagerPollResultsView, \
    MobileSupportTicketListView, MobileSupportTicketCreateView, MobileSupportTicketDetailView, \
    MobileSupportTicketMessageView, MobileSupportTicketCloseView, ManagerSupportTicketListView, \
    ManagerSupportTicketDetailView, ManagerSupportTicketMessageView, ManagerSupportTicketCloseView

urlpatterns = [
    path(
        'auth/login/',
        LoginView.as_view(),
        name='api_login'
    ),

    # داشبورد مدیر
    path(
        'manager/dashboard/',
        ManagerDashboardView.as_view(),
        name='manager_dashboard'
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

    # Managers Urls

    path(
        'manager/announcements/',
        ManagerAnnouncementListCreateView.as_view(),
        name='manager_announcements'
    ),

    path(
        'manager/announcements/<int:pk>/',
        ManagerAnnouncementDetailView.as_view(),
        name='manager_announcement_detail'
    ),

    # ============================================================
    # مدیریت پیام‌های مدیر
    # یک لیست برای همه پیام‌ها
    # ============================================================

    path(
        'manager/messages/',
        ManagerMessageListCreateAPIView.as_view(),
        name='manager-message-list-create',
    ),

    # ============================================================
    # واحدهای قابل انتخاب برای پیام
    # ============================================================

    path(
        'manager/messages/units/',
        ManagerMessageUnitsAPIView.as_view(),
        name='manager-message-units',
    ),

    # ============================================================
    # جزئیات / ویرایش / حذف
    # ============================================================

    path(
        'manager/messages/<int:pk>/',
        ManagerMessageDetailAPIView.as_view(),
        name='manager-message-detail',
    ),

    # ============================================================
    # ارسال پیام
    # ============================================================

    path(
        'manager/messages/<int:pk>/send/',
        ManagerMessageSendAPIView.as_view(),
        name='manager-message-send',
    ),

    # -----------------------------
    # بانکها
    # -----------------------------
    path(
        'manager/houses/',
        ManagerHouseListView.as_view(),
        name='manager-house-list'
    ),
    path(
        'manager/banks/',
        ManagerBankListCreateView.as_view(),
        name='manager-bank-list-create'
    ),

    path(
        'manager/banks/<int:pk>/',
        ManagerBankDetailView.as_view(),
        name='manager-bank-detail'
    ),

    path(
        'manager/bank-transfers/',
        ManagerBankTransferListCreateView.as_view(),
        name='manager-bank-transfer-list-create'
    ),

    path(
        'manager/bank-transfers/<int:pk>/',
        ManagerBankTransferDeleteView.as_view(),
        name='manager-bank-transfer-delete'
    ),

    # -----------------------------
    # نظرسنجی
    # -----------------------------
    path(
        'manager/polls/',
        ManagerPollListCreateView.as_view(),
        name='manager_poll_list_create'
    ),

    # جزئیات + ویرایش + حذف
    path(
        'manager/polls/<int:poll_id>/',
        ManagerPollDetailView.as_view(),
        name='manager_poll_detail'
    ),

    # فعال / غیرفعال
    path(
        'manager/polls/<int:poll_id>/toggle-active/',
        ManagerPollToggleActiveView.as_view(),
        name='manager_poll_toggle_active'
    ),

    # نتایج
    path(
        'manager/polls/<int:poll_id>/results/',
        ManagerPollResultsView.as_view(),
        name='manager_poll_results'
    ),
    # -------------------------------------------------
    # TICKET /User
    # -------------------------------------------------

    path(
        'support/tickets/',
        MobileSupportTicketListView.as_view(),
        name='mobile_support_ticket_list',
    ),

    path(
        'support/tickets/create/',
        MobileSupportTicketCreateView.as_view(),
        name='mobile_support_ticket_create',
    ),

    path(
        'support/tickets/<int:ticket_id>/',
        MobileSupportTicketDetailView.as_view(),
        name='mobile_support_ticket_detail',
    ),

    path(
        'support/tickets/<int:ticket_id>/messages/',
        MobileSupportTicketMessageView.as_view(),
        name='mobile_support_ticket_message',
    ),

    path(
        'support/tickets/<int:ticket_id>/close/',
        MobileSupportTicketCloseView.as_view(),
        name='mobile_support_ticket_close',
    ),

    # -------------------------------------------------
    # TICKET/Manager
    # -------------------------------------------------

    path(
        'manager/support/tickets/',
        ManagerSupportTicketListView.as_view(),
        name='manager_support_ticket_list',
    ),

    path(
        'manager/support/tickets/<int:ticket_id>/',
        ManagerSupportTicketDetailView.as_view(),
        name='manager_support_ticket_detail',
    ),

    path(
        'manager/support/tickets/<int:ticket_id>/messages/',
        ManagerSupportTicketMessageView.as_view(),
        name='manager_support_ticket_message',
    ),

    path(
        'manager/support/tickets/<int:ticket_id>/close/',
        ManagerSupportTicketCloseView.as_view(),
        name='manager_support_ticket_close',
    ),
]
