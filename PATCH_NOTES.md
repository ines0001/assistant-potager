
## [v2.13.0] — 2026-04-11

### 🚀 Nouveautés
- Ajoute l'aide contextuelle par mot-clé : `/help parcelle`, `/help semis`, `/help godet`, `/help recolte`, `/help stock`, `/help stats` (US_Aide_contextuelle_par_commande)
- Enrichit `/help` sans argument d'une section "Aide ciblée" listant les thèmes disponibles ; mot-clé inconnu → liste des mots-clés valides (US_Aide_contextuelle_par_commande)
- Ajoute `/parcelle modifier [nom] clé=valeur...` pour mettre à jour exposition, superficie ou ordre d'une parcelle existante (US_Plan_occupation_parcelles)
- Ajoute `/parcelle lister` et son alias `/parcelles` pour lister toutes les parcelles (US_Plan_occupation_parcelles)
- Enrichit `/parcelle ajouter` pour accepter `[exposition]` et `[superficie]` en paramètres positionnels (US_Plan_occupation_parcelles)

### 🔧 Améliorations techniques
- Ajoute `update_parcelle` dans `utils/parcelles.py` avec validation des champs via `_CHAMPS_MODIFIER`, lève `LookupError` si parcelle introuvable et `ValueError` si paramètre inconnu
- Ajoute les constantes statiques `_HELP_PARCELLE`, `_HELP_SEMIS`, `_HELP_GODET`, `_HELP_RECOLTE`, `_HELP_STOCK`, `_HELP_STATS`, `_HELP_CONTEXTUEL` dans `bot.py`
- Transmet `exposition` et `superficie_m2` depuis le handler `parcelle_confirm` lors de la confirmation de création

## [v2.12.0] — 2026-04-11

