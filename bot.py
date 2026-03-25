"""
bot.py — Bot Telegram pour l'Assistant Potager
------------------------------------------------
Fonctionnalités :
  - Message vocal → transcription Groq Whisper → parsing → PostgreSQL
  - Message texte → parsing direct → PostgreSQL
  - Récapitulatif vocal structuré après chaque enregistrement
  - /ask  → question analytique sur l'historique
  - /stats → statistiques rapides
  - /historique → derniers événements
  - /tts → afficher l'état de la synthèse vocale
  - /tts_on → activer les réponses vocales
  - /tts_off → désactiver les réponses vocales
  - Guidage conversationnel (propose les suites possibles)

Installation :
  pip install python-telegram-bot groq sqlalchemy psycopg2-binary unidecode python-dotenv gtts

Lancement :
  python bot.py
"""

import os
import json
import asyncio
import tempfile
import logging
from datetime import date, datetime

# ── Logging console ────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)s │ %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("potager")

from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    ContextTypes, filters, ConversationHandler
)
from groq import Groq
from sqlalchemy import func

from config import GROQ_API_KEY, DATABASE_URL, TELEGRAM_BOT_TOKEN, GROQ_WHISPER_MODEL
from database.db import SessionLocal, Base, engine
from database.models import Evenement
from utils.actions import normalize_action
from llm.groq_client import parse_commande, repondre_question
from utils.date_utils import parse_date
from utils.tts import send_voice_reply, set_tts_enabled, is_tts_enabled
from utils.meteo import save_meteo_observation, fetch_meteo, format_meteo_commentaire

# ── Init ────────────────────────────────────────────────────────────────────────
Base.metadata.create_all(bind=engine)

# ── Dictionnaire mots-clés → action ─────────────────────────────────────────
ACTION_KEYWORDS = {
    "arrosage"     : "arrosage",
    "arroser"      : "arrosage",
    "arrosé"       : "arrosage",
    "semis"        : "semis",
    "semé"         : "semis",
    "semer"        : "semis",
    "planté"       : "plantation",
    "planter"      : "plantation",
    "plantation"   : "plantation",
    "récolté"      : "recolte",
    "récolter"     : "recolte",
    "récolte"      : "recolte",
    "cueilli"      : "recolte",
    "ramassé"      : "recolte",
    "repiqué"      : "repiquage",
    "repiquer"     : "repiquage",
    "repiquage"    : "repiquage",
    "traité"       : "traitement",
    "traiter"      : "traitement",
    "traitement"   : "traitement",
    "désherbé"     : "desherbage",
    "désherber"    : "desherbage",
    "desherbage"   : "desherbage",
    "paillé"       : "paillage",
    "pailler"      : "paillage",
    "paillage"     : "paillage",
    "taillé"       : "taille",
    "tailler"      : "taille",
    "taille"       : "taille",
    "tuteuré"      : "tuteurage",
    "tuteurer"     : "tuteurage",
    "tuteurage"    : "tuteurage",
    "fertilisé"    : "fertilisation",
    "fertiliser"   : "fertilisation",
    "fertilisation": "fertilisation",
    "observé"      : "observation",
    "observer"     : "observation",
    "observation"  : "observation",
    "constaté"     : "observation",
}

# ── Légumes connus ────────────────────────────────────────────────────────────
CULTURES_CONNUES = {
    "tomate","tomates","carotte","carottes","courgette","courgettes",
    "salade","salades","laitue","laitues","radis","poireau","poireaux",
    "oignon","oignons","ail","ails","poivron","poivrons","aubergine",
    "aubergines","concombre","concombres","haricot","haricots","petits pois",
    "pois","épinard","épinards","chou","choux","chou-fleur","choux-fleurs",
    "brocoli","brocolis","celeri","céleri","panais","navet","navets",
    "betterave","betteraves","potiron","potirons","courge","courges",
    "mûre","mûres","fraise","fraises","framboise","framboises",
    "patate","patates","pomme de terre","pommes de terre","patate douce",
    "patates douces","maïs","persil","basilic","thym","romarin",
    "poireau","poireaux","échalote","échalotes","melon","melons",
    "pastèque","tomate cerise","tomates cerises",
}

# ── Mots temporels ─────────────────────────────────────────────────────────────
from datetime import date, timedelta

TEMPORAL_MAP = {
    "hier"        : lambda: (date.today() - timedelta(days=1)).isoformat(),
    "avant-hier"  : lambda: (date.today() - timedelta(days=2)).isoformat(),
    "aujourd'hui" : lambda: date.today().isoformat(),
    "aujourd hui" : lambda: date.today().isoformat(),
    "lundi"       : lambda: _last_weekday(0),
    "mardi"       : lambda: _last_weekday(1),
    "mercredi"    : lambda: _last_weekday(2),
    "jeudi"       : lambda: _last_weekday(3),
    "vendredi"    : lambda: _last_weekday(4),
    "samedi"      : lambda: _last_weekday(5),
    "dimanche"    : lambda: _last_weekday(6),
}

def _last_weekday(weekday: int) -> str:
    today = date.today()
    days_ago = (today.weekday() - weekday) % 7 or 7
    return (today - timedelta(days=days_ago)).isoformat()

def _infer_action(texte: str) -> str | None:
    words = texte.lower().replace(",", " ").replace(".", " ").split()
    for word in words:
        if word in ACTION_KEYWORDS:
            return ACTION_KEYWORDS[word]
    return None

def _infer_culture(texte: str) -> str | None:
    t = texte.lower()
    for cult in sorted(CULTURES_CONNUES, key=len, reverse=True):
        if cult in t:
            return cult.rstrip("s") if cult.endswith("s") and len(cult) > 4 else cult
    return None

def _infer_date(texte: str) -> str | None:
    t = texte.lower()
    for mot, fn in TEMPORAL_MAP.items():
        if mot in t:
            return fn()
    return None


def _normalize_items(items: list, texte_original: str = "") -> list:
    normalized = []
    for item in items:
        item = dict(item)
        if texte_original:
            if item.get("action") is None:
                inferred = _infer_action(texte_original)
                if inferred:
                    item["action"] = inferred
                    log.info(f"🔧 ACTION INFÉRÉE  : '{inferred}'")
            if item.get("culture") is None:
                action = item.get("action","")
                if action not in {"arrosage","desherbage","fertilisation"}:
                    inferred = _infer_culture(texte_original)
                    if inferred:
                        item["culture"] = inferred
                        log.info(f"🔧 CULTURE INFÉRÉE : '{inferred}'")
            if item.get("date") is None:
                if texte_original and any(m in texte_original.lower() for m in TEMPORAL_MAP):
                    inferred = _infer_date(texte_original)
                    if inferred:
                        item["date"] = inferred
                        log.info(f"🔧 DATE INFÉRÉE    : '{inferred}'")

        culture  = item.get("culture")
        quantite = item.get("quantite")

        if not isinstance(culture, list):
            normalized.append(item)
            continue

        log.warning(f"⚠️  NORMALISATION  : Groq a retourné des listes, explosion en {len(culture)} objets")
        for i, cult in enumerate(culture):
            new_item = dict(item)
            new_item["culture"] = cult
            if isinstance(quantite, list) and i < len(quantite):
                new_item["quantite"] = quantite[i]
            elif isinstance(quantite, list):
                new_item["quantite"] = None
            normalized.append(new_item)

    return normalized

groq_client = Groq(api_key=GROQ_API_KEY)

# ── Clavier principal ────────────────────────────────────────────────────────────
MENU_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("🎤 Nouvelle action vocale"), KeyboardButton("🔍 Interroger")],
        [KeyboardButton("📋 Historique"),             KeyboardButton("📊 Stats")],
    ],
    resize_keyboard=True,
    is_persistent=True
)

