from django.db.models import Q
from rest_framework import serializers

from admin_panel.models import UnifiedCharge, Fund, Announcement, CivilManage, CivilInstallment, SewageInstallment, \
    SewageManage, MessageToUser, AnnouncementDocument, BankFund
from notifications.models import SupportFile, SupportMessage, SupportUser, Notification, AdminTicketFile, \
    AdminTicketMessage, AdminTicket, MiddleAdminNotification
from polls_app.models import Choice, Question, Poll, Vote
from user_app.models import Unit, MyHouse, User, Bank, UserPayMoney, Renter


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(
        required=True,
        max_length=150
    )

    password = serializers.CharField(
        required=True,
        write_only=True
    )


class UserMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'full_name',
            'mobile',
            'is_unit',
            'is_resident',
            'is_middle_admin',
            'house_id',
        ]


class HouseMeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MyHouse
        fields = [
            'id',
            'name',
            'city',
            'address',
            'phone',
        ]


class UnitMeSerializer(serializers.ModelSerializer):
    is_renter = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = [
            'id',
            'unit',
            'floor_number',
            'area',
            'bedrooms_count',
            'parking_number',
            'owner_name',
            'owner_mobile',
            'is_renter',
            'is_active',
        ]

    def get_is_renter(self, obj):
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
            return False

        return obj.renters.filter(
            user=request.user,
            renter_is_active=True
        ).exists()


class ManualChargePaymentSerializer(serializers.Serializer):
    transaction_reference = serializers.CharField(
        max_length=20,
        required=True
    )

    payment_date = serializers.DateField(
        required=True
    )

    bank_id = serializers.IntegerField(
        required=True
    )

    def validate(self, attrs):

        request = self.context['request']
        user = request.user

        charge_id = self.context.get('charge_id')

        # =====================================================
        # پیدا کردن شارژ
        #
        # کاربر می‌تواند:
        #
        # 1. مالک/کاربر اصلی واحد باشد
        #
        # 2. مستأجر فعال واحد باشد
        # =====================================================

        charge = UnifiedCharge.objects.filter(
            Q(
                unit__user=user
            )
            |
            Q(
                unit__renters__user=user,
                unit__renters__renter_is_active=True,
            ),
            id=charge_id,
            is_paid=False,
            send_notification=True,
            unit__is_active=True,
        ).select_related(
            'unit',
            'house',
        ).distinct().first()

        # =====================================================
        # شارژ پیدا نشد
        # =====================================================

        if not charge:
            raise serializers.ValidationError(
                'شارژ مورد نظر پیدا نشد یا متعلق به شما نیست.'
            )

        # =====================================================
        # اگر پرداخت قبلی در انتظار تأیید است
        # =====================================================

        if charge.payment_pending:
            raise serializers.ValidationError(
                'درخواست پرداخت این شارژ قبلاً ثبت شده '
                'و در انتظار تأیید مدیر ساختمان است.'
            )

        # =====================================================
        # پیدا کردن حساب بانکی ساختمان
        # =====================================================

        bank = Bank.objects.filter(
            id=attrs['bank_id'],
            house=charge.house,
            is_active=True,
        ).first()

        if not bank:
            raise serializers.ValidationError(
                'حساب بانکی معتبر برای این ساختمان پیدا نشد.'
            )

        # =====================================================
        # بررسی نهایی پرداخت
        # =====================================================

        if charge.is_paid:
            raise serializers.ValidationError(
                'این شارژ قبلاً پرداخت شده است.'
            )

        # =====================================================
        # قرار دادن اطلاعات در validated_data
        # =====================================================

        attrs['charge'] = charge
        attrs['bank'] = bank

        return attrs


class MobileChargeListSerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()

    house_name = serializers.CharField(
        source='house.name',
        read_only=True
    )

    total_charge = serializers.SerializerMethodField()
    previous_debt = serializers.SerializerMethodField()
    payable_amount = serializers.SerializerMethodField()
    payment_deadline = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedCharge

        fields = [
            'id',

            'unit_id',
            'unit_number',

            'house_id',
            'house_name',

            'charge_type',
            'title',
            'details',

            'base_charge',
            'penalty_amount',
            'total_charge',

            'previous_debt',
            'payable_amount',

            'payment_deadline',

            'is_paid',
            'payment_pending',
            'payment_date',

            'send_notification',
            'created_at',
        ]

    def get_unit_number(self, obj):
        if not obj.unit:
            return None

        return getattr(
            obj.unit,
            'unit_number',
            None
        )

    def get_total_charge(self, obj):
        return (
                obj.total_charge_month
                or obj.amount
                or 0
        )

    def get_previous_debt(self, obj):
        return obj.total_previous_debt or 0

    def get_payable_amount(self, obj):
        return obj.total_payable_with_previous or 0

    def get_payment_deadline(self, obj):
        return obj.payment_deadline_date


class MobileChargeDetailSerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()

    house_name = serializers.CharField(
        source='house.name',
        read_only=True
    )

    total_charge = serializers.SerializerMethodField()
    previous_debt = serializers.SerializerMethodField()
    payable_amount = serializers.SerializerMethodField()
    payment_deadline = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedCharge

        fields = [
            'id',

            'house_id',
            'house_name',

            'unit_id',
            'unit_number',

            'charge_type',
            'title',
            'details',

            'base_charge',
            'penalty_amount',
            'total_charge',

            'previous_debt',
            'payable_amount',

            'payment_deadline',

            'is_paid',
            'payment_pending',
            'payment_date',

            'send_notification',
            'created_at',
        ]

    def get_unit_number(self, obj):
        if not obj.unit:
            return None

        return getattr(
            obj.unit,
            'unit_number',
            None
        )

    def get_total_charge(self, obj):
        return (
                obj.total_charge_month
                or obj.amount
                or 0
        )

    def get_previous_debt(self, obj):
        return obj.total_previous_debt or 0

    def get_payable_amount(self, obj):
        return obj.total_payable_with_previous or 0

    def get_payment_deadline(self, obj):
        return obj.payment_deadline_date


class MobilePaymentHistorySerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()
    house_name = serializers.SerializerMethodField()
    payer_type = serializers.SerializerMethodField()

    class Meta:
        model = Fund
        fields = [
            'id',
            'doc_number',
            'amount',
            'debtor_amount',
            'creditor_amount',
            'payment_date',
            'transaction_no',
            'payment_description',
            'payer_name',
            'receiver_name',
            'is_initial',
            'is_received_money',
            'is_paid_money',
            'is_paid',
            'unit_number',
            'house_name',
            'payer_type',
            'created_at',
        ]

    def get_unit_number(self, obj):
        if obj.unit:
            return obj.unit.unit

        return None

    def get_house_name(self, obj):
        if obj.house:
            return obj.house.name

        if obj.unit and obj.unit.myhouse:
            return obj.unit.myhouse.name

        return None

    def get_payer_type(self, obj):
        if not obj.unit:
            return None

        if obj.unit.is_renter:
            renter = obj.unit.get_active_renter()

            if renter:
                return 'renter'

        return 'owner'


class MobileAnnouncementDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AnnouncementDocument
        fields = [
            'id',
            'url',
            'uploaded_at',
        ]

    def get_url(self, obj):
        if obj.document:
            request = self.context.get('request')

            if request:
                return request.build_absolute_uri(
                    obj.document.url
                )

            return obj.document.url

        return None


class MobileAnnouncementSerializer(serializers.ModelSerializer):
    documents = MobileAnnouncementDocumentSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'created_at',
            'documents',
        ]


class ChoiceSerializer(serializers.ModelSerializer):
    vote_count = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = Choice
        fields = [
            'id',
            'title',
            'vote_count',
            'percentage',
        ]

    def get_vote_count(self, obj):
        return obj.vote_count()

    def get_percentage(self, obj):
        return obj.percentage()


class QuestionSerializer(serializers.ModelSerializer):
    choices = ChoiceSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Question
        fields = [
            'id',
            'title',
            'question_type',
            'order',
            'choices',
        ]


