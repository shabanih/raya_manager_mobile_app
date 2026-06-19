import json
from datetime import timedelta
from decimal import Decimal

import requests
from dateutil.relativedelta import relativedelta
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone

from admin_panel.models import SmsCredit, AdminFund, SubscriptionPlan, Subscription, Coupon, CouponUsage
from payment_app.views import ZP_API_STARTPAY, ZP_API_REQUEST
from user_app.models import Bank, MyHouse, User

MERCHANT = "3d6d6a26-c139-49ac-9d8d-b03a8cdf0fdd"

# ZP_API_REQUEST = "https://api.zarinpal.com/pg/v4/payment/request.json"
# ZP_API_VERIFY = "https://api.zarinpal.com/pg/v4/payment/verify.json"
# ZP_API_STARTPAY = "https://www.zarinpal.com/pg/StartPay/{authority}"#


ZP_API_REQUEST = "https://sandbox.zarinpal.com/pg/v4/payment/request.json"
ZP_API_VERIFY = "https://sandbox.zarinpal.com/pg/v4/payment/verify.json"
ZP_API_STARTPAY = "https://sandbox.zarinpal.com/pg/StartPay/{authority}"

description = "Raya"  # Required

CallbackURLSMS = 'http://127.0.0.1:8001/admin-payment/verify-sms-pay/'
CallbackURLSub = 'http://127.0.0.1:8001/admin-payment/verify-subscription-pay/'
CallbackURLSubUser = 'http://127.0.0.1:8001/admin-payment/verify-subscription-by-user/'


@login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN)
def request_sms_pay(request):

    if request.method != 'POST':
        return redirect('add_sms_credit')

    amount = request.POST.get('amount')

    try:
        amount = int(amount.replace(',', ''))

        if amount <= 0:
            messages.error(request, "مبلغ وارد شده معتبر نیست")
            return redirect('add_sms_credit')

    except Exception:
        messages.error(request, "مبلغ وارد شده معتبر نیست")
        return redirect('add_sms_credit')

    amount_with_tax = round(amount * 1.1)

    callback_url = (
        f"{CallbackURLSMS}"
        f"?amount={amount}"
        f"&amount_with_tax={amount_with_tax}"
    )

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(amount_with_tax * 10),
        "callback_url": callback_url,
        "description": "شارژ حساب پیامک",
    }

    req_header = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        response = requests.post(
            url=ZP_API_REQUEST,
            data=json.dumps(req_data),
            headers=req_header,
            timeout=10
        )

        result = response.json()

        if (
            response.status_code == 200 and
            result.get('data', {}).get('authority')
        ):

            authority = result['data']['authority']

            return redirect(
                ZP_API_STARTPAY.format(authority=authority)
            )

        error_data = result.get('errors', {})

        return HttpResponse(
            f"{error_data.get('code')} - "
            f"{error_data.get('message')}"
        )

    except requests.RequestException as e:

        return HttpResponse(
            f"خطا در ارتباط با درگاه: {e}",
            status=500
        )