AFTER_RECORD_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("➕ Autre action"), KeyboardButton("🔍 Interroger mes données")],
        [KeyboardButton("📋 Historique"),  KeyboardButton("🏠 Menu principal")],
    ],
    resize_keyboard=True
)

WAITING_ASK = 1


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS PRINCIPAUX
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    prenom = update.effective_user.first_name or "jardinier"
    db = SessionLocal()
    nb = db.query(Evenement).count()
    db.close()

    tts_etat = "🔊 activée" if is_tts_enabled() else "🔇 désactivée"

    await update.message.reply_text(
        f"🌿 *Bonjour {prenom} !*\n\n"
        f"Je suis votre assistant potager.\n"
        f"📦 *{nb} événements* enregistrés dans votre base.\n"
        f"Synthèse vocale : {tts_etat}\n\n"
        f"Envoyez-moi un *message vocal* ou *texte* pour enregistrer une action.\n"
        f"Ex : _\"Récolté 3 kg de tomates variété cerise parcelle nord\"_\n\n"
        f"Ou utilisez les boutons ci-dessous :",
        parse_mode="Markdown",
        reply_markup=MENU_KEYBOARD
    )


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🎤 *Transcription en cours...*", parse_mode="Markdown")

    voice_file = await update.message.voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

    try:
        with open(tmp_path, "rb") as audio:
            transcription = groq_client.audio.transcriptions.create(
                file=("message.ogg", audio),
                model=GROQ_WHISPER_MODEL,
                language="fr",
                response_format="text"
            )
        texte = transcription.strip()
        os.unlink(tmp_path)
    except Exception as e:
        os.unlink(tmp_path)
        await msg.edit_text(f"❌ Erreur transcription : {e}")
        return

    if not texte:
        await msg.edit_text("❌ Je n'ai pas compris. Réessayez en parlant plus distinctement.")
        return

    log.info(f"🎤 TRANSCRIPTION  : {texte}")

    await msg.edit_text(f"🗣 _\"{texte}\"_\n\n⏳ Analyse en cours...", parse_mode="Markdown")

    mode = ctx.user_data.get('mode')
    MODES_CORR = {'corr_search','corr_select','corr_apply','corr_confirm','corr_confirm_delete'}
    if mode in MODES_CORR:
        if mode == 'corr_search':
            await _corr_search(update, ctx, texte)
        elif mode == 'corr_select':
            await _corr_select(update, ctx, texte)
        elif mode == 'corr_apply':
            await msg.delete()
            await _corr_apply(update, ctx, texte)
        elif mode == 'corr_confirm':
            await _corr_confirm(update, ctx, texte)
        elif mode == 'corr_confirm_delete':
            await _corr_confirm_delete(update, ctx, texte)
        return

    if mode == 'ask':
        ctx.user_data['mode'] = None
        await _ask_question(update, texte)
        return

    intent = classify_intent(texte)

    if intent == "STATS":
        await msg.edit_text("📊 *Statistiques*", parse_mode="Markdown")
        await cmd_stats(update, ctx)
        return
    if intent == "HISTORIQUE":
        await msg.edit_text("📋 *Historique*", parse_mode="Markdown")
        await cmd_historique(update, ctx)
        return
    if intent == "INTERROGER":
        mots = texte.strip().split()
        if len(mots) > 4:
            log.info(f"❓ QUESTION DIRECTE : '{texte}' → traitement immédiat")
            await msg.edit_text("🔍 *Analyse de vos données...*", parse_mode="Markdown")
            await _ask_question(update, texte)
        else:
            await msg.edit_text(
                "🔍 *Quelle est votre question ?*\n\nPosez-la en vocal ou par écrit.",
                parse_mode="Markdown"
            )
            ctx.user_data['mode'] = 'ask'
        return
    if intent == "CORRIGER":
        await msg.edit_text("✏️ *Mode correction*", parse_mode="Markdown")
        for k in ['mode','corr_event_id','corr_candidates','corr_last_id',
                  'corr_pending','corr_event_actuel']:
            ctx.user_data.pop(k, None)
        await _corr_start(update, ctx)
        return
    if intent == "SUPPRIMER":
        await msg.edit_text("🗑 *Suppression*", parse_mode="Markdown")
        await _corr_annuler_dernier(update, ctx)
        return
    if intent == "MENU":
        await msg.edit_text("🏠 *Menu principal*", parse_mode="Markdown")
        await cmd_start(update, ctx)
        return
    if intent == "NOUVELLE":
        await msg.edit_text(
            "🎤 *Je vous écoute !*\n\nDites-moi ce que vous avez fait au potager.",
            parse_mode="Markdown", reply_markup=MENU_KEYBOARD
        )
        return

    await _parse_and_save(update, texte, msg)


QUESTION_STARTERS = (
    "combien", "quand", "quel", "quelle", "quels", "quelles",
    "est-ce", "depuis", "total", "bilan de", "liste des",
    "montre", "donne", "rappelle", "résume", "résumé de",
    "quelle quantité", "quelle date", "à quelle",
    "date des", "dates des", "date de", "dates de",
    "liste de", "liste des", "historique de", "historique des",
    "dernière", "dernier", "derniers", "dernières",
    "quelles cultures", "quel traitement", "quels traitements",
)

ACTION_VERBS = (
    "arros", "semé", "semer", "planté", "planter", "récolté", "récolter",
    "cueilli", "cueillir", "ramassé", "ramasser", "repiqué", "repiquer",
    "traité", "traiter", "désherbé", "désherber", "paillé", "pailler",
    "taillé", "tailler", "tuteurer", "tuteuré", "fertilisé", "fertiliser",
    "observé", "observer", "constaté", "constater", "mis en", "mis ",
    "posé", "appliqué", "installé", "sorti",
)

def _is_question(texte: str) -> bool:
    t = texte.lower().strip()
    if t.startswith(ACTION_VERBS):
        return False
    return t.startswith(QUESTION_STARTERS) or t.endswith("?")

NAV_NOUVELLE = {"🎤 nouvelle action vocale", "➕ autre action", "autre action",
                "nouvelle action", "nouvelle", "action"}
NAV_INTERROGER = {"🔍 interroger", "🔍 interroger mes données", "interroger",
                  "interrogation", "question", "demander", "analyser",
                  "requête", "requete", "analyse", "recherche", "cherche"}
NAV_HISTORIQUE = {"📋 historique", "historique", "histo", "journal",
                  "historiques", "derniers", "dernier", "liste", "log"}
NAV_STATS      = {"📊 stats", "📊 statistiques", "stats", "statistiques", "stat",
                  "statistique", "chiffres", "résumé", "resume", "bilan",
                  "données", "donnees"}
NAV_MENU       = {"🏠 menu principal", "menu", "accueil", "home", "retour"}
NAV_CORRIGER   = {"✏️ corriger", "corriger", "modifier", "correction", "corriger le dernier",
                  "modifier le dernier", "annuler le dernier", "corriger une saisie",
                  "modifier une saisie", "/corriger",
                  "corrigé", "corrigée", "corrigés", "corrigées",
                  "modifié", "modifiée", "modifiés", "modifiées",
                  "une correction", "faire une correction", "une modification",
                  "je veux corriger", "je veux modifier"}
NAV_SUPPRIMER  = {"🗑 supprimer", "supprimer", "supprimer le dernier", "annuler",
                  "effacer", "effacer le dernier", "delete",
                  "supprimé", "supprimée", "supprimés", "effacé", "effacée"}

