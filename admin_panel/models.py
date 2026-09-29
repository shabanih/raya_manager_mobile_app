import json
import math
from collections import defaultdict
from decimal import Decimal
from django.db.models import Count, Q, F
from ckeditor_uploader.fields import RichTextUploadingField
from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey, GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models, transaction
from django.db.models import Count
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from datetime import date, timedelta

from jalali_date import date2jalali

from user_app.models import Unit, User, Bank, MyHouse
import uuid
import secrets


class Announcement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    house = models.ForeignKey(MyHouse, on_delete=models.CASCADE)
    title = RichTextUploadingField(null=True, blank=True)
    show_in_marquee = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return self.title

    def get_image_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))


class AnnouncementDocument(models.Model):
    announcement = models.ForeignKey(Announcement, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/announcement/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


class ImpersonationLog(models.Model):
    admin = models.ForeignKey(User, on_delete=models.CASCADE, related_name="impersonated_by_me")
    target_user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="impersonated_me")

    start_time = models.DateTimeField(auto_now_add=True)
    end_time = models.DateTimeField(null=True, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)

    def __str__(self):
        return f"{self.admin} → {self.target_user}"


class MessageToUser(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=400, null=True, blank=True)
    message = models.TextField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    send_notification = models.BooleanField(default=False)
    send_notification_date = models.DateTimeField(null=True, blank=True)

    notified_units = models.ManyToManyField(
        Unit,
        related_name='notified_messages',
        blank=True
    )

    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.title or str(self.id)


class MessageReadStatus(models.Model):
    message = models.ForeignKey(
        MessageToUser,
        on_delete=models.CASCADE,
        related_name='read_statuses'
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE
    )

    recipient = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='message_read_statuses'
    )

    is_read = models.BooleanField(default=False)

    read_at = models.DateTimeField(
        null=True,
        blank=True
    )

    class Meta:
        unique_together = (
            'message',
            'recipient',
        )

    def __str__(self):
        return (
            f"{self.recipient} - "
            f"{self.message.title} - "
            f"{'خوانده شده' if self.is_read else 'خوانده نشده'}"
        )


# ------------------- Admin Message To MiddleAdmin --------------------------

class AdminMessageToMiddle(models.Model):
    sender = models.ForeignKey(
        User, on_delete=models.CASCADE,
        related_name='sent_admin_messages',
        limit_choices_to={'is_superuser': True},  # فقط ادمین اصلی
        verbose_name='فرستنده'
    )
    middleAdmins = models.ManyToManyField(
        User,
        related_name='received_admin_messages',
        verbose_name='مدیران ساختمان'
    )
    title = models.CharField(max_length=400, null=True, blank=True, verbose_name='عنوان پیام')
    message = models.TextField(null=True, blank=True, verbose_name='متن پیام')
    send_notification = models.BooleanField(default=False)
    send_notification_date = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال')

    def __str__(self):
        return self.title or f"پیام {self.id} از {self.sender.full_name}"


class MiddleMessageReadStatus(models.Model):
    message = models.ForeignKey(
        AdminMessageToMiddle,
        on_delete=models.CASCADE,
        related_name='read_statuses'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE
    )
    is_read = models.BooleanField(default=False, verbose_name='خوانده شده')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='زمان خواندن')

    class Meta:
        unique_together = ('message', 'user')

    def __str__(self):
        return f"{self.user.full_name} - {self.message.title} - {'خوانده شده' if self.is_read else 'خوانده نشده'}"


# -------------------- Expense View ------------------------
class ExpenseCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    title = models.CharField(max_length=100, verbose_name='نام')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='')
    is_active = models.BooleanField(default=True, verbose_name='')
    is_default = models.BooleanField(
        default=False,
        verbose_name='دسته پیش‌فرض'
    )

    def __str__(self):
        return self.title


class Expense(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_expenses',
        verbose_name='ساختمان مرتبط'
    )
    receiver_name = models.CharField(max_length=400, null=True, blank=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, verbose_name='گروه',
                                 related_name='expenses')
    date = models.DateField(verbose_name='تاریخ سند')
    doc_no = models.IntegerField(null=True, blank=True, verbose_name='شماره سند')
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    description = models.CharField(max_length=4000, verbose_name='شرح')
    amount = models.PositiveIntegerField(verbose_name='قیمت', null=True, blank=True, default=0)
    details = models.TextField(verbose_name='توضیحات', null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return str(self.doc_no)

    def get_image_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))


class ExpenseDocument(models.Model):
    expense = models.ForeignKey(Expense, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/expense/')
    uploaded_at = models.DateTimeField(auto_now_add=True)


# Income Modals ==============================================================
class IncomeCategory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subject = models.CharField(max_length=100, verbose_name='نام')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='')
    is_active = models.BooleanField(default=True, verbose_name='')

    def __str__(self):
        return self.subject


class Income(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_incomes',
        verbose_name='ساختمان مرتبط'
    )
    payer_name = models.CharField(max_length=400, null=True, blank=True)
    category = models.ForeignKey(IncomeCategory, on_delete=models.CASCADE, verbose_name='گروه', related_name='incomes')
    doc_date = models.DateField(verbose_name='تاریخ سند')
    doc_number = models.IntegerField(null=True, blank=True, verbose_name='شماره سند')
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    description = models.CharField(max_length=4000, verbose_name='شرح')
    amount = models.PositiveIntegerField(verbose_name='قیمت', null=True, blank=True, default=0)
    details = models.TextField(verbose_name='توضیحات', null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return str(self.doc_number)

    def get_document_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]

        return mark_safe(json.dumps(image_urls))


class IncomeDocument(models.Model):
    income = models.ForeignKey(Income, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/income/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.income.category)


# ======================= Receive & Pay Modals ==========================
class ReceiveMoney(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_receives',
        verbose_name='ساختمان مرتبط'
    )
    payer_name = models.CharField(max_length=400, null=True, blank=True)
    doc_date = models.DateField(verbose_name='تاریخ سند')
    doc_number = models.IntegerField(null=True, blank=True, verbose_name='شماره سند')
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    description = models.CharField(max_length=4000, verbose_name='شرح')
    amount = models.PositiveIntegerField(verbose_name='مبلغ', null=True, blank=True, default=0)
    details = models.TextField(verbose_name='توضیحات', null=True, blank=True)
    is_received_money = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return str(self.unit.unit)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

    def get_document_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))

    def get_payer_display(self):
        if self.unit:
            renter = self.unit.get_active_renter()
            if renter and getattr(renter, 'renter_name', None):
                return f"واحد {self.unit.unit} - {renter.renter_name}"  # نام مستاجر
            elif self.unit.owner_name:
                return f"واحد {self.unit.unit} - {self.unit.owner_name}"  # نام مالک
            else:
                return f"واحد {self.unit.unit}"  # fallback امن
        else:
            return self.payer_name


