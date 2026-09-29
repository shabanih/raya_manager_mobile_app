from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, ProtectedError, F, Count, Prefetch
from django.http import JsonResponse
from django.shortcuts import redirect, get_object_or_404, render
from django.urls import reverse_lazy, reverse
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.generic import CreateView, ListView, UpdateView
from django.views.generic.edit import FormMixin

from admin_panel.forms import MessageToUserForm, AdminMessageToMiddleForm
from admin_panel.models import MessageToUser, MessageReadStatus, AdminMessageToMiddle, MiddleMessageReadStatus
from admin_panel.views import admin_required
from middleAdmin_panel.views import middle_admin_required
from notifications.models import SupportUser, SupportFile, SupportMessage, Notification, AdminTicket, AdminTicketFile, \
    AdminTicketMessage, MiddleAdminNotification
from user_app.forms import SupportUserForm, SupportMessageForm, MiddleAdminTicketForm, MiddleAdminMessageForm
from user_app.models import User, Unit, MyHouse


@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class SupportUserCreateView(CreateView):
    model = SupportUser
    template_name = 'user_send_ticket.html'
    form_class = SupportUserForm
    success_url = reverse_lazy('tickets')

    def form_valid(self, form):
        # 1️⃣ ایجاد تیکت
        obj = form.save(commit=False)
        obj.user = self.request.user
        obj.is_sent = True
        obj.save()

        # 2️⃣ ذخیره فایل‌ها
        files = self.request.FILES.getlist('file')
        file_objects = [SupportFile.objects.create(support_user=obj, file=f) for f in files]

        # 3️⃣ ایجاد پیام اولیه
        initial_message = form.cleaned_data.get('message')
        if initial_message:
            msg = SupportMessage.objects.create(
                support_user=obj,
                sender=self.request.user,
                message=initial_message,
                is_read=False  # پیام هنوز توسط مدیر خوانده نشده
            )
            for fobj in file_objects:
                msg.attachments.add(fobj)

        channel_layer = get_channel_layer()

        # فقط مدیر مربوط به کاربر
        middle_admin = obj.user.manager  # obj = SupportUser که الان ایجاد شده
        if middle_admin and middle_admin.is_middle_admin:
            # نوتیفیکیشن (اختیاری)
            Notification.objects.create(
                user=middle_admin,
                ticket=obj,
                title="تیکت جدید",
                message=f"یک پیام جدید از کاربر {self.request.user.mobile} دریافت شد.",
                link=f"/admin-panel/ticket/{obj.id}/"
            )
            # WebSocket broadcast
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{middle_admin.id}",
                {"type": "send_ticket_count"}
            )

        messages.success(
            self.request,
            'تیکت با موفقیت ارسال گردید. پس از بررسی پاسخ داده خواهد شد.'
        )
        return redirect(self.success_url)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['tickets'] = SupportUser.objects.filter(user=self.request.user).order_by('-created_at')
        return context


@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class TicketsView(ListView):
    model = SupportUser
    template_name = 'user_ticket.html'
    context_object_name = 'tickets'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None  # نمایش همه
        return int(paginate or 20)

    def get_queryset(self):
        query = self.request.GET.get('q', '')
        qs = SupportUser.objects.filter(user=self.request.user)
        if query:
            qs = qs.filter(
                Q(subject__icontains=query) |
                Q(message__icontains=query) |
                Q(ticket_no__icontains=query)
            )
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


