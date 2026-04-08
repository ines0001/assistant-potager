"""
groq_client.py — LLM Groq pour parsing et questions
----------------------------------------------------
Corrections v2.1 :
  - Date réelle extraite (hier, avant-hier, lundi dernier...)
  - Détection phrases multiples → liste de JSONs
"""
import json
import re
from datetime import date, timedelta
from groq import Groq
from config import GROQ_API_KEY, GROQ_MODEL

_client = Groq(api_key=GROQ_API_KEY)

# ── Date du jour injectée dans le prompt ──────────────────────────────────────
def _today_context() -> str:
    today      = date.today()
    yesterday  = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    return (
        f"Aujourd'hui nous sommes le {today.strftime('%A %d %B %Y')} "
        f"({today.isoformat()}). "
        f"Hier = {yesterday.isoformat()}. "
        f"Avant-hier = {day_before.isoformat()}."
    )


INTENT_PROMPT = """Tu es un assistant assistant potager spécialisé dans l'analyse de questions en langage naturel.
Donne uniquement du JSON sans texte additionnel, sans guillemets, avec ces champs:
{
  "action": "semis|plantation|arrosage|recolte|repiquage|traitement|desherbage|taille|paillage|observation|perte|recolte_graines|null",
  "culture": string|null,  # nom du légume au singulier minuscule, sinon null
  "date_from": string|null  # date ISO ou null
}

Exemples :
"quels légumes ai-je le plus récoltés en kg ?" -> {"action":"recolte","culture":null,"date_from":null}
"arrosage courgettes cette semaine" -> {"action":"arrosage","culture":"courgette","date_from":"2026-03-19"}
"quand ai-je semé des carottes" -> {"action":"semis","culture":"carotte","date_from":null}
""" 


def extract_intent(question: str) -> dict:
    chat = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": INTENT_PROMPT},
            {"role": "user", "content": question}
        ],
        temperature=0.0,
        max_tokens=128,
        stream=False
    )

    raw = chat.choices[0].message.content.strip()
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    try:
        parsed = json.loads(raw)
    except Exception as e:
        # fallback conservatif
        return {"action": None, "culture": None, "date_from": None}

    # normalisation des clés
    return {
        "action": parsed.get("action"),
        "culture": parsed.get("culture"),
        "date_from": parsed.get("date_from"),
    }