class ReceiveDocument(models.Model):
    receive = models.ForeignKey(ReceiveMoney, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/receive/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.receive.payer_name)


# =====================================================================

class PayMoney(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.SET_NULL, null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_payments',
        verbose_name='ساختمان مرتبط'
    )
    receiver_name = models.CharField(max_length=200, verbose_name='دریافت کننده')
    document_date = models.DateField(verbose_name='تاریخ سند')
    document_number = models.IntegerField(null=True, blank=True, verbose_name='شماره سند')
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    description = models.CharField(max_length=4000, verbose_name='شرح')
    amount = models.PositiveIntegerField(verbose_name='مبلغ', null=True, blank=True, default=0)
    details = models.TextField(verbose_name='توضیحات', null=True, blank=True)
    is_paid_money = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return str(self.receiver_name)

    def save(self, *args, **kwargs):

        super().save(*args, **kwargs)

    @property
    def get_receiver_display(self):
        if self.unit:
            renter = self.unit.get_active_renter()
            if renter and getattr(renter, 'renter_name', None):
                return f"واحد {self.unit.unit} - {renter.renter_name}"  # نام مستاجر
            elif self.unit.owner_name:
                return f"واحد {self.unit.unit} - {self.unit.owner_name}"  # نام مالک
            else:
                return f"واحد {self.unit.unit}"  # fallback امن
        else:
            return self.receiver_name

    def get_document_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))


class PayDocument(models.Model):
    payment = models.ForeignKey(PayMoney, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/payment/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.payment.receiver_name)


# =========================== middleProperty Views ====================
class Property(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_property',
        verbose_name='ساختمان مرتبط'
    )
    receiver_name = models.CharField(max_length=200, verbose_name='دریافت کننده')
    company_name = models.CharField(max_length=200, verbose_name='فروشنده', null=True, blank=True)
    document_number = models.IntegerField(verbose_name='شماره سند')
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    count = models.IntegerField(verbose_name='تعداد')
    property_name = models.CharField(max_length=400, verbose_name='نام')
    property_unit = models.CharField(max_length=3000, verbose_name='واحد')
    property_location = models.CharField(max_length=400, verbose_name='آدرس')
    property_code = models.CharField(max_length=200, verbose_name='کد')
    property_price = models.IntegerField(verbose_name='ارزش')
    details = models.CharField(max_length=4000, verbose_name='توضیحات', null=True, blank=True)
    property_purchase_date = models.DateField(verbose_name='تاریخ خرید', null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد', null=True, blank=True)
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def __str__(self):
        return str(self.property_name)

    def get_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))


class PropertyDocument(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/property/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.property.property_name)


# ======================== Maintenance =============================
class Maintenance(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.SET_NULL, verbose_name='شماره حساب', null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_maintenance',
        verbose_name='ساختمان مرتبط'
    )
    expert_name = models.CharField(max_length=200, verbose_name='نام کارشناس')
    maintenance_description = models.CharField(max_length=1000, verbose_name='')
    maintenance_start_date = models.DateField(verbose_name='')
    maintenance_end_date = models.DateField(verbose_name='')
    maintenance_price = models.PositiveIntegerField(verbose_name='')
    maintenance_status = models.CharField(max_length=100, verbose_name='')
    service_company = models.CharField(max_length=200, verbose_name='')
    maintenance_document_no = models.CharField(max_length=100, verbose_name='', null=True, blank=True)
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )
    details = models.CharField(max_length=4000, verbose_name='', null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    receiver_name = models.CharField(max_length=200, verbose_name='دریافت کننده')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='')
    is_active = models.BooleanField(default=True, verbose_name='')

    def __str__(self):
        return str(self.maintenance_description)

    def get_documents_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))


class MaintenanceDocument(models.Model):
    maintenance = models.ForeignKey(Maintenance, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/maintenance/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.maintenance.maintenance_description)


class FinancialDocumentSequence(models.Model):
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name='financial_document_sequences',
        verbose_name='ساختمان'
    )

    last_number = models.PositiveIntegerField(
        default=0,
        verbose_name='آخرین شماره سند'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['house'],
                name='unique_financial_document_sequence_per_house'
            )
        ]

    def __str__(self):
        return f'{self.house} - {self.last_number}'


# =========================== sewage Modals =============================
class SewageManage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_sewage',
        verbose_name='ساختمان مرتبط'
    )
    name = models.CharField(max_length=500)
    amount = models.PositiveIntegerField(verbose_name='')
    prepayment = models.PositiveIntegerField(verbose_name='')
    installment_count = models.PositiveIntegerField(verbose_name='')
    first_due_date = models.DateField(
        null=True, blank=True,
        verbose_name="تاریخ شروع اقساط"
    )
    details = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name='')

    def __str__(self):
        return str(self.name)

    def get_documents_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.sewage_documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))

    def count_sent_units(self):
        """
        تعداد واحدهای منحصر به فردی که برای این CivilManage شارژ ارسال شده است را برمی‌گرداند.
        """
        # استفاده از Count برای شمارش واحدهای منحصر به فرد (unit_id)
        # که CivilInstallment با send_notification=True دارند.
        sent_units_count = SewageInstallment.objects.filter(
            sewage_manage=self,
            send_notification=True
        ).aggregate(
            unique_unit_count=Count('unit_id', distinct=True)
        )
        return sent_units_count.get('unique_unit_count', 0)


class SewageDocument(models.Model):
    sewage = models.ForeignKey(SewageManage, on_delete=models.CASCADE, related_name='sewage_documents')
    document = models.FileField(upload_to='images/sewage/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.sewage.name)


class SewageInstallment(models.Model):
    sewage_manage = models.ForeignKey('SewageManage', on_delete=models.CASCADE, related_name='sewage_installments')
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_installment_sewage',
        verbose_name='ساختمان مرتبط'
    )
    financial_document_number = models.PositiveIntegerField(null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, null=True, blank=True)
    installment_number = models.PositiveIntegerField()
    amount = models.PositiveIntegerField()
    prepayment_per_unit = models.PositiveIntegerField()
    due_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    payment_pending = models.BooleanField(
        default=False,
        verbose_name='در انتظار تایید پرداخت'
    )

    payment_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ ثبت درخواست پرداخت'
    )
    transaction_reference = models.CharField(max_length=20, null=True, blank=True, default=0)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    payment_gateway = models.CharField(max_length=100, null=True, blank=True)
    send_notification = models.BooleanField(default=False)

    # تاریخ ارسال نوتیفیکیشن
    send_notification_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ ارسال اعلان"
    )

    def __str__(self):
        return f"قسط شماره {self.installment_number} از {self.sewage_manage.name}"


