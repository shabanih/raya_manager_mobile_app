
import uuid
from decimal import Decimal

import jdatetime

from django.core.exceptions import ValidationError
from django.db import transaction
from django.contrib.contenttypes.models import ContentType

from user_app.models import Bank
from admin_panel.models import BankFund, ThirdParty

from admin_panel.services.utils import (
    get_next_financial_document_number,
)

from middleAdmin_panel.services.bank_balance_service import (
    recalculate_bank_balance,
)


class BankTransactionService:

    # =========================================================
    # اعتبارسنجی شخص ثالث
    # =========================================================

    @staticmethod
    def _validate_third_party(
        *,
        third_party,
        house,
        field_label,
    ):
        if not third_party:
            raise ValidationError(
                f"{field_label} مشخص نشده است."
            )

        if not third_party.is_active:
            raise ValidationError(
                f"{field_label} انتخاب‌شده غیرفعال است."
            )

        if not house:
            raise ValidationError(
                "ساختمان تراکنش مشخص نیست."
            )

        if third_party.house_id != house.pk:
            raise ValidationError(
                f"{field_label} انتخاب‌شده متعلق به این ساختمان نیست."
            )

        name = (third_party.name or "").strip()

        if not name:
            raise ValidationError(
                f"نام {field_label} مشخص نیست."
            )

        return name

    # =========================================================
    # اعتبارسنجی بانک و ساختمان
    # =========================================================

    @staticmethod
    def _get_financial_house(
        *,
        bank,
        house=None,
    ):
        financial_house = house or bank.house

        if not financial_house:
            raise ValidationError(
                "ساختمان برای ثبت تراکنش مشخص نیست."
            )

        if bank.house_id and bank.house_id != financial_house.pk:
            raise ValidationError(
                "بانک انتخاب‌شده متعلق به ساختمان تراکنش نیست."
            )

        return financial_house

    # =========================================================
    # شماره سند مالی
    # =========================================================

    @staticmethod
    def _get_document_number(
        *,
        financial_house,
        financial_document_number=None,
    ):
        if financial_document_number is not None:
            return financial_document_number

        return get_next_financial_document_number(
            financial_house
        )

    # =========================================================
    # DEPOSIT - واریز
    # =========================================================

    @staticmethod
    @transaction.atomic
    def deposit(
        *,
        user,
        bank: Bank,
        unit=None,
        amount: Decimal,
        description: str,
        content_object=None,
        payment_date=None,
        payer_type=None,
        payer_renter=None,
        payer_name=None,
        payer_third_party=None,
        transaction_no=None,
        gateway="پرداخت الکترونیک",
        house=None,
        transfer_group_id=None,
        financial_document_number=None,
    ):

        amount = Decimal(str(amount or 0))

        if amount <= 0:
            raise ValidationError(
                "مبلغ تراکنش باید بیشتر از صفر باشد."
            )

        if payer_type not in (
            None, "owner", "renter", "other"
        ):
            raise ValidationError(
                f"نوع پرداخت‌کننده نامعتبر است: {payer_type}"
            )

        # قفل بانک
        bank = (
            Bank.objects
            .select_for_update()
            .get(pk=bank.pk)
        )

        financial_house = (
            BankTransactionService._get_financial_house(
                bank=bank,
                house=house,
            )
        )

        # -----------------------------------------------------
        # پرداخت‌کننده مستأجر
        # -----------------------------------------------------

        if payer_type == "renter":

            if not payer_renter or not payer_renter.unit:
                raise ValidationError(
                    "مستأجر یا واحد پرداخت‌کننده مشخص نشده است."
                )

            if not payer_renter.renter_is_active:
                raise ValidationError(
                    "مستأجر پرداخت‌کننده فعال نیست."
                )

            unit = payer_renter.unit

            if (
                unit.myhouse_id
                and unit.myhouse_id != financial_house.pk
            ):
                raise ValidationError(
                    "واحد مستأجر متعلق به این ساختمان نیست."
                )

            renter_name = (
                payer_renter.renter_name or ""
            ).strip()

            if not renter_name:
                raise ValidationError(
                    "نام مستأجر پرداخت‌کننده مشخص نیست."
                )

            payer_name = f"واحد {unit.unit} - {renter_name}"
            payer_third_party = None

        # -----------------------------------------------------
        # پرداخت‌کننده مالک
        # -----------------------------------------------------

        elif payer_type == "owner":

            if not unit:
                raise ValidationError(
                    "واحد پرداخت‌کننده مشخص نشده است."
                )

            if (
                unit.myhouse_id
                and unit.myhouse_id != financial_house.pk
            ):
                raise ValidationError(
                    "واحد پرداخت‌کننده متعلق به این ساختمان نیست."
                )

            owner_name = (unit.owner_name or "").strip()

            if not owner_name:
                raise ValidationError(
                    "نام مالک پرداخت‌کننده مشخص نیست."
                )

            payer_name = f"واحد {unit.unit} - {owner_name}"
            payer_renter = None
            payer_third_party = None

        # -----------------------------------------------------
        # پرداخت‌کننده شخص ثالث
        # -----------------------------------------------------

        elif payer_type == "other":

            unit = None
            payer_renter = None

            payer_name = (
                BankTransactionService._validate_third_party(
                    third_party=payer_third_party,
                    house=financial_house,
                    field_label="شخص ثالث پرداخت‌کننده",
                )
            )

        else:
            payer_name = (payer_name or "").strip()
            payer_renter = None
            payer_third_party = None

        # -----------------------------------------------------
        # شماره سند مالی
        # -----------------------------------------------------

        financial_document_number = (
            BankTransactionService._get_document_number(
                financial_house=financial_house,
                financial_document_number=financial_document_number,
            )
        )

        # -----------------------------------------------------
        # ContentType
        # -----------------------------------------------------

        content_type = ContentType.objects.get_for_model(
            content_object or bank
        )

        # -----------------------------------------------------
        # ثبت واریز
        # -----------------------------------------------------

        fund = BankFund.objects.create(
            user=user,
            bank=bank,
            unit=unit,
            house=financial_house,
            amount=amount,
            payment_gateway=gateway,
            transaction_no=transaction_no,
            payment_date=payment_date,
            payment_description=description,
            transaction_type="deposit",

            payer_type=payer_type,
            payer_renter=(
                payer_renter
                if payer_type == "renter"
                else None
            ),
            payer_name=payer_name,
            payer_third_party=(
                payer_third_party
                if payer_type == "other"
                else None
            ),

            financial_document_number=(
                financial_document_number
            ),
            content_type=content_type,
            object_id=(
                content_object.pk
                if content_object
                else bank.pk
            ),
            balance_after=Decimal("0"),
            is_paid=True,
            transfer_group_id=transfer_group_id,
        )

        recalculate_bank_balance(bank)
        fund.refresh_from_db()

        return fund

    # =========================================================
    # WITHDRAW - برداشت
    # =========================================================

    @staticmethod
    @transaction.atomic
    def withdraw(
        *,
        user,
        bank: Bank,
        unit=None,
        amount: Decimal,
        description: str,
        content_object=None,
        payment_date=None,
        transaction_no=None,
        receiver_type=None,
        receiver_renter=None,
        receiver_name=None,
        receiver_third_party=None,
        gateway="پرداخت الکترونیک",
        house=None,
        transfer_group_id=None,
        financial_document_number=None,
    ):

        amount = Decimal(str(amount or 0))

        if amount <= 0:
            raise ValidationError(
                "مبلغ تراکنش باید بیشتر از صفر باشد."
            )

        if receiver_type not in (
            None, "owner", "renter", "other"
        ):
            raise ValidationError(
                f"نوع دریافت‌کننده نامعتبر است: {receiver_type}"
            )

        # قفل بانک
        bank = (
            Bank.objects
            .select_for_update()
            .get(pk=bank.pk)
        )

        financial_house = (
            BankTransactionService._get_financial_house(
                bank=bank,
                house=house,
            )
        )

        # -----------------------------------------------------
        # دریافت‌کننده مستأجر
        # -----------------------------------------------------

        if receiver_type == "renter":

            if not receiver_renter or not receiver_renter.unit:
                raise ValidationError(
                    "مستأجر یا واحد دریافت‌کننده مشخص نشده است."
                )

            if not receiver_renter.renter_is_active:
                raise ValidationError(
                    "مستأجر دریافت‌کننده فعال نیست."
                )

            unit = receiver_renter.unit

            if (
                unit.myhouse_id
                and unit.myhouse_id != financial_house.pk
            ):
                raise ValidationError(
                    "واحد مستأجر متعلق به این ساختمان نیست."
                )

            renter_name = (
                receiver_renter.renter_name or ""
            ).strip()

            if not renter_name:
                raise ValidationError(
                    "نام مستأجر دریافت‌کننده مشخص نیست."
                )

            receiver_name = f"واحد {unit.unit} - {renter_name}"
            receiver_third_party = None

        # -----------------------------------------------------
        # دریافت‌کننده مالک
        # -----------------------------------------------------

        elif receiver_type == "owner":

            if not unit:
                raise ValidationError(
                    "واحد دریافت‌کننده مشخص نشده است."
                )

            if (
                unit.myhouse_id
                and unit.myhouse_id != financial_house.pk
            ):
                raise ValidationError(
                    "واحد دریافت‌کننده متعلق به این ساختمان نیست."
                )

            owner_name = (unit.owner_name or "").strip()

            if not owner_name:
                raise ValidationError(
                    "نام مالک دریافت‌کننده مشخص نیست."
                )

            receiver_name = f"واحد {unit.unit} - {owner_name}"
            receiver_renter = None
            receiver_third_party = None

        # -----------------------------------------------------
        # دریافت‌کننده شخص ثالث
        # -----------------------------------------------------

        elif receiver_type == "other":

            unit = None
            receiver_renter = None

            receiver_name = (
                BankTransactionService._validate_third_party(
                    third_party=receiver_third_party,
                    house=financial_house,
                    field_label="شخص ثالث دریافت‌کننده",
                )
            )

        else:
            receiver_name = (receiver_name or "").strip()
            receiver_renter = None
            receiver_third_party = None

        # -----------------------------------------------------
        # محاسبه موجودی و کنترل برداشت
        # -----------------------------------------------------

        result = recalculate_bank_balance(bank)

        real_balance = Decimal(
            str(result["calculated_balance"])
        )

        if real_balance < amount:
            raise ValidationError(
                f"موجودی حساب کافی نیست. "
                f"موجودی فعلی: {real_balance:,.0f} تومان، "
                f"مبلغ برداشت: {amount:,.0f} تومان."
            )

        # -----------------------------------------------------
        # شماره سند مالی
        # -----------------------------------------------------

        financial_document_number = (
            BankTransactionService._get_document_number(
                financial_house=financial_house,
                financial_document_number=financial_document_number,
            )
        )

        # -----------------------------------------------------
        # ContentType
        # -----------------------------------------------------

        content_type = ContentType.objects.get_for_model(
            content_object or bank
        )

        # -----------------------------------------------------
        # ثبت برداشت
        # -----------------------------------------------------

        fund = BankFund.objects.create(
            user=user,
            bank=bank,
            unit=unit,
            house=financial_house,
            amount=amount,
            payment_gateway=gateway,
            transaction_no=transaction_no,
            payment_date=payment_date,
            payment_description=description,
            transaction_type="withdraw",

            receiver_type=receiver_type,
            receiver_renter=(
                receiver_renter
                if receiver_type == "renter"
                else None
            ),
            receiver_name=receiver_name,
            receiver_third_party=(
                receiver_third_party
                if receiver_type == "other"
                else None
            ),

            financial_document_number=(
                financial_document_number
            ),
            content_type=content_type,
            object_id=(
                content_object.pk
                if content_object
                else bank.pk
            ),
            balance_after=Decimal("0"),
            transfer_group_id=transfer_group_id,
            is_paid=True,
        )

        recalculate_bank_balance(bank)
        fund.refresh_from_db()

        return fund

    # =========================================================
    # TRANSFER - انتقال بین بانک‌ها
    # =========================================================

    @staticmethod
    @transaction.atomic
    def transfer(
        *,
        user,
        from_bank: Bank,
        to_bank: Bank,
        unit=None,
        amount: Decimal,
        description: str,
        payment_date=None,
        transaction_no=None,
        content_object=None,
        transfer_group_id=None,
        house=None,
        financial_document_number=None,
        receiver_type=None,
        receiver_renter=None,
        receiver_name=None,
        receiver_third_party=None,
        payer_type=None,
        payer_renter=None,
        payer_name=None,
        payer_third_party=None,
    ):

        amount = Decimal(str(amount or 0))

        if amount <= 0:
            raise ValidationError(
                "مبلغ انتقال باید بیشتر از صفر باشد."
            )

        if from_bank.pk == to_bank.pk:
            raise ValidationError(
                "بانک مبدأ و مقصد نمی‌توانند یکسان باشند."
            )

        # -----------------------------------------------------
        # قفل بانک‌ها با ترتیب ثابت برای کاهش احتمال deadlock
        # -----------------------------------------------------

        bank_ids = sorted([
            from_bank.pk,
            to_bank.pk,
        ])

        locked_banks = list(
            Bank.objects
            .select_for_update()
            .filter(pk__in=bank_ids)
            .order_by("pk")
        )

        bank_map = {
            bank.pk: bank
            for bank in locked_banks
        }

        if (
            from_bank.pk not in bank_map
            or to_bank.pk not in bank_map
        ):
            raise ValidationError(
                "بانک مبدأ یا مقصد پیدا نشد."
            )

        from_bank = bank_map[from_bank.pk]
        to_bank = bank_map[to_bank.pk]

        # -----------------------------------------------------
        # کنترل ساختمان
        # -----------------------------------------------------

        financial_house = (
            house
            or from_bank.house
            or to_bank.house
        )

        if not financial_house:
            raise ValidationError(
                "ساختمان برای ایجاد شماره سند مالی مشخص نیست."
            )

        for current_bank in (from_bank, to_bank):
            if (
                current_bank.house_id
                and current_bank.house_id != financial_house.pk
            ):
                raise ValidationError(
                    "هر دو بانک باید متعلق به ساختمان تراکنش باشند."
                )

        # -----------------------------------------------------
        # کنترل موجودی بانک مبدأ
        # -----------------------------------------------------

        source_result = recalculate_bank_balance(
            from_bank
        )

        source_balance = Decimal(
            str(source_result["calculated_balance"])
        )

        if source_balance < amount:
            raise ValidationError(
                f"موجودی حساب مبدأ کافی نیست. "
                f"موجودی فعلی: {source_balance:,.0f} تومان، "
                f"مبلغ انتقال: {amount:,.0f} تومان."
            )

        # -----------------------------------------------------
        # شماره سند مشترک
        # -----------------------------------------------------

        financial_document_number = (
            BankTransactionService._get_document_number(
                financial_house=financial_house,
                financial_document_number=financial_document_number,
            )
        )

        group_id = transfer_group_id or uuid.uuid4()

        # -----------------------------------------------------
        # برداشت از بانک مبدأ
        # -----------------------------------------------------

        withdrawal = BankTransactionService.withdraw(
            user=user,
            bank=from_bank,
            unit=unit,
            amount=amount,
            transaction_no=transaction_no,
            description=(
                f"انتقال به {to_bank.bank_name} - {description}"
            ),
            payment_date=payment_date,
            content_object=content_object,
            transfer_group_id=group_id,
            house=financial_house,
            financial_document_number=financial_document_number,
            receiver_type=receiver_type,
            receiver_renter=receiver_renter,
            receiver_name=receiver_name,
            receiver_third_party=receiver_third_party,
        )

        # -----------------------------------------------------
        # واریز به بانک مقصد
        # -----------------------------------------------------

        deposit = BankTransactionService.deposit(
            user=user,
            bank=to_bank,
            unit=unit,
            amount=amount,
            transaction_no=transaction_no,
            description=(
                f"دریافت از {from_bank.bank_name} - {description}"
            ),
            payment_date=payment_date,
            content_object=content_object,
            transfer_group_id=group_id,
            house=financial_house,
            financial_document_number=financial_document_number,
            payer_type=payer_type,
            payer_renter=payer_renter,
            payer_name=payer_name,
            payer_third_party=payer_third_party,
        )

        recalculate_bank_balance(from_bank)
        recalculate_bank_balance(to_bank)

        return {
            "withdraw": withdrawal,
            "deposit": deposit,
            "transfer_group_id": group_id,
        }


# =============================================================
# اعتبارسنجی تاریخ تراکنش بانکی
# =============================================================

def validate_bank_transaction_date(bank, payment_date):

    if not bank or not payment_date:
        return

    opening_date = bank.create_at

    if not opening_date:
        return

    if payment_date < opening_date:
        opening_date_jalali = jdatetime.date.fromgregorian(
            date=opening_date
        )

        raise ValidationError(
            "تاریخ تراکنش نمی‌تواند قبل از تاریخ افتتاح حساب "
            f"({opening_date_jalali.strftime('%Y/%m/%d')}) باشد."
        )

