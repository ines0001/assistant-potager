**Titre :** Afficher les statistiques détaillées par variété d'une culture

**Story :**
En tant que jardinier
Je veux interroger l'assistant pour obtenir le détail des stats d'une culture par variété
Afin de comparer les performances de mes variétés et orienter mes choix de semis futurs

**Critères d'acceptance :**
- [ ] CA1 : `/stats` sans argument conserve le comportement actuel (synthèse par culture)
- [ ] CA2 : Le pied du message `/stats` contient le hint "*Pour le détail d'une variété : /stats [culture]*"
- [ ] CA3 : `/stats tomate` retourne un message par variété de tomate avec ses indicateurs propres
- [ ] CA4 : Chaque bloc variété affiche : nom variété, nb plants, quantité récoltée, période (du … au …)
- [ ] CA5 : Si une culture n'a qu'une seule variété (ou variété non renseignée), le message l'indique clairement ("Variété non précisée")
- [ ] CA6 : Si la culture demandée n'existe pas en base, le bot répond "Aucune donnée pour [culture]"
- [ ] CA7 : La commande est insensible à la casse (`/stats Tomate` = `/stats tomate`)
- [ ] CA8 : La commande vocale "stats tomate" est reconnue et redirigée vers le même handler

**Notes fonctionnelles :**
- Zone fonctionnelle : consultation / stats
- Migration BDD requise : non (la variété est déjà un champ existant ou à vérifier)
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
    Given 3 plants de "Tomate Cœur de Bœuf" et 2 plants de "Tomate Cerise" en base
    When l'utilisateur envoie /stats tomate
    Then le message contient un bloc "Cœur de Bœuf" avec ses indicateurs
    And le message contient un bloc "Cerise" avec ses indicateurs
    And le message ne contient pas d'autres cultures

  Scenario: Variété non renseignée
    Given 4 plants de Courgette sans variété précisée
    When l'utilisateur envoie /stats courgette
    Then le message contient "Variété non précisée — 4 plants"

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