# =========================== civil Modals =============================
class CivilManage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_civil',
        verbose_name='ساختمان مرتبط'
    )
    name = models.CharField(max_length=500)
    amount = models.PositiveIntegerField(verbose_name='')
    prepayment = models.PositiveIntegerField(verbose_name='')
    installment_count = models.PositiveIntegerField(verbose_name='')
    first_due_date = models.DateField(
        null=True, blank=True,
        verbose_name="تاریخ شروع اقساط"
    )
    details = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True, verbose_name='')

    def __str__(self):
        return str(self.name)

    def get_documents_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.civil_documents.all() if doc.document]
        print(image_urls)
        return mark_safe(json.dumps(image_urls))

    def count_sent_units(self):
        """
        تعداد واحدهای منحصر به فردی که برای این CivilManage شارژ ارسال شده است را برمی‌گرداند.
        """
        # استفاده از Count برای شمارش واحدهای منحصر به فرد (unit_id)
        # که CivilInstallment با send_notification=True دارند.
        sent_units_count = CivilInstallment.objects.filter(
            civil_manage=self,
            send_notification=True
        ).aggregate(
            unique_unit_count=Count('unit_id', distinct=True)
        )
        return sent_units_count.get('unique_unit_count', 0)

    def count_fully_paid_units(self):
        return (
            self.installments
            .filter(unit__isnull=False)
            .values('unit_id')
            .annotate(
                total_installments=Count('id'),
                paid_installments=Count(
                    'id',
                    filter=Q(is_paid=True)
                )
            )
            .filter(
                total_installments=F('paid_installments')
            )
            .count()
        )


class CivilDocument(models.Model):
    civil = models.ForeignKey(CivilManage, on_delete=models.CASCADE, related_name='civil_documents')
    document = models.FileField(upload_to='images/civil/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.civil.name)


class CivilInstallment(models.Model):
    civil_manage = models.ForeignKey('CivilManage', on_delete=models.CASCADE, related_name='installments')
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_installment',
        verbose_name='ساختمان مرتبط'
    )
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, null=True, blank=True)
    installment_number = models.PositiveIntegerField()
    amount = models.PositiveIntegerField()
    prepayment_per_unit = models.PositiveIntegerField()
    due_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده/ نشده')
    financial_document_number = models.PositiveIntegerField(null=True, blank=True)
    payment_pending = models.BooleanField(
        default=False,
        verbose_name='در انتظار تایید پرداخت'
    )

    payment_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ ثبت درخواست پرداخت'
    )
    transaction_reference = models.CharField(max_length=20, null=True, blank=True, default=0)
    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )
    payment_gateway = models.CharField(max_length=100, null=True, blank=True)
    send_notification = models.BooleanField(default=False)

    # تاریخ ارسال نوتیفیکیشن
    send_notification_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ ارسال اعلان"
    )

    def __str__(self):
        return f"قسط شماره {self.installment_number} از {self.civil_manage.name}"


# =========================== Charge Modals =============================

class BaseCharge(models.Model):
    # فیلدهای عمومی
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    name = models.CharField(max_length=300, null=True, blank=True)
    unit_count = models.IntegerField(null=True, blank=True)
    civil = models.PositiveIntegerField(default=0, null=True, blank=True, verbose_name='شارژ عمرانی')
    other_cost_amount = models.PositiveIntegerField(null=True, blank=True)
    payment_deadline = models.DateField(null=True, blank=True)
    payment_penalty_amount = models.PositiveIntegerField(null=True, blank=True)
    details = models.CharField(max_length=4000, null=True, blank=True)
    unified_charges = GenericRelation('UnifiedCharge', related_query_name='charge')
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    charge_type = ''  # باید در مدل فرزند مشخص شود

    # ⚡ اضافه می‌کنیم: فیلدهایی که میخوای در template نمایش داده شوند
    display_fields = []

    class Meta:
        abstract = True

    def to_dict(self):
        data = {
            'id': self.id,
            'name': self.name,
            'charge_type': self.charge_type,
            'created_at': self.created_at,
            'details': self.details,
            'civil': self.civil or 0,
            'other_cost_amount': self.other_cost_amount,
            'payment_penalty_amount': self.payment_penalty_amount,
            'payment_deadline': self.payment_deadline,
            'unit_count': self.unit_count,
            'app_label': self._meta.app_label,
            'model_name': self._meta.model_name,
        }

        # فقط فیلدهای قابل نمایش
        for field_name in getattr(self, 'display_fields', []):
            if hasattr(self, field_name):
                field = self._meta.get_field(field_name)  # گرفتن فیلد مدل
                data[str(field.verbose_name)] = getattr(self, field_name)

        return data


class FixCharge(BaseCharge):
    fix_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر واحد')
    charge_type = 'fix'
    display_fields = ['fix_amount']


class AreaCharge(BaseCharge):
    area_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر متر')
    total_area = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'area'
    display_fields = ['area_amount']


class PersonCharge(BaseCharge):
    person_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر نفر')
    total_people = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'person'
    display_fields = ['person_amount']


class FixPersonCharge(BaseCharge):
    fix_charge_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر واحد')
    person_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر نفر')
    total_people = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'fix_person'
    display_fields = ['fix_charge_amount', 'person_amount']


class FixAreaCharge(BaseCharge):
    fix_charge_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر واحد')
    area_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر متر')
    total_area = models.PositiveIntegerField(null=True, blank=True, )
    total_people = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'fix_area'
    display_fields = ['fix_charge_amount', 'area_amount']


class ChargeByPersonArea(BaseCharge):
    area_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر متر')
    person_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر نفر')
    total_area = models.PositiveIntegerField(null=True, blank=True)
    total_people = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'person_area'
    display_fields = ['area_amount', 'person_amount', ]


class ChargeByFixPersonArea(BaseCharge):
    fix_charge_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر واحد')
    area_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر متر')
    person_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ به ازای هر نفر')
    total_area = models.PositiveIntegerField(null=True, blank=True)
    total_people = models.PositiveIntegerField(null=True, blank=True)
    parking_count = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'fix_person_area'
    display_fields = ['fix_charge_amount', 'area_amount', 'person_amount', ]


class ChargeFixVariable(BaseCharge):
    unit_fix_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ شارژ ثابت به ازای هر واحد')
    unit_variable_person_amount = models.PositiveIntegerField(null=True, blank=True,
                                                              verbose_name='مبلغ شارژ متغیر به ازای هر نفر')
    unit_variable_area_amount = models.PositiveIntegerField(null=True, blank=True,
                                                            verbose_name='مبلغ شارژ متغیر به ازای هر متر')
    extra_parking_amount = models.PositiveIntegerField(null=True, blank=True, verbose_name='مبلغ هزینه پارکینگ اضافه')
    total_area = models.PositiveIntegerField(null=True, blank=True)
    total_people = models.PositiveIntegerField(null=True, blank=True)
    charge_type = 'fix_variable'
    display_fields = ['unit_fix_amount', 'unit_variable_amount', 'unit_variable_area_amount', 'extra_parking_amount', ]