@login_required
def user_ticket_detail(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk, user=request.user)
    form = SupportMessageForm()

    # پیام‌های مدیر به کاربر → به خوانده‌شده تبدیل شوند
    unread_admin_messages = SupportMessage.objects.filter(
        support_user=ticket,
        sender__is_middle_admin=True,
        is_read=False
    )

    if unread_admin_messages.exists():
        unread_admin_messages.update(is_read=True)

        # کانتر مدیر صفر شود → فقط مدیر مربوطه
        channel_layer = get_channel_layer()
        middle_admin = ticket.user.manager
        if middle_admin and middle_admin.is_middle_admin:
            async_to_sync(channel_layer.group_send)(
                f"user_{middle_admin.id}",
                {"type": "send_ticket_count"}
            )

    # ارسال پیام جدید توسط کاربر
    if request.method == 'POST':
        if ticket.is_closed:
            messages.error(request, "این تیکت بسته شده و نمی‌توانید پیام جدید ارسال کنید.")
            return redirect('ticket_detail', pk=ticket.id)

        form = SupportMessageForm(request.POST, request.FILES)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.support_user = ticket
            msg.sender = request.user
            msg.is_read = False  # پیام جدید کاربر → برای مدیر خوانده نشده
            msg.save()

            # ذخیره فایل اختیاری
            file_obj = request.FILES.get('file')
            if file_obj:
                file_instance = SupportFile.objects.create(file=file_obj, support_user=ticket)
                msg.attachments.add(file_instance)

            # وضعیت تیکت
            ticket.is_answer = False
            ticket.is_closed = False
            ticket.save()

            # نوتیفیکیشن و کانتر مدیر → فقط مدیر مربوطه
            channel_layer = get_channel_layer()
            middle_admin = ticket.user.manager
            if middle_admin and middle_admin.is_middle_admin:
                Notification.objects.create(
                    user=middle_admin,
                    ticket=ticket,
                    title="پیام جدید کاربر",
                    message=f"یک پیام جدید از کاربر {request.user.mobile} دریافت شد.",
                    link=f"/admin-panel/ticket/{ticket.id}/"
                )
                async_to_sync(channel_layer.group_send)(
                    f"user_{middle_admin.id}",
                    {"type": "send_ticket_count"}
                )

            return redirect('ticket_detail', pk=ticket.id)

    messages_list = ticket.messages.filter(support_user=ticket).order_by('-created_at')
    return render(request, 'user_ticket_details.html', {
        'ticket': ticket,
        'messages': messages_list,
        'form': form
    })


@login_required
def close_ticket(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    ticket.is_closed = True
    ticket.save()
    # messages.success(request, "تیکت بسته شد.")
    return redirect('ticket_detail', pk=ticket.id)


# =============================================
@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class MiddleTicketsView(ListView):
    model = SupportUser
    template_name = 'middle_tickets.html'
    context_object_name = 'tickets'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None  # نمایش همه
        return int(paginate or 20)

    def get_queryset(self):
        query = self.request.GET.get('q', '')
        managed_users = self.request.user.managed_users.all()
        qs = SupportUser.objects.filter(
            Q(user=self.request.user) | Q(user__in=managed_users)
        )
        if query:
            qs = qs.filter(
                Q(subject__icontains=query) |
                Q(message__icontains=query) |
                Q(ticket_no__icontains=query)
            )
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


@login_required
def middleAdmin_ticket_detail(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    form = SupportMessageForm()

    # پیام‌های کاربر که توسط مدیر هنوز خوانده نشده‌اند → خوانده شده شوند
    unread_messages = ticket.messages.filter(
        sender=ticket.user,
        is_read=False
    )
    if unread_messages.exists():
        unread_messages.update(is_read=True)

        # صفر کردن کانتر مدیر (WebSocket)
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"user_{request.user.id}",
            {"type": "send_ticket_count"}
        )

    if request.method == 'POST':
        form = SupportMessageForm(request.POST, request.FILES)
        if form.is_valid():
            # ایجاد پیام جدید توسط مدیر
            msg = form.save(commit=False)
            msg.support_user = ticket
            msg.sender = request.user
            msg.is_read = False  # پیام هنوز توسط کاربر خوانده نشده
            msg.save()

            # ذخیره فایل اختیاری
            file_obj = request.FILES.get('file')
            if file_obj:
                file_instance = SupportFile.objects.create(file=file_obj, support_user=ticket)
                msg.attachments.add(file_instance)

            # بروزرسانی وضعیت تیکت
            ticket.is_answer = True
            ticket.is_closed = False
            ticket.save()

            # 🔥 ارسال کانتر به کاربر (فقط کاربر دریافت می‌کند)
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"user_{ticket.user.id}",
                {"type": "send_ticket_count"}
            )

            return redirect('middleAdmin_ticket_detail', pk=ticket.id)

    messages_list = ticket.messages.filter(support_user=ticket).order_by('-created_at')

    return render(request, 'middle_ticket_detail.html', {
        'ticket': ticket,
        'messages_list': messages_list,
        'form': form
    })


