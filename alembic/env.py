import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.core.config import settings
from app.db.base import Base

# Register all models so Alembic can detect schema changes
import app.models.command  # noqa: F401
import app.models.task     # noqa: F401
import app.models.note     # noqa: F401
import app.models.project  # noqa: F401
import app.models.goal     # noqa: F401
import app.models.contact  # noqa: F401
import app.models.finance  # noqa: F401
import app.models.event    # noqa: F401
import app.models.user     # noqa: F401
import app.models.approval # noqa: F401
import app.models.organization # noqa: F401
import app.models.execution # noqa: F401
import app.models.integration # noqa: F401
import app.models.memory # noqa: F401
import app.models.email # noqa: F401
import app.models.daily_run # noqa: F401
import app.models.employee # noqa: F401
import app.models.integration_signal # noqa: F401
import app.models.ops_metrics # noqa: F401
import app.models.decision_log # noqa: F401
import app.models.policy_rule # noqa: F401
import app.models.weekly_report # noqa: F401
import app.models.ai_call_log  # noqa: F401
import app.models.chat_message  # noqa: F401
import app.models.ceo_control  # noqa: F401
import app.models.clone_control  # noqa: F401
import app.models.clone_performance  # noqa: F401
import app.models.conversation  # noqa: F401
import app.models.daily_plan  # noqa: F401
import app.models.decision_trace  # noqa: F401
import app.models.github  # noqa: F401
import app.models.media_project  # noqa: F401
import app.models.org_membership  # noqa: F401
import app.models.notification  # noqa: F401
import app.models.social  # noqa: F401
import app.models.threat_signal  # noqa: F401
import app.models.whatsapp_message  # noqa: F401
import app.models.self_learning_run  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Generate a SQL script without connecting to the DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
