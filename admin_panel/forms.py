import datetime
import re

import jdatetime
from ckeditor_uploader.widgets import CKEditorUploadingWidget
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import ClearableFileInput
from django.utils import timezone
from django_select2.forms import ModelSelect2MultipleWidget
from jalali_date.fields import JalaliDateField
from jalali_date.widgets import AdminJalaliDateWidget
from admin_panel.models import (Announcement, Expense, ExpenseCategory, Income, IncomeCategory, ReceiveMoney, PayMoney, \
                                Property, Maintenance, ChargeByPersonArea, ChargeByFixPersonArea, FixCharge, AreaCharge,
                                PersonCharge,
                                FixPersonCharge, FixAreaCharge, ChargeFixVariable, SmsManagement, UnifiedCharge,
                                MessageToUser, SmsCredit, AdminMessageToMiddle, AdminSmsManagement, Subscription,
                                SubscriptionPlan, CivilManage, SewageManage, BankFund, Coupon)
from home.models import SliderText
from middleAdmin_panel.services.bank_services import validate_bank_transaction_date

from user_app.models import Unit, Bank, User, MyHouse, ChargeMethod, Renter, HouseLicense, HousePaymentGateway

attr = {'class': 'form-control border-1 py-2 mb-4 '}
attr0 = {'class': 'form-control form-control-sm border-1 py-1 mb-4 '}
attr1 = {'class': 'form-control border-1 py-1 mb-4 '}
attr3 = {'class': 'form-control form-control-sm border-1'}
attr2 = {'class': 'form-control border-1 my-2 mb-4 ', 'placeholder': 'لطفا واحد را انتخاب کنید'}

error_message = {
    'required': "تکمیل این فیلد ضروری است!",
    'min_length': 'تعداد کاراکترهای وارد شده کمتر از حد مجاز است!',
    'max_length': 'تعداد کاراکترهای وارد شده بیشتر از حد مجاز است!',
}

CHOICES = {
    'True': 'فعال',
    'False': 'غیرفعال'
}
MARQUEE_CHOICES = {
    'True': 'بله',
    'False': 'خیر'
}

MIDDLE_CHOICES = (
    (1, 'بله'),
    (0, 'خیر'),
)


class SliderForm(forms.ModelForm):
    title = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.TextInput(attrs=attr),
        label='عنوان اصلی '
    )
    title2 = forms.CharField(
        error_messages=error_message,
        required=False,
        widget=forms.TextInput(attrs=attr),
        label='عنوان دوم '
    )
    text = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.Textarea(attrs=attr),
        label='متن '
    )

    is_active = forms.ChoiceField(label='فعال /غیرفعال نمودن ', required=True,
                                  error_messages=error_message, choices=CHOICES, widget=forms.Select(attrs=attr))

    class Meta:
        model = SliderText
        fields = ['title', 'is_active', 'text', 'title2']


class announcementForm(forms.ModelForm):
    # title = forms.CharField(widget=CKEditorUploadingWidget())
    title = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.Textarea(attrs=attr),
        label='متن اطلاعیه '
    )
    # slug = forms.SlugField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr),
    #                        label='عنوان در Url')
    is_active = forms.ChoiceField(label='فعال /غیرفعال نمودن اطلاعیه', required=True,
                                  error_messages=error_message, choices=CHOICES, widget=forms.Select(attrs=attr))
    show_in_marquee = forms.ChoiceField(label='نمایش در اخبار مهم ساختمان', required=True, initial=False,
                                        error_messages=error_message, choices=MARQUEE_CHOICES,
                                        widget=forms.Select(attrs=attr))

    class Meta:
        model = Announcement
        fields = ['title', 'is_active', 'show_in_marquee']


class MessageToUserForm(forms.ModelForm):
    title = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.TextInput(attrs=attr),
        label='عنوان پیام'
    )
    message = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.Textarea(attrs=attr),
        label='متن پیام'
    )

    is_active = forms.ChoiceField(
        label='فعال / غیرفعال نمودن',
        required=True,
        error_messages=error_message,
        choices=CHOICES,
        widget=forms.Select(attrs=attr)
    )

    class Meta:
        model = MessageToUser
        fields = ['title', 'message', 'is_active']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # تمام کاربران تحت مدیریت این مدیر + خودش
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))
            self.fields['unit'].queryset = Unit.objects.filter(
                is_active=True,
                user__in=managed_users
            ).select_related('user')

        # # نمایش نام مستاجر فعال یا مالک
        # self.fields['unit'].label_from_instance = lambda obj: (
        #     f"واحد {obj.unit} - {obj.get_active_renter().renter_name}"
        #     if obj.get_active_renter() else
        #     f"واحد {obj.unit} - {obj.owner_name}"
        # )


class AdminMessageToMiddleForm(forms.ModelForm):
    title = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.TextInput(attrs=attr),
        label='عنوان پیام'
    )
    message = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.Textarea(attrs=attr),
        label='متن پیام'
    )

    is_active = forms.ChoiceField(
        label='فعال / غیرفعال نمودن',
        required=True,
        error_messages=error_message,
        choices=CHOICES,
        widget=forms.Select(attrs=attr)
    )

    class Meta:
        model = AdminMessageToMiddle
        fields = ['title', 'message', 'is_active']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


RESIDENCE_STATUS_CHOICES = {
    '': '--- انتخاب کنید ---',
    'occupied': 'ساکن',
    'empty': 'خالی'
}

BEDROOMS_COUNT_CHOICES = {
    '': '--- انتخاب کنید ---', '1': '1', '2': '2', '3': '3', '4': '4', '5': '5', '6': '6', '7': '7', '8': '8'
}

AREA_CHOICES = {
    '': '--- انتخاب کنید ---', '90': '90', '120': '120', '130': '130', '150': '150',
}

PARKING_PLACE_CHOICES = {
    '': '--- انتخاب کنید ---', 'همکف': 'همکف', 'طبقه -1': 'طبقه -1', 'طبقه -2': 'طبقه -2', 'طبقه -3': 'طبقه -3',
    'طبقه -4': 'طبقه -4', 'طبقه -5': 'طبقه -5',
}

PARKING_NUMBER_CHOICES = {
    ('', '--- انتخاب کنید ---'),
    ('B45', 'B45'),
    ('B52', 'B52'),
    ('B47', 'B47'),
}

PARKING_COUNT_CHOICES = {
    '': '--- انتخاب کنید ---', '1': '1', '2': '2', '3': '3',
}

BANK_CHOICES = {
    '': '--- انتخاب کنید ---', 'ملی': 'ملی', 'ملت': 'ملت', 'تجارت': 'تجارت', 'صادرات': 'صادرات', 'رسالت': 'رسالت',
    'صنعت و معدن': 'صنعت و معدن', 'کشاورزی': 'کشاورزی', 'مسکن': 'مسکن', 'رفاه': 'رفاه', 'سپه': 'سپه', 'سینا': 'سینا',
    'توسعه صادرات': 'توسعه صادرات', 'پست بانک': 'پست بانک', 'پاسارگاد': 'پاسارگاد', 'اقتصاد نوین': 'اقتصاد نوین',
    'پارسیان': 'پارسیان',
    'سامان': 'سامان', 'گردشگری': 'گردشگری', 'کارآفرین': 'کارآفرین', 'دی': 'دی', 'شهر': 'شهر',
    'ایران زمین': 'ایران زمین',
    'مهر ایران': 'مهر ایران',
}


class ChargeCategoryForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, required=True,
                           widget=forms.TextInput(attrs=attr),
                           label='روش شارژ')

    is_active = forms.ChoiceField(label='فعال /غیرفعال  ', required=True,
                                  error_messages=error_message, choices=CHOICES, widget=forms.Select(attrs=attr))

    class Meta:
        model = ChargeMethod
        fields = ['name', 'is_active']


