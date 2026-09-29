from datetime import timedelta
from decimal import Decimal

from django.core.cache import cache
from django.db.models import Q, Sum
from django.utils import timezone

from admin_panel.models import UnifiedCharge, Announcement, MessageToUser, MessageReadStatus, SmsCredit, \
    MiddleMessageReadStatus, SmsManagement, Subscription
from home.models import FreeRequest, ContactUs
from polls_app.models import Poll
from user_app.models import MyHouse, Unit, Renter


def user_unit_context(request):
    if not request.user.is_authenticated:
        return {}

    house = MyHouse.objects.filter(
        Q(units__user=request.user) |
        Q(units__renters__user=request.user, units__renters__renter_is_active=True)
    ).distinct().order_by('-created_at').first()

    unit = None
    is_unit_owner = False

    if house:
        unit = Unit.objects.filter(
            Q(user=request.user) |
            Q(renters__user=request.user, renters__renter_is_active=True),
            myhouse=house
        ).distinct().first()

        if unit and unit.user == request.user:
            is_unit_owner = True

    return {
        'current_house': house,
        'current_unit': unit,
        'is_unit_owner': is_unit_owner,
    }



def current_middle_house(request):
    """
    ارسال اطلاعات خانه و اشتراک فعال به تمامی قالب‌ها بدون خطا
    """
    if not request.user.is_authenticated:
        return {}

    middle_house = MyHouse.objects.filter(
        user=request.user,
        is_active=True
    ).order_by('-created_at').first()

    # مقادیر پیش‌فرض امن
    context = {
        "middle_house": middle_house,
        "current_subscription": None,
        "total_days": 1,
        "remaining_days": 0,
        "sub_status": "inactive",
        "plan": None,
        "subscription_warning": True,  # به صورت پیش‌فرض هشدار فعال است مگر خلافش ثابت شود
        "redirect_to_buy": False,
        "progress_dashoffset": 345
    }

    last_sub = Subscription.objects.filter(user=request.user).order_by('-created_at').first()

    if last_sub:
        last_sub.expire_if_needed()
        last_sub.refresh_from_db()  # دریافت وضعیت جدیدِ منقضی شده بعد از تغییر احتمالی

        context["current_subscription"] = last_sub
        context["plan"] = last_sub.plan
        context["total_days"] = last_sub.total_days
        context["remaining_days"] = last_sub.days_remaining

        if last_sub.status == "active":
            context["sub_status"] = "trial" if last_sub.is_trial else "paid"

            remaining = last_sub.days_remaining
            context["subscription_warning"] = (0 < remaining <= 3)

            ratio = min(max(remaining / last_sub.total_days, 0), 1)
            context["progress_dashoffset"] = int(345 - (ratio * 345))
        else:
            context["sub_status"] = "inactive"
            context["subscription_warning"] = True
            context["progress_dashoffset"] = 345
    today = timezone.now().date()

    expire_warning_date = today + timedelta(days=1)

    expiring_renters = (
        Renter.objects
        .select_related(
            'unit',
            'myhouse'
        )
        .filter(
            myhouse__user=request.user,
            renter_is_active=True,
            end_date__isnull=False,
            end_date__lte=expire_warning_date
        )
        .order_by('end_date')
    )

    renter_expire_notifications = []

    for renter in expiring_renters:

        remaining_days = (
                renter.end_date - today
        ).days

        if remaining_days < 0:

            status = "expired"

        elif remaining_days == 0:

            status = "today"

        else:

            status = "warning"

        renter_expire_notifications.append({
            "renter": renter,
            "unit": renter.unit,
            "remaining_days": remaining_days,
            "status": status,
        })

    context["renter_expire_notifications"] = renter_expire_notifications

    context["has_renter_expire_warning"] = bool(
        renter_expire_notifications
    )
    return context


