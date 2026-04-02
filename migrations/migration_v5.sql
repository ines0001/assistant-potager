-- =============================================================================
-- Migration v5 — Classification agronomique des cultures (US-001)
-- =============================================================================
-- À exécuter UNE SEULE FOIS depuis pgAdmin ou psql :
--   psql -U potager_user -d potager -f migrations/migration_v5.sql
--
-- Cette migration :
--   1. Ajoute la colonne type_organe_recolte à evenements
--   2. Crée la table culture_config avec index de performance
--   3. Pré-popule 25+ cultures françaises classiques
--   4. Rétropopule les événements existants
-- =============================================================================

-- [US-001 / CA1] Ajout colonne type_organe_recolte sur evenements
ALTER TABLE evenements
    ADD COLUMN IF NOT EXISTS type_organe_recolte VARCHAR(255);

-- [US-001 / CA2] Création de la table culture_config
CREATE TABLE IF NOT EXISTS culture_config (
    id                      SERIAL PRIMARY KEY,
    nom                     VARCHAR(255) UNIQUE NOT NULL,
    type_organe_recolte     VARCHAR(255) NOT NULL,   -- "végétatif" | "reproducteur"
    description_agronomique TEXT
);

-- Index pour les performances
CREATE INDEX IF NOT EXISTS idx_culture_config_nom  ON culture_config(nom);
CREATE INDEX IF NOT EXISTS idx_culture_config_type ON culture_config(type_organe_recolte);

-- [US-001 / CA3] Seed — cultures classiques françaises
-- Règle : ON CONFLICT DO NOTHING → idempotent, safe à rejouer
INSERT INTO culture_config (nom, type_organe_recolte, description_agronomique) VALUES

-- ── Légumes-feuilles (végétatif) ──────────────────────────────────────────────
('salade',         'végétatif',    'Feuille consommée directement, plante détruite à la récolte'),
('laitue',         'végétatif',    'Feuille, plante annuelle détruite à la récolte'),
('chou',           'végétatif',    'Feuille ou inflorescence, plante généralement détruite'),
('épinard',        'végétatif',    'Feuille, récolte possible par feuilles ou plant entier'),
('mâche',          'végétatif',    'Rosette de feuilles, récolte destructive'),

-- ── Racines (végétatif) ───────────────────────────────────────────────────────
('carotte',        'végétatif',    'Racine pivotante, plante détruite à la récolte'),
('betterave',      'végétatif',    'Racine tubérisée, plante détruite à la récolte'),
('radis',          'végétatif',    'Racine, plante annuelle rapide, récolte destructive'),
('navet',          'végétatif',    'Racine, plante bisannuelle mais récolte destructive'),
('panais',         'végétatif',    'Racine, plante bisannuelle, récolte destructive'),

-- ── Tiges / bulbes (végétatif) ────────────────────────────────────────────────
('oignon',         'végétatif',    'Bulbe, plante détruite à la récolte'),
('échalote',       'végétatif',    'Bulbe, plante détruite à la récolte'),
('ail',            'végétatif',    'Bulbe, plante annuelle détruite à la récolte'),
('poireau',        'végétatif',    'Faux-bulbe et tige, plante bisannuelle'),
('céleri',         'végétatif',    'Tige et feuilles, récolte destructive'),

-- ── Inflorescences (végétatif) ────────────────────────────────────────────────
('brocoli',        'végétatif',    'Inflorescence, plante bisannuelle'),
('chou-fleur',     'végétatif',    'Inflorescence, plante bisannuelle'),
('artichaut',      'végétatif',    'Capitule floral, plante pérenne mais récolte destructive'),

-- ── Tubercules (végétatif) ────────────────────────────────────────────────────
('pomme de terre', 'végétatif',    'Tubercule souterrain, plante détruite à la récolte'),
('patate douce',   'végétatif',    'Tubercule, plante annuelle sous nos latitudes'),

-- ── Fruits (reproducteur) ─────────────────────────────────────────────────────
('tomate',         'reproducteur', 'Fruit issu de la fleur, plante continue — stock reste vivant'),
('poivron',        'reproducteur', 'Fruit, plante annuelle productive sur toute la saison'),
('aubergine',      'reproducteur', 'Fruit, plante annuelle continue'),
('courgette',      'reproducteur', 'Fruit, plante annuelle très productive, récoltes répétées'),
('concombre',      'reproducteur', 'Fruit, plante annuelle, récoltes répétées'),
('haricot',        'reproducteur', 'Gousse (fruit), plante annuelle, récoltes répétées'),
('melon',          'reproducteur', 'Fruit, plante annuelle rampante'),
('pastèque',       'reproducteur', 'Fruit, plante annuelle, récolte unique par fruit mais plante continue'),
('fraise',         'reproducteur', 'Faux-fruit, plante pérenne productive sur toute la saison'),
('asperge',        'reproducteur', 'Turion, plante pérenne avec récoltes répétées sur plusieurs années')

ON CONFLICT (nom) DO NOTHING;

-- [US-001 / CA3] Rétropopulation des événements existants
-- Met à jour type_organe_recolte pour tous les événements dont la culture
-- correspond à une entrée dans culture_config
UPDATE evenements
SET    type_organe_recolte = cc.type_organe_recolte
FROM   culture_config cc
WHERE  evenements.culture          = cc.nom
  AND  evenements.type_organe_recolte IS NULL;

-- =============================================================================
-- Vérifications post-migration (à décommenter manuellement)
-- =============================================================================
-- SELECT COUNT(*) AS total_cultures FROM culture_config;
-- SELECT type_organe_recolte, COUNT(*) FROM culture_config GROUP BY 1;
-- SELECT culture, type_organe_recolte, COUNT(*) AS nb
--   FROM evenements WHERE type_organe_recolte IS NOT NULL
--   GROUP BY 1, 2 ORDER BY 1;
