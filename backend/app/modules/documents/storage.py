"""Private local filesystem storage with traversal and frontend-public guards."""

from pathlib import Path

from app.core.config import get_settings


class DocumentStorageError(RuntimeError):
    """Raised when private storage cannot safely resolve or write a file."""


def get_storage_root() -> Path:
    configured = Path(get_settings().document_storage_root).expanduser()
    project_root = Path(__file__).resolve().parents[4]
    root = (
        (project_root / configured).resolve()
        if not configured.is_absolute()
        else configured.resolve()
    )
    public_frontend = (project_root / "frontend").resolve()
    if root == public_frontend or public_frontend in root.parents:
        raise DocumentStorageError("Document storage must remain outside the frontend directory")
    return root


def get_document_path(storage_key: str) -> Path:
    root = get_storage_root()
    candidate = (root / storage_key).resolve()
    if candidate == root or root not in candidate.parents:
        raise DocumentStorageError("Invalid private document storage key")
    return candidate


def save_document(storage_key: str, content: bytes) -> Path:
    path = get_document_path(storage_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as destination:
        destination.write(content)
    return path