class UserRegistrationForm(forms.ModelForm):
    mobile = forms.CharField(error_messages=error_message,
                             required=True,
                             max_length=11,
                             min_length=11,
                             widget=forms.TextInput(attrs=attr),
                             label='شماره تلفن ')
    full_name = forms.CharField(error_messages=error_message, required=True,
                                widget=forms.TextInput(attrs=attr), label='نام ')
    username = forms.CharField(error_messages=error_message, required=False,
                               widget=forms.TextInput(attrs=attr3), label='نام کاربری ')

    password = forms.CharField(
        required=False,
        label='رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )
    confirm_password = forms.CharField(
        required=False,
        label='تایید رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )
    charge_methods = forms.ModelMultipleChoiceField(
        queryset=ChargeMethod.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='روش‌های شارژ قابل دسترسی'
    )

    is_active = forms.BooleanField(
        required=False,
        label='فعال باشد؟',
        widget=forms.Select(choices=[
            (True, 'بله'),
            (False, 'خیر'),
        ], attrs=attr)
    )

    is_resident = forms.ChoiceField(
        choices=[
            ('True', 'بله'),
            ('False', 'خیر'),
        ],
        widget=forms.Select(attrs=attr),
        required=False,
        label='ساکن ساختمان میباشد؟',

    )

    is_trial = forms.ChoiceField(
        choices=[
            ('True', 'دارد'),
            ('False', 'ندارد'),
        ],
        widget=forms.Select(attrs=attr),
        required=False,
        label='اشتراک رایگان؟'
    )

    class Meta:
        model = User
        fields = ['full_name', 'username', 'mobile', 'password', 'is_active', 'charge_methods', 'is_resident',
                  'is_trial']

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if User.objects.filter(mobile=mobile).exclude(pk=self.instance.pk).exists():
            raise ValidationError("شماره موبایل قبلاً ثبت شده است.")
        return mobile

    # def clean_username(self):
    #     username = self.cleaned_data.get('username')
    #     if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
    #         raise ValidationError("نام کاربری قبلاً ثبت شده است.")
    #     return username

    def clean_password2(self):
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("password")

        if password and confirm_password and password != confirm_password:
            raise ValidationError("رمزهای عبور با هم مطابقت ندارند!")

        return confirm_password

    # def clean_is_active(self):
    #     return self.cleaned_data.get('is_active', False)

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        else:
            user.password = self.instance.password

        if commit:
            user.save()

        return user


class UserRegistrationByUserForm(forms.ModelForm):

    mobile = forms.CharField(error_messages=error_message,
                             required=True,
                             max_length=11,
                             min_length=11,
                             widget=forms.TextInput(attrs=attr),
                             label='شماره تلفن ')
    full_name = forms.CharField(error_messages=error_message, required=True,
                                widget=forms.TextInput(attrs=attr), label='نام ')
    username = forms.CharField(error_messages=error_message, required=False,
                               widget=forms.TextInput(attrs=attr3), label='نام کاربری ')

    password = forms.CharField(
        required=False,
        label='رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )
    confirm_password = forms.CharField(
        required=False,
        label='تایید رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )
    # charge_methods = forms.ModelMultipleChoiceField(
    #     queryset=ChargeMethod.objects.all(),
    #     required=False,
    #     widget=forms.CheckboxSelectMultiple,
    #     label='روش‌های شارژ قابل دسترسی'
    # )
    charge_methods = forms.ModelChoiceField(
        queryset=ChargeMethod.objects.all(),
        widget=forms.RadioSelect,
        required=True,
        label='روش محاسبه شارژ'
    )

    is_active = forms.TypedChoiceField(
        choices=(
            ('1', 'بله'),
            ('0', 'خیر'),
        ),
        required=False,
        coerce=lambda x: x == '1',
        widget=forms.Select(attrs=attr),
        label='فعال باشد؟'
    )

    is_resident = forms.TypedChoiceField(
        choices=(
            ('1', 'بله'),
            ('0', 'خیر'),
        ),
        required=False,
        coerce=lambda x: x == '1',
        widget=forms.Select(attrs=attr),
        label='ساکن ساختمان میباشد؟',

    )

    is_trial = forms.TypedChoiceField(
        choices=(
            ('1', 'بله'),
            ('0', 'خیر'),
        ),
        required=False,
        coerce=lambda x: x == '1',
        widget=forms.Select(attrs=attr),
        label='اشتراک رایگان؟',

    )

    class Meta:
        model = User
        fields = ['full_name', 'username', 'mobile', 'password', 'is_active', 'charge_methods', 'is_resident',
                  'is_trial']

    def clean_mobile(self):
        mobile = self.cleaned_data.get('mobile')
        if User.objects.filter(mobile=mobile).exclude(pk=self.instance.pk).exists():
            raise ValidationError("شماره موبایل قبلاً ثبت شده است.")
        return mobile

    # def clean_username(self):
    #     username = self.cleaned_data.get('username')
    #     if User.objects.filter(username=username).exclude(pk=self.instance.pk).exists():
    #         raise ValidationError("نام کاربری قبلاً ثبت شده است.")
    #     return username

    def clean_confirm_password(self):
        password = self.cleaned_data.get("password")
        confirm_password = self.cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            raise ValidationError("رمزهای عبور با هم مطابقت ندارند!")

        return confirm_password

    # def clean_is_active(self):
    #     return self.cleaned_data.get('is_active', False)

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        else:
            user.password = self.instance.password

        if commit:
            user.save()

        return user


IS_CHOICES = (
    ('', '--- انتخاب کنید ---'),
    (1, 'بله'),
    (0, 'خیر'),
)
IS_CHOICES_Active = (
    ('', '--- انتخاب کنید ---'),
    (1, 'بله'),
    (0, 'خیر'),
)


class BankForm(forms.ModelForm):
    house = forms.ModelChoiceField(
        queryset=MyHouse.objects.none(),
        required=True,
        widget=forms.Select(attrs=attr3),
        label='نام ساختمان'
    )
    bank_name = forms.ChoiceField(error_messages=error_message, required=True, choices=BANK_CHOICES,
                                  widget=forms.Select(attrs=attr3), label='نام بانک')

    account_holder_name = forms.CharField(error_messages=error_message, required=True,
                                          widget=forms.TextInput(attrs=attr),
                                          label='نام صاحب حساب')
    account_no = forms.CharField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr),
                                 label='شماره حساب')
    sheba_number = forms.CharField(error_messages=error_message,
                                   max_length=24,
                                   min_length=24,
                                   required=False, widget=forms.TextInput(attrs=attr),
                                   label='شماره شبا')
    cart_number = forms.CharField(error_messages=error_message,
                                  max_length=16,
                                  min_length=16,
                                  required=False, widget=forms.TextInput(attrs=attr),
                                  label='شماره کارت')
    initial_fund = forms.CharField(error_messages=error_message, required=False, widget=forms.NumberInput(attrs=attr),
                                   label='موجودی اولیه', initial=0)
    is_default = forms.ChoiceField(choices=IS_CHOICES, label='حساب پیش فرض باشد', widget=forms.Select(attrs=attr))
    is_gateway = forms.ChoiceField(choices=IS_CHOICES, label='حساب پیش فرض درگاه اینترنتی باشد',
                                   widget=forms.Select(attrs=attr))
    is_active = forms.ChoiceField(choices=IS_CHOICES_Active, label='حساب فعال باشد', widget=forms.Select(attrs=attr))

    class Meta:
        model = Bank
        fields = (
            'house', 'bank_name', 'account_holder_name', 'account_no', 'sheba_number', 'cart_number',
            'initial_fund', 'is_active', 'is_default', 'is_gateway')

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user and user.is_middle_admin:
            self.fields['house'].queryset = MyHouse.objects.filter(
                Q(user=user) | Q(user__manager=user),
                is_active=True
            )
        else:
            self.fields['house'].queryset = MyHouse.objects.none()

    def clean_sheba_number(self):
        sheba = self.cleaned_data.get('sheba_number')
        if sheba:
            sheba = sheba.replace(' ', '').upper()
            if not sheba.startswith('IR'):
                raise forms.ValidationError('شماره شبا باید با IR شروع شود')
            if len(sheba) != 24:
                raise forms.ValidationError('شماره شبا باید ۲۴ کاراکتر باشد')
        return sheba


CITY_CHOICES = [
    ('', '--- انتخاب کنید ---'),
    ('تهران', 'تهران'),
    ('مشهد', 'مشهد'),
    ('شیراز', 'شیراز'),
    ('اصفهان', 'اصفهان'),
    ('کرج', 'کرج'),
    ('قم', 'قم'),
    ('رشت', 'رشت'),
    ('اهواز', 'اهواز'),
    ('تبریز', 'تبریز'),
    ('یزد', 'یزد'),
    ('کرمان', 'کرمان'),
    ('گرگان', 'گرگان'),
    ('سنندج', 'سنندج'),
    ('بندرعباس', 'بندرعباس'),
    ('زاهدان', 'زاهدان'),
    ('اردبیل', 'اردبیل'),
    ('بوشهر', 'بوشهر'),
    ('قزوین', 'قزوین'),
    ('ارومیه', 'ارومیه'),
    ('ساری', 'ساری'),
]

USER_TYPE_CHOICES = [
    ('', '--- انتخاب کنید ---'),
    ('مسکونی', 'مسکونی'),
    ('اداری', 'اداری'),
    ('تجاری', 'تجاری'),
    ('سایر', 'سایر'),
]


class MyHouseForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr),
                           label='نام ساختمان')
    phone = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                            label='تلفن', max_length=11)
    # boss_mobile = forms.CharField(error_messages=error_message, max_length=11, required=True,
    #                               widget=forms.TextInput(attrs=attr),
    #                               label='موبایل مدیر')
    subdomain = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                label='نام لاتین')
    user_type = forms.ChoiceField(error_messages=error_message, choices=USER_TYPE_CHOICES, required=True,
                                  widget=forms.Select(attrs=attr),
                                  label='نوع کاربری')
    floor_counts = forms.IntegerField(error_messages=error_message, required=False,
                                      widget=forms.NumberInput(attrs=attr),
                                      label='تعداد طبقات')
    unit_counts = forms.IntegerField(error_messages=error_message, required=False,
                                     widget=forms.NumberInput(attrs=attr),
                                     label='تعداد واحدها')

    city = forms.ChoiceField(error_messages=error_message, choices=CITY_CHOICES, required=True,
                             widget=forms.Select(attrs=attr),
                             label='شهر')
    address = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.TextInput(attrs=attr),
                              label='آدرس')
    is_active = forms.BooleanField(
        required=False,
        label='فعال باشد؟',
        widget=forms.Select(choices=[
            (True, 'بله'),
            (False, 'خیر'),
        ], attrs=attr)
    )


    class Meta:
        model = MyHouse
        fields = ['name', 'address', 'user_type', 'city', 'is_active', 'floor_counts', 'unit_counts', 'subdomain',
                  'phone']

    def clean_subdomain(self):
        subdomain = self.cleaned_data.get('subdomain')

        if not subdomain:
            return subdomain

        subdomain = subdomain.lower()

        if not re.match(r'^[a-z0-9]+$', subdomain):
            raise ValidationError("فقط حروف کوچک انگلیسی و عدد مجاز است.")

        RESERVED = ["admin", "www", "panel", "api"]
        if subdomain in RESERVED:
            raise ValidationError("این نام قابل استفاده نیست.")

        # 🔥 مهم: چک دیتابیس
        if MyHouse.objects.filter(subdomain=subdomain).exclude(pk=self.instance.pk).exists():
            raise ValidationError("این زیردامنه قبلاً استفاده شده است.")

        return subdomain


class HouseLicenseForm(forms.ModelForm):
    html_code = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10, 'cols': 6}),
                                required=False,
                                )

    class Meta:
        model = HouseLicense
        fields = ['license_type', 'html_code', 'is_active']


class HousePaymentGatewayForm(forms.ModelForm):
    api_key = forms.CharField(widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 10, 'cols': 6}),
                              required=False,
                              )
    merchant_id = forms.CharField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr),
                                  )

    class Meta:
        model = HousePaymentGateway
        fields = [
            'gateway_type',
            'merchant_id',
            'api_key',
            'is_active',
            'is_sandbox',
        ]

        widgets = {
            'api_key': forms.Textarea(attrs={'rows': 8}),
        }


