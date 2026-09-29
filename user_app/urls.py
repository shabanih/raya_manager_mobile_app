from django.urls import path

from user_app import views

urlpatterns = [
    # path('', views.index, name='index'),
    path('user_dashboard/', views.user_panel, name='user_panel'),
    path('switch-to-manager/', views.switch_to_manager, name='switch_to_manager'),
    path('mobile-login/', views.mobile_login, name='mobile_login'),
    path('logout_user/', views.logout_user, name='logout_user'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),

    path('charge/pdf/<int:pk>/', views.export_charge_pdf, name='export_charge_pdf'),
    path('user-charges/', views.fetch_user_charges, name='user_charges'),
    path('user-announce/', views.AnnouncementListView.as_view(), name='user_announce_manage'),
    path('user/messages/', views.MessageListView.as_view(), name='user_message'),

    path('user-pay/', views.UserPayMoneyViewCreateView.as_view(), name='user_pay_money'),
    path('pay/user/edit/<int:pk>/', views.pay_user_edit, name='user_pay_money_edit'),
    path('pay/user/delete/<int:pk>/', views.user_pay_delete, name='user_pay_delete'),
    path('user/pay/delete-document/', views.user_delete_pay_document, name='user_delete_pay_document'),
    path('user-pay-pdf/', views.export_user_pay_money_pdf, name='user_pay_money_pdf'),
    path('user-pay-excel/', views.export_user_pay_money_excel, name='user_pay_money_excel'),

    path('user-civil-charges/', views.unit_civil_charge_list, name='user_civil_charge_list'),
    path('user-civil-installments/<int:civil_id>/unit/<int:unit_id>/', views.unit_installments_civil_list,
         name='user_civil_installments_list'),
    path('user-civil-charge-pdf/', views.export_charge_civil_pdf, name='user_civil_charge_pdf'),
    path('user-civil-installments-pdf/<int:civil_id>/unit/<int:unit_id>/', views.export_installments_civil_pdf,
         name='user_civil_installments_pdf'),

    path('user-sewage/', views.unit_sewage_list, name='user_sewage_list'),
    path('user-sewage-installments/<int:sewage_id>/unit/<int:unit_id>/', views.unit_installments_sewage_list,
         name='user_sewage_installments_list'),
    path('user-sewage-pdf/', views.export_sewage_pdf, name='user_sewage_pdf'),
    path('user-sewage-installments-pdf/<int:sewage_id>/unit/<int:unit_id>/', views.export_installments_sewage_pdf,
         name='user_sewage_installments_pdf'),

    path('profile/', views.user_profile, name='user_profile'),
    path('poll/', views.unit_polls, name='unit_poll'),
    path('poll/<int:poll_id>/', views.resident_poll_vote, name='resident_poll_vote'),

]
