import json

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.utils import timezone
from django.utils.safestring import mark_safe


class ChargeMethod(models.Model):
    # code = models.PositiveSmallIntegerField(unique=True)
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True, verbose_name='')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='')

    def __str__(self):
        return self.name


class User(AbstractUser):
    house = models.ForeignKey(
        'MyHouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='house_users',
        verbose_name='ساختمان'
    )
    full_name = models.CharField(max_length=200, verbose_name='نام')
    mobile = models.CharField(max_length=11, unique=True, verbose_name='موبایل')
    username = models.CharField(max_length=150, unique=True, verbose_name='نام کاربری')

    otp = models.PositiveIntegerField(null=True, blank=True, verbose_name='کد فعالسازی')
    otp_create_time = models.DateTimeField(null=True, blank=True, verbose_name='زمان ارسال کد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')
    created_time = models.DateTimeField(auto_now_add=True, verbose_name='زمان ثبت')

    # This is the key field for user hierarchy:
    manager = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='managed_users',
        verbose_name='مدیر سطح میانی'
    )
    charge_methods = models.ManyToManyField(
        'ChargeMethod',
        blank=True,
        verbose_name='روش‌های شارژ قابل دسترسی'
    )

    is_middle_admin = models.BooleanField(default=False, verbose_name='مدیر سطح میانی')
    is_resident = models.BooleanField(default=False, verbose_name='مدیر ساکن ساختمان')
    is_unit = models.BooleanField(default=False, verbose_name=' ساکن ساختمان')
    is_trial = models.BooleanField(default=False, verbose_name='')

    objects = UserManager()

    USERNAME_FIELD = 'mobile'
    REQUIRED_FIELDS = ['username']

    def __str__(self):
        return f"{self.full_name}"

    def get_full_name(self):
        return self.full_name

    @property
    def charge_method_codes(self):
        return list(
            self.charge_methods
            .filter(is_active=True)
            .values_list(flat=True)
        )

    @staticmethod
    def get_manager_for_user(user):
        if user.manager and user.manager.is_middle_admin:
            return user.manager
        return None


class Bank(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        verbose_name='کاربر (مدیر)'
    )
    house = models.ForeignKey(
        'MyHouse',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='banks',
        verbose_name='ساختمان مرتبط'
    )
    bank_name = models.CharField(max_length=100, verbose_name='نام بانک')
    account_no = models.CharField(max_length=100, verbose_name='شماره حساب')
    account_holder_name = models.CharField(max_length=100, verbose_name='نام صاحب حساب')
    sheba_number = models.CharField(max_length=100, verbose_name='شماره شبا')
    cart_number = models.CharField(max_length=100, verbose_name='شماره کارت')
    initial_fund = models.PositiveIntegerField(
        verbose_name='موجودی اولیه صندوق',
        null=True,
        blank=True
    )
    current_balance = models.DecimalField(
        max_digits=18,
        decimal_places=2,
        default=0,
        null=True,
        blank=True
    )
    is_default = models.BooleanField(default=False, verbose_name='حساب پیش فرض')
    is_gateway = models.BooleanField(default=False, verbose_name='حساب پیش فرض درگاه اینترنتی')
    create_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    def save(self, *args, **kwargs):
        if self.is_default:
            # همه بانک‌های دیگر را برای همان کاربر غیرپیش‌فرض می‌کنیم
            Bank.objects.filter(user=self.user, is_default=True).exclude(id=self.id).update(is_default=False)
        super().save(*args, **kwargs)

    @classmethod
    def get_default(cls, user, house=None):
        qs = cls.objects.filter(user=user, is_default=True, is_active=True)
        if house:
            qs = qs.filter(house=house)
        return qs.first()

    def __str__(self):
        return f"{self.bank_name} - {self.account_no}"


class MyHouse(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='managed_houses'
    )

    residents = models.ManyToManyField(User, related_name='houses', blank=True, verbose_name='ساکنین')
    name = models.CharField(max_length=100, verbose_name='نام ساختمان')
    floor_counts = models.PositiveIntegerField(default=1)
    unit_counts = models.PositiveIntegerField(default=1)
    phone = models.CharField(max_length=11)
    # boss_mobile = models.CharField(max_length=11)
    user_type = models.CharField(max_length=100, null=True, blank=True, verbose_name='نوع کاربری')
    city = models.CharField(max_length=100, null=True, blank=True, verbose_name='شهر')
    address = models.CharField(max_length=200, verbose_name='آدرس')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='تاریخ ایجاد')
    is_active = models.BooleanField(default=True, verbose_name='فعال/غیرفعال')

    subdomain = models.CharField(max_length=50, null=True, blank=True, verbose_name='زیردامنه')

    def __str__(self):
        return self.name


