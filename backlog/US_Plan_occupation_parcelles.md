**Titre :** Afficher le plan d'occupation actuel du potager par parcelle

**Référence GitHub :** issue #18 — [FEATURE] Multi-parcelles — table parcelles + commande /plan

**Story :**
En tant que jardinier
Je veux consulter le plan d'occupation actuel de mon potager parcelle par parcelle
Afin de savoir en un coup d'œil ce qui pousse où, l'âge de mes plants et les parcelles libres disponibles pour mes prochains semis

**Critères d'acceptance :**
- [ ] CA1 : `/plan` retourne un message structuré par parcelle listant les cultures actives avec leur variété et leur nombre de plants
- [ ] CA2 : Chaque culture affiche son **âge en jours** (J+ depuis la première plantation sur cette parcelle/culture)
- [ ] CA3 : Les cultures dont l'âge dépasse un seuil typique pour leur type (végétatif ≥ 45 j, reproducteur ≥ 90 j) sont marquées `⚠️ récolte imminente`
- [ ] CA4 : Les parcelles sans culture active sont affichées comme `🟢 [NOM] — Libre`
- [ ] CA5 : `/plan nord` filtre l'affichage sur la parcelle "nord" (insensible à la casse)
- [ ] CA6 : Le pied du message contient le hint `_Pour le détail d'une parcelle : /plan [nom]_` et un renvoi vers la commande d'analyse de rotation
- [ ] CA7 : Les cultures sans parcelle renseignée sont regroupées sous `📍 Non localisé`
- [ ] CA8 : La table `parcelles` est créée en BDD pour stocker les métadonnées de chaque parcelle (nom, exposition, superficie, ordre d'affichage)
- [ ] CA9 : La commande vocale "plan du potager" ou "plan parcelle nord" est reconnue et redirigée vers `/plan`
- [ ] CA10 : Lors de l'ajout d'une parcelle, un contrôle de doublon est effectué : si un nom identique ou une variante proche existe déjà (ex : "Nord" / "NORD" / "nord"), le bot refuse la création et affiche `❌ La parcelle "NORD" existe déjà`
- [ ] CA11 : La détection de variante s'appuie sur une normalisation (strip + lower + suppression des accents et tirets) avant comparaison ; "Serre-froide" et "Serre Froide" sont considérés comme identiques
- [ ] CA12 : En cas de variante proche détectée sans correspondance exacte, le bot propose : `⚠️ Une parcelle similaire existe : "Serre Froide". Confirmer la création de "Serre-froide" ? (oui / non)`
- [ ] CA13 : La commande `/parcelle ajouter [nom]` permet de créer une nouvelle parcelle ; un récapitulatif de toutes les parcelles existantes est affiché avant de demander confirmation

**Exemples d'affichage attendus :**

`/plan` (vue globale) :
```
📋 Plan d'occupation — 11 avr 2026

📍 NORD · 3 cultures actives
  🍅 Tomate Cœur de Bœuf — 3 plants · J+27
  🥬 Salade Batavia — 8 plants · J+32 ⚠️ récolte imminente
  🥕 Carotte Nantaise — 50 graines · J+15

📍 SUD · 2 cultures actives
  🌿 Courgette — 2 plants · J+18
  🫑 Poivron — 4 plants · J+12

🟢 EST — Libre
🟢 SERRE — Libre

📍 Non localisé · 1 culture
  🌱 Basilic — 20 plants · J+8

_Pour le détail : /plan [nom parcelle]_
_Historique de rotation : "rotation parcelle nord"_
```

`/plan nord` (vue parcelle) :
```
📍 NORD — Plan détaillé

🍅 Tomate Cœur de Bœuf
  3 plants actifs · plantés le 15 mars (J+27)
  Type : reproducteur · Rendement en cours : 0 kg

🥬 Salade Batavia
  8 plants · plantés le 10 mars (J+32)
  ⚠️ Récolte imminente (végétatif > 45 j)

🥕 Carotte Nantaise
  50 graines · semées le 27 mars (J+15)

_Historique de rotation : "rotation parcelle nord"_
```

**Notes fonctionnelles :**
- Zone fonctionnelle : consultation / dashboard / parcelles
- Migration BDD requise : **oui** — création table `parcelles` (id, nom, nom_normalise, exposition, superficie_m2, ordre, actif) ; `nom_normalise` (String unique) stocke la forme canonique (lower + sans accents + sans tirets/espaces) pour garantir l'unicité en BDD
- Le champ `parcelle` (String) sur `Evenement` reste la source de données principale ; la table `parcelles` sert uniquement aux métadonnées d'affichage (ordre, libellé, exposition)
- Normalisation : `strip().lower().replace("-", "").replace(" ", "")` + suppression des accents (ex : "Sère-Froide" → "serefroi­de") — fonction partagée `normalize_parcelle_name()` dans `utils/`
- Contrôle doublon : 1) comparaison exacte sur `nom_normalise` → refus immédiat ; 2) distance de Levenshtein ≤ 2 sur `nom_normalise` → confirmation demandée (CA12)
- Calcul âge : `date_today - MIN(Evenement.date WHERE type_action='plantation' AND culture=X AND parcelle=P)`
- Cultures "actives" = cultures ayant des plants en stock positif (réutilise `calcul_stock_cultures` de `utils/stock.py`)
- Seuil d'alerte configurable : végétatif ≥ 45 j, reproducteur ≥ 90 j (valeur par défaut, extensible via `culture_config`)
- Pas de table pivot : la jointure se fait par correspondance de la valeur `parcelle` (String) entre `Evenement` et `parcelles`
- Fichiers impactés : `migrations/migration_vX.sql`, `database/models.py`, `bot.py`, `utils/parcelles.py` (nouveau — normalisation + CRUD), `utils/stock.py` (optionnel)
- Dépendances : US_Bilan_rotation_par_parcelle (complémentaire — historique), US-002 `calcul_stock_cultures`