# class ChargeByExpense(BaseCharge):

#     extra_parking_amount = models.PositiveIntegerField(null=True)
#     charge_type = 'expense_charge'
#     display_fields = ['extra_parking_amount' ]


class ChargeCalculation(models.Model):
    class Status(models.TextChoices):
        DRAFT = 'draft', 'پیش‌نویس'
        CALCULATED = 'calculated', 'محاسبه شده'
        FINALIZED = 'finalized', 'نهایی شده'
        CANCELLED = 'cancelled', 'لغو شده'

    house = models.ForeignKey(
        'user_app.MyHouse',
        on_delete=models.CASCADE,
        related_name='charge_calculations',
        verbose_name='ساختمان'
    )

    name = models.CharField(
        max_length=300,
        verbose_name='عنوان شارژ'
    )

    start_date = models.DateField(
        verbose_name='از تاریخ'
    )

    end_date = models.DateField(
        verbose_name='تا تاریخ'
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_charge_calculations',
        verbose_name='ایجاد کننده'
    )

    # -------------------------
    # اطلاعات پایه شارژ
    # -------------------------

    unit_count = models.PositiveIntegerField(
        default=0,
        verbose_name='تعداد واحد'
    )

    # civil = models.PositiveIntegerField(
    #     default=0,
    #     verbose_name='شارژ عمرانی'
    # )

    other_cost_amount = models.PositiveIntegerField(
        default=0,
        verbose_name='هزینه متفرقه'
    )

    payment_deadline = models.DateField(
        null=True,
        blank=True,
        verbose_name='مهلت پرداخت'
    )

    payment_penalty_amount = models.PositiveIntegerField(
        default=0,
        verbose_name='مبلغ جریمه'
    )

    details = models.CharField(
        max_length=4000,
        null=True,
        blank=True,
        verbose_name='توضیحات'
    )

    # -------------------------
    # وضعیت محاسبه
    # -------------------------

    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name='وضعیت'
    )

    is_finalized = models.BooleanField(
        default=False,
        verbose_name='نهایی شده'
    )

    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ نهایی شدن'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ ایجاد'
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='آخرین ویرایش'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'محاسبه شارژ'
        verbose_name_plural = 'محاسبات شارژ'

    def __str__(self):
        return self.name

    def can_edit(self):
        return not self.is_finalized

    def can_finalize(self):
        return (
                not self.is_finalized
                and self.items.filter(is_selected=True).exists()
        )

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'charge_type': 'calculation',
            'created_at': self.created_at,
            'details': self.details,
            'civil': 0,
            'other_cost_amount': self.other_cost_amount,
            'payment_penalty_amount': self.payment_penalty_amount,
            'payment_deadline': self.payment_deadline,
            'unit_count': self.unit_count,

            'app_label': self._meta.app_label,
            'model_name': self._meta.model_name,

            # مخصوص ChargeCalculation
            'start_date': self.start_date,
            'end_date': self.end_date,
            'status': self.status,
            'status_display': self.get_status_display(),
            'is_finalized': self.is_finalized,
            'finalized_at': self.finalized_at,
        }


# class ChargeCalculationItem(models.Model):

#     class AllocationBasis(models.TextChoices):
#         EQUAL = 'equal', 'مساوی'
#         AREA = 'area', 'متراژ'
#         PERSON = 'person', 'تعداد نفرات'

#     class AllocationScope(models.TextChoices):
#         ALL = 'all', 'همه واحدها'
#         OCCUPIED = 'occupied', 'واحدهای ساکن'
#         VACANT = 'vacant', 'واحدهای خالی'

#     calculation = models.ForeignKey(
#         ChargeCalculation,
#         on_delete=models.CASCADE,
#         related_name='items',
#         verbose_name='محاسبه شارژ'
#     )

#     content_type = models.ForeignKey(
#         ContentType,
#         on_delete=models.PROTECT,
#         verbose_name='نوع هزینه'
#     )

#     object_id = models.PositiveIntegerField(
#         verbose_name='شناسه هزینه'
#     )

#     source = GenericForeignKey(
#         'content_type',
#         'object_id'
#     )

#     amount = models.PositiveIntegerField(
#         verbose_name='مبلغ هزینه'
#     )

#     title = models.CharField(
#         max_length=1000,
#         verbose_name='شرح هزینه'
#     )

#     source_date = models.DateField(
#         null=True,
#         blank=True,
#         verbose_name='تاریخ هزینه'
#     )

#     allocation_basis = models.CharField(
#         max_length=30,
#         choices=AllocationBasis.choices,
#         verbose_name='مبنای تقسیم'
#     )

#     # =====================================================
#     # واحدهای مشمول هزینه
#     # =====================================================

#     allocation_scope = models.CharField(
#         max_length=20,
#         choices=AllocationScope.choices,
#         default=AllocationScope.ALL,
#         verbose_name='واحدهای مشمول'
#     )

#     source_unit = models.ForeignKey(
#         Unit,
#         on_delete=models.PROTECT,
#         null=True,
#         blank=True,
#         related_name='charge_calculation_items',
#         verbose_name='واحد هزینه'
#     )

#     fixed_amount = models.PositiveIntegerField(
#         default=0,
#         verbose_name='مبلغ ثابت'
#     )

#     is_selected = models.BooleanField(
#         default=True,
#         verbose_name='انتخاب شده'
#     )

#     created_at = models.DateTimeField(
#         auto_now_add=True,
#         verbose_name='تاریخ ایجاد'
#     )

#     class Meta:
#         ordering = ['source_date', 'id']

#         constraints = [
#             models.UniqueConstraint(
#                 fields=[
#                     'calculation',
#                     'content_type',
#                     'object_id'
#                 ],
#                 name='unique_charge_calculation_source'
#             )
#         ]

#         verbose_name = 'هزینه انتخاب شده برای شارژ'
#         verbose_name_plural = 'هزینه های انتخاب شده برای شارژ'

#     def __str__(self):
#         return f'{self.title} - {self.amount:,}'

#     @property
#     def source_type(self):
#         return self.content_type.model

#     @property
#     def source_name(self):
#         if self.source_type == 'expense':
#             return 'هزینه'

#         if self.source_type == 'maintenance':
#             return 'تعمیرات'

#         return self.source_type

