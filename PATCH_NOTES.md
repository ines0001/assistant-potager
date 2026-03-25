# Patch — Météo quotidienne Open-Meteo

## Fichiers modifiés / ajoutés

| Fichier | Nature |
|---------|--------|
| `app/utils/meteo.py` | **NOUVEAU** — module complet météo |
| `app/bot.py` | + import, + `cmd_meteo`, + `job_meteo_quotidienne`, + `main()` |
| `app/requirements.txt` | + `requests`, + `pytz`, `python-telegram-bot[job-queue]` |

---

## Déploiement

### 1. Copier les fichiers

```
assistant-potager/app/utils/meteo.py    ← nouveau fichier
assistant-potager/app/bot.py            ← remplacer
assistant-potager/app/requirements.txt  ← remplacer
```

### 2. Installer les nouvelles dépendances

```bash
pip install requests pytz
pip install "python-telegram-bot[job-queue]==21.6"
```

⚠️ Le `[job-queue]` est obligatoire pour que `app.job_queue` fonctionne.
Sans ça, le bot démarre mais le job silencieux à 5h ne se déclenchera jamais.

### 3. Aucune migration SQL nécessaire

Les observations météo utilisent la table `evenements` existante avec
`type_action='observation'` et `texte_original='[AUTO-METEO]'`.

---

## Utilisation

| Commande | Effet |
|----------|-------|
| `/meteo` | Déclenche manuellement la météo du jour + enregistrement en base |
| Job 05h00 | Automatique chaque matin — silencieux, pas de message Telegram |

### Tester immédiatement après déploiement

```
/meteo
```

Doit répondre :
```
🌤️ Météo enregistrée !
☀️ Ciel dégagé · Min 8°C / Max 18°C · Matin 12°C / AM 17°C · Pluie 0mm (5%) · Vent 14km/h · ☀ 07:12→20:34 · ✅ Conditions idéales
```

Puis vérifier en base :
```sql
SELECT id, date, type_action, commentaire, texte_original
FROM evenements
WHERE texte_original = '[AUTO-METEO]'
ORDER BY date DESC
LIMIT 5;
```

---

## Ce qui est enregistré en base

```sql
type_action    = 'observation'
texte_original = '[AUTO-METEO]'
commentaire    = '☀️ Ensoleillé · Min 8°C / Max 22°C · Matin 12°C / AM 21°C · Pluie 0mm (5%) · Vent 18km/h · ☀ 07:12→20:34 · ✅ Conditions idéales'
date           = 2026-03-25 00:00:00
culture        = NULL
```

### Anti-doublon intégré

Si tu lances `/meteo` deux fois dans la même journée, ou si le job
se redéclenche par erreur, **aucun doublon ne sera créé** — la fonction
vérifie si une observation `[AUTO-METEO]` existe déjà pour aujourd'hui.

---

## Données Open-Meteo récupérées

| Donnée | Source API |
|--------|-----------|
| Température min/max | `daily.temperature_2m_min/max` |
| Température 8h / 14h | `hourly.temperature_2m` |
| Précipitations totales | `daily.precipitation_sum` |
| Probabilité de pluie max | `daily.precipitation_probability_max` |
| Vent max | `daily.windspeed_10m_max` |
| Code météo WMO | `daily.weathercode` |
| Lever/coucher soleil | `daily.sunrise/sunset` |

**Coordonnées configurées :**
Latitude 48.96082 / Longitude 2.20382 (Cergy / Val-d'Oise)

---

## Conseils potager générés automatiquement (logique locale)

| Condition | Conseil affiché |
|-----------|----------------|
| Temp matin ≤ 0°C | ⚠️ Risque de gel — protéger les plantations |
| Temp PM ≥ 35°C | 🌡️ Canicule — arrosage en soirée indispensable |
| Orage prévu (WMO 95/96/99) | ⛈️ Pas d'arrosage ni de traitement |
| Précip ≥ 10mm | 🌧️ Pluie abondante — arrosage inutile |
| Pas de pluie + temp ≥ 22°C | 💧 Penser à arroser en soirée |
| Vent ≥ 50 km/h | 💨 Vérifier tuteurs et protections |
| Brouillard | 🌫️ Risque de maladies fongiques |
| Beau temps + vent < 20km/h | ✅ Conditions idéales pour traitements |

---

## BotFather — ajouter la commande (optionnel)

```
meteo - Météo du jour et conseil potager
```
