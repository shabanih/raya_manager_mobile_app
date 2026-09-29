from django.db.models import Q
from rest_framework import serializers

from admin_panel.models import UnifiedCharge, Fund, Announcement, CivilManage, CivilInstallment, SewageInstallment, \
    SewageManage, MessageToUser, AnnouncementDocument, BankFund
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
            'has_voted',
        ]

    def get_has_voted(self, obj):
        request = self.context.get('request')

        if not request or not request.user.is_authenticated:
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
            'questions',
            'has_voted',
        ]

    def get_has_voted(self, obj):
        request = self.context.get('request')

        if not request:
            return False

        if not request.user.is_authenticated:
            return False

        return Vote.objects.filter(
            poll=obj,
            user=request.user,
        ).exists()


# Civil
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


# Sewage
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


# pay money

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

# -------------------------------------------
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

    # --------------------------------------------------------
    # شرح انتقال - اختیاری
    # --------------------------------------------------------

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

        if not user.is_middle_admin:

            raise serializers.ValidationError(
                'دسترسی فقط برای مدیر ساختمان مجاز است.'
            )

        from_bank = Bank.objects.filter(
            id=attrs['from_bank'],
            user=user,
            is_active=True
        ).select_related(
            'house'
        ).first()

        if not from_bank:

            raise serializers.ValidationError({
                'from_bank':
                    'حساب مبدا معتبر نیست.'
            })

        to_bank = Bank.objects.filter(
            id=attrs['to_bank'],
            user=user,
            is_active=True
        ).select_related(
            'house'
        ).first()

        if not to_bank:

            raise serializers.ValidationError({
                'to_bank':
                    'حساب مقصد معتبر نیست.'
            })

        if from_bank.id == to_bank.id:

            raise serializers.ValidationError(
                'بانک مبدا و مقصد نمی‌تواند یکسان باشد.'
            )

        # --------------------------------------------------------
        # ساختمان
        # --------------------------------------------------------

        if (
            from_bank.house_id
            and to_bank.house_id
            and from_bank.house_id != to_bank.house_id
        ):

            raise serializers.ValidationError(
                'حساب‌های مبدا و مقصد باید متعلق به یک ساختمان باشند.'
            )

        amount = attrs['amount']

        # --------------------------------------------------------
        # بررسی موجودی
        # --------------------------------------------------------

        if from_bank.current_balance < amount:

            raise serializers.ValidationError({
                'amount':
                    f'موجودی حساب مبدا کافی نیست. '
                    f'(موجودی فعلی: {from_bank.current_balance:,})'
            })

        payment_date = attrs['payment_date']

        # --------------------------------------------------------
        # تاریخ افتتاح بانک مبدا
        # --------------------------------------------------------

        if (
            from_bank.create_at
            and payment_date < from_bank.create_at
        ):

            raise serializers.ValidationError({
                'payment_date':
                    'تاریخ انتقال نمی‌تواند قبل از تاریخ افتتاح '
                    'حساب مبدا باشد.'
            })

        # --------------------------------------------------------
        # تاریخ افتتاح بانک مقصد
        # --------------------------------------------------------

        if (
            to_bank.create_at
            and payment_date < to_bank.create_at
        ):

            raise serializers.ValidationError({
                'payment_date':
                    'تاریخ انتقال نمی‌تواند قبل از تاریخ افتتاح '
                    'حساب مقصد باشد.'
            })

        # --------------------------------------------------------
        # بانک‌ها
        # --------------------------------------------------------

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

    financial_document_number = serializers.SerializerMethodField()

    transfer_group_id = serializers.SerializerMethodField()

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

    def get_from_bank_id(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = BankFund.objects.filter(
            transfer_group_id=group_id,
            transaction_type='withdraw'
        ).select_related(
            'bank'
        ).first()

        if record and record.bank:
            return record.bank.id

        return None

    def get_from_bank_name(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = BankFund.objects.filter(
            transfer_group_id=group_id,
            transaction_type='withdraw'
        ).select_related(
            'bank'
        ).first()

        if record and record.bank:
            return record.bank.bank_name

        return None

    def get_to_bank_id(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = BankFund.objects.filter(
            transfer_group_id=group_id,
            transaction_type='deposit'
        ).select_related(
            'bank'
        ).first()

        if record and record.bank:
            return record.bank.id

        return None

    def get_to_bank_name(self, obj):

        group_id = obj.transfer_group_id

        if not group_id:
            return None

        record = BankFund.objects.filter(
            transfer_group_id=group_id,
            transaction_type='deposit'
        ).select_related(
            'bank'
        ).first()

        if record and record.bank:
            return record.bank.bank_name

        return None

    def get_transfer_amount(self, obj):

        return obj.amount or 0

    def get_transaction_reference(self, obj):

        return obj.transaction_no

    def get_description(self, obj):

        # --------------------------------------------------------
        # شرح واقعی انتقال که توسط مدیر وارد شده
        # --------------------------------------------------------

        return obj.payment_description or ''

    def get_payment_date(self, obj):

        return obj.payment_date

    def get_financial_document_number(self, obj):

        return obj.financial_document_number

    def get_transfer_group_id(self, obj):

        if obj.transfer_group_id:
            return str(
                obj.transfer_group_id
            )

        return None