@login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN)
def verify_sms_credit_pay(request):

    authority = request.GET.get('Authority')
    status = request.GET.get('Status')

    amount = request.GET.get('amount')
    amount_with_tax = request.GET.get('amount_with_tax')

    house = MyHouse.objects.filter(user=request.user).first()

    if not amount or not amount_with_tax:
        messages.error(request, 'اطلاعات پرداخت ناقص است')
        return redirect('add_sms_credit')

    try:
        amount = int(amount)
        amount_with_tax = int(amount_with_tax)

    except ValueError:
        messages.error(request, 'مبلغ نامعتبر است')
        return redirect('add_sms_credit')

    if status != 'OK':
        messages.error(request, 'پرداخت لغو شد')
        return redirect('add_sms_credit')

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(amount_with_tax * 10),
        "authority": authority
    }

    req_header = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:

        response = requests.post(
            ZP_API_VERIFY,
            data=json.dumps(req_data),
            headers=req_header,
            timeout=10
        )

        result = response.json()

        if result.get('errors'):

            return render(request, 'admin_payment_done.html', {
                'error': result['errors'].get('message')
            })

        data = result.get('data', {})
        code = data.get('code')

        if code == 100:

            ref_id = data.get('ref_id')

            # ایجاد رکورد فقط بعد از پرداخت موفق
            credit = SmsCredit.objects.create(
                user=request.user,
                house=house,
                amount=amount,
                amount_with_tax=amount_with_tax,
                is_paid=True,
                paid_at=timezone.now(),
                payment_date=timezone.now(),
                transaction_no=ref_id,
            )

            content_type = ContentType.objects.get_for_model(SmsCredit)

            AdminFund.objects.create(
                user=request.user,
                bank=None,
                content_type=content_type,
                object_id=credit.id,
                amount=credit.amount_with_tax,
                payment_gateway='پرداخت اینترنتی',
                payment_date=credit.paid_at,
                transaction_no=ref_id,
                house=credit.house,
                payment_description='شارژ حساب پیامک',
                is_paid=True
            )

            messages.success(
                request,
                f'پرداخت با موفقیت انجام شد. کد پیگیری: {ref_id}'
            )

            return redirect('add_sms_credit')

        elif code == 101:

            messages.info(
                request,
                'این پرداخت قبلاً ثبت شده است'
            )

            return redirect('add_sms_credit')

        return render(request, 'admin_payment_done.html', {
            'error': data.get('message')
        })

    except requests.RequestException as e:

        return render(request, 'admin_payment_done.html', {
            'error': f'خطا در ارتباط با درگاه: {e}'
        })


@login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN)
def request_subscription_pay(request):
    if request.method != 'POST':
        return redirect('buy_subscription')

    plan_id = request.POST.get('plan')

    units_count = request.POST.get('units_count')
    coupon_code = request.POST.get('code', '').strip()

    if not plan_id or not units_count:
        messages.error(request, "اطلاعات ناقص است")
        return redirect('buy_subscription')

    try:
        units_count = int(units_count)
        if units_count <= 0:
            raise ValueError
    except ValueError:
        messages.error(request, "تعداد واحد نامعتبر است")
        return redirect('buy_subscription')

    try:
        plan = SubscriptionPlan.objects.get(id=plan_id)
    except SubscriptionPlan.DoesNotExist:
        messages.error(request, "پلن انتخابی معتبر نیست")
        return redirect('buy_subscription')

    total_amount = units_count * plan.price_per_unit

    coupon = None
    discount_amount = 0

    if coupon_code:
        try:
            coupon = Coupon.objects.get(code__iexact=coupon_code)

            if not coupon.is_valid():
                messages.error(request, "کد تخفیف منقضی یا غیرفعال است")
                return redirect('buy_subscription')

            already_used = Coupon.objects.filter(
                user=request.user,
                code=coupon
            ).exists()

            if already_used:
                messages.error(request, "شما قبلاً از این کد تخفیف استفاده کرده‌اید")
                return redirect('buy_subscription')

            if coupon.discount > total_amount:
                messages.error(
                    request,
                    "مبلغ کد تخفیف بیشتر از مبلغ کل سفارش است و قابل استفاده نیست."
                )
                return redirect('buy_subscription')

            discount_amount = coupon.discount

        except Coupon.DoesNotExist:
            messages.error(request, "کد تخفیف نامعتبر است")
            return redirect('buy_subscription')

    final_amount = total_amount - discount_amount

    request.session['subscription_payment'] = {
        "plan_id": plan.id,
        "units_count": units_count,

        "total_amount": total_amount,
        "discount_amount": discount_amount,
        "final_amount": final_amount,

        "coupon_id": coupon.id if coupon else None,
    }

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(final_amount * 10),
        "callback_url": CallbackURLSub,
        "description": "خرید اشتراک ساختمان",
    }

    req_header = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        req = requests.post(
            url=ZP_API_REQUEST,
            data=json.dumps(req_data),
            headers=req_header
        )

        result = req.json()

        if req.status_code == 200 and 'authority' in result.get('data', {}):
            authority = result['data']['authority']
            return redirect(
                ZP_API_STARTPAY.format(authority=authority)
            )

        e_code = result.get('errors', {}).get('code', '')
        e_message = result.get('errors', {}).get('message', '')
        return HttpResponse(f"{e_code} - {e_message}")

    except requests.RequestException as e:
        return HttpResponse(
            f"خطا در ارتباط با درگاه: {e}",
            status=500
        )