@login_required
def middle_close_ticket(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    ticket.is_closed = True
    ticket.save()
    # messages.success(request, "تیکت بسته شد.")
    return redirect('middleAdmin_ticket_detail', pk=ticket.id)


@login_required
def middle_open_ticket(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    ticket.is_closed = False
    ticket.save()
    # messages.success(request, "تیکت باز شد.")
    return redirect('middleAdmin_ticket_detail', pk=ticket.id)


@login_required
def middle_is_waiting(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    ticket.is_waiting = True
    ticket.save()
    return redirect('middleAdmin_ticket_detail', pk=ticket.id)


@login_required
def middle_is_continue(request, pk):
    ticket = get_object_or_404(SupportUser, id=pk)
    ticket.is_waiting = False
    ticket.save()
    return redirect('middleAdmin_ticket_detail', pk=ticket.id)


# =================================================
@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class MiddleAdminTicketCreateView(CreateView):
    model = AdminTicket
    template_name = 'middleAdmin_send_ticket.html'
    form_class = MiddleAdminTicketForm
    success_url = reverse_lazy('middleAdmin_tickets')

    def form_valid(self, form):
        # 1️⃣ ایجاد تیکت
        obj = form.save(commit=False)
        obj.user = self.request.user
        house = MyHouse.objects.filter(user=self.request.user).first()
        obj.house = house
        obj.is_sent = True
        # 👇 اختصاص ادمین (فرض می‌کنیم تنها یک ادمین داریم)
        obj.assigned_admin = User.objects.filter(is_superuser=True).first()
        obj.middle_admin = self.request.user
        obj.save()

        # 2️⃣ ذخیره فایل‌ها
        files = self.request.FILES.getlist('file')
        file_objects = [AdminTicketFile.objects.create(ticket=obj, file=f) for f in files]

        # 3️⃣ پیام اولیه
        initial_message = form.cleaned_data.get('message')
        if initial_message:
            msg = AdminTicketMessage.objects.create(
                ticket=obj,
                sender=self.request.user,
                message=initial_message,
                is_read=False
            )
            for fobj in file_objects:
                msg.attachments.add(fobj)

        # 4️⃣ نوتیفیکیشن فقط برای ادمین اختصاصی
        if obj.assigned_admin:
            MiddleAdminNotification.objects.create(
                user=obj.assigned_admin,
                ticket=obj,
                title="تیکت جدید از مدیر میانی",
                message=f"یک پیام جدید از {self.request.user.full_name} دریافت شد.",
                link=f"/admin-panel/admin_ticket/{obj.id}/"
            )

            # 🔥 بروزرسانی کانتر WebSocket
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "admins_group",
                {"type": "send_admin_ticket_count"}
            )

        messages.success(
            self.request,
            'تیکت با موفقیت ارسال شد. کارشناسان ما پس از بررسی طی 3 تا 5 ساعت آینده پاسخ خواهند داد.'
        )
        return redirect(self.success_url)


@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class MiddleAdminTicketsView(ListView):
    model = AdminTicket
    template_name = 'middleAdmin_ticket.html'
    context_object_name = 'middleTickets'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None  # نمایش همه
        return int(paginate or 20)

    def get_queryset(self):
        query = self.request.GET.get('q', '')
        qs = AdminTicket.objects.filter(user=self.request.user)
        if query:
            qs = qs.filter(
                Q(subject__icontains=query) |
                Q(message__icontains=query) |
                Q(ticket_no__icontains=query)
            )
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


@login_required
def MiddleAdmin_ticket_detail(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)

    if ticket.middle_admin != request.user:
        messages.error(request, "شما اجازه ارسال پیام در این تیکت را ندارید.")
        return redirect('middleAdmin_tickets')

    form = MiddleAdminMessageForm()

    # پیام‌های ادمین که هنوز خوانده نشده‌اند → خوانده شوند
    unread_admin_messages = ticket.messages.filter(
        sender__is_superuser=True,
        is_read=False
    )
    if unread_admin_messages.exists():
        unread_admin_messages.update(is_read=True)

        # بروزرسانی کانتر WebSocket همان مدیر میانی
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f"middle_admin_group_{request.user.id}",
            {"type": "send_admin_ticket_count"}
        )

    if request.method == 'POST':
        form = MiddleAdminMessageForm(request.POST, request.FILES)
        if form.is_valid():
            msg = form.save(commit=False)
            msg.ticket = ticket
            msg.sender = request.user
            msg.is_read = False
            msg.save()

            for f in request.FILES.getlist('file'):
                file_instance = AdminTicketFile.objects.create(file=f, ticket=ticket)
                msg.attachments.add(file_instance)

            ticket.is_answer = True
            ticket.is_closed = False
            ticket.save()

            MiddleAdminNotification.objects.create(
                user=ticket.middle_admin,
                ticket=ticket,
                title="پیام جدید از مدیر میانی",
                message="یک پیام جدید از مدیر میانی دریافت شد.",
                link=f"/middle-admin/admin_ticket/{ticket.id}/"
            )

            # ارسال نوتیف به ادمین ها
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                "admins_group",
                {"type": "send_admin_ticket_count"}
            )

            return redirect('MAdmin_ticket_detail', pk=ticket.id)

    messages_list = ticket.messages.all().order_by('-created_at')

    return render(request, 'middleAdmin_ticket_detail.html', {
        'ticket': ticket,
        'messages_list': messages_list,
        'form': form
    })


