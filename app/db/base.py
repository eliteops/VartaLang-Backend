"""Declarative base for all ORM models."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared metadata/registry for every SQLAlchemy model.

    Tables are created on startup (no migrations for the MVP), so all models
    must be imported before `Base.metadata.create_all` is called.
    """
