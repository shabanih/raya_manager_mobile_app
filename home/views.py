from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import authenticate, login
from django.core.paginator import Paginator
from django.db.models import ProtectedError
from django.http import HttpResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView, UpdateView

from admin_panel.forms import UserRegistrationForm, MyHouseForm, UserRegistrationByUserForm
from admin_panel.helper import get_house_by_subdomain
from admin_panel.models import Subscription
from home.forms import FreeRequestForm, ContactUsForm, ArticleForm, CommentSiteForm
from home.models import SliderText, FreeRequest, ContactUs, Articles, CommentSite
from user_app.forms import LoginForm
from user_app.models import Unit, MyHouse, HouseLicense


def house_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.house:
            return redirect('main_site')  # صفحه اصلی سایت
        return view_func(request, *args, **kwargs)

    return wrapper


def index(request):
    if request.house:
        return redirect('house_login_subdomain')

    articles = Articles.objects.filter(
        is_active=True
    ).order_by('-created_at')[:3]

    sliders = SliderText.objects.all().order_by('-id')
    comments = CommentSite.objects.filter(is_approved=True).order_by('-id')

    form = FreeRequestForm()
    form2 = CommentSiteForm()

    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'درخواست شما ثبت شد')
        return redirect('home')

    return render(request, 'home.html', {
        'form': form,
        'form2': form2,
        'articles': articles,
        'comments': comments,
        'sliders': sliders,
    })


def add_comment(request):
    if request.method == 'POST':
        form = CommentSiteForm(request.POST)

        if form.is_valid():
            comment = form.save(commit=False)
            comment.save()

            messages.success(request, 'نظر شما با موفقیت ثبت شد.')

    return redirect('home')


def house_login(request):
    house = request.house
    enamad = HouseLicense.objects.filter(
        house=house,
        license_type='enamad',
        is_active=True
    ).first()

    if not house:
        return render(request, '404_house.html', status=404)

    if request.user.is_authenticated:

        if house.user_id == request.user.id:
            return redirect('middle_admin_dashboard')

        if request.user.house_id == house.id:
            return redirect('user_panel')

        messages.error(request, 'شما به این ساختمان دسترسی ندارید')

    form = LoginForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():

        mobile = form.cleaned_data['mobile']
        password = form.cleaned_data['password']

        user = authenticate(
            request,
            username=mobile,
            password=password
        )

        if not user:
            messages.error(request, 'اطلاعات کاربری اشتباه است')

        elif not user.is_active:
            messages.error(request, 'حساب غیرفعال است')

        elif user.is_superuser:
            messages.error(request, 'ورود از این بخش مجاز نیست')

        else:

            # 🔥 مهم‌ترین اصلاح
            is_owner = house.user_id == user.id
            is_resident = user.house_id == house.id

            if not (is_owner or is_resident):
                messages.error(request, 'شما عضو این ساختمان نیستید')

            else:
                login(request, user)

                if is_owner:
                    return redirect('middle_admin_dashboard')

                return redirect('user_panel')

    return render(request, 'login_subdomain.html', {
        'form': form,
        'house': house,
        'enamad': enamad
    })


def charge_select(request):
    return render(request, 'charge_select_by_user.html')


def register_house_by_user(request):
    user_form = UserRegistrationByUserForm(request.POST or None)
    house_form = MyHouseForm(request.POST or None)

    if request.method == "POST":

        if user_form.is_valid() and house_form.is_valid():

            # ساخت کاربر
            user_obj = user_form.save(commit=False)

            # ❌ هنوز تایید نشده → دسترسی پنل ندارد
            user_obj.is_middle_admin = True

            # ❗ مهم: برای جلوگیری از ورود
            user_obj.is_active = False

            user_obj.is_resident = user_form.cleaned_data.get('is_resident')
            user_obj.mobile = user_form.cleaned_data.get('mobile')
            user_obj.manager = request.user
            user_obj.username = user_obj.mobile

            charge_methods = user_form.cleaned_data.get('charge_methods')
            if charge_methods:
                user_obj.charge_methods.set(charge_methods)

            user_obj.save()

            # ساخت ساختمان
            house = house_form.save(commit=False)

            house.user = user_obj
            house.save()

            user_obj.house = house
            user_obj.save()

            # اشتراک تست (در صورت فعال بودن)
            if user_obj.is_trial:
                Subscription.objects.create(
                    user=user_obj,
                    house=user_obj.house,
                    units_count=5,
                    total_amount=0,
                    discount_amount=0,
                    final_amount=0,
                    is_trial=True,
                    start_date=timezone.now(),
                    end_date=timezone.now() + timedelta(days=19),
                    is_paid=True,
                    status='active'
                )

            messages.success(
                request,
                "ثبت‌نام با موفقیت انجام شد. طی چند ساعت آینده پنل کاربری شما ایجاد و با شما تماس خواهیم گرفت"
            )

            # ⛔ مهم: لاگین ممنوع
            return redirect('home')
    print(user_form.errors)
    print(house_form.errors)
    return render(
        request,
        'register_house_by_user.html',
        {
            'user_form': user_form,
            'house_form': house_form,
        }
    )


