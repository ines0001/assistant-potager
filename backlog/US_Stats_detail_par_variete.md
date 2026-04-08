**Titre :** Afficher les statistiques détaillées par variété d'une culture

**Story :**
En tant que jardinier
Je veux interroger l'assistant pour obtenir le détail des stats d'une culture par variété
Afin de comparer les performances de mes variétés et orienter mes choix de semis futurs

**Critères d'acceptance :**
- [ ] CA1 : `/stats` sans argument conserve le comportement actuel (synthèse par culture)
- [ ] CA2 : Le pied du message `/stats` contient le hint "*Pour le détail d'une variété : /stats [culture]*"
- [ ] CA3 : `/stats tomate` retourne un message par variété de tomate avec ses indicateurs propres
- [ ] CA4 : Chaque bloc variété affiche : nom variété, nb plants, quantité récoltée, période de **première plantation → dernière récolte** (ou "en cours" si aucune récolte finale)
- [ ] CA5 : Si une culture n'a qu'une seule variété (ou variété non renseignée), le message l'indique clairement ("Variété non précisée")
- [ ] CA6 : Si la culture demandée n'existe pas en base, le bot répond "Aucune donnée pour [culture]"
- [ ] CA7 : La commande est insensible à la casse (`/stats Tomate` = `/stats tomate`)
- [ ] CA8 : La commande vocale "stats tomate" est reconnue et redirigée vers le même handler

**Exemples d'affichage attendus :**

`/stats tomate` (reproducteur) :
```
🍅 Tomate — détail par variété

🔸 Cœur de Bœuf
  • 3 plants actifs · 4.2 kg récoltés (6 fois)
    (planté 3)
  📅 15 avr → 12 sept 2025

🔸 Cerise
  • 2 plants actifs · 3.8 kg récoltés (12 fois)
    (planté 2, perdu 0)
  📅 20 avr → en cours

🔸 Variété non précisée
  • 1 plant actif · 0.9 kg récoltés (2 fois)
    (planté 1)

_Pour revenir à la synthèse : /stats_
```

`/stats salade` (végétatif) :
```
🥬 Salade — détail par variété

🔸 Batavia
  • 8 plants (planté 12, perdu 1, récolté 3)
  📅 10 mars → en cours

🔸 Romaine
  • 0 plant (planté 5, récolté 5)
  📅 01 avr → 18 mai 2025

_Pour revenir à la synthèse : /stats_
```

**Notes fonctionnelles :**
- Zone fonctionnelle : consultation / stats
- Migration BDD requise : non (la variété est déjà un champ existant ou à vérifier)
- Calcul des dates : `MIN(Evenement.date WHERE type_action='plantation')` → `MAX(Evenement.date WHERE type_action='recolte')` par culture + variété ; affiche "en cours" si aucune récolte enregistrée
- La période est uniforme pour les deux types (végétatif et reproducteur) : plantation → dernière récolte
- Dépendances : US-003 (Afficher stats agronomiquement), US_Modéliser_type_organe_récolté
- L'affichage doit respecter le type d'organe récolté (végétatif vs reproducteur) hérité de US-003

**Estimation :** 3 points

**Scénario Gherkin :**
```gherkin
Feature: Détail des statistiques par variété

  Scenario: /stats seul conserve la vue synthétique
    Given des cultures Tomate (2 variétés) et Courgette (1 variété) en base
    When l'utilisateur envoie /stats
    Then le message affiche la synthèse par culture
    And le pied du message contient "Pour le détail d'une variété : /stats [culture]"

  Scenario: /stats avec nom de culture affiche le détail par variété
    Given 3 plants de "Tomate Cœur de Bœuf" plantés le 15 avr avec 4.2 kg récoltés
    And 2 plants de "Tomate Cerise" plantés le 20 avr sans récolte finale
    When l'utilisateur envoie /stats tomate
    Then le message contient un bloc "Cœur de Bœuf" avec "4.2 kg récoltés" et "📅 15 avr → [date dernière récolte]"
    And le message contient un bloc "Cerise" avec "📅 20 avr → en cours"
    And le message ne contient pas d'autres cultures
    And le pied du message contient "Pour revenir à la synthèse : /stats"

  Scenario: Variété non renseignée
    Given 4 plants de Courgette sans variété précisée
    When l'utilisateur envoie /stats courgette
    Then le message contient un bloc "Variété non précisée" avec le nb de plants et la période plantation → dernière récolte

  Scenario: Culture inexistante
    Given aucune culture "Aubergine" en base
    When l'utilisateur envoie /stats aubergine
    Then le bot répond "Aucune donnée pour Aubergine"

  Scenario: Insensibilité à la casse
    Given des plants de Tomate en base
    When l'utilisateur envoie /stats Tomate
    Then le comportement est identique à /stats tomate
```

**Labels GitHub :** `us`, `stats`, `variete`, `telegram-ux`
