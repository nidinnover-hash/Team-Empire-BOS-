-- Seed staging users (idempotent — uses ON CONFLICT)
-- Run in Supabase SQL Editor after migration

-- Org 1: Team Empire Org
INSERT INTO organizations (name, slug)
VALUES ('Team Empire Org', 'team-empire-org')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

-- Org 2: Team Empire India
INSERT INTO organizations (name, slug)
VALUES ('Team Empire India', 'team-empire-india')
ON CONFLICT (slug) DO UPDATE SET name = EXCLUDED.name;

-- User 1: CEO for Team Empire Org (staging-admin@empireoe.com)
INSERT INTO users (organization_id, email, name, password_hash, role, is_active, token_version, is_super_admin, created_at)
VALUES (
  (SELECT id FROM organizations WHERE slug = 'team-empire-org'),
  'staging-admin@empireoe.com',
  'Staging Admin',
  'pbkdf2_sha256$600000$PY9fMaR6RYBq0kpRnMaITQ==$/Z+Dwz58OsU05lZmWtOdWVq1olcGmwGPThWirVV5FxQ=',
  'CEO',
  true,
  1,
  false,
  NOW()
)
ON CONFLICT (email) DO UPDATE SET
  organization_id = EXCLUDED.organization_id,
  name = EXCLUDED.name,
  password_hash = EXCLUDED.password_hash,
  role = EXCLUDED.role,
  is_active = EXCLUDED.is_active;

-- User 2: ADMIN for Team Empire India (staging-india@empireoe.com)
INSERT INTO users (organization_id, email, name, password_hash, role, is_active, token_version, is_super_admin, created_at)
VALUES (
  (SELECT id FROM organizations WHERE slug = 'team-empire-india'),
  'staging-india@empireoe.com',
  'Staging India Admin',
  'pbkdf2_sha256$600000$AP7yIs1dJ3dXhfqKPqPExw==$Z/xaliQPCp23HDBYHq1WIDA+n98KZFOHrc9vTr9uga4=',
  'ADMIN',
  true,
  1,
  false,
  NOW()
)
ON CONFLICT (email) DO UPDATE SET
  organization_id = EXCLUDED.organization_id,
  name = EXCLUDED.name,
  password_hash = EXCLUDED.password_hash,
  role = EXCLUDED.role,
  is_active = EXCLUDED.is_active;
