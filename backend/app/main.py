"""FastAPI application entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.modules.businesses.router import router as businesses_router
from app.modules.documents.router import router as documents_router
from app.modules.identity.router import router as identity_router

app = FastAPI(title="LedgerPilot API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.include_router(identity_router)
app.include_router(businesses_router)
app.include_router(documents_router)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Report API process health; database readiness is verified separately."""
    return {"status": "ok"}
