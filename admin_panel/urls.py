from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from admin_panel import views

urlpatterns = [
    path('', views.admin_dashboard, name='admin_dashboard'),
    path('login-admin/', views.admin_login_view, name='login_admin'),
    path('log-out-admin/', views.logout_admin, name='logout_admin'),
    path('user-management/', views.UserManagementListView.as_view(), name='user_management'),
    path("impersonate/<int:user_id>/", views.impersonate_user, name="impersonate"),
    path("stop-impersonation/", views.stop_impersonation, name="stop_impersonation"),

    path(
        'manage/app-versions/create/',
        views.app_version_create,
        name='app_version_create'
    ),

    path(
        'manage/app-versions/<int:pk>/edit/',
        views.app_version_update,
        name='app-version-update'
    ),

    path(
        'manage/app-versions/<int:pk>/delete/',
        views.app_version_delete,
        name='app-version-delete'
    ),


    path('add-articles/', views.ArticleCreateView.as_view(), name='add_articles'),
    path('manage-articles/', views.manage_articles, name='manage_articles'),
    path('edit-article/<int:pk>/', views.ArticleUpdateView.as_view(), name='edit_article'),
    path('delete-article/<int:pk>/', views.article_delete, name='delete_article'),

    path('register-coupon', views.CouponListView.as_view(), name='register_coupon'),
    path('edit/coupon/<int:pk>', views.CouponEditView.as_view(), name='edit_coupon'),
    path('delete/coupon/<int:pk>', views.delete_coupon, name='delete_coupon'),

    path('admin/finance/by/house/', views.AdminFinanceByHouse.as_view(), name='admin_finance_by_house'),
    path('admin-finance/<int:house_id>/', views.AdminFinanceList.as_view(), name='admin_finance_list'),

    # middle admin urls

    path('create-house/', views.CreateHouseAndManagerView.as_view(), name='create_house'),
    path('house-list/', views.HouseListView.as_view(), name='house_list'),
    path(
        'house/update/<int:pk>/',
        views.UpdateHouseAndManagerView.as_view(),
        name='update_house'
    ),
    path(
        'house/delete/<int:pk>/',
        views.DeleteHouseView.as_view(),
        name='delete_house'
    ),

    path('house/<int:house_id>/license/add/', views.add_house_license, name='add_house_license'),
    path(
        'house-license/update/<int:pk>/',
        views.update_house_license,
        name='update_house_license'
    ),
    path(
        'house-license/delete/<int:pk>/',
        views.delete_house_license,
        name='delete_house_license'
    ),
    path(
        'house/<int:house_id>/gateway/',
        views.add_house_gateway,
        name='add_house_gateway'
    ),

    path(
        'house-gateway/update/<int:pk>/',
        views.update_house_gateway,
        name='update_house_gateway'
    ),
    path(
        'house-gateway/delete/<int:pk>/',
        views.delete_house_gateway,
        name='delete_house_gateway'
    ),
    path('middle-admin-list/', views.MiddleAdminListView.as_view(), name='middle_admin_list'),
    # path('middle/edit/<int:pk>/', views.MiddleAdminUpdateView.as_view(), name='edit_middle_admin'),
    # path('middle/delete/<int:pk>/', views.middleAdmin_delete, name='delete_middle_admin'),

    path('conatct/management/', views.ContactUsManagement.as_view(), name='contact_management'),
    path('comment/approved/<str:comment_code>/', views.approved_comment, name='comment_approved'),
    path('comment/disapproved/<str:comment_code>/', views.disapproved_comment,
         name='comment_disapproved'),

    path('consultant/management/', views.FreeRequestManagement.as_view(), name='consultant_management'),
    path('consultant/approved/<str:cons_code>/', views.approved_request_management, name='consultant_approved'),
    path('consultant/disapproved/<str:cons_code>/', views.disapproved_request_management,
         name='consultant_disapproved'),

    # Slider urls

    path('create-slider-text/', views.SliderTextCreateView.as_view(), name='create_slider_text'),
    path('slider/text/edit/<int:pk>/', views.SliderTextUpdateView.as_view(), name='edit_slider_text'),
    path('slider/text/delete/<int:pk>/', views.delete_slider_text, name='delete_slider_text'),

    # Announce urls
    path('announcement/', views.AnnouncementView.as_view(), name='announcement'),
    path(
        "announcements/<int:house_id>/",
        views.ManagerAnnouncementsDetailView.as_view(),
        name="house_announcements"
    ),
    path('admin-announcement-delete/<int:pk>/', views.announcement_delete, name='admin_delete_announcement'),

    # House Urls
    # path('manage-house', views.AddMyHouseView.as_view(), name='manage_house'),
    path(
        "banks/<int:house_id>/",
        views.HouseBanksDetailView.as_view(),
        name="house_banks"
    ),
    # path('house/edit/<int:pk>/', views.MyHouseUpdateView.as_view(), name='edit_house'),
    # path('delete/house/<int:pk>/', views.house_delete, name='delete_house'),

    # Bank Urls
    path('manage-bank', views.AddBankView.as_view(), name='manage_bank'),
    # path('bank/edit/<int:pk>/', views.BankUpdateView.as_view(), name='edit_bank'),
    # path('delete/bank/<int:pk>/', views.bank_delete, name='delete_bank'),

    # Unit Urls
    path('add-unit', views.UnitRegisterView.as_view(), name='manage_unit'),
    path('houses/<int:house_id>/units/', views.UnitHouseDetailView.as_view(), name='unit_house_detail'),
    path('info-unit/<int:pk>/', views.UnitInfoView.as_view(), name='unit_info'),
    # path('edit/unit/<int:pk>/', views.UnitUpdateView.as_view(), name='edit_unit'),
    # path('delete/unit/<int:pk>/', views.unit_delete, name='delete_unit'),
    # path('unit-list', views.UnitListView.as_view(), name='unit_list'),
    path('houses/<int:house_id>/units/export/', views.export_units_excel, name='export_units_excel'),

    path('units/export/pdf/<int:house_id>', views.export_units_pdf, name='export_units_pdf'),

    # Expense_category Urls
    path('add-category-expense', views.ExpenseCategoryView.as_view(), name='add_category_expense'),
    path('edit/category/expense/<int:pk>/', views.ExpenseCategoryUpdate.as_view(), name='edit_category_expense'),
    path('delete/category/expense/<int:pk>/', views.expense_category_delete, name='delete_category_expense'),

    # Expense Urls
    path('add-expense', views.ExpenseView.as_view(), name='add_expense'),
    path('expense/edit/<int:pk>/', views.expense_edit, name='expense_edit'),
    path('expense/delete/<int:pk>/', views.expense_delete, name='expense_delete'),
    path('expense/delete-document/', views.delete_expense_document, name='delete_expense_document'),
    path('expense/export/excel/', views.export_units_excel, name='export_expense_excel'),
    path('expense/export/pdf/', views.export_expense_pdf, name='export_expense_pdf'),

    # Income_category Urls
    path('add-category_income', views.IncomeCategoryView.as_view(), name='add_category_income'),
    path('edit/category/income/<int:pk>/', views.IncomeCategoryUpdate.as_view(), name='edit_category_income'),
    path('delete/category/income/<int:pk>/', views.income_category_delete, name='delete_category_income'),

    # Income Urls
    path('add-income', views.IncomeView.as_view(), name='add_income'),
    path('income/edit/<int:pk>/', views.income_edit, name='income_edit'),
    path('income/delete/<int:pk>/', views.income_delete, name='income_delete'),
    path('income/delete-document/', views.delete_income_document, name='delete_income_document'),
    path('income/export/excel/', views.export_income_excel, name='export_income_excel'),
    path('income/export/pdf/', views.export_income_pdf, name='export_income_pdf'),

    # ReceiveMoney Urls
    path('add-receive', views.ReceiveMoneyCreateView.as_view(), name='add_receive'),
    path('receive/edit/<int:pk>/', views.receive_edit, name='receive_edit'),
    path('receive/delete/<int:pk>/', views.receive_delete, name='receive_delete'),
    path('receive/delete-document/', views.delete_receive_document, name='delete_delete_document'),
    path('receive/export/excel/', views.export_receive_excel, name='export_receive_excel'),
    path('receive/export/pdf/', views.export_receive_pdf, name='export_receive_pdf'),

    # PayMoney Urls
    path('add-pay', views.PaymentMoneyCreateView.as_view(), name='add_pay'),
    path('pay/edit/<int:pk>/', views.pay_edit, name='pay_edit'),
    path('pay/delete/<int:pk>/', views.pay_delete, name='pay_delete'),
    path('pay/delete-document/', views.delete_pay_document, name='delete_pay_document'),
    path('pay/export/excel/', views.export_pay_excel, name='export_pay_excel'),
    path('pay/export/pdf/', views.export_pay_pdf, name='export_pay_pdf'),

    # Property Urls
    path('add-productProperty', views.PropertyCreateView.as_view(), name='add_property'),
    path('productProperty/edit/<int:pk>/', views.property_edit, name='property_edit'),
    path('productProperty/delete/<int:pk>/', views.property_delete, name='property_delete'),
    path('productProperty/delete-document/', views.delete_property_document, name='delete_property_document'),
    path('productProperty/export/excel/', views.export_property_excel, name='export_property_excel'),
    path('productProperty/export/pdf/', views.export_property_pdf, name='export_property_pdf'),

    # Maintenance Urls
    path('add-maintenance', views.MaintenanceCreateView.as_view(), name='add_maintenance'),
    path('maintenance/edit/<int:pk>/', views.maintenance_edit, name='maintenance_edit'),
    path('maintenance/delete/<int:pk>/', views.maintenance_delete, name='maintenance_delete'),
    path('maintenance/delete-document/', views.delete_maintenance_document, name='delete_maintenance_document'),
    path('maintenance/export/excel/', views.export_maintenance_excel, name='export_maintenance_excel'),
    path('maintenance/export/pdf/', views.export_maintenance_pdf, name='export_maintenance_pdf'),

    # Charge Urls
    path('add-charge-category', views.ChargeCategoryCreateView.as_view(), name='add_charge_category'),
    path('edit/chrage/category/<int:pk>/', views.ChargeCategoryUpdateView.as_view(), name='edit_charge_category'),
    path('charge-category-delete/<int:pk>/', views.charge_category_delete, name='delete_charge_category'),
    path('charges-method', views.charge_view, name='charges_method'),

    path('add-fixed-Charge', views.FixChargeCreateView.as_view(), name='add_fixed_charge'),

    path('add-area-charge', views.AreaChargeCreateView.as_view(), name='add_area_charge'),

    path('add-person-charge', views.PersonChargeCreateView.as_view(), name='add_person_charge'),

    path('add-fix_person-charge', views.FixPersonChargeCreateView.as_view(), name='add_fix_person_charge'),

    path('add-fix_area-charge', views.FixAreaChargeCreateView.as_view(), name='add_fix_area_charge'),

    path('add-person_area-charge', views.PersonAreaChargeCreateView.as_view(), name='add_person_area_charge'),

    path('add-person_area-fix-charge', views.PersonAreaFixChargeCreateView.as_view(),
         name='add_person_area_fix_charge'),

    path('add-variable-fix-charge', views.VariableFixChargeCreateView.as_view(), name='add_variable_fix_charge'),

    # Sms_Management

    path('admin/register/sms/', views.AdminSmsManagementView.as_view(), name='admin_register_sms'),
    path('admin/edit/sms/<int:pk>/', views.AdminSmsUpdateView.as_view(), name='admin_edit_sms'),
    path('admin-sms-delete/<int:pk>/', views.admin_sms_delete, name='admin_delete_sms'),
    path('admin/sms/send/form/<int:pk>/', views.admin_show_send_sms_form, name='admin_show_send_sms_form'),
    path('admin-send-sms/<int:pk>/', views.admin_send_sms, name='admin_send_sms'),
    path('admin/sms/management/', views.AdminSmsListView.as_view(), name='admin_sms_management'),
    path('admin/sms/approved/', views.ApprovedSms.as_view(), name='admin_sms_approved'),
    path(
        "sms/<int:house_id>/", views.ApprovedSmsDetailView.as_view(), name="sms_approved_list"),

    path('admin-approved-sms/<int:pk>/', views.approve_sms, name='admin_approved_sms'),
    path('admin-disapproved-sms/<int:pk>/', views.disapprove_sms, name='admin_disapproved_sms'),
    path('admin/sms/credit/', views.CreditSmsManagement.as_view(), name='admin_sms_credit'),
    path(
        "credit/sms/<int:house_id>/", views.CreditSmsDetailView.as_view(), name="sms_credit_list"),

    path('middle/sms/report/', views.middleSmsManagementReport.as_view(), name='middle_sms_report'),
    path(
        "middle/report/sms/<int:house_id>/", views.middleReportSmsDetailView.as_view(), name="middle_sms_report_list"),

    path('admin/ticket/report/', views.AdminTicketReport.as_view(), name='admin_ticket_report'),
    path(
        "admin/report/ticket/<int:house_id>/", views.AdminTicketDetailView.as_view(), name="admin_ticket_report_list"),

    # Fund Report

    path('admin/fund/report/', views.AdminFundReport.as_view(), name='admin_fund_report'),
    path(
        "admin/report/fund/<int:house_id>/", views.AdminFundReportDetailView.as_view(), name="admin_fund_report_list"),

    # Charge Report

    path('charge/issued/', views.ChargeIssued.as_view(), name='charge_issued'),
    path(
        "charges/<int:house_id>/", views.ChargeIssuedDetailView.as_view(), name="charges_issued_detail"),

    # Bank Fund Report

    path('admin/banks/report/', views.AdminBanksReport.as_view(), name='admin_bank_report'),
    path(
        "admin/report/bank/list/<int:house_id>/", views.AdminBanksListReportView.as_view(),
        name="admin_bank_report_list"),

    path('admin/banks/details<int:bank_id>/', views.admin_bank_detail_view, name='admin_bank_detail'),

    # Unit Fund Report

    path('admin/unit/fund/report/', views.AdminUnitFundReport.as_view(), name='admin_unit_fund_report'),
    path(
        "admin/report/unit/list/<int:house_id>/", views.AdminUnitsListReportView.as_view(),
        name="admin_unit_fund_report_list"),
    path('admin/unit/fund/details/<int:unit_id>/', views.admin_Unit_Fund_detail, name='admin_unit_fund_detail'),

    # Debtor Report

    path('admin/debtor/report/', views.AdminDebtorReport.as_view(), name='admin_debtor_report'),
    path('admin/unit/debtor/<int:pk>/', views.AdminDebtorUnitDetailView.as_view(), name='admin_debtor_detail'),

    # Unit History Report

    path('admin/unit/history/report/', views.AdminUnitHistoryReport.as_view(), name='admin_unit_history_report'),
    path(
        "admin/history/unit/list/<int:house_id>/", views.AdminUnitsHistoryListView.as_view(),
        name="admin_unit_history_list"),
    path('admin/unit/history/details/<int:unit_id>/', views.admin_Unit_history_detail,
         name='admin_unit_history_detail'),

    # Expense Report

    path('admin/expense/report/', views.AdminExpenseReport.as_view(), name='admin_expense_report'),
    path(
        "admin/report/expenses/<int:house_id>/", views.AdminExpensesDetailView.as_view(),
        name="admin_expense_report_list"),

    # Income Report

    path('admin/income/report/', views.AdminIncomeReport.as_view(), name='admin_income_report'),
    path(
        "admin/report/incomes/<int:house_id>/", views.AdminIncomesDetailView.as_view(),
        name="admin_income_report_list"),

    # Receive Report

    path('admin/receive/report/', views.AdminReceiveReport.as_view(), name='admin_receive_report'),
    path(
        "admin/report/receives/<int:house_id>/", views.AdminReceiveDetailView.as_view(),
        name="admin_receive_report_list"),

    # Pay Report

    path('admin/pay/report/', views.AdminPayReport.as_view(), name='admin_pay_report'),
    path(
        "admin/report/payments/<int:house_id>/", views.AdminPayDetailView.as_view(),
        name="admin_pay_report_list"),

    # Property Report

    path('admin/property/report/', views.AdminPropertyReport.as_view(), name='admin_property_report'),
    path(
        "admin/report/property/<int:house_id>/", views.AdminPropertyDetailView.as_view(),
        name="admin_property_report_list"),

    # Maintenance Report

    path('admin/maintenance/report/', views.AdminMaintenanceReport.as_view(), name='admin_maintenance_report'),
    path(
        "admin/report/maintenance/<int:house_id>/", views.AdminMaintenanceDetailView.as_view(),
        name="admin_maintenance_report_list"),

    # Billan Report
    path('admin/billan/report/', views.AdminBillanReport.as_view(), name='admin_house_balance_report'),
    path(
        'admin/billan/<int:house_id>/',
        views.admin_house_balance,
        name='admin_house_balance_detail'
    ),

    # مسیر دریافت نوت‌ها
    path('calendar/notes/<int:year>/<int:month>/', views.get_notes, name='get_notes'),
    path('calendar/save-note/', views.save_note, name='save_note'),
    path('calendar/delete-note/', views.delete_note, name='delete_note'),

    #  Subscription
    path('subscription/plan/', views.AddSubscriptionPlan.as_view(), name='subscription_plan'),
    path('subscription/plan/edit/<int:pk>/"', views.SubscriptionPlanUpdate.as_view(), name='subscription_plan_edit'),
    path('subscription/plan/delete/<int:pk>/"', views.subscription_plan_delete, name='subscription_plan_delete'),

    path('subscription/', views.SubscriptionListView.as_view(), name='subscription_list'),
    # path('subscription-change/<int:subscription_id>/', views.admin_cancel_subscription, name='subscription_change'),
    path('subscriptions/edit/<int:subscription_id>/', views.admin_edit_subscription, name='admin_edit_subscription'),
    # path('subscriptions/create/<int:user_id>/', views.admin_create_subscription, name='admin_create_subscription'),

    path('admin/comment/management/', views.CommentListView.as_view(), name='admin_comment_management'),
    path('admin/comment/approved/<int:pk>/', views.approved_comment, name='admin_comment_approved'),
    path('admin/comment/disapproved/<int:pk>/', views.disapproved_comment, name='admin_comment_disapproved'),


]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
