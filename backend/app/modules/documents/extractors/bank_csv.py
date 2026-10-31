"""Bank transaction extraction from CSV, without float conversion."""

import re
from dataclasses import dataclass
from decimal import Decimal
from io import BytesIO

import pandas as pd

from app.modules.documents.extractors.common import parse_amount, parse_currency, parse_date


@dataclass
class BankCsvResult:
    transactions: list[dict]
    errors: list[dict[str, str]]


def _normalise_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _find_column(columns: dict[str, str], names: set[str]) -> str | None:
    return next((columns[name] for name in names if name in columns), None)


def _validation_errors(fields: dict) -> list[dict[str, str]]:
    errors = []
    for name in ("transaction_date", "amount", "description", "currency"):
        value = fields.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            errors.append(
                {
                    "field": name,
                    "code": "missing_or_invalid",
                    "message": f"Review the {name.replace('_', ' ')} value.",
                }
            )
    return errors


def extract_bank_csv(content: bytes) -> BankCsvResult:
    frame = pd.read_csv(BytesIO(content), dtype=str, keep_default_na=False, encoding="utf-8-sig")
    original_columns = [str(column) for column in frame.columns]
    columns = {_normalise_header(column): column for column in original_columns}
    date_column = _find_column(columns, {"date", "transactiondate", "posteddate", "postingdate"})
    description_column = _find_column(
        columns, {"description", "memo", "details", "payee", "merchant", "transactiondescription"}
    )
    amount_column = _find_column(columns, {"amount", "transactionamount"})
    debit_column = _find_column(columns, {"debit", "withdrawal", "debitamount"})
    credit_column = _find_column(columns, {"credit", "deposit", "creditamount"})
    currency_column = _find_column(columns, {"currency", "currencycode", "ccy"})
    reference_column = _find_column(columns, {"reference", "transactionid", "checknumber", "fitid"})

    missing = []
    if date_column is None:
        missing.append("date")
    if description_column is None:
        missing.append("description")
    if amount_column is None and debit_column is None and credit_column is None:
        missing.append("amount or debit/credit")
    if missing:
        return BankCsvResult(
            transactions=[],
            errors=[
                {
                    "code": "required_columns_missing",
                    "message": "CSV is missing required columns: " + ", ".join(missing),
                }
            ],
        )

    output = []
    for offset, raw in enumerate(frame.to_dict(orient="records"), start=2):
        raw_values = {str(key): str(value) for key, value in raw.items()}
        raw_date = raw_values.get(date_column, "")
        raw_description = raw_values.get(description_column, "") if description_column else ""
        raw_currency = raw_values.get(currency_column, "") if currency_column else ""
        raw_amount = raw_values.get(amount_column, "") if amount_column else None

        if amount_column:
            amount = parse_amount(raw_amount)
        else:
            debit_raw = raw_values.get(debit_column, "") if debit_column else ""
            credit_raw = raw_values.get(credit_column, "") if credit_column else ""
            debit = parse_amount(debit_raw) if debit_raw.strip() else Decimal(0)
            credit = parse_amount(credit_raw) if credit_raw.strip() else Decimal(0)
            amount = credit - debit if debit is not None and credit is not None else None

        description = raw_description.strip() or None
        if description is not None and len(description) > 500:
            description = None
        fields = {
            "transaction_date": parse_date(raw_date),
            "description": description,
            "amount": amount,
            "currency": parse_currency(raw_currency),
            "external_reference": (
                raw_values.get(reference_column, "").strip()[:200] or None
                if reference_column
                else None
            ),
        }
        errors = _validation_errors(fields)
        if description is None and raw_description.strip():
            errors.append(
                {
                    "field": "description",
                    "code": "too_long",
                    "message": "Description exceeds 500 characters.",
                }
            )
        output.append(
            {
                "source_row_number": offset,
                "source_location": f"CSV row {offset}",
                "fields": fields,
                "errors": errors,
                "raw_data": raw_values,
            }
        )
    if not output:
        return BankCsvResult(
            transactions=[],
            errors=[
                {
                    "code": "no_transaction_rows",
                    "message": "CSV contains headers but no transaction rows.",
                }
            ],
        )
    return BankCsvResult(transactions=output, errors=[])