class ChargeCalculationItem(models.Model):
    class AllocationBasis(models.TextChoices):
        EQUAL = 'equal', 'مساوی'
        AREA = 'area', 'متراژ'
        PERSON = 'person', 'تعداد نفرات'

    class AllocationScope(models.TextChoices):
        ALL = 'all', 'همه واحدها'
        OCCUPIED = 'occupied', 'واحدهای ساکن'
        VACANT = 'vacant', 'واحدهای خالی'
        SELECTED = 'selected', 'انتخاب واحد'

    calculation = models.ForeignKey(
        ChargeCalculation,
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='محاسبه شارژ'
    )

    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.PROTECT,
        verbose_name='نوع هزینه'
    )

    object_id = models.PositiveIntegerField(
        verbose_name='شناسه هزینه'
    )

    source = GenericForeignKey(
        'content_type',
        'object_id'
    )

    amount = models.PositiveIntegerField(
        verbose_name='مبلغ هزینه'
    )

    title = models.CharField(
        max_length=1000,
        verbose_name='شرح هزینه'
    )

    source_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='تاریخ هزینه'
    )

    allocation_basis = models.CharField(
        max_length=30,
        choices=AllocationBasis.choices,
        verbose_name='مبنای تقسیم'
    )

    allocation_scope = models.CharField(
        max_length=20,
        choices=AllocationScope.choices,
        default=AllocationScope.ALL,
        verbose_name='واحدهای مشمول'
    )

    # =====================================================
    # واحدهای انتخاب‌شده در حالت انتخاب دستی
    # =====================================================

    selected_units = models.ManyToManyField(
        Unit,
        blank=True,
        related_name='selected_charge_calculation_items',
        verbose_name='واحدهای انتخاب شده'
    )

    source_unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='charge_calculation_items',
        verbose_name='واحد هزینه'
    )

    fixed_amount = models.PositiveIntegerField(
        default=0,
        verbose_name='مبلغ ثابت'
    )

    is_selected = models.BooleanField(
        default=True,
        verbose_name='انتخاب شده'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ ایجاد'
    )

    class Meta:
        ordering = ['source_date', 'id']

        constraints = [
            models.UniqueConstraint(
                fields=[
                    'calculation',
                    'content_type',
                    'object_id'
                ],
                name='unique_charge_calculation_source'
            )
        ]

        verbose_name = 'هزینه انتخاب شده برای شارژ'
        verbose_name_plural = 'هزینه های انتخاب شده برای شارژ'

    def __str__(self):
        return f'{self.title} - {self.amount:,}'

    @property
    def source_type(self):
        return self.content_type.model

    @property
    def source_name(self):
        if self.source_type == 'expense':
            return 'هزینه'

        if self.source_type == 'maintenance':
            return 'تعمیرات'

        return self.source_type


class ChargeAllocation(models.Model):
    item = models.ForeignKey(
        ChargeCalculationItem,
        on_delete=models.CASCADE,
        related_name='allocations',
        verbose_name='هزینه محاسبه'
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.PROTECT,
        related_name='charge_allocations',
        verbose_name='واحد'
    )

    # مقدار واقعی استفاده شده در محاسبه
    #
    # اگر مبنا متراژ باشد:
    # 120
    #
    # اگر مبنا نفرات باشد:
    # 3
    #
    # اگر مساوی باشد:
    # 1
    calculation_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=0,
        verbose_name='مقدار محاسباتی'
    )

    # Snapshot متراژ
    area_snapshot = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name='متراژ در زمان محاسبه'
    )

    # Snapshot تعداد نفرات
    people_snapshot = models.PositiveIntegerField(
        null=True,
        blank=True,
        verbose_name='تعداد نفرات در زمان محاسبه'
    )

    # مبلغ سهم این واحد از این هزینه
    amount = models.PositiveIntegerField(
        default=0,
        verbose_name='سهم واحد'
    )

    # برای کنترل خطاهای گرد کردن
    exact_amount = models.DecimalField(
        max_digits=18,
        decimal_places=6,
        default=0,
        verbose_name='مبلغ دقیق محاسباتی'
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='تاریخ ایجاد'
    )

    class Meta:
        ordering = ['id']

        constraints = [
            models.UniqueConstraint(
                fields=['item', 'unit'],
                name='unique_charge_allocation_item_unit'
            )
        ]

        verbose_name = 'سهم واحد از هزینه'
        verbose_name_plural = 'سهم واحدها از هزینه'

    def __str__(self):
        return (
            f'واحد {self.unit.unit} - '
            f'{self.amount:,}'
        )