class PollListSerializer(serializers.ModelSerializer):
    has_voted = serializers.SerializerMethodField()

    # =====================================================
    # نوع شرکت‌کنندگان
    # =====================================================

    participant_type = serializers.CharField(
        read_only=True
    )

    # =====================================================
    # تعداد مالکین فعال
    # =====================================================

    owner_count = serializers.SerializerMethodField()

    # =====================================================
    # تعداد مستأجرین فعال
    # =====================================================

    renter_count = serializers.SerializerMethodField()

    # =====================================================
    # تعداد افراد مجاز به شرکت
    # =====================================================

    eligible_user_count = serializers.SerializerMethodField()

    class Meta:
        model = Poll
        fields = [
            'id',
            'title',
            'description',
            'start_date',
            'end_date',
            'is_active',
            'created_at',

            # شرکت‌کنندگان
            'participant_type',
            'owner_count',
            'renter_count',
            'eligible_user_count',

            # وضعیت رأی کاربر
            'has_voted',
        ]

    # =====================================================
    # تعداد مالکین فعال
    # =====================================================

    def get_owner_count(self, obj):

        return obj.house.units.filter(
            is_active=True
        ).count()

    # =====================================================
    # تعداد مستأجرین فعال
    # =====================================================

    def get_renter_count(self, obj):

        return Renter.objects.filter(
            myhouse=obj.house,
            unit__myhouse=obj.house,
            unit__is_active=True,
            renter_is_active=True,
        ).count()

    # =====================================================
    # تعداد افراد مجاز
    # =====================================================

    def get_eligible_user_count(self, obj):

        owner_count = self.get_owner_count(obj)
        renter_count = self.get_renter_count(obj)

        participant_type = (
                obj.participant_type or 'all'
        ).strip().lower()

        if participant_type == 'owners':
            return owner_count

        if participant_type == 'renters':
            return renter_count

        return owner_count + renter_count

    # =====================================================
    # آیا کاربر رأی داده؟
    # =====================================================

    def get_has_voted(self, obj):

        request = self.context.get(
            'request'
        )

        if not request:
            return False

        if not request.user.is_authenticated:
            return False

        return Vote.objects.filter(
            poll=obj,
            user=request.user,
        ).exists()


class PollDetailSerializer(serializers.ModelSerializer):
    questions = QuestionSerializer(
        many=True,
        read_only=True,
    )

    has_voted = serializers.SerializerMethodField()

    # =====================================================
    # نوع شرکت‌کنندگان
    # =====================================================

    participant_type = serializers.CharField(
        read_only=True
    )

    # =====================================================
    # تعداد مالکین فعال
    # =====================================================

    owner_count = serializers.SerializerMethodField()

    # =====================================================
    # تعداد مستأجرین فعال
    # =====================================================

    renter_count = serializers.SerializerMethodField()

    # =====================================================
    # تعداد افراد مجاز
    # =====================================================

    eligible_user_count = serializers.SerializerMethodField()

    class Meta:
        model = Poll
        fields = [
            'id',
            'title',
            'description',
            'start_date',
            'end_date',
            'is_active',
            'created_at',

            # شرکت‌کنندگان
            'participant_type',
            'owner_count',
            'renter_count',
            'eligible_user_count',

            # سؤالات
            'questions',

            # وضعیت رأی
            'has_voted',
        ]

    # =====================================================
    # تعداد مالکین فعال
    # =====================================================

    def get_owner_count(self, obj):

        return obj.house.units.filter(
            is_active=True
        ).count()

    # =====================================================
    # تعداد مستأجرین فعال
    # =====================================================

    def get_renter_count(self, obj):

        return Renter.objects.filter(
            myhouse=obj.house,
            unit__myhouse=obj.house,
            unit__is_active=True,
            renter_is_active=True,
        ).count()

    # =====================================================
    # تعداد افراد مجاز
    # =====================================================

    def get_eligible_user_count(self, obj):

        owner_count = self.get_owner_count(obj)
        renter_count = self.get_renter_count(obj)

        participant_type = (
                obj.participant_type or 'all'
        ).strip().lower()

        if participant_type == 'owners':
            return owner_count

        if participant_type == 'renters':
            return renter_count

        return owner_count + renter_count

    # =====================================================
    # آیا کاربر رأی داده؟
    # =====================================================

    def get_has_voted(self, obj):

        request = self.context.get(
            'request'
        )

        if not request:
            return False

        if not request.user.is_authenticated:
            return False

        return Vote.objects.filter(
            poll=obj,
            user=request.user,
        ).exists()


# ==================# Civil=================================
class ManualCivilPaymentSerializer(serializers.Serializer):
    transaction_reference = serializers.CharField(
        max_length=20,
        required=True,
    )

    payment_date = serializers.DateField(
        required=True,
    )

    bank_id = serializers.IntegerField(
        required=True,
    )

    def validate(self, attrs):

        request = self.context['request']
        user = request.user

        installment_id = self.context.get(
            'installment_id'
        )

        # =====================================================
        # پیدا کردن قسط
        # =====================================================

        installment = (
            CivilInstallment.objects
            .filter(
                Q(
                    unit__user=user
                )
                |
                Q(
                    unit__renters__user=user,
                    unit__renters__renter_is_active=True,
                ),
                id=installment_id,
                is_paid=False,
                unit__is_active=True,
                civil_manage__is_active=True,
            )
            .select_related(
                'unit',
                'house',
                'civil_manage',
            )
            .distinct()
            .first()
        )

        if not installment:
            raise serializers.ValidationError(
                'قسط مورد نظر پیدا نشد یا متعلق به شما نیست.'
            )

        # =====================================================
        # درخواست قبلی
        # =====================================================

        if installment.payment_pending:
            raise serializers.ValidationError(
                'درخواست پرداخت این قسط قبلاً ثبت شده '
                'و در انتظار تأیید مدیر ساختمان است.'
            )

        # =====================================================
        # حساب بانکی
        # =====================================================

        bank = Bank.objects.filter(
            id=attrs['bank_id'],
            house=installment.house,
            is_active=True,
        ).first()

        if not bank:
            raise serializers.ValidationError(
                'حساب بانکی معتبر برای این ساختمان پیدا نشد.'
            )

        # =====================================================
        # قرار دادن اطلاعات
        # =====================================================

        attrs['installment'] = installment
        attrs['bank'] = bank

        return attrs


class CivilManageSerializer(serializers.ModelSerializer):
    total_installments = serializers.SerializerMethodField()
    paid_installments_count = serializers.SerializerMethodField()

    class Meta:
        model = CivilManage
        fields = [
            'id',
            'name',
            'amount',
            'prepayment',
            'installment_count',
            'first_due_date',
            'details',
            'created_at',
            'is_active',
            'total_installments',
            'paid_installments_count',
        ]

    def get_total_installments(self, obj):
        if obj.prepayment and obj.prepayment > 0:
            return obj.installment_count + 1

        return obj.installment_count

    def get_paid_installments_count(self, obj):
        unit = self.context.get('unit')

        if not unit:
            return 0

        return CivilInstallment.objects.filter(
            civil_manage=obj,
            unit=unit,
            is_paid=True,
        ).count()


class CivilInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = CivilInstallment
        fields = [
            'id',
            'civil_manage',
            'unit',
            'installment_number',
            'amount',
            'prepayment_per_unit',
            'due_date',
            'is_paid',
            'payment_pending',
            'payment_submitted_at',
            'transaction_reference',
            'payment_date',
            'payment_gateway',
            'send_notification',
        ]


# ================# Sewage==========================================
class ManualSewagePaymentSerializer(serializers.Serializer):
    transaction_reference = serializers.CharField(
        max_length=20,
        required=True,
    )

    payment_date = serializers.DateField(
        required=True,
    )

    bank_id = serializers.IntegerField(
        required=True,
    )

    def validate(self, attrs):

        request = self.context['request']
        user = request.user

        installment_id = self.context.get(
            'installment_id'
        )

        # =====================================================
        # پیدا کردن قسط
        # =====================================================

        installment = (
            SewageInstallment.objects
            .filter(
                Q(
                    unit__user=user
                )
                |
                Q(
                    unit__renters__user=user,
                    unit__renters__renter_is_active=True,
                ),
                id=installment_id,
                is_paid=False,
                unit__is_active=True,
                sewage_manage__is_active=True,
            )
            .select_related(
                'unit',
                'house',
                'sewage_manage',
            )
            .distinct()
            .first()
        )

        if not installment:
            raise serializers.ValidationError(
                'قسط مورد نظر پیدا نشد یا متعلق به شما نیست.'
            )

        # =====================================================
        # درخواست قبلی
        # =====================================================

        if installment.payment_pending:
            raise serializers.ValidationError(
                'درخواست پرداخت این قسط قبلاً ثبت شده '
                'و در انتظار تأیید مدیر ساختمان است.'
            )

        # =====================================================
        # حساب بانکی
        # =====================================================

        bank = Bank.objects.filter(
            id=attrs['bank_id'],
            house=installment.house,
            is_active=True,
        ).first()

        if not bank:
            raise serializers.ValidationError(
                'حساب بانکی معتبر برای این ساختمان پیدا نشد.'
            )

        # =====================================================
        # قرار دادن اطلاعات
        # =====================================================

        attrs['installment'] = installment
        attrs['bank'] = bank

        return attrs