class HouseLicense(models.Model):
    LICENSE_TYPES = (
        ('enamad', 'اینماد'),
        ('samandehi', 'ساماندهی'),
        ('business', 'جواز کسب'),
    )

    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name='licenses'
    )

    license_type = models.CharField(
        max_length=50,
        choices=LICENSE_TYPES
    )

    html_code = models.TextField()

    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.house.name}"

    def get_enamad(self):
        return self.licenses.filter(
            license_type='enamad',
            is_active=True
        ).first()


class HousePaymentGateway(models.Model):
    class GatewayType(models.TextChoices):
        ZARINPAL = "zarinpal", "زرین‌پال"
        IDPAY = "idpay", "آی‌دی‌پی"
        NEXTPAY = "nextpay", "نکست‌پی"
        STRIPE = "stripe", "Stripe"
        MELLAT = "mellat", "به پرداخت ملت"

    house = models.ForeignKey(
        MyHouse,
        on_delete=models.CASCADE,
        related_name='gateways'
    )

    gateway_type = models.CharField(
        max_length=50,
        choices=GatewayType.choices,
        verbose_name="نوع درگاه"
    )

    merchant_id = models.CharField(max_length=255, verbose_name="Merchant ID")
    api_key = models.CharField(max_length=500, verbose_name="API Key")

    is_active = models.BooleanField(default=True, verbose_name="فعال")
    is_sandbox = models.BooleanField(default=False, verbose_name="حالت تست")

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.house.name} - {self.gateway_type}"