INTENTS = {
    "STATS", "HISTORIQUE", "INTERROGER", "CORRIGER",
    "SUPPRIMER", "MENU", "NOUVELLE", "ACTION",
}

_CLASSIFY_PROMPT = """Tu es un assistant potager. L'utilisateur t'envoie un message (transcrit vocalement ou tapé).
Classe ce message dans UNE SEULE catégorie parmi :
- STATS       : veut voir des statistiques, bilan, résumé, chiffres
- HISTORIQUE  : veut voir l'historique, le journal, les derniers événements
- INTERROGER  : pose une question sur ses données (combien, quand, quel...)
- CORRIGER    : veut corriger, modifier, changer un enregistrement existant
- SUPPRIMER   : veut supprimer ou effacer un enregistrement
- MENU        : veut revenir au menu, accueil, annuler
- NOUVELLE    : veut saisir une nouvelle action (après une autre)
- ACTION      : décrit une action potager à enregistrer (récolte, semis, plantation, arrosage, paillage, traitement, observation, fertilisation, taille, tuteurage, repiquage, désherbage)

Message : "{texte}"

Réponds avec UN SEUL MOT en majuscules parmi : STATS, HISTORIQUE, INTERROGER, CORRIGER, SUPPRIMER, MENU, NOUVELLE, ACTION
Réponse :"""

