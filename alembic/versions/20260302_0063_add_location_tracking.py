"""Add location tracking and checkin tables, employee consent column.

Revision ID: 20260302_0063
Revises: 20260302_0062
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260302_0063"
down_revision = "20260302_0062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "location_trackings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "employee_id",
            sa.Integer,
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("accuracy_m", sa.Float, nullable=True),
        sa.Column("altitude_m", sa.Float, nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "latitude >= -90 AND latitude <= 90",
            name="ck_location_lat_range",
        ),
        sa.CheckConstraint(
            "longitude >= -180 AND longitude <= 180",
            name="ck_location_lng_range",
        ),
        sa.CheckConstraint(
            "source IN ('gps', 'ip_geolocation', 'manual_checkin', 'google_maps')",
            name="ck_location_source_valid",
        ),
    )
    op.create_index(
        "ix_location_trackings_org_emp_created",
        "location_trackings",
        ["organization_id", "employee_id", "created_at"],
    )
    op.create_index(
        "ix_location_trackings_org_active",
        "location_trackings",
        ["organization_id", "is_active"],
    )

    op.create_table(
        "location_checkins",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column(
            "organization_id",
            sa.Integer,
            sa.ForeignKey("organizations.id", ondelete="RESTRICT"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "employee_id",
            sa.Integer,
            sa.ForeignKey("employees.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("latitude", sa.Float, nullable=False),
        sa.Column("longitude", sa.Float, nullable=False),
        sa.Column("place_name", sa.String(300), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("checkin_type", sa.String(20), nullable=False, server_default="arrival"),
        sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "checkin_type IN ('arrival', 'departure', 'meeting', 'site_visit', 'other')",
            name="ck_checkin_type_valid",
        ),
    )
    op.create_index(
        "ix_location_checkins_org_emp_created",
        "location_checkins",
        ["organization_id", "employee_id", "created_at"],
    )

    op.add_column(
        "employees",
        sa.Column(
            "location_tracking_consent",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("employees", "location_tracking_consent")
    op.drop_index("ix_location_checkins_org_emp_created", table_name="location_checkins")
    op.drop_table("location_checkins")
    op.drop_index("ix_location_trackings_org_active", table_name="location_trackings")
    op.drop_index("ix_location_trackings_org_emp_created", table_name="location_trackings")
    op.drop_table("location_trackings")