@login_required
def middlAdmin_close_ticket(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)
    ticket.is_closed = True
    ticket.save()
    # messages.success(request, "تیکت بسته شد.")
    return redirect('middleAdmin_ticket_detail', pk=ticket.id)


# -------------------------------------------------------------------------------
@method_decorator(admin_required, name='dispatch')
class AdminTicketsView(ListView):
    model = AdminTicket
    template_name = 'admin_tickets.html'
    context_object_name = 'admin_tickets'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None  # نمایش همه
        return int(paginate or 20)

    def get_queryset(self):
        query = self.request.GET.get('q', '')
        qs = AdminTicket.objects.filter(user__is_middle_admin=True).select_related('user')
        if query:
            qs = qs.filter(
                Q(subject__icontains=query) |
                Q(message__icontains=query) |
                Q(ticket_no__icontains=query)
            )
        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        return context


@login_required
def admin_ticket_detail(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)

    # فقط ادمین اجازه دارد
    if not request.user.is_superuser:
        messages.error(request, "اجازه دسترسی ندارید.")
        return redirect('admin_tickets')

    form = MiddleAdminMessageForm()

    # پیام‌های خوانده‌نشده مدیر میانی → باید توسط ادمین خوانده شوند
    unread_messages = ticket.messages.filter(
        sender__is_middle_admin=True,
        is_read=False
    )

    if unread_messages.exists():
        unread_messages.update(is_read=True)

        # بروزرسانی کانتر مدیر میانی
        if ticket.middle_admin:
            channel_layer = get_channel_layer()
            async_to_sync(channel_layer.group_send)(
                f"middle_admin_group_{ticket.middle_admin.id}",
                {"type": "send_admin_ticket_count"}
            )

    if request.method == 'POST':
        form = MiddleAdminMessageForm(request.POST, request.FILES)
        if form.is_valid():

            msg = form.save(commit=False)
            msg.ticket = ticket
            msg.sender = request.user  # ادمین
            msg.is_read = False
            msg.save()

            # ذخیره فایل‌ها
            for f in request.FILES.getlist('file'):
                file_instance = AdminTicketFile.objects.create(file=f, ticket=ticket)
                msg.attachments.add(file_instance)

            ticket.is_answer = True
            ticket.is_closed = False
            ticket.save()

            # نوتیفیکیشن برای مدیر میانی
            if ticket.middle_admin:
                MiddleAdminNotification.objects.create(
                    user=ticket.middle_admin,
                    ticket=ticket,
                    title="پیام جدید از ادمین",
                    message=f"ادمین یک پیام جدید برای تیکت #{ticket.ticket_no} ارسال کرد.",
                    link=f"/middle-admin/admin_ticket/{ticket.id}/"
                )

                # آپدیت کانتر مدیر میانی
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"middle_admin_group_{ticket.middle_admin.id}",
                    {"type": "send_admin_ticket_count"}
                )

            return redirect('admin_ticket_detail', pk=ticket.id)

    messages_list = ticket.messages.all().order_by('-created_at')

    return render(request, 'admin_ticket_detail.html', {
        'ticket': ticket,
        'messages_list': messages_list,
        'form': form
    })