**Estimation :** 5 points

**Scénario Gherkin :**
```gherkin
Feature: Plan d'occupation du potager par parcelle

  Scenario: Vue globale /plan
    Given des plantations actives sur les parcelles NORD et SUD
    And la parcelle EST n'a aucune culture active
    When l'utilisateur envoie /plan
    Then le message contient une section "📍 NORD" avec les cultures actives
    And le message contient une section "📍 SUD" avec ses cultures
    And le message contient "🟢 EST — Libre"
    And le pied contient le hint de navigation

  Scenario: Affichage de l'âge des plants
    Given 3 plants de Tomate Cœur de Bœuf plantés il y a 27 jours sur NORD
    When l'utilisateur envoie /plan
    Then la ligne contient "J+27"

  Scenario: Alerte récolte imminente végétatif
    Given 8 plants de Salade Batavia plantés il y a 46 jours sur NORD
    And salade est classifiée type_organe_recolte = "végétatif"
    When l'utilisateur envoie /plan
    Then la ligne contient "⚠️ récolte imminente"

  Scenario: Pas d'alerte pour reproducteur avant 90 jours
    Given 3 plants de Tomate plantés il y a 27 jours
    And tomate est classifiée type_organe_recolte = "reproducteur"
    When l'utilisateur envoie /plan
    Then la ligne ne contient pas "⚠️"

  Scenario: Vue parcelle spécifique /plan nord
    Given des cultures sur NORD et sur SUD
    When l'utilisateur envoie /plan nord
    Then le message contient uniquement les cultures de la parcelle NORD
    And le message ne contient pas les cultures de SUD

  Scenario: Parcelle inconnue
    Given aucune culture sur la parcelle "OUEST"
    When l'utilisateur envoie /plan ouest
    Then le bot répond "Aucune culture active sur la parcelle OUEST"

  Scenario: Cultures sans parcelle
    Given une culture Basilic sans parcelle renseignée
    When l'utilisateur envoie /plan
    Then la section "📍 Non localisé" contient Basilic

  Scenario: Commande vocale
    Given le jardinier dicte "plan du potager"
    When le bot reçoit le message vocal transcrit
    Then le bot produit le même affichage que /plan

  Scenario: Création d'une parcelle sans doublon
    Given aucune parcelle "NORD" n'existe en base
    When l'utilisateur envoie /parcelle ajouter nord
    Then le bot affiche la liste des parcelles existantes
    And demande confirmation avant création
    And crée la parcelle avec nom_normalise = "nord"

  Scenario: Refus de doublon exact
    Given la parcelle "NORD" (nom_normalise="nord") existe déjà en base
    When l'utilisateur envoie /parcelle ajouter NORD
    Then le bot répond "❌ La parcelle "NORD" existe déjà"
    And aucune nouvelle ligne n'est insérée en base

  Scenario: Détection de variante proche et demande de confirmation
    Given la parcelle "Serre Froide" (nom_normalise="serrefroide") existe déjà
    When l'utilisateur envoie /parcelle ajouter Serre-froide
    Then le bot répond "⚠️ Une parcelle similaire existe : "Serre Froide". Confirmer la création ? (oui / non)"
    And si l'utilisateur répond "non" aucune parcelle n'est créée
    And si l'utilisateur répond "oui" la parcelle "Serre-froide" est créée avec son propre nom_normalise
```

