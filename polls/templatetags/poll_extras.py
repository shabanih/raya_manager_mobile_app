import datetime

import jdatetime
import pytz
from django import template
from django.utils import timezone

from user_app.models import MyHouse

register = template.Library()


@register.filter(name='cut')
def cut(value, arg):
    return value.replace(arg, '')


# @register.filter(name='show_jalali_date')
# def show_jalali_date(value):
#     return jdate.fromgregorian(date=value).strftime('%Y/%m/%d')

WEEKDAYS = ['شنبه', 'یک‌شنبه', 'دوشنبه', 'سه‌شنبه', 'چهارشنبه', 'پنج‌شنبه', 'جمعه']
MONTHS = ['فروردین', 'اردیبهشت', 'خرداد', 'تیر', 'مرداد', 'شهریور',
          'مهر', 'آبان', 'آذر', 'دی', 'بهمن', 'اسفند']


@register.filter(name='show_jalali_date_time')
def show_jalali_date_time(value):
    if value is None:
        return ''
    # تبدیل به Jalali
    jalali_datetime = jdatetime.datetime.fromgregorian(datetime=value)

    # نام روز و ماه
    weekday = WEEKDAYS[jalali_datetime.weekday()]
    month = MONTHS[jalali_datetime.month - 1]

    # فرمت تاریخ و زمان
    formatted_date = f'{jalali_datetime.hour:02d}:{jalali_datetime.minute:02d} - {jalali_datetime.day}/ {jalali_datetime.month}/ {jalali_datetime.year} '
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted_date.translate(translation_table)


@register.filter(name='show_jalali_date_only')
def show_jalali_date(value):
    if value is None:
        return ''
    # Convert the Gregorian datetime to Jalali datetime
    jalali_datetime = jdatetime.datetime.fromgregorian(datetime=value)

    # Get the Persian weekday and month name
    weekday = WEEKDAYS[jalali_datetime.weekday()]
    month = MONTHS[jalali_datetime.month - 1]  # Index starts from 0 for MONTHS list

    # Format the date manually using Persian names without time
    formatted_date = f'{weekday} {jalali_datetime.day} {month} {jalali_datetime.year}'
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted_date.translate(translation_table)


@register.filter(name='show_jalali_date_excel')
def show_jalali_date_excel(value):
    if not value:
        return ''

    # اگر datetime باشه، به تایم‌زون محلی تبدیل کن
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        jalali = jdatetime.datetime.fromgregorian(datetime=value)
    elif isinstance(value, datetime.date):
        jalali = jdatetime.date.fromgregorian(date=value)
    else:
        return ''

    # قالب سال-ماه-روز
    formatted_date = f'{jalali.year:04d}-{jalali.month:02d}-{jalali.day:02d}'

    # تبدیل اعداد به فارسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted_date.translate(translation_table)


@register.filter(name='show_jalali')
def show_jalali(value):
    if not value:
        return ''

    # اگر datetime باشه، به تایم‌زون محلی تبدیل کن
    if isinstance(value, datetime.datetime):
        if timezone.is_aware(value):
            value = timezone.localtime(value)
        jalali = jdatetime.datetime.fromgregorian(datetime=value)
    elif isinstance(value, datetime.date):
        jalali = jdatetime.date.fromgregorian(date=value)
    else:
        return ''

    # قالب سال-ماه-روز
    formatted_date = f'{jalali.year:04d}-{jalali.month:02d}-{jalali.day:02d}'

    # تبدیل اعداد به فارسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted_date.translate(translation_table)


@register.filter(name='show_jalali_admin')
def show_jalali(value):
    if not value:
        return ''

    if isinstance(value, datetime.datetime):
        jalali = jdatetime.datetime.fromgregorian(datetime=value)
    elif isinstance(value, datetime.date):
        jalali = jdatetime.date.fromgregorian(date=value)
    else:
        return ''

    formatted_date = f'{jalali.day:02d}-{jalali.month:02d}-{jalali.year}'

    # تبدیل اعداد به فارسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted_date.translate(translation_table)


# @register.filter(name='three_digit_currency')
# def three_digit_currency(value):
#     try:
#         return '{:,}'.format(int(value))
#     except (ValueError, TypeError):
#         return '0'