class UnitForm(forms.ModelForm):
    unit = forms.CharField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr0),
                           label='شماره واحد')
    owner_bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=False,
        label=' حساب بانکی جهت واریز شارژ',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
                # 'data-placeholder': 'واحد / مالک یا مستاجر را انتخاب کنید1'
            }
        )
    )
    renter_bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=False,
        label=' حساب بانکی جهت واریز شارژ',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
                # 'data-placeholder': 'واحد / مالک یا مستاجر را انتخاب کنید1'
            }
        )
    )
    unit_phone = forms.CharField(error_messages=error_message,
                                 max_length=8,
                                 min_length=8,
                                 required=False, widget=forms.TextInput(attrs=attr0),
                                 label='شماره تلفن واحد')
    floor_number = forms.IntegerField(error_messages=error_message, required=True,
                                      widget=forms.NumberInput(attrs=attr0),
                                      label='شماره طبقه')
    area = forms.IntegerField(error_messages=error_message, required=True,
                              widget=forms.NumberInput(attrs=attr0),
                              label='متراژ')
    bedrooms_count = forms.ChoiceField(error_messages=error_message, choices=BEDROOMS_COUNT_CHOICES, required=True,
                                       widget=forms.Select(attrs=attr0),
                                       label='تعداد خواب')

    parking_place = forms.ChoiceField(error_messages=error_message, choices=PARKING_PLACE_CHOICES, required=False,
                                      widget=forms.Select(attrs=attr0),
                                      label='موقعیت پارکینگ اصلی')
    extra_parking_first = forms.CharField(error_messages=error_message, required=False,
                                          widget=forms.TextInput(attrs=attr0),
                                          label=' پارکینگ اضافه اول')
    extra_parking_second = forms.CharField(error_messages=error_message, required=False,
                                           widget=forms.TextInput(attrs=attr0),
                                           label=' پارکینگ اضافه دوم')

    parking_number = forms.CharField(
        error_messages=error_message,
        required=False,
        widget=forms.TextInput(attrs=attr0),
        label='شماره پارکینگ'
    )
    owner_transaction_no = forms.IntegerField(error_messages=error_message,
                                              widget=forms.TextInput(attrs=attr),
                                              required=False, min_value=0,
                                              label='کد پیگیری')
    owner_payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    renter_transaction_no = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    renter_payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    # parking_count = forms.ChoiceField(error_messages=error_message, choices=PARKING_COUNT_CHOICES, required=True,
    #                                   widget=forms.Select(attrs=attr0),
    #                                   label='تعداد پارکینگ')
    unit_details = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'rows': 8}), required=False,
                                   label='توضیحات واحد')
    owner_name = forms.CharField(error_messages=error_message, required=True, widget=forms.TextInput(attrs=attr),
                                 label='نام ')
    owner_mobile = forms.CharField(error_messages=error_message,
                                   max_length=11,
                                   min_length=11,
                                   required=True, widget=forms.TextInput(attrs=attr),
                                   label='شماره تلفن ')
    owner_national_code = forms.CharField(error_messages=error_message, required=True,
                                          max_length=10,
                                          min_length=10,
                                          widget=forms.TextInput(attrs=attr),
                                          label='کد ملی ')
    owner_people_count = forms.CharField(error_messages=error_message, required=True,
                                         widget=forms.TextInput(attrs=attr),
                                         label='تعداد نفرات مالک')
    purchase_date = JalaliDateField(error_messages=error_message, widget=AdminJalaliDateWidget(attrs=attr),
                                    required=True,
                                    label='تاریخ خرید')

    status_residence = forms.ChoiceField(error_messages=error_message, choices=RESIDENCE_STATUS_CHOICES, required=True,
                                         widget=forms.Select(attrs=attr0),
                                         label='وضعیت سکونت')
    is_renter = forms.TypedChoiceField(
        choices=((True, 'بله'), (False, 'خیر')),
        coerce=lambda x: x == 'True',
        widget=forms.Select(attrs={'class': 'form-control'}),
        label='واحد دارای مستاجر است؟',
        initial=False
    )
    owner_details = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'rows': 8}), required=False,
                                    label='توضیحات مالک')
    renter_name = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                  label='نام مستاجر')
    renter_mobile = forms.CharField(error_messages=error_message,
                                    required=False,
                                    max_length=11,
                                    min_length=11,
                                    widget=forms.TextInput(attrs=attr),
                                    label='شماره تلفن مستاجر')
    renter_national_code = forms.CharField(error_messages=error_message, required=False,
                                           max_length=10,
                                           min_length=10,
                                           widget=forms.TextInput(attrs=attr), label='کد ملی مستاجر')
    renter_people_count = forms.CharField(error_messages=error_message, required=False,
                                          widget=forms.TextInput(attrs=attr),
                                          label='تعداد نفرات')

    start_date = JalaliDateField(
        label='تاریخ شروع اجاره',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    end_date = JalaliDateField(
        label='تاریخ پایان اجاره',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    contract_number = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                      label='شماره قرارداد')
    estate_name = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                  label='نام اجاره دهنده')
    first_charge_owner = forms.CharField(error_messages=error_message, required=False,
                                         widget=forms.TextInput(attrs=attr),
                                         label='شارژ اولیه مالک', initial=0)
    first_charge_renter = forms.CharField(error_messages=error_message, required=False,
                                          widget=forms.TextInput(attrs=attr),
                                          label='شارژ اولیه مستاجر', initial=0)
    renter_details = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'rows': 8}), required=False,
                                     label='توضیحات مستاجر')
    is_active = forms.BooleanField(required=False, initial=True, label='فعال/غیرفعال نمودن')
    owner_password = forms.CharField(
        required=False,
        label='رمز عبور مالک',
        widget=forms.PasswordInput(attrs=attr),
    )

    confirm_owner_password = forms.CharField(
        required=False,
        label='تایید رمز عبور مالک',
        widget=forms.PasswordInput(attrs=attr),
    )

    renter_password = forms.CharField(
        required=False,
        label='رمز عبور مستاجر',
        widget=forms.PasswordInput(attrs=attr),
    )

    confirm_renter_password = forms.CharField(
        required=False,
        label='تایید رمز عبور مستاجر',
        widget=forms.PasswordInput(attrs=attr),
    )

    def clean(self):
        cleaned_data = super().clean()
        owner_password = cleaned_data.get("owner_password")
        confirm_owner_password = cleaned_data.get("confirm_owner_password")

        renter_password = cleaned_data.get("renter_password")
        confirm_renter_password = cleaned_data.get("confirm_renter_password")

        owner_mobile = cleaned_data.get('owner_mobile')
        renter_mobile = cleaned_data.get('renter_mobile')

        instance = getattr(self, 'instance', None)

        # ------------------------
        # OWNER MOBILE CHECK
        # ------------------------
        if owner_mobile:
            qs = User.objects.filter(mobile=owner_mobile)

            if instance and instance.pk and instance.user:
                qs = qs.exclude(pk=instance.user.pk)

            # مدیر ساکن ساختمان است
            if (
                    self.current_user
                    and self.current_user.mobile == owner_mobile
                    and self.current_user.is_resident
            ):
                qs = qs.exclude(pk=self.current_user.pk)

            if qs.exists():
                self.add_error(
                    'owner_mobile',
                    'این شماره موبایل قبلاً ثبت شده است.'
                )

        # ------------------------
        # RENTER MOBILE CHECK
        # ------------------------
        if renter_mobile:
            qs = User.objects.filter(mobile=renter_mobile)

            if instance and instance.pk:
                active_renter = instance.get_active_renter()
                if active_renter:
                    qs = qs.exclude(pk=active_renter.user.pk)

            if qs.exists():
                self.add_error('renter_mobile', 'این شماره موبایل قبلاً ثبت شده است.')

        if owner_password or confirm_owner_password:
            if owner_password != confirm_owner_password:
                self.add_error('confirm_owner_password', "رمز عبور مالک یکسان نیست.")

        if renter_password or confirm_renter_password:
            if renter_password != confirm_renter_password:
                self.add_error('confirm_renter_password', "رمز عبور مستاجر یکسان نیست.")

        is_renter = cleaned_data.get('is_renter')

        if cleaned_data.get('start_date') and cleaned_data.get('end_date'):
            start_date = cleaned_data.get('start_date')
            end_date = cleaned_data.get('end_date')

            if start_date > end_date:
                self.add_error('start_date', 'تاریخ شروع اجاره نباید از تاریخ پایان بزرگتر باشد.')

        if str(is_renter).lower() == 'true':
            required_fields_if_rented = [
                'renter_name', 'renter_mobile', 'renter_national_code',
                'renter_people_count', 'start_date', 'end_date',
            ]
            for field in required_fields_if_rented:
                if not cleaned_data.get(field):
                    self.add_error(field, 'این فیلد الزامی است.')

        # ------------------------------
        # بررسی تاریخ افتتاح حساب مالک
        # ------------------------------
        owner_bank = cleaned_data.get('owner_bank')
        owner_payment_date = cleaned_data.get('owner_payment_date')
        if owner_payment_date:
            if owner_payment_date > datetime.date.today():
                self.add_error(
                    "renter_payment_date",
                    "تاریخ پرداخت نباید از تاریخ امروز بیشتر باشد."
                )

        if owner_bank and owner_payment_date:
            try:
                validate_bank_transaction_date(
                    owner_bank,
                    owner_payment_date
                )
            except ValidationError as e:
                self.add_error('owner_payment_date', e.message)

        # ------------------------------
        # بررسی تاریخ افتتاح حساب مستاجر
        # ------------------------------
        renter_bank = cleaned_data.get('renter_bank')
        renter_payment_date = cleaned_data.get('renter_payment_date')

        if renter_payment_date:
            if renter_payment_date > datetime.date.today():
                self.add_error(
                    "renter_payment_date",
                    "تاریخ پرداخت نباید از تاریخ امروز بیشتر باشد."
                )

        if renter_bank and renter_payment_date:
            try:
                validate_bank_transaction_date(
                    renter_bank,
                    renter_payment_date
                )
            except ValidationError as e:
                self.add_error('renter_payment_date', e.message)
        return cleaned_data

    class Meta:
        model = Unit
        fields = ['unit', 'floor_number', 'area', 'unit_details',
                  'bedrooms_count', 'parking_place', 'owner_name', 'owner_mobile',
                  'owner_national_code', 'unit_phone', 'owner_details',
                  'parking_number', 'status_residence', 'purchase_date', 'renter_name',
                  'renter_national_code', 'renter_details', 'extra_parking_first', 'extra_parking_second',
                  'renter_mobile', 'is_renter', 'owner_people_count', 'renter_bank',
                  'renter_people_count', 'start_date', 'end_date', 'first_charge_owner', 'first_charge_renter',
                  'contract_number', 'owner_bank', 'owner_transaction_no', 'owner_payment_date', 'renter_payment_date',
                  'estate_name', 'is_active', 'owner_password', 'confirm_owner_password',
                  'renter_password', 'confirm_renter_password', 'renter_transaction_no']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        self.current_user = user
        super().__init__(*args, **kwargs)

        # بانک‌ها
        if user:
            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['owner_bank'].queryset = banks
            self.fields['renter_bank'].queryset = banks
            self.fields['owner_bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")
            self.fields['renter_bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")

        # مقداردهی مستاجر از instance
        if self.instance.pk:
            active_renter = self.instance.get_active_renter()
            if active_renter:
                self.fields['renter_name'].initial = active_renter.renter_name
                self.fields['renter_mobile'].initial = active_renter.renter_mobile
                self.fields['renter_national_code'].initial = active_renter.renter_national_code
                self.fields['renter_people_count'].initial = active_renter.renter_people_count
                self.fields['renter_bank'].initial = active_renter.renter_bank
                self.fields['start_date'].initial = active_renter.start_date
                self.fields['end_date'].initial = active_renter.end_date
                self.fields['contract_number'].initial = active_renter.contract_number
                self.fields['estate_name'].initial = active_renter.estate_name
                self.fields['first_charge_renter'].initial = active_renter.first_charge_renter
                self.fields['renter_details'].initial = active_renter.renter_details
                self.fields['renter_payment_date'].initial = active_renter.renter_payment_date
                self.fields['renter_transaction_no'].initial = active_renter.renter_transaction_no
                self.fields['is_renter'].initial = True
            else:
                self.fields['is_renter'].initial = False

    def save(self, commit=True):
        instance = super().save(commit=False)

        is_renter = self.cleaned_data.get('is_renter')

        if not is_renter:
            # Owner is resident, clear renter fields
            instance.renter_name = ''
            instance.renter_mobile = ''
            instance.renter_national_code = ''
            instance.renter_people_count = ''
            instance.start_date = None
            instance.end_date = None
            instance.contract_number = ''
            instance.first_charge_renter = None or 0
            instance.renter_details = ''
            instance.renter_transaction_no = None
            instance.renter_payment_date = None

            # Set people_count from owner's info
            instance.people_count = int(self.cleaned_data.get('owner_people_count')) or 0
        else:
            # We'll assign renter_people_count later
            instance.people_count = 0  # default for now

        if commit:
            instance.save()  # ✅ Save first so instance has a PK

            # ✅ Now you can access related renters
            if not is_renter:
                active_renter = instance.renters.filter(renter_is_active=True).last()
                if active_renter:
                    instance.people_count = active_renter.renter_people_count or 0
                    instance.save(update_fields=['people_count'])  # update only this field

        return instance


class RenterAddForm(forms.ModelForm):
    renter_bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=False,
        label=' حساب بانکی جهت واریز شارژ',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
                # 'data-placeholder': 'واحد / مالک یا مستاجر را انتخاب کنید1'
            }
        )
    )
    renter_name = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                  label='نام مستاجر')
    renter_mobile = forms.CharField(error_messages=error_message,
                                    required=False,
                                    max_length=11,
                                    min_length=11,
                                    widget=forms.TextInput(attrs=attr),
                                    label='شماره تلفن مستاجر')
    renter_national_code = forms.CharField(error_messages=error_message, required=False,
                                           max_length=10,
                                           min_length=10,
                                           widget=forms.TextInput(attrs=attr), label='کد ملی مستاجر')
    renter_people_count = forms.CharField(error_messages=error_message, required=False,
                                          widget=forms.TextInput(attrs=attr),
                                          label='تعداد نفرات')

    start_date = JalaliDateField(
        label='تاریخ شروع اجاره',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    end_date = JalaliDateField(
        label='تاریخ پایان اجاره',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    contract_number = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                      label='شماره قرارداد')
    estate_name = forms.CharField(error_messages=error_message, required=False, widget=forms.TextInput(attrs=attr),
                                  label='نام اجاره دهنده')
    first_charge_owner = forms.CharField(error_messages=error_message, required=False,
                                         widget=forms.TextInput(attrs=attr),
                                         label='شارژ اولیه مالک', initial=0)
    first_charge_renter = forms.CharField(error_messages=error_message, required=False,
                                          widget=forms.TextInput(attrs=attr),
                                          label='شارژ اولیه مستاجر', initial=0)
    renter_details = forms.CharField(widget=forms.TextInput(attrs={'class': 'form-control', 'rows': 8}), required=False,
                                     label='توضیحات مستاجر')

    renter_is_active = forms.BooleanField(required=False, initial=True, label='فعال')
    renter_transaction_no = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    renter_payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    # mobile = forms.CharField(
    #     required=True,
    #     max_length=11,
    #     min_length=11,
    #     error_messages=error_message,
    #     label='نام کاربری',
    #     widget=forms.TextInput(attrs=attr)
    # )
    password = forms.CharField(
        required=False,
        label='رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )
    confirm_password = forms.CharField(
        required=False,
        label='تایید رمز عبور',
        widget=forms.PasswordInput(attrs=attr),
        help_text='رمز عبور باید شامل اعداد و حروف باشد'
    )

    class Meta:
        model = Renter
        fields = [
            'renter_name',
            'renter_mobile',
            'renter_national_code',
            'renter_people_count',
            'start_date',
            'end_date',
            'contract_number',
            'estate_name',
            'first_charge_renter',
            'renter_details',
            'renter_is_active',
            'renter_transaction_no',
            'renter_payment_date',
            'renter_bank',
            'password',
            'confirm_password'
        ]

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        renter_mobile = cleaned_data.get('renter_mobile')

        if renter_mobile:
            if User.objects.filter(mobile=renter_mobile).exists():
                self.add_error('renter_mobile', 'این شماره موبایل قبلاً ثبت شده است.')

        if password or confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "کلمه عبور و تکرار آن باید یکسان باشند.")

            # -------------------------
            # بررسی تاریخ پرداخت مستاجر
            # -------------------------
        renter_bank = cleaned_data.get('renter_bank')
        renter_payment_date = cleaned_data.get('renter_payment_date')

        if renter_bank and renter_payment_date:
            validate_bank_transaction_date(renter_bank, renter_payment_date)

        if renter_payment_date:
            if renter_payment_date > datetime.date.today():
                self.add_error(
                    "renter_payment_date",
                    "تاریخ پرداخت نباید از تاریخ امروز بیشتر باشد."
                )

        # -------------------------
        # بررسی تاریخ اجاره (اختیاری ولی پیشنهاد میشه)
        # -------------------------
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date:
            if start_date > end_date:
                self.add_error('start_date', 'تاریخ شروع نباید بعد از پایان باشد.')

            if renter_bank:
                validate_bank_transaction_date(renter_bank, start_date)

        return cleaned_data

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['renter_bank'].queryset = banks
            self.fields['renter_bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")


# ======================== Expense Forms =============================

class ExpenseForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.none(),
        widget=forms.Select(attrs=attr),
        empty_label="یک گروه انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='موضوع هزینه'
    )
    amount = forms.CharField(error_messages=error_message, max_length=20, required=True,
                             widget=forms.TextInput(attrs=attr),
                             label='مبلغ')
    description = forms.CharField(error_messages=error_message, widget=forms.TextInput(attrs=attr), required=True,
                                  label='شرح سند')
    date = JalaliDateField(
        label='تاریخ ثبت سند',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    doc_no = forms.CharField(error_messages=error_message, max_length=10, widget=forms.TextInput(attrs=attr),
                             required=True,
                             label='شماره فاکتور')
    document = forms.FileField(
        required=False,
        error_messages=error_message,
        widget=forms.ClearableFileInput(attrs=attr),
        label='تصویر سند'
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = Expense
        fields = ['category', 'amount', 'date', 'description', 'doc_no', 'details', 'document']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        default_categories = ['هزینه آب', 'هزینه برق', 'هزینه گاز', 'هزینه بیمه', 'هزینه حقوق و دستمزد']

        if user:
            for title in default_categories:
                ExpenseCategory.objects.get_or_create(
                    title=title,
                    is_default=True,
                    user=user,
                    defaults={'is_active': True}
                )

            self.fields['category'].queryset = ExpenseCategory.objects.filter(
                is_active=True,
                user=user
            )

    def clean_amount(self):
        """
        تبدیل مبلغ به عدد + حذف کاما
        """
        amount = self.cleaned_data.get('amount')
        try:
            amount = int(str(amount).replace(',', ''))
            if amount <= 0:
                raise ValidationError('مبلغ باید بزرگتر از صفر باشد')
            return amount
        except ValueError:
            raise ValidationError('مبلغ وارد شده معتبر نیست')

    def clean_date(self):
        """
        اگر تاریخ وارد نشده بود → امروز
        """
        date = self.cleaned_data.get('date')
        if not date:
            return timezone.now().date()
        return date


class ExpensePayForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        label='دریافت کننده توسط ساکنین',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
            }
        )
    )
    receiver_name = forms.CharField(
        max_length=200, required=False, label='دریافت کننده غیر از ساکنین ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Expense
        fields = ['bank', 'transaction_reference', 'payment_date', 'receiver_name', 'unit']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))
            self.fields['unit'].queryset = Unit.objects.filter(
                is_active=True,
                user__in=managed_users
            ).select_related('user').order_by('unit')

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")

            def get_unit_label(obj):
                renter = obj.get_active_renter()
                if renter and getattr(renter, 'renter_name', None):
                    return f"واحد {obj.unit} - {renter.renter_name}"
                elif obj.owner_name:
                    return f"واحد {obj.unit} - {obj.owner_name}"
                else:
                    return f"واحد {obj.unit} - نام نامشخص"

            self.fields['unit'].label_from_instance = get_unit_label

    def clean(self):
        cleaned_data = super().clean()
        unit = cleaned_data.get('unit')
        payer_name = cleaned_data.get('receiver_name')

        if not unit and not payer_name:
            raise forms.ValidationError("لطفا یا واحد را انتخاب کنید یا نام دریافت کننده را وارد نمایید.")

        return cleaned_data

    def clean_payment_date(self):
        date = self.cleaned_data.get('payment_date')

        bank = self.cleaned_data.get('bank')
        payment_date = self.cleaned_data.get('payment_date')

        if bank and payment_date:
            validate_bank_transaction_date(bank, payment_date)

        if date:
            # تاریخ امروز به شمسی
            today = jdatetime.date.today()
            if date > today:
                raise ValidationError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")
        return date


