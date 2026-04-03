-- =============================================================================
-- migration_v6.sql — Ajout des 46 nouvelles cultures Île-de-France (ids 100-145)
-- =============================================================================
-- Ce script insère UNIQUEMENT les nouvelles cultures (ids 100-145).
-- Les 30 cultures existantes (ids 1-90) ne sont PAS touchées.
-- ON CONFLICT DO NOTHING garantit l'idempotence : safe à rejouer.
--
-- Exécution depuis pgAdmin : ouvrir l'éditeur SQL, coller, exécuter (F5)
-- Exécution depuis psql :
--   psql -U potager_user -d potager --client-encoding=UTF8 -f migration_v6.sql
-- =============================================================================

INSERT INTO culture_config (id, nom, type_organe_recolte, description_agronomique) VALUES

-- ── Feuilles & salades ────────────────────────────────────────────────────────
(100, 'roquette',          'végétatif',    'Feuille poivrée, croissance rapide, récolte destructive ou en coupe'),
(101, 'mesclun',           'végétatif',    'Mélange de jeunes pousses, récolte en coupe successive'),
(102, 'cresson',           'végétatif',    'Feuille aquatique ou de jardin, récolte en coupe'),
(103, 'chou de Bruxelles', 'végétatif',    'Bourgeons axillaires, récolte échelonnée sur la tige — plante détruite en fin'),
(104, 'chou frisé',        'végétatif',    'Feuilles frisées, résistant au gel, récolte en coupe successive'),
(105, 'chou rouge',        'végétatif',    'Pomme de chou à feuilles rouges, récolte destructive'),
(106, 'chou rave',         'végétatif',    'Tige renflée hypocotyle, récolte destructive'),
(107, 'endive',            'végétatif',    'Chicorée witloof, forçage en cave, récolte destructive du chicon'),
(108, 'chicorée',          'végétatif',    'Feuilles amères, récolte en coupe ou destructive selon variété'),
(109, 'oseille',           'reproducteur', 'Feuilles acidulées, plante vivace — récolte en coupe sans détruire'),
(110, 'épinard perpétuel', 'reproducteur', 'Tétragone cornue, feuilles charnues, vivace productive'),
(111, 'bette',             'reproducteur', 'Côtes et feuilles, récolte en coupe successive — plante bisannuelle'),

-- ── Racines & tubercules ──────────────────────────────────────────────────────
(112, 'persil racine',     'végétatif',    'Racine pivotante aromatique, récolte destructive'),
(113, 'scorsonère',        'végétatif',    'Racine noire longue, bisannuelle, récolte destructive'),
(114, 'salsifis',          'végétatif',    'Racine blanche longue, bisannuelle, récolte destructive'),
(115, 'rutabaga',          'végétatif',    'Hybride chou-navet, racine tubérisée, récolte destructive'),
(116, 'topinambour',       'reproducteur', 'Tubercule souterrain, plante vivace — se resème seule d''une année à l''autre'),
(117, 'céleri-rave',       'végétatif',    'Renflement hypocotyle, récolte destructive'),

-- ── Bulbes & alliacées ────────────────────────────────────────────────────────
(118, 'oignon blanc',      'végétatif',    'Bulbe frais de printemps, récolte destructive précoce'),
(119, 'ciboulette',        'reproducteur', 'Feuilles fines, plante vivace — récolte en coupe sans détruire'),
(120, 'ail rose',          'végétatif',    'Bulbe, variété d''automne adaptée climat nord, récolte destructive'),

-- ── Légumineuses ──────────────────────────────────────────────────────────────
(121, 'petit pois',        'reproducteur', 'Gousse et graine, plante annuelle — plusieurs cueillettes possibles'),
(122, 'fève',              'reproducteur', 'Grande gousse, plante annuelle de printemps — récolte échelonnée'),
(123, 'haricot grimpant',  'reproducteur', 'Gousse, variété à rames, plus productive que le haricot nain'),
(124, 'pois gourmand',     'reproducteur', 'Gousse entière consommée, récolte échelonnée sur plusieurs semaines'),

-- ── Cucurbitacées ─────────────────────────────────────────────────────────────
(125, 'potiron',           'reproducteur', 'Fruit cucurbitacée, une à deux récoltes par plante en fin de saison'),
(126, 'courge butternut',  'reproducteur', 'Fruit cucurbitacée, conservation longue, récolte en fin de saison'),
(127, 'pâtisson',          'reproducteur', 'Fruit cucurbitacée décoratif, récolte échelonnée comme la courgette'),
(128, 'cornichon',         'reproducteur', 'Petit concombre à confire, récolte très fréquente en été'),

-- ── Aromatiques ───────────────────────────────────────────────────────────────
(129, 'persil',            'reproducteur', 'Feuilles aromatiques, bisannuelle — récolte en coupe sans détruire'),
(130, 'basilic',           'reproducteur', 'Feuilles aromatiques, annuelle thermophile — récolte en coupe'),
(131, 'thym',              'reproducteur', 'Feuilles aromatiques, vivace arbustive — récolte en coupe'),
(132, 'romarin',           'reproducteur', 'Feuilles aromatiques, vivace arbustive — récolte en coupe'),
(133, 'coriandre',         'végétatif',    'Feuilles et graines, annuelle — monte vite en graine, récolte rapide'),
(134, 'aneth',             'végétatif',    'Feuilles et ombelles aromatiques, annuelle — monte en graine rapidement'),
(135, 'menthe',            'reproducteur', 'Feuilles aromatiques, vivace envahissante — récolte en coupe'),
(136, 'estragon',          'reproducteur', 'Feuilles aromatiques, vivace — récolte en coupe toute la saison'),
(137, 'sarriette',         'reproducteur', 'Feuilles aromatiques, annuelle ou vivace — récolte en coupe'),
(138, 'cerfeuil',          'végétatif',    'Feuilles aromatiques fines, annuelle — monte vite, récolte rapide'),

-- ── Fleurs comestibles ────────────────────────────────────────────────────────
(139, 'capucine',          'reproducteur', 'Fleurs et feuilles comestibles, annuelle — récolte en coupe'),
(140, 'bourrache',         'reproducteur', 'Fleurs bleues comestibles, annuelle — ressème spontanément'),
(141, 'souci',             'reproducteur', 'Fleurs comestibles et médicinales, annuelle — récolte régulière'),

-- ── Fruits rouges & vivaces ───────────────────────────────────────────────────
(142, 'framboise',         'reproducteur', 'Fruit rouge, arbuste vivace — production annuelle sur cannes de 2 ans'),
(143, 'groseille',         'reproducteur', 'Fruit rouge ou blanc, arbuste vivace — production annuelle'),
(144, 'cassis',            'reproducteur', 'Fruit noir, arbuste vivace — production annuelle'),
(145, 'rhubarbe',          'reproducteur', 'Pétiole charnu, plante vivace pérenne — récolte en coupe chaque année')

ON CONFLICT (nom) DO NOTHING;

-- ── Vérification post-import ──────────────────────────────────────────────────
SELECT
    type_organe_recolte,
    COUNT(*) AS nb_cultures
FROM culture_config
GROUP BY type_organe_recolte
ORDER BY type_organe_recolte;
-- Attendu : végétatif = 39, reproducteur = 37, total = 76

SELECT COUNT(*) AS total FROM culture_config;
-- Attendu : 76
