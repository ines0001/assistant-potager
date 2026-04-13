**ID :** US-006
**Titre :** Renommer une parcelle avec propagation sur toutes les données

**Story :**
En tant que jardinier
Je veux pouvoir renommer une parcelle existante via le bot
Afin que le nouveau nom soit immédiatement reflété dans tous les événements, l'historique et les affichages

**Contexte technique :**
La table `parcelles` contient `nom` et `nom_normalise`.
La table `evenements` contient `parcelle` (String dénormalisé) et `parcelle_id` (FK Integer).
Un renommage doit mettre à jour : `parcelles.nom`, `parcelles.nom_normalise`, et `evenements.parcelle` pour tous les événements liés.

**Critères d'acceptance :**
- [ ] CA1 : La sous-commande `/parcelle renommer <ancien_nom> <nouveau_nom>` est reconnue par le bot
- [ ] CA2 : `parcelles.nom` et `parcelles.nom_normalise` sont mis à jour en base
- [ ] CA3 : Tous les enregistrements `evenements.parcelle` correspondant à l'ancien nom sont mis à jour avec le nouveau nom
- [ ] CA4 : Si l'ancien nom n'existe pas, le bot répond "Parcelle introuvable : <ancien_nom>"
- [ ] CA5 : Si le nouveau nom est déjà utilisé par une autre parcelle, le bot répond "Ce nom est déjà utilisé par une autre parcelle"
- [ ] CA6 : La confirmation affiche le nombre d'événements mis à jour : "Parcelle renommée : <ancien> → <nouveau> (42 événements mis à jour)"
- [ ] CA7 : Le renommage fonctionne indépendamment de la casse et des accents (résolution via `nom_normalise`)
- [ ] CA8 : La commande `/help parcelles` (ou aide contextuelle équivalente) mentionne `/parcelle renommer` avec un exemple d'utilisation
- [ ] CA9 : En cas d'appel sans arguments ou incomplet, le bot affiche le message d'aide : "Usage : /parcelle renommer <ancien_nom> <nouveau_nom> — ex : /parcelle renommer sud carré-sud"

**Notes fonctionnelles :**
- Zone fonctionnelle concernée : interaction Telegram | gestion parcelles | aide contextuelle
- Migration BDD requise : non (colonnes existantes)
- Dépendances : US_Plan_occupation_parcelles (modèle `Parcelle`), US_Aide_contextuelle_par_commande (mise à jour du /help)
- Sécurité : vérifier que la mise à jour est atomique (transaction SQL)

**Estimation :** 2 points

**Scénario Gherkin :**
```gherkin
Feature: Renommage d'une parcelle

  Scenario: Renommage nominal avec propagation
    Given la parcelle "sud" existe avec 15 événements associés
    When le jardinier envoie "/parcelle renommer sud carré-sud"
    Then parcelles.nom vaut "carré-sud" et nom_normalise vaut "carre-sud"
    And les 15 événements ont evenements.parcelle = "carré-sud"
    And le bot répond "Parcelle renommée : sud → carré-sud (15 événements mis à jour)"

  Scenario: Ancien nom introuvable
    When le jardinier envoie "/parcelle renommer inexistante nouveau"
    Then le bot répond "Parcelle introuvable : inexistante"

  Scenario: Nouveau nom déjà utilisé
    Given les parcelles "nord" et "sud" existent
    When le jardinier envoie "/parcelle renommer nord sud"
    Then le bot répond "Ce nom est déjà utilisé par une autre parcelle"

  Scenario: Renommage insensible à la casse
    Given la parcelle "Sud" existe
    When le jardinier envoie "/parcelle renommer sud nouveau-nom"
    Then la parcelle est trouvée et renommée correctement
  Scenario: Appel sans arguments — affichage de l'aide
    When le jardinier envoie "/parcelle renommer" (sans arguments)
    Then le bot répond "Usage : /parcelle renommer <ancien_nom> <nouveau_nom>"
    And affiche l'exemple : "/parcelle renommer sud carré-sud"

  Scenario: Aide contextuelle mise à jour
    When le jardinier envoie "/help parcelles"
    Then la réponse contient "/parcelle renommer <ancien> <nouveau>"
    And contient l'exemple "ex : /parcelle renommer sud carré-sud"
```

**Labels GitHub :** `us`, `sprint-courant`, `parcelles`, `bot`