class Unit(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='کاربر')
    unit = models.IntegerField(verbose_name='واحد')
    myhouse = models.ForeignKey(
        'MyHouse',
        on_delete=models.CASCADE,
        related_name='units',
        null=True,  # اگر دیتای قدیمی داری
        blank=True
    )
    owner_bank = models.ForeignKey(Bank, on_delete=models.CASCADE, null=True, blank=True, verbose_name='شماره حساب')

    unit_phone = models.CharField(max_length=8, null=True, blank=True, verbose_name='')
    floor_number = models.IntegerField()
    area = models.IntegerField()
    bedrooms_count = models.IntegerField()
    parking_number = models.CharField(max_length=10, null=True, blank=True)
    # parking_count = models.IntegerField()
    parking_place = models.CharField(max_length=100, null=True, blank=True, verbose_name='موقعیت پارکینگ ')
    extra_parking_first = models.CharField(max_length=100, null=True, blank=True, verbose_name='موقعیت پارکینگ اول')
    extra_parking_second = models.CharField(max_length=100, null=True, blank=True, verbose_name='موقعیت پارکینگ دوم')
    unit_details = models.TextField(null=True, blank=True, verbose_name='توضیحات ساختمان')
    owner_name = models.CharField(max_length=100, null=True, blank=True, verbose_name='نام مالک')
    owner_mobile = models.CharField(max_length=11, verbose_name='همراه مالک')
    owner_national_code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد ملی')
    purchase_date = models.DateField(null=True, blank=True, verbose_name='تاریخ خرید')
    owner_people_count = models.PositiveIntegerField(null=True, blank=True, verbose_name='تعداد نفرات مالک')
    owner_details = models.TextField(null=True, blank=True, verbose_name='توضیحات مالک')
    status_residence = models.CharField(max_length=100, null=True, blank=True, verbose_name='وضعیت سکونت')
    is_renter = models.BooleanField(default=False, verbose_name=' مستاجر دارد؟', null=True, blank=True)
    people_count = models.IntegerField(null=True, blank=True, verbose_name='تعداد نفرات')
    parking_counts = models.IntegerField(null=True, blank=True, verbose_name='تعداد پارکینگ اضافه')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='زمان ایجاد')
    first_charge_owner = models.IntegerField(null=True, blank=True, verbose_name='شارژ اولیه مالک', default=0)
    owner_payment_date = models.DateField(null=True, blank=True)
    owner_transaction_no = models.CharField(max_length=30, null=True, blank=True)

    is_active = models.BooleanField(default=True, verbose_name='فعال/غیر فعال')

    class Meta:
        unique_together = ('user', 'unit')
        verbose_name = "واحد"
        verbose_name_plural = "واحدها"

    def __str__(self):
        return f"واحد {self.unit} -  {self.user}"

    def get_unit(self):
        return f"واحد {self.unit} - {self.owner_name}"

    def get_active_renter(self):
        return self.renters.filter(renter_is_active=True).first()

    @property
    def get_label(self):
        renter = self.get_active_renter()
        return f"واحد {self.unit} - {renter.renter_name}" if renter else f"واحد {self.unit} - {self.owner_name}"

    # def get_label(self):
    #     renter = self.get_active_renter()
    #     # اگر مستاجر وجود دارد ولی نام ندارد، مالک را نمایش بده
    #     if renter and renter.renter_name:
    #         return f"واحد {self.unit} - {renter.renter_name}"
    #
    #     owner = self.owner_name or "نام مالک ندارد"
    #     return f"واحد {self.unit} - {owner}"

    def get_label_invoice(self):
        renter = self.get_active_renter()
        return f" {renter.renter_name}" if renter else f"{self.owner_name}"

    def update_people_count(self):
        renter = self.get_active_renter()
        if renter:
            self.people_count = int(renter.renter_people_count or 0)
        else:
            self.people_count = int(self.owner_people_count or 0)

    def _close_current_resident(self, date):
        UnitResidenceHistory.objects.filter(
            unit=self,
            to_date__isnull=True
        ).update(to_date=date)

    def save(self, *args, **kwargs):
        today = timezone.now().date()
        is_new = self.pk is None

        old = None
        if not is_new:
            old = Unit.objects.get(pk=self.pk)

        # محاسبه پارکینگ
        count = 0
        if self.extra_parking_first:
            count += 1
        if self.extra_parking_second:
            count += 1
        self.parking_counts = count

        # ذخیره اولیه
        super().save(*args, **kwargs)

        # بروزرسانی نفرات
        self.update_people_count()
        super().save(update_fields=['people_count', 'parking_counts'])

        # مستاجر فعال
        active_renter = self.get_active_renter()

        # -----------------------
        # واحد جدید
        # -----------------------
        if is_new:
            UnitResidenceHistory.objects.create(
                unit=self,
                resident_type='owner',
                name=self.owner_name,
                mobile=self.owner_mobile,
                people_count=int(self.owner_people_count or 0),
                from_date=today,
                changed_by=self.user
            )
            if active_renter:
                UnitResidenceHistory.objects.create(
                    unit=self,
                    resident_type='renter',
                    renter=active_renter,
                    name=active_renter.renter_name,
                    mobile=active_renter.renter_mobile,
                    people_count=int(active_renter.renter_people_count or 0),
                    from_date=active_renter.start_date or today,
                    changed_by=self.user
                )
            return

        # -----------------------
        # بروزرسانی مالک
        # -----------------------
        last_owner = UnitResidenceHistory.objects.filter(
            unit=self,
            resident_type='owner',
        ).first()

        if old and last_owner:
            old_name = old.owner_name or ""
            new_name = self.owner_name or ""
            old_mobile = old.owner_mobile or ""
            new_mobile = self.owner_mobile or ""

            # اگر تغییر کامل (نام و موبایل) داشتیم → رکورد جدید بساز
            if old_name != new_name and old_mobile != new_mobile:
                self._close_current_resident(today)
                if active_renter:
                    Renter.objects.filter(pk=active_renter.pk).update(
                        renter_is_active=False,
                        end_date=today
                    )
                UnitResidenceHistory.objects.create(
                    unit=self,
                    resident_type='owner',
                    name=self.owner_name,
                    mobile=self.owner_mobile,
                    people_count=int(self.owner_people_count or 0),
                    from_date=today,
                    changed_by=self.user
                )
            # اگر فقط نام یا موبایل تغییر کرده → بروزرسانی رکورد موجود
            elif old_name != new_name or old_mobile != new_mobile:
                last_owner.name = self.owner_name
                last_owner.mobile = self.owner_mobile
                last_owner.people_count = int(self.owner_people_count or 0)
                last_owner.save(update_fields=['name', 'mobile', 'people_count'])

        # -----------------------
        # بروزرسانی مستاجر
        # -----------------------
        if active_renter:
            last_renter = UnitResidenceHistory.objects.filter(
                unit=self,
                resident_type='renter',
                to_date__isnull=True
            ).first()

            if last_renter and last_renter.renter == active_renter:
                # فقط بروزرسانی رکورد موجود
                last_renter.name = active_renter.renter_name
                last_renter.mobile = active_renter.renter_mobile
                last_renter.people_count = int(active_renter.renter_people_count or 0)
                last_renter.save(update_fields=['name', 'mobile', 'people_count'])
            else:
                # مستاجر جدید → رکورد قبلی بسته شود و رکورد جدید ایجاد شود
                self._close_current_resident(today)
                UnitResidenceHistory.objects.create(
                    unit=self,
                    resident_type='renter',
                    renter=active_renter,
                    name=active_renter.renter_name,
                    mobile=active_renter.renter_mobile,
                    people_count=int(active_renter.renter_people_count or 0),
                    from_date=active_renter.start_date or today,
                    changed_by=self.user
                )


