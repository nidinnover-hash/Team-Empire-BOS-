-- Migration: 20260310_0087 -> 20260311_0088
-- Add soft delete columns (is_deleted, deleted_at) to Contact, Task, Deal, Goal, Project
-- Run in Supabase SQL Editor

BEGIN;

ALTER TABLE contacts ADD COLUMN is_deleted BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE contacts ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX ix_contacts_is_deleted ON contacts (is_deleted);

ALTER TABLE tasks ADD COLUMN is_deleted BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE tasks ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX ix_tasks_is_deleted ON tasks (is_deleted);

ALTER TABLE deals ADD COLUMN is_deleted BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE deals ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX ix_deals_is_deleted ON deals (is_deleted);

ALTER TABLE goals ADD COLUMN is_deleted BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE goals ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX ix_goals_is_deleted ON goals (is_deleted);

ALTER TABLE projects ADD COLUMN is_deleted BOOLEAN DEFAULT '0' NOT NULL;
ALTER TABLE projects ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE;
CREATE INDEX ix_projects_is_deleted ON projects (is_deleted);

UPDATE alembic_version SET version_num='20260311_0088' WHERE alembic_version.version_num = '20260310_0087';

COMMIT;
