-- Base de test pour Assistant Potager
-- Insérer ces données dans la table 'evenements'
-- Dates : février-mars 2026
-- Actions : semis, plantation, arrosage, recolte, observation

INSERT INTO evenements (date, type_action, culture, variete, quantite, unite, parcelle, rang, duree, traitement, commentaire, texte_original) VALUES
-- Février 2026 - Semis et plantations initiales
('2026-02-05', 'semis', 'carotte', 'nantaise', NULL, NULL, 'est', NULL, NULL, NULL, 'semis en ligne espacées de 5 cm', 'semis carottes nantaise parcelle est'),
('2026-02-10', 'semis', 'radis', NULL, NULL, NULL, 'sud', NULL, NULL, NULL, 'semis direct en poquets', 'semis radis carré sud'),
('2026-02-12', 'plantation', 'tomate', 'coeur de boeuf', 30, 'plants', 'sud', 3, NULL, NULL, 'plantation en rangs de 3 plants chacun', 'planté 30 tomates coeur de boeuf sur 3 rangs parcelle sud'),
('2026-02-15', 'semis', 'salade', 'batavia', NULL, NULL, 'ouest', NULL, NULL, NULL, 'semis en serre pour précocité', 'semis salades batavia parcelle ouest'),
('2026-02-18', 'plantation', 'courgette', NULL, 15, 'plants', 'nord', 2, NULL, NULL, 'plantation espacée pour éviter maladies', 'planté 15 courgettes sur 2 rangs parcelle nord'),
('2026-02-20', 'arrosage', 'tomate', NULL, NULL, NULL, 'sud', NULL, 20, NULL, 'arrosage léger après plantation', 'arrosage tomates parcelle sud 20 minutes'),
('2026-02-22', 'observation', NULL, NULL, NULL, NULL, 'sud', NULL, NULL, NULL, 'pluie abondante, sol bien humidifié', 'observation pluie abondante carré sud'),
('2026-02-25', 'semis', 'oignon', 'blanc', NULL, NULL, 'est', NULL, NULL, NULL, 'semis en caissettes pour repiquage', 'semis oignons blancs parcelle est'),

-- Mars 2026 - Arrosages, récoltes, observations
('2026-03-01', 'arrosage', 'carotte', NULL, NULL, NULL, 'est', NULL, 15, NULL, 'arrosage régulier pour germination', 'arrosage carottes parcelle est 15 minutes'),
('2026-03-03', 'recolte', 'radis', NULL, 0.5, 'kg', 'sud', NULL, NULL, NULL, 'récolte précoce, taille moyenne', 'récolté 500g de radis carré sud'),
('2026-03-05', 'observation', 'tomate', NULL, NULL, NULL, 'sud', NULL, NULL, NULL, 'pousses vigoureuses, hauteur 10 cm', 'observation tomates poussent bien parcelle sud'),
('2026-03-07', 'arrosage', 'courgette', NULL, NULL, NULL, 'nord', NULL, 25, NULL, 'arrosage en profondeur', 'arrosage courgettes parcelle nord 25 minutes'),
('2026-03-10', 'plantation', 'poivron', 'rouge', 10, 'plants', 'ouest', 1, NULL, NULL, 'plantation en serre', 'planté 10 poivrons rouges sur 1 rang parcelle ouest'),
('2026-03-12', 'semis', 'persil', NULL, NULL, NULL, 'est', NULL, NULL, NULL, 'semis en bordure pour accessibilité', 'semis persil parcelle est'),
('2026-03-14', 'recolte', 'salade', 'batavia', 1.2, 'kg', 'ouest', NULL, NULL, NULL, 'récolte pour consommation familiale', 'récolté 1.2 kg de salades batavia parcelle ouest'),
('2026-03-16', 'observation', NULL, NULL, NULL, NULL, 'nord', NULL, NULL, NULL, 'pluie fine, pas besoin d''arroser', 'observation pluie fine parcelle nord'),
('2026-03-18', 'arrosage', 'oignon', NULL, NULL, NULL, 'est', NULL, 10, NULL, 'arrosage modéré pour éviter pourriture', 'arrosage oignons parcelle est 10 minutes'),
('2026-03-20', 'plantation', 'aubergine', NULL, 8, 'plants', 'sud', 2, NULL, NULL, 'plantation ensoleillée', 'planté 8 aubergines sur 2 rangs carré sud'),
('2026-03-22', 'recolte', 'tomate', 'coeur de boeuf', 2.5, 'kg', 'sud', NULL, NULL, NULL, 'premières tomates de saison', 'récolté 2.5 kg de tomates coeur de boeuf parcelle sud'),
('2026-03-24', 'observation', 'courgette', NULL, NULL, NULL, 'nord', NULL, NULL, NULL, 'fleurs apparues, pollinisation naturelle', 'observation courgettes en fleurs parcelle nord'),
('2026-03-26', 'arrosage', 'poivron', NULL, NULL, NULL, 'ouest', NULL, 30, NULL, 'arrosage abondant après plantation', 'arrosage poivrons parcelle ouest 30 minutes');