# ─────────────────────────────────────────────────────────────────────────────
# PROMPT PARSING — retourne UN ou PLUSIEURS JSONs selon la phrase
# ─────────────────────────────────────────────────────────────────────────────
PARSE_PROMPT = """Tu es un extracteur de données pour un potager maraîcher français.
{date_context}

Analyse la phrase et retourne UNIQUEMENT un JSON avec les informations extraites.
Si une information n'est pas mentionnée, mets null. Ne jamais inventer.

Champs à extraire :
{{
  "action"           : string,   // recolte | recolte_finale | semis | repiquage | arrosage | fertilisation | traitement | desherbage | taille | paillage | observation | plantation | tuteurage | perte | mise_en_godet | recolte_graines
  "culture"          : string,   // légume au singulier minuscule ("tomates" → "tomate")
  "variete"          : string,   // variété ou couleur ("rouge", "nantaise"...)
  "quantite"         : number,   // quantité numérique (PAR RANG si rang mentionné)
  "unite"            : string,   // kg | g | l | plants | graines
  "parcelle"         : string,   // localisation (nord, sud, carré sud, serre...)
  "rang"             : number,   // NOMBRE de rangs (pas un identifiant). "3 rangs" → 3
  "duree_minutes"    : number,   // durée en minutes
  "traitement"       : string,   // produit utilisé (purin d ortie, compost...)
  "date"             : string,   // date ISO si mentionnée : "hier"→{yesterday}, "aujourd'hui"→{today_iso}, "avant-hier"→{day_before}
  "commentaire"      : string,   // toute autre observation utile
  "nb_graines_semees": number,   // pour mise_en_godet : nombre de graines semees initialement
  "nb_plants_godets" : number    // pour mise_en_godet : nombre de plants obtenus en godet
  "origine_graines_id": number   // pour semis : id de la recolte_graines source si mentionné (ex: "graines id 42", "mes graines de l'an dernier" → null si inconnu)
}}

Exemples :
"J'ai paillé les tomates hier"
→ {{"action":"paillage","culture":"tomate","date":"{yesterday}","quantite":null,"unite":null,"parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"variete":null,"commentaire":null}}

"récolté 2 kg de tomates hier parcelle nord"
→ {{"action":"recolte","culture":"tomate","quantite":2,"unite":"kg","date":"{yesterday}","parcelle":"nord","rang":null,"duree_minutes":null,"traitement":null,"variete":null,"commentaire":null}}

"arrosage carré sud pendant 20 minutes"
→ {{"action":"arrosage","culture":null,"quantite":null,"unite":null,"date":null,"parcelle":"carré sud","rang":null,"duree_minutes":20,"traitement":null,"variete":null,"commentaire":null}}

"planter 10 choux-fleurs sur 3 rangs parcelle nord"
→ {{"action":"plantation","culture":"chou-fleur","quantite":10,"unite":"plants","date":null,"parcelle":"nord","rang":3,"duree_minutes":null,"traitement":null,"variete":null,"commentaire":null}}

"traitement purin d'ortie sur les courgettes hier"
→ {{"action":"traitement","culture":"courgette","quantite":null,"unite":null,"date":"{yesterday}","parcelle":null,"rang":null,"duree_minutes":null,"traitement":"purin d ortie","variete":null,"commentaire":null}}

"semé des carottes nantaises parcelle est"
→ {{"action":"semis","culture":"carotte","quantite":null,"unite":null,"date":null,"parcelle":"est","rang":null,"duree_minutes":null,"traitement":null,"variete":"nantaise","commentaire":null}}

"J'ai perdu 3 plants de tomates à cause du gel"
→ {{"action":"perte","culture":"tomate","quantite":3,"unite":"plants","date":null,"parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"variete":null,"commentaire":"gel"}}

"J'ai planté 15 oignons blancs et 10 radis hier"
→ [{{"action":"plantation","culture":"oignon","variete":"blanc","quantite":15,"unite":"plants","date":"{yesterday}","parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"commentaire":null}},{{"action":"plantation","culture":"radis","variete":null,"quantite":10,"unite":"plants","date":"{yesterday}","parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"commentaire":null}}]

"Mis en godet 24 tomates cerise sur 30 graines semées"
→ {{"action":"mise_en_godet","culture":"tomate","variete":"cerise","quantite":null,"unite":null,"date":null,"parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"variete":"cerise","commentaire":null,"nb_graines_semees":30,"nb_plants_godets":24,"origine_graines_id":null}}

"Récolté graines tomates cœur de bœuf 15 g"
→ {{"action":"recolte_graines","culture":"tomate","variete":"coeur de boeuf","quantite":15,"unite":"g","date":null,"parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"commentaire":null,"nb_graines_semees":null,"nb_plants_godets":null,"origine_graines_id":null}}

"Semis tomates coeur de boeuf avec graines id 42"
→ {{"action":"semis","culture":"tomate","variete":"coeur de boeuf","quantite":null,"unite":null,"date":null,"parcelle":null,"rang":null,"duree_minutes":null,"traitement":null,"commentaire":null,"nb_graines_semees":null,"nb_plants_godets":null,"origine_graines_id":42}}

"Récolte finale tomates cerise parcelle nord 1.2 kg fin de culture"
→ {{"action":"recolte_finale","culture":"tomate cerise","variete":null,"quantite":1.2,"unite":"kg","date":null,"parcelle":"nord","rang":null,"duree_minutes":null,"traitement":null,"commentaire":"fin de culture","nb_graines_semees":null,"nb_plants_godets":null,"origine_graines_id":null}}

Retourne UNIQUEMENT le JSON brut, sans texte ni backticks.
Si plusieurs cultures dans la même phrase → tableau de JSONs.
"""