@login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN)
def verify_subscription_pay(request):
    authority = request.GET.get('Authority')
    status = request.GET.get('Status')

    payment_data = request.session.get('subscription_payment')

    if not payment_data:
        return render(request, 'admin_payment_done.html', {
            'error': 'اطلاعات پرداخت پیدا نشد'
        })

    if status != 'OK':
        messages.error(request, "پرداخت لغو شد")
        return redirect('buy_subscription')

    plan = get_object_or_404(
        SubscriptionPlan,
        id=payment_data['plan_id']
    )

    total_amount = payment_data['total_amount']
    discount_amount = payment_data['discount_amount']
    final_amount = payment_data['final_amount']
    units_count = payment_data['units_count']
    coupon_id = payment_data.get('coupon_id')

    coupon = None
    if coupon_id:
        coupon = Coupon.objects.filter(id=coupon_id).first()

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(final_amount * 10),
        "authority": authority
    }

    req_header = {
        "accept": "application/json",
        "content-type": "application/json"
    }

    try:
        req = requests.post(
            ZP_API_VERIFY,
            data=json.dumps(req_data),
            headers=req_header
        )

        result = req.json()
        data = result.get('data', {})

        if result.get('errors'):
            return render(request, 'admin_payment_done.html', {
                'error': result['errors'].get('message')
            })

        if data.get('code') == 100:

            ref_id = str(data.get('ref_id'))
            now = timezone.now()

            house = MyHouse.objects.filter(
                user=request.user
            ).first()

            subscription = Subscription.objects.create(
                user=request.user,
                house=house,

                coupon=coupon,

                units_count=units_count,
                plan=plan,

                total_amount=total_amount,
                discount_amount=discount_amount,
                final_amount=final_amount,

                is_paid=True,
                payment_date=now,
                transaction_id=ref_id,

                start_date=now,
                end_date=now + relativedelta(
                    months=plan.duration
                )
            )

            if coupon:
                CouponUsage.objects.get_or_create(
                    user=request.user,
                    coupon=coupon
                )

            content_type = ContentType.objects.get_for_model(
                Subscription
            )

            AdminFund.objects.create(
                user=request.user,
                content_type=content_type,
                object_id=subscription.id,

                amount=final_amount,

                payment_gateway='پرداخت اینترنتی',
                payment_date=now,
                transaction_no=ref_id,

                payment_description=f"خرید اشتراک {plan}",
                house=house,
                is_paid=True
            )

            del request.session['subscription_payment']

            messages.success(
                request,
                f"پرداخت موفق. کد پیگیری: {ref_id}"
            )

            return redirect('middle_admin_dashboard')

        elif data.get('code') == 101:
            messages.info(request, "این پرداخت قبلاً ثبت شده")
            return redirect('middle_admin_dashboard')

        return render(request, 'admin_payment_done.html', {
            'error': data.get('message')
        })

    except Exception as e:
        return render(request, 'admin_payment_done.html', {
            'error': f"خطا در تایید پرداخت: {e}"
        })


# ========================================================

