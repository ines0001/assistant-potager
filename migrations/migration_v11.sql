-- =============================================================================
-- migration_v11.sql — Ajout FK parcelle_id sur evenements
-- =============================================================================
-- Relie la colonne texte `parcelle` à la table `parcelles` via une clé étrangère.
-- Idempotent : utilise IF NOT EXISTS / ON CONFLICT, safe à rejouer.
--
-- Prérequis : migration_v10.sql (table parcelles) doit être appliquée.
--
-- Exécution depuis psql :
--   psql -U potager_user -d potager -f migration_v11.sql
-- =============================================================================

-- [1] Ajout de la colonne FK (nullable pour rétrocompatibilité avec l'historique)
ALTER TABLE evenements
    ADD COLUMN IF NOT EXISTS parcelle_id INTEGER REFERENCES parcelles(id);

-- Index pour les jointures et filtres par parcelle
CREATE INDEX IF NOT EXISTS ix_evenements_parcelle_id ON evenements(parcelle_id);

-- [2] Rétro-remplissage : résoudre le texte libre `parcelle` vers parcelles.id
--     via normalisation identique à normalize_parcelle_name() Python :
--     lower + unaccent + suppression tirets/espaces
UPDATE evenements e
SET    parcelle_id = p.id
FROM   parcelles p
WHERE  lower(regexp_replace(unaccent(e.parcelle), '[\s\-]+', '', 'g'))
       = p.nom_normalise
  AND  e.parcelle     IS NOT NULL
  AND  e.parcelle     <> ''
  AND  e.parcelle_id  IS NULL;

-- [3] Vérification post-migration
SELECT
    COUNT(*)                                        AS total_evenements,
    COUNT(*) FILTER (WHERE parcelle IS NOT NULL)    AS avec_texte_parcelle,
    COUNT(*) FILTER (WHERE parcelle_id IS NOT NULL) AS resolus_fk,
    COUNT(*) FILTER (
        WHERE parcelle IS NOT NULL
          AND parcelle_id IS NULL
    )                                               AS non_resolus
FROM evenements;
-- Attendu : non_resolus = 0 si toutes les parcelles du texte existent bien en table.