class UnifiedCharge(models.Model):
    class ChargeType(models.TextChoices):
        FIX = 'fix', 'ثابت'  # Fixed Charge → ثابت
        AREA = 'area', 'متراژی'  # Area Charge → متراژ
        PERSON = 'person', 'نفری'  # Person Charge → نفر
        FIX_PERSON = 'fix_person', 'ثابت + نفر'  # Fixed Person Charge → ثابت + نفر
        FIX_AREA = 'fix_area', 'ثابت + متراژ'  # Fixed Area Charge → ثابت + متراژ
        PERSON_AREA = 'person_area', 'نفر + متراژ'  # Person Area Charge → نفر + متراژ
        FIX_PERSON_AREA = 'fix_person_area', 'ثابت + نفر + متراژ'  # Fixed Person Area → ثابت + نفر + متراژ
        FIX_VARIABLE = 'fix_variable', 'ثابت و متغیر'  # Variable Fixed Charge → ثابت متغیر
        EXPENSE_CHARGE = 'expense_charge', 'هزینه ها'  # Variable Fixed Charge → ثابت متغیر

    main_charge = GenericForeignKey('content_type', 'object_id')
    # کاربر صاحب شارژ
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="unified_charges"
    )
    # payment_token = models.CharField(
    #     max_length=16,
    #     unique=True,
    #     editable=False
    # )
    financial_document_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        editable=False,
        verbose_name='شماره سند مالی'
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.CASCADE,
        related_name="unified_charges",
        null=True,
        blank=True
    )
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name="unified_charges",
        null=True,
        blank=True
    )

    bank = models.ForeignKey(
        Bank,
        on_delete=models.CASCADE,
        related_name="unified_charges",
        null=True,
        blank=True
    )
    # نوع شارژ (نوع محاسبات)
    charge_type = models.CharField(
        max_length=50,
        choices=ChargeType.choices
    )
    # مبلغ نهایی

    amount = models.IntegerField(null=True, blank=True)
    other_cost_amount = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    civil = models.PositiveIntegerField(verbose_name='شارژ عمرانی', default=0, null=True, blank=True)
    base_charge = models.IntegerField(null=True, blank=True)
    penalty_percent = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    penalty_amount = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    total_charge_month = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    extra_parking_price = models.PositiveIntegerField(verbose_name='', null=True, blank=True)

    details = models.CharField(max_length=4000, verbose_name='', null=True, blank=True)
    transaction_reference = models.CharField(max_length=20, null=True, blank=True)
    payment_gateway = models.CharField(max_length=100, null=True, blank=True)

    # توضیح
    title = models.TextField(blank=True, null=True)
    send_notification = models.BooleanField(default=False)

    # تاریخ ارسال نوتیفیکیشن
    send_notification_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ ارسال اعلان"
    )
    send_sms = models.BooleanField(default=False)

    # تاریخ ارسال نوتیفیکیشن
    send_sms_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ ارسال پیامک"
    )
    sms_count = models.PositiveIntegerField(default=0)
    sms_price = models.DecimalField(max_digits=10, decimal_places=0, default=0)
    sms_total_price = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    # تاریخ ددلاین پرداخت
    payment_deadline_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="مهلت پرداخت"
    )

    payment_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="تاریخ پرداخت"
    )

    # وضعیت پرداخت
    is_paid = models.BooleanField(default=False)
    payment_pending = models.BooleanField(
        default=False,
        verbose_name='در انتظار تایید پرداخت'
    )

    payment_submitted_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='تاریخ ثبت درخواست پرداخت'
    )

    # 🟦 Generic Relation به مدل اصلی محاسبه
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    object_id = models.PositiveIntegerField(
        null=True,
        blank=True
    )
    is_penalty_waived = models.BooleanField(default=False)
    penalty_waived_at = models.DateTimeField(null=True, blank=True)
    penalty_waived_by = models.ForeignKey(
        User,
        null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='waived_penalties'
    )
    previous_penalty_amount = models.PositiveIntegerField(null=True, blank=True)

    # تاریخ ایجاد
    created_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.unit:
            self.house = self.unit.myhouse

        if not self.payment_token:
            self.payment_token = secrets.token_urlsafe(12)

        super().save(*args, **kwargs)

    # def generate_payment_token():
    #     return secrets.token_urlsafe(12)

    @property
    def app_label(self):
        return self._meta.app_label

    @property
    def model_name(self):
        return self._meta.model_name

    @property
    def notified_count_property(self):
        managed_users = self.user.managed_users.all()

        return UnifiedCharge.objects.filter(
            unit__is_active=True,
            unit__user__in=managed_users,
            send_notification=True,
            charge_type=self.charge_type
        ).values('unit').distinct().count()

    def waive_penalty(self, user):
        if not user:
            raise ValueError('user is required to waive penalty')

        # مبلغ واقعی جریمه قبل از بخشودگی
        previous_penalty = self.penalty_amount or 0

        # ذخیره مبلغ جریمه قبلی
        self.previous_penalty_amount = previous_penalty

        # وضعیت بخشودگی
        self.is_penalty_waived = True
        self.penalty_amount = 0
        self.penalty_waived_at = timezone.now()
        self.penalty_waived_by = user

        # مبلغ کل شارژ بدون جریمه
        self.total_charge_month = self.base_charge or 0

        self.save(update_fields=[
            'is_penalty_waived',
            'penalty_amount',
            'previous_penalty_amount',
            'penalty_waived_at',
            'penalty_waived_by',
            'total_charge_month',
        ])

        return {
            'title': self.title or 'شارژ',
            'previous_penalty_amount': previous_penalty,
        }

    def restore_penalty(self):
        if not self.is_penalty_waived or self.previous_penalty_amount is None:
            return None  # جریمه‌ای برای بازیابی وجود ندارد

        self.penalty_amount = self.previous_penalty_amount
        self.is_penalty_waived = False
        self.penalty_waived_at = None
        self.penalty_waived_by = None
        self.previous_penalty_amount = None
        self.total_charge_month = (self.base_charge or 0) + self.penalty_amount
        self.save()

        return {
            'title': getattr(self, 'name', f'واحد {self.id}'),
            'penalty_amount': self.penalty_amount
        }

    @property
    def real_unit_count(self):
        return (
            self.unified_charges
            .filter(unit__is_active=True)
            .values_list('unit_id', flat=True)
            .distinct()
            .count()
        )

    def update_penalty(self, save=True):
        """
        محاسبه جریمه دیرکرد فقط در صورت مجاز بودن
        """

        # 1️⃣ پرداخت شده → جریمه ندارد
        if self.is_paid:
            return

        # 2️⃣ جریمه توسط مدیر بخشیده شده
        if self.is_penalty_waived:
            if self.penalty_amount != 0:
                self.penalty_amount = 0
                self.total_charge_month = self.base_charge or 0
                if save:
                    self.save(update_fields=['penalty_amount', 'total_charge_month'])
            return

        # 3️⃣ شرایط محاسبه
        if not self.payment_deadline_date or not self.penalty_percent:
            return

        today = timezone.now().date()

        # 4️⃣ هنوز مهلت نگذشته
        if today <= self.payment_deadline_date:
            if self.penalty_amount != 0:
                self.penalty_amount = 0
                self.total_charge_month = self.base_charge or 0
                if save:
                    self.save(update_fields=['penalty_amount', 'total_charge_month'])
            return

        # 5️⃣ محاسبه جریمه
        delay_days = (today - self.payment_deadline_date).days
        base = self.base_charge or 0
        new_penalty = int(base * self.penalty_percent / 100 * delay_days)

        if new_penalty != (self.penalty_amount or 0):
            self.penalty_amount = new_penalty
            self.total_charge_month = base + new_penalty
            if save:
                self.save(update_fields=['penalty_amount', 'total_charge_month'])

    def get_mobile(self):
        """
        شماره موبایل برای ارسال پیامک:
        اولویت:
        1️⃣ مستاجر فعال
        2️⃣ مالک واحد
        """
        if not self.unit:
            return None

        # مستاجر فعال
        renter = self.unit.renters.filter(renter_is_active=True).first()
        if renter and renter.renter_mobile:
            return renter.renter_mobile

        # مالک
        if self.unit.owner_mobile:
            return self.unit.owner_mobile

        return None

    from django.db.models import Sum, Q

    # def get_previous_debt(self):
    #     """
    #     محاسبه مجموع بدهی‌های پرداخت‌نشده قبلی همان واحد
    #     """
    #     if not self.unit:
    #         return 0
    #
    #     # به‌روزرسانی جریمه همه بدهی‌های قبلی قبل از محاسبه
    #     previous_charges = UnifiedCharge.objects.filter(
    #         unit=self.unit,
    #         is_paid=False,
    #         created_at__lt=self.created_at
    #     )
    #
    #     total = 0
    #     for charge in previous_charges:
    #         charge.update_penalty(save=False)
    #         total += charge.total_charge_month or 0
    #
    #     return total
    #
    # @property
    # def total_payable_with_previous(self):
    #     previous = self.get_previous_debt()
    #     current = self.total_charge_month or self.amount or 0
    #     return previous + current

    def get_previous_debt_by_type(self):
        """
        محاسبه بدهی‌های پرداخت‌نشده قبلی همان واحد، تفکیک شده بر اساس نوع شارژ
        """
        if not self.unit:
            return {}

        today = timezone.now().date()

        # همه بدهی‌های قبلی که پرداخت نشده و قبل از این شارژ ایجاد شده‌اند
        previous_charges = UnifiedCharge.objects.filter(
            unit=self.unit,
            is_paid=False,
            send_notification=True,
            payment_deadline_date__lt=self.created_at
        )

        result = defaultdict(int)
        for charge in previous_charges:
            charge.update_penalty(save=False)
            result[charge.charge_type] += charge.total_charge_month or 0

        return dict(result)

    @property
    def total_previous_debt(self):
        """
        جمع عددی تمام بدهی‌های معوقه قبلی (فرقی نمی‌کند نوع شارژ)
        """
        debts_by_type = self.get_previous_debt_by_type()
        return sum(debts_by_type.values())

    @property
    def total_payable_with_previous(self):
        """
        جمع کل قابل پرداخت = شارژ این ماه + بدهی معوقه
        """
        current = self.total_charge_month or self.amount or 0
        return current + self.total_previous_debt


