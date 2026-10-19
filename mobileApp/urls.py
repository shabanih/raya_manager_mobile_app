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
    ManagerSupportTicketDetailView, ManagerSupportTicketMessageView, ManagerSupportTicketCloseView, \
    ManagerSupportTicketWaitingView, UserSupportTicketReadView, UserSupportTicketCloseView, \
    UserSupportTicketMessageView, UserSupportTicketDetailView, UserSupportTicketListCreateView, \
    UserSupportUnreadCountView, ManagerSupportUnreadCountView, ManagerAdminSupportTicketListView, \
    ManagerAdminSupportTicketCreateView, ManagerAdminSupportTicketDetailView, ManagerAdminSupportTicketMessageView, \
    ManagerAdminSupportTicketReadView, ManagerAdminSupportUnreadCountView, ManagerAdminSupportTicketCloseView, \
    ManagerChargeHomeView, \
    ManagerFixedChargeCreateView, ManagerFixedChargeAPIView, ManagerFixedChargeUnitsAPIView, \
    ManagerFixedChargeSendAPIView, ManagerFixedChargeCancelAPIView, ManagerAreaChargeUnitsAPIView, \
    ManagerAreaChargeSendAPIView, ManagerAreaChargeCancelAPIView, ManagerUnitCreateAPIView, ManagerUnitUpdateAPIView, \
    ManagerRenterUpdateAPIView, ManagerUnitRentersAPIView, ManagerUnitListAPIView, ManagerRenterDeactivateAPIView, \
    ManagerRenterDeleteAPIView, ManagerUnitDetailAPIView, ManagerUnitOwnerUpdateAPIView, ManagerUnitStatusAPIView, \
    ManagerRenterActivateAPIView, ManagerAreaChargeAPIView, ManagerPersonChargeAPIView, ManagerPersonChargeUnitsAPIView, \
    ManagerPersonChargeCancelAPIView, ManagerPersonChargeSendAPIView, ManagerFixAreaChargeAPIView, \
    ManagerFixAreaChargeUnitsAPIView, ManagerFixAreaChargeSendAPIView, ManagerFixAreaChargeCancelAPIView, \
    ManagerFixPersonChargeAPIView, ManagerFixPersonChargeUnitsAPIView, ManagerFixPersonChargeSendAPIView, \
    ManagerFixPersonChargeCancelAPIView, ManagerPersonAreaChargeAPIView, ManagerPersonAreaChargeUnitsAPIView, \
    ManagerPersonAreaChargeSendAPIView, ManagerPersonAreaChargeCancelAPIView, ManagerFixPersonAreaChargeAPIView, \
    ManagerFixPersonAreaChargeUnitsAPIView, ManagerFixPersonAreaChargeSendAPIView, \
    ManagerFixPersonAreaChargeCancelAPIView, ManagerFixVariableChargeAPIView, ManagerFixVariableChargeUnitsAPIView, \
    ManagerFixVariableChargeSendAPIView, ManagerFixVariableChargeCancelAPIView, ManagerChargeCalculationAPIView, \
    ManagerChargeCalculationItemsAPIView, ManagerChargeCalculationUnitsAPIView, ManagerChargeCalculationSendAPIView, \
    ManagerChargeCalculationCancelAPIView

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
    # =====================================================
    # Resident ticket
    # =====================================================

    path(
        'user-support/tickets/',
        UserSupportTicketListCreateView.as_view(),
        name='user_support_ticket_list_create',
    ),

    path(
        'user-support/tickets/<int:ticket_id>/',
        UserSupportTicketDetailView.as_view(),
        name='user_support_ticket_detail',
    ),

    path(
        'user-support/tickets/<int:ticket_id>/messages/',
        UserSupportTicketMessageView.as_view(),
        name='user_support_ticket_message_create',
    ),

    path(
        'user-support/tickets/<int:ticket_id>/close/',
        UserSupportTicketCloseView.as_view(),
        name='user_support_ticket_close',
    ),

    path(
        'user-support/tickets/<int:ticket_id>/read/',
        UserSupportTicketReadView.as_view(),
        name='user_support_ticket_read',
    ),
    path(
        'user-support/unread-count/',
        UserSupportUnreadCountView.as_view(),
        name='user_support_unread_count',
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
    path(
        'manager/support/tickets/<int:ticket_id>/waiting/',
        ManagerSupportTicketWaitingView.as_view(),
        name='manager_support_ticket_waiting',
    ),
    path(
        'manager-support/unread-count/',
        ManagerSupportUnreadCountView.as_view(),
        name='manager_support_unread_count',
    ),

    # =========================================================
    # مدیریت پشتیبانی مدیر ساختمان
    # =========================================================

    path(
        'manager/admin-support/tickets/',
        ManagerAdminSupportTicketListView.as_view(),
        name='manager_admin_support_ticket_list',
    ),

    path(
        'manager/admin-support/tickets/create/',
        ManagerAdminSupportTicketCreateView.as_view(),
        name='manager_admin_support_ticket_create',
    ),

    path(
        'manager/admin-support/tickets/<int:ticket_id>/',
        ManagerAdminSupportTicketDetailView.as_view(),
        name='manager_admin_support_ticket_detail',
    ),

    path(
        'manager/admin-support/tickets/<int:ticket_id>/message/',
        ManagerAdminSupportTicketMessageView.as_view(),
        name='manager_admin_support_ticket_message',
    ),

    path(
        'manager/admin-support/tickets/<int:ticket_id>/close/',
        ManagerAdminSupportTicketCloseView.as_view(),
        name='manager_admin_support_ticket_close',
    ),

    path(
        'manager/admin-support/tickets/<int:ticket_id>/read/',
        ManagerAdminSupportTicketReadView.as_view(),
        name='manager_admin_support_ticket_read',
    ),

    path(
        'manager/admin-support/unread-count/',
        ManagerAdminSupportUnreadCountView.as_view(),
        name='manager_admin_support_unread_count',
    ),

    # =====================================================
    # مدیریت واحدها
    # =====================================================

    # path(
    #     'manager/units/',
    #     ManagerUnitListCreateView.as_view(),
    #     name='manager_units',
    # ),
    #
    # # جزئیات / ویرایش / حذف واحد
    # path(
    #     'manager/units/<int:unit_id>/',
    #     ManagerUnitDetailView.as_view(),
    #     name='manager_unit_detail',
    # ),
    #
    # # =====================================================
    # # مستأجر
    # # =====================================================
    #
    # path(
    #     'manager/units/<int:unit_id>/renters/',
    #     ManagerUnitAddRenterView.as_view(),
    #     name='manager_unit_add_renter',
    # ),
    #
    # path(
    #     'manager/units/<int:unit_id>/renters/<int:renter_id>/',
    #     ManagerRenterDetailView.as_view(),
    #     name='manager_renter_detail',
    # ),

    # ثبت واحد و مالک
    path(
        'manager/units/create/',
        ManagerUnitCreateAPIView.as_view(),
        name='api_manager_unit_create',
    ),

    # ویرایش واحد و مالک
    path(
        'manager/units/<int:unit_id>/update/',
        ManagerUnitUpdateAPIView.as_view(),
        name='api_manager_unit_update',
    ),
    path(
        'manager/units/<int:unit_id>/',
        ManagerUnitDetailAPIView.as_view(),
        name='api_manager_unit_detail'
    ),
    path(
        'manager/units/<int:unit_id>/owner/',
        ManagerUnitOwnerUpdateAPIView.as_view(),
        name='api_manager_unit_owner_update',
    ),

    path(
        'manager/units/<int:unit_id>/status/',
        ManagerUnitStatusAPIView.as_view(),
        name='api_manager_unit_status',
    ),

    # لیست مستأجران و افزودن مستأجر
    path(
        'manager/units/<int:unit_id>/renters/',
        ManagerUnitRentersAPIView.as_view(),
        name='api_manager_unit_renters',
    ),

    # ویرایش مستأجر فعال
    path(
        'manager/renters/<int:renter_id>/update/',
        ManagerRenterUpdateAPIView.as_view(),
        name='api_manager_renter_update',
    ),

    path(
        'manager/renters/<int:renter_id>/deactivate/',
        ManagerRenterDeactivateAPIView.as_view(),
        name='api_manager_renter_deactivate',
    ),
    path(
        'manager/renters/<int:renter_id>/activate/',
        ManagerRenterActivateAPIView.as_view(),
        name='manager-renter-activate',
    ),

    path(
        'manager/renters/<int:renter_id>/delete/',
        ManagerRenterDeleteAPIView.as_view(),
        name='api_manager_renter_delete',
    ),
    path(
        'manager/units/',
        ManagerUnitListAPIView.as_view(),
        name='api_manager_unit_list',
    ),

    # ============= Charge Urls ======================

    path(
        'manager/charges/',
        ManagerChargeHomeView.as_view(),
        name='manager-charge-home',
    ),

    path(
        "manager/charges/fixed/",
        ManagerFixedChargeAPIView.as_view(),
        name="manager-fixed-charges",
    ),

    # مشاهده جزئیات، ویرایش و حذف شارژ واحدی
    path(
        "manager/charges/fixed/<int:pk>/",
        ManagerFixedChargeAPIView.as_view(),
        name="manager-fixed-charge-detail",
    ),

    # فهرست واحدهای شارژ
    path(
        "manager/charges/fixed/<int:pk>/units/",
        ManagerFixedChargeUnitsAPIView.as_view(),
        name="manager-fixed-charge-units",
    ),

    # ارسال اطلاعیه برای واحدهای انتخاب‌شده
    path(
        "manager/charges/fixed/<int:pk>/units/send/",
        ManagerFixedChargeSendAPIView.as_view(),
        name="manager-fixed-charge-send",
    ),

    # لغو اطلاعیه واحدهای انتخاب‌شده
    path(
        "manager/charges/fixed/<int:pk>/units/cancel/",
        ManagerFixedChargeCancelAPIView.as_view(),
        name="manager-fixed-charge-cancel",
    ),
    # ============= Area Charge Urls ======================
    path(
        "manager/charges/area/",
        ManagerAreaChargeAPIView.as_view(),
        name="manager-area-charges",
    ),
    path(
        "manager/charges/area/<int:pk>/",
        ManagerAreaChargeAPIView.as_view(),
        name="manager-area-charge-detail",
    ),
    path(
        "manager/charges/area/<int:pk>/units/",
        ManagerAreaChargeUnitsAPIView.as_view(),
        name="manager-area-charge-units",
    ),
    path(
        "manager/charges/area/<int:pk>/units/send/",
        ManagerAreaChargeSendAPIView.as_view(),
        name="manager-area-charge-send",
    ),
    path(
        "manager/charges/area/<int:pk>/units/cancel/",
        ManagerAreaChargeCancelAPIView.as_view(),
        name="manager-area-charge-cancel",
    ),
    # ============= Person Charge Urls ======================
    path(
        "manager/charges/person/",
        ManagerPersonChargeAPIView.as_view(),
        name="manager-person-charges",
    ),

    path(
        "manager/charges/person/<int:pk>/",
        ManagerPersonChargeAPIView.as_view(),
        name="manager-person-charge-detail",
    ),

    path(
        "manager/charges/person/<int:pk>/units/",
        ManagerPersonChargeUnitsAPIView.as_view(),
        name="manager-person-charge-units",
    ),

    path(
        "manager/charges/person/<int:pk>/units/send/",
        ManagerPersonChargeSendAPIView.as_view(),
        name="manager-person-charge-send",
    ),

    path(
        "manager/charges/person/<int:pk>/units/cancel/",
        ManagerPersonChargeCancelAPIView.as_view(),
        name="manager-person-charge-cancel",
    ),
    # ============= Fix Area Charge Urls ======================

    path(
        "manager/charges/fix-area/",
        ManagerFixAreaChargeAPIView.as_view(),
        name="manager-fix-area-charge-list-create",
    ),

    path(
        "manager/charges/fix-area/<int:pk>/",
        ManagerFixAreaChargeAPIView.as_view(),
        name="manager-fix-area-charge-detail",
    ),

    path(
        "manager/charges/fix-area/<int:pk>/units/",
        ManagerFixAreaChargeUnitsAPIView.as_view(),
        name="manager-fix-area-charge-units",
    ),
    path(
        "manager/charges/fix-area/<int:pk>/units/send/",
        ManagerFixAreaChargeSendAPIView.as_view(),
        name="manager-fix-area-charge-send",
    ),

    path(
        "manager/charges/fix-area/<int:pk>/units/cancel/",
        ManagerFixAreaChargeCancelAPIView.as_view(),
        name="manager-fix-area-charge-cancel",
    ),
    # ============= Fix Person Charge Urls ======================
    path(
        "manager/charges/fix-person/",
        ManagerFixPersonChargeAPIView.as_view(),
        name="manager-fix-person-charge-list",
    ),
    path(
        "manager/charges/fix-person/<int:pk>/",
        ManagerFixPersonChargeAPIView.as_view(),
        name="manager-fix-person-charge-detail",
    ),
    path(
        "manager/charges/fix-person/<int:pk>/units/",
        ManagerFixPersonChargeUnitsAPIView.as_view(),
        name="manager-fix-person-charge-units",
    ),
    path(
        "manager/charges/fix-person/<int:pk>/units/send/",
        ManagerFixPersonChargeSendAPIView.as_view(),
        name="manager-fix-person-charge-send",
    ),
    path(
        "manager/charges/fix-person/<int:pk>/units/cancel/",
        ManagerFixPersonChargeCancelAPIView.as_view(),
        name="manager-fix-person-charge-cancel",
    ),


    path(
        "manager/person-area-charges/",
        ManagerPersonAreaChargeAPIView.as_view(),
        name="manager-person-area-charges",
    ),
    path(
        "manager/person-area-charges/<int:pk>/",
        ManagerPersonAreaChargeAPIView.as_view(),
        name="manager-person-area-charge-detail",
    ),
    path(
        "manager/person-area-charges/<int:pk>/units/",
        ManagerPersonAreaChargeUnitsAPIView.as_view(),
        name="manager-person-area-charge-units",
    ),
    path(
        "manager/person-area-charges/<int:pk>/send/",
        ManagerPersonAreaChargeSendAPIView.as_view(),
        name="manager-person-area-charge-send",
    ),
    path(
        "manager/person-area-charges/<int:pk>/cancel/",
        ManagerPersonAreaChargeCancelAPIView.as_view(),
        name="manager-person-area-charge-cancel",
    ),

    path(
        "manager/fix-person-area-charges/",
        ManagerFixPersonAreaChargeAPIView.as_view(),
        name="manager-fix-person-area-charges",
    ),
    path(
        "manager/fix-person-area-charges/<int:pk>/",
        ManagerFixPersonAreaChargeAPIView.as_view(),
        name="manager-fix-person-area-charge-detail",
    ),
    path(
        "manager/fix-person-area-charges/<int:pk>/units/",
        ManagerFixPersonAreaChargeUnitsAPIView.as_view(),
        name="manager-fix-person-area-charge-units",
    ),
    path(
        "manager/fix-person-area-charges/<int:pk>/send/",
        ManagerFixPersonAreaChargeSendAPIView.as_view(),
        name="manager-fix-person-area-charge-send",
    ),
    path(
        "manager/fix-person-area-charges/<int:pk>/cancel/",
        ManagerFixPersonAreaChargeCancelAPIView.as_view(),
        name="manager-fix-person-area-charge-cancel",
    ),

    path(
        "manager/fix-variable-charges/",
        ManagerFixVariableChargeAPIView.as_view(),
        name="manager-fix-variable-charge-list",
    ),
    path(
        "manager/fix-variable-charges/<int:pk>/",
        ManagerFixVariableChargeAPIView.as_view(),
        name="manager-fix-variable-charge-detail",
    ),
    path(
        "manager/fix-variable-charges/<int:pk>/units/",
        ManagerFixVariableChargeUnitsAPIView.as_view(),
        name="manager-fix-variable-charge-units",
    ),
    path(
        "manager/fix-variable-charges/<int:pk>/send/",
        ManagerFixVariableChargeSendAPIView.as_view(),
        name="manager-fix-variable-charge-send",
    ),
    path(
        "manager/fix-variable-charges/<int:pk>/cancel/",
        ManagerFixVariableChargeCancelAPIView.as_view(),
        name="manager-fix-variable-charge-cancel",
    ),

    path(
        "manager/charge-calculations/",
        ManagerChargeCalculationAPIView.as_view(),
        name="manager-charge-calculation-list",
    ),
    path(
        "manager/charge-calculations/<int:pk>/",
        ManagerChargeCalculationAPIView.as_view(),
        name="manager-charge-calculation-detail",
    ),
    path(
        "manager/charge-calculations/<int:pk>/items/",
        ManagerChargeCalculationItemsAPIView.as_view(),
        name="manager-charge-calculation-items",
    ),
    path(
        "manager/charge-calculations/<int:pk>/units/",
        ManagerChargeCalculationUnitsAPIView.as_view(),
        name="manager-charge-calculation-units",
    ),
    path(
        "manager/charge-calculations/<int:pk>/send/",
        ManagerChargeCalculationSendAPIView.as_view(),
        name="manager-charge-calculation-send",
    ),
    path(
        "manager/charge-calculations/<int:pk>/cancel/",
        ManagerChargeCalculationCancelAPIView.as_view(),
        name="manager-charge-calculation-cancel",
    ),



]