# def index(request):
#     articles = Articles.objects.filter(is_active=True).order_by('-created_at')[:3]
#     sliders = SliderText.objects.all().order_by('-id')
#
#     if request.house:
#         return redirect('house_login_subdomain')
#
#     form = FreeRequestForm()
#     if request.method == 'POST':
#         form = FreeRequestForm(request.POST)
#         if form.is_valid():
#             form.save()
#             messages.success(request, 'درخواست شما با موفقیت ثبت گردید. پس از بررسی با شما تماس خواهیم گرفت')
#             return redirect('home')
#         else:
#             messages.error(request, 'oxg')
#             return redirect('home')
#
#     return render(request, 'home.html', {
#         'form': form,
#         'articles': articles,
#         'sliders': sliders
#     })
#
#
# def house_home(request):
#     house = get_house_by_subdomain(getattr(request, 'subdomain', None))
#
#     # house = request.house
#
#     # اگر ساب‌دامین معتبر نبود
#     if not house:
#         return render(request, '404_house.html', status=404)
#
#     # اگر قبلا لاگین کرده
#     if request.user.is_authenticated:
#
#         # مدیر همین ساختمان
#         if house.user == request.user:
#             return redirect('middle_admin_dashboard')
#
#         # ساکن همین ساختمان
#         if house.residents.filter(id=request.user.id).exists():
#             return redirect('user_panel')
#
#         messages.error(
#             request,
#             'شما به این ساختمان دسترسی ندارید.'
#         )
#
#     form = LoginForm(request.POST or None)
#
#     if request.method == 'POST' and form.is_valid():
#
#         mobile = form.cleaned_data['mobile']
#         password = form.cleaned_data['password']
#
#         user = authenticate(
#             request,
#             username=mobile,
#             password=password
#         )
#
#         if not user:
#             messages.error(
#                 request,
#                 'شماره موبایل یا رمز عبور صحیح نیست.'
#             )
#
#         elif not user.is_active:
#             messages.error(
#                 request,
#                 'حساب کاربری شما غیرفعال است.'
#             )
#
#         elif user.is_superuser:
#             messages.error(
#                 request,
#                 'از پنل مدیریت وارد شوید.'
#             )
#
#         else:
#
#             # مدیر ساختمان
#             is_house_owner = house.user_id == user.id
#
#             # ساکن ساختمان
#             is_resident = house.residents.filter(
#                 id=user.id
#             ).exists()
#
#             if not (is_house_owner or is_resident):
#                 messages.error(
#                     request,
#                     'شما عضو این ساختمان نیستید.'
#                 )
#
#             else:
#
#                 login(request, user)
#
#                 # مدیر ساختمان
#                 if is_house_owner:
#                     return redirect(
#                         'middle_admin_dashboard'
#                     )
#
#                 # ساکنین
#                 return redirect(
#                     'user_panel'
#                 )
#
#     context = {
#         'form': form,
#         'house': house,
#     }
#
#     return render(
#         request,
#         'building_page.html',
#         context
#     )
#
#
# def house_login(request):
#     house = get_house_by_subdomain(getattr(request, 'subdomain', None))
#
#     if not house:
#         return render(request, "404_house.html")
#
#     if request.method == "POST":
#         username = request.POST.get("username")
#         password = request.POST.get("password")
#
#         user = authenticate(request, username=username, password=password)
#
#         if user and user in house.residents.all():
#             login(request, user)
#             return redirect("dashboard")
#
#         return render(request, "middle_login.html", {
#             "house": house,
#             "error": "اطلاعات اشتباه است"
#         })
#
#     return render(request, "middle_login.html", {
#         "house": house
#     })


def site_header_component(request):
    return render(request, 'renter_partials/site_header.html')


def site_footer_component(request):
    return render(request, 'renter_partials/site_footer.html')


def test_subdomain(request):
    return HttpResponse(
        f"Subdomain: {request.subdomain} | House: {request.house}"
    )


def middle_login(request):
    form = LoginForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        mobile = form.cleaned_data['mobile']
        password = form.cleaned_data['password']

        user = authenticate(request, username=mobile, password=password)

        if user:
            if user.is_superuser:
                messages.error(request, 'شما مجوز ورود از این صفحه را ندارید.')

            elif not user.is_active:
                messages.error(request, 'حساب کاربری شما غیرفعال است.')

            # ⛔ مالک با مستاجر فعال
            # elif Unit.objects.filter(
            #         user=user,
            #         renters__renter_is_active=True
            # ).exists():
            #     messages.error(
            #         request,
            #         'برای واحد شما مستاجر فعال ثبت شده است و امکان ورود مالک وجود ندارد.'
            #     )

            else:
                login(request, user)

                if user.is_middle_admin:
                    has_house = MyHouse.objects.filter(user=user).exists()
                    if has_house:
                        return redirect('middle_admin_dashboard')
                    else:
                        return redirect('middle_manage_house')

                return redirect('user_panel')


        else:
            messages.error(request, 'ورود ناموفق: شماره موبایل یا کلمه عبور نادرست است.')
    context = {
        'form': form,
        "house": request.house,

    }
    return render(request, "middle_login.html", context)


def contact_us_view(request):
    form = ContactUsForm(request.POST or None)
    if request.method == 'POST':

        if form.is_valid():
            form.save()
            messages.success(request,
                             'پیام شما با موفقیت ارسال گردید. پس از بررسی در صورت ثبت شماره تماس و یا ایمیل با شما ارتباط  خواهیم گرفت.')
            return redirect(reverse('contact_us'))
        else:
            messages.error(request, 'لطفا موارد ذیل را بررسی کنید.')

    context = {
        'form': form
    }
    return render(request, 'contact.html', context)


def about_us_view(request):
    return render(request, 'about.html')


def introduction_view(request):
    return render(request, 'introduction.html')


def articles_view(request):
    articles = Articles.objects.filter(is_active=True).order_by('-created_at')
    return render(request, 'articles.html', {'articles': articles})


def article_details_view(request, article_id):
    article = Articles.objects.get(pk=article_id)
    similar_articles = Articles.objects.filter(is_active=True).exclude(pk=article.pk)
    return render(request, 'article_details.html', {'article': article, 'similar_articles': similar_articles})