class ExpenseCategoryForm(forms.ModelForm):
    title = forms.CharField(error_messages=error_message, widget=forms.TextInput(attrs=attr), required=True,
                            label='موضوع')
    is_active = forms.BooleanField(required=False, initial=True, label='فعال/غیرفعال')

    class Meta:
        model = ExpenseCategory
        fields = ['title', 'is_active']


class SearchExpenseForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all(), required=False, label='گروه هزینه'
    )
    description = forms.CharField(
        max_length=200, required=False, label='شرح هزینه', widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    amount = forms.IntegerField(
        required=False, label=' مبلغ', widget=forms.TextInput(attrs=attr)
    )
    details = forms.CharField(
        required=False, label=' توضیحات', widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    date_from = JalaliDateField(
        label='از تاریخ',
        widget=AdminJalaliDateWidget(),
        error_messages=error_message, required=True
    )
    date_to = JalaliDateField(
        required=False,
        label='تا تاریخ',
        widget=AdminJalaliDateWidget()
    )
    doc_no = forms.IntegerField(
        required=False, label='شماره سند', widget=forms.TextInput(attrs={'class': 'form-control'})
    )


# =============================== Income Forms ===================================
class IncomeForm(forms.ModelForm):
    category = forms.ModelChoiceField(
        queryset=IncomeCategory.objects.none(),
        widget=forms.Select(attrs=attr),
        empty_label="یک گروه انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='موضوع درآمد'
    )
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        label='پرداخت کننده توسط ساکنین',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
            }
        )
    )
    payer_name = forms.CharField(
        max_length=200, required=False, label='پرداخت کننده غیر از ساکنین ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    amount = forms.CharField(error_messages=error_message, max_length=20, required=True,
                             widget=forms.TextInput(attrs=attr),
                             label='مبلغ')
    description = forms.CharField(error_messages=error_message, widget=forms.TextInput(attrs=attr), required=True,
                                  label='شرح سند')
    doc_date = JalaliDateField(
        label='تاریخ ثبت سند',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    doc_number = forms.CharField(error_messages=error_message, max_length=10, widget=forms.TextInput(attrs=attr),
                                 required=True,
                                 label='شماره فاکتور')
    document = forms.FileField(
        required=False,
        error_messages=error_message,
        widget=forms.ClearableFileInput(attrs=attr),
        label='تصویر سند'
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = Income
        fields = ['category', 'amount', 'doc_date', 'description', 'doc_number', 'details',
                  'document']

    def clean_amount(self):
        """
        تبدیل مبلغ به عدد + حذف کاما
        """
        amount = self.cleaned_data.get('amount')
        try:
            amount = int(str(amount).replace(',', ''))
            if amount <= 0:
                raise ValidationError('مبلغ باید بزرگتر از صفر باشد')
            return amount
        except ValueError:
            raise ValidationError('مبلغ وارد شده معتبر نیست')

    def clean_date(self):
        """
        اگر تاریخ وارد نشده بود → امروز
        """
        doc_date = self.cleaned_data.get('doc_date')
        if not doc_date:
            return timezone.now().date()
        return doc_date

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            self.fields['category'].queryset = IncomeCategory.objects.filter(is_active=True, user=user)


class IncomePayForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        label='پرداخت کننده توسط ساکنین',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
            }
        )
    )
    payer_name = forms.CharField(
        max_length=200, required=False, label='پرداخت کننده غیر از ساکنین ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Income
        fields = ['bank', 'transaction_reference', 'payment_date', 'payer_name', 'unit']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))
            self.fields['unit'].queryset = Unit.objects.filter(
                is_active=True,
                user__in=managed_users
            ).select_related('user').order_by('unit')

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")

            def get_unit_label(obj):
                renter = obj.get_active_renter()
                if renter and getattr(renter, 'renter_name', None):
                    return f"واحد {obj.unit} - {renter.renter_name}"
                elif obj.owner_name:
                    return f"واحد {obj.unit} - {obj.owner_name}"
                else:
                    return f"واحد {obj.unit} - نام نامشخص"

            self.fields['unit'].label_from_instance = get_unit_label

    def clean(self):
        cleaned_data = super().clean()
        unit = cleaned_data.get('unit')
        payer_name = cleaned_data.get('payer_name')

        if not unit and not payer_name:
            raise forms.ValidationError("لطفا یا واحد را انتخاب کنید یا نام پرداخت کننده را وارد نمایید.")

        return cleaned_data

    def clean_payment_date(self):
        doc_date = getattr(self.instance, "doc_date", None)
        payment_date = self.cleaned_data.get('payment_date')
        bank = self.cleaned_data.get('bank')

        if not payment_date:
            return payment_date

            # نباید قبل از تاریخ ثبت سند باشد
        if doc_date and payment_date < doc_date:
            raise ValidationError("تاریخ پرداخت نمی‌تواند قبل از تاریخ ثبت سند باشد.")

        # 1️⃣ بررسی تاریخ آینده
        today = jdatetime.date.today()
        if payment_date > today:
            raise ValidationError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")

        # 2️⃣ بررسی تاریخ افتتاح بانک
        if bank:
            try:
                validate_bank_transaction_date(bank, payment_date)
            except ValidationError as e:
                raise ValidationError(e.message)

        return payment_date