---

## Référentiel des commandes — détail complet

> Pour chaque commande : syntaxe exacte, paramètres acceptés, comportement attendu et exemple de réponse du bot.

---

### `/plan` — Vue globale

**Syntaxe :** `/plan`  
**Commande vocale équivalente :** "plan du potager"

Affiche toutes les parcelles avec leurs cultures actives, l'âge des plants et les parcelles libres.

**Exemple de réponse :**
```
📋 Plan d'occupation — 11 avr 2026

📍 NORD · 3 cultures actives
  🍅 Tomate Cœur de Bœuf — 3 plants · J+27
  🥬 Salade Batavia — 8 plants · J+32 ⚠️ récolte imminente
  🥕 Carotte Nantaise — 50 graines · J+15

📍 SUD · 2 cultures actives
  🌿 Courgette — 2 plants · J+18
  🫑 Poivron — 4 plants · J+12

🟢 EST — Libre
🟢 SERRE — Libre

📍 Non localisé · 1 culture
  🌱 Basilic — 20 plants · J+8

_Pour le détail : /plan [nom parcelle]_
_Historique de rotation : "rotation parcelle nord"_
```

---

### `/plan [nom]` — Vue détaillée d'une parcelle

**Syntaxe :** `/plan nord`  
**Commande vocale équivalente :** "plan parcelle nord", "qu'est-ce qui pousse en nord ?"  
**Paramètres :**

| Paramètre | Obligatoire | Description |
|-----------|-------------|-------------|
| `nom` | oui | Nom de la parcelle (insensible à la casse) |

**Exemple de réponse :**
```
📍 NORD — Plan détaillé

🍅 Tomate Cœur de Bœuf
  3 plants actifs · plantés le 15 mars (J+27)
  Type : reproducteur · Rendement en cours : 0 kg

🥬 Salade Batavia
  8 plants · plantés le 10 mars (J+32)
  ⚠️ Récolte imminente (végétatif > 45 j)

🥕 Carotte Nantaise
  50 graines · semées le 27 mars (J+15)

_Historique de rotation : "rotation parcelle nord"_
```

**Cas d'erreur :**
```
❌ Aucune culture active sur la parcelle OUEST.
Parcelles connues : nord, sud, est, serre
```

---

### `/parcelle ajouter` — Créer une nouvelle parcelle

**Syntaxe complète :** `/parcelle ajouter [nom] [exposition] [superficie]`  
**Commande vocale équivalente :** "ajouter une nouvelle parcelle nord"

**Paramètres :**