class Fund(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, null=True, blank=True, related_name='funds')
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_funds',
        verbose_name='ساختمان مرتبط'
    )
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    doc_number = models.PositiveIntegerField(null=True, blank=True)
    financial_document_number = models.PositiveIntegerField(null=True, blank=True)

    payer_name = models.CharField(max_length=200, null=True, blank=True)
    receiver_name = models.CharField(max_length=200, null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    debtor_amount = models.DecimalField(max_digits=12, decimal_places=0)
    creditor_amount = models.DecimalField(max_digits=12, decimal_places=0)
    final_amount = models.DecimalField(max_digits=12, decimal_places=0, default=0)

    payment_gateway = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    transaction_no = models.CharField(max_length=15, null=True, blank=True)
    payment_description = models.CharField(max_length=500, blank=True, null=True)
    is_initial = models.BooleanField(default=False, verbose_name='افتتاحیه حساب')
    created_at = models.DateTimeField(auto_now_add=True)
    is_received_money = models.BooleanField(default=False)
    is_paid_money = models.BooleanField(default=False)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"Fund: {self.payment_description} for {self.content_object}"

    def clean(self):
        """
        قبل از ذخیره، مطمئن شویم final_amount منفی نمی‌شود
        """
        if self.final_amount < 0:
            raise ValidationError("موجودی صندوق کافی نیست. ثبت این تراکنش باعث منفی شدن موجودی می‌شود.")

    @transaction.atomic
    def save(self, *args, **kwargs):
        # تعیین شماره سند فقط برای رکورد جدید
        if not self.pk:
            if not self.doc_number:
                last_doc_number = Fund.objects.aggregate(models.Max('doc_number'))['doc_number__max']
                self.doc_number = (last_doc_number or 0) + 1

            # محاسبه final_amount فقط برای رکورد جدید
            last_fund = Fund.objects.order_by('-doc_number').first()
            previous_final = Decimal(last_fund.final_amount if last_fund and last_fund.final_amount is not None else 0)
            self.final_amount = previous_final + (self.debtor_amount or 0) - (self.creditor_amount or 0)

            # بررسی منفی شدن موجودی
            if self.final_amount < 0:
                raise ValidationError("موجودی صندوق کافی نیست. ثبت این تراکنش باعث منفی شدن موجودی می‌شود.")

        # برای رکوردهای موجود، final_amount با recalc_final_amounts_from به‌روزرسانی می‌شود
        super().save(*args, **kwargs)

    @classmethod
    def recalc_final_amounts_from(cls, fund):
        """
        بازمحاسبه final_amount فقط از Fund داده شده به بعد
        """
        with transaction.atomic():
            # موجودی قبل از fund
            last_before = cls.objects.filter(doc_number__lt=fund.doc_number).order_by('-doc_number').first()
            running_total = Decimal(last_before.final_amount if last_before else 0)

            # بروزرسانی این Fund و بعدی‌ها
            qs = cls.objects.filter(doc_number__gte=fund.doc_number).order_by('doc_number')
            for f in qs:
                running_total += (f.debtor_amount or 0) - (f.creditor_amount or 0)
                if running_total < 0:
                    raise ValidationError(f"خطا: موجودی صندوق در سند شماره {f.doc_number} منفی شد!")
                f.final_amount = running_total
                f.save(update_fields=['final_amount'])


class BankFund(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, null=True, blank=True, related_name='banks_funds')
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bank_funds',
        verbose_name='ساختمان مرتبط'
    )
    TRANSACTION_TYPES = (
        ('deposit', 'واریز'),
        ('withdraw', 'برداشت'),
        ('transfer', 'انتقال'),
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        default='deposit'
    )
    transfer_group_id = models.UUIDField(null=True, blank=True, editable=False, db_index=True)

    to_bank = models.ForeignKey(
        Bank,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='received_transfers'
    )
    balance_after = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0
    )
    financial_document_number = models.PositiveIntegerField(null=True, blank=True)
    payer_name = models.CharField(max_length=200, null=True, blank=True)
    receiver_name = models.CharField(max_length=200, null=True, blank=True)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    payment_gateway = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    transaction_no = models.CharField(max_length=15, null=True, blank=True)
    payment_description = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"Fund: {self.payment_description} for {self.content_object}"


class AdminFund(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    house = models.ForeignKey(MyHouse, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True,
                              related_name='admin_houses')
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    amount = models.DecimalField(max_digits=12, decimal_places=0, null=True, blank=True)
    payment_gateway = models.CharField(max_length=100, null=True, blank=True)
    payment_date = models.DateField(null=True, blank=True)
    transaction_no = models.CharField(max_length=15, null=True, blank=True)
    payment_description = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_paid = models.BooleanField(default=False)

    def __str__(self):
        return f"Fund: {self.payment_description} for {self.content_object}"


class SmsCredit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='مدیر')
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name="sms_credit",
        null=True,
        blank=True
    )
    res_num = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name='شناسه سفارش'
    )
    amount = models.DecimalField(max_digits=10, decimal_places=0, verbose_name='مبلغ شارژ')
    amount_with_tax = models.DecimalField(max_digits=10, decimal_places=2, verbose_name='مبلغ با مالیات', default=0)
    is_paid = models.BooleanField(default=False, verbose_name='پرداخت شده؟')
    payment_date = models.DateField(null=True, blank=True)
    transaction_no = models.CharField(max_length=15, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.amount} تومان - {'پرداخت شده' if self.is_paid else 'در انتظار پرداخت'}"