class IncomeCategoryForm(forms.ModelForm):
    subject = forms.CharField(error_messages=error_message, widget=forms.TextInput(attrs=attr), required=True,
                              label='موضوع درآمد')
    is_active = forms.BooleanField(required=False, initial=True, label='فعال/غیرفعال')

    class Meta:
        model = IncomeCategory
        fields = ['subject', 'is_active']


class SearchIncomeForm(forms.Form):
    category = forms.ModelChoiceField(
        queryset=ExpenseCategory.objects.all(), required=False, label='گروه درآمد'
    )
    description = forms.CharField(
        max_length=200, required=False, label='شرح درآمد', widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    amount = forms.IntegerField(
        required=False, label=' مبلغ', widget=forms.TextInput(attrs=attr)
    )
    details = forms.CharField(
        required=False, label=' توضیحات', widget=forms.TextInput(attrs={'class': 'form-control'})
    )
    date_from = JalaliDateField(
        label='از تاریخ',
        widget=AdminJalaliDateWidget(),
        error_messages=error_message, required=False
    )
    date_to = JalaliDateField(
        required=False,
        label='تا تاریخ',
        widget=AdminJalaliDateWidget()
    )
    doc_number = forms.IntegerField(
        required=False, label='شماره سند', widget=forms.TextInput(attrs={'class': 'form-control'})
    )


# ================================ Receive Forms ======================

class ReceiveMoneyForm(forms.ModelForm):
    amount = forms.IntegerField(
        required=True, label='مبلغ',
        widget=forms.NumberInput(attrs={'class': 'form-control form-control-sm'})
    )

    description = forms.CharField(
        required=True, label='شرح سند',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    doc_date = JalaliDateField(
        label='تاریخ ثبت سند',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        required=False
    )

    doc_number = forms.CharField(
        max_length=10, required=True, label='شماره سند',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    document = forms.FileField(
        required=False, label='تصویر سند',
        widget=forms.ClearableFileInput(attrs={'class': 'form-control'})
    )

    details = forms.CharField(
        required=False, label='توضیحات',
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3})
    )

    class Meta:
        model = ReceiveMoney
        fields = [
            'amount', 'doc_date', 'description', 'doc_number',
            'details', 'document',
        ]


class ReceivePayForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        label='پرداخت کننده توسط ساکنین',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
            }
        )
    )
    payer_name = forms.CharField(
        max_length=200, required=False, label='پرداخت کننده غیر از ساکنین ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = ReceiveMoney
        fields = ['bank', 'transaction_reference', 'payment_date', 'payer_name', 'unit']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))
            self.fields['unit'].queryset = Unit.objects.filter(
                is_active=True,
                user__in=managed_users
            ).select_related('user').order_by('unit')

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")

            def get_unit_label(obj):
                renter = obj.get_active_renter()
                if renter and getattr(renter, 'renter_name', None):
                    return f"واحد {obj.unit} - {renter.renter_name}"
                elif obj.owner_name:
                    return f"واحد {obj.unit} - {obj.owner_name}"
                else:
                    return f"واحد {obj.unit} - نام نامشخص"

            self.fields['unit'].label_from_instance = get_unit_label

    def clean_payment_date(self):
        doc_date = getattr(self.instance, "doc_date", None)

        payment_date = self.cleaned_data.get('payment_date')
        bank = self.cleaned_data.get('bank')

        if not payment_date:
            return payment_date

        # تبدیل تاریخ سند به جلالی
        if doc_date:
            doc_date = jdatetime.date.fromgregorian(date=doc_date)

            if payment_date < doc_date:
                raise ValidationError(
                    "تاریخ پرداخت نمی‌تواند قبل از تاریخ ثبت سند باشد."
                )

        # بررسی تاریخ آینده
        today = jdatetime.date.today()
        if payment_date > today:
            raise ValidationError(
                "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
            )

        # بررسی تاریخ افتتاح حساب بانکی
        if bank:
            try:
                validate_bank_transaction_date(bank, payment_date)
            except ValidationError as e:
                raise ValidationError(e.message)

        return payment_date

    def clean(self):
        cleaned_data = super().clean()

        unit = cleaned_data.get('unit')
        payer_name = cleaned_data.get('payer_name')

        if not unit and not payer_name:
            raise ValidationError(
                "لطفا یا واحد را انتخاب کنید یا نام پرداخت کننده را وارد نمایید."
            )

        return cleaned_data


