from django.conf import settings
from django.conf.urls.static import static
from django.urls import path

from middleAdmin_panel import views

urlpatterns = [
    path('middle-dashboard', views.middle_admin_dashboard, name='middle_admin_dashboard'),
    path('login-middleAdmin/', views.middle_admin_login_view, name='login_middle_admin'),
    path('log-out/', views.logout__middle_admin, name='logout_middle_admin'),
    path('switch-to-resident/', views.switch_to_resident, name='switch_to_resident'),

    path('buy-subscription/', views.buy_subscription, name='buy_subscription'),
    path("ajax/check-coupon/", views.check_coupon, name="check_coupon"),

    path('middle/profile/', views.middle_profile, name='middle_profile'),

    path('middle-send-announcement/', views.MiddleAnnouncementView.as_view(), name='middle_send_announcement'),
    path('middle-announcement/', views.MiddleAnnouncementListView.as_view(), name='middle_announcement'),
    path('edit/middle/announcement/<int:pk>/', views.MiddleAnnouncementUpdateView.as_view(),
         name='edit_middle_announcement'),
    path('announcement-middle-delete/<int:pk>/', views.middle_announcement_delete, name='delete_middle_announcement'),

    # House Urls

    # path('middle-house/', views.MiddleAddMyHouseView.as_view(), name='middle_manage_house'),
    # path('middle/house/edit/<int:pk>/', views.MiddleMyHouseUpdateView.as_view(), name='middle_edit_house'),
    # path('middle/delete/house/<int:pk>/', views.middle_house_delete, name='middle_delete_house'),

    # Bank Urls
    path('middle-manage-bank', views.middleAddBankView.as_view(), name='middle_manage_bank'),
    path('middle/bank/edit/<int:pk>/', views.middleBankUpdateView.as_view(), name='middle_edit_bank'),
    path('middle/delete/bank/<int:pk>/', views.middle_bank_delete, name='middle_delete_bank'),

    path('middle-transfer-bank', views.TransferMoneyView.as_view(), name='middle_transfer_bank'),
    path('middle-transfer-bank_list', views.transfer_list_view, name='middle_transfer_bank_list'),
    path('middle--delete-transfer-bank/<int:pk>/', views.delete_transfer, name='middle_delete_transfer_bank'),

    # Unit Urls
    path('middle-add-unit', views.MiddleUnitRegisterView.as_view(), name='middle_unit_register'),
    path('middle-info-unit/<int:pk>/', views.MiddleUnitInfoView.as_view(), name='middle_unit_info'),
    path('unit//add-renter/<int:unit_id>/', views.add_renter_to_unit, name='add_renter_to_unit'),

    path('edit/middle/unit/<int:pk>/', views.MiddleUnitUpdateView.as_view(), name='middle_edit_unit'),
    path('delete/middle/unit/<int:pk>/', views.middle_unit_delete, name='middle_delete_unit'),
    path('middle-manage-unit', views.MiddleUnitListView.as_view(), name='middle_manage_unit'),
    path('units/export/excel/', views.export_units_excel, name='export_units_excel'),
    path('units/export/pdf/', views.export_units_pdf, name='export_units_pdf'),

    # Expense_category Urls
    path('middle_add-category-expense', views.MiddleExpenseCategoryView.as_view(),
         name='middle_register_category_expense'),
    path('edit/middle/category/expense/<int:pk>/', views.MiddleExpenseCategoryUpdate.as_view(),
         name='middle_edit_category_expense'),
    path('delete/middle/category/expense/<int:pk>/', views.middle_expense_category_delete,
         name='middle_delete_category_expense'),

    # Expense Urls
    path('middle-add-expense', views.MiddleExpenseView.as_view(), name='middle_register_expense'),
    path('expense/pay/<int:expense_id>/', views.expense_pay_view, name='expense_pay'),
    path(
        'expense/cancel-pay/<int:expense_id>/',
        views.expense_cancel_pay_view,
        name='expense_cancel_pay'
    ),

    path('expense/middle/edit/<int:pk>/', views.middle_expense_edit, name='middle_expense_edit'),
    path('expense/middle/delete/<int:pk>/', views.middle_expense_delete, name='middle_expense_delete'),
    path('expense/middle/delete-document/', views.middle_delete_expense_document,
         name='middle_delete_expense_document'),
    path('middle/expense/export/excel/', views.middle_export_expense_excel, name='middle_export_expense_excel'),
    path('middle/expense/export/pdf/', views.middle_export_expense_pdf, name='middle_export_expense_pdf'),

    # Income_category Urls
    path('middle-add-category_income', views.MiddleIncomeCategoryView.as_view(),
         name='middle_register_category_income'),
    path('edit/category/middle/income/<int:pk>/', views.MiddleIncomeCategoryUpdate.as_view(),
         name='middle_edit_category_income'),
    path('delete/category/middle/income/<int:pk>/', views.middle_income_category_delete,
         name='middle_delete_category_income'),

    # Income Urls
    path('middle-add-income', views.MiddleIncomeView.as_view(), name='middle_register_income'),
    path('income/pay/<int:income_id>/', views.income_pay_view, name='income_pay'),
    path(
        'income/cancel-pay/<int:income_id>/',
        views.income_cancel_pay_view,
        name='income_cancel_pay'
    ),
    path('income/middle/edit/<int:pk>/', views.middle_income_edit, name='middle_income_edit'),
    path('income/middle/delete/<int:pk>/', views.middle_income_delete, name='middle_income_delete'),
    path('income/middle/delete-document/', views.middle_delete_income_document, name='middle_delete_income_document'),
    path('income/export/excel/', views.export_income_excel, name='export_income_excel'),
    path('income/export/pdf/', views.export_income_pdf, name='export_income_pdf'),

    # ReceiveMoney Urls
    path('middle-add-receive', views.MiddleReceiveMoneyCreateView.as_view(), name='middle_register_receive'),

    # path('receive/<int:pk>/delete_fund/', views.delete_fund_record, name='delete_fund_record'),
    path('receive/middle/edit/<int:pk>/', views.middle_receive_edit, name='middle_receive_edit'),
    path('receive/pay/<int:receive_id>/', views.receive_pay_view, name='receive_pay'),
    path(
        'receive/cancel-pay/<int:receive_id>/',
        views.receive_cancel_pay_view,
        name='receive_cancel_pay'
    ),
    path('receive/middle/delete/<int:pk>/', views.middle_receive_delete, name='middle_receive_delete'),
    path('receive/middle/delete-document/', views.middle_delete_receive_document, name='middle_delete_delete_document'),
    path('receive/export/excel/', views.export_receive_excel, name='export_receive_excel'),
    path('receive/export/pdf/', views.export_receive_pdf, name='export_receive_pdf'),

    # PayMoney Urls
    path('middle-add-pay', views.MiddlePaymentMoneyCreateView.as_view(), name='middle_register_pay'),
    # path('pay/<int:pk>/delete_fund/', views.delete_pay_fund_record, name='delete_pay_fund_record'),
    path('pay/middle/edit/<int:pk>/', views.middle_pay_edit, name='middle_pay_edit'),
    path('payment/pay/<int:payment_id>/', views.payment_pay_money_view, name='payment_pay_money'),
    path(
        'payment/cancel-pay/<int:payment_id>/',
        views.payment_cancel_pay_money_view,
        name='payment_cancel_pay_money'
    ),
    path('pay/middle/delete/<int:pk>/', views.middle_pay_delete, name='middle_pay_delete'),
    path('pay/middle/delete-document/', views.middle_delete_pay_document, name='middle_delete_pay_document'),
    path('pay/export/excel/', views.export_pay_excel, name='export_pay_excel'),
    path('pay/export/pdf/', views.export_pay_pdf, name='export_pay_pdf'),

    # Property Urls
    path('middle-add-Property', views.MiddlePropertyCreateView.as_view(), name='middle_register_property'),
    path('Property/middle/edit/<int:pk>/', views.middle_property_edit, name='middle_property_edit'),
    path('property/pay/<int:property_id>/', views.property_pay_money_view, name='property_pay_money'),
    path(
        'property/cancel-pay/<int:property_id>/',
        views.property_cancel_pay_money_view,
        name='property_cancel_pay_money'
    ),
    path('Property/middle/delete/<int:pk>/', views.middle_property_delete, name='middle_property_delete'),
    path('middleProperty/delete-document/', views.middle_delete_property_document,
         name='middle_delete_property_document'),
    # path('Property/export/excel/', views.export_property_excel, name='export_property_excel'),
    # path('Property/export/pdf/', views.export_property_pdf, name='export_property_pdf'),
    # path('property/<int:pk>/delete_fund/', views.delete_property_fund_record,
    #      name='delete_property_fund_record'),

    # Maintenance Urls
    path('middle-add-maintenance', views.MiddleMaintenanceCreateView.as_view(), name='middle_register_maintenance'),
    path('maintenance/middle/edit/<int:pk>/', views.middle_maintenance_edit, name='middle_maintenance_edit'),
    path('maintenance/middle/delete/<int:pk>/', views.middle_maintenance_delete, name='middle_maintenance_delete'),
    path('maintenance/middle/delete-document/', views.middle_delete_maintenance_document,
         name='middle_delete_maintenance_document'),

    path('maintenance/pay/<int:maintenance_id>/', views.maintenance_pay_money_view, name='maintenance_pay_money'),
    path(
        'maintenance/cancel-pay/<int:maintenance_id>/',views.maintenance_cancel_pay_money_view,
        name='maintenance_cancel_pay_money'),
    # path('maintenance/export/excel/', views.export_maintenance_excel, name='export_maintenance_excel'),
    # path('maintenance/export/pdf/', views.export_maintenance_pdf, name='export_maintenance_pdf'),
    # path('maintenance/<int:pk>/delete_fund/', views.delete_maintenance_fund_record,
    #      name='delete_maintenance_fund_record'),

    # sewage Urls

    path('middle-add-sewage/', views.SewageCostManage.as_view(), name='middle_register_sewage'),
    path('sewage/middle/edit/<int:pk>/', views.sewage_cost_edit, name='middle_sewage_edit'),
    path('sewage/middle/delete/<int:pk>/', views.middle_sewage_delete, name='middle_sewage_delete'),
    path('sewage/middle/delete-document/', views.middle_delete_sewage_document,
         name='middle_delete_sewage_document'),
    path('middle/sewage/send/form/<int:pk>/', views.middle_show_sewage_form, name='middle_show_send_sewage_form'),
    path('middle-send-sewage/<int:pk>/', views.middle_send_sewage, name='middle_send_sewage'),

    # Charge Urls

    path('middle-add-charge', views.middle_charge_view, name='middle_add_charge'),
    path('middle-manage-charges', views.base_charge_list, name='middle_main_charges'),
    path('middle-main-charges-pdf/', views.middle_base_charges_pdf, name='middle_main_charges_pdf'),
    path('middle_main_charges_excel/', views.middle_base_charges_excel, name='middle_main_charges_excel'),

    path('base-charges/<str:app_label>/<str:model_name>/<int:charge_id>/units/', views.charge_units_list,
         name='middle_main_charges_units_list'),
    path('middle-charge/<str:app_label>/<str:model_name>/<int:charge_id>/units/pdf/', views.charge_units_list_pdf,
         name='charge_units_list_pdf'),
    path('middle-charge/<str:app_label>/<str:model_name>/<int:charge_id>/units/excel/', views.charge_units_list_excel,
         name='charge_units_list_excel'),
    path(
        'middle-charge<int:charge_id>',
        views.charge_units_pdf,
        name='single_charge_invoice_pdf'
    ),
    path(
        'middle-charge_all/<str:app_label>/<str:model_name>/<int:charge_id>/invoices/pdf/',
        views.all_invoices_pdf,
        name='all_invoices_pdf'),

    path(
        'charges/penalty/waive/bulk/',
        views.waive_penalty_bulk,
        name='waive_penalty_bulk'
    ),
    path(
        'charges/restore-penalty/',
        views.restore_penalty_bulk,
        name='restore_penalty'
    ),

    # Civil Charge

    path('civil_charge/', views.CivilChargeManage.as_view(), name='civil_charge_manage'),
    path('civil/middle/edit/<int:pk>/', views.civil_charge_edit, name='middle_civil_edit'),
    path('civil/middle/delete/<int:pk>/', views.middle_civil_delete, name='middle_civil_delete'),
    path('civil/middle/delete-document/', views.middle_delete_civil_document,
         name='middle_delete_civil_document'),
    path('middle/civil/send/form/<int:pk>/', views.middle_show_civil_form, name='middle_show_send_civil_form'),
    path('middle-send-civil/<int:pk>/', views.middle_send_civil_charge, name='middle_send_civil_charge'),

    # Fix Charge
    path('middle-add-fixed-Charge', views.MiddleFixChargeCreateView.as_view(), name='middle_add_fixed_charge'),
    path('charge/middle/edit/<int:pk>/', views.middle_fix_charge_edit, name='middle_charge_edit'),
    path('charge/middle/delete/<int:pk>/', views.middle_fix_charge_delete, name='middle_fix_charge_delete'),
    path('fix-charge/<int:pk>/notify/', views.middle_fix_charge_notification_view,
         name='middle_add_fix_charge_notify'),
    path('charge/middle/notify/remove/<int:pk>/', views.middle_remove_send_notification_fix,
         name='middle_remove_send_notification_ajax'),

    # Area charge
    path('middle-add-area-charge', views.MiddleAreaChargeCreateView.as_view(), name='middle_add_area_charge'),
    path('area/middle/charge/edit/<int:pk>/', views.middle_area_charge_edit, name='middle_charge_area_edit'),
    path('area/middle/charge/delete/<int:pk>/', views.middle_area_charge_delete, name='middle_charge-area_delete'),
    path('charge/middle/area/notify/<int:pk>/', views.middle_area_charge_notification_view,
         name='middle_add_show_notification_area_charge_form'),
    path('middle-remove-send-notification-area/<int:pk>/', views.middle_remove_send_notification_area,
         name='middle_remove_send_notification_area'),

    # Person charge
    path('middle_add-person-charge', views.MiddlePersonChargeCreateView.as_view(), name='middle_add_person_charge'),
    path('person/middle/charge/edit/<int:pk>/', views.middle_person_charge_edit, name='middle_charge_person_edit'),
    path('person/middle/charge/delete/<int:pk>/', views.middle_person_charge_delete,
         name='middle_charge-person_delete'),
    path('charge/middle/person/notify/<int:pk>/', views.middle_person_charge_notification_view,
         name='middle_add_show_notification_person_charge_form'),
    path('middle-remove-send-notification-person/<int:pk>/', views.middle_remove_send_notification_person,
         name='middle_remove_send_notification_person'),

    # Fix Area Charge
    path('middle_add-fix_area-charge', views.MiddleFixAreaChargeCreateView.as_view(),
         name='middle_add_fix_area_charge'),
    path('fix/area/middle/charge/edit/<int:pk>/', views.middle_fix_area_charge_edit,
         name='middle_charge_fix_area_edit'),
    path('fix/area/middle/charge/delete/<int:pk>/', views.middle_fix_area_charge_delete,
         name='middle_charge-fix_area_delete'),
    path('fix/area/middle/charge/notify/<int:pk>/', views.middle_show_fix_area_charge_notification_form,
         name='middle_add_show_notification_fix_area_charge_form'),
    path('middle-remove-send-notification-fix-area/<int:pk>/', views.middle_remove_send_notification_fix_area,
         name='middle_remove_send_notification_fix_area'),

    # Fix Person charge
    path('middle-add-fix_person-charge', views.MiddleFixPersonChargeCreateView.as_view(),
         name='middle_add_fix_person_charge'),
    path('fix/person/middle/charge/edit/<int:pk>/', views.middle_fix_person_charge_edit,
         name='middle_charge_fix_person_edit'),
    path('fix/person/middle/charge/delete/<int:pk>/', views.middle_fix_person_charge_delete,
         name='middle_charge_fix_person_delete'),
    path('charge/middle/fix/person/notify/<int:pk>/', views.middle_show_fix_person_charge_notification_form,
         name='middle_add_show_notification_fix_person_charge_form'),
    path('middle-remove-send-notification-fix-person/<int:pk>/', views.middle_remove_send_notification_fix_person,
         name='middle_remove_send_notification_fix_person'),

    # Person Area Charge
    path('middle-add-person_area-charge', views.MiddlePersonAreaChargeCreateView.as_view(),
         name='middle_add_person_area_charge'),
    path('area/person/middle/charge/edit/<int:pk>/', views.middle_person_area_charge_edit,
         name='middle_charge_area_person_edit'),
    path('area/person/middle/charge/delete/<int:pk>/', views.middle_person_area_charge_delete,
         name='middle_charge_area_person_delete'),
    path('area/person/middle/notify/<int:pk>/', views.middle_show_person_area_charge_notification_form,
         name='middle_add_show_notification_person_area_charge_form'),
    path('middle-remove-send-notification-person-area/<int:pk>/', views.middle_remove_send_notification_person_area,
         name='middle_remove_send_notification_person_area'),

    # Fix Person Area
    path('middle-add-person_area-fix-charge', views.MiddlePersonAreaFixChargeCreateView.as_view(),
         name='middle_add_person_area_fix_charge'),
    path('fix/area/person/middle/charge/edit/<int:pk>/', views.middle_person_area_fix_charge_edit,
         name='middle_charge_area_person_fix_edit'),
    path('fix/area/person/charge/delete/<int:pk>/', views.middle_person_area_fix_delete,
         name='middle_charge_area_person_fix_delete'),
    path('charge/middle/fix/person/area/notify/<int:pk>/', views.middle_show_fix_person_area_charge_notification_form,
         name='middle_add_show_notification_fix_person_area_charge_form'),
    path('middle-remove-send-notification-fix-person-area/<int:pk>/',
         views.middle_remove_send_notification_fix_person_area,
         name='middle_remove_send_notification_fix_person_area'),

    # Fix variable
    path('middle-add-variable-fix-charge', views.MiddleVariableFixChargeCreateView.as_view(),
         name='middle_add_variable_fix_charge'),
    path('fix/variable/middle/charge/edit/<int:pk>/', views.middle_variable_fix_charge_edit,
         name='middle_charge_variable_fix_edit'),
    path('variable/fix/middle/charge/delete/<int:pk>/', views.middle_variable_fix_charge_delete,
         name='middle_charge_variable_fix_delete'),
    path('charge/fix/variable/middle/charge/notify/<int:pk>/', views.middle_show_fix_variable_notification_form,
         name='middle_add_show_notification_fix_variable_charge_form'),
    path('middle-remove-send-notification-fix-variable-charge/<int:pk>/',
         views.middle_remove_send_notification_fix_variable,
         name='middle_remove_send_notification_fix_variable_charge'),

    # path('middle-add-expense-charge', views.MiddleExpenseCharge.as_view(),
    #      name='middle_add_expense_charge'),

    # Sms_Management
    path('middle/sms/credit/', views.add_sms_credit, name='add_sms_credit'),

    path('middle/sms/register/', views.MiddleSmsManagementView.as_view(), name='sms_middle_sms'),
    path('middle/sms/management/', views.MiddleSmsListView.as_view(), name='middle_sms_management'),
    path('middle/edit/sms/<int:pk>/', views.MiddleSmsUpdateView.as_view(), name='sms_middle_edit'),
    path('middle-sms-delete/<int:pk>/', views.middle_sms_delete, name='middle_delete_sms'),
    path('middle/sms/send/form/<int:pk>/', views.middle_show_send_sms_form, name='sms_middle_show_send_form'),
    path('middle-send-sms/<int:pk>/', views.middle_send_sms, name='middle_send_sms'),

    path(
        'charge/<int:pk>/toggle-unit/',
        views.toggle_unit_selection,
        name='toggle_unit_selection'
    )
]
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
