**Titre :** Fournir une aide contextuelle ciblée via /help [commande]

**Story :**
En tant que jardinier
Je veux saisir `/help parcelle` (ou `/help semis`, `/help recolte`, etc.) pour obtenir une aide détaillée sur cette seule commande
Afin de comprendre rapidement toutes les options et usages possibles sans lire l'aide générale complète

**Critères d'acceptance :**
- [x] CA1 : La commande `/help <mot-clé>` retourne un message dédié au domaine ou à la commande demandée (ex : `/help parcelle`, `/help semis`, `/help stock`, `/help recolte`, `/help stats`)
- [x] CA2 : Le message contextuel liste toutes les variantes de saisie reconnues pour ce domaine (options, mots-clés alternatifs)
- [x] CA3 : Chaque variante est accompagnée d'au moins 1 exemple concret de message vocal ou texte à envoyer au bot
- [x] CA4 : Si le mot-clé n'est pas reconnu, le bot répond avec la liste des mots-clés d'aide disponibles (ex : `Mots-clés disponibles : parcelle, semis, recolte, stock, stats, godet`)
- [x] CA5 : La commande `/help` sans argument continue d'afficher l'aide générale existante (rétrocompatibilité)
- [x] CA6 : Chaque message d'aide contextuelle reste ≤ 4096 chars et lisible sur écran mobile

**Notes fonctionnelles :**
- Zone fonctionnelle concernée : interaction Telegram (bot.py, handler `/help`)
- Migration BDD requise : non
- Dépendances : US_Restructurer_help_4_domaines (à livrer après, ou en parallèle si la structure générale est stable)
- Contenu 100% statique, zéro token Groq
- Mots-clés d'aide à couvrir en priorité : `parcelle`, `semis`, `recolte`, `stock`, `stats`, `godet`
- Le parsing du mot-clé est insensible à la casse et aux accents (`Récolte` = `recolte`)

**Estimation :** 3 points

**Scénario Gherkin :**
```gherkin
Feature: /help contextuel par commande

  Scenario: Aide détaillée sur les parcelles
    Given le bot est démarré
    When le jardinier envoie "/help parcelle"
    Then le bot répond avec un message dédié aux parcelles
    And le message liste toutes les options reconnues (créer, lister, affecter, libérer…)
    And chaque option est illustrée par au moins 1 exemple de saisie

  Scenario: Aide détaillée sur les semis
    When le jardinier envoie "/help semis"
    Then le bot répond avec un message dédié aux semis
    And le message distingue semis pépinière et pleine terre
    And fournit des exemples vocaux concrets

  Scenario: Mot-clé inconnu
    When le jardinier envoie "/help truc"
    Then le bot répond "Mot-clé non reconnu."
    And liste les mots-clés d'aide disponibles

  Scenario: Aide générale inchangée
    When le jardinier envoie "/help"
    Then le bot affiche l'aide générale complète (comportement existant)
```

**Labels GitHub :** `us`, `sprint-next`, `bot`, `ux`, `help`, `priorite-haute`

---

## Maquettes des messages affichés

> Ces maquettes définissent le contenu attendu de chaque réponse contextuelle. Le développeur doit les reproduire à l'identique (emojis, structure, exemples).

---

### `/help parcelle`

```
📍 Aide — Parcelles

Gérer et consulter vos parcelles du potager.

── Plan d'occupation ──────────────────────────
• Vue globale de toutes les parcelles
  → /plan
  → "plan du potager"

• Vue détaillée d'une parcelle
  → /plan nord
  → "plan parcelle nord"
  → "qu'est-ce qui pousse en nord ?"

── Gestion des parcelles ──────────────────────
• Lister toutes les parcelles connues
  → /parcelle lister
  → /parcelles

• Créer une nouvelle parcelle
  → /parcelle ajouter nord
  → /parcelle ajouter nord sud 12.5
    (nom · exposition · superficie en m²)

• Modifier les métadonnées d'une parcelle
  → /parcelle modifier nord exposition=sud
  → /parcelle modifier nord superficie=8.5
  → /parcelle modifier nord exposition=sud superficie=8.5
  Paramètres : exposition · superficie · ordre

💡 Noms de parcelle insensibles à la casse.
   Les doublons sont détectés automatiquement.
```

---

### `/help semis`

```
🌱 Aide — Semis

Enregistrer vos semis en pépinière ou en pleine terre.

Actions disponibles :
• Semis en pépinière
  → "semis tomates variété Saint-Pierre le 5 mars"
  → "j'ai semé 30 graines de basilic en plateau"

• Semis en pleine terre
  → "semis direct carottes en parcelle B2"
  → "semis radis pleine terre parcelle A3 le 8 avril"

• Consulter les semis en cours
  → "liste de mes semis"
  → "quels semis sont en cours ?"

💡 Précisez toujours : culture · variété (optionnel) · date · lieu
```

---

### `/help godet`

```
🪴 Aide — Mise en godet

Suivre le repiquage des plants de pépinière en godet.

Actions disponibles :
• Enregistrer une mise en godet
  → "mise en godet tomates Saint-Pierre 20 plants"
  → "repiquer 15 plants de poivron en godet le 10 mars"

• Consulter les godets en attente
  → "liste des godets"
  → "quels plants sont en godet ?"

💡 La mise en godet est l'étape entre le semis plateau
   et la plantation en parcelle.
```

---

### `/help recolte`

```
🧺 Aide — Récoltes

Enregistrer vos récoltes ponctuelles ou finales.

Actions disponibles :
• Récolte ponctuelle (culture continue)
  → "récolté 800g de tomates en A1"
  → "cueilli 3 courgettes parcelle B2 aujourd'hui"

• Récolte finale / clôture de culture
  → "récolte finale haricots parcelle A3"
  → "dernière récolte courgettes B2, culture terminée"

• Récolte de graines
  → "récolte graines tomates Saint-Pierre 15g"
  → "mis de côté graines courge pour semis prochain"

• Consulter l'historique
  → "historique récoltes"
  → "mes récoltes du mois de mars"
```

---

### `/help stock`

```
📦 Aide — Stock

Suivre vos stocks de semences et intrants.

Actions disponibles :
• Consulter le stock
  → "stock tomates"
  → "combien de graines de basilic il me reste ?"

• Ajouter au stock
  → "ajout stock carottes Nantaise 50g"
  → "reçu 1 sachet poivron Corno di Toro"

• Déduire du stock (automatique après semis)
  → Le stock est mis à jour automatiquement
    à chaque semis enregistré.

• Alertes stock faible
  → Le bot signale automatiquement si un stock
    passe sous le seuil critique.
```

---

### `/help stats`

```
📊 Aide — Statistiques

Consulter les bilans de votre potager.

Actions disponibles :
• Statistiques générales
  → "/stats"
  → "bilan du potager"

• Stats par culture
  → "stats tomates"
  → "bilan courgettes cette saison"

• Stats par parcelle
  → "stats parcelle A1"
  → "bilan rotation parcelle B2"

• Synthèse des semis
  → "synthèse semis"
  → "récapitulatif de mes semis"

• Bilan de rotation
  → "rotation des cultures"
  → "quelles familles ont occupé chaque parcelle ?"
```

---

### Mot-clé inconnu — `/help truc`

```
❓ Mot-clé "truc" non reconnu.

Mots-clés disponibles :
  parcelle · semis · godet · recolte · stock · stats

Exemple : /help parcelle
```