class SmsManagement(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, related_name='sms_unit', blank=True, null=True)
    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name="house_sms",
        null=True,
        blank=True
    )
    STATUS_CHOICES = [
        ("draft", "پیش نویس"),
        ("pending", "در انتظار بررسی"),
        ("approved", "تأیید شده"),
        ("revision", "نیاز به اصلاح"),
        ("ready", "آماده ارسال مجدد"),
    ]

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="pending"
    )

    review_note = models.TextField(
        blank=True,
        verbose_name="دلیل نیاز به اصلاح"
    )

    reviewed_by = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_sms"
    )

    reviewed_at = models.DateTimeField(
        null=True,
        blank=True
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    send_notification = models.BooleanField(default=False)
    send_notification_date = models.DateField(null=True, blank=True)
    notified_units = models.ManyToManyField('user_app.Unit', blank=True)  # اضافه کردن رابطه با واحدها
    is_active = models.BooleanField(default=True)

    total_units_sent = models.PositiveIntegerField(default=0)
    sms_per_message = models.PositiveIntegerField(default=0)
    total_sms_sent = models.PositiveIntegerField(default=0)

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0
    )

    # is_approved = models.BooleanField(default=False)
    # approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.subject

    @property
    def message_length(self):
        return len(self.message or "")

    @property
    def sms_count(self):
        """
        هر ۷۰ کاراکتر = ۱ پیامک
        """
        if not self.message:
            return 0
        return math.ceil(len(self.message) / 70)

    @property
    def notified_units_count(self):
        return self.notified_units.count()

    @property
    def total_sms_needed(self):
        """
        تعداد کل پیامک = تعداد پیامک هر متن × تعداد واحدها
        """
        return self.sms_count * self.notified_units_count


class AdminSmsManagement(models.Model):
    # فرستنده پیامک
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="admin_sms_sent"
    )

    # گیرندگان پیامک
    notified_users = models.ManyToManyField(
        User,
        blank=True,
        related_name="admin_sms_received"
    )
    subject = models.CharField(max_length=200)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    send_notification = models.BooleanField(default=False)
    send_notification_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    total_units_sent = models.PositiveIntegerField(default=0)
    sms_per_message = models.PositiveIntegerField(default=0)
    total_sms_sent = models.PositiveIntegerField(default=0)

    total_price = models.DecimalField(
        max_digits=12,
        decimal_places=0,
        default=0
    )

    @property
    def sms_count(self):
        """
        هر ۷۰ کاراکتر = ۱ پیامک
        """
        if not self.message:
            return 0
        return math.ceil(len(self.message) / 70)

    @property
    def notified_users_count(self):
        return self.notified_users.count()

    def total_sms_needed(self):
        """
        تعداد کل پیامک = تعداد پیامک هر متن × تعداد واحدها
        """
        return self.sms_count * self.notified_users_count


class SubscriptionPlan(models.Model):
    DURATION_CHOICES = (
        (3, 'سه ماهه'),
        (6, 'شش ماهه'),
        (12, 'دوازده ماهه'),
    )

    duration = models.PositiveSmallIntegerField(choices=DURATION_CHOICES, verbose_name="مدت اشتراک")
    price_per_unit = models.PositiveIntegerField(verbose_name="هزینه هر واحد برای این پلن")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاریخ ایجاد")

    def __str__(self):
        return f"{self.get_duration_display()}"

    @property
    def duration_days(self):
        return self.duration * 1


class Coupon(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="coupon_user"
    )
    code = models.CharField(max_length=50, unique=True)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    discount = models.PositiveIntegerField(
        validators=[
            MinValueValidator(0),
            MaxValueValidator(10000000)
        ],
        verbose_name='مبلغ تخفیف'
    )
    active = models.BooleanField(default=True)

    class Meta:
        unique_together = ('user', 'coupon')

    def __str__(self):
        return self.code

    def clean(self):
        if self.valid_to <= self.valid_from:
            raise ValidationError("تاریخ پایان باید پس از تاریخ شروع باشد.")

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

    def is_valid(self):
        now = timezone.now()
        return self.active and self.valid_from <= now < self.valid_to

    def get_jalali_date(self):
        return date2jalali(self.valid_from)

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['active', 'valid_from', 'valid_to']),
        ]


class Subscription(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    house = models.ForeignKey(MyHouse, on_delete=models.CASCADE, null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE, null=True, blank=True)
    discount_amount = models.PositiveIntegerField(default=0)
    final_amount = models.PositiveIntegerField()
    STATUS_CHOICES = (
        ('active', 'فعال'),
        ('expired', 'منقضی شده'),
        ('cancelled', 'لغو شده'),
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='active'
    )

    units_count = models.PositiveIntegerField(verbose_name="تعداد واحد")
    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.CASCADE,
        null=True,
        blank=True
    )

    total_amount = models.PositiveIntegerField(null=True, blank=True)
    payment_date = models.DateTimeField(null=True, blank=True)
    transaction_id = models.CharField(max_length=150, null=True, blank=True)

    is_paid = models.BooleanField(default=False)
    is_trial = models.BooleanField(default=False)

    start_date = models.DateTimeField(null=True, blank=True)
    end_date = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def start_trial(self):
        self.is_trial = True
        self.start_date = timezone.now()
        self.end_date = self.start_date + timedelta(days=35)
        self.save()

    @property
    def trial_days_remaining(self):
        if self.is_trial and self.end_date:
            delta = self.end_date.date() - timezone.now().date()
            return max(delta.days, 0)
        return 0

    @property
    def days_remaining(self):
        if self.end_date:
            delta = self.end_date.date() - timezone.now().date()
            return max(delta.days, 0)
        return 0

    @property
    def is_active(self):
        if self.status != "active":
            return False
        if not self.end_date:
            return False
        return timezone.now() <= self.end_date

    # ➕ پروپرتی جدید و فوق‌العاده کاربردی برای محاسبه کل روزهای دوره
    @property
    def total_days(self):
        if self.start_date and self.end_date:
            return max((self.end_date.date() - self.start_date.date()).days + 1, 1)
        return 1

    def expire_if_needed(self):
        if self.end_date and timezone.now() > self.end_date:
            if self.status == "active":
                self.status = "expired"
                self.is_trial = False
                self.save(update_fields=["status", "is_trial"])


class SubscriptionPayment(models.Model):
    STATUS_CHOICES = (
        ('pending', 'در انتظار پرداخت'),
        ('success', 'موفق'),
        ('failed', 'ناموفق'),
        ('cancelled', 'لغو شده'),
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='subscription_payments'
    )

    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='subscription_payments'
    )

    plan = models.ForeignKey(
        SubscriptionPlan,
        on_delete=models.PROTECT
    )

    coupon = models.ForeignKey(
        Coupon,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    units_count = models.PositiveIntegerField()

    total_amount = models.PositiveIntegerField()

    discount_amount = models.PositiveIntegerField(
        default=0
    )

    final_amount = models.PositiveIntegerField()

    # شماره‌ای که به سامان ارسال می‌شود
    res_num = models.CharField(
        max_length=100,
        unique=True,
        db_index=True
    )

    # RefNum برگشتی سامان
    ref_num = models.CharField(
        max_length=200,
        null=True,
        blank=True
    )

    # StraceNo سامان
    tracking_code = models.CharField(
        max_length=100,
        null=True,
        blank=True
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending'
    )

    new_registration = models.BooleanField(
        default=False
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    paid_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f'{self.res_num} - {self.user}'


class CouponUsage(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    coupon = models.ForeignKey(Coupon, on_delete=models.CASCADE)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'coupon')


