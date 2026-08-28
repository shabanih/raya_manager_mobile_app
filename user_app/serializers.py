from rest_framework import serializers
from django.contrib.auth import authenticate
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from .models import (
    User, MyHouse, Unit, Renter, Bank,
    ChargeMethod, UserPayMoney, UserPayMoneyDocument,
    UnitResidenceHistory, CalendarNote, HouseLicense,
    HousePaymentGateway
)


# ==================== Serializerهای ساده ====================

class ChargeMethodSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChargeMethod
        fields = ['id', 'name', 'is_active', 'created_at']


class BankSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bank
        fields = [
            'id', 'bank_name', 'account_no', 'account_holder_name',
            'sheba_number', 'cart_number', 'initial_fund', 'current_balance',
            'is_default', 'is_gateway', 'is_active', 'create_at'
        ]
        read_only_fields = ['current_balance', 'create_at']


class MyHouseSerializer(serializers.ModelSerializer):
    manager_name = serializers.ReadOnlyField(source='user.full_name')
    manager_username = serializers.ReadOnlyField(source='user.username')
    resident_count = serializers.SerializerMethodField()
    unit_count = serializers.SerializerMethodField()

    class Meta:
        model = MyHouse
        fields = [
            'id', 'name', 'floor_counts', 'unit_counts', 'phone',
            'city', 'address', 'subdomain', 'is_active', 'created_at',
            'manager_name', 'manager_username', 'resident_count', 'unit_count'
        ]
        read_only_fields = ['created_at']

    def get_resident_count(self, obj):
        return obj.residents.count()

    def get_unit_count(self, obj):
        return obj.units.count()


class UnitSerializer(serializers.ModelSerializer):
    myhouse_name = serializers.ReadOnlyField(source='myhouse.name')
    owner_name_display = serializers.ReadOnlyField(source='owner_name')
    active_renter = serializers.SerializerMethodField()
    residence_history = serializers.SerializerMethodField()

    class Meta:
        model = Unit
        fields = [
            'id', 'unit', 'myhouse', 'myhouse_name', 'floor_number',
            'area', 'bedrooms_count', 'parking_number', 'parking_place',
            'extra_parking_first', 'extra_parking_second', 'parking_counts',
            'unit_details', 'owner_name', 'owner_mobile', 'owner_national_code',
            'owner_people_count', 'owner_details', 'is_renter', 'people_count',
            'created_at', 'is_active', 'owner_bank', 'first_charge_owner',
            'active_renter', 'residence_history'
        ]
        read_only_fields = ['created_at', 'parking_counts', 'people_count']

    def get_active_renter(self, obj):
        renter = obj.get_active_renter()
        if renter:
            return {
                'id': renter.id,
                'name': renter.renter_name,
                'mobile': renter.renter_mobile,
                'start_date': renter.start_date,
                'end_date': renter.end_date,
                'first_charge': renter.first_charge_renter
            }
        return None

    def get_residence_history(self, obj):
        histories = obj.residence_histories.filter(to_date__isnull=True)
        return UnitResidenceHistorySerializer(histories, many=True).data


class RenterSerializer(serializers.ModelSerializer):
    unit_label = serializers.ReadOnlyField(source='unit.get_label')
    unit_number = serializers.ReadOnlyField(source='unit.unit')
    myhouse_name = serializers.ReadOnlyField(source='myhouse.name')

    class Meta:
        model = Renter
        fields = [
            'id', 'unit', 'unit_label', 'unit_number', 'myhouse', 'myhouse_name',
            'renter_name', 'renter_mobile', 'renter_national_code',
            'renter_people_count', 'start_date', 'end_date',
            'contract_number', 'estate_name', 'first_charge_renter',
            'renter_details', 'renter_is_active', 'created_at',
            'renter_bank', 'renter_payment_date', 'renter_transaction_no'
        ]
        read_only_fields = ['created_at']


class UnitResidenceHistorySerializer(serializers.ModelSerializer):
    resident_type_display = serializers.ReadOnlyField(source='get_resident_type_display')
    unit_number = serializers.ReadOnlyField(source='unit.unit')

    class Meta:
        model = UnitResidenceHistory
        fields = [
            'id', 'unit', 'unit_number', 'resident_type', 'resident_type_display',
            'name', 'mobile', 'people_count', 'from_date', 'to_date',
            'changed_by', 'created_at'
        ]
        read_only_fields = ['created_at']


class UserPayMoneyDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserPayMoneyDocument
        fields = ['id', 'document', 'uploaded_at']
        read_only_fields = ['uploaded_at']


class UserPayMoneySerializer(serializers.ModelSerializer):
    unit_label = serializers.ReadOnlyField(source='unit.get_label')
    unit_number = serializers.ReadOnlyField(source='unit.unit')
    house_name = serializers.ReadOnlyField(source='house.name')
    bank_name = serializers.ReadOnlyField(source='bank.bank_name')
    documents = UserPayMoneyDocumentSerializer(many=True, read_only=True)
    payer_full_name = serializers.ReadOnlyField(source='payer_name')
    is_paid_display = serializers.SerializerMethodField()

    class Meta:
        model = UserPayMoney
        fields = [
            'id', 'user', 'bank', 'bank_name', 'unit', 'unit_label', 'unit_number',
            'house', 'house_name', 'payer_name', 'payer_full_name',
            'payment_gateway', 'description', 'amount', 'register_date',
            'details', 'is_paid', 'is_paid_display', 'transaction_reference',
            'payment_date', 'created_at', 'is_active', 'documents'
        ]
        read_only_fields = ['created_at', 'is_paid_display']

    def get_is_paid_display(self, obj):
        return "پرداخت شده" if obj.is_paid else "پرداخت نشده"


class CalendarNoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = CalendarNote
        fields = ['id', 'year', 'month', 'day', 'note']


# ==================== Serializerهای احراز هویت ====================

class UserSerializer(serializers.ModelSerializer):
    managed_houses_count = serializers.SerializerMethodField()
    units_count = serializers.SerializerMethodField()
    charge_methods = ChargeMethodSerializer(many=True, read_only=True)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'full_name', 'mobile', 'email',
            'house', 'is_active', 'is_middle_admin', 'is_resident',
            'is_unit', 'is_trial', 'is_staff', 'is_superuser',
            'manager', 'created_time', 'charge_methods',
            'managed_houses_count', 'units_count', 'date_joined'
        ]
        read_only_fields = ['created_time', 'date_joined']

    def get_managed_houses_count(self, obj):
        return obj.managed_houses.count()

    def get_units_count(self, obj):
        return obj.units.count()


class UserRegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    password2 = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'username', 'full_name', 'mobile', 'email',
            'password', 'password2'
        ]

    def validate(self, data):
        if data['password'] != data['password2']:
            raise serializers.ValidationError("رمز عبور با تکرار آن مطابقت ندارد")
        return data

    def create(self, validated_data):
        validated_data.pop('password2')
        user = User.objects.create_user(
            username=validated_data['username'],
            mobile=validated_data['mobile'],
            full_name=validated_data.get('full_name', ''),
            email=validated_data.get('email', ''),
            password=validated_data['password']
        )
        return user


class UserLoginSerializer(serializers.Serializer):
    mobile = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        user = authenticate(username=data['mobile'], password=data['password'])
        if user and user.is_active:
            return user
        raise serializers.ValidationError("شماره موبایل یا رمز عبور اشتباه است")


class UserChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True, min_length=8)
    new_password2 = serializers.CharField(write_only=True, min_length=8)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError("رمز عبور جدید با تکرار آن مطابقت ندارد")
        return data


class UserUpdateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['full_name', 'email', 'mobile']