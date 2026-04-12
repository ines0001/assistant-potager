**Titre :** Variété absente du critère de recherche et de l'affichage dans le mode correction

**Type :** Bug

**Priorité :** Haute

**Story :**
En tant que jardinier
Je veux pouvoir retrouver un événement en précisant sa variété (ex : "modifier plantation tomate ronde")
Et voir la variété affichée dans la liste de sélection
Afin de distinguer sans ambiguïté deux enregistrements de la même culture quand ils diffèrent par la variété

**Contexte et trace observée :**
💬 MESSAGE TEXTE : modifier plantation tomate ronde
🔎 CRITÈRES RECHERCHE : {'action': 'plantation', 'culture': 'tomate', 'date_debut': None, 'date_fin': None, 'parcelle': None}
🔎 RÉSULTATS SQL : 2 trouvé(s)

Plusieurs événements trouvés, lequel voulez-vous modifier ?

#247 07/04 — plantation tomate 10.0plants
#162 12/02 — plantation tomate 30.0plants [sud]
La variété "ronde" n'a pas été transmise au filtre SQL, et les lignes affichées ne l'incluent pas.

**Cause identifiée (deux bugs distincts) :**

**Bug 1 — `_find_candidates` dans `bot.py` : variété absente du schéma Groq et du filtre SQL**
Le prompt envoyé à Groq ne demande que `{action, culture, date_debut, date_fin, parcelle}`.
Le champ `variete` n'est ni extrait ni utilisé pour filtrer `Evenement.variete` en SQL.

**Bug 2 — `_fmt_event` dans `bot.py` : variété absente du formatage**
```python
def _fmt_event(e) -> str:
    cult = f" {e.culture}" if e.culture else ""
    # ← e.variete absent → "tomate" au lieu de "tomate (ronde)"
Critères d'acceptance :

 CA1 : Quand l'utilisateur tape "modifier plantation tomate ronde", le log CRITÈRES RECHERCHE contient 'variete': 'ronde'
 CA2 : La requête SQL filtre sur Evenement.variete.ilike("%ronde%") si la variété est renseignée dans les critères
 CA3 : Le filtre variété est optionnel (null si non mentionné) — la recherche sans variété doit continuer à fonctionner
 CA4 : _fmt_event affiche la variété entre parenthèses quand elle est non nulle : #247 07/04 — plantation tomate (ronde) 10.0plants
 CA5 : La liste de sélection multi-résultats affiche la variété, permettant de distinguer deux enregistrements d'une même culture  
 bot.py — fonction _find_candidates : prompt Groq + filtre SQL
bot.py — fonction _fmt_event : mise en forme d'un événement
Migration BDD requise : non

Estimation : 1 point

Scénario Gherkin :

Feature: Recherche par variété dans le mode correction

  Scenario: Variété incluse dans les critères de recherche
    Given le jardinier est en mode correction
    When il tape "modifier plantation tomate ronde"
    Then les critères extraits contiennent action="plantation", culture="tomate", variete="ronde"
    And la requête SQL filtre sur variete ILIKE "%ronde%"
    And seuls les événements de la variété "ronde" sont retournés

  Scenario: Variété affichée dans la liste multi-résultats
    Given 2 événements de type "plantation tomate" existent en base avec des variétés différentes
    When le bot présente la liste de sélection
    Then chaque ligne affiche la variété entre parenthèses
    And l'utilisateur peut distinguer les deux enregistrements

  Scenario: Recherche sans variété (rétrocompatibilité)
    When le jardinier tape "modifier plantation tomate"
    Then les critères extraits contiennent variete=null
    And la requête SQL ne filtre pas sur la variété
    And tous les événements de plantation tomate sont retournés

  Scenario: Événement sans variété affiché sans parenthèses
    Given un événement tomate sans variété renseignée
    When _fmt_event est appelé
    Then la ligne affichée est "#X DD/MM — plantation tomate 10.0plants"
    And aucun "()" vide n'apparaît

    Labels GitHub : bug, correction, sprint-courant, bot, ux