@register.filter(name='three_digit_currency')
def three_digit_currency(value):
    if value is None:
        return ""

    try:
        value = int(value)
    except (ValueError, TypeError):
        return "۰"

    formatted = f"{value:,}"

    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)

    return formatted.translate(translation_table)


@register.filter(name='four_digit_cart')
def four_digit_cart(value):
    try:
        # تبدیل مقدار به رشته عددی
        value_str = str(int(value))
    except (ValueError, TypeError):
        return value  # اگر تبدیل نشد، همون مقدار اصلی برگرده

    # تبدیل اعداد به فارسی
    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'
    translation_table = str.maketrans(english_digits, persian_digits)
    value_str = value_str.translate(translation_table)

    # جدا کردن هر ۴ رقم با فاصله
    grouped = ' '.join([value_str[i:i + 4] for i in range(0, len(value_str), 4)])

    # اضافه کردن Left-to-Right Mark برای نمایش درست در متون راست‌به‌چپ
    return '\u200E' + grouped


@register.filter
def get_item(dictionary, key):
    return dictionary.get(key)


@register.filter
def get_field(obj, field_name):
    return getattr(obj, field_name, None)


@register.filter
def dict_get(d, key):
    return d.get(key)


# def jalali_to_gregorian(jdate_str):
#     if not jdate_str:
#         return None
#
#     y, m, d = map(int, jdate_str.split('/'))
#     return jdatetime.date(y, m, d).togregorian()
def jalali_to_gregorian(jdate):
    if not jdate:
        return None

    # اگر قبلاً date هست
    if isinstance(jdate, datetime.date):
        return jdate

    # اگر رشته است
    if isinstance(jdate, str):
        y, m, d = map(int, jdate.split('/'))
        return jdatetime.date(y, m, d).togregorian()

    return None


REPORT_PREFIXES = [
    "admin_fund",
    "charge",
    "admin_bank",
    "admin_unit_fund",
    "admin_debtor",
    "admin_unit_history",
    "admin_expense",
    "admin_income",
    "admin_receive",
    "admin_pay",
    "admin_property",
    "admin_maintenance",
    "admin_house_balance",


]
Middle_REPORT_PREFIXES = [
    "fund_turn_over",
    "unit_report",
    "middle_bank",
    "charge_notify",
    "middle_sewage",
    "charge_civil",
    "debtor_units_report",
    "unit_history_report",
    "expense_history_report",
    "income_history_report",
    "pay_receive_report",
    "property_history_report",
    "maintenance_history_report",
    "user_pay_report",
    "house_balance_view",


]
USER_PREFIXES = [
    "user_charges",
    "user_civil",
]

USER_FINANCE_PREFIXES = [
    "user_pay_money",
    "user_sewage",
    "fund_turn_over_user",
]

@register.simple_tag
def is_report_section(url_name):
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in REPORT_PREFIXES)

@register.simple_tag
def is_user_finance_section(url_name):
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in USER_FINANCE_PREFIXES)


@register.simple_tag
def is_middle_report_section(url_name):
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in Middle_REPORT_PREFIXES)

@register.simple_tag
def is_user_charge_section(url_name):
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in USER_PREFIXES)


CHARGE_PREFIXES = [
    "middle_add",
    "middle_civil",
    "middle_main",
]
SMS_PREFIXES = [
    "add_sms_credit",
    "sms_middle",
    "middle_sms_management",
]
MESSAGE_PREFIXES = [
    "message_middle",
    "message_management_for_middle",
    "middle_message_management_from_admin",
]


@register.simple_tag
def is_charge_section(url_name):
    """بررسی می‌کند که URL با پیشوند شارژ شروع شده باشد"""
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in CHARGE_PREFIXES)

@register.simple_tag
def is_message_section(url_name):
    """بررسی می‌کند که URL با پیشوند شارژ شروع شده باشد"""
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in MESSAGE_PREFIXES)

@register.simple_tag
def is_sms_section(url_name):
    """بررسی می‌کند که URL با پیشوند شارژ شروع شده باشد"""
    if not url_name:
        return False
    return any(url_name.startswith(p) for p in SMS_PREFIXES)

@register.filter
def to_persian_number(value):
    if value is None:
        return value

    persian_digits = '۰۱۲۳۴۵۶۷۸۹'
    english_digits = '0123456789'

    translation_table = str.maketrans(english_digits, persian_digits)
    return str(value).translate(translation_table)