| Paramètre | Obligatoire | Type | Description |
|-----------|-------------|------|-------------|
| `nom` | oui | texte | Nom unique de la parcelle (ex : `nord`, `serre-froide`) |
| `exposition` | non | texte | Orientation cardinale ou descriptive (ex : `sud`, `mi-ombre`) |
| `superficie` | non | décimal (m²) | Surface en m² (ex : `12.5`) |

**Exemples d'utilisation :**
```
/parcelle ajouter nord
/parcelle ajouter nord sud 12.5
/parcelle ajouter serre-froide mi-ombre 6
```

**Flux complet (création sans doublon) :**
```
Jardinier : /parcelle ajouter nord sud 12.5

Bot :
📋 Parcelles existantes :
  · SUD · 8 m²
  · EST · 6 m²
  · SERRE · 15 m²

➕ Créer la parcelle "NORD" (exposition : sud · superficie : 12.5 m²) ?
Répondez oui pour confirmer.

Jardinier : oui

Bot : ✅ Parcelle "NORD" créée avec succès.
```

**Cas d'erreur — doublon exact :**
```
Jardinier : /parcelle ajouter NORD

Bot : ❌ La parcelle "NORD" existe déjà.
Utilisez /plan pour consulter les parcelles existantes.
```

**Cas d'erreur — variante proche (Levenshtein ≤ 2) :**
```
Jardinier : /parcelle ajouter Serre-froide

Bot : ⚠️ Une parcelle similaire existe : "Serre Froide".
Confirmer la création de "Serre-froide" quand même ? (oui / non)

Jardinier : non
Bot : ↩️ Création annulée.
```

---

### `/parcelle modifier` — Mettre à jour les métadonnées

**Syntaxe complète :** `/parcelle modifier [nom] [clé=valeur ...]`  
**Commande vocale équivalente :** *(non supportée pour cette commande — saisie texte uniquement)*

**Paramètres :**

| Paramètre | Obligatoire | Type | Valeurs acceptées |
|-----------|-------------|------|-------------------|
| `nom` | oui | texte | Nom de la parcelle existante (insensible à la casse) |
| `exposition=` | non | texte | `nord`, `sud`, `est`, `ouest`, `mi-ombre`, `ombre`, `plein-soleil` |
| `superficie=` | non | décimal | Surface en m² (ex : `8.5`) |
| `ordre=` | non | entier | Position d'affichage dans `/plan` (ex : `1`) |

**Exemples d'utilisation :**
```
/parcelle modifier nord exposition=sud
/parcelle modifier nord superficie=8.5
/parcelle modifier nord exposition=sud superficie=8.5
/parcelle modifier serre-froide ordre=1 superficie=15
```

**Exemple de réponse (succès) :**
```
Jardinier : /parcelle modifier nord exposition=sud superficie=8.5

Bot : ✅ Parcelle "NORD" mise à jour :
  · Exposition : sud
  · Superficie : 8.5 m²
```

**Cas d'erreur — parcelle introuvable :**
```
Bot : ❌ Parcelle "OUEST" introuvable.
Parcelles connues : nord, sud, est, serre
```

**Cas d'erreur — paramètre inconnu :**
```
Jardinier : /parcelle modifier nord couleur=verte

Bot : ❌ Paramètre inconnu : "couleur".
Paramètres acceptés : exposition, superficie, ordre
```

---

### `/parcelle lister` — Afficher toutes les parcelles

**Syntaxe :** `/parcelle lister`  
**Alias :** `/parcelles`

**Exemple de réponse :**
```
📋 Parcelles enregistrées (4)

📍 NORD · exposition sud · 12.5 m²
📍 SUD · exposition nord · 8 m²
📍 EST · exposition est · 6 m²
🟢 SERRE · exposition mixte · 15 m² — aucune culture active

_Ajouter : /parcelle ajouter [nom] [exposition] [superficie]_
_Modifier : /parcelle modifier [nom] clé=valeur_
```

---

**Labels GitHub :** `us`, `feature`, `données`, `parcelle`, `dashboard`, `telegram-ux`, `deduplication`
