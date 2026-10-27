from decimal import Decimal

from django.db import transaction
from django.db.models import F, Q

from admin_panel.models import BankFund


OPENING_DESCRIPTION = "افتتاحیه"


def get_opening_bank_funds(bank):
    """
    پیدا کردن رکوردهای افتتاحیه بانک.

    رکورد افتتاحیه ممکن است با یکی از این دو روش ثبت شده باشد:
    1. payment_gateway = افتتاحیه
    2. payment_description شامل افتتاحیه باشد
    """

    return list(
        BankFund.objects.filter(
            bank=bank
        ).filter(
            Q(payment_gateway="افتتاحیه") |
            Q(payment_description__icontains="افتتاحیه")
        ).order_by("payment_date", "created_at", "id")
    )


def get_bank_funds_ordered(bank):
    """
    ترتیب قطعی تراکنش‌های بانک.
    """

    return BankFund.objects.filter(
        bank=bank
    ).order_by(
        F("payment_date").asc(nulls_last=True),
        "created_at",
        "id",
    )


@transaction.atomic
def recalculate_bank_balance(bank):
    """
    محاسبه مجدد موجودی بانک و balance_after تمام BankFundها.

    منطق:

    حالت 1:
        اگر دقیقاً یک رکورد افتتاحیه وجود داشته باشد:
        موجودی از صفر شروع می‌شود و افتتاحیه نیز جزو تراکنش‌هاست.

    حالت 2:
        اگر رکورد افتتاحیه وجود نداشته باشد:
        موجودی از Bank.initial_fund شروع می‌شود.

    حالت 3:
        اگر هیچ BankFund وجود نداشته باشد:
        هیچ تغییری روی current_balance ایجاد نمی‌شود.

    اگر بیش از یک رکورد افتتاحیه وجود داشته باشد:
        برای جلوگیری از محاسبه اشتباه، عملیات متوقف می‌شود.
    """

    bank_model = bank.__class__

    bank = (
        bank_model.objects
        .select_for_update()
        .get(pk=bank.pk)
    )

    funds = list(
        BankFund.objects
        .select_for_update()
        .filter(bank=bank)
        .order_by(
            F("payment_date").asc(nulls_last=True),
            "created_at",
            "id",
        )
    )

    # -----------------------------------------
    # اگر هیچ تراکنشی وجود ندارد
    # -----------------------------------------

    if not funds:
        return {
            "bank": bank,
            "changed": False,
            "start_balance": Decimal(str(bank.initial_fund or 0)),
            "calculated_balance": Decimal(
                str(bank.current_balance or 0)
            ),
            "opening_mode": "no_funds",
            "fund_count": 0,
        }

    # -----------------------------------------
    # پیدا کردن رکوردهای افتتاحیه
    # -----------------------------------------

    opening_funds = [
        fund
        for fund in funds
        if (
            fund.payment_gateway == "افتتاحیه"
            or (
                fund.payment_description
                and "افتتاحیه" in fund.payment_description
            )
        )
    ]

    # -----------------------------------------
    # بیش از یک افتتاحیه
    # -----------------------------------------

    if len(opening_funds) > 1:
        raise ValueError(
            f"بانک {bank.id} دارای {len(opening_funds)} "
            f"رکورد افتتاحیه است. "
            f"ابتدا رکوردهای افتتاحیه اضافی را بررسی کنید."
        )

    # -----------------------------------------
    # تعیین موجودی اولیه محاسبات
    # -----------------------------------------

    if len(opening_funds) == 1:

        # افتتاحیه داخل BankFund وجود دارد.
        # بنابراین initial_fund نباید دوباره اضافه شود.

        balance = Decimal("0")

        opening_mode = "bankfund_opening"

        opening_fund_id = opening_funds[0].id

    else:

        # افتتاحیه در BankFund وجود ندارد.
        # بنابراین initial_fund نقطه شروع است.

        balance = Decimal(
            str(bank.initial_fund or 0)
        )

        opening_mode = "initial_fund"

        opening_fund_id = None

    # -----------------------------------------
    # محاسبه تمام تراکنش‌ها
    # -----------------------------------------

    changed_count = 0

    for fund in funds:

        amount = Decimal(
            str(fund.amount or 0)
        )

        if fund.transaction_type == "deposit":

            balance += amount

        elif fund.transaction_type == "withdraw":

            balance -= amount

        elif fund.transaction_type == "transfer":

            # در سیستم فعلی انتقال واقعی به صورت
            # withdraw از بانک مبدا
            # و deposit به بانک مقصد
            # ثبت می‌شود.

            if fund.to_bank_id:
                balance -= amount
            else:
                balance += amount

        else:

            raise ValueError(
                f"نوع تراکنش نامعتبر است: "
                f"{fund.transaction_type} "
                f"(BankFund ID={fund.id})"
            )

        # -----------------------------------------
        # اصلاح balance_after
        # -----------------------------------------

        if fund.balance_after != balance:

            fund.balance_after = balance

            fund.save(
                update_fields=["balance_after"]
            )

            changed_count += 1

    # -----------------------------------------
    # اصلاح current_balance
    # -----------------------------------------

    old_current_balance = Decimal(
        str(bank.current_balance or 0)
    )

    if old_current_balance != balance:

        bank.current_balance = balance

        bank.save(
            update_fields=["current_balance"]
        )

        bank_changed = True

    else:

        bank_changed = False

    return {
        "bank": bank,
        "changed": bank_changed or changed_count > 0,
        "old_current_balance": old_current_balance,
        "calculated_balance": balance,
        "opening_mode": opening_mode,
        "opening_fund_id": opening_fund_id,
        "fund_count": len(funds),
        "changed_fund_count": changed_count,
    }