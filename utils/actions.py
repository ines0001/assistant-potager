# app/utils/actions.py
from __future__ import annotations
import re
from unidecode import unidecode

# Actions canoniques (potager)
# IMPORTANT : recolte_graines DOIT précéder recolte pour éviter un faux match
# startswith("recolte") sur "recolte graines".
ACTION_MAP: dict[str, list[str]] = {
    "recolte_graines": [
        "recolte graines", "recolter graines", "recolte de graines",
        "graines recoltees", "graines recoltes",
        "recolte semences", "recolter semences", "semences recoltees",
        "ramasse graines", "ramasse les graines", "cueilli graines",
    ],
    # [US-recolte_finale] DOIT précéder "recolte" pour éviter faux match startswith
    "recolte_finale": [
        "recolte finale", "recolter finale", "derniere recolte", "dernier recolte",
        "fin de culture", "fin culture", "recolte de fin", "recolte definitive",
        "cloturer culture", "cloture culture", "recolte et cloture",
    ],
    "recolte": [
        "recolte", "recolter", "recolte de", "recolte des",
        "cueillir", "cueilli", "cueillie",
        "ramasser", "ramasse", "ramassees", "ramasses"
    ],
    "semis": [
        "semis", "semer", "seme", "semee", "semes", "semees"
    ],
    "plantation": [
        "planter", "plante", "plantee", "plantes", "plantees",
        "repiquer", "repique", "repiquee", "repiquees",
        "mise en terre", "mettre en terre", "transplanter"
    ],
    "arrosage": [
        "arrosage", "arroser", "arrose", "arrose", "arrosees",
        "irriguer", "donner de l eau", "donner de l'eau"
    ],
    "desherbage": [
        "desherbage", "desherber", "desherbe", "désherbé",
        "sarcler", "sarclage",
        "enlever les mauvaises herbes", "arracher les herbes"
    ],
    "paillage": [
        "paillage", "pailler", "paillé", "paillis",
        "mettre de la paille", "couvrir le sol", "mulch", "mulcher"
    ],
    "amendement": [
        "amender", "amendement",
        "ajouter du compost", "mettre du compost", "compost",
        "fumier", "terreau", "engrais", "fertiliser", "fertilisation", "fertilisé"
    ],
    "taille": [
        "taille", "tailler", "taillé", "couper", "pincer", "elaguer", "rabattre"
    ],
    "tuteurage": [
        "tuteurage", "tuteurer", "tuteuré", "mettre un tuteur",
        "attacher", "palissage", "palisser"
    ],
    "traitement": [
        "traitement", "traiter", "traité", "pulveriser", "pulverisation",
        "spray", "savon noir", "purin d ortie", "purin d'ortie"
    ],
    "protection": [
        "protection", "proteger", "protege",
        "voile", "filet", "cloche", "tunnel",
        "proteger du gel", "proteger du froid", "anti insectes", "anti-insectes"
    ],
    "observation": [
        "observation", "observer", "observé", "surveiller", "constat", "noter",
        "maladie", "mildiou", "attaque", "gel", "secheresse", "limaces"
    ],
    "perte": [
        "perte", "perdu", "perdue", "perdus", "perdues",
        "mort", "morte", "morts", "mortes",
        "arrache", "arrachee", "arraches", "arrachees",
        "creve", "crevee", "creves", "crevees",
        "disparu", "disparue", "disparus", "disparues"
    ],
    "mise_en_godet": [
        "mise en godet", "mis en godet", "mettre en godet",
        "godet", "godets", "rempotage godet",
        "repique en godet", "repique en godets",
    ],
}

# Petits mots à ignorer au début (langage naturel)
LEADING_NOISE = (
    "j ai", "j'ai", "on a", "on", "je", "tu", "il", "elle", "nous", "vous",
    "aujourd hui", "aujourd'hui", "hier", "ce matin", "cet apres midi", "cet après-midi",
)

def _clean_text(s: str) -> str:
    s = unidecode(s.lower())
    s = s.replace("’", "'")
    # normalise apostrophes / espaces
    s = re.sub(r"[^a-z0-9'\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def normalize_action(action: str | None) -> str | None:
    """
    Retourne l'action canonique (ex: 'recolte') ou None.
    Stratégie:
      - nettoie la chaîne (minuscules, sans accents)
      - enlève un préfixe de type "j'ai", "aujourd'hui"...
      - match sur startswith puis sur contains
      - fallback : renvoie la version nettoyée (utile pour détecter les nouveaux cas)
    """
    if not action:
        return None

    value = _clean_text(action)

    # retirer un peu de bruit en tête
    for noise in LEADING_NOISE:
        if value.startswith(noise + " "):
            value = value[len(noise):].strip()
            break

    # 1) startswith (le plus fiable)
    for canonical, variants in ACTION_MAP.items():
        for v in variants:
            v_clean = _clean_text(v)
            if value.startswith(v_clean):
                return canonical

    # 2) contains (plus permissif)
    for canonical, variants in ACTION_MAP.items():
        for v in variants:
            v_clean = _clean_text(v)
            if v_clean and v_clean in value:
                return canonical

    # fallback (permet de loguer/voir les actions inconnues)
    return value or None