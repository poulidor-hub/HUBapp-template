-- Convertit les tables de démonstration `items` et `test_data` en TIMESTAMPTZ.
-- Séparé de 001 : en mode --clean (INITIALISE), ces tables n'existent jamais —
-- ALTER TABLE IF EXISTS évite le warning « relation does not exist » au boot.
-- Forme statement simple : le splitter SQL coupe sur ';' (pas de DO block).

ALTER TABLE IF EXISTS items
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';

ALTER TABLE IF EXISTS test_data
  ALTER COLUMN created_at TYPE TIMESTAMPTZ USING created_at AT TIME ZONE 'UTC',
  ALTER COLUMN updated_at TYPE TIMESTAMPTZ USING updated_at AT TIME ZONE 'UTC';