def classify_intent(texte: str) -> str:
    from groq import Groq
    from config import GROQ_API_KEY, GROQ_MODEL
    client = Groq(api_key=GROQ_API_KEY)
    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": _CLASSIFY_PROMPT.format(texte=texte)}],
            temperature=0.0,
            max_tokens=10,
        )
        intent = resp.choices[0].message.content.strip().upper().rstrip(".!? ")
        if intent not in INTENTS:
            log.warning(f"⚠️ INTENT INCONNU  : '{intent}' → fallback ACTION")
            intent = "ACTION"
        log.info(f"🧭 INTENT          : '{texte}' → {intent}")
        return intent
    except Exception as e:
        log.error(f"Erreur classify_intent : {e}")
        return "ACTION"


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    texte_raw = update.message.text.strip()
    texte     = texte_raw.lower()
    log.info(f"💬 MESSAGE TEXTE  : {texte_raw}")

    MODES_CORRECTION = {'corr_select', 'corr_apply', 'corr_search', 'corr_confirm_delete', 'corr_confirm'}
    if ctx.user_data.get('mode') not in MODES_CORRECTION:
        ctx.user_data['mode'] = None

    if texte in NAV_NOUVELLE:
        await update.message.reply_text(
            "🎤 *Je vous écoute !*\n\nEnvoyez-moi un message vocal ou tapez votre action.",
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        return

    if texte in NAV_INTERROGER:
        await update.message.reply_text(
            "🔍 *Quelle est votre question ?*\n\n"
            "Exemples :\n"
            "• _Combien de kg de tomates cette saison ?_\n"
            "• _Quand ai-je récolté mes patates douces ?_\n"
            "• _Historique des traitements courgettes_",
            parse_mode="Markdown"
        )
        ctx.user_data['mode'] = 'ask'
        return

    if texte in NAV_HISTORIQUE:
        await cmd_historique(update, ctx)
        return

    if texte in NAV_STATS:
        await cmd_stats(update, ctx)
        return

    if texte in NAV_MENU:
        await cmd_start(update, ctx)
        return

    mode = ctx.user_data.get('mode')
    MODES_CORR = {'corr_search','corr_select','corr_apply','corr_confirm','corr_confirm_delete'}

    if mode in MODES_CORR and (
        texte in NAV_CORRIGER or texte in NAV_MENU
        or texte in NAV_STATS or texte in NAV_HISTORIQUE
        or texte in NAV_INTERROGER
    ):
        log.info(f"🔄 RESET CORRECTION : mode={mode}, texte='{texte}' → nettoyage")
        for k in ['mode','corr_event_id','corr_candidates','corr_last_id',
                  'corr_pending','corr_event_actuel']:
            ctx.user_data.pop(k, None)
    elif mode == 'corr_search':
        await _corr_search(update, ctx, texte_raw)
        return
    elif mode == 'corr_select':
        await _corr_select(update, ctx, texte_raw)
        return
    elif mode == 'corr_apply':
        await _corr_apply(update, ctx, texte_raw)
        return
    elif mode == 'corr_confirm':
        await _corr_confirm(update, ctx, texte_raw)
        return
    elif mode == 'corr_confirm_delete':
        await _corr_confirm_delete(update, ctx, texte_raw)
        return

    if mode == 'ask':
        ctx.user_data['mode'] = None
        log.info(f"❓ MODE ASK        : reroutage → _ask_question")
        await _ask_question(update, texte_raw)
        return

    if texte in NAV_SUPPRIMER or any(texte.startswith(k) for k in ["supprimer", "effacer", "annuler"]):
        await _corr_annuler_dernier(update, ctx)
        return
    if texte in NAV_CORRIGER or any(texte.startswith(k) for k in ["corriger", "modifier"]):
        for k in ['mode','corr_event_id','corr_candidates','corr_last_id',
                  'corr_pending','corr_event_actuel']:
            ctx.user_data.pop(k, None)
        await _corr_start(update, ctx)
        return

    if _is_question(texte_raw):
        log.info(f"❓ QUESTION AUTO   : détectée → reroutage vers _ask_question")
        await _ask_question(update, texte_raw)
        return

    lignes = [l.strip() for l in texte_raw.split("\n") if l.strip()]
    if len(lignes) > 1:
        msg = await update.message.reply_text(
            f"⏳ *{len(lignes)} actions détectées*, traitement en cours...",
            parse_mode="Markdown"
        )
        await _parse_multi(update, lignes, msg)
    else:
        msg = await update.message.reply_text("⏳ Analyse en cours...", parse_mode="Markdown")
        await _parse_and_save(update, texte_raw, msg)


# ── PARSING MULTI-LIGNES ─────────────────────────────────────────────────────────
async def _parse_multi(update, lignes: list, msg=None):
    log.info(f"📋 MULTI-LIGNES    : {len(lignes)} phrases à traiter séparément")
    total_saved = []

    for i, ligne in enumerate(lignes, 1):
        log.info(f"  [{i}/{len(lignes)}] Traitement : {ligne}")
        try:
            items = parse_commande(ligne)
            items = _normalize_items(items, ligne)
        except Exception as e:
            log.error(f"  [{i}] Erreur parsing : {e}")
            continue

        first = items[0] if items else {}
        useful = [first.get(k) for k in ("action","culture","quantite","traitement","duree_minutes","parcelle","rang","variete","commentaire")]
        if all(v is None for v in useful):
            log.warning(f"  [{i}] JSON vide ignoré pour : {ligne}")
            continue

        db = SessionLocal()
        try:
            for parsed in items:
                event = Evenement(
                    type_action    = normalize_action(parsed.get("action")),
                    culture        = parsed.get("culture"),
                    variete        = parsed.get("variete"),
                    quantite       = _to_float(parsed.get("quantite")),
                    unite          = parsed.get("unite"),
                    parcelle       = parsed.get("parcelle"),
                    rang           = _to_int(parsed.get("rang")),
                    duree          = _to_int(parsed.get("duree_minutes")),
                    traitement     = parsed.get("traitement"),
                    commentaire    = parsed.get("commentaire"),
                    texte_original = ligne,
                    date           = parse_date(parsed.get("date")),
                )
                db.add(event)
                db.commit()
                db.refresh(event)
                log.info(f"  💾 DB SAVE : id={event.id} | action={event.type_action} | culture={event.culture} | date={event.date}")
                total_saved.append((parsed, event.id))
        except Exception as e:
            db.rollback()
            log.error(f"  [{i}] Erreur DB : {e}")
        finally:
            db.close()

    if not total_saved:
        if msg: await msg.edit_text("❌ Aucune action reconnue.")
        return

    lines_out = [f"✅ *{len(total_saved)} action(s) enregistrée(s)*\n"]
    for parsed, eid in total_saved:
        cult  = parsed.get("culture") or "—"
        act   = parsed.get("action")  or "?"
        d     = parsed.get("date")    or "aujourd'hui"
        lines_out.append(f"• #{eid} *{act}* — {cult} _{d}_")

    recap = "\n".join(lines_out)
    if msg:   await msg.edit_text(recap, parse_mode="Markdown")
    else:     await update.message.reply_text(recap, parse_mode="Markdown")
    await update.message.reply_text(
        "_Que voulez-vous faire ensuite ?_",
        parse_mode="Markdown",
        reply_markup=AFTER_RECORD_KEYBOARD
    )
    refreshed = SessionLocal()
    try:
        nb = refreshed.query(Evenement).count()
        log.info(f"📦 TOTAL BASE     : {nb} événements")
    finally:
        refreshed.close()


# ── PARSING + SAUVEGARDE ────────────────────────────────────────────────────────
async def _parse_and_save(update: Update, texte: str, msg=None):
    try:
        items = parse_commande(texte)
    except Exception as e:
        log.error(f"❌ ERREUR PARSING  : {e}")
        txt = f"❌ Erreur parsing : {e}\n\nEssayez de reformuler votre action."
        if msg: await msg.edit_text(txt)
        else:   await update.message.reply_text(txt)
        return

    log.info(f"🤖 GROQ PARSING   : {json.dumps(items, ensure_ascii=False)}")
    items = _normalize_items(items, texte)
    if len(items) > 1:
        log.info(f"📦 ITEMS NORMALISÉS: {len(items)} événements à sauvegarder")

    if not items:
        await update.message.reply_text("❌ Aucune action détectée.")
        return

    first = items[0] if items else {}
    useful_fields = [first.get(k) for k in (
        "action","culture","quantite","traitement",
        "duree_minutes","parcelle","rang","variete","commentaire"
    )]
    if all(v is None for v in useful_fields):
        log.warning("⚠️  JSON VIDE       : phrase non reconnue comme action, pas de sauvegarde")
        await update.message.reply_text(
            "🤔 Je n'ai pas compris cette action.\n\n"
            "• Pour enregistrer : _\"Récolté 2 kg de tomates hier\"_\n"
            "• Pour interroger  : _\"Combien de tomates ai-je récolté ?\"_",
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        return

    if len(items) == 1 and items[0].get("action") == "AMBIGUE":
        hint = items[0].get("commentaire", "précisez le nombre de plants par rang et le nombre de rangs")
        await update.message.reply_text(
            "🤔 *Précision nécessaire*\n\n"
            "Je n'ai pas bien compris la quantité et les rangs.\n\n"
            "Reformulez en précisant :\n"
            f"_{hint}_\n\n"
            "Exemple : _planter 10 choux-fleurs par rang sur 3 rangs parcelle nord_",
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        return

    db = SessionLocal()
    saved_items = []
    try:
        for parsed in items:
            event = Evenement(
                type_action    = normalize_action(parsed.get("action")),
                culture        = parsed.get("culture"),
                variete        = parsed.get("variete"),
                quantite       = _to_float(parsed.get("quantite")),
                unite          = parsed.get("unite"),
                parcelle       = parsed.get("parcelle"),
                rang           = _to_int(parsed.get("rang")),
                duree          = _to_int(parsed.get("duree_minutes")),
                traitement     = parsed.get("traitement"),
                commentaire    = parsed.get("commentaire"),
                texte_original = texte,
                date           = parse_date(parsed.get("date")),
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            log.info(f"💾 DB SAVE        : id={event.id} | action={event.type_action} | culture={event.culture} | qte={event.quantite} {event.unite or ''} | rang={event.rang} | parcelle={event.parcelle} | date={event.date}")
            saved_items.append((parsed, event.id))
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"❌ Erreur base de données : {e}")
        return
    finally:
        db.close()

    if len(saved_items) == 1:
        parsed, event_id = saved_items[0]
        recap = _build_recap(parsed, event_id)
        if msg:   await msg.edit_text(recap, parse_mode="Markdown")
        else:     await update.message.reply_text(recap, parse_mode="Markdown")
    else:
        lines_out = [f"✅ *{len(saved_items)} actions enregistrées !*\n"]
        for parsed, event_id in saved_items:
            cult = parsed.get("culture") or "?"
            qte  = str(parsed["quantite"]) + " " + (parsed.get("unite") or "") if parsed.get("quantite") else ""
            d    = parsed.get("date") or str(date.today())
            lines_out.append(f"• *{cult}* {qte} — _{d}_ ✔")
        recap_multi = "\n".join(lines_out)
        if msg:   await msg.edit_text(recap_multi, parse_mode="Markdown")
        else:     await update.message.reply_text(recap_multi, parse_mode="Markdown")

    await update.message.reply_text(
        "_Que voulez-vous faire ensuite ?_",
        parse_mode="Markdown",
        reply_markup=AFTER_RECORD_KEYBOARD
    )

    # ── Synthèse vocale du récapitulatif ─────────────────────────────────────
    if len(saved_items) == 1:
        parsed, _ = saved_items[0]
        await send_voice_reply(update, _build_recap_tts(parsed))


def _build_recap_tts(p: dict) -> str:
    parties = []
    action = p.get("action") or "action"
    parties.append(f"{action.capitalize()} enregistrée.")

    if p.get("culture"):
        qte    = p.get("quantite")
        unite  = p.get("unite") or ""
        cult   = p.get("culture")
        variete = p.get("variete")
        label  = f"{cult} {variete}".strip() if variete else cult
        if qte:
            rang = p.get("rang")
            if rang:
                total = int(qte) * int(rang)
                parties.append(f"{total} {unite} de {label} sur {rang} rangs.")
            else:
                parties.append(f"{qte} {unite} de {label}.".strip())
        else:
            parties.append(f"Culture : {label}.")

    if p.get("parcelle"):
        parties.append(f"Parcelle {p['parcelle']}.")
    if p.get("duree_minutes"):
        parties.append(f"Durée : {p['duree_minutes']} minutes.")
    if p.get("traitement"):
        parties.append(f"Traitement : {p['traitement']}.")
    if p.get("date"):
        parties.append(f"Date : {p['date']}.")
    if p.get("commentaire"):
        parties.append(p["commentaire"])

    return " ".join(parties)


def _build_recap(p: dict, event_id: int) -> str:
    lines = ["✅ *C'est noté !* _(ID #%d)_\n" % event_id]

    qte_str = None
    if p.get("quantite") is not None:
        qte_val = p["quantite"]
        unite   = p.get("unite") or ""
        rang    = p.get("rang")
        if rang:
            total   = int(qte_val) * int(rang)
            qte_str = f"{int(qte_val)} {unite}/rang × {rang} rangs = *{total} {unite} total*"
        else:
            qte_str = f"{qte_val} {unite}".strip()

    fields = [
        ("🌱 Action",      p.get("action")),
        ("🥬 Culture",     p.get("culture")),
        ("🏷 Variété",     p.get("variete")),
        ("⚖️ Quantité",   qte_str),
        ("📍 Parcelle",    p.get("parcelle")),
        ("🌾 Rangs",       str(p["rang"]) + " rangs" if p.get("rang") else None),
        ("⏱ Durée",       str(p["duree_minutes"]) + " min" if p.get("duree_minutes") else None),
        ("💊 Traitement",  p.get("traitement")),
        ("📅 Date",        p.get("date")),
        ("📝 Note",        p.get("commentaire")),
    ]

    for label, val in fields:
        if val:
            lines.append(f"{label} : *{val}*")

    lines.append("\n_Que voulez-vous faire ensuite ?_")
    return "\n".join(lines)


# ── QUESTION ANALYTIQUE ─────────────────────────────────────────────────────────
async def _ask_question(update: Update, question: str):
    log.info(f"🔍 QUESTION       : {question}")
    msg = await update.message.reply_text("🔍 *Analyse de vos données...*", parse_mode="Markdown")
    db  = SessionLocal()
    try:
        events = db.query(Evenement).order_by(Evenement.date).all()
        if not events:
            await msg.edit_text("📭 Aucune donnée enregistrée pour l'instant.")
            return

        data = [
            {
                "id"         : e.id,
                "date"       : str(e.date)[:10] if e.date else None,
                "action"     : e.type_action,
                "culture"    : e.culture,
                "variete"    : e.variete,
                "quantite"   : e.quantite,
                "unite"      : e.unite,
                "parcelle"   : e.parcelle,
                "rang"       : e.rang,
                "duree_min"  : e.duree,
                "traitement" : e.traitement,
                "commentaire": e.commentaire,
            }
            for e in events
        ]
        contexte = json.dumps(data, ensure_ascii=False)
        reponse  = repondre_question(question, contexte)

        log.info(f"💡 RÉPONSE GROQ   : {reponse[:200]}{'...' if len(reponse)>200 else ''}")
        try:
            await msg.edit_text(f"🔍 *Réponse :*\n\n{reponse}", parse_mode="Markdown")
        except Exception:
            await msg.edit_text(f"🔍 Réponse :\n\n{reponse}")
        await update.message.reply_text(
            "_Autre question ou action ?_",
            parse_mode="Markdown",
            reply_markup=AFTER_RECORD_KEYBOARD
        )
        # ── Synthèse vocale de la réponse analytique ─────────────────────────
        await send_voice_reply(update, reponse)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}", reply_markup=MENU_KEYBOARD)
    finally:
        db.close()


# ── COMMANDES ───────────────────────────────────────────────────────────────────
async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        total = db.query(Evenement).count()
        lines_out = [f"📊 *Statistiques potager*\n\n📦 Total : *{total} événements*\n"]

        recoltes = (
            db.query(Evenement.culture, Evenement.unite, func.sum(Evenement.quantite))
            .filter(Evenement.type_action == "recolte")
            .group_by(Evenement.culture, Evenement.unite)
            .all()
        )
        if recoltes:
            lines_out.append("🥬 *Récoltes :*")
            for culture, unite, qte in recoltes:
                if culture:
                    lines_out.append(f"  • {culture} : *{round(qte,2) if qte else 0} {unite or 'unités'}*")

        plantations = (
            db.query(Evenement.culture, Evenement.quantite, Evenement.rang, Evenement.unite)
            .filter(Evenement.type_action == "plantation")
            .all()
        )
        if plantations:
            totaux = {}
            for culture, qte, rang, unite in plantations:
                if not culture: continue
                total_plants = (qte or 0) * (rang or 1)
                key = (culture, unite or "plants")
                totaux[key] = totaux.get(key, 0) + total_plants
            if totaux:
                lines_out.append("\n🌱 *Plantations (total plants) :*")
                for (culture, unite), tot in totaux.items():
                    lines_out.append(f"  • {culture} : *{int(tot)} {unite}*")

        arrosages = (
            db.query(func.count(Evenement.id), func.sum(Evenement.duree))
            .filter(Evenement.type_action == "arrosage")
            .first()
        )
        if arrosages and arrosages[0]:
            lines_out.append(f"\n💧 *Arrosages :* {arrosages[0]} fois")
            if arrosages[1]:
                lines_out.append(f"  Durée totale : *{arrosages[1]} min*")

        await update.message.reply_text(
            "\n".join(lines_out),
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        # ── Synthèse vocale des statistiques ─────────────────────────────────
        await send_voice_reply(update, "\n".join(lines_out))
    finally:
        db.close()


async def cmd_historique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        events = (
            db.query(Evenement)
            .order_by(Evenement.date.desc())
            .limit(10)
            .all()
        )
        if not events:
            await update.message.reply_text("📭 Aucun événement enregistré.")
            return

        lines = ["📋 *10 derniers événements :*\n"]
        for e in events:
            d      = str(e.date)[:10] if e.date else "?"
            action = (e.type_action or "?").upper()
            cult   = " ".join(filter(None, [e.culture, e.variete]))
            qte    = f"{e.quantite} {e.unite or ''}" if e.quantite else ""
            parc   = f"· {e.parcelle}" if e.parcelle else ""
            lines.append(f"*{d}* — {action}\n  {cult} {qte} {parc}".strip())

        await update.message.reply_text(
            "\n\n".join(lines),
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        # ── Synthèse vocale de l'historique ──────────────────────────────────
        await send_voice_reply(update, "\n\n".join(lines))
    finally:
        db.close()


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    question = " ".join(ctx.args) if ctx.args else None
    if not question:
        await update.message.reply_text(
            "🔍 *Posez votre question :*\n\nEx : `/ask Combien de tomates cette saison ?`",
            parse_mode="Markdown"
        )
        return
    await _ask_question(update, question)


# ── COMMANDES TTS ────────────────────────────────────────────────────────────────
async def cmd_tts(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Affiche l'état de la synthèse vocale + rappel des commandes."""
    etat = "🔊 *activée*" if is_tts_enabled() else "🔇 *désactivée*"
    await update.message.reply_text(
        f"Synthèse vocale : {etat}\n\n"
        f"• `/tts_on`  — activer les réponses vocales\n"
        f"• `/tts_off` — désactiver les réponses vocales",
        parse_mode="Markdown"
    )

async def cmd_tts_on(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Active les réponses vocales (persiste au redémarrage)."""
    set_tts_enabled(True)
    log.info("🔊 TTS ACTIVÉ      : par commande utilisateur")
    await update.message.reply_text(
        "🔊 *Synthèse vocale activée !*\n\n"
        "Je vais maintenant lire mes réponses à voix haute.\n"
        "Tapez `/tts_off` pour désactiver.",
        parse_mode="Markdown"
    )

async def cmd_tts_off(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Désactive les réponses vocales (persiste au redémarrage)."""
    set_tts_enabled(False)
    log.info("🔇 TTS DÉSACTIVÉ   : par commande utilisateur")
    await update.message.reply_text(
        "🔇 *Synthèse vocale désactivée.*\n\n"
        "Tapez `/tts_on` pour réactiver.",
        parse_mode="Markdown"
    )


# ── HELPERS ─────────────────────────────────────────────────────────────────────
def _to_float(v):
    try:    return float(v) if v is not None else None
    except: return None

def _to_int(v):
    try:    return int(float(v)) if v is not None else None
    except: return None


# ══════════════════════════════════════════════════════════════════════════════
# SYSTÈME DE CORRECTION
# ══════════════════════════════════════════════════════════════════════════════

CORR_KEYBOARD = ReplyKeyboardMarkup(
    [["✏️ Corriger", "🗑 Supprimer"], ["❌ Annuler"]],
    resize_keyboard=True, one_time_keyboard=True
)

def _fmt_event(e) -> str:
    d    = e.date.strftime("%d/%m") if e.date else "?"
    act  = e.type_action or "?"
    cult = f" {e.culture}" if e.culture else ""
    qte  = f" {e.quantite}{e.unite or ''}" if e.quantite else ""
    parc = f" [{e.parcelle}]" if e.parcelle else ""
    rang = f" x{e.rang}rangs" if e.rang else ""
    trt  = f" ({e.traitement})" if e.traitement else ""
    return f"#{e.id} {d} — {act}{cult}{qte}{rang}{parc}{trt}"


def _normalize_action_search(action: str) -> str:
    from unidecode import unidecode
    mapping = {
        "recolte": "recolte", "récolte": "recolte", "recolter": "recolte", "récolter": "recolte",
        "plantation": "plantation", "planter": "plantation", "planté": "plantation",
        "semis": "semis", "semer": "semis", "semé": "semis",
        "repiquage": "repiquage", "repiquer": "repiquage", "repiqué": "repiquage",
        "arrosage": "arrosage", "arroser": "arrosage", "arrosé": "arrosage",
        "traitement": "traitement", "traiter": "traitement", "traité": "traitement",
        "desherbage": "desherbage", "désherbage": "desherbage", "desherber": "desherbage",
        "paillage": "paillage", "pailler": "paillage", "paillé": "paillage",
        "taille": "taille", "tailler": "taille", "taillé": "taille",
        "tuteurage": "tuteurage", "tuteurer": "tuteurage", "tuteuré": "tuteurage",
        "fertilisation": "fertilisation", "fertiliser": "fertilisation",
        "observation": "observation", "observer": "observation",
    }
    key = unidecode(action.lower().strip())
    return mapping.get(action.lower().strip(), mapping.get(key, action.lower().strip()))


def _find_candidates(description: str, limit: int = 3) -> list:
    from groq import Groq
    from config import GROQ_API_KEY, GROQ_MODEL
    import json

    client = Groq(api_key=GROQ_API_KEY)
    today     = date.today()
    last_week = (today - timedelta(days=7)).isoformat()
    last_month= (today - timedelta(days=30)).isoformat()

    prompt = f"""Aujourd'hui : {today.isoformat()} (année {today.year}).
L'utilisateur veut retrouver un événement potager.
Description : "{description}"

Retourne UNIQUEMENT ce JSON (null si non mentionné) :
{{"action": string|null, "culture": string|null, "date_debut": "YYYY-MM-DD"|null, "date_fin": "YYYY-MM-DD"|null, "parcelle": string|null}}

RÈGLES :
- action SANS accent : recolte, plantation, semis, arrosage, paillage, traitement, desherbage, taille, observation, tuteurage, fertilisation, repiquage
- culture au singulier minuscule sans accent
- "11 mars" ou "11 mars dernier" → date_debut="{today.year}-03-11", date_fin="{today.year}-03-11"  
- "la semaine dernière" → date_debut="{last_week}", date_fin="{today.isoformat()}"
- "ce mois" → date_debut="{last_month}", date_fin="{today.isoformat()}"
- "le dernier/la dernière" → pas de date, juste l'action/culture
- Toujours utiliser l'année {today.year} sauf si explicitement dit autrement
JSON brut uniquement."""

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=200
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        criteres = json.loads(raw)
    except Exception as e:
        log.error(f"Groq critères erreur : {e}")
        criteres = {}

    if criteres.get("action"):
        criteres["action"] = _normalize_action_search(criteres["action"])

    log.info(f"🔎 CRITÈRES RECHERCHE : {criteres}")

    db = SessionLocal()
    try:
        q = db.query(Evenement)
        if criteres.get("action"):
            q = q.filter(Evenement.type_action == criteres["action"])
        if criteres.get("culture"):
            q = q.filter(Evenement.culture.ilike(f"%{criteres['culture']}%"))
        if criteres.get("parcelle"):
            q = q.filter(Evenement.parcelle.ilike(f"%{criteres['parcelle']}%"))
        if criteres.get("date_debut"):
            q = q.filter(Evenement.date >= criteres["date_debut"])
        if criteres.get("date_fin"):
            q = q.filter(Evenement.date <= criteres["date_fin"] + " 23:59:59")
        results = q.order_by(Evenement.date.desc()).limit(limit).all()
        log.info(f"🔎 RÉSULTATS SQL   : {len(results)} trouvé(s)")
        return results
    finally:
        db.close()


async def _corr_annuler_dernier(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        event = db.query(Evenement).order_by(Evenement.id.desc()).first()
        if not event:
            await update.message.reply_text("❌ Aucun événement en base.")
            return
        ctx.user_data['corr_event_id'] = event.id
        ctx.user_data['mode'] = 'corr_select'
        ctx.user_data['corr_candidates'] = [event.id]
        await update.message.reply_text(
            f"Voici le dernier enregistrement :\n\n`{_fmt_event(event)}`\n\n"
            f"Que souhaitez-vous faire ?",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["✏️ Corriger", "🗑 Supprimer"], ["❌ Annuler"]],
                resize_keyboard=True, one_time_keyboard=True
            )
        )
    finally:
        db.close()


async def _corr_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    db = SessionLocal()
    try:
        last = db.query(Evenement).order_by(Evenement.id.desc()).first()
    finally:
        db.close()

    ctx.user_data['mode'] = 'corr_search'
    ctx.user_data['corr_last_id'] = last.id if last else None

    txt = "✏️ *Mode correction*\n\nDécrivez l'action à retrouver :\n_Ex : récolte de tomates du 11 mars, dernier arrosage, paillage courgettes..._"
    if last:
        txt += f"\n\n_Ou tapez_ *1* _pour sélectionner directement le dernier :_\n`{_fmt_event(last)}`"

    await update.message.reply_text(
        txt, parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup([["1", "❌ Annuler"]], resize_keyboard=True)
    )


async def _corr_search(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    if "annuler" in texte.lower():
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    if texte.strip() == "1" and ctx.user_data.get('corr_last_id'):
        db = SessionLocal()
        try:
            event = db.get(Evenement, ctx.user_data['corr_last_id'])
            candidates = [event] if event else []
        finally:
            db.close()
    else:
        msg_wait = await update.message.reply_text("🔎 Recherche en cours...")
        candidates = _find_candidates(texte)
        try:
            await msg_wait.delete()
        except Exception:
            pass

    if not candidates:
        await update.message.reply_text(
            "❌ Aucun événement trouvé avec ces critères.\n\n"
            "💡 Essayez en précisant : l'action (_récolte, plantation..._), "
            "la culture (_tomate, carotte..._) ou la date (_11 mars, hier..._)",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ Annuler"]], resize_keyboard=True)
        )
        return

    ctx.user_data['corr_candidates'] = [e.id for e in candidates]
    ctx.user_data['mode'] = 'corr_select'

    if len(candidates) == 1:
        e = candidates[0]
        ctx.user_data['corr_event_id'] = e.id
        ctx.user_data['mode'] = 'corr_apply'
        await update.message.reply_text(
            f"✅ Événement trouvé :\n\n`{_fmt_event(e)}`\n\n"
            f"✏️ Dites-moi ce que vous souhaitez modifier :\n"
            f"_Ex : c\'était 3 kg / la date c\'était le 9 mars / ajouter parcelle nord_\n\n"
            f"Ou : [🗑 Supprimer] pour effacer cet événement.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["🗑 Supprimer"], ["❌ Annuler"]],
                resize_keyboard=True
            )
        )
    else:
        lines = ["*Plusieurs événements trouvés, lequel voulez-vous modifier ?*\n"]
        for i, e in enumerate(candidates, 1):
            lines.append(f"*{i}.* `{_fmt_event(e)}`")
        btns = [[str(i) for i in range(1, len(candidates)+1)], ["❌ Annuler"]]
        await update.message.reply_text(
            "\n".join(lines), parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(btns, resize_keyboard=True)
        )


async def _corr_select(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    t = texte.strip().lower()

    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    event_id = ctx.user_data.get('corr_event_id')

    if not event_id:
        try:
            num = int(t) - 1
            candidates = ctx.user_data.get('corr_candidates', [])
            event_id = candidates[num]
            ctx.user_data['corr_event_id'] = event_id
        except (ValueError, IndexError):
            await update.message.reply_text("❓ Tapez le numéro affiché (1, 2, 3...).")
            return

    db = SessionLocal()
    try:
        event = db.get(Evenement, event_id)
    finally:
        db.close()

    if not event:
        await update.message.reply_text("❌ Événement introuvable.")
        ctx.user_data['mode'] = None
        return

    if "supprimer" in t:
        ctx.user_data['mode'] = 'corr_confirm_delete'
        await update.message.reply_text(
            f"⚠️ *Confirmer la suppression ?*\n\n`{_fmt_event(event)}`\n\nCette action est irréversible.",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup(
                [["✅ Oui, supprimer"], ["❌ Non, annuler"]], resize_keyboard=True
            )
        )
        return

    if t in ("✏️ corriger", "corriger"):
        ctx.user_data['mode'] = 'corr_apply'
        await update.message.reply_text(
            f"✏️ Événement à corriger :\n\n`{_fmt_event(event)}`\n\n"
            f"Dites-moi ce que vous souhaitez modifier :\n"
            f"_Ex : c'était 3 kg et non 2 / la date c'était le 10 mars / ajouter parcelle nord_",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ Annuler"]], resize_keyboard=True)
        )
        return

    MOTS_CORRECTION = ("changer", "modifier", "mettre", "c'était", "c etait",
                       "il s'agit", "il s agit", "ajouter", "enlever", "suppr",
                       "corriger", "plutôt", "plutot", "non ", "pas ")
    if any(t.startswith(m) or m in t for m in MOTS_CORRECTION):
        log.info(f"⚡ CORRECTION DIRECTE : texte '{texte}' → saut vers corr_apply")
        ctx.user_data['mode'] = 'corr_apply'
        await _corr_apply(update, ctx, texte)
        return

    ctx.user_data['corr_event_id'] = event_id
    await update.message.reply_text(
        f"Événement sélectionné :\n\n`{_fmt_event(event)}`\n\nQue souhaitez-vous faire ?",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardMarkup(
            [["✏️ Corriger", "🗑 Supprimer"], ["❌ Annuler"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )


async def _corr_confirm_delete(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    t = texte.strip().lower()
    event_id = ctx.user_data.get('corr_event_id')

    if "oui" in t or "supprimer" in t:
        db = SessionLocal()
        try:
            event = db.get(Evenement, event_id)
            if event:
                db.delete(event)
                db.commit()
                log.info(f"🗑 SUPPRESSION     : id={event_id}")
        finally:
            db.close()
        ctx.user_data['mode'] = None
        ctx.user_data.pop('corr_event_id', None)
        await update.message.reply_text(
            f"🗑 Événement #{event_id} supprimé avec succès.",
            reply_markup=MENU_KEYBOARD
        )
    else:
        ctx.user_data['mode'] = None
        ctx.user_data.pop('corr_event_id', None)
        await update.message.reply_text("↩️ Suppression annulée.", reply_markup=MENU_KEYBOARD)


async def _corr_apply(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    t = texte.strip().lower()
    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return
    if "supprimer" in t:
        event_id = ctx.user_data.get('corr_event_id')
        if event_id:
            ctx.user_data['corr_event_id'] = event_id
            ctx.user_data['mode'] = 'corr_confirm_delete'
            db = SessionLocal()
            try:
                ev = db.get(Evenement, event_id)
                txt = _fmt_event(ev) if ev else f"#{event_id}"
            finally:
                db.close()
            await update.message.reply_text(
                f"⚠️ *Confirmer la suppression ?*\n\n`{txt}`",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardMarkup(
                    [["✅ Oui, supprimer"], ["❌ Non, annuler"]], resize_keyboard=True
                )
            )
        return

    event_id = ctx.user_data.get('corr_event_id')
    if not event_id:
        ctx.user_data['mode'] = None
        return

    db = SessionLocal()
    try:
        event = db.get(Evenement, event_id)
        if not event:
            await update.message.reply_text("❌ Événement introuvable.")
            ctx.user_data['mode'] = None
            return
        event_actuel = {
            "action": event.type_action, "culture": event.culture,
            "variete": event.variete, "quantite": float(event.quantite) if event.quantite else None,
            "unite": event.unite, "parcelle": event.parcelle,
            "rang": event.rang, "duree_minutes": event.duree,
            "traitement": event.traitement, "commentaire": event.commentaire,
            "date": event.date.strftime("%Y-%m-%d") if event.date else None
        }
    finally:
        db.close()

    msg_wait = await update.message.reply_text("⏳ Analyse de la correction...")

    from groq import Groq
    from config import GROQ_API_KEY, GROQ_MODEL
    import json

    client = Groq(api_key=GROQ_API_KEY)
    today     = date.today()
    yesterday = (today - timedelta(days=1)).isoformat()

    prompt = f"""Aujourd'hui : {today.isoformat()}. Hier : {yesterday}.
Événement actuel : {json.dumps(event_actuel, ensure_ascii=False)}
Correction demandée : "{texte}"

Retourne UNIQUEMENT un JSON avec les champs MODIFIÉS (seulement ceux qui changent) :
{{"champ": nouvelle_valeur, ...}}

Champs disponibles : action, culture, variete, quantite, unite, parcelle, rang, duree_minutes, traitement, commentaire, date (format YYYY-MM-DD)
Exemples :
"c'était 3 kg pas 2" → {{"quantite": 3}}
"la date c'était le 10 mars" → {{"date": "{today.year}-03-10"}}
"ajouter parcelle nord" → {{"parcelle": "nord"}}
"enlever la parcelle" → {{"parcelle": null}}
"c'était 4 plants et non 5" → {{"quantite": 4}}
JSON brut uniquement."""

    try:
        resp = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0, max_tokens=300
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:-1])
        corrections = json.loads(raw)
    except Exception as e:
        log.error(f"Groq correction erreur : {e}")
        await msg_wait.edit_text("❌ Je n'ai pas compris la correction. Reformulez.")
        return

    if not corrections:
        await msg_wait.edit_text(
            "❓ Je n'ai identifié aucun champ à modifier.\n"
            "Précisez davantage : _ex : c'était 3 kg, la date c'était hier..._",
            parse_mode="Markdown"
        )
        return

    log.info(f"✏️ CORRECTIONS     : {corrections}")

    LABELS = {
        "action": "Action", "culture": "Culture", "variete": "Variété",
        "quantite": "Quantité", "unite": "Unité", "parcelle": "Parcelle",
        "rang": "Rangs", "duree_minutes": "Durée (min)", "traitement": "Traitement",
        "commentaire": "Commentaire", "date": "Date"
    }

    lines = [f"📋 *Résumé des modifications sur #{event_id} :*\n"]
    for champ, nouvelle_val in corrections.items():
        ancienne_val = event_actuel.get(champ, "—") or "—"
        label = LABELS.get(champ, champ)
        lines.append(f"• *{label}* : `{ancienne_val}` → `{nouvelle_val if nouvelle_val is not None else 'supprimé'}`")

    lines.append("\nConfirmez-vous ces modifications ?")

    ctx.user_data['corr_pending']      = corrections
    ctx.user_data['corr_event_actuel'] = event_actuel
    ctx.user_data['mode'] = 'corr_confirm'

    await msg_wait.edit_text("\n".join(lines), parse_mode="Markdown")
    await update.message.reply_text(
        "Confirmez ?",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Confirmer"], ["✏️ Modifier autre chose"], ["❌ Annuler"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )


async def _corr_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    t = texte.strip().lower()

    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    if "modifier" in t or "autre" in t:
        ctx.user_data['mode'] = 'corr_apply'
        db = SessionLocal()
        try:
            event = db.get(Evenement, ctx.user_data['corr_event_id'])
        finally:
            db.close()
        await update.message.reply_text(
            f"✏️ Que souhaitez-vous modifier d'autre ?\n\n`{_fmt_event(event)}`",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardMarkup([["❌ Annuler"]], resize_keyboard=True)
        )
        return

    if "confirm" in t or "oui" in t or t == "✅ confirmer":
        event_id    = ctx.user_data.get('corr_event_id')
        corrections = ctx.user_data.get('corr_pending', {})
        event_actuel= ctx.user_data.get('corr_event_actuel', {})
        mapping = {
            "action": "type_action", "culture": "culture", "variete": "variete",
            "quantite": "quantite", "unite": "unite", "parcelle": "parcelle",
            "rang": "rang", "duree_minutes": "duree", "traitement": "traitement",
            "commentaire": "commentaire"
        }
        db = SessionLocal()
        try:
            event = db.get(Evenement, event_id)
            for champ, valeur in corrections.items():
                col = mapping.get(champ, champ)
                if champ == "date":
                    setattr(event, "date", parse_date(valeur))
                elif champ == "quantite":
                    setattr(event, col, _to_float(valeur))
                elif champ in ("rang", "duree_minutes"):
                    setattr(event, col, _to_int(valeur))
                elif hasattr(event, col):
                    setattr(event, col, valeur)

            LABELS = {
                "action": "action", "culture": "culture", "variete": "variété",
                "quantite": "quantité", "unite": "unité", "parcelle": "parcelle",
                "rang": "rangs", "duree_minutes": "durée", "traitement": "traitement",
                "commentaire": "commentaire", "date": "date"
            }
            details = ", ".join(
                f"{LABELS.get(k, k)}: {event_actuel.get(k, '—') or '—'} → {v if v is not None else 'supprimé'}"
                for k, v in corrections.items()
            )
            trace = f" | [CORR {date.today().isoformat()}] {details}"
            event.texte_original = (event.texte_original or "") + trace
            log.info(f"📝 TRACE CORRECTION: {trace}")
            db.commit()
            db.refresh(event)
            log.info(f"✅ CORRIGÉ         : id={event_id} → {_fmt_event(event)}")
            result_fmt = _fmt_event(event)
        except Exception as e:
            db.rollback()
            log.error(f"Erreur UPDATE : {e}")
            await update.message.reply_text(f"❌ Erreur : {e}", reply_markup=MENU_KEYBOARD)
            return
        finally:
            db.close()

        ctx.user_data['mode'] = None
        ctx.user_data.pop('corr_pending', None)
        ctx.user_data.pop('corr_event_id', None)
        ctx.user_data.pop('corr_event_actuel', None)

        await update.message.reply_text(
            f"✅ *Modification enregistrée !*\n\n`{result_fmt}`",
            parse_mode="Markdown",
            reply_markup=AFTER_RECORD_KEYBOARD
        )
    else:
        await update.message.reply_text(
            "❓ Tapez *✅ Confirmer* pour valider ou *❌ Annuler*.",
            parse_mode="Markdown"
        )


# ══════════════════════════════════════════════════════════════════════════════
# MÉTÉO
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_meteo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """
    /meteo — Déclenche manuellement la récupération météo et l'enregistre en base.
    Utile pour tester ou forcer une mise à jour hors du job automatique 5h00.
    """
    msg = await update.message.reply_text("🌤️ *Récupération météo en cours...*", parse_mode="Markdown")
    db  = SessionLocal()
    try:
        meteo = save_meteo_observation(db)
        if meteo is None:
            # Doublon ou erreur — tenter un fetch sans sauvegarde pour afficher quand même
            meteo = fetch_meteo()
            if meteo:
                commentaire = format_meteo_commentaire(meteo)
                await msg.edit_text(
                    f"🌤️ *Météo du jour* _(déjà enregistrée aujourd'hui)_\n\n`{commentaire}`",
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text("❌ Impossible de récupérer la météo. Vérifiez votre connexion.")
            return

        commentaire = format_meteo_commentaire(meteo)
        await msg.edit_text(
            f"🌤️ *Météo enregistrée !*\n\n`{commentaire}`",
            parse_mode="Markdown"
        )
        log.info("🌤️  MÉTÉO MANUELLE  : déclenchée par /meteo")
    except Exception as e:
        log.error(f"❌ MÉTÉO COMMANDE   : {e}")
        await msg.edit_text(f"❌ Erreur : {e}")
    finally:
        db.close()


async def job_meteo_quotidienne(context: ContextTypes.DEFAULT_TYPE):
    """
    Job planifié à 05h00 chaque matin (Europe/Paris).
    Récupère la météo Open-Meteo et l'enregistre silencieusement en base
    comme action 'observation' avec texte_original='[AUTO-METEO]'.
    Aucun message Telegram envoyé.
    Zéro token Groq consommé.
    """
    log.info("🌅 JOB MÉTÉO       : déclenchement automatique 05h00")
    db = SessionLocal()
    try:
        meteo = save_meteo_observation(db)
        if meteo:
            log.info(
                f"🌤️  MÉTÉO AUTO      : {meteo['emoji']} {meteo['label']} | "
                f"{meteo['temp_matin']}°C matin / {meteo['temp_aprem']}°C AM | "
                f"Pluie {meteo['precipitations']}mm ({meteo['proba_pluie']}%)"
            )
        else:
            log.warning("⚠️  MÉTÉO AUTO      : aucune donnée sauvée (doublon ou erreur réseau)")
    except Exception as e:
        log.error(f"❌ JOB MÉTÉO ERREUR : {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# LANCEMENT
# ══════════════════════════════════════════════════════════════════════════════
def main():
    print("🌿 Démarrage du bot Telegram potager...")
    print(f"   Token : {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"   TTS   : {'🔊 activé' if is_tts_enabled() else '🔇 désactivé'} (commande /tts pour changer)")
    print(f"   Météo : 🌤️ job planifié à 05h00 Europe/Paris · /meteo pour déclencher manuellement")

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Commandes
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("stats",      cmd_stats))
    app.add_handler(CommandHandler("historique", cmd_historique))
    app.add_handler(CommandHandler("ask",        cmd_ask))
    app.add_handler(CommandHandler("corriger",   lambda u,c: _corr_start(u,c)))

    # Commandes TTS
    app.add_handler(CommandHandler("tts",        cmd_tts))
    app.add_handler(CommandHandler("tts_on",     cmd_tts_on))
    app.add_handler(CommandHandler("tts_off",    cmd_tts_off))

    # Commande météo manuelle
    app.add_handler(CommandHandler("meteo",      cmd_meteo))

    # Messages
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # ── Job météo quotidien à 05h00 (Europe/Paris) ────────────────────────────
    import pytz
    from datetime import time as dtime
    tz_paris = pytz.timezone("Europe/Paris")
    app.job_queue.run_daily(
        job_meteo_quotidienne,
        time=dtime(hour=5, minute=0, second=0, tzinfo=tz_paris),
        name="meteo_quotidienne",
    )
    log.info("🌅 JOB MÉTÉO       : planifié à 05h00 Europe/Paris")

    print("   Bot prêt ! Ouvrez Telegram et parlez à votre bot.")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
