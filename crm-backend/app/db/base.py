import re
from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Shared declarative base for all ORM models.

    Auto-derives __tablename__ from the class name:
        Lead        → leads
        Application → applications
    """

    @declared_attr.directive
    def __tablename__(cls) -> str:  # noqa: N805
        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return f"{name}s"


# ── Import every model here so Alembic can detect them ───────────────────────
# from app.models.lead import Lead          # noqa: F401  ← uncomment as you add models
