"""Text-based invoice extraction from PDF pages using PyMuPDF."""

import re
from dataclasses import dataclass

import pymupdf

from app.modules.documents.extractors.common import parse_amount, parse_currency, parse_date


@dataclass
class InvoicePdfResult:
    fields: dict
    locations: dict[str, str]
    errors: list[dict[str, str]]


_INVOICE_NUMBER = re.compile(
    r"\bInvoice\s*(?:Number|No\.?|#)\s*[:#]?\s*([A-Z0-9][A-Z0-9/-]{1,})", re.IGNORECASE
)
_INVOICE_DATE = re.compile(r"\bInvoice\s+Date\s*[:#]?\s*([^\r\n]+)", re.IGNORECASE)
_DUE_DATE = re.compile(r"\bDue\s+Date\s*[:#]?\s*([^\r\n]+)", re.IGNORECASE)
_TOTAL = re.compile(
    r"\b(?:Grand\s+Total|Total\s+Due|Amount\s+Due|Invoice\s+Total|Total\s+Amount|Total)"
    r"\s*[:\-]?\s*((?:USD|CAD|AUD|EUR|GBP|INR|JPY|CHF)?\s*[$€£₹]?\s*\(?-?\d[\d,]*(?:\.\d{1,4})?\)?)",
    re.IGNORECASE,
)
_CURRENCY = re.compile(r"\b(USD|CAD|AUD|EUR|GBP|INR|JPY|CHF)\b", re.IGNORECASE)
_VENDOR = re.compile(r"^\s*(?:Vendor|Supplier|From)\s*:\s*(.+?)\s*$", re.IGNORECASE)


def _first_match(pattern: re.Pattern, pages: list[str]) -> tuple[str | None, str | None]:
    for page_number, text in enumerate(pages, start=1):
        match = pattern.search(text)
        if match:
            return match.group(1).strip(), f"PDF page {page_number}"
    return None, None


def extract_invoice_pdf(content: bytes) -> InvoicePdfResult:
    with pymupdf.open(stream=content, filetype="pdf") as pdf:
        if pdf.needs_pass:
            raise ValueError("Password-protected PDFs are not supported for extraction.")
        if pdf.page_count > 300:
            raise ValueError("PDF exceeds the supported 300-page processing limit.")
        pages = [page.get_text("text") for page in pdf]

    combined = "\n".join(pages)
    invoice_number, invoice_number_location = _first_match(_INVOICE_NUMBER, pages)
    raw_date, date_location = _first_match(_INVOICE_DATE, pages)
    raw_due_date, due_date_location = _first_match(_DUE_DATE, pages)
    raw_total, total_location = _first_match(_TOTAL, pages)
    raw_currency, currency_location = _first_match(_CURRENCY, pages)

    vendor_name = None
    vendor_location = None
    for page_number, text in enumerate(pages, start=1):
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        explicit = next((_VENDOR.match(line) for line in lines if _VENDOR.match(line)), None)
        if explicit:
            vendor_name = explicit.group(1).strip()[:200] or None
            vendor_location = f"PDF page {page_number}"
            break
    if vendor_name is None and pages:
        for line_number, line in enumerate(pages[0].splitlines(), start=1):
            candidate = line.strip()
            if candidate and not re.search(
                r"invoice|date|bill\s+to|ship\s+to|total|page\s+\d", candidate, re.I
            ):
                vendor_name = candidate[:200]
                vendor_location = f"PDF page 1, line {line_number}"
                break

    fields = {
        "invoice_number": invoice_number,
        "vendor_name": vendor_name,
        "invoice_date": parse_date(raw_date),
        "due_date": parse_date(raw_due_date),
        "total_amount": parse_amount(raw_total),
        "currency": parse_currency(raw_currency),
    }
    locations = {
        "invoice_number": invoice_number_location or "PDF page 1",
        "vendor_name": vendor_location or "PDF page 1",
        "invoice_date": date_location or "PDF page 1",
        "due_date": due_date_location or "PDF page 1",
        "total_amount": total_location or "PDF page 1",
        "currency": currency_location or total_location or "PDF page 1",
    }
    errors = []
    for name in ("invoice_number", "vendor_name", "invoice_date", "total_amount", "currency"):
        if fields[name] is None or (isinstance(fields[name], str) and not fields[name].strip()):
            errors.append(
                {
                    "field": name,
                    "code": "missing_or_invalid",
                    "message": f"Review the {name.replace('_', ' ')} value against the PDF.",
                }
            )
    if not combined.strip():
        errors.append(
            {
                "code": "no_embedded_text",
                "message": (
                    "No selectable PDF text was found. This scanned document needs manual entry; "
                    "OCR is not configured."
                ),
            }
        )
    if raw_date and fields["invoice_date"] is None:
        errors.append(
            {
                "field": "invoice_date",
                "code": "date_ambiguous_or_invalid",
                "message": "Review the invoice date; its format could not be established safely.",
            }
        )
    if raw_total and fields["total_amount"] is None:
        errors.append(
            {
                "field": "total_amount",
                "code": "amount_invalid",
                "message": "Review the total; it is outside the supported decimal format.",
            }
        )
    if raw_due_date and fields["due_date"] is None:
        errors.append(
            {
                "field": "due_date",
                "code": "date_ambiguous_or_invalid",
                "message": "Review the due date; its format could not be established safely.",
            }
        )

    return InvoicePdfResult(fields=fields, locations=locations, errors=errors)