class Renter(models.Model):
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, verbose_name='واحد', related_name='renters', null=True,
                             blank=True)
    myhouse = models.ForeignKey(
        'MyHouse',
        on_delete=models.CASCADE,
        related_name='renters',
        null=True,  # اگر دیتای قدیمی داری
        blank=True
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name='کاربر')
    renter_bank = models.ForeignKey(Bank, on_delete=models.CASCADE, null=True, blank=True, verbose_name='شماره حساب')
    renter_name = models.CharField(max_length=100, null=True, blank=True, verbose_name='نام مستاجر')
    renter_mobile = models.CharField(max_length=11, null=True, blank=True, verbose_name='همراه')
    renter_national_code = models.CharField(max_length=10, null=True, blank=True, verbose_name='کد ملی')
    renter_people_count = models.CharField(max_length=10, null=True, blank=True, verbose_name='تعداد نفرات')
    start_date = models.DateField(null=True, blank=True, verbose_name='تاریخ شروع اجاره')
    end_date = models.DateField(null=True, blank=True, verbose_name='تاریخ پایان اجاره')
    contract_number = models.CharField(max_length=100, null=True, blank=True, verbose_name='شماره قرارداد')
    estate_name = models.CharField(max_length=100, null=True, blank=True, verbose_name='نام مشاور املاک')
    first_charge_renter = models.IntegerField(null=True, blank=True, verbose_name='شارژ اولیه مستاجر', default=0)
    renter_details = models.TextField(null=True, blank=True, verbose_name='توضیحات مستاجر')
    renter_payment_date = models.DateField(null=True, blank=True)
    renter_transaction_no = models.CharField(max_length=30, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='')
    renter_is_active = models.BooleanField(default=True, verbose_name='')

    def __str__(self):
        return self.renter_name

    def save(self, *args, **kwargs):
        # is_new = self.pk is None
        # old = None
        # if not is_new:
        #     old = Renter.objects.get(pk=self.pk)

        super().save(*args, **kwargs)
        # today = timezone.now().date()


class UnitResidenceHistory(models.Model):
    RESIDENT_TYPE_CHOICES = (
        ('owner', 'مالک'),
        ('renter', 'مستاجر'),
    )

    unit = models.ForeignKey(
        Unit,
        on_delete=models.SET_NULL,
        related_name='residence_histories',
        null=True, blank=True
    )

    resident_type = models.CharField(
        max_length=10,
        choices=RESIDENT_TYPE_CHOICES
    )

    # اطلاعات شخص
    name = models.CharField(max_length=255)
    mobile = models.CharField(max_length=20)
    people_count = models.IntegerField(default=0)

    # فقط برای مستاجر
    renter = models.ForeignKey(
        Renter,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )

    from_date = models.DateField()
    to_date = models.DateField(null=True, blank=True)

    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='unit_residence_changes'
    )

    created_at = models.DateTimeField(auto_now_add=True)

    def is_active(self):
        return self.to_date is None

    def __str__(self):
        return f"{self.get_resident_type_display()} | {self.name} | واحد {self.unit.unit}"


class CalendarNote(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    year = models.IntegerField()
    month = models.IntegerField()
    day = models.IntegerField()
    note = models.TextField(blank=True)

    class Meta:
        unique_together = ('user', 'year', 'month', 'day')

    def __str__(self):
        return f"{self.user} - {self.year}/{self.month}/{self.day}"


class UserPayMoney(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    bank = models.ForeignKey(Bank, on_delete=models.CASCADE, verbose_name='شماره حساب', null=True, blank=True)
    unit = models.ForeignKey(Unit, on_delete=models.CASCADE, null=True, blank=True)
    house = models.ForeignKey(
        'MyHouse',
        on_delete=models.CASCADE,
        related_name='user_pay_money',
        null=True,  # اگر دیتای قدیمی داری
        blank=True
    )
    payer_name = models.CharField(max_length=400, null=True, blank=True)
    payment_gateway = models.CharField(max_length=400, null=True, blank=True)
    description = models.CharField(max_length=4000, verbose_name='شرح')
    amount = models.PositiveIntegerField(verbose_name='قیمت', null=True, blank=True, default=0)
    register_date = models.DateField(verbose_name='تاریخ سند')
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
        return str(self.unit) if self.unit else f"Payment by {self.user}"

    def get_document_urls_json(self):
        # Use the correct attribute to access the file URL in the related `ExpenseDocument` model
        image_urls = [doc.document.url for doc in self.documents.all() if doc.document]

        return mark_safe(json.dumps(image_urls))


class UserPayMoneyDocument(models.Model):
    user_pay = models.ForeignKey(UserPayMoney, on_delete=models.CASCADE, related_name='documents')
    document = models.FileField(upload_to='images/user_pay/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return str(self.user_pay.unit)