@login_required
def admin_close_ticket(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)
    ticket.is_closed = True
    ticket.save()
    # messages.success(request, "تیکت بسته شد.")
    return redirect('admin_ticket_detail', pk=ticket.id)


@login_required
def admin_open_ticket(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)
    ticket.is_closed = False
    ticket.save()
    # messages.success(request, "تیکت باز شد.")
    return redirect('admin_ticket_detail', pk=ticket.id)


@login_required
def admin_is_waiting(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)
    ticket.is_waiting = True
    ticket.save()
    return redirect('admin_ticket_detail', pk=ticket.id)


@login_required
def admin_is_continue(request, pk):
    ticket = get_object_or_404(AdminTicket, id=pk)
    ticket.is_waiting = False
    ticket.save()
    return redirect('admin_ticket_detail', pk=ticket.id)


# ========================= Message To User ======
@method_decorator(login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN), name='dispatch')
class MessageToUserListCreateView(CreateView):
    model = MessageToUser
    form_class = MessageToUserForm
    template_name = 'message_to_user.html'
    success_url = reverse_lazy('message_middle_to_user')

    def form_valid(self, form):
        message = form.save(commit=False)
        message.user = self.request.user
        message.save()  # بدون اختصاص واحدها
        messages.success(self.request, 'پیام با موفقیت ثبت شد.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        all_messages = MessageToUser.objects.filter(user=self.request.user,
                                                    send_notification=False).order_by(
            '-created_at')
        context['all_messages'] = all_messages
        context['units'] = Unit.objects.all()
        paginate_by = self.request.GET.get('paginate', '20')

        if paginate_by == '1000':  # نمایش همه
            paginator = Paginator(all_messages, all_messages.count() or 20)
        else:
            paginate_by = int(paginate_by)
            paginator = Paginator(all_messages, paginate_by)

        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['charges'] = page_obj
        context['page_obj'] = page_obj
        context['paginate'] = paginate_by

        return context


@method_decorator(middle_admin_required, name='dispatch')
class MiddleMessageUpdateView(UpdateView):
    model = MessageToUser
    form_class = MessageToUserForm
    template_name = 'message_to_user.html'
    success_url = reverse_lazy('message_middle_to_user')

    def form_valid(self, form):
        edit_instance = form.instance
        self.object = form.save(commit=False)
        messages.success(self.request, 'پیامک با موفقیت ویرایش گردید!')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['all_messages'] = MessageToUser.objects.filter(
            is_active=True,
            user=self.request.user,
            send_notification=False
        ).order_by('-created_at')
        return context


@login_required
def message_user_delete(request, pk):
    message = get_object_or_404(MessageToUser, id=pk)
    try:
        message.delete()
        messages.success(request, 'پیام با موفقیت حذف گردید!')
    except ProtectedError:
        messages.error(request, " امکان حذف وجود ندارد! ")
    return redirect(reverse('message_middle_to_user'))


@login_required
def message_user_delete_list(request, pk):
    message = get_object_or_404(MessageToUser, id=pk)
    try:
        message.delete()
        messages.success(request, 'پیام با موفقیت حذف گردید!')
    except ProtectedError:
        messages.error(request, " امکان حذف وجود ندارد! ")
    return redirect(reverse('message_management_for_middle'))


@login_required
def middle_show_message_form(request, pk):
    managed_users = request.user.managed_users.all()
    message = get_object_or_404(MessageToUser, id=pk, user=request.user)
    house = MyHouse.objects.filter(user=request.user).first()
    units = Unit.objects.filter(Q(user=request.user) | Q(user__in=managed_users),
                                is_active=True, myhouse=house).prefetch_related('renters').order_by('unit')
    units_with_details = []
    for unit in units:
        active_renter = unit.renters.filter(renter_is_active=True).first()
        units_with_details.append({
            'unit': unit,
            'active_renter': active_renter
        })
    all_messages = MessageToUser.objects.filter(user=request.user,
                                                send_notification=False, pk=pk).order_by(
        '-created_at')

    return render(request, 'middle_send_message.html', {
        'message': message,
        'units_with_details': units_with_details,
        'all_messages': all_messages
    })


