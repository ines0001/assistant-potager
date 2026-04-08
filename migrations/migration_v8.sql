-- =============================================================================
-- migration_v8.sql — Cycle graines : champ origine_graines_id
-- =============================================================================
-- Ajoute le champ de traçabilité du cycle graines.
-- Idempotent : utilise IF NOT EXISTS, safe à rejouer.
--
-- Exécution depuis psql :
--   psql -U potager_user -d potager -f migration_v8.sql
-- =============================================================================

-- Champ FK nullable sur evenements → vers l'id de la recolte_graines source
-- Utilisé sur les semis pour relier l'origine des graines
ALTER TABLE evenements
    ADD COLUMN IF NOT EXISTS origine_graines_id INTEGER DEFAULT NULL
        REFERENCES evenements(id) ON DELETE SET NULL;

-- Vérification post-migration
SELECT column_name, data_type, is_nullable
FROM information_schema.columns
WHERE table_name = 'evenements'
  AND column_name = 'origine_graines_id'
ORDER BY column_name;
-- Attendu : 1 ligne, type integer, nullable YES
