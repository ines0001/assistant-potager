-- =============================================================================
-- migration_v10.sql — Table parcelles (US_Plan_occupation_parcelles)
-- =============================================================================
-- Crée la table `parcelles` pour gérer les parcelles physiques du potager.
-- Idempotent : utilise IF NOT EXISTS / ON CONFLICT, safe à rejouer.
--
-- Exécution depuis psql :
--   psql -U potager_user -d potager -f migration_v10.sql
-- =============================================================================

-- [CA8] Création de la table parcelles
CREATE TABLE IF NOT EXISTS parcelles (
    id            SERIAL PRIMARY KEY,
    nom           VARCHAR(255) NOT NULL,
    nom_normalise VARCHAR(255) UNIQUE NOT NULL,
    exposition    VARCHAR(50),
    superficie_m2 FLOAT,
    ordre         INTEGER DEFAULT 0,
    actif         BOOLEAN DEFAULT TRUE NOT NULL
);

-- Index sur nom_normalise pour les recherches rapides (CA10, CA11, CA12)
CREATE INDEX IF NOT EXISTS ix_parcelles_nom_normalise ON parcelles(nom_normalise);

-- [CA8] Prépopuler depuis les parcelles déjà utilisées dans evenements
-- Nécessite l'extension unaccent (activée par défaut sur PostgreSQL 13+)
-- SI unaccent n'est pas disponible : CREATE EXTENSION IF NOT EXISTS unaccent;
INSERT INTO parcelles (nom, nom_normalise, ordre)
SELECT DISTINCT
    parcelle,
    lower(regexp_replace(unaccent(parcelle), '[\s\-]+', '', 'g')),
    ROW_NUMBER() OVER (ORDER BY parcelle)
FROM evenements
WHERE parcelle IS NOT NULL
  AND parcelle <> ''
ON CONFLICT (nom_normalise) DO NOTHING;

-- Vérification post-migration
SELECT id, nom, nom_normalise, ordre, actif
FROM parcelles
ORDER BY ordre;
-- Attendu : autant de lignes que de parcelles distinctes dans evenements