### 🚀 Nouveautés
- Ajoute `/plan` : vue globale du potager par parcelle avec cultures actives, âge J+ de chaque culture et alertes ⚠️ récolte imminente (végétatif ≥ 45 j, reproducteur ≥ 90 j) (US_Plan_occupation_parcelles #18)
- Ajoute `/plan [nom]` : vue détaillée d'une parcelle spécifique, insensible à la casse
- Ajoute `/parcelle ajouter [nom]` : création de parcelle avec refus sur doublon exact et demande de confirmation si variante proche (distance Levenshtein ≤ 2)
- Signale les parcelles libres avec 🟢 et regroupe les cultures sans parcelle dans "Non localisé"
- Reconnaît les commandes vocales "plan du potager" et "plan parcelle [nom]" et les route vers `/plan`

### 🔧 Améliorations techniques
- Ajoute `utils/parcelles.py` : `normalize_parcelle_name`, `levenshtein_distance`, `find_doublon`, `create_parcelle`, `get_all_parcelles`, `calcul_occupation_parcelles`
- Ajoute `cmd_plan`, `cmd_parcelle`, `_extract_plan_parcelle()` et les handlers `/plan` et `/parcelle` dans `bot.py`

### 💾 Base de données
- Ajoute le modèle SQLAlchemy `Parcelle` dans `database/models.py` (colonne `nom_normalise` UNIQUE)
- Ajoute `migration_v10.sql` : création de la table `parcelles` avec prépopulation depuis `evenements`

## [v2.11.0] — 2026-04-09

### 🚀 Nouveautés
- Ajoute `/stats [culture]` : affiche le détail par variété avec nombre de plants, quantité récoltée et période (date plantation → dernière récolte ou "en cours") (US_Stats_detail_par_variete)
- Ajoute un hint en pied de `/stats` : "Pour le détail d'une variété : /stats [culture]"
- Groupe les plants sans variété renseignée sous "Variété non précisée"
- Retourne "Aucune donnée pour [culture]" si la culture est inconnue
- Reconnaît la commande vocale "stats [culture]" et la redirige vers `/stats [culture]`

### 🔧 Améliorations techniques
- Ajoute `calcul_stock_par_variete(db, culture)` et `format_variete_bloc_telegram(v)` dans `utils/stock.py`
- Ajoute `_extract_stats_culture(texte)` dans `bot.py` pour l'extraction de la culture depuis une commande vocale (CA8)
- Modifie `cmd_stats` pour brancher sur le détail variété quand un argument culture est fourni
- Insensible à la casse pour le nom de la culture

## [v2.10.0] — 2026-04-08

### 🚀 Nouveautés
- Ajoute l'enregistrement d'une mise en godet avec calcul automatique du taux de réussite de germination (nb_plants_godets / nb_graines_semees) (US_Enregistrer_mise_en_godet)

### 🔧 Améliorations techniques
- Ajoute `mise_en_godet` dans `ACTION_MAP` avec ses synonymes vocaux et dans le prompt d'intention du bot
- Ajoute les champs `nb_graines_semees` et `nb_plants_godets` dans le schéma JSON Groq et l'exemple Gherkin du `PARSE_PROMPT`
- Spécialise `_build_recap` pour afficher le taux de réussite uniquement pour `mise_en_godet`
- Isole `mise_en_godet` du domaine stock actif : ne modifie pas `calcul_stock_cultures`

### 💾 Base de données
- Ajoute `migration_v7.sql` : colonnes `nb_graines_semees INTEGER` et `nb_plants_godets INTEGER` (nullable) sur la table `evenements`
- Ajoute les colonnes `nb_graines_semees` et `nb_plants_godets` dans le modèle SQLAlchemy `Evenement`

## [v2.9.0] — 2026-04-07

### 🚀 Nouveautés
- Ajoute la commande `/help` : aide en ligne synthétique en français, optimisée mobile, message unique ≤ 4096 chars (commandes, actions, mots-clés navigation, exemples de questions), sans appel Groq (US_Commande_help_aide_mobile)
- Ajoute la mention `📖 Tapez /help pour l'aide en ligne.` dans le message de bienvenue `/start`

## [v2.8.2] — 2026-04-03

### 🐛 Corrections
- Corrige `calcul_semis` dans `utils/stock.py` : l'agrégation des récoltes écrasait les entrées précédentes au lieu de les accumuler quand une même culture avait des récoltes en unités différentes (ex : 1.0 kg puis 500 g pour les carottes) — la carotte passe de "500.0 g récoltés (1 fois)" à "1.5 kg récoltés (2 fois)"

### 🔧 Améliorations techniques
- Normalise les unités de récolte en grammes lors de l'addition (kg→g, g→g), puis restitue dans l'unité la plus lisible (kg si ≥ 1000 g, sinon g)

## [v2.8.1] — 2026-04-03

### 🐛 Corrections
- Corrige `calcul_semis` dans `utils/stock.py` : le GROUP BY sur `(culture, unite)` causait un sous-comptage des semis quand une même culture avait des enregistrements avec des unités différentes (ex : NULL et 'graines') — radis passait de 1 à 3 semis (valeur réelle)

## [v2.8.0] — 2026-04-03

### 🚀 Nouveautés
- Ajoute la synthèse des semis dans les statistiques Telegram, classés par type de récolte (végétatif / reproducteur) avec les récoltes déjà réalisées (US_Afficher_synthese_semis_dans_stats)
- Supprime le compteur "Total : X événements" de l'en-tête des statistiques

### 🔧 Améliorations techniques
- Ajoute la fonction `calcul_semis` dans `utils/stock.py` pour agréger les semis et les croiser avec les récoltes existantes

## [v2.7.0] — 2026-04-03

### 🚀 Nouveautés
- Ajoute `update_dev.ps1` : script PowerShell de mise à jour automatique de l'environnement de développement (pip + migrations SQL)
- Ajoute `.githooks/post-merge` : hook git qui déclenche `update_dev.ps1` automatiquement après chaque `git pull` si `requirements.txt` ou les migrations changent

### 🐛 Corrections
- Corrige `migration_v6.sql` : suppression du double `ON CONFLICT` invalide en PostgreSQL qui empêchait l'insertion des 46 nouvelles cultures
- Corrige `update_dev.ps1` : ajout de `-v ON_ERROR_STOP=1` sur psql pour détecter les vraies erreurs SQL (les NOTICE ne bloquent plus le script)

### 🔧 Améliorations techniques
- Ajoute `.migrations_applied` au `.gitignore` (fichier de suivi local des migrations déjà jouées en dev)

## [v2.5.0] — 2026-04-03

### 🚀 Nouveautés
- Ajoute un bouton « Corriger » dans le menu Telegram pour accéder directement au mode modification (US-011)

## [v2.6.0] — 2026-04-03

### 🗃️ Données
- Ajout de la migration_v6.sql : insertion de 46 nouvelles cultures Île-de-France (ids 100-145) dans la table culture_config. Les cultures existantes (1-90) ne sont pas modifiées. Script idempotent (ON CONFLICT DO NOTHING).

# Patch — Déploiement automatisé Scaleway (US-005)

**Version :** v2.4.0 — 2 avril 2026  
**Fichiers créés :** `deploy.sh`, `.github/workflows/deploy.yml`, `infra/potager.service`, `tests/test_us005_deploiement.py`  
**Migrations SQL :** aucune

---

## Contexte

Mise en place du pipeline de déploiement automatisé sur serveur Scaleway (Ubuntu 22.04).
Deux modes disponibles : script manuel `deploy.sh` et workflow GitHub Actions déclenché sur push `main`.

---

## Évolutions réalisées

- `deploy.sh` : script SSH en 5 étapes (sync git → pip install → migrations SQL → restart systemd → smoke test)
- `.github/workflows/deploy.yml` : workflow GitHub Actions équivalent, déclenché sur push main ou manuellement
- `infra/potager.service` : unit systemd avec `Restart=on-failure`, `EnvironmentFile=.env.prod`, `APP_ENV=prod`
- Aucun secret transmis par les scripts — tous injectés via `.env.prod` côté serveur ou GitHub Secrets

## Tests

```
tests/test_us005_deploiement.py — 18/18 PASSED
```

---

# Patch — Gestion des environnements dev/prod (US-004)

**Version :** v2.3.0 — 2 avril 2026  
**Fichiers modifiés :** `config.py`, `.gitignore`, `tests/conftest.py`  
**Fichiers créés :** `.env.example`, `tests/test_us004_config_env.py`  
**Migrations SQL :** aucune

---

## Contexte

Séparation des environnements dev (local) et production (Scaleway) avec fichiers `.env` dédiés.
Correction de la vulnérabilité OWASP A02 : suppression des tokens Telegram et credentials PostgreSQL hardcodés.

---

## Évolutions réalisées

- `config.py` : charge `.env.dev` ou `.env.prod` selon la variable `APP_ENV` — plus aucune valeur hardcodée
- `.gitignore` : ajout de `.env.dev` et `.env.prod` — suppression de `config.py` (désormais versionnable)
- `.env.example` : template public avec placeholders pour onboarding nouveaux développeurs
- `tests/conftest.py` : initialisation des vars d'environnement de test avant les imports

## Tests

```
tests/test_us004_config_env.py — 8/8 PASSED
```

---

# Patch — Classification agronomique des cultures (végétatif vs reproducteur)

**Version :** v2.2.0 — 31 mars 2026  
**Fichiers modifiés :** `database/models.py`, `migrations/migration_v5.sql`, `main.py`, `tests/test_api.py`, `llm/rag.py`  
**Migrations SQL :** migration_v5.sql

---

## Contexte

Ajout de la classification agronomique fondamentale distinguant les cultures selon leur organe récolté (végétatif vs reproducteur) pour des calculs de rendement scientifiquement corrects.

---

## Évolutions réalisées

### 1. Modèle de données agronomique (`database/models.py`)
- Ajout colonne `type_organe_recolte` à la table `evenements` (valeurs : végétatif | reproducteur | null)
- Création modèle `CultureConfig` pour classifier les cultures classiques

### 2. Migration de base de données (`migrations/migration_v5.sql`)
- Ajout colonne `type_organe_recolte` à `evenements`
- Création table `culture_config` avec index de performance
- Seed de 20+ cultures avec descriptions agronomiques (salade→végétatif, tomate→reproducteur)
- Rétropopulation automatique des événements existants

### 3. API REST étendue (`main.py`)
- Nouvel endpoint `GET /cultures` retournant liste des cultures avec type et description
- Héritage automatique du type lors du parsing vocal (`POST /parse`)

### 4. Module RAG (`llm/rag.py`)
- Création du module pour l'indexation RAG (Retrieval-Augmented Generation)

### 5. Tests API complets (`tests/test_api.py`)
- Tests pour l'endpoint `/cultures`
- Tests d'héritage automatique du type lors du parsing
- Tests de gestion des cultures inconnues

---

## Impact

- **Classification agronomique** : Base de données prête pour calculs de rendement différenciés
- **API enrichie** : Exposition des cultures configurées pour interfaces tierces
- **Données rétropopulées** : Événements historiques automatiquement classés
- **Fondation US suivantes** : Prêt pour adaptation du calcul de stock et affichage différencié
- **Tests complets** : Couverture des nouveaux endpoints et logique métier

---

# Patch — Correction calcul stock réel avec récoltes

**Version :** v2.1.0 — 30 mars 2026  
**Fichiers modifiés :** `bot.py`, `llm/groq_client.py`, `tests/test_bot.py`, `tests/conftest.py`  
**Migrations SQL :** aucune

---

## Contexte

Correction d'un bug où le calcul du stock réel ne prenait pas en compte les récoltes, affichant un stock incorrectement élevé.

---

## Évolutions réalisées

### 1. Mise à jour de `llm/groq_client.py`
- Ajout des récoltes dans la `REGLE CALCUL STOCK REEL` du `QUERY_PROMPT`.
- Nouveau calcul : stock réel = plantations - pertes - récoltes.
- Exemple d'affichage explicite incluant les récoltes.

### 2. Modification de `bot.py`
- Calcul des `recoltes_dict` dans `cmd_stats()`.
- Mise à jour du calcul du stock réel pour soustraire les récoltes.
- Affichage enrichi : "(planté X, perdu Y, récolté Z)" selon les valeurs présentes.

### 3. Amélioration des tests unitaires
- Ajout de test pour le cas plantations + pertes + récoltes.
- Refactorisation des tests existants pour utiliser les fixtures pytest.
- Nettoyage automatique de la base de données entre tests.

---

## Impact

- **Calcul correct** : Stock réel prend désormais en compte les récoltes.
- **Affichage précis** : /stats montre le détail complet (planté, perdu, récolté).
- **Fiabilité accrue** : Tests couvrent tous les scénarios de calcul de stock.
- **Maintenance facilitée** : Fixtures de test améliorées pour éviter les interférences.

---

# Patch — Fonctionnalité perte de plants

**Version :** feature — 30 mars 2026  
**Fichiers modifiés :** `utils/actions.py`, `llm/groq_client.py`, `bot.py`, `tests/` (nouveau)  
**Migrations SQL :** aucune

---

## Contexte

Ajout de la fonctionnalité de signalement des pertes de plants (gel, maladie, ravageur) avec recalcul automatique du stock réel.

---

## Évolutions réalisées

### 1. Extension de `utils/actions.py`
- Ajout de l'action canonique `perte` dans `ACTION_MAP` avec synonymes (perdu, mort, arraché, crevé...).
- Mise à jour des variants pour les actions existantes (paillé, fertilisé, etc.).

### 2. Mise à jour de `llm/groq_client.py`
- Ajout de `perte` dans `INTENT_PROMPT`, `PARSE_PROMPT` et `QUERY_PROMPT`.
- Ajout d'exemple de parsing pour "J'ai perdu 3 plants de tomates à cause du gel".
- Règle de calcul stock réel dans `QUERY_PROMPT` (plantations - pertes).

### 3. Modification de `bot.py`
- Ajout de mots-clés pour `perte` dans `ACTION_KEYWORDS`.
- Ajout de `perte` dans `_CLASSIFY_PROMPT`.
- Modification de `cmd_stats()` pour calculer stock réel avec détail (planté X, perdu Y).

### 4. Création de tests unitaires
- `tests/test_actions.py` : Tests pour `normalize_action` et `ACTION_MAP`.
- `tests/test_groq.py` : Tests pour parsing et questions (mocks).
- `tests/test_bot.py` : Tests pour `cmd_stats` avec DB de test.
- `requirements.txt` : Ajout de `pytest` et `pytest-asyncio`.

---

## Impact

- **Nouveau type d'action** : "perte" pour signaler les pertes de plants.
- **Calcul automatique** : Stock réel = plantations totales - pertes totales.
- **Affichage enrichi** : /stats montre "X plants (planté Y, perdu Z)".
- **Questions analytiques** : Support des questions sur stock restant.
- **Tests** : Couverture pour validation des fonctionnalités.

---

# Patch — Optimisation orchestrateur IA pour questions analytiques

**Version :** feature — 26 mars 2026  
**Fichiers modifiés :** `utils/ia_orchestrator.py` (nouveau), `bot.py`, `BACKLOG.md` (nouveau)  
**Migrations SQL :** aucune

---

## Contexte

Les questions analytiques (`/ask`) envoyaient l'intégralité de l'historique potager en JSON à Groq, causant :
- Consommation excessive de tokens.
- Risques de dépassement de quota.
- Bruit contextuel pour le LLM.
- Manque de traçabilité du trafic sortant.

---

## Évolutions réalisées

### 1. Création de `utils/ia_orchestrator.py`
- **Fonction `extract_question_intent`** : Extraction d'intention (action, culture, filtres temporels) à partir de la question.
- **Fonction `fetch_filtered_events`** : Requête DB ciblée avec filtres SQL (au lieu de `SELECT *`).
- **Fonction `build_reduced_context`** : Construction d'un JSON limité à 50 événements max.
- **Fonction `build_question_context`** : Orchestrateur complet question → contexte réduit.

### 2. Modification de `bot.py`
- Remplacement du dump complet par `build_question_context(db, question)`.
- Ajout de logs pour mesurer le trafic sortant (taille JSON, tokens estimés ~4 chars/token).
- Gestion des cas sans données pertinentes.

### 3. Logs professionnels ajoutés
- **Orchestrateur** : Intention extraite, événements récupérés, taille contexte.
- **LLM** : Taille appel et réponse pour suivi quota.
- Format structuré avec emojis pour filtrage (ex. `grep "ORCHESTRATOR"`).

### 4. Création de `BACKLOG.md`
- Liste des tâches prioritaires pour tests unitaires, sécurité, et améliorations futures.

---

## Impact

- **Réduction tokens** : Contexte limité vs historique complet (ex. 50 événements au lieu de 1000+).
- **Traçabilité** : Logs détaillés pour mesurer correspondance quota Groq.
- **Performance** : Requêtes DB plus rapides et ciblées.
- **Sécurité** : Moins de données sensibles transmises.

---

## Tests recommandés

- Poser des questions variées (`/ask "Combien de tomates ?"`, `/ask "Dernier arrosage courgettes ?"`, `/ask "Fenouils cette année ?"`).
- Vérifier les logs pour volume transmis.
- Mesurer tokens consommés via dashboard Groq.

---

# Patch — Fix garde sauvegarde (bug latent)

**Version :** hotfix — 25 mars 2026  
**Fichiers modifiés :** `app/bot.py`  
**Migrations SQL :** aucune

---

## Problème

Toute phrase envoyée au bot — même dénuée de sens potager — était
**enregistrée en base** dès que Groq renvoyait une valeur dans le champ
`commentaire`.

Exemples observés en test :
- `"météo du jour"` → id=139, action=None, culture=None
- `"acheter du jour"` → id=140, action=None, culture=None
- `"acheter lapin ce jour"` → id=141, action=None, culture=None
- `"je veux acheter un lapin aujourd'hui et pour toujours"` → id=142

### Cause racine

La condition de garde dans `_parse_and_save()` et `_parse_multi()`
incluait `commentaire` dans la liste des champs "utiles" :

```python
# AVANT — bugué
useful_fields = [first.get(k) for k in (
    "action","culture","quantite","traitement",
    "duree_minutes","parcelle","rang","variete","commentaire"  # ← commentaire inclus
)]
if all(v is None for v in useful_fields):
    # bloquer
```

Groq place systématiquement le résidu textuel dans `commentaire`,
donc `all(v is None)` n'était **jamais `True`**.
La garde ne bloquait rien.

Ce bug était présent depuis l'origine — les tests du 25 mars l'ont
mis en évidence pour la première fois avec des phrases hors contexte.

---

## Fix

Remplacement de la condition dans les deux fonctions par un test
**positif** : exiger qu'au moins `action` **ou** `culture` **ou**
`quantite` soit présent.

### `_parse_multi()` — ligne ~611

```python
# AVANT
useful = [first.get(k) for k in ("action","culture","quantite","traitement","duree_minutes","parcelle","rang","variete","commentaire")]
if all(v is None for v in useful):
    log.warning(f"  [{i}] JSON vide ignoré pour : {ligne}")
    continue

# APRÈS
if not (first.get("action") or first.get("culture") or first.get("quantite")):
    log.warning(f"  [{i}] JSON sans action ni culture — ignoré : {ligne}")
    continue
```

### `_parse_and_save()` — ligne ~696

```python
# AVANT
useful_fields = [first.get(k) for k in (
    "action","culture","quantite","traitement",
    "duree_minutes","parcelle","rang","variete","commentaire"
)]
if all(v is None for v in useful_fields):
    log.warning("⚠️  JSON VIDE       : phrase non reconnue comme action, pas de sauvegarde")

# APRÈS
if not (first.get("action") or first.get("culture") or first.get("quantite")):
    log.warning("⚠️  JSON SANS ACTION NI CULTURE : phrase non reconnue, pas de sauvegarde")
```

---

## Nettoyage base de données

Les enregistrements parasites créés lors des tests sont à supprimer
manuellement :

```sql
-- Supprimer les entrées parasites du 25 mars
DELETE FROM evenements WHERE id IN (139, 140, 141, 142);

-- Vérification générale : détecter d'éventuels autres parasites
SELECT id, date::date, commentaire, texte_original
FROM evenements
WHERE type_action IS NULL AND culture IS NULL
ORDER BY id DESC;

-- Nettoyage global si nécessaire (à adapter selon résultats)
-- DELETE FROM evenements WHERE type_action IS NULL AND culture IS NULL;
```
```

---

## Comportement attendu après fix

| Phrase envoyée | Avant | Après |
|----------------|-------|-------|
| `"météo du jour"` | Sauvegardé en base (parasite) | Message d'incompréhension, pas de sauvegarde |
| `"acheter un lapin"` | Sauvegardé en base (parasite) | Message d'incompréhension, pas de sauvegarde |
| `"récolté 2 kg de tomates"` | Sauvegardé ✅ | Sauvegardé ✅ |
| `"arrosage carré sud 20 min"` | Sauvegardé ✅ | Sauvegardé ✅ |

Log console attendu pour une phrase rejetée :
```
HH:MM:SS │ WARNING │ ⚠️  JSON SANS ACTION NI CULTURE : phrase non reconnue, pas de sauvegarde
```

---

## Backlog connexe

Ce patch ne couvre pas l'asymétrie suivante, à traiter séparément :
- Les messages **texte** ne passent pas par `classify_intent()`, contrairement
  aux messages **vocaux**. "Météo du jour" en texte ne bénéficie pas du
  routage intelligent vers `INTERROGER`. À corriger dans une prochaine itération.

---

*Assistant Potager — hotfix 25 mars 2026*
