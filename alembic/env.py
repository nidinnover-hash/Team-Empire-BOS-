import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

import app.models.ai_call_log
import app.models.approval
import app.models.ceo_control
import app.models.chat_message
import app.models.clone_control
import app.models.clone_performance

# Register all models so Alembic can detect schema changes
import app.models.command
import app.models.contact
import app.models.conversation
import app.models.daily_plan
import app.models.daily_run
import app.models.decision_log
import app.models.decision_trace
import app.models.email
import app.models.employee
import app.models.event
import app.models.execution
import app.models.finance
import app.models.github
import app.models.goal
import app.models.integration
import app.models.integration_signal
import app.models.media_project
import app.models.memory
import app.models.note
import app.models.notification
import app.models.ops_metrics
import app.models.org_membership
import app.models.organization
import app.models.policy_rule
import app.models.project
import app.models.quote
import app.models.sales_playbook
import app.models.self_learning_run
import app.models.social
import app.models.survey
import app.models.task
import app.models.threat_signal
import app.models.user
import app.models.weekly_report
import app.models.whatsapp_message  # noqa: F401

# Batch 17: customer health, meetings, document signing, leaderboard, dedup, stage gates, activity goals
import app.models.customer_health  # noqa: F401
import app.models.meeting_scheduler  # noqa: F401
import app.models.document_signing  # noqa: F401
import app.models.sales_leaderboard  # noqa: F401
import app.models.dedup_rule  # noqa: F401
import app.models.stage_gate  # noqa: F401
import app.models.activity_goal  # noqa: F401

# Batch 18: subscriptions, drip campaigns, lead scoring, onboarding, forecast scenarios, feature requests, audit trail
import app.models.subscription  # noqa: F401
import app.models.drip_campaign  # noqa: F401
import app.models.lead_score_rule  # noqa: F401
import app.models.onboarding_checklist  # noqa: F401
import app.models.forecast_scenario  # noqa: F401
import app.models.feature_request  # noqa: F401
import app.models.audit_entry  # noqa: F401

# Batch 19: call logs, drip analytics, deal splits, contact merge logs, product bundles, forecast rollups, conversion funnels
import app.models.call_log  # noqa: F401
import app.models.drip_analytics  # noqa: F401
import app.models.deal_split  # noqa: F401
import app.models.contact_merge_log  # noqa: F401
import app.models.product_bundle  # noqa: F401
import app.models.forecast_rollup  # noqa: F401
import app.models.conversion_funnel  # noqa: F401

# Batch 20: revenue goals, deal dependencies, contact timeline, email warmup, territory assignments, quote approvals, win/loss
import app.models.revenue_goal  # noqa: F401
import app.models.deal_dependency  # noqa: F401
import app.models.contact_timeline  # noqa: F401
import app.models.email_warmup  # noqa: F401
import app.models.territory_assignment  # noqa: F401
import app.models.quote_approval  # noqa: F401
import app.models.win_loss_analysis  # noqa: F401

from alembic import context
from app.core.config import settings
from app.db.base import Base

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("%", "%%"))

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
        connect_args={"server_settings": {"statement_timeout": "0"}},
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
