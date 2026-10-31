"""Declarative base for application models and Alembic metadata."""

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql.functions import Function


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


@compiles(Function, "sqlite")
def compile_sqlite_functions(element, compiler, **kw):
    if element.name.casefold() == "sysutcdatetime":
        return "CURRENT_TIMESTAMP"
    return compiler.visit_function(element, **kw)