@login_required(login_url=settings.LOGIN_URL_MIDDLE_ADMIN)
def middle_send_message(request, pk):
    managed_users = request.user.managed_users.all()
    message = get_object_or_404(MessageToUser, id=pk, user=request.user)

    if request.method == "POST":
        selected_units = request.POST.getlist('units')
        if not selected_units:
            messages.warning(request, 'هیچ واحدی انتخاب نشده است.')
            return redirect('message_middle_to_user')

        units_qs = Unit.objects.filter(Q(user=request.user) | Q(user__in=managed_users),
                                       is_active=True)

        if 'all' in selected_units:
            units_to_notify = units_qs
        else:
            units_to_notify = units_qs.filter(id__in=selected_units)

        # فقط واحدهایی که کاربر و موبایل دارند
        units_to_notify = units_to_notify.filter(user__isnull=False, user__mobile__isnull=False)

        if not units_to_notify.exists():
            messages.warning(request, 'هیچ واحد معتبری برای ارسال پیامک پیدا نشد.')
            return redirect('message_middle_to_user')

        with transaction.atomic():
            notified_units = list(units_to_notify)

            message.notified_units.set(notified_units)
            message.send_notification = True
            message.send_notification_date = timezone.now()
            message.save()

            for unit in notified_units:
                MessageReadStatus.objects.get_or_create(
                    message=message,
                    unit=unit,
                    defaults={'is_read': False}
                )

            # 👇 فقط یک پیام کلی
            messages.success(
                request,
                f"پیام برای {len(notified_units)} واحد ارسال شد."
            )

        return redirect('message_management_for_middle')

    units_with_details = Unit.objects.filter(is_active=True)
    return render(request, 'middle_send_message.html', {
        'message': message,
        'units_with_details': units_with_details,
    })


@method_decorator(middle_admin_required, name='dispatch')
class MiddleMessageToUserListView(ListView):
    model = MessageToUser
    template_name = 'middle_message_management.html'
    context_object_name = 'all_messages'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None
        return int(paginate or 20)

    def get_queryset(self):
        query = self.request.GET.get('q', '')

        # Prefetch read_statuses و unit مرتبط
        read_statuses_prefetch = Prefetch(
            'read_statuses',
            queryset=MessageReadStatus.objects.select_related('unit__user')
            .prefetch_related('unit__renters')
        )

        qs = MessageToUser.objects.filter(
            user=self.request.user,
            is_active=True,
            send_notification=True
        ).annotate(
            sent_users_count=Count('notified_units', distinct=True)
        ).prefetch_related(
            'notified_units',  # در صورت نیاز به جدول قدیمی
            read_statuses_prefetch  # اینجا وضعیت واحدها را آماده می‌کنیم
        )

        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(message__icontains=query)
            )

        return qs.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['paginate'] = self.request.GET.get('paginate', '20')
        return context


# ========================= Message admin to middleAdmin ===============
@method_decorator(admin_required, name='dispatch')
class AdminMessageToMiddleListCreateView(CreateView):
    model = AdminMessageToMiddle
    form_class = AdminMessageToMiddleForm
    template_name = 'message_send_admin_to_middle.html'
    success_url = reverse_lazy('message_admin_to_middle')

    def form_valid(self, form):
        msg = form.save(commit=False)
        msg.sender = self.request.user  # فرستنده
        msg.save()
        form.save_m2m()

        messages.success(self.request, 'پیام با موفقیت ثبت شد.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        all_messages = AdminMessageToMiddle.objects.filter(
            sender=self.request.user,
            is_active=True,
            send_notification=False
        ).order_by('-created_at')

        paginator = Paginator(all_messages, 20)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['all_messages'] = page_obj
        context['middle_admins'] = User.objects.filter(is_staff=True)

        return context


@method_decorator(admin_required, name='dispatch')
class AdminMessageToMiddleUpdateView(UpdateView):
    model = AdminMessageToMiddle
    form_class = AdminMessageToMiddleForm
    template_name = 'message_send_admin_to_middle.html'
    success_url = reverse_lazy('message_admin_to_middle')

    def form_valid(self, form):
        messages.success(self.request, 'پیام ویرایش شد.')
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        all_messages = AdminMessageToMiddle.objects.filter(
            sender=self.request.user,
            is_active=True
        ).order_by('-created_at')

        paginator = Paginator(all_messages, 20)
        page_number = self.request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context['all_messages'] = page_obj
        context['middle_admins'] = User.objects.filter(is_staff=True)

        return context