class SewageManageSerializer(serializers.ModelSerializer):
    total_installments = serializers.SerializerMethodField()
    paid_installments_count = serializers.SerializerMethodField()

    class Meta:
        model = SewageManage
        fields = [
            'id',
            'name',
            'amount',
            'prepayment',
            'installment_count',
            'first_due_date',
            'details',
            'created_at',
            'is_active',
            'total_installments',
            'paid_installments_count',
        ]

    def get_total_installments(self, obj):
        if obj.prepayment and obj.prepayment > 0:
            return obj.installment_count + 1

        return obj.installment_count

    def get_paid_installments_count(self, obj):
        unit = self.context.get('unit')

        if not unit:
            return 0

        return SewageInstallment.objects.filter(
            sewage_manage=obj,
            unit=unit,
            is_paid=True,
        ).count()


class SewageInstallmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = SewageInstallment
        fields = [
            'id',
            'sewage_manage',
            'unit',
            'installment_number',
            'amount',
            'prepayment_per_unit',
            'due_date',
            'is_paid',
            'payment_pending',
            'payment_submitted_at',
            'transaction_reference',
            'payment_date',
            'payment_gateway',
            'send_notification',
        ]


# =====================MessageToUser=====================================
class MessageToUserSerializer(serializers.ModelSerializer):
    is_read = serializers.SerializerMethodField()
    read_at = serializers.SerializerMethodField()

    class Meta:
        model = MessageToUser
        fields = [
            'id',
            'title',
            'message',
            'created_at',
            'is_read',
            'read_at',
        ]

    def get_is_read(self, obj):
        return self.context.get(
            'message_read_status',
            {}
        ).get(obj.id, {}).get(
            'is_read',
            False
        )

    def get_read_at(self, obj):
        return self.context.get(
            'message_read_status',
            {}
        ).get(obj.id, {}).get(
            'read_at'
        )


# =================# pay money=============================================

class UserPayMoneySerializer(serializers.ModelSerializer):
    unit_number = serializers.SerializerMethodField()
    house_name = serializers.SerializerMethodField()
    bank_name = serializers.SerializerMethodField()
    documents = serializers.SerializerMethodField()

    class Meta:
        model = UserPayMoney

        fields = [
            'id',

            'amount',
            'description',
            'details',
            'payer_name',

            'register_date',
            'payment_date',

            'is_paid',
            'transaction_reference',
            'payment_gateway',

            'unit',
            'unit_number',

            'house',
            'house_name',

            'bank',
            'bank_name',

            'created_at',
            'is_active',

            'documents',
        ]

        read_only_fields = [
            'id',
            'user',
            'unit',
            'house',
            'is_paid',
            'transaction_reference',
            'payment_gateway',
            'payment_date',
            'bank',
            'created_at',
            'is_active',
        ]

    def get_unit_number(self, obj):
        if not obj.unit:
            return None

        return obj.unit.unit

    def get_house_name(self, obj):
        if obj.house:
            return obj.house.name

        if obj.unit and obj.unit.myhouse:
            return obj.unit.myhouse.name

        return None

    def get_bank_name(self, obj):
        if obj.bank:
            return obj.bank.bank_name

        return None

    def get_documents(self, obj):
        request = self.context.get('request')

        result = []

        for document in obj.documents.all():

            if not document.document:
                continue

            url = document.document.url

            if request:
                url = request.build_absolute_uri(url)

            result.append({
                'id': document.id,
                'url': url,
                'uploaded_at': document.uploaded_at,
            })

        return result


class CreateUserPayMoneySerializer(serializers.Serializer):
    amount = serializers.IntegerField(
        required=True,
        min_value=1,
    )

    description = serializers.CharField(
        required=True,
        max_length=4000,
    )

    register_date = serializers.DateField(
        required=True,
    )

    details = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
    )

    payer_name = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=400,
    )


class ManualUserPayMoneyPaymentSerializer(serializers.Serializer):
    transaction_reference = serializers.CharField(
        max_length=20,
        required=True,
    )

    payment_date = serializers.DateField(
        required=True,
    )

    bank_id = serializers.IntegerField(
        required=True,
    )

    def validate(self, attrs):

        request = self.context['request']
        user = request.user

        payment_id = self.context.get('payment_id')

        # =====================================================
        # پیدا کردن کمک
        # =====================================================

        payment = (
            UserPayMoney.objects
            .filter(
                id=payment_id,
                user=user,
                is_active=True,
                is_paid=False,
            )
            .select_related(
                'unit',
                'house',
            )
            .first()
        )

        if not payment:
            raise serializers.ValidationError(
                'کمک مورد نظر پیدا نشد یا متعلق به شما نیست.'
            )

        # =====================================================
        # بررسی واحد
        # =====================================================

        if not payment.unit:
            raise serializers.ValidationError(
                'واحد مربوط به این کمک مشخص نیست.'
            )

        # =====================================================
        # بررسی مالک / مستأجر
        # =====================================================

        is_owner = (
                payment.unit.user_id == user.id
        )

        is_active_renter = Renter.objects.filter(
            unit=payment.unit,
            user=user,
            renter_is_active=True,
        ).exists()

        if not is_owner and not is_active_renter:
            raise serializers.ValidationError(
                'این کمک متعلق به شما نیست.'
            )

        # =====================================================
        # پیدا کردن بانک ساختمان
        # =====================================================

        bank = Bank.objects.filter(
            id=attrs['bank_id'],
            house=payment.house,
            is_active=True,
        ).first()

        if not bank:
            raise serializers.ValidationError(
                'حساب بانکی معتبر برای این ساختمان پیدا نشد.'
            )

        # =====================================================
        # اطلاعات
        # =====================================================

        attrs['payment'] = payment
        attrs['bank'] = bank

        return attrs


# ===================== Manager =================================

class ManagerAnnouncementDocumentSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AnnouncementDocument
        fields = [
            'id',
            'url',
            'uploaded_at',
        ]

    def get_url(self, obj):
        if not obj.document:
            return None

        request = self.context.get('request')

        if request:
            return request.build_absolute_uri(
                obj.document.url
            )

        return obj.document.url


class ManagerAnnouncementSerializer(serializers.ModelSerializer):
    documents = ManagerAnnouncementDocumentSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = Announcement
        fields = [
            'id',
            'title',
            'show_in_marquee',
            'is_active',
            'created_at',
            'documents',
        ]


# ===================== Manager Messages =========================


class ManagerMessageUnitSerializer(serializers.ModelSerializer):
    unit_id = serializers.IntegerField(
        source='id',
        read_only=True
    )

    recipient_type = serializers.SerializerMethodField()

    recipient_name = serializers.SerializerMethodField()

    mobile = serializers.SerializerMethodField()

    has_mobile = serializers.SerializerMethodField()

    class Meta:
        model = Unit

        fields = [
            'id',
            'unit_id',
            'unit',
            'recipient_type',
            'recipient_name',
            'mobile',
            'has_mobile',
        ]

    def _get_renter(self, obj):

        renter = getattr(
            obj,
            '_active_renter',
            None
        )

        if renter:
            return renter

        return getattr(
            obj,
            '_message_renter',
            None
        )

    def get_recipient_type(self, obj):

        recipient_type = getattr(
            obj,
            '_recipient_type',
            None
        )

        if recipient_type:
            return recipient_type

        renter = self._get_renter(obj)

        if renter:
            return 'renter'

        return 'owner'

    def get_recipient_name(self, obj):

        renter = self._get_renter(obj)

        # =====================================================
        # مستأجر
        # =====================================================

        if renter:
            renter_user = renter.user

            return (
                    renter.renter_name
                    or (
                        renter_user.full_name
                        if renter_user
                        else ''
                    )
                    or (
                        renter_user.username
                        if renter_user
                        else ''
                    )
                    or ''
            )

        # =====================================================
        # مالک
        # =====================================================

        owner_user = obj.user

        return (
                obj.owner_name
                or (
                    owner_user.full_name
                    if owner_user
                    else ''
                )
                or (
                    owner_user.username
                    if owner_user
                    else ''
                )
                or ''
        )

    def get_mobile(self, obj):

        renter = self._get_renter(obj)

        # =====================================================
        # مستأجر
        # =====================================================

        if renter:
            renter_user = renter.user

            return (
                    renter.renter_mobile
                    or (
                        renter_user.mobile
                        if renter_user
                        else ''
                    )
                    or ''
            )

        # =====================================================
        # مالک
        # =====================================================

        owner_user = obj.user

        return (
                obj.owner_mobile
                or (
                    owner_user.mobile
                    if owner_user
                    else ''
                )
                or ''
        )

    def get_has_mobile(self, obj):

        mobile = self.get_mobile(obj)

        return bool(
            str(mobile).strip()
        )