def request_subscription_pay_by_user(request, user_id):

    user = get_object_or_404(User, id=user_id)
    house = user.house

    if request.method != "POST":
        return redirect("buy_subscription_by_user", user_id=user.id)

    plan_id = request.POST.get("plan")
    units_count = request.POST.get("units_count")
    coupon_code = request.POST.get("code", "").strip()

    if not plan_id or not units_count:
        messages.error(request, "اطلاعات ناقص است")
        return redirect("buy_subscription_by_user", user_id=user.id)

    try:
        units_count = int(units_count)
    except:
        messages.error(request, "تعداد واحد نامعتبر است")
        return redirect("buy_subscription_by_user", user_id=user.id)

    plan = get_object_or_404(SubscriptionPlan, id=plan_id, is_active=True)

    total_amount = units_count * plan.price_per_unit

    coupon = None
    discount_amount = 0

    if coupon_code:
        coupon = Coupon.objects.filter(code__iexact=coupon_code).first()

        if not coupon or not coupon.is_valid():
            messages.error(request, "کد تخفیف نامعتبر است")
            return redirect("buy_subscription_by_user", user_id=user.id)

        discount_amount = min(coupon.discount, total_amount)

    final_amount = total_amount - discount_amount

    # 🔥 مهم: ذخیره در session همراه user_id
    request.session["subscription_payment"] = {
        "user_id": user.id,
        "plan_id": plan.id,
        "units_count": units_count,
        "total_amount": total_amount,
        "discount_amount": discount_amount,
        "final_amount": final_amount,
        "coupon_id": coupon.id if coupon else None,
    }

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(final_amount * 10),
        "callback_url": CallbackURLSubUser,  # جدا از ادمین
        "description": "خرید اشتراک کاربر",
    }

    try:
        result = requests.post(
            ZP_API_REQUEST,
            data=json.dumps(req_data),
            headers={"content-type": "application/json"}
        ).json()

        if result.get("data", {}).get("authority"):
            return redirect(
                ZP_API_STARTPAY.format(authority=result["data"]["authority"])
            )

        return HttpResponse("خطا در اتصال به درگاه")

    except Exception as e:
        return HttpResponse(str(e), status=500)


def verify_subscription_pay_by_user(request):

    authority = request.GET.get("Authority")
    status = request.GET.get("Status")

    payment_data = request.session.get("subscription_payment")

    if status != "OK":
        messages.error(request, "پرداخت ناموفق یا لغو شد")
        return redirect("home")

    if not payment_data:
        return render(request, "payment_done.html", {
            "error": "اطلاعات پرداخت پیدا نشد"
        })

    user = get_object_or_404(User, id=payment_data["user_id"])
    plan = get_object_or_404(SubscriptionPlan, id=payment_data["plan_id"])
    house = user.house

    final_amount = payment_data["final_amount"]

    req_data = {
        "merchant_id": MERCHANT,
        "amount": int(final_amount * 10),
        "authority": authority,
    }

    result = requests.post(
        ZP_API_VERIFY,
        data=json.dumps(req_data),
        headers={"content-type": "application/json"}
    ).json()

    data = result.get("data", {})

    if data.get("code") == 100:

        ref_id = data.get("ref_id")
        now = timezone.now()

        subscription = Subscription.objects.create(
            user=user,
            house=house,
            plan=plan,
            units_count=payment_data["units_count"],
            total_amount=payment_data["total_amount"],
            discount_amount=payment_data["discount_amount"],
            final_amount=final_amount,
            is_paid=True,
            status="active",
            transaction_id=ref_id,
            payment_date=now,
            start_date=now,
            end_date=now + relativedelta(
                months=plan.duration
            )
        )
        content_type = ContentType.objects.get_for_model(
            Subscription
        )

        AdminFund.objects.create(
            user=user,
            content_type=content_type,
            object_id=subscription.id,

            amount=final_amount,

            payment_gateway='پرداخت اینترنتی2',
            payment_date=now,
            transaction_no=ref_id,

            payment_description=f"خرید اشتراک توسط کاربر {plan}",
            house=house,
            is_paid=True
        )

        if payment_data.get("coupon_id"):
            coupon = Coupon.objects.filter(id=payment_data["coupon_id"]).first()
            if coupon:
                CouponUsage.objects.get_or_create(user=user, coupon=coupon)

        request.session.pop("subscription_payment", None)

        messages.success(request, "اشتراک شما ثبت شد. پس از تایید، کارشناسان شارژیار با شما تماس خواهند گرفت")
        return redirect("home")

    return render(request, "payment_done.html", {
        "error": data.get("message", "خطا در پرداخت")
    })