def current_house(request):
    if not request.user.is_authenticated:
        return {}

    houses = MyHouse.objects.filter(
        Q(units__user=request.user) |
        Q(units__renters__user=request.user)
    ).distinct().order_by('-created_at')

    return {
        'house': houses.first(),
        'houses': houses,  # اگر بعداً لیست هم خواستی
    }


def user_header_notifications(request):
    if not request.user.is_authenticated:
        return {
            'new_charges_count': 0,
            'new_messages_count': 0,
            'new_polls_count': 0,
        }

    user_units = Unit.objects.filter(
        Q(user=request.user) |
        Q(renters__user=request.user, renters__renter_is_active=True),
        is_active=True
    )
    user_houses = MyHouse.objects.filter(
        units__in=user_units
    ).distinct()
    polls = Poll.objects.filter(
        house__in=user_houses,
        is_active=True
    )
    user_polls_without_vote = polls.exclude(
        vote__unit__in=user_units
    ).count()

    user_unit_ids = Unit.objects.filter(
        is_active=True
    ).filter(
        Q(user=request.user) |
        Q(renters__user=request.user,
          renters__renter_is_active=True)
    ).values_list('id', flat=True)

    new_user_charges_count = UnifiedCharge.objects.filter(
        unit__in=user_unit_ids,
        is_paid=False,
        send_notification=True
    ).count()

    # پیام‌های خوانده‌نشده
    new_user_messages_count = MessageReadStatus.objects.filter(
        unit__in=user_unit_ids,
        is_read=False
    ).values('message').distinct().count()

    user = request.user
    if user.is_middle_admin:
        units = (
            Unit.objects
            .filter(user__manager=user, is_active=True)
            .prefetch_related('renters')
        )
        marquee_announcements = (
            Announcement.objects
            .filter(user=user, is_active=True)
            .order_by('-created_at')[:5]
        )
    else:
        units = (
            Unit.objects
            .filter(user=user, is_active=True)
            .prefetch_related('renters')
        )
        marquee_announcements = (
            Announcement.objects
            .filter(user=user.manager, is_active=True)
            .order_by('-created_at')[:5]
        )


    return {
        'new_user_charges_count': new_user_charges_count,
        'new_user_messages_count': new_user_messages_count,
        'marquee_announcements': marquee_announcements,
        'user_polls_without_vote': user_polls_without_vote,
    }


def middle_header_notifications(request):
    if not request.user.is_authenticated:
        return {
            'new_messages_count': 0,
            'middle_current_credit': Decimal('0'),
        }

    user = request.user

    # پیام‌های خوانده‌نشده
    middle_new_messages_count = MiddleMessageReadStatus.objects.filter(
        user=user,
        is_read=False
    ).values('message').distinct().count()

    # اعتبار پیامک مدیر ساختمان
    middle_current_credit = (
            SmsCredit.objects
            .filter(user=user, is_paid=True)
            .aggregate(total=Sum('amount'))['total']
            or Decimal('0')
    )

    return {
        'middle_new_messages_count': middle_new_messages_count,
        'middle_current_credit': middle_current_credit,
    }


def admin_header_notifications(request):
    if not request.user.is_authenticated or not request.user.is_superuser:
        return {
            'admin_new_messages_count': 0,
            'admin_new_consultant': 0,
            'admin_new_comment': 0
        }

    admin_new_messages_count = SmsManagement.objects.filter(
        is_approved=False,
        is_active=True
    ).count()

    admin_new_consultant = FreeRequest.objects.filter(
        is_call=False
    ).count()

    admin_new_comment = ContactUs.objects.filter(
        is_read=False
    ).count()

    return {
        'admin_new_messages_count': admin_new_messages_count,
        'admin_new_consultant': admin_new_consultant,
        'admin_new_comment': admin_new_comment
    }


def impersonation_banner(request):
    return {
        "is_impersonating": bool(request.session.get("impersonator_id")),
        "impersonator_id": request.session.get("impersonator_id"),
    }