class ManagerMessageListSerializer(
    serializers.ModelSerializer
):
    """
    Serializer لیست مدیریت پیام‌ها

    این لیست شامل:
    - پیام‌های آماده ارسال
    - پیام‌های ارسال شده
    """

    recipient_count = serializers.SerializerMethodField()

    read_count = serializers.SerializerMethodField()

    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = MessageToUser

        fields = [
            'id',
            'title',
            'message',
            'created_at',
            'send_notification',
            'send_notification_date',
            'recipient_count',
            'read_count',
            'unread_count',
        ]

    # =========================================================
    # تعداد گیرندگان واقعی
    # =========================================================

    def get_recipient_count(
            self,
            obj
    ):
        return (
            obj.read_statuses
            .values(
                'recipient_id'
            )
            .distinct()
            .count()
        )

    # =========================================================
    # خوانده شده
    # =========================================================

    def get_read_count(
            self,
            obj
    ):
        return (
            obj.read_statuses
            .filter(
                is_read=True
            )
            .values(
                'recipient_id'
            )
            .distinct()
            .count()
        )

    # =========================================================
    # خوانده نشده
    # =========================================================

    def get_unread_count(
            self,
            obj
    ):
        return (
            obj.read_statuses
            .filter(
                is_read=False
            )
            .values(
                'recipient_id'
            )
            .distinct()
            .count()
        )


class ManagerMessageDetailSerializer(serializers.ModelSerializer):
    """
    جزئیات پیام مدیر
    """

    recipient_count = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    notified_units = ManagerMessageUnitSerializer(
        many=True,
        read_only=True
    )

    recipients = serializers.SerializerMethodField()

    class Meta:
        model = MessageToUser

        fields = [
            'id',
            'title',
            'message',
            'created_at',
            'send_notification',
            'send_notification_date',

            'recipient_count',
            'read_count',
            'unread_count',

            'notified_units',
            'recipients',
        ]

    def get_recipient_count(self, obj):

        return (
            obj.read_statuses
            .values('recipient_id')
            .distinct()
            .count()
        )

    def get_read_count(self, obj):

        return (
            obj.read_statuses
            .filter(
                is_read=True
            )
            .values('recipient_id')
            .distinct()
            .count()
        )

    def get_unread_count(self, obj):

        return (
            obj.read_statuses
            .filter(
                is_read=False
            )
            .values('recipient_id')
            .distinct()
            .count()
        )

    def get_recipients(self, obj):

        result = []

        read_statuses = (
            obj.read_statuses
            .select_related(
                'unit',
                'recipient',
                'unit__user',
            )
            .prefetch_related(
                'unit__renters'
            )
        )

        for status in read_statuses:

            unit = status.unit
            recipient = status.recipient

            if not unit:
                continue

            # =================================================
            # مالک
            # =================================================

            if unit.user_id == recipient.id:
                result.append({
                    'unit_id': unit.id,
                    'unit': unit.unit,
                    'type': 'owner',
                    'recipient_type': 'owner',

                    'name': (
                            unit.owner_name
                            or getattr(
                        recipient,
                        'full_name',
                        ''
                    )
                            or getattr(
                        recipient,
                        'username',
                        ''
                    )
                    ),

                    'mobile': (
                            unit.owner_mobile
                            or getattr(
                        recipient,
                        'mobile',
                        ''
                    )
                            or ''
                    ),

                    'is_read': status.is_read,
                    'read_at': status.read_at,
                })

                continue

            # =================================================
            # مستأجر فعال
            # =================================================

            renter = (
                unit.renters
                .filter(
                    renter_is_active=True,
                    user_id=recipient.id,
                )
                .first()
            )

            if renter:
                result.append({
                    'unit_id': unit.id,
                    'unit': unit.unit,
                    'type': 'renter',
                    'recipient_type': 'renter',

                    'name': (
                            renter.renter_name
                            or getattr(
                        recipient,
                        'full_name',
                        ''
                    )
                            or getattr(
                        recipient,
                        'username',
                        ''
                    )
                    ),

                    'mobile': (
                            renter.renter_mobile
                            or getattr(
                        recipient,
                        'mobile',
                        ''
                    )
                            or ''
                    ),

                    'is_read': status.is_read,
                    'read_at': status.read_at,
                })

        return result


# ============================================================
# ===================== Manager Banks ========================
# ============================================================


class ManagerBankSerializer(serializers.ModelSerializer):
    house_name = serializers.SerializerMethodField()

    class Meta:
        model = Bank

        fields = [
            'id',

            'house',
            'house_name',

            'bank_name',
            'account_no',
            'account_holder_name',

            'sheba_number',
            'cart_number',

            'initial_fund',
            'current_balance',

            'financial_document_number',

            'is_default',
            'is_gateway',
            'create_at',
            'is_active',
        ]

        read_only_fields = [
            'id',
            'current_balance',
            'financial_document_number',
        ]

    def get_house_name(self, obj):

        if obj.house:
            return obj.house.name

        return None

    def validate_house(self, house):

        request = self.context.get('request')

        if not request:
            raise serializers.ValidationError(
                'درخواست معتبر نیست.'
            )

        user = request.user

        if not user.is_middle_admin:
            raise serializers.ValidationError(
                'دسترسی فقط برای مدیر ساختمان مجاز است.'
            )

        if not house or not house.is_active:
            raise serializers.ValidationError(
                'ساختمان انتخاب شده معتبر نیست.'
            )

        has_access = MyHouse.objects.filter(
            id=house.id,
            is_active=True
        ).filter(
            Q(user=user) |
            Q(user__manager=user)
        ).exists()

        if not has_access:
            raise serializers.ValidationError(
                'شما به این ساختمان دسترسی ندارید.'
            )

        return house

    def validate_sheba_number(self, value):

        value = (
                value or ''
        ).replace(
            ' ',
            ''
        ).strip().upper()

        if not value.startswith('IR'):
            raise serializers.ValidationError(
                'شماره شبا باید با IR شروع شود.'
            )

        if len(value) != 26:
            raise serializers.ValidationError(
                'شماره شبا باید ۲۶ کاراکتر باشد.'
            )

        if not value[2:].isdigit():
            raise serializers.ValidationError(
                'بعد از IR باید دقیقاً ۲۴ رقم وارد شود.'
            )

        return value

    def validate_cart_number(self, value):

        value = (
            str(value or '')
            .replace(' ', '')
            .strip()
        )

        if len(value) != 16:
            raise serializers.ValidationError(
                'شماره کارت باید ۱۶ رقم باشد.'
            )

        if not value.isdigit():
            raise serializers.ValidationError(
                'شماره کارت باید فقط شامل اعداد باشد.'
            )

        return value

    def validate_create_at(self, value):

        if not value:
            raise serializers.ValidationError(
                'تاریخ افتتاح حساب الزامی است.'
            )

        return value

    def validate_initial_fund(self, value):

        if value is None:
            return 0

        if value < 0:
            raise serializers.ValidationError(
                'موجودی اولیه نمی‌تواند منفی باشد.'
            )

        return value