@login_required
def admin_message_delete(request, pk):
    msg = get_object_or_404(AdminMessageToMiddle, pk=pk)

    try:
        msg.delete()
        messages.success(request, 'پیام حذف شد.')
    except ProtectedError:
        messages.error(request, 'امکان حذف وجود ندارد.')

    return redirect('admin_message_management')


@login_required
def admin_show_send_form(request, pk):
    message = get_object_or_404(AdminMessageToMiddle, pk=pk)

    middle_admins = User.objects.filter(is_middle_admin=True)

    return render(request, 'admin_send_message.html', {
        'message': message,
        'middle_admins': middle_admins
    })


@login_required
def admin_send_message(request, pk):
    message = get_object_or_404(AdminMessageToMiddle, pk=pk)

    if request.method == "POST":
        selected = request.POST.getlist('users')  # لیست id مدیران

        if not selected:
            messages.warning(request, 'هیچ مدیری انتخاب نشد.')
            return redirect('message_admin_to_middle')

        users = User.objects.filter(
            id__in=selected,
            is_middle_admin=True
        )

        with transaction.atomic():
            # ثبت مدیران انتخاب‌شده
            message.middleAdmins.set(users)

            # ثبت وضعیت خوانده شدن
            for user in users:
                MiddleMessageReadStatus.objects.get_or_create(
                    message=message,
                    user=user,
                    defaults={'is_read': False}
                )

            # ثبت اینکه پیام ارسال شده
            message.send_notification = True
            message.send_notification_date = timezone.now()
            message.save()

        messages.success(
            request,
            f"پیام برای {users.count()} مدیر ارسال شد."
        )

        return redirect('admin_message_management')

    return redirect('message_admin_to_middle')


@method_decorator(admin_required, name='dispatch')
class AdminMessageToMiddleListView(ListView):
    model = AdminMessageToMiddle
    template_name = 'admin_message_management.html'
    context_object_name = 'all_messages'
    paginate_by = 20

    def get_queryset(self):
        qs = AdminMessageToMiddle.objects.filter(
            sender=self.request.user,
            is_active=True
        ).annotate(
            sent_count=Count('middleAdmins', distinct=True)
        ).prefetch_related(
            Prefetch(
                'read_statuses',
                queryset=MiddleMessageReadStatus.objects.select_related('user')
            )
        )

        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(
                Q(title__icontains=query) |
                Q(message__icontains=query)
            )

        return qs.order_by('-created_at')


@method_decorator(middle_admin_required, name='dispatch')
class MiddleMessageListView(ListView):
    template_name = 'middle_message_from_admin.html'
    context_object_name = 'middle_messages'

    def get_paginate_by(self, queryset):
        paginate = self.request.GET.get('paginate')
        if paginate == '1000':
            return None  # نمایش همه آیتم‌ها
        return int(paginate or 20)

    def get_queryset(self):
        user = self.request.user
        query = self.request.GET.get('q', '')

        # Prefetch read_status برای کاربر جاری
        read_status_prefetch = Prefetch(
            'read_statuses',
            queryset=MiddleMessageReadStatus.objects.filter(user=user)
        )

        queryset = AdminMessageToMiddle.objects.filter(
            middleAdmins=user,
            is_active=True
        ).prefetch_related(read_status_prefetch)

        # آپدیت وضعیت خوانده شده
        for msg in queryset:
            status, created = MiddleMessageReadStatus.objects.get_or_create(
                message=msg,
                user=user
            )
            if not status.is_read:
                status.is_read = True
                status.read_at = timezone.now()
                status.save()

        # فیلتر جستجو
        if query:
            queryset = queryset.filter(
                Q(sender__full_name__icontains=query) |
                Q(title__icontains=query) |
                Q(message__icontains=query)
            ).distinct()

        return queryset.order_by('-created_at')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['query'] = self.request.GET.get('q', '')
        context['paginate'] = self.request.GET.get('paginate', '20')
        return context
