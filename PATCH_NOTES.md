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