class ManagerBankTransferSerializer(serializers.Serializer):
    from_bank = serializers.IntegerField(
        required=True
    )

    to_bank = serializers.IntegerField(
        required=True
    )

    amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=0,
        required=True,
        min_value=1
    )

    payment_date = serializers.DateField(
        required=True
    )

    transaction_reference = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=15
    )

    description = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        max_length=500
    )

    def validate(self, attrs):

        request = self.context.get('request')

        if not request:
            raise serializers.ValidationError(
                'درخواست معتبر نیست.'
            )

        user = request.user

        # -------------------------------------------------
        # فقط مدیر ساختمان
        # -------------------------------------------------
        if not user.is_middle_admin:
            raise serializers.ValidationError(
                'دسترسی فقط برای مدیر ساختمان مجاز است.'
            )

        # -------------------------------------------------
        # حساب مبدأ
        # -------------------------------------------------
        from_bank = (
            Bank.objects
            .filter(
                id=attrs['from_bank'],
                user=user,
                is_active=True
            )
            .select_related('house')
            .first()
        )

        if not from_bank:
            raise serializers.ValidationError({
                'from_bank':
                    'حساب مبدا معتبر نیست.'
            })

        # -------------------------------------------------
        # حساب مقصد
        # -------------------------------------------------
        to_bank = (
            Bank.objects
            .filter(
                id=attrs['to_bank'],
                user=user,
                is_active=True
            )
            .select_related('house')
            .first()
        )

        if not to_bank:
            raise serializers.ValidationError({
                'to_bank':
                    'حساب مقصد معتبر نیست.'
            })

        # -------------------------------------------------
        # مبدأ و مقصد نباید یکی باشند
        # -------------------------------------------------
        if from_bank.id == to_bank.id:
            raise serializers.ValidationError(
                'بانک مبدا و مقصد نمی‌تواند یکسان باشد.'
            )

        # -------------------------------------------------
        # دو حساب باید مربوط به یک ساختمان باشند
        # -------------------------------------------------
        if (
                from_bank.house_id
                and to_bank.house_id
                and from_bank.house_id != to_bank.house_id
        ):
            raise serializers.ValidationError(
                'حساب‌های مبدا و مقصد باید متعلق '
                'به یک ساختمان باشند.'
            )

        # -------------------------------------------------
        # بررسی موجودی
        # -------------------------------------------------
        amount = attrs['amount']

        if from_bank.current_balance < amount:
            raise serializers.ValidationError({
                'amount':
                    f'موجودی حساب مبدا کافی نیست. '
                    f'(موجودی فعلی: '
                    f'{from_bank.current_balance:,})'
            })

        # -------------------------------------------------
        # بررسی تاریخ مبدأ
        # -------------------------------------------------
        payment_date = attrs['payment_date']

        if (
                from_bank.create_at
                and payment_date < from_bank.create_at
        ):
            raise serializers.ValidationError({
                'payment_date':
                    'تاریخ انتقال نمی‌تواند قبل از '
                    'تاریخ افتتاح حساب مبدا باشد.'
            })

        # -------------------------------------------------
        # بررسی تاریخ مقصد
        # -------------------------------------------------
        if (
                to_bank.create_at
                and payment_date < to_bank.create_at
        ):
            raise serializers.ValidationError({
                'payment_date':
                    'تاریخ انتقال نمی‌تواند قبل از '
                    'تاریخ افتتاح حساب مقصد باشد.'
            })

        # -------------------------------------------------
        # نرمال‌سازی شرح
        # -------------------------------------------------
        attrs['description'] = (
                attrs.get('description') or ''
        ).strip()

        # -------------------------------------------------
        # ذخیره آبجکت‌های بانک برای استفاده View
        # -------------------------------------------------
        attrs['from_bank_obj'] = from_bank
        attrs['to_bank_obj'] = to_bank

        return attrs


