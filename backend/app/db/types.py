"""Database-portable exact decimal storage for financial amounts."""

from decimal import Decimal, InvalidOperation

from sqlalchemy import Numeric, String
from sqlalchemy.types import TypeDecorator


class MoneyAmount(TypeDecorator):
    """Use SQL DECIMAL and exact decimal text for SQLite, avoiding float affinity."""

    impl = Numeric(19, 4, asdecimal=True)
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(Numeric(19, 4, asdecimal=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
        if not amount.is_finite() or amount.as_tuple().exponent < -4:
            raise ValueError("Financial amounts must be finite with at most four decimal places")
        if abs(amount) >= Decimal("1000000000000000"):
            raise ValueError("Financial amount exceeds DECIMAL(19,4) precision")
        return (
            format(amount.quantize(Decimal("0.0001")), "f") if dialect.name == "sqlite" else amount
        )

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        try:
            amount = value if isinstance(value, Decimal) else Decimal(str(value))
            return amount.quantize(Decimal("0.0001"))
        except InvalidOperation as exc:
            raise ValueError("Database contains an invalid financial amount") from exc
