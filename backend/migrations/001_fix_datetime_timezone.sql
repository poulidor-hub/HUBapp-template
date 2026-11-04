-- SPDX-License-Identifier: MIT
-- Copyright (C) 2026 POULIDOR Audit & Développement (Valérian Poulidor)

-- Convertit les colonnes timestamps applicatives en TIMESTAMPTZ.
-- Les valeurs existantes sont interpretees comme UTC.
-- NB : les tables de démonstration `items` et `test_data` (retirées par
-- INITIALISE --clean) sont converties en 010, protégé par IF EXISTS.

ALTER TABLE user_preferences
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';

ALTER TABLE uploaded_files
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';