class ManagerBankTransferListSerializer(
    serializers.ModelSerializer
):
    from_bank_id = serializers.SerializerMethodField()

    from_bank_name = serializers.SerializerMethodField()

    to_bank_id = serializers.SerializerMethodField()

    to_bank_name = serializers.SerializerMethodField()

    transfer_amount = serializers.SerializerMethodField()

    transaction_reference = serializers.SerializerMethodField()

    description = serializers.SerializerMethodField()

    payment_date = serializers.SerializerMethodField()

    financial_document_number = (
        serializers.SerializerMethodField()
    )

    transfer_group_id = (
        serializers.SerializerMethodField()
    )

    class Meta:

        model = BankFund

        fields = [
            'id',
            'transfer_group_id',

            'from_bank_id',
            'from_bank_name',

            'to_bank_id',
            'to_bank_name',

            'transfer_amount',

            'payment_date',

            'transaction_reference',

            'description',

            'financial_document_number',

            'created_at',
        ]

    # =====================================================
    # بانک مبدأ
    # =====================================================

    def get_from_bank_id(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = (
            BankFund.objects
            .filter(
                transfer_group_id=group_id,
                transaction_type='withdraw'
            )
            .select_related('bank')
            .first()
        )

        if record and record.bank:
            return record.bank.id

        return None

    def get_from_bank_name(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = (
            BankFund.objects
            .filter(
                transfer_group_id=group_id,
                transaction_type='withdraw'
            )
            .select_related('bank')
            .first()
        )

        if record and record.bank:
            return record.bank.bank_name

        return None

    # =====================================================
    # بانک مقصد
    # =====================================================

    def get_to_bank_id(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = (
            BankFund.objects
            .filter(
                transfer_group_id=group_id,
                transaction_type='deposit'
            )
            .select_related('bank')
            .first()
        )

        if record and record.bank:
            return record.bank.id

        return None

    def get_to_bank_name(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = (
            BankFund.objects
            .filter(
                transfer_group_id=group_id,
                transaction_type='deposit'
            )
            .select_related('bank')
            .first()
        )

        if record and record.bank:
            return record.bank.bank_name

        return None

    # =====================================================
    # مبلغ انتقال
    # =====================================================

    def get_transfer_amount(self, obj):

        return obj.amount or 0

    # =====================================================
    # شماره تراکنش
    # =====================================================

    def get_transaction_reference(self, obj):

        return obj.transaction_no

    # =====================================================
    # شرح انتقال
    # =====================================================

    def get_description(self, obj):

        return obj.payment_description or ''

    # =====================================================
    # تاریخ پرداخت
    # =====================================================

    def get_payment_date(self, obj):

        return obj.payment_date

    # =====================================================
    # شماره سند مالی
    # =====================================================

    def get_financial_document_number(self, obj):

        return obj.financial_document_number

    # =====================================================
    # گروه انتقال
    # =====================================================

    def get_transfer_group_id(self, obj):

        if obj.transfer_group_id:
            return str(
                obj.transfer_group_id
            )

        return None


# ============================================================
# POLL / Choice
# ============================================================

class ManagerPollChoiceSerializer(
    serializers.ModelSerializer
):
    vote_count = serializers.SerializerMethodField()
    percentage = serializers.SerializerMethodField()

    class Meta:
        model = Choice

        fields = [
            'id',
            'title',
            'vote_count',
            'percentage',
        ]

        read_only_fields = [
            'id',
            'vote_count',
            'percentage',
        ]

    def get_vote_count(self, obj):
        return Vote.objects.filter(
            choice=obj
        ).count()

    def get_percentage(self, obj):
        total = (
            Vote.objects
            .filter(
                question=obj.question
            )
            .values(
                'user'
            )
            .distinct()
            .count()
        )

        if total == 0:
            return 0

        count = (
            Vote.objects
            .filter(
                choice=obj
            )
            .count()
        )

        return round(
            (count / total) * 100,
            1
        )


# ============================================================
# Question
# ============================================================

class ManagerPollQuestionSerializer(
    serializers.ModelSerializer
):
    choices = ManagerPollChoiceSerializer(
        many=True,
        required=False
    )

    class Meta:
        model = Question

        fields = [
            'id',
            'title',
            'question_type',
            'order',
            'choices',
        ]

        read_only_fields = [
            'id',
        ]

    def validate_question_type(
            self,
            value
    ):

        allowed = [
            'yesno',
            'single',
            'multi'
        ]

        if value not in allowed:
            raise serializers.ValidationError(
                'نوع سؤال نامعتبر است.'
            )

        return value

    def validate(self, attrs):

        question_type = attrs.get(
            'question_type',
            getattr(
                self.instance,
                'question_type',
                None
            )
        )

        choices = attrs.get(
            'choices',
            None
        )

        # ----------------------------------------------------
        # yes/no
        # ----------------------------------------------------

        if question_type == 'yesno':

            # برای yes/no گزینه‌ها توسط Backend ساخته می‌شوند.
            pass

        # ----------------------------------------------------
        # single / multi
        # ----------------------------------------------------

        elif question_type in [
            'single',
            'multi'
        ]:

            if choices is not None:

                if len(choices) == 0:
                    raise serializers.ValidationError({
                        'choices':
                            'برای این نوع سؤال حداقل یک گزینه لازم است.'
                    })

        return attrs


# ============================================================
# Poll List
# ============================================================

class ManagerPollListSerializer(
    serializers.ModelSerializer
):
    question_count = serializers.SerializerMethodField()

    has_votes = serializers.SerializerMethodField()

    participant_count = serializers.SerializerMethodField()

    eligible_user_count = serializers.SerializerMethodField()

    owner_count = serializers.SerializerMethodField()

    renter_count = serializers.SerializerMethodField()

    participation_percentage = (
        serializers.SerializerMethodField()
    )

    class Meta:
        model = Poll

        fields = [
            'id',
            'title',
            'description',
            'start_date',
            'end_date',
            'is_active',
            'created_at',

            # نوع افراد مجاز
            'participant_type',

            'question_count',
            'has_votes',

            # تعداد افراد
            'owner_count',
            'renter_count',
            'eligible_user_count',

            'participant_count',
            'participation_percentage',
        ]

    # ========================================================
    # تعداد سوالات
    # ========================================================

    def get_question_count(
            self,
            obj
    ):

        return obj.questions.count()

    # ========================================================
    # آیا رأی دارد؟
    # ========================================================

    def get_has_votes(
            self,
            obj
    ):

        return Vote.objects.filter(
            poll=obj
        ).exists()

    # ========================================================
    # تعداد مالکین فعال
    # ========================================================

    def get_owner_count(
            self,
            obj
    ):

        return obj.house.units.filter(
            is_active=True
        ).count()

    # ========================================================
    # تعداد مستاجرین فعال
    # ========================================================

    def get_renter_count(
            self,
            obj
    ):

        return Renter.objects.filter(
            unit__myhouse=obj.house,
            unit__is_active=True,
            renter_is_active=True
        ).count()

    # ========================================================
    # تعداد افراد مجاز
    # ========================================================

    def get_eligible_user_count(
            self,
            obj
    ):

        owner_count = self.get_owner_count(
            obj
        )

        renter_count = self.get_renter_count(
            obj
        )

        if obj.participant_type == 'owners':
            return owner_count

        if obj.participant_type == 'renters':
            return renter_count

        return (
                owner_count +
                renter_count
        )

    # ========================================================
    # تعداد شرکت کنندگان
    # ========================================================

    def get_participant_count(
            self,
            obj
    ):

        return (
            Vote.objects
            .filter(
                poll=obj
            )
            .values(
                'user'
            )
            .distinct()
            .count()
        )

    # ========================================================
    # درصد مشارکت
    # ========================================================

    def get_participation_percentage(
            self,
            obj
    ):

        eligible = (
            self.get_eligible_user_count(
                obj
            )
        )

        if eligible == 0:
            return 0

        participants = (
            self.get_participant_count(
                obj
            )
        )

        return round(
            (
                    participants /
                    eligible
            ) * 100,
            1
        )


# ============================================================
# Poll Detail
# ============================================================

class ManagerPollDetailSerializer(
    serializers.ModelSerializer
):
    questions = ManagerPollQuestionSerializer(
        many=True,
        read_only=True
    )

    has_votes = serializers.SerializerMethodField()

    participant_count = (
        serializers.SerializerMethodField()
    )

    eligible_user_count = (
        serializers.SerializerMethodField()
    )

    owner_count = (
        serializers.SerializerMethodField()
    )

    renter_count = (
        serializers.SerializerMethodField()
    )

    participation_percentage = (
        serializers.SerializerMethodField()
    )

    class Meta:

        model = Poll

        fields = [
            'id',
            'title',
            'description',
            'house',
            'start_date',
            'end_date',
            'is_active',
            'created_at',
            'created_by',

            # نوع افراد مجاز
            'participant_type',

            'has_votes',

            # تعداد افراد
            'owner_count',
            'renter_count',
            'eligible_user_count',

            'participant_count',
            'participation_percentage',

            'questions',
        ]

        read_only_fields = [
            'id',
            'house',
            'created_by',
            'created_at',

            'has_votes',

            'owner_count',
            'renter_count',
            'eligible_user_count',

            'participant_count',
            'participation_percentage',

            'questions',
        ]

    # ========================================================
    # آیا رأی دارد؟
    # ========================================================

    def get_has_votes(
            self,
            obj
    ):

        return Vote.objects.filter(
            poll=obj
        ).exists()

    # ========================================================
    # تعداد مالکین فعال
    # ========================================================

    def get_owner_count(
            self,
            obj
    ):

        return obj.house.units.filter(
            is_active=True
        ).count()

    # ========================================================
    # تعداد مستاجرین فعال
    # ========================================================

    def get_renter_count(
            self,
            obj
    ):

        return Renter.objects.filter(
            unit__myhouse=obj.house,
            unit__is_active=True,
            renter_is_active=True
        ).count()

    # ========================================================
    # تعداد افراد مجاز
    # ========================================================

    def get_eligible_user_count(
            self,
            obj
    ):

        owner_count = (
            self.get_owner_count(
                obj
            )
        )

        renter_count = (
            self.get_renter_count(
                obj
            )
        )

        if obj.participant_type == 'owners':
            return owner_count

        if obj.participant_type == 'renters':
            return renter_count

        return (
                owner_count +
                renter_count
        )

    # ========================================================
    # تعداد شرکت کنندگان
    # ========================================================

    def get_participant_count(
            self,
            obj
    ):

        return (
            Vote.objects
            .filter(
                poll=obj
            )
            .values(
                'user'
            )
            .distinct()
            .count()
        )

    # ========================================================
    # درصد مشارکت
    # ========================================================

    def get_participation_percentage(
            self,
            obj
    ):

        eligible = (
            self.get_eligible_user_count(
                obj
            )
        )

        if eligible == 0:
            return 0

        participants = (
            self.get_participant_count(
                obj
            )
        )

        return round(
            (
                    participants /
                    eligible
            ) * 100,
            1
        )


# ============================================================
# Create / Update Poll
# ============================================================

class ManagerPollWriteSerializer(
    serializers.ModelSerializer
):
    questions = ManagerPollQuestionSerializer(
        many=True,
        required=False
    )

    class Meta:

        model = Poll

        fields = [
            'id',
            'title',
            'description',
            'start_date',
            'end_date',
            'is_active',

            # افراد مجاز
            'participant_type',

            'questions',
        ]

        read_only_fields = [
            'id',
        ]

    # ========================================================
    # Validate
    # ========================================================

    def validate(
            self,
            attrs
    ):

        start_date = attrs.get(
            'start_date'
        )

        end_date = attrs.get(
            'end_date'
        )

        if start_date and end_date:

            if end_date <= start_date:
                raise serializers.ValidationError({
                    'end_date':
                        'تاریخ پایان باید بعد از تاریخ شروع باشد.'
                })

        # ----------------------------------------------------
        # participant_type
        # ----------------------------------------------------

        participant_type = attrs.get(
            'participant_type'
        )

        if participant_type is not None:

            allowed = [
                'all',
                'owners',
                'renters',
            ]

            if participant_type not in allowed:
                raise serializers.ValidationError({
                    'participant_type':
                        'نوع افراد مجاز نامعتبر است.'
                })

        return attrs

    # ========================================================
    # CREATE
    # ========================================================

    def create(
            self,
            validated_data
    ):

        questions_data = validated_data.pop(
            'questions',
            []
        )

        request = self.context[
            'request'
        ]

        user = request.user

        # ----------------------------------------------------
        # ساختمان مدیر
        # ----------------------------------------------------

        house_obj = (
            MyHouse.objects
            .filter(
                user=user,
                is_active=True
            )
            .first()
        )

        if not house_obj:
            raise serializers.ValidationError(
                'ساختمان فعال مرتبط با مدیر پیدا نشد.'
            )

        # ----------------------------------------------------
        # ایجاد Poll
        # ----------------------------------------------------

        poll = Poll.objects.create(
            house=house_obj,
            created_by=user,
            **validated_data
        )

        # ----------------------------------------------------
        # ایجاد سوالات
        # ----------------------------------------------------

        self._create_questions(
            poll,
            questions_data
        )

        return poll

    # ========================================================
    # UPDATE
    # ========================================================

    def update(
            self,
            instance,
            validated_data
    ):

        # ----------------------------------------------------
        # اگر رأی وجود داشته باشد ویرایش ممنوع
        # ----------------------------------------------------

        has_votes = Vote.objects.filter(
            poll=instance
        ).exists()

        if has_votes:
            raise serializers.ValidationError({
                'detail':
                    'این نظرسنجی دارای پاسخ است و دیگر قابل ویرایش نیست. '
                    'فقط می‌توانید آن را غیرفعال کنید.'
            })

        questions_data = (
            validated_data.pop(
                'questions',
                None
            )
        )

        # ----------------------------------------------------
        # بروزرسانی فیلدهای Poll
        # ----------------------------------------------------

        for attr, value in validated_data.items():
            setattr(
                instance,
                attr,
                value
            )

        instance.save()

        # ----------------------------------------------------
        # بروزرسانی سوالات
        # ----------------------------------------------------

        if questions_data is not None:
            instance.questions.all().delete()

            self._create_questions(
                instance,
                questions_data
            )

        return instance

    # ========================================================
    # CREATE QUESTIONS
    # ========================================================

    def _create_questions(
            self,
            poll,
            questions_data
    ):

        for index, question_data in enumerate(
                questions_data,
                start=1
        ):

            # ------------------------------------------------
            # کپی داده‌ها
            # ------------------------------------------------

            question_data = dict(
                question_data
            )

            choices_data = (
                question_data.pop(
                    'choices',
                    []
                )
            )

            # ------------------------------------------------
            # ایجاد سؤال
            # ------------------------------------------------

            question = Question.objects.create(
                poll=poll,

                title=question_data.get(
                    'title'
                ),

                question_type=question_data.get(
                    'question_type'
                ),

                order=question_data.get(
                    'order',
                    index
                )
            )

            # ------------------------------------------------
            # yes / no
            # ------------------------------------------------

            if question.question_type == 'yesno':

                Choice.objects.create(
                    question=question,
                    title='بله'
                )

                Choice.objects.create(
                    question=question,
                    title='خیر'
                )

            # ------------------------------------------------
            # single / multi
            # ------------------------------------------------

            else:

                for choice_data in choices_data:

                    if isinstance(
                            choice_data,
                            dict
                    ):

                        title = (
                            choice_data.get(
                                'title'
                            )
                        )

                    else:

                        title = choice_data

                    if (
                            title is not None
                            and
                            str(title).strip()
                    ):
                        Choice.objects.create(
                            question=question,
                            title=str(
                                title
                            ).strip()
                        )

        return poll


# ====================Ticket To user ====================

class SupportFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = SupportFile
        fields = [
            'id',
            'url',
            'uploaded_at',
        ]

    def get_url(self, obj):
        request = self.context.get('request')

        if not obj.file:
            return None

        url = obj.file.url

        if request:
            return request.build_absolute_uri(url)

        return url


class SupportMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()
    attachments = SupportFileSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = SupportMessage
        fields = [
            'id',
            'sender',
            'sender_name',
            'sender_role',
            'message',
            'attachments',
            'created_at',
            'is_read',
        ]

    def get_sender_name(self, obj):
        return str(obj.sender)

    def get_sender_role(self, obj):
        if obj.sender.is_superuser:
            return 'ادمین'

        if obj.sender.is_middle_admin:
            return 'مدیر ساختمان'

        return 'ساکن'


class SupportTicketListSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_mobile = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()

    class Meta:
        model = SupportUser

        fields = [
            'id',
            'ticket_no',
            'subject',
            'is_sent',
            'is_read',
            'is_call',
            'is_closed',
            'is_answer',
            'is_waiting',
            'user_name',
            'user_mobile',
            'unread_count',
            'last_message',
            'created_at',
            'updated_at',
        ]

    # =====================================================
    # نام ساکن
    # =====================================================

    def get_user_name(self, obj):
        return str(obj.user)

    # =====================================================
    # موبایل ساکن
    # =====================================================

    def get_user_mobile(self, obj):
        if not obj.is_call:
            return None

        return getattr(obj.user, 'mobile', None)

    # =====================================================
    # تعداد پیام‌های جدید برای مدیر
    #
    # منبع اصلی Notification است، نه SupportMessage.is_read
    # چون is_read در Notification برای هر مدیر جداگانه است.
    # =====================================================

    def get_unread_count(self, obj):
        request = self.context.get('request')

        if not request:
            return 0

        user = request.user

        if not user or not user.is_authenticated:
            return 0

        return Notification.objects.filter(
            user=user,
            ticket=obj,
            is_read=False,
        ).count()

    # =====================================================
    # آخرین پیام
    # =====================================================

    def get_last_message(self, obj):
        message = (
            obj.messages
            .select_related('sender')
            .order_by('-created_at')
            .first()
        )

        if not message:
            return None

        return {
            'id': message.id,
            'message': message.message,
            'sender_name': str(message.sender),
            'sender_role': (
                'ادمین'
                if message.sender.is_superuser
                else 'مدیر ساختمان'
                if message.sender.is_middle_admin
                else 'ساکن'
            ),
            'created_at': message.created_at,
            'is_read': message.is_read,
        }


class SupportTicketDetailSerializer(serializers.ModelSerializer):
    user_name = serializers.SerializerMethodField()
    user_mobile = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    files = SupportFileSerializer(
        many=True,
        read_only=True
    )

    class Meta:
        model = SupportUser
        fields = [
            'id',
            'ticket_no',
            'subject',
            'message',
            'answer_message',
            'is_sent',
            'is_read',
            'is_call',
            'is_closed',
            'is_answer',
            'is_waiting',
            'user_name',
            'user_mobile',
            'files',
            'messages',
            'created_at',
            'updated_at',
        ]

    def get_user_name(self, obj):
        return str(obj.user)

    def get_user_mobile(self, obj):
        if not obj.is_call:
            return None

        return getattr(obj.user, 'mobile', None)

    def get_messages(self, obj):
        request = self.context.get('request')

        queryset = obj.messages.select_related(
            'sender'
        ).prefetch_related(
            'attachments'
        ).order_by('created_at')

        return SupportMessageSerializer(
            queryset,
            many=True,
            context={
                'request': request
            }
        ).data


# =========================================================
# resident ticket
# =========================================================

class UserSupportFileSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = SupportFile
        fields = [
            'id',
            'url',
            'uploaded_at',
        ]

    def get_url(self, obj):
        request = self.context.get('request')

        if not obj.file:
            return None

        try:
            url = obj.file.url
        except Exception:
            return None

        if request:
            return request.build_absolute_uri(url)

        return url


# =========================================================
# پیام گفتگو
# =========================================================

class UserSupportMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()

    attachments = UserSupportFileSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = SupportMessage

        fields = [
            'id',
            'sender',
            'sender_name',
            'sender_role',
            'message',
            'attachments',
            'created_at',
            'is_read',
        ]

        read_only_fields = [
            'id',
            'sender',
            'sender_name',
            'sender_role',
            'attachments',
            'created_at',
            'is_read',
        ]

    def get_sender_name(self, obj):
        if not obj.sender:
            return ''

        return (
            getattr(obj.sender, 'full_name', None)
            or str(obj.sender)
        )

    def get_sender_role(self, obj):
        if obj.sender and obj.sender.is_middle_admin:
            return 'مدیر ساختمان'

        return 'ساکن'


# =========================================================
# آخرین پیام
# =========================================================

class UserSupportLastMessageSerializer(serializers.ModelSerializer):
    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()

    class Meta:
        model = SupportMessage

        fields = [
            'id',
            'sender_name',
            'sender_role',
            'message',
            'created_at',
            'is_read',
        ]

    def get_sender_name(self, obj):
        if not obj.sender:
            return ''

        return (
            getattr(obj.sender, 'full_name', None)
            or str(obj.sender)
        )

    def get_sender_role(self, obj):
        if obj.sender and obj.sender.is_middle_admin:
            return 'مدیر ساختمان'

        return 'ساکن'


# =========================================================
# لیست تیکت‌های ساکن
# =========================================================

class UserSupportTicketListSerializer(serializers.ModelSerializer):
        unread_count = serializers.SerializerMethodField()
        last_message = serializers.SerializerMethodField()
        status = serializers.SerializerMethodField()

        class Meta:
            model = SupportUser

            fields = [
                'id',
                'ticket_no',
                'subject',
                'is_call',
                'is_closed',
                'is_answer',
                'is_waiting',
                'status',
                'unread_count',
                'last_message',
                'created_at',
                'updated_at',
            ]

            read_only_fields = [
                'id',
                'ticket_no',
                'is_closed',
                'is_answer',
                'is_waiting',
                'status',
                'unread_count',
                'last_message',
                'created_at',
                'updated_at',
            ]

        # -----------------------------------------------------
        # تعداد پیام‌های خوانده نشده مدیر
        # -----------------------------------------------------

        def get_unread_count(self, obj):
            request = self.context.get('request')

            if not request or not request.user:
                return 0

            return (
                obj.messages
                .filter(is_read=False)
                .exclude(sender=request.user)
                .count()
            )

        # -----------------------------------------------------
        # آخرین پیام
        # -----------------------------------------------------

        def get_last_message(self, obj):
            message = (
                obj.messages
                .select_related('sender')
                .order_by('-created_at')
                .first()
            )

            if not message:
                return None

            serializer = UserSupportLastMessageSerializer(
                message,
                context=self.context,
            )

            return serializer.data

        # -----------------------------------------------------
        # وضعیت تیکت
        # -----------------------------------------------------

        def get_status(self, obj):
            if obj.is_closed:
                return 'بسته شده'

            if obj.is_waiting:
                return 'در حال بررسی'

            if obj.is_answer:
                return 'پاسخ داده شده'

            return 'در انتظار پاسخ'


# =========================================================
# جزئیات تیکت
# =========================================================

class UserSupportTicketDetailSerializer(serializers.ModelSerializer):
    files = UserSupportFileSerializer(
        many=True,
        read_only=True,
    )

    messages = UserSupportMessageSerializer(
        many=True,
        read_only=True,
    )

    unread_count = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = SupportUser

        fields = [
            'id',
            'ticket_no',
            'subject',
            'message',
            'answer_message',
            'is_sent',
            'is_call',
            'is_closed',
            'is_answer',
            'is_waiting',
            'status',
            'unread_count',
            'files',
            'messages',
            'created_at',
            'updated_at',
        ]

        read_only_fields = [
            'id',
            'ticket_no',
            'answer_message',
            'is_sent',
            'is_closed',
            'is_answer',
            'is_waiting',
            'status',
            'unread_count',
            'files',
            'messages',
            'created_at',
            'updated_at',
        ]

    # -----------------------------------------------------
    # تعداد پیام‌های خوانده نشده
    # -----------------------------------------------------

    def get_unread_count(self, obj):
        request = self.context.get('request')

        if not request or not request.user:
            return 0

        return (
            obj.messages
            .filter(is_read=False)
            .exclude(sender=request.user)
            .count()
        )

    # -----------------------------------------------------
    # وضعیت
    # -----------------------------------------------------

    def get_status(self, obj):
        if obj.is_closed:
            return 'بسته شده'

        if obj.is_waiting:
            return 'در حال بررسی'

        if obj.is_answer:
            return 'پاسخ داده شده'

        return 'در انتظار پاسخ'


# =========================================================
# ایجاد تیکت توسط ساکن
# =========================================================

class UserSupportTicketCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SupportUser

        fields = [
            'subject',
            'message',
            'is_call',
        ]

    # -----------------------------------------------------
    # عنوان
    # -----------------------------------------------------

    def validate_subject(self, value):
        value = (value or '').strip()

        if not value:
            raise serializers.ValidationError(
                'عنوان تیکت الزامی است.'
            )

        if len(value) > 200:
            raise serializers.ValidationError(
                'عنوان تیکت نمی‌تواند بیشتر از ۲۰۰ کاراکتر باشد.'
            )

        return value

    # -----------------------------------------------------
    # متن پیام
    # -----------------------------------------------------

    def validate_message(self, value):
        value = value or ''

        if not value.strip():
            raise serializers.ValidationError(
                'متن تیکت الزامی است.'
            )

        return value


# =========================================================
#  تیکت ادمین
# =========================================================

class AdminTicketFileSerializer(serializers.ModelSerializer):

    file_url = serializers.SerializerMethodField()

    class Meta:
        model = AdminTicketFile

        fields = [
            'id',
            'file',
            'file_url',
            'uploaded_at',
        ]

        read_only_fields = [
            'id',
            'file_url',
            'uploaded_at',
        ]

    def get_file_url(self, obj):

        if not obj.file:
            return None

        try:
            url = obj.file.url
        except Exception:
            return None

        request = self.context.get('request')

        if request:
            try:
                return request.build_absolute_uri(url)
            except Exception:
                pass

        return url


# =========================================================
# آخرین پیام
# =========================================================

class AdminTicketLastMessageSerializer(
    serializers.ModelSerializer
):

    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()

    class Meta:
        model = AdminTicketMessage

        fields = [
            'id',
            'sender_name',
            'sender_role',
            'message',
            'created_at',
            'is_read',
        ]

    def get_sender_name(self, obj):

        if not obj.sender:
            return 'نامشخص'

        return str(obj.sender)

    def get_sender_role(self, obj):

        if not obj.sender:
            return 'نامشخص'

        if obj.sender.is_superuser:
            return 'ادمین'

        if obj.sender.is_middle_admin:
            return 'مدیر ساختمان'

        return 'کاربر'


# =========================================================
# پیام
# =========================================================

class AdminTicketMessageSerializer(
    serializers.ModelSerializer
):

    sender_name = serializers.SerializerMethodField()
    sender_role = serializers.SerializerMethodField()

    attachments = AdminTicketFileSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = AdminTicketMessage

        fields = [
            'id',
            'sender_name',
            'sender_role',
            'message',
            'attachments',
            'created_at',
            'is_read',
        ]

    def get_sender_name(self, obj):

        if not obj.sender:
            return 'نامشخص'

        return str(obj.sender)

    def get_sender_role(self, obj):

        if not obj.sender:
            return 'نامشخص'

        if obj.sender.is_superuser:
            return 'ادمین'

        if obj.sender.is_middle_admin:
            return 'مدیر ساختمان'

        return 'کاربر'


# =========================================================
# لیست تیکت
# =========================================================

class AdminTicketListSerializer(
    serializers.ModelSerializer
):

    unread_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()

    class Meta:
        model = AdminTicket

        fields = [
            'id',
            'ticket_no',
            'subject',

            'is_sent',
            'is_read',
            'is_call',

            'is_closed',
            'is_answer',
            'is_waiting',

            'status',

            'unread_count',
            'last_message',

            'created_at',
            'updated_at',
        ]

        read_only_fields = [
            'id',
            'ticket_no',

            'is_sent',
            'is_read',
            'is_call',

            'is_closed',
            'is_answer',
            'is_waiting',

            'status',
            'unread_count',
            'last_message',

            'created_at',
            'updated_at',
        ]

    # -----------------------------------------------------
    # تعداد اعلان‌های خوانده نشده
    # -----------------------------------------------------

    def get_unread_count(self, obj):

        request = self.context.get('request')

        if not request:
            return 0

        user = request.user

        if not user.is_authenticated:
            return 0

        return MiddleAdminNotification.objects.filter(
            user=user,
            ticket=obj,
            is_read=False,
        ).count()

    # -----------------------------------------------------
    # آخرین پیام
    # -----------------------------------------------------

    def get_last_message(self, obj):

        message = (
            obj.messages
            .select_related('sender')
            .order_by('-created_at')
            .first()
        )

        if not message:
            return None

        return AdminTicketLastMessageSerializer(
            message,
            context=self.context,
        ).data

    # -----------------------------------------------------
    # وضعیت
    # -----------------------------------------------------

    def get_status(self, obj):

        if obj.is_closed:
            return 'بسته شده'

        if obj.is_waiting:
            return 'در حال بررسی'

        if obj.is_answer:
            return 'پاسخ داده شده'

        return 'در انتظار پاسخ'


# =========================================================
# جزئیات تیکت
# =========================================================

class AdminTicketDetailSerializer(
    serializers.ModelSerializer
):

    status = serializers.SerializerMethodField()
    messages = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()

    class Meta:
        model = AdminTicket

        fields = [
            'id',
            'ticket_no',
            'subject',
            'message',

            'is_sent',
            'is_read',
            'is_call',

            'is_closed',
            'is_answer',
            'is_waiting',

            'status',

            'created_at',
            'updated_at',

            'files',
            'messages',
        ]

    def get_status(self, obj):

        if obj.is_closed:
            return 'بسته شده'

        if obj.is_waiting:
            return 'در حال بررسی'

        if obj.is_answer:
            return 'پاسخ داده شده'

        return 'در انتظار پاسخ'

    # -----------------------------------------------------
    # فایل‌های اولیه تیکت
    # -----------------------------------------------------

    def get_files(self, obj):

        files = (
            obj.files_ticket
            .all()
            .order_by('uploaded_at')
        )

        return AdminTicketFileSerializer(
            files,
            many=True,
            context=self.context,
        ).data

    # -----------------------------------------------------
    # پیام‌ها
    # -----------------------------------------------------

    def get_messages(self, obj):

        messages = (
            obj.messages
            .select_related('sender')
            .prefetch_related('attachments')
            .order_by('created_at')
        )

        return AdminTicketMessageSerializer(
            messages,
            many=True,
            context=self.context,
        ).data


# =========================================================
# ایجاد تیکت
# =========================================================

class AdminTicketCreateSerializer(
    serializers.ModelSerializer
):

    class Meta:
        model = AdminTicket

        fields = [
            'subject',
            'message',
        ]

        extra_kwargs = {
            'subject': {
                'required': False,
                'allow_blank': True,
            },

            'message': {
                'required': True,
                'allow_blank': False,
            },
        }

    def validate_message(self, value):

        value = (value or '').strip()

        if not value:
            raise serializers.ValidationError(
                'متن تیکت را وارد کنید.'
            )

        return value


# =========================================================
# ایجاد پیام
# =========================================================

class AdminTicketMessageCreateSerializer(
    serializers.Serializer
):

    message = serializers.CharField(
        required=False,
        allow_blank=True,
        trim_whitespace=True,
    )

    def validate(self, attrs):

        attrs['message'] = (
            attrs.get('message')
            or ''
        ).strip()

        return attrs