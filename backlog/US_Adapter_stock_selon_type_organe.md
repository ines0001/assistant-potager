US-002 : Adapter le calcul du stock réel selon le type d'organe
Titre : Adapter le calcul du stock selon que la récolte soit destructive ou continue

Story :
En tant que jardinier
Je veux que le stock des plants soit calculé différemment selon qu'il s'agisse de cultures récolte-destructive ou récolte-continue
Afin d'avoir un suivi précis : nombre de plants vivants vs rendement cumulé

Critères d'acceptance :

 CA1 : Pour les organes vegétatif : récolte réduit le stock de plants (récolte 1 plant = -1 du stock)
 CA2 : Pour les organes reproducteur : récolte n'affecte pas le stock de plants (toujours vivant)
 CA3 : Dans cmd_stats(), affichage différencié : "salade : 3 plants récoltés" vs "tomate : 5 plants actuels, 12 kg cumulés"
 CA4 : /stats JSON API retourne champs distincts : stock_plants + rendement_total_kg selon le type
Notes techniques :

Composants impactés : bot.py (cmd_stats), ia_orchestrator.py (build_question_context)
Migration BDD requise : non
Dépendances : #US-001
Estimation : 3 points

Scénario Gherkin :

```gherkin
Feature: Calcul du stock adapté au type d'organe récolté

  Scenario: Récolte d'une culture végétative réduit le stock
    Given un plant de salade avec stock = 4 et type_organe_recolte = "végétatif"
    When l'utilisateur enregistre une récolte de 1 plant de salade
    Then le stock de salade est décrémenté à 3
    And l'événement de récolte est enregistré en base

  Scenario: Récolte d'une culture reproductive ne réduit pas le stock
    Given un plant de tomate avec stock = 2 et type_organe_recolte = "reproducteur"
    When l'utilisateur enregistre une récolte de 1.5 kg de tomates
    Then le stock de tomate reste à 2
    And le rendement_total_kg de tomate est incrémenté de 1.5

  Scenario: Affichage différencié dans /stats Telegram
    Given des plants de salade (végétatif) et de tomate (reproducteur) en base
    When l'utilisateur envoie la commande /stats
    Then le message contient "salade : 3 plants récoltés"
    And le message contient "tomate : 5 plants actuels, 12 kg cumulés"

  Scenario: API /stats retourne les champs distincts
    Given des cultures des deux types en base
    When l'API reçoit GET /stats
    Then la réponse JSON contient stock_plants pour les cultures végétatives
    And la réponse JSON contient rendement_total_kg pour les cultures reproductrices
```

Labels GitHub : us, bot, scoring