def parse_commande(texte: str) -> list[dict]:
    """
    Parse une commande vocale.
    Retourne TOUJOURS une liste de dicts (1 élément ou plusieurs).
    """
    today      = date.today()
    yesterday  = today - timedelta(days=1)
    day_before = today - timedelta(days=2)
    prompt = PARSE_PROMPT.format(
        date_context = _today_context(),
        today_iso    = today.isoformat(),
        yesterday    = yesterday.isoformat(),
        day_before   = day_before.isoformat(),
    )

    chat = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user",   "content": texte}
        ],
        temperature=0.0,
        max_tokens=1024,
        stream=False
    )
    raw = chat.choices[0].message.content.strip()

    # Nettoyage backticks éventuels
    if raw.startswith("```"):
        lines = raw.split("\n")
        raw = "\n".join(lines[1:-1]) if len(lines) > 2 else raw

    parsed = json.loads(raw.strip())

    # Normaliser : toujours retourner une liste
    if isinstance(parsed, dict):
        return [parsed]
    elif isinstance(parsed, list):
        return parsed
    else:
        return [parsed]


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT ANALYTIQUE
# ─────────────────────────────────────────────────────────────────────────────
QUERY_PROMPT = """Tu es l'assistant potager d'un jardinier. Aujourd'hui : {today_iso}.

REGLE ABSOLUE - REPONSE DIRECTE UNIQUEMENT :
Donne SEULEMENT le resultat final. Pas de raisonnement, pas de calculs intermediaires,
pas d'introduction, pas de conclusion. Une ou deux phrases maximum.

EXEMPLES DE BONNES REPONSES :
Q: "Combien de plants de tomates en tout ?"
R: "42 plants de tomates au total (30 coeur de boeuf + 12 classiques)."

Q: "Quel legume a le plus produit en kg ?"
R: "La tomate avec 15 kg, suivie de la courgette avec 8 kg."

Q: "Quand ai-je arrose les courgettes pour la derniere fois ?"
R: "Dernier arrosage courgettes : 9 mars 2026."

Q: "Historique des traitements ?"
R: "2 traitements : savon noir sur courgettes (5 mars), bouillie bordelaise sur tomates (10 mars)."

Si une liste est necessaire : tirets courts uniquement, pas de paragraphes.
Si donnee absente : "Pas de donnees enregistrees pour cela."
Ne jamais inventer de donnees. Utilise UNIQUEMENT les donnees fournies.

REGLE CALCUL PLANTATIONS :
- Quantite totale = quantite x rang (si rang present), sinon quantite seule.
- Afficher UNIQUEMENT le total final, jamais les calculs intermediaires entre parentheses.
- Exemple correct  : "- tomate : 42 plants"
- Exemple INTERDIT : "- tomate : 42 plants (10 x 3 + 4 x 3)"

REGLE CALCUL STOCK REEL :
- Stock reel = plantations totales - pertes totales - récoltes totales pour chaque culture.
- Afficher : "culture : X plants (plante Y, perdu Z, récolté W)"
- Si pas de pertes ou récoltes : ajuster l'affichage en conséquence.
- Exemple : "salade : 19 plants (planté 25, perdu 4, récolté 2)"
"""

def repondre_question(question: str, contexte_json: str) -> str:
    """Repond a une question analytique sur l'historique."""
    chat = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {
                "role": "system",
                "content": QUERY_PROMPT.format(today_iso=date.today().isoformat())
                           + f"\n\nHistorique potager :\n{contexte_json}"
            },
            {"role": "user", "content": question}
        ],
        temperature=0.0,
        max_tokens=200,
        stream=False
    )
    return chat.choices[0].message.content.strip()