# =========================================================
class PayerMoneyForm(forms.ModelForm):
    receiver_name = forms.CharField(
        max_length=200, required=False, label=' دریافت کننده',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    amount = forms.IntegerField(error_messages=error_message, required=True,
                                widget=forms.NumberInput(attrs=attr),
                                label='مبلغ')
    description = forms.CharField(error_messages=error_message, widget=forms.TextInput(attrs=attr), required=True,
                                  label='شرح سند')
    document_date = JalaliDateField(
        label='تاریخ ثبت سند',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    document_number = forms.CharField(error_messages=error_message, max_length=10, widget=forms.TextInput(attrs=attr),
                                      required=True,
                                      label='شماره سند')
    document = forms.FileField(
        required=False,
        error_messages=error_message,
        widget=forms.ClearableFileInput(attrs=attr),
        label='تصویر سند'
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = PayMoney
        fields = ['amount', 'document_date', 'description', 'document_number',
                  'details', 'document']


class PayMoneyForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')
    unit = forms.ModelChoiceField(
        queryset=Unit.objects.none(),
        required=False,
        label='دریافت کننده توسط ساکنین',
        widget=forms.Select(
            attrs={
                'class': 'form-control-sm ',
                'style': 'width:100%',
            }
        )
    )
    receiver_name = forms.CharField(
        max_length=200, required=False, label='دریافت کننده غیر از ساکنین ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = PayMoney
        fields = ['bank', 'transaction_reference', 'payment_date', 'receiver_name', 'unit']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))
            self.fields['unit'].queryset = Unit.objects.filter(
                is_active=True,
                user__in=managed_users
            ).select_related('user').order_by('unit')

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
                " (پیش‌فرض)" if obj.is_default else "")

            def get_unit_label(obj):
                renter = obj.get_active_renter()
                if renter and getattr(renter, 'renter_name', None):
                    return f"واحد {obj.unit} - {renter.renter_name}"
                elif obj.owner_name:
                    return f"واحد {obj.unit} - {obj.owner_name}"
                else:
                    return f"واحد {obj.unit} - نام نامشخص"

            self.fields['unit'].label_from_instance = get_unit_label

    def clean_payment_date(self):
        doc_date = getattr(self.instance, "document_date", None)

        payment_date = self.cleaned_data.get('payment_date')
        bank = self.cleaned_data.get('bank')

        if not payment_date:
            return payment_date

        # تبدیل تاریخ سند به جلالی
        if doc_date:
            doc_date = jdatetime.date.fromgregorian(date=doc_date)

            if payment_date < doc_date:
                raise ValidationError(
                    "تاریخ پرداخت نمی‌تواند قبل از تاریخ ثبت سند باشد."
                )

        # بررسی تاریخ آینده
        today = jdatetime.date.today()
        if payment_date > today:
            raise ValidationError(
                "تاریخ پرداخت نمی‌تواند بعد از امروز باشد."
            )

        # بررسی تاریخ افتتاح حساب بانکی
        if bank:
            try:
                validate_bank_transaction_date(bank, payment_date)
            except ValidationError as e:
                raise ValidationError(e.message)

        return payment_date

    def clean(self):
        cleaned_data = super().clean()

        unit = cleaned_data.get('unit')
        receiver_name = cleaned_data.get('receiver_name')

        if not unit and not receiver_name:
            raise ValidationError(
                "لطفا یا واحد را انتخاب کنید یا نام دریافت کننده را وارد نمایید."
            )

        return cleaned_data


# --------------------------------------------------------------------------


PROPERTY_CHOICES = {
    '': '--- انتخاب کنید ---', 'عدد': 'عدد', 'دستگاه': 'دستگاه', 'تخته': 'تخته', 'کپسول': 'کپسول',
}


class PropertyForm(forms.ModelForm):
    property_name = forms.CharField(
        max_length=200, required=True, label='نام اموال', widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    property_unit = forms.ChoiceField(error_messages=error_message, required=True, choices=PROPERTY_CHOICES,
                                      widget=forms.Select(attrs=attr3),
                                      label='واحد')
    document_number = forms.CharField(error_messages=error_message, max_length=10, widget=forms.TextInput(attrs=attr),
                                      required=True,
                                      label='شماره فاکتور')
    count = forms.CharField(error_messages=error_message, max_length=10, widget=forms.NumberInput(attrs=attr),
                            required=True,
                            label='تعداد')
    property_location = forms.CharField(error_messages=error_message,
                                        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                                        required=True,
                                        label='موقعیت')
    property_purchase_date = JalaliDateField(
        label='تاریخ خرید',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    property_code = forms.CharField(error_messages=error_message, max_length=500,
                                    widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                                    required=True,
                                    label='کد اموال')
    property_price = forms.IntegerField(error_messages=error_message, widget=forms.NumberInput(attrs=attr),
                                        required=True,
                                        label='ارزش')
    document = forms.FileField(
        required=False,
        error_messages=error_message,
        widget=forms.ClearableFileInput(attrs=attr),
        label='تصویر اموال'
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    company_name = forms.CharField(
        max_length=200, required=False, label=' نام فروشنده',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Property
        fields = ['property_name', 'property_code', 'property_unit', 'property_price', 'property_location',
                  'property_purchase_date', 'details', 'document', 'company_name',
                  'document_number', 'count']

    # def __init__(self, *args, **kwargs):
    #     user = kwargs.pop('user', None)
    #     super().__init__(*args, **kwargs)
    #
    #     if user:
    #         # بانک‌ها
    #         banks = Bank.objects.filter(is_active=True, user=user)
    #         self.fields['bank'].queryset = banks
    #         # default_bank = banks.filter(is_default=True).first()
    #         # if default_bank:
    #         #     self.fields['bank'].initial = default_bank


class PropertyPayForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=True, min_value=0,
                                               label='کد پیگیری')

    receiver_name = forms.CharField(
        max_length=200, required=True, label='دریافت کننده ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = PayMoney
        fields = ['bank', 'transaction_reference', 'payment_date', 'receiver_name']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            # self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
            #     " (پیش‌فرض)" if obj.is_default else "")

    def clean(self):
        cleaned_data = super().clean()

        payment_date = cleaned_data.get('payment_date')
        property_purchase_date = getattr(self.instance, "property_purchase_date", None)
        bank = self.cleaned_data.get('bank')

        # تبدیل میلادی به جلالی
        if property_purchase_date:
            property_purchase_date = jdatetime.date.fromgregorian(date=property_purchase_date)

        if payment_date:
            today = jdatetime.date.today()

            # نباید بعد از امروز باشد
            if payment_date > today:
                raise ValidationError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")

            # نباید قبل از تاریخ ثبت سند باشد
            if property_purchase_date and payment_date < property_purchase_date:
                raise ValidationError("تاریخ پرداخت نمی‌تواند قبل از تاریخ ثبت سند باشد.")

            # بررسی تاریخ افتتاح حساب بانکی
        if bank:
            try:
                validate_bank_transaction_date(bank, payment_date)
            except ValidationError as e:
                raise ValidationError(e.message)

        return cleaned_data


# =========================================================


MAINTENANCE_CHOICES = {
    ' ': '--- انتخاب کنید ---', 'تکمیل شده': 'تکمیل شده', 'در حال انجام': 'در حال انجام',
}


class MaintenanceForm(forms.ModelForm):
    maintenance_description = forms.CharField(
        max_length=200, required=True, label='شرح کار', widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    maintenance_start_date = JalaliDateField(
        label='تاریخ شروع',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    maintenance_end_date = JalaliDateField(
        label='تاریخ پایان',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    expert_name = forms.CharField(
        max_length=200, required=True, label='نام کارشناس ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    maintenance_price = forms.CharField(error_messages=error_message, max_length=20, widget=forms.TextInput(attrs=attr),
                                        required=True,
                                        label='اجرت و دستمزد')
    service_company = forms.CharField(error_messages=error_message, max_length=100,
                                      widget=forms.TextInput(attrs=attr),
                                      required=True,
                                      label='شرکت خدماتی')
    maintenance_document_no = forms.CharField(error_messages=error_message, max_length=20,
                                              widget=forms.TextInput(attrs=attr),
                                              required=True,
                                              label='شماره فاکتور')
    maintenance_status = forms.ChoiceField(error_messages=error_message, required=True, choices=MAINTENANCE_CHOICES,
                                           widget=forms.Select(attrs=attr3),
                                           label='آخرین وضعیت')
    document = forms.FileField(
        required=False,
        error_messages=error_message,
        widget=forms.ClearableFileInput(attrs=attr),
        label='تصویر سند'
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = Maintenance
        fields = ['maintenance_description', 'maintenance_start_date', 'maintenance_end_date', 'maintenance_price',
                  'maintenance_status', 'service_company', 'details', 'document', 'maintenance_document_no',
                  'expert_name'
                  ]


class MaintenancePayForm(forms.ModelForm):
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره حساب را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='شماره حساب بانکی'
    )
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=True, min_value=0,
                                               label='کد پیگیری')

    receiver_name = forms.CharField(
        max_length=200, required=True, label='دریافت کننده ',
        widget=forms.TextInput(attrs={'class': 'form-control'})
    )

    class Meta:
        model = Maintenance
        fields = ['bank', 'transaction_reference', 'payment_date', 'receiver_name']

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            managed_users = User.objects.filter(Q(manager=user) | Q(pk=user.pk))

            banks = Bank.objects.filter(is_active=True, user=user)
            self.fields['bank'].queryset = banks

            # پیدا کردن بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # تغییر label برای نمایش "(پیش‌فرض)" کنار نام بانک
            # self.fields['bank'].label_from_instance = lambda obj: f"{obj.bank_name} - {obj.account_no}" + (
            #     " (پیش‌فرض)" if obj.is_default else "")

    def clean(self):
        cleaned_data = super().clean()

        payment_date = cleaned_data.get('payment_date')
        maintenance_start_date = getattr(self.instance, "maintenance_start_date", None)
        bank = self.cleaned_data.get('bank')

        # تبدیل میلادی به جلالی
        if maintenance_start_date:
            maintenance_start_date = jdatetime.date.fromgregorian(date=maintenance_start_date)

        if payment_date:
            today = jdatetime.date.today()

            # نباید بعد از امروز باشد
            if payment_date > today:
                raise ValidationError("تاریخ پرداخت نمی‌تواند بعد از امروز باشد.")

            # نباید قبل از تاریخ ثبت سند باشد
            if maintenance_start_date and payment_date < maintenance_start_date:
                raise ValidationError("تاریخ پرداخت نمی‌تواند قبل از تاریخ شروع باشد.")

        # بررسی تاریخ افتتاح حساب بانکی
        if bank:
            try:
                validate_bank_transaction_date(bank, payment_date)
            except ValidationError as e:
                raise ValidationError(e.message)

        return cleaned_data


# =================================================================


class SewageForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=200, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان  ')
    amount = forms.IntegerField(error_messages=error_message,
                                widget=forms.TextInput(attrs=attr),
                                required=True,
                                label='مبلغ')
    prepayment = forms.IntegerField(error_messages=error_message,
                                    widget=forms.TextInput(attrs=attr),
                                    required=False, initial=0,
                                    label='پیش پرداخت')
    installment_count = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='تعداد اقساط ')
    first_due_date = JalaliDateField(
        label='تاریخ پرداخت اولین قسط',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control m-1'}),
        error_messages=error_message, required=True
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = SewageManage
        fields = ['name', 'amount', 'prepayment', 'installment_count', 'first_due_date', 'details']

    def clean_first_due_date(self):
        deadline = self.cleaned_data.get('first_due_date')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('تاریخ سررسید نمی‌تواند قبل از امروز باشد')

        return deadline

    def clean(self):
        cleaned_data = super().clean()

        amount = cleaned_data.get('amount')
        prepayment = cleaned_data.get('prepayment') or 0

        if amount is not None and prepayment is not None:
            if prepayment > amount:
                self.add_error('prepayment', 'مبلغ پیش‌پرداخت نمی‌تواند بیشتر از هزینه کل باشد.')

        return cleaned_data


# ============================== Charge Forms ===================================

class FixChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    fix_amount = forms.IntegerField(error_messages=error_message,
                                    widget=forms.TextInput(attrs=attr),
                                    required=True,
                                    label='مبلغ شارژ به ازای هر واحد')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = FixCharge
        fields = ['name', 'fix_amount', 'details', 'civil', 'payment_deadline', 'payment_penalty_amount',
                  'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class AreaChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    area_amount = forms.IntegerField(error_messages=error_message,
                                     widget=forms.TextInput(attrs=attr),
                                     required=True,
                                     label='مبلغ شارژ به اساس متراژ')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    def clean_civil_charge(self):
        value = self.cleaned_data.get('civil')
        if value in [None, '']:  # empty string or None
            return 0
        return value

    class Meta:
        model = AreaCharge
        fields = ['name', 'area_amount', 'details', 'civil', 'payment_deadline', 'payment_penalty_amount',
                  'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class PersonChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    person_amount = forms.IntegerField(error_messages=error_message,
                                       widget=forms.TextInput(attrs=attr),
                                       required=True,
                                       label='مبلغ شارژ به ازای هر نفر')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = PersonCharge
        fields = ['name', 'person_amount', 'details', 'civil', 'payment_deadline', 'payment_penalty_amount',
                  'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class FixAreaChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    fix_charge_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=True,
                                           label=' شارژ ثابت')
    area_amount = forms.IntegerField(error_messages=error_message,
                                     widget=forms.TextInput(attrs=attr),
                                     required=True,
                                     label='مبلغ شارژ به اساس متراژ')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = FixAreaCharge
        fields = ['name', 'area_amount', 'details', 'civil', 'fix_charge_amount', 'payment_deadline',
                  'payment_penalty_amount',
                  'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class FixPersonChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    fix_charge_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=True,
                                           label=' شارژ ثابت')
    person_amount = forms.IntegerField(error_messages=error_message,
                                       widget=forms.TextInput(attrs=attr),
                                       required=True,
                                       label='مبلغ شارژ به ازای هر نفر')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = FixPersonCharge
        fields = ['name', 'person_amount', 'details', 'civil', 'fix_charge_amount', 'payment_deadline'
            , 'payment_penalty_amount', 'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class PersonAreaChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    person_amount = forms.IntegerField(error_messages=error_message,
                                       widget=forms.TextInput(attrs=attr),
                                       required=True,
                                       label='مبلغ شارژ نفر')
    area_amount = forms.IntegerField(error_messages=error_message,
                                     widget=forms.TextInput(attrs=attr),
                                     required=True,
                                     label='مبلغ شارژ هر متر')
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی(تومان)', disabled=True)
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = ChargeByPersonArea
        fields = ['name', 'area_amount', 'details', 'person_amount', 'civil', 'payment_deadline',
                  'payment_penalty_amount', 'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class PersonAreaFixChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=100, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')
    fix_charge_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=True,
                                           label=' شارژ ثابت')
    person_amount = forms.IntegerField(error_messages=error_message,
                                       widget=forms.TextInput(attrs=attr),
                                       required=True,
                                       label='مبلغ شارژ نفر')
    area_amount = forms.IntegerField(error_messages=error_message,
                                     widget=forms.TextInput(attrs=attr),
                                     required=True,
                                     label='مبلغ شارژ هر متر')
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )
    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')

    class Meta:
        model = ChargeByFixPersonArea
        fields = ['name', 'area_amount', 'details', 'person_amount', 'civil', 'fix_charge_amount', 'payment_deadline',
                  'payment_penalty_amount', 'other_cost_amount']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


class VariableFixChargeForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=200, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان شارژ ')

    unit_fix_amount = forms.IntegerField(error_messages=error_message,
                                         widget=forms.TextInput(attrs=attr),
                                         required=True,
                                         label='شارژ ثابت به ازای هر واحد')
    extra_parking_amount = forms.IntegerField(error_messages=error_message,
                                              widget=forms.TextInput(attrs=attr),
                                              required=False, initial=0,
                                              label='هزینه اجاره پارکینگ ')
    unit_variable_person_amount = forms.IntegerField(error_messages=error_message,
                                                     widget=forms.TextInput(attrs=attr),
                                                     required=True,
                                                     label='شارژ متغیر به ازای هر نفر')
    unit_variable_area_amount = forms.IntegerField(error_messages=error_message,
                                                   widget=forms.TextInput(attrs=attr),
                                                   required=True,
                                                   label='شارژ متغیر به ازای هر متر')

    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')
    civil = forms.IntegerField(error_messages=error_message,
                               widget=forms.TextInput(attrs=attr),
                               required=False, initial=0,
                               label='شارژ عمرانی', disabled=True)

    other_cost_amount = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='سایر هزینه ها')
    payment_penalty_amount = forms.IntegerField(error_messages=error_message,
                                                widget=forms.TextInput(attrs=attr),
                                                required=False, initial=0,
                                                label='جریمه دیرکرد به درصد')

    payment_deadline = JalaliDateField(
        label='مهلت پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=True
    )

    class Meta:
        model = ChargeFixVariable
        fields = ['name', 'extra_parking_amount', 'unit_fix_amount', 'unit_variable_area_amount',
                  'unit_variable_person_amount', 'civil', 'details', 'other_cost_amount',
                  'payment_penalty_amount', 'payment_deadline']

    def clean_payment_deadline(self):
        deadline = self.cleaned_data.get('payment_deadline')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')

        return deadline


# class MultiFileInput(ClearableFileInput):
#     allow_multiple_selected = True


class CivilForm(forms.ModelForm):
    name = forms.CharField(error_messages=error_message, max_length=200, widget=forms.TextInput(attrs=attr),
                           required=True,
                           label='عنوان  ')
    amount = forms.IntegerField(error_messages=error_message,
                                widget=forms.TextInput(attrs=attr),
                                required=True,
                                label='مبلغ شارژ عمرانی')
    prepayment = forms.IntegerField(error_messages=error_message,
                                    widget=forms.TextInput(attrs=attr),
                                    required=False, initial=0,
                                    label='پیش پرداخت')
    installment_count = forms.IntegerField(error_messages=error_message,
                                           widget=forms.TextInput(attrs=attr),
                                           required=False, initial=0,
                                           label='تعداد اقساط ')
    first_due_date = JalaliDateField(
        label='تاریخ پرداخت اولین قسط',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control m-1'}),
        error_messages=error_message, required=True
    )
    details = forms.CharField(error_messages=error_message, required=False,
                              widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
                              label='توضیحات ')

    class Meta:
        model = CivilManage
        fields = ['name', 'amount', 'prepayment', 'installment_count', 'first_due_date', 'details']

    def clean_first_due_date(self):
        deadline = self.cleaned_data.get('first_due_date')

        if deadline:
            today = jdatetime.date.today()

            if deadline < today:
                raise forms.ValidationError('تاریخ سررسید نمی‌تواند قبل از امروز باشد')

        return deadline

    def clean(self):
        cleaned_data = super().clean()

        amount = cleaned_data.get('amount')
        prepayment = cleaned_data.get('prepayment') or 0

        if amount is not None and prepayment is not None:
            if prepayment > amount:
                self.add_error('prepayment', 'مبلغ پیش‌پرداخت نمی‌تواند بیشتر از مبلغ شارژ باشد.')

        return cleaned_data


# class ExpenseChargeForm(forms.ModelForm):
#     name = forms.CharField(error_messages=error_message, max_length=200, widget=forms.TextInput(attrs=attr),
#                            required=True,
#                            label='عنوان شارژ ')
#     unit_power_amount = forms.IntegerField(error_messages=error_message,
#                                            widget=forms.TextInput(attrs=attr),
#                                            required=True,
#                                            label='جمع کل هزینه برق')
#     unit_water_amount = forms.IntegerField(error_messages=error_message,
#                                            widget=forms.TextInput(attrs=attr),
#                                            required=True,
#                                            label='جمع کل هزینه آب')
#     unit_gas_amount = forms.IntegerField(error_messages=error_message,
#                                          widget=forms.TextInput(attrs=attr),
#                                          required=True,
#                                          label='جمع کل هزینه گاز')
#
#     details = forms.CharField(error_messages=error_message, required=False,
#                               widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
#                               label='توضیحات ')
#     civil = forms.IntegerField(error_messages=error_message,
#                                widget=forms.TextInput(attrs=attr),
#                                required=False, min_value=0,
#                                label='سایر هزینه ها')
#
#     other_cost_amount = forms.IntegerField(error_messages=error_message,
#                                            widget=forms.TextInput(attrs=attr),
#                                            required=False, min_value=0,
#                                            label='شارژ عمرانی')
#     payment_penalty_amount = forms.IntegerField(error_messages=error_message,
#                                                 widget=forms.TextInput(attrs=attr),
#                                                 required=False, min_value=0,
#                                                 label='جریمه دیرکرد به درصد')
#
#     payment_deadline = JalaliDateField(
#         label='مهلت پرداخت',
#         widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
#         error_messages=error_message, required=False
#     )
#
#     class Meta:
#         model = ChargeFixVariable
#         fields = ['name', 'civil', 'details', 'other_cost_amount', 'payment_penalty_amount', 'payment_deadline']
#
#     def clean_payment_deadline(self):
#         deadline = self.cleaned_data.get('payment_deadline')
#
#         if deadline:
#             today = jdatetime.date.today()
#
#             if deadline < today:
#                 raise forms.ValidationError('مهلت پرداخت نمی‌تواند قبل از امروز باشد')
#
#         return deadline


class UnifiedChargePaymentForm(forms.ModelForm):
    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    transaction_reference = forms.IntegerField(error_messages=error_message,
                                               widget=forms.TextInput(attrs=attr),
                                               required=False, min_value=0,
                                               label='کد پیگیری')

    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="شماره کارت را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label=' شماره کارت'
    )

    class Meta:
        model = UnifiedCharge
        fields = ['payment_date', 'transaction_reference', 'bank']

    def __init__(self, *args, **kwargs):
        charge = kwargs.pop('charge', None)
        super().__init__(*args, **kwargs)

        charge = self.instance

        # پیش‌فرض خالی
        self.fields['bank'].queryset = Bank.objects.none()

        if charge and charge.unit and charge.unit.myhouse:
            house = charge.unit.myhouse

            banks = Bank.objects.filter(
                is_active=True,
                house=house
            ).order_by('-is_default', 'bank_name')

            self.fields['bank'].queryset = banks

            # بانک پیش‌فرض
            default_bank = banks.filter(is_default=True).first()
            if default_bank:
                self.fields['bank'].initial = default_bank

            # label زیبا
            self.fields['bank'].label_from_instance = (
                lambda obj: f"{obj.bank_name} - {obj.cart_number}"
                            + (" (پیش‌فرض)" if obj.is_default else "")
            )

    def clean_payment_date(self):
        date = self.cleaned_data.get('payment_date')
        if date:
            # تبدیل Jalali به Gregorian
            gregorian_date = date.togregorian().date() if isinstance(date, jdatetime.date) else date

            today = timezone.now().date()
            if gregorian_date > today:
                raise ValidationError("تاریخ پرداخت نمی‌تواند از امروز بیشتر باشد.")
        return date


class SmsForm(forms.ModelForm):
    subject = forms.CharField(error_messages=error_message, max_length=20, widget=forms.TextInput(attrs=attr),
                              required=True,
                              label='عنوان پیامک ')
    message = forms.CharField(error_messages=error_message, required=True, widget=forms.Textarea(
        attrs={'class': 'form-control', 'rows': 2}),
                              label='متن پیامک')

    is_active = forms.ChoiceField(label='فعال /غیرفعال نمودن پیامک', required=True,
                                  error_messages=error_message, choices=CHOICES, widget=forms.Select(attrs=attr))

    class Meta:
        model = SmsManagement
        fields = ['subject', 'message', 'is_active']


class AdminSmsForm(forms.ModelForm):
    subject = forms.CharField(error_messages=error_message, max_length=20, widget=forms.TextInput(attrs=attr),
                              required=True,
                              label='عنوان پیامک ')
    message = forms.CharField(
        error_messages=error_message,
        required=True,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'id': 'sms_message',
            'placeholder': 'متن پیامک را وارد کنید...'
        }),
        label='متن پیامک'
    )

    is_active = forms.ChoiceField(label='فعال /غیرفعال نمودن پیامک', required=True,
                                  error_messages=error_message, choices=CHOICES, widget=forms.Select(attrs=attr))

    class Meta:
        model = AdminSmsManagement
        fields = ['subject', 'message', 'is_active']


class SubscriptionPlanForm(forms.ModelForm):
    class Meta:
        model = SubscriptionPlan
        fields = ['duration', 'price_per_unit']


class SmsCreditForm(forms.ModelForm):
    class Meta:
        model = SmsCredit
        fields = ['amount']
        widgets = {
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': 'مبلغ را وارد کنید'})
        }


class SubscriptionForm(forms.ModelForm):
    class Meta:
        model = Subscription
        # house حذف شده، فقط کاربر تعداد واحد و پلن انتخاب می‌کنه
        fields = ['units_count', 'plan']


class SubscriptionUpdateForm(forms.ModelForm):
    plan = forms.ModelChoiceField(
        queryset=SubscriptionPlan.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="پلن را انتخاب کنید",
        error_messages=error_message,
        required=False,
        label=' پلن انتخابی'
    )
    house = forms.ModelChoiceField(
        queryset=MyHouse.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="مدیر را انتخاب کنید",
        error_messages=error_message,
        required=True,
        label='مدیر ساختمان'
    )
    units_count = forms.IntegerField(error_messages=error_message,
                                     widget=forms.TextInput(attrs=attr),
                                     required=False,
                                     label='تعداد واحد')
    total_amount = forms.IntegerField(error_messages=error_message,
                                      widget=forms.TextInput(attrs=attr),
                                      required=False,
                                      label='مبلغ پرداختی')
    start_date = JalaliDateField(
        label='تاریخ شروع',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    end_date = JalaliDateField(
        label='تاریخ پایان',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )

    payment_date = JalaliDateField(
        label='تاریخ پرداخت',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        error_messages=error_message, required=False
    )
    transaction_id = forms.IntegerField(error_messages=error_message,
                                        widget=forms.TextInput(attrs=attr),
                                        required=False, min_value=0,
                                        label='کد پیگیری')
    status = forms.ChoiceField(
        choices=Subscription.STATUS_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        label='وضعیت اشتراک'
    )

    class Meta:
        model = Subscription
        fields = ['house', 'payment_date', 'start_date', 'end_date', 'plan', 'transaction_id', 'total_amount', 'status',
                  'units_count']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)  # ابتدا سوپر را صدا بزنید

        # تنظیم کوئری‌ست‌ها (همیشه انجام شود)
        self.fields['plan'].queryset = SubscriptionPlan.objects.filter(is_active=True)
        self.fields['house'].queryset = MyHouse.objects.all()

        # تنظیم label_from_instance
        self.fields['plan'].label_from_instance = lambda obj: f"{obj.duration} ماهه - {obj.price_per_unit} تومان"
        self.fields['house'].label_from_instance = lambda obj: f"{obj.name} -  {obj.user.full_name}"


class TransferMoneyForm(forms.ModelForm):
    # تعریف فیلدها خارج از متا چون مستقیماً در مدل BankFund نیستند (مثل from_bank و to_bank)
    from_bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="بانک مبدا را انتخاب کنید",
        label='از بانک'
    )
    to_bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        widget=forms.Select(attrs={'class': 'form-control form-control-sm'}),
        empty_label="بانک مقصد را انتخاب کنید",
        label='به بانک'
    )
    payment_date = JalaliDateField(
        label='تاریخ انتقال',
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
        initial=jdatetime.date.today
    )
    amount = forms.IntegerField(
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'مبلغ را وارد کنید'}),
        min_value=1,
        label='مبلغ'
    )
    transaction_reference = forms.CharField(
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        required=False,
        label='کد پیگیری / شماره تراکنش'
    )

    class Meta:
        model = BankFund
        # فقط فیلدهایی که در مدل وجود دارند یا فیلد اضافه
        fields = ['from_bank', 'to_bank', 'amount', 'transaction_reference', 'payment_date']

    def __init__(self, *args, **kwargs):
        # دریافت کاربر از ویو
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)

        if user:
            # فیلتر کردن بانک‌های مربوط به کاربر
            user_banks = Bank.objects.filter(user=user, is_active=True)

            # مقداردهی کوئری‌ست‌ها
            self.fields['from_bank'].queryset = user_banks
            self.fields['to_bank'].queryset = user_banks

            # انتخاب بانک پیش‌فرض برای مبدا
            default_bank = user_banks.filter(is_default=True).first()
            if default_bank:
                self.fields['from_bank'].initial = default_bank

    def clean(self):
        cleaned_data = super().clean()

        from_bank = cleaned_data.get('from_bank')
        to_bank = cleaned_data.get('to_bank')
        amount = cleaned_data.get('amount')
        payment_date = cleaned_data.get('payment_date')

        # ۱. بررسی یکسان نبودن بانک‌ها
        if from_bank and to_bank and from_bank == to_bank:
            raise ValidationError("بانک مبدا و مقصد نمی‌تواند یکسان باشد.")

        # ۲. بررسی تاریخ افتتاح بانک مبدا
        if from_bank and payment_date:
            bank_open_date = from_bank.create_at.date()

            if payment_date < bank_open_date:
                self.add_error(
                    'payment_date',
                    f'تاریخ انتقال نمی‌تواند قبل از تاریخ افتتاح حساب بانک مبدا باشد.'
                )

        # ۳. بررسی تاریخ افتتاح بانک مقصد
        if to_bank and payment_date:
            bank_open_date = to_bank.create_at.date()

            if payment_date < bank_open_date:
                self.add_error(
                    'payment_date',
                    f'تاریخ انتقال نمی‌تواند قبل از تاریخ افتتاح حساب بانک مقصد باشد.'
                )

        # ۴. بررسی موجودی بانک مبدا
        if from_bank and amount:
            if from_bank.current_balance < amount:
                self.add_error(
                    'amount',
                    f"موجودی حساب مبدا کافی نیست. (موجودی فعلی: {from_bank.current_balance:,})"
                )

        # ۵. بررسی تاریخ آینده
        if payment_date:
            today = jdatetime.date.today().togregorian()

            if payment_date > today:
                self.add_error(
                    'payment_date',
                    "تاریخ انتقال نمی‌تواند بعد از امروز باشد."
                )

        return cleaned_data


class CouponApplyForm(forms.ModelForm):
    error_message = {
        'required': 'این فیلد الزامی است.',
        'invalid': 'لطفا مقدار معتبری وارد کنید.'
    }

    code = forms.CharField(
        required=True,
        error_messages=error_message,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='کد تخفیف'
    )
    valid_from = JalaliDateField(
        label='تاریخ شروع',
        required=True,
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
    )
    valid_to = JalaliDateField(
        label='تاریخ پایان',
        required=True,
        widget=AdminJalaliDateWidget(attrs={'class': 'form-control'}),
    )
    discount = forms.CharField(
        required=True,
        error_messages=error_message,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
        label='مبلغ تخفیف'
    )
    active = forms.ChoiceField(label='فعال /غیرفعال  ', required=True,
                               error_messages=error_message, choices=CHOICES,
                               widget=forms.Select(attrs={'class': 'form-control form-control-sm'}))

    class Meta:
        model = Coupon
        fields = ['code', 'valid_from', 'valid_to', 'discount', 'active']
