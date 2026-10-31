"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.modules.businesses.router import router as businesses_router
from app.modules.documents.router import router as documents_router
from app.modules.identity.router import router as identity_router
from app.modules.reconciliation.router import router as reconciliation_router

app = FastAPI(title="LedgerPilot API", version="0.1.0")
allowed_origins = [
    origin.strip() for origin in get_settings().cors_allowed_origins.split(",") if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(identity_router)
app.include_router(businesses_router)
app.include_router(documents_router)
app.include_router(reconciliation_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report API process health; database readiness is verified separately."""
    return {"status": "ok"}
