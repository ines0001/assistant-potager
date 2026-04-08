import json
import logging
from datetime import datetime, timedelta

from database.models import Evenement
from llm.groq_client import extract_intent

log = logging.getLogger("potager.orchestrator")


# --- Intention simplifiée à partir de la question utilisateur ---
def extract_question_intent(question: str) -> dict:
    q = question.lower()

    intent = {
        "action": None,
        "culture": None,
        "filter_last": False,
        "filter_aggregated": False,
        "date_from": None,
    }

    # Actions identifiables
    for a in [
        "arrosage", "semis", "plantation", "recolte", "repiquage", "traitement",
        "desherbage", "taille", "paillage", "observation", "recolte_graines"
    ]:
        if a in q:
            intent["action"] = a
            break

    # Culture simple
    # Exemple: tomate, courgette, carotte, etc.
    mots = [
        "tomate", "courgette", "carotte", "salade", "radis", "oignon", "persil",
        "haricot", "poivron", "aubergine", "concombre", "chou", "navet", "betterave"
    ]
    for c in mots:
        if c in q:
            intent["culture"] = c
            break

    # Type de question
    if "combien" in q or "total" in q or "somme" in q or "kg" in q:
        intent["filter_aggregated"] = True
    if "derniere" in q or "dernier" in q or "quand" in q or "date" in q:
        intent["filter_last"] = True

    # Intervalles temporels simples
    if "semaine" in q or "7 jours" in q:
        intent["date_from"] = datetime.utcnow() - timedelta(days=7)
    elif "mois" in q or "30 jours" in q:
        intent["date_from"] = datetime.utcnow() - timedelta(days=30)

    return intent


# --- Requête DB filtrée ---
def fetch_filtered_events(db_session, intent: dict) -> list[Evenement]:
    query = db_session.query(Evenement)

    if intent.get("action"):
        query = query.filter(Evenement.type_action == intent["action"])
    if intent.get("culture"):
        query = query.filter(Evenement.culture == intent["culture"])
    if intent.get("date_from"):
        date_from = intent["date_from"]
        if isinstance(date_from, str):
            try:
                date_from = datetime.fromisoformat(date_from)
            except Exception:
                date_from = None
        if date_from:
            query = query.filter(Evenement.date >= date_from)

    # Dernier événement en priorité
    if intent.get("filter_last"):
        query = query.order_by(Evenement.date.desc()).limit(30)
    else:
        query = query.order_by(Evenement.date.desc()).limit(100)

    return query.all()


# --- Context JSON réduit pour LLM ---
def build_reduced_context(events: list[Evenement]) -> str:
    if not events:
        return "[]"

    data = []
    for e in events:
        data.append({
            "date": str(e.date)[:10] if e.date else None,
            "action": e.type_action,
            "culture": e.culture,
            "variete": e.variete,
            "quantite": e.quantite,
            "unite": e.unite,
            "parcelle": e.parcelle,
            "rang": e.rang,
            "duree_minutes": e.duree,
            "traitement": e.traitement,
            "commentaire": e.commentaire,
            "origine_graines_id": e.origine_graines_id,
        })

    # Max 50 éléments pour conserver faible token usage
    if len(data) > 50:
        data = data[:50]

    return json.dumps(data, ensure_ascii=False)


# --- Orchestrateur complet (question -> contexte réduit) ---
def build_question_context(db_session, question: str) -> str:
    log.info(f"🔍 ORCHESTRATOR | Question: '{question}'")

    intent = extract_question_intent(question)

    # Fallback vers Groq si intention locale non assez définie
    if not intent.get('action') and not intent.get('culture'):
        log.info("🚀 ORCHESTRATOR | Intention locale incomplete, appel fallback Groq pour extraire action/culture/date")
        external_intent = extract_intent(question)
        if external_intent:
            intent['action'] = intent.get('action') or external_intent.get('action')
            intent['culture'] = intent.get('culture') or external_intent.get('culture')
            if not intent.get('date_from') and external_intent.get('date_from'):
                intent['date_from'] = external_intent.get('date_from')

    log.info(f"🎯 ORCHESTRATOR | Intention extraite: action='{intent.get('action')}', culture='{intent.get('culture')}', "
             f"filter_last={intent.get('filter_last')}, filter_aggregated={intent.get('filter_aggregated')}, "
             f"date_from={intent.get('date_from')}")

    events = fetch_filtered_events(db_session, intent)
    log.info(f"📊 ORCHESTRATOR | Événements récupérés: {len(events)} (limite appliquée)")

    contexte = build_reduced_context(events)
    contexte_size = len(contexte)
    estimated_tokens = contexte_size // 4  # Approximation: ~4 caractères par token pour Groq
    log.info(f"📤 ORCHESTRATOR | Contexte JSON transmis à Groq: {contexte_size} caractères (~{estimated_tokens} tokens estimés)")

    return contexte
