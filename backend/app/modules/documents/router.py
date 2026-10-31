"""Business-scoped uploads, extraction previews, validation, and retry APIs."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse

from app.core.config import get_settings
from app.modules.documents.schemas import (
    DocumentDetail,
    DocumentRead,
    DocumentType,
    InvoiceVerification,
    TransactionVerification,
    UploadResult,
)
from app.modules.documents.service import (
    get_business_document,
    get_document_detail,
    list_business_documents,
    retry_document,
    upload_document,
    verify_invoice,
    verify_transaction,
)
from app.modules.documents.storage import get_document_path
from app.modules.identity.dependencies import CurrentUser, DbSession, require_business_membership

router = APIRouter(prefix="/api/v1/businesses/{business_id}/documents", tags=["documents"])
READ_ROLES = {"owner", "admin", "member", "viewer"}
WRITE_ROLES = {"owner", "admin", "member"}


@router.post("", response_model=UploadResult, status_code=status.HTTP_201_CREATED)
async def upload(
    business_id: UUID,
    db: DbSession,
    user: CurrentUser,
    response: Response,
    file: Annotated[UploadFile, File(...)],
    document_type: Annotated[DocumentType, Form()],
) -> UploadResult:
    require_business_membership(business_id, db, user, WRITE_ROLES)
    limit = get_settings().max_document_upload_mb * 1024 * 1024
    content = await file.read(limit + 1)
    document, duplicate = upload_document(
        db, business_id, user, document_type, file.filename, content
    )
    if duplicate:
        response.status_code = status.HTTP_200_OK
    return UploadResult(document=DocumentRead.model_validate(document), duplicate=duplicate)


@router.get("", response_model=list[DocumentRead])
def list_documents(business_id: UUID, db: DbSession, user: CurrentUser) -> list[DocumentRead]:
    require_business_membership(business_id, db, user, READ_ROLES)
    return [DocumentRead.model_validate(item) for item in list_business_documents(db, business_id)]


@router.get("/{document_id}", response_model=DocumentDetail)
def document_detail(
    business_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser
) -> DocumentDetail:
    require_business_membership(business_id, db, user, READ_ROLES)
    document = get_business_document(db, business_id, document_id)
    return DocumentDetail.model_validate(get_document_detail(db, document))


@router.get("/{document_id}/file")
def document_file(
    business_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser
) -> FileResponse:
    require_business_membership(business_id, db, user, READ_ROLES)
    document = get_business_document(db, business_id, document_id)
    path = get_document_path(document.storage_key)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Stored source file is unavailable")
    return FileResponse(
        path,
        media_type=document.content_type,
        filename=document.original_filename,
        content_disposition_type="inline",
    )


@router.post("/{document_id}/process", response_model=DocumentRead)
def process(business_id: UUID, document_id: UUID, db: DbSession, user: CurrentUser) -> DocumentRead:
    require_business_membership(business_id, db, user, WRITE_ROLES)
    document = get_business_document(db, business_id, document_id)
    return DocumentRead.model_validate(retry_document(db, document))


@router.patch("/{document_id}/invoices/{invoice_id}", response_model=DocumentDetail)
def verify_invoice_fields(
    business_id: UUID,
    document_id: UUID,
    invoice_id: UUID,
    data: InvoiceVerification,
    db: DbSession,
    user: CurrentUser,
) -> DocumentDetail:
    require_business_membership(business_id, db, user, WRITE_ROLES)
    document = get_business_document(db, business_id, document_id)
    verify_invoice(db, document, invoice_id, data, user)
    return DocumentDetail.model_validate(get_document_detail(db, document))


@router.patch("/{document_id}/transactions/{transaction_id}", response_model=DocumentDetail)
def verify_transaction_fields(
    business_id: UUID,
    document_id: UUID,
    transaction_id: UUID,
    data: TransactionVerification,
    db: DbSession,
    user: CurrentUser,
) -> DocumentDetail:
    require_business_membership(business_id, db, user, WRITE_ROLES)
    document = get_business_document(db, business_id, document_id)
    verify_transaction(db, document, transaction_id, data, user)
    return DocumentDetail.model_validate(get_document_detail(db, document))
