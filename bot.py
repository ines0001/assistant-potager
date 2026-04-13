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
    datefmt="%Y-%m-%d %H:%M:%S"  # Affiche date + heure
)
log = logging.getLogger("potager")

# ── Suppression logs verbeux (HTTP Telegram, httpx, etc.) ──────────────────────
logging.getLogger("httpx").setLevel(logging.WARNING)  # Supprime logs HTTP
logging.getLogger("telegram").setLevel(logging.WARNING)  # Supprime logs telegram.ext
logging.getLogger("apscheduler").setLevel(logging.WARNING)  # Supprime logs scheduler

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
from utils.parcelles import (
    calcul_occupation_parcelles, normalize_parcelle_name,
    find_doublon, create_parcelle, update_parcelle, get_all_parcelles,
    resolve_parcelle, rename_parcelle,
)
from llm.groq_client import parse_commande, repondre_question
from utils.ia_orchestrator import build_question_context
from utils.date_utils import parse_date
from utils.tts import send_voice_reply, set_tts_enabled, is_tts_enabled
from utils.stock import calcul_stock_cultures, format_stock_ligne_telegram
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
    "perdu"        : "perte",
    "perte"        : "perte",
    "mort"         : "perte",
    "arraché"      : "perte",
    "crevé"        : "perte",
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
    """Déduit l'action depuis le texte si Groq a retourné action=null."""
    words = texte.lower().replace(",", " ").replace(".", " ").split()
    for word in words:
        if word in ACTION_KEYWORDS:
            return ACTION_KEYWORDS[word]
    return None

def _infer_culture(texte: str) -> str | None:
    """Extrait le légume depuis le texte si Groq a retourné culture=null."""
    t = texte.lower()
    # Chercher d'abord les expressions multi-mots (plus spécifiques)
    for cult in sorted(CULTURES_CONNUES, key=len, reverse=True):
        if cult in t:
            # Retourner au singulier
            return cult.rstrip("s") if cult.endswith("s") and len(cult) > 4 else cult
    return None

def _infer_date(texte: str) -> str | None:
    """Extrait la date depuis le texte si Groq a retourné date=null."""
    t = texte.lower()
    for mot, fn in TEMPORAL_MAP.items():
        if mot in t:
            return fn()
    return None


def _normalize_items(items: list, texte_original: str = "") -> list:
    """
    Normalise la réponse Groq :
    1. Si action=null → inférence depuis le texte original
    2. Si culture/quantite sont des listes → explosion en objets séparés
    """
    normalized = []
    for item in items:
        # ── Inférence des champs null depuis le texte original ───────────────
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
                # N'inférer la date que si le texte source contient un mot temporel explicite
                if texte_original and any(m in texte_original.lower() for m in TEMPORAL_MAP):
                    inferred = _infer_date(texte_original)
                    if inferred:
                        item["date"] = inferred
                        log.info(f"🔧 DATE INFÉRÉE    : '{inferred}'")

        culture  = item.get("culture")
        quantite = item.get("quantite")

        # Cas normal : culture est une string → pas de transformation
        if not isinstance(culture, list):
            normalized.append(item)
            continue

        # Cas Groq défaillant : culture est une liste
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
        [KeyboardButton("✏️ Corriger")],
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

# ── États conversation ───────────────────────────────────────────────────────────
WAITING_ASK = 1


# ══════════════════════════════════════════════════════════════════════════════
# HANDLERS PRINCIPAUX
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Message de bienvenue."""
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
        f"Ou utilisez les boutons ci-dessous.\n"
        f"📖 Tapez /help pour l'aide en ligne.",
        parse_mode="Markdown",
        reply_markup=MENU_KEYBOARD
    )


# ──────────────────────────────────────────────────────────────────────────────
# [US_Aide_contextuelle_par_commande] Textes d'aide contextuels par mot-clé
# ──────────────────────────────────────────────────────────────────────────────

_HELP_PARCELLE = (
    "📍 *Aide — Parcelles*\n"
    "Gérer et consulter vos parcelles du potager.\n\n"
    "*── Plan d'occupation ──*\n"
    "• Vue globale de toutes les parcelles\n"
    "  → /plan\n"
    "  → _\"plan du potager\"_\n"
    "• Vue détaillée d'une parcelle\n"
    "  → /plan nord\n"
    "  → _\"plan parcelle nord\"_\n"
    "  → _\"qu'est-ce qui pousse en nord ?\"_\n\n"
    "*── Gestion des parcelles ──*\n"
    "• Lister toutes les parcelles connues\n"
    "  → /parcelle lister\n"
    "  → /parcelles\n"
    "• Créer une nouvelle parcelle\n"
    "  → /parcelle ajouter nord\n"
    "  → /parcelle ajouter nord sud 12.5\n"
    "  _(nom · exposition · superficie en m²)_\n"
    "• Modifier les métadonnées d'une parcelle\n"
    "  → /parcelle modifier nord exposition=sud\n"
    "  → /parcelle modifier nord superficie=8.5\n"
    "  → /parcelle modifier nord exposition=sud superficie=8.5\n"
    "  _Paramètres : exposition · superficie · ordre_\n"
    "• Renommer une parcelle (propagation sur tout l'historique)\n"
    "  → /parcelle renommer sud carré-sud\n\n"
    "💡 _Noms de parcelle insensibles à la casse.\n"
    "   Les doublons sont détectés automatiquement._"
)

_HELP_SEMIS = (
    "🌱 *Aide — Semis*\n"
    "Enregistrer vos semis en pépinière ou en pleine terre.\n\n"
    "*Actions disponibles :*\n"
    "• Semis en pépinière\n"
    "  → _\"semis tomates variété Saint-Pierre le 5 mars\"_\n"
    "  → _\"j'ai semé 30 graines de basilic en plateau\"_\n"
    "• Semis en pleine terre\n"
    "  → _\"semis direct carottes en parcelle B2\"_\n"
    "  → _\"semis radis pleine terre parcelle A3 le 8 avril\"_\n"
    "• Consulter les semis en cours\n"
    "  → _\"liste de mes semis\"_\n"
    "  → _\"quels semis sont en cours ?\"_\n\n"
    "💡 _Précisez toujours : culture · variété (optionnel) · date · lieu_"
)

_HELP_GODET = (
    "🪴 *Aide — Mise en godet*\n"
    "Suivre le repiquage des plants de pépinière en godet.\n\n"
    "*Actions disponibles :*\n"
    "• Enregistrer une mise en godet\n"
    "  → _\"mise en godet tomates Saint-Pierre 20 plants\"_\n"
    "  → _\"repiquer 15 plants de poivron en godet le 10 mars\"_\n"
    "• Consulter les godets en attente\n"
    "  → _\"liste des godets\"_\n"
    "  → _\"quels plants sont en godet ?\"_\n\n"
    "💡 _La mise en godet est l'étape entre le semis plateau\n"
    "   et la plantation en parcelle._"
)

_HELP_RECOLTE = (
    "🧺 *Aide — Récoltes*\n"
    "Enregistrer vos récoltes ponctuelles ou finales.\n\n"
    "*Actions disponibles :*\n"
    "• Récolte ponctuelle (culture continue)\n"
    "  → _\"récolté 800g de tomates en A1\"_\n"
    "  → _\"cueilli 3 courgettes parcelle B2 aujourd'hui\"_\n"
    "• Récolte finale / clôture de culture\n"
    "  → _\"récolte finale haricots parcelle A3\"_\n"
    "  → _\"dernière récolte courgettes B2, culture terminée\"_\n"
    "• Récolte de graines\n"
    "  → _\"récolte graines tomates Saint-Pierre 15g\"_\n"
    "  → _\"mis de côté graines courge pour semis prochain\"_\n"
    "• Consulter l'historique\n"
    "  → _\"historique récoltes\"_\n"
    "  → _\"mes récoltes du mois de mars\"_"
)

_HELP_STOCK = (
    "📦 *Aide — Stock*\n"
    "Suivre vos stocks de semences et intrants.\n\n"
    "*Actions disponibles :*\n"
    "• Consulter le stock\n"
    "  → _\"stock tomates\"_\n"
    "  → _\"combien de graines de basilic il me reste ?\"_\n"
    "• Ajouter au stock\n"
    "  → _\"ajout stock carottes Nantaise 50g\"_\n"
    "  → _\"reçu 1 sachet poivron Corno di Toro\"_\n"
    "• Déduire du stock (automatique après semis)\n"
    "  → _Le stock est mis à jour automatiquement_\n"
    "  → _à chaque semis enregistré._\n"
    "• Alertes stock faible\n"
    "  → _Le bot signale automatiquement si un stock_\n"
    "  → _passe sous le seuil critique._"
)

_HELP_STATS = (
    "📊 *Aide — Statistiques*\n"
    "Consulter les bilans de votre potager.\n\n"
    "*Actions disponibles :*\n"
    "• Statistiques générales\n"
    "  → /stats\n"
    "  → _\"bilan du potager\"_\n"
    "• Stats par culture\n"
    "  → _\"stats tomates\"_\n"
    "  → _\"bilan courgettes cette saison\"_\n"
    "• Stats par parcelle\n"
    "  → _\"stats parcelle A1\"_\n"
    "  → _\"bilan rotation parcelle B2\"_\n"
    "• Synthèse des semis\n"
    "  → _\"synthèse semis\"_\n"
    "  → _\"récapitulatif de mes semis\"_\n"
    "• Bilan de rotation\n"
    "  → _\"rotation des cultures\"_\n"
    "  → _\"quelles familles ont occupé chaque parcelle ?\"_"
)

_HELP_MOTS_CLES = "parcelle · semis · godet · recolte · stock · stats"

_HELP_CONTEXTUEL: dict[str, str] = {
    "parcelle":  _HELP_PARCELLE,
    "parcelles": _HELP_PARCELLE,
    "plan":      _HELP_PARCELLE,
    "semis":     _HELP_SEMIS,
    "godet":     _HELP_GODET,
    "godets":    _HELP_GODET,
    "recolte":   _HELP_RECOLTE,
    "recoltes":  _HELP_RECOLTE,
    "stock":     _HELP_STOCK,
    "stocks":    _HELP_STOCK,
    "stats":     _HELP_STATS,
    "statistiques": _HELP_STATS,
}


async def cmd_help(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """[US_Aide_contextuelle_par_commande] Aide générale ou ciblée via /help [mot-clé]."""
    from unidecode import unidecode as _uni

    mot_cle = (ctx.args[0].lower().strip() if ctx.args else None)
    if mot_cle:
        mot_cle = _uni(mot_cle)  # insensible aux accents

    if mot_cle and mot_cle in _HELP_CONTEXTUEL:
        await update.message.reply_text(
            _HELP_CONTEXTUEL[mot_cle], parse_mode="Markdown"
        )
        return

    if mot_cle and mot_cle not in _HELP_CONTEXTUEL:
        await update.message.reply_text(
            f'❓ Mot-clé \"*{mot_cle}*\" non reconnu.\n\n'
            f"Mots-clés disponibles :\n  {_HELP_MOTS_CLES}\n\n"
            f"Exemple : /help parcelle",
            parse_mode="Markdown",
        )
        return

    # ── Aide générale (comportement existant / CA5) ────────────────────────────
    texte = (
        "🌿 *AIDE — Assistant Potager*\n"
        "━━━━━━━━━━━━━━━━━━━━\n\n"
        "*📝 Enregistrer une action*\n"
        "Parlez ou écrivez naturellement :\n"
        "• _\"Récolté 2 kg de tomates cerise\"_\n"
        "• _\"Planté 6 poivrons en 2 rangs\"_\n"
        "• _\"Semé carottes Nantaise rang 4\"_\n"
        "• _\"Arrosé les courgettes 30 min\"_\n"
        "• _\"Traité rosiers au savon noir\"_\n"
        "• _\"Observation : pucerons sur fèves\"_\n\n"
        "*Actions reconnues :*\n"
        "récolte · plantation · semis · repiquage\n"
        "arrosage · paillage · traitement\n"
        "désherbage · taille · tuteurage\n"
        "amendement · protection · observation\n\n"
        "*Dates :* hier · avant-hier · lundi… \"le 5 mars\"\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*⌨️ Commandes*\n"
        "/start — Menu principal\n"
        "/plan — Plan d'occupation des parcelles\n"
        "/parcelle ajouter [nom] — Créer une parcelle\n"
        "/stats — Statistiques saison\n"
        "/historique — 10 derniers événements\n"
        "/ask — Question analytique\n"
        "/corriger — Modifier un événement\n"
        "/meteo — Météo + conseil potager\n"
        "/tts\\_on · /tts\\_off — Vocal on/off\n"
        "/help — Cette aide\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*💡 Aide ciblée par domaine*\n"
        f"  {_HELP_MOTS_CLES}\n"
        "Exemple : /help parcelle\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "*🔍 Exemples de questions*\n"
        "• _\"Combien de kg de tomates récoltés ?\"_\n"
        "• _\"Quand ai-je planté les courgettes ?\"_\n"
        "• _\"Bilan de ma saison de carottes\"_\n"
        "• _\"Dernier arrosage des poivrons\"_\n\n"
        "💡 _Plusieurs actions : séparez par un retour à la ligne._"
    )
    await update.message.reply_text(texte, parse_mode="Markdown")


async def handle_voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Message vocal → transcription Groq Whisper → parsing → PostgreSQL."""
    msg = await update.message.reply_text("🎤 *Transcription en cours...*", parse_mode="Markdown")

    # ── 1. Télécharger le fichier audio ────────────────────────────────────────
    voice_file = await update.message.voice.get_file()

    with tempfile.NamedTemporaryFile(suffix=".ogg", delete=False) as tmp:
        tmp_path = tmp.name
        await voice_file.download_to_drive(tmp_path)

    # ── 2. Transcrire via Groq Whisper ──────────────────────────────────────────
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

    # ── 3. Modes correction actifs : bypass intent classification ──────────────
    # Quand on est en pleine conversation de correction, on ne reclassifie pas —
    # le texte est une réponse dans un flux déjà engagé.
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

    # ── 4. Mode ask actif : bypass aussi ──────────────────────────────────────
    if mode == 'ask':
        ctx.user_data['mode'] = None
        await _ask_question(update, texte)
        return

    # ── 5. Classification de l'intention via Groq ──────────────────────────────
    intent = classify_intent(texte)

    # ── 6. Routage selon intent ────────────────────────────────────────────────
    if intent == "STATS":
        await msg.edit_text("📊 *Statistiques*", parse_mode="Markdown")
        # [US_Stats_detail_par_variete / CA8] Détecter "stats <culture>" vocal
        culture_vocal = _extract_stats_culture(texte)
        if culture_vocal:
            log.info(f"📊 STATS VOCAL VARIETE : culture='{culture_vocal}'")
            ctx.args = [culture_vocal]
        else:
            ctx.args = []
        await cmd_stats(update, ctx)
        return
    if intent == "HISTORIQUE":
        await msg.edit_text("📋 *Historique*", parse_mode="Markdown")
        await cmd_historique(update, ctx)
        return
    # [US_Plan_occupation_parcelles / CA9] Routage vocal PLAN
    if intent == "PLAN":
        await msg.edit_text("🗺 *Plan du potager...*", parse_mode="Markdown")
        parcelle_vocal = _extract_plan_parcelle(texte)
        if parcelle_vocal:
            log.info(f"🗺 PLAN VOCAL PARCELLE : parcelle='{parcelle_vocal}'")
            ctx.args = [parcelle_vocal]
        else:
            ctx.args = []
        await cmd_plan(update, ctx)
        return
    if intent == "INTERROGER":
        # Si le texte est déjà une question complète (>4 mots), la traiter directement
        # Sinon, demander de formuler la question (mot court type "interroger", "question"...)
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

    # intent == "ACTION" : enregistrer comme action potager
    await _parse_and_save(update, texte, msg)


# Mots déclencheurs de QUESTION analytique (début de phrase)
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

# Verbes d'action potager — ne jamais les traiter comme des questions
ACTION_VERBS = (
    "arros", "semé", "semer", "planté", "planter", "récolté", "récolter",
    "cueilli", "cueillir", "ramassé", "ramasser", "repiqué", "repiquer",
    "traité", "traiter", "désherbé", "désherber", "paillé", "pailler",
    "taillé", "tailler", "tuteurer", "tuteuré", "fertilisé", "fertiliser",
    "observé", "observer", "constaté", "constater", "mis en", "mis ",
    "posé", "appliqué", "installé", "sorti",
    "godet", "mis en godet", "mise en godet",
)

def _is_question(texte: str) -> bool:
    """Retourne True si la phrase ressemble à une question analytique."""
    t = texte.lower().strip()
    # Si ça commence par un verbe d'action → jamais une question
    if t.startswith(ACTION_VERBS):
        return False
    return t.startswith(QUESTION_STARTERS) or t.endswith("?")

# Mots-clés de navigation reconnus (avec ou sans émoji, insensible à la casse)
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

# ── Intent classification via Groq ─────────────────────────────────────────
# Intents possibles retournés par classify_intent()
INTENTS = {
    "STATS",        # statistiques, bilan, résumé
    "HISTORIQUE",   # journal, historique, derniers événements
    "INTERROGER",   # question, analyser, demander
    "CORRIGER",     # corriger, modifier, changer un enregistrement
    "SUPPRIMER",    # supprimer, effacer, annuler le dernier
    "MENU",         # retour accueil, menu
    "NOUVELLE",     # nouvelle action, autre chose
    "ACTION",       # action potager à enregistrer (récolte, semis, arrosage...)
    "PLAN",         # [US_Plan_occupation_parcelles / CA9] plan d'occupation parcelles
}

_CLASSIFY_PROMPT = """Tu es un assistant potager. L'utilisateur t'envoie un message (transcrit vocalement ou tapé).
Classe ce message dans UNE SEULE catégorie parmi :
- STATS       : veut voir des statistiques, bilan, résumé, chiffres
- HISTORIQUE  : veut voir l'historique, le journal, les derniers événements
- INTERROGER  : pose une question ou demande d'AFFICHER des données existantes (combien, quand, quel, afficher, montrer, liste, voir, consulter...)
- CORRIGER    : veut corriger, modifier, changer un enregistrement existant
- SUPPRIMER   : veut supprimer ou effacer un enregistrement
- MENU        : veut revenir au menu, accueil, annuler
- NOUVELLE    : veut saisir une nouvelle action (après une autre)
- ACTION      : décrit une action potager réellement RÉALISÉE à enregistrer (récolte, semis, plantation, arrosage, paillage, traitement, observation, fertilisation, taille, tuteurage, repiquage, désherbage, perte, mise_en_godet)
- PLAN        : veut voir le plan d'occupation des parcelles (plan du potager, plan parcelle X)

RÈGLE IMPORTANTE : si le message contient "afficher", "montrer", "voir", "liste", "consulter", "quand", "combien", "quel" → c'est INTERROGER ou HISTORIQUE, jamais ACTION.

Exemples :
- "afficher les récoltes de carotte variété nantaise" → INTERROGER
- "afficher mes semis de radis" → INTERROGER
- "voir l'historique des arrosages courgette" → HISTORIQUE
- "combien ai-je récolté de tomates" → INTERROGER
- "j'ai récolté 2 kg de tomates" → ACTION
- "récolte 500g de carotte nantaise hier" → ACTION
- "semis de radis 50 graines" → ACTION
- "quand ai-je semé les carottes" → INTERROGER
- "plan du potager" → PLAN
- "plan parcelle nord" → PLAN
- "montre-moi le plan" → PLAN

Message : "{texte}"

Réponds avec UN SEUL MOT en majuscules parmi : STATS, HISTORIQUE, INTERROGER, CORRIGER, SUPPRIMER, MENU, NOUVELLE, ACTION, PLAN
Réponse :"""

def classify_intent(texte: str) -> str:
    """Utilise Groq pour classer l'intention du message en un intent canonique."""
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
        return "ACTION"  # fallback sûr


def _extract_stats_culture(texte: str) -> str | None:
    """
    [US_Stats_detail_par_variete / CA8]
    Extrait la culture depuis une phrase vocale type 'stats tomate'.

    Exemples reconnus :
      "stats tomate" → "tomate"
      "statistiques de la tomate" → "tomate"
      "stats" seul → None
    """
    import re
    m = re.match(
        r'^(?:stats?|statistiques?)\s+(?:de\s+(?:la\s+|les?\s+|des?\s+)?|du\s+)?(\w+)$',
        texte.lower().strip(),
    )
    return m.group(1) if m else None


def _extract_plan_parcelle(texte: str) -> str | None:
    """
    [US_Plan_occupation_parcelles / CA9]
    Extrait le nom de parcelle depuis une phrase vocale type 'plan parcelle nord'.

    Exemples reconnus :
      "plan du potager"     → None  (vue globale)
      "plan parcelle nord"  → "nord"
      "plan nord"           → "nord"
    """
    m = re.search(
        r'plan\s+(?:parcelle\s+)?(\w+)',
        texte.lower().strip(),
    )
    if m:
        mot = m.group(1)
        # Ignorer les mots génériques qui ne sont pas des noms de parcelle
        if mot in {"du", "des", "le", "la", "les", "potager", "jardin"}:
            return None
        return mot
    return None


async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Message texte → parsing direct ou commande de navigation."""
    texte_raw = update.message.text.strip()
    texte     = texte_raw.lower()  # comparaison insensible à la casse
    log.info(f"💬 MESSAGE TEXTE  : {texte_raw}")

    # Réinitialiser le mode SAUF si on est en plein flux de correction ou en attente de question
    MODES_CORRECTION = {'corr_select', 'corr_apply', 'corr_search', 'corr_confirm_delete', 'corr_confirm', 'ask', 'parcelle_confirm'}
    if ctx.user_data.get('mode') not in MODES_CORRECTION:
        ctx.user_data['mode'] = None

    # Boutons de navigation (avec ou sans émoji, texte libre accepté)
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

    # ── PRIORITÉ 1 : modes correction actifs
    mode = ctx.user_data.get('mode')
    MODES_CORR = {'corr_search','corr_select','corr_apply','corr_confirm','corr_confirm_delete'}

    # Si l'utilisateur tape "corriger" ou un mot-clé NAV en plein milieu d'une correction
    # → reset complet et redémarrage propre (évite les états bloqués)
    if mode in MODES_CORR and (
        texte in NAV_CORRIGER
        or texte in NAV_MENU
        or texte in NAV_STATS
        or texte in NAV_HISTORIQUE
        or texte in NAV_INTERROGER
    ):
        log.info(f"🔄 RESET CORRECTION : mode={mode}, texte='{texte}' → nettoyage")
        for k in ['mode','corr_event_id','corr_candidates','corr_last_id',
                  'corr_pending','corr_event_actuel']:
            ctx.user_data.pop(k, None)
        # Laisser le flux normal gérer la commande (pas de return ici)
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

    # ── PRIORITÉ 2 : mode question analytique actif
    if mode == 'ask':
        ctx.user_data['mode'] = None
        log.info(f"❓ MODE ASK        : reroutage → _ask_question")
        await _ask_question(update, texte_raw)
        return

    # ── PRIORITÉ 2b : confirmation parcelle en attente [US_Plan_occupation_parcelles / CA12, CA13]
    if mode == 'parcelle_confirm':
        pending = ctx.user_data.get('parcelle_pending', {})
        ctx.user_data.pop('parcelle_pending', None)
        ctx.user_data['mode'] = None
        reponse = texte.strip().lower()
        if reponse in {"oui", "o", "yes", "y"}:
            nom = pending.get("nom", "")
            if nom:
                try:
                    db = SessionLocal()
                    try:
                        new_p = create_parcelle(
                            db, nom,
                            exposition=pending.get("exposition"),
                            superficie_m2=pending.get("superficie_m2"),
                        )
                        log.info(f"[US_Plan_occupation_parcelles] Parcelle confirmée : {new_p.nom!r}")
                        details = []
                        if new_p.exposition:
                            details.append(f"exposition {new_p.exposition}")
                        if new_p.superficie_m2 is not None:
                            details.append(f"{new_p.superficie_m2} m²")
                        detail_str = f" ({', '.join(details)})" if details else ""
                        await update.message.reply_text(
                            f"✅ Parcelle *{new_p.nom.upper()}* créée{detail_str}.",
                            parse_mode="Markdown",
                        )
                    finally:
                        db.close()
                except ValueError as e:
                    await update.message.reply_text(f"❌ {e}", parse_mode="Markdown")
            return
        else:
            await update.message.reply_text("↩️ Création annulée.", parse_mode="Markdown")
            return

    # ── PRIORITÉ 3 : mots-clés correction/suppression
    if texte in NAV_SUPPRIMER or any(texte.startswith(k) for k in ["supprimer", "effacer", "annuler"]):
        await _corr_annuler_dernier(update, ctx)
        return
    if texte in NAV_CORRIGER or any(texte.startswith(k) for k in ["corriger", "modifier"]):
        # Nettoyer tout contexte correction résiduel avant de démarrer
        for k in ['mode','corr_event_id','corr_candidates','corr_last_id',
                  'corr_pending','corr_event_actuel']:
            ctx.user_data.pop(k, None)
        await _corr_start(update, ctx)
        return

    # ── PRIORITÉ 4 : détection automatique question
    if _is_question(texte_raw):
        log.info(f"❓ QUESTION AUTO   : détectée → reroutage vers _ask_question")
        await _ask_question(update, texte_raw)
        return

    # Sinon : parser comme action(s) potager
    # Si multi-lignes → traiter chaque ligne séparément
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
    """Traite chaque ligne séparément → chaque événement a son propre texte_original et sa propre date."""
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
        if not (first.get("action") or first.get("culture") or first.get("quantite")):
            log.warning(f"  [{i}] JSON sans action ni culture — ignoré : {ligne}")
            continue

        db = SessionLocal()
        try:
            for parsed in items:
                event = Evenement(
                    type_action       = normalize_action(parsed.get("action")),
                    culture           = parsed.get("culture"),
                    variete           = parsed.get("variete"),
                    quantite          = _to_float(parsed.get("quantite")),
                    unite             = parsed.get("unite"),
                    parcelle          = parsed.get("parcelle"),
                    rang              = _to_int(parsed.get("rang")),
                    duree             = _to_int(parsed.get("duree_minutes")),
                    traitement        = parsed.get("traitement"),
                    commentaire       = parsed.get("commentaire"),
                    texte_original    = ligne,   # ← texte propre à CETTE ligne
                    date              = parse_date(parsed.get("date")),
                    nb_graines_semees = _to_int(parsed.get("nb_graines_semees")),
                    nb_plants_godets  = _to_int(parsed.get("nb_plants_godets")),
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

    # Récapitulatif global
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
        from sqlalchemy import func
        nb = refreshed.query(Evenement).count()
        # pas de reply ici, juste log
        log.info(f"📦 TOTAL BASE     : {nb} événements")
    finally:
        refreshed.close()


# ── PARSING + SAUVEGARDE ────────────────────────────────────────────────────────
async def _parse_and_save(update: Update, texte: str, msg=None):
    """Parse le texte → liste d'événements → PostgreSQL → récapitulatif."""
    try:
        items = parse_commande(texte)   # retourne toujours une liste
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

    # Cas JSON sans action ni culture → phrase non reconnue comme action potager
    first = items[0] if items else {}
    if not (first.get("action") or first.get("culture") or first.get("quantite")):
        log.warning("⚠️  JSON SANS ACTION NI CULTURE : phrase non reconnue, pas de sauvegarde")
        await update.message.reply_text(
            "🤔 Je n'ai pas compris cette action.\n\n"
            "• Pour enregistrer : _\"Récolté 2 kg de tomates hier\"_\n"
            "• Pour interroger  : _\"Combien de tomates ai-je récolté ?\"_",
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        return

    # Cas ambiguïté rang/quantité détectée par Groq
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

    # Sauvegarde PostgreSQL (1 ou plusieurs événements)
    db = SessionLocal()
    saved_items = []
    try:
        for parsed in items:
            # ── Résolution FK parcelle ────────────────────────────────────────
            nom_parcelle = parsed.get("parcelle")
            parcelle_obj = None
            if nom_parcelle:
                parcelle_obj = resolve_parcelle(db, nom_parcelle)
                if parcelle_obj is None:
                    log.warning(f"⚠️ PARCELLE INCONNUE : {nom_parcelle!r} — sauvegarde bloquée")
                    err_msg = (
                        f"❌ La parcelle *{nom_parcelle}* n'existe pas dans votre potager.\n\n"
                        f"Créez-la d'abord avec : `/parcelle ajouter {nom_parcelle}`"
                    )
                    if msg:  await msg.edit_text(err_msg, parse_mode="Markdown")
                    else:    await update.message.reply_text(err_msg, parse_mode="Markdown", reply_markup=MENU_KEYBOARD)
                    return
            event = Evenement(
                type_action       = normalize_action(parsed.get("action")),
                culture           = parsed.get("culture"),
                variete           = parsed.get("variete"),
                quantite          = _to_float(parsed.get("quantite")),
                unite             = parsed.get("unite"),
                parcelle          = parcelle_obj.nom if parcelle_obj else None,
                parcelle_id       = parcelle_obj.id  if parcelle_obj else None,
                rang              = _to_int(parsed.get("rang")),
                duree             = _to_int(parsed.get("duree_minutes")),
                traitement        = parsed.get("traitement"),
                commentaire       = parsed.get("commentaire"),
                texte_original    = texte,
                date              = parse_date(parsed.get("date")),
                nb_graines_semees = _to_int(parsed.get("nb_graines_semees")),
                nb_plants_godets  = _to_int(parsed.get("nb_plants_godets")),
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            log.info(f"💾 DB SAVE        : id={event.id} | action={event.type_action} | culture={event.culture} | qte={event.quantite} {event.unite or ''} | rang={event.rang} | parcelle={event.parcelle} (id={event.parcelle_id}) | date={event.date}")
            saved_items.append((parsed, event.id))
    except Exception as e:
        db.rollback()
        await update.message.reply_text(f"❌ Erreur base de données : {e}")
        return
    finally:
        db.close()

    # Récapitulatif
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

    # ── Synthèse vocale du récapitulatif ──────────────────────────────────────
    if len(saved_items) == 1:
        parsed, _ = saved_items[0]
        await send_voice_reply(update, _build_recap_tts(parsed))


def _build_recap_tts(p: dict) -> str:
    """
    Version vocale du récapitulatif — phrase naturelle sans Markdown ni émoji.
    Ex : "Récolte enregistrée. 3 kg de tomates cerise, parcelle nord, le 2026-03-11."
    """
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
    """Construit le message de récapitulatif."""
    lines = ["✅ *C'est noté !* _(ID #%d)_\n" % event_id]

    # Cas spécial mise_en_godet : affichage taux de réussite germination
    action_norm = normalize_action(p.get("action")) or p.get("action") or ""
    if action_norm == "mise_en_godet":
        nb_g = p.get("nb_graines_semees")
        nb_p = p.get("nb_plants_godets")
        taux_str = ""
        if nb_g and nb_p:
            taux = round(nb_p / nb_g * 100)
            taux_str = f" \u2192 *{taux}% de réussite*"
        lines.append(f"🌱 Action : *mise en godet* (pépinière — hors stock)")
        if p.get("culture"):  lines.append(f"🥬 Culture : *{p['culture']}*")
        if p.get("variete"): lines.append(f"🏷 Variété : *{p['variete']}*")
        if nb_g:             lines.append(f"🌱 Graines semées : *{nb_g}*")
        if nb_p:             lines.append(f"🌱 Plants obtenus : *{nb_p}*{taux_str}")
        if p.get("parcelle"): lines.append(f"📍 Parcelle : *{p['parcelle']}*")
        if p.get("date"):    lines.append(f"📅 Date : *{p['date']}*")
        if p.get("commentaire"): lines.append(f"📝 Note : *{p['commentaire']}*")
        lines.append("\n_Que voulez-vous faire ensuite ?_")
        return "\n".join(lines)

    # Calcul quantité totale si rang présent
    qte_str  = None
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
    """Interroge l'historique via Groq."""
    log.info(f"🔍 QUESTION       : {question}")
    msg = await update.message.reply_text("🔍 *Analyse de vos données...*", parse_mode="Markdown")
    db  = SessionLocal()
    try:
        contexte = build_question_context(db, question)
        if not contexte or contexte == "[]":
            await msg.edit_text("📭 Aucune donnée pertinente pour cette question.")
            return

        log.info(f"🤖 LLM | Appel à Groq pour question analytique: '{question}' (contexte: {len(contexte)} chars)")
        reponse = repondre_question(question, contexte)
        log.info(f"💡 LLM | Réponse Groq reçue: {len(reponse)} caractères")

        log.info(f"💡 RÉPONSE GROQ   : {reponse[:200]}{'...' if len(reponse)>200 else ''}")
        # Pas de parse_mode sur la réponse Groq : elle peut contenir des caractères
        # spéciaux (apostrophes, tirets, parenthèses) qui cassent le parser Telegram
        try:
            await msg.edit_text(f"🔍 *Réponse :*\n\n{reponse}", parse_mode="Markdown")
        except Exception:
            # Fallback sans markdown si la réponse contient des caractères problématiques
            await msg.edit_text(f"🔍 Réponse :\n\n{reponse}")
        await update.message.reply_text(
            "_Autre question ou action ?_",
            parse_mode="Markdown",
            reply_markup=AFTER_RECORD_KEYBOARD
        )
        # ── Synthèse vocale de la réponse analytique ──────────────────────────
        await send_voice_reply(update, reponse)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}", reply_markup=MENU_KEYBOARD)
    finally:
        db.close()


# ── COMMANDES ───────────────────────────────────────────────────────────────────

# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA1-CA7, CA9] Commande /plan
# ──────────────────────────────────────────────────────────────────────────────

# [US_Plan_occupation_parcelles / CA3] Seuils d'alerte par type d'organe (jours)
SEUIL_ALERTE = {"végétatif": 45, "reproducteur": 90}

# [US_Plan_occupation_parcelles] Emoji par type d'organe
_EMOJI_ORGANE = {"reproducteur": "🍅", "végétatif": "🥬"}
_EMOJI_INCONNU = "🌱"


async def cmd_plan(update, ctx) -> None:
    """
    /plan [parcelle] — Plan d'occupation du potager.

    [CA1] Vue globale : cultures actives par parcelle avec variété et nb plants
    [CA2] Âge J+ depuis la première plantation
    [CA3] Alerte ⚠️ si âge > seuil typique (végétatif ≥ 45j, reproducteur ≥ 90j)
    [CA4] Parcelles libres affichées 🟢 [NOM] — Libre
    [CA5] /plan nord filtre sur la parcelle "nord" (insensible à la casse)
    [CA6] Hint en pied de message
    [CA7] Cultures sans parcelle sous 📍 Non localisé
    """
    from datetime import date as date_type
    db = SessionLocal()
    try:
        occupation = calcul_occupation_parcelles(db)
        parcelles_bdd = get_all_parcelles(db)

        # ── Filtre parcelle spécifique (CA5) ──────────────────────────────────
        filtre_arg = (ctx.args[0].strip().lower() if ctx.args else None)

        if filtre_arg:
            # Vue détaillée d'une parcelle
            cles_norm = {
                (k.strip().lower() if k else None): k
                for k in occupation
            }
            cle_originale = cles_norm.get(filtre_arg)

            if cle_originale is None and cle_originale not in occupation:
                # Chercher dans toutes les clés normalisées
                for k in occupation:
                    if k and k.strip().lower() == filtre_arg:
                        cle_originale = k
                        break

            cultures = occupation.get(cle_originale, [])
            if not cultures:
                await update.message.reply_text(
                    f"Aucune culture active sur la parcelle *{filtre_arg.upper()}*.",
                    parse_mode="Markdown",
                )
                return

            nom_affiche = (cle_originale or filtre_arg).upper()
            lignes = [f"📍 *{nom_affiche}* — Plan détaillé\n"]
            for c in sorted(cultures, key=lambda x: x["culture"]):
                alerte = _alerte_recolte(c["type_organe"], c["age_jours"])
                emoji = _EMOJI_ORGANE.get(c["type_organe"], _EMOJI_INCONNU)
                var = f" {c['variete']}" if c["variete"] else ""
                nb = int(c["nb_plants"])
                unite = c["unite"] or "plants"
                date_str = (
                    c["date_plantation"].strftime("%d %b").lstrip("0")
                    if c["date_plantation"] else "?"
                )
                lignes.append(
                    f"{emoji} *{c['culture']}{var}*\n"
                    f"  {nb} {unite} actifs · plantés le {date_str} (J+{c['age_jours']})"
                )
                if c["type_organe"]:
                    lignes.append(f"  Type : {c['type_organe']}")
                if alerte:
                    seuil = SEUIL_ALERTE.get(c["type_organe"], 0)
                    lignes.append(f"  ⚠️ Récolte imminente ({c['type_organe']} > {seuil} j)")

            lignes.append(
                f"\n_Historique de rotation : \"rotation parcelle {filtre_arg}\"_"
            )
            await update.message.reply_text("\n".join(lignes), parse_mode="Markdown")
            await send_voice_reply(update, f"Détail de la parcelle {filtre_arg}")
            return

        # ── Vue globale ────────────────────────────────────────────────────────
        today = date_type.today()
        date_str = today.strftime("%d %b %Y").lstrip("0") if hasattr(today, "strftime") else str(today)

        lignes = [f"📋 *Plan d'occupation — {date_str}*\n"]

        # Parcelles connues en BDD → ordre défini
        noms_bdd = {p.nom.strip().lower(): p.nom for p in parcelles_bdd}
        affichees: set = set()

        def _bloc_parcelle(nom_cle, cultures_liste: list) -> list:
            """Formate le bloc d'une parcelle avec ses cultures."""
            bloc = []
            nom_affiche = (nom_cle or "").upper()
            nb = len(cultures_liste)
            bloc.append(f"📍 *{nom_affiche}* · {nb} culture{'s' if nb > 1 else ''} active{'s' if nb > 1 else ''}")
            for c in sorted(cultures_liste, key=lambda x: x["culture"]):
                emoji = _EMOJI_ORGANE.get(c["type_organe"], _EMOJI_INCONNU)
                var = f" {c['variete']}" if c["variete"] else ""
                nb_plants = int(c["nb_plants"])
                unite = c["unite"] or "plants"
                alerte = _alerte_recolte(c["type_organe"], c["age_jours"])
                alerte_str = " ⚠️ récolte imminente" if alerte else ""
                bloc.append(
                    f"  {emoji} {c['culture']}{var} — {nb_plants} {unite} · J+{c['age_jours']}{alerte_str}"
                )
            return bloc

        # Parcelles BDD actives (ordonnées)
        for p in parcelles_bdd:
            nom_key = p.nom.strip()
            nom_lower = nom_key.lower()
            affichees.add(nom_lower)

            cultures = occupation.get(nom_key, [])
            # Essai avec la clé telle quelle, puis en ignorant la casse
            if not cultures:
                for k in occupation:
                    if k and k.strip().lower() == nom_lower:
                        cultures = occupation[k]
                        break

            if cultures:
                lignes.extend(_bloc_parcelle(nom_key, cultures))
            else:
                # [CA4] Parcelle libre
                lignes.append(f"🟢 *{nom_key.upper()}* — Libre")
            lignes.append("")  # ligne vide entre parcelles

        # Parcelles dans occupation mais pas en BDD (non référencées)
        for nom_cle, cultures in occupation.items():
            if nom_cle is None:
                continue
            if nom_cle.strip().lower() not in affichees:
                lignes.extend(_bloc_parcelle(nom_cle, cultures))
                lignes.append("")

        # [CA7] Cultures sans parcelle
        sans_parcelle = occupation.get(None, [])
        if sans_parcelle:
            nb = len(sans_parcelle)
            lignes.append(f"📍 *Non localisé* · {nb} culture{'s' if nb > 1 else ''}")
            for c in sorted(sans_parcelle, key=lambda x: x["culture"]):
                emoji = _EMOJI_ORGANE.get(c["type_organe"], _EMOJI_INCONNU)
                var = f" {c['variete']}" if c["variete"] else ""
                nb_plants = int(c["nb_plants"])
                unite = c["unite"] or "plants"
                alerte = _alerte_recolte(c["type_organe"], c["age_jours"])
                alerte_str = " ⚠️ récolte imminente" if alerte else ""
                lignes.append(
                    f"  {emoji} {c['culture']}{var} — {nb_plants} {unite} · J+{c['age_jours']}{alerte_str}"
                )
            lignes.append("")

        # [CA6] Pied du message
        lignes.append("_Pour le détail : /plan [nom parcelle]_")
        lignes.append("_Historique de rotation : \"rotation parcelle X\"_")

        texte_final = "\n".join(lignes).strip()
        await update.message.reply_text(texte_final, parse_mode="Markdown")
        await send_voice_reply(update, "Plan du potager affiché")

    except Exception as e:
        log.error(f"[US_Plan_occupation_parcelles] cmd_plan erreur : {e}")
        await update.message.reply_text(f"❌ Erreur : {e}", reply_markup=MENU_KEYBOARD)
    finally:
        db.close()


def _alerte_recolte(type_organe: str | None, age_jours: int) -> bool:
    """[CA3] Retourne True si la culture dépasse le seuil d'alerte."""
    if type_organe and type_organe in SEUIL_ALERTE:
        return age_jours >= SEUIL_ALERTE[type_organe]
    return False


# ──────────────────────────────────────────────────────────────────────────────
# [US_Plan_occupation_parcelles / CA10, CA12, CA13] Commande /parcelle
# ──────────────────────────────────────────────────────────────────────────────

async def cmd_parcelle(update, ctx) -> None:
    """
    /parcelle <sous-commande> — Gestion des parcelles.

    Sous-commandes :
      ajouter [nom] [exposition] [superficie]  — créer une parcelle (CA10, CA12, CA13)
      modifier [nom] clé=valeur ...             — mettre à jour les métadonnées
      lister                                    — afficher toutes les parcelles
    """
    USAGE = (
        "*Usage :*\n"
        "  /parcelle ajouter [nom] [exposition] [superficie]\n"
        "  /parcelle modifier [nom] exposition=sud superficie=8.5\n"
        "  /parcelle renommer <ancien_nom> <nouveau_nom>\n"
        "  /parcelle lister\n\n"
        "Exemples :\n"
        "  /parcelle ajouter nord sud 12.5\n"
        "  /parcelle modifier nord exposition=sud superficie=8.5\n"
        "  /parcelle renommer sud carré-sud"
    )

    if not ctx.args:
        await update.message.reply_text(USAGE, parse_mode="Markdown")
        return

    sous_cmd = ctx.args[0].lower()

    # ── /parcelle lister ──────────────────────────────────────────────────────
    if sous_cmd == "lister":
        db = SessionLocal()
        try:
            parcelles = get_all_parcelles(db)
            if not parcelles:
                await update.message.reply_text(
                    "📋 Aucune parcelle enregistrée.\n"
                    "Créez-en une : /parcelle ajouter [nom]",
                    parse_mode="Markdown",
                )
                return
            lignes = [f"📋 *Parcelles enregistrées ({len(parcelles)})*\n"]
            for p in parcelles:
                details = []
                if p.exposition:
                    details.append(f"exposition {p.exposition}")
                if p.superficie_m2 is not None:
                    details.append(f"{p.superficie_m2} m²")
                detail_str = f" · {' · '.join(details)}" if details else ""
                lignes.append(f"📍 *{p.nom.upper()}*{detail_str}")
            lignes.append("\n_Ajouter : /parcelle ajouter [nom] [exposition] [superficie]_")
            lignes.append("_Modifier : /parcelle modifier [nom] clé=valeur_")
            await update.message.reply_text("\n".join(lignes), parse_mode="Markdown")
        except Exception as e:
            log.error(f"[US_Plan_occupation_parcelles] cmd_parcelle lister erreur : {e}")
            await update.message.reply_text(f"❌ Erreur : {e}")
        finally:
            db.close()
        return

    # ── /parcelle modifier [nom] clé=valeur ... ───────────────────────────────
    if sous_cmd == "modifier":
        if len(ctx.args) < 3:
            await update.message.reply_text(
                "❌ Usage : /parcelle modifier [nom] clé=valeur ...\n"
                "Exemple : /parcelle modifier nord exposition=sud superficie=8.5",
                parse_mode="Markdown",
            )
            return

        nom = ctx.args[1].strip()
        kwargs: dict = {}
        for token in ctx.args[2:]:
            if "=" in token:
                k, _, v = token.partition("=")
                kwargs[k.lower().strip()] = v.strip()
            else:
                await update.message.reply_text(
                    f"❌ Paramètre invalide : *{token}*\n"
                    "Format attendu : clé=valeur (ex : exposition=sud)",
                    parse_mode="Markdown",
                )
                return

        db = SessionLocal()
        try:
            parc, modifs = update_parcelle(db, nom, **kwargs)
            lignes = [f"✅ Parcelle *{parc.nom.upper()}* mise à jour :"]
            for m in modifs:
                lignes.append(f"  · {m}")
            await update.message.reply_text("\n".join(lignes), parse_mode="Markdown")
        except LookupError:
            all_p = get_all_parcelles(db)
            noms = ", ".join(p.nom.lower() for p in all_p) or "(aucune)"
            await update.message.reply_text(
                f"❌ Parcelle *{nom}* introuvable.\nParcelles connues : {noms}",
                parse_mode="Markdown",
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}", parse_mode="Markdown")
        except Exception as e:
            log.error(f"[US_Plan_occupation_parcelles] cmd_parcelle modifier erreur : {e}")
            await update.message.reply_text(f"❌ Erreur : {e}")
        finally:
            db.close()
        return

    # ── /parcelle ajouter [nom] [exposition] [superficie] ─────────────────────
    if sous_cmd == "ajouter":
        if len(ctx.args) < 2:
            await update.message.reply_text(
                "❌ Précisez le nom de la parcelle.\nExemple : /parcelle ajouter nord",
                parse_mode="Markdown",
            )
            return

        nom = ctx.args[1].strip()
        # Parsing optionnel : arg[2]=exposition (texte), arg[3]=superficie (float)
        exposition: str | None = None
        superficie_m2: float | None = None
        extra = ctx.args[2:]
        for tok in extra:
            try:
                superficie_m2 = float(tok.replace(",", "."))
            except ValueError:
                exposition = tok

        nom_normalise = normalize_parcelle_name(nom)

        db = SessionLocal()
        try:
            exact, proche = find_doublon(db, nom_normalise)

            # [CA10] Doublon exact
            if exact:
                log.info(f"[US_Plan_occupation_parcelles] Doublon exact : {nom!r} → {exact.nom!r}")
                await update.message.reply_text(
                    f"❌ La parcelle *{exact.nom.upper()}* existe déjà.\n"
                    "Utilisez /plan pour consulter les parcelles existantes.",
                    parse_mode="Markdown",
                )
                return

            # [CA12] Variante proche
            if proche:
                log.info(f"[US_Plan_occupation_parcelles] Variante proche : {nom!r} ≈ {proche.nom!r}")
                ctx.user_data['mode'] = 'parcelle_confirm'
                ctx.user_data['parcelle_pending'] = {
                    "nom": nom,
                    "exposition": exposition,
                    "superficie_m2": superficie_m2,
                }
                await update.message.reply_text(
                    f"⚠️ Une parcelle similaire existe : *{proche.nom.upper()}*.\n"
                    f"Confirmer la création de *{nom.upper()}* ? _(oui / non)_",
                    parse_mode="Markdown",
                )
                return

            # [CA13] Pas de doublon → récapitulatif + confirmation
            parcelles_existantes = get_all_parcelles(db)
            lignes = ["📋 *Parcelles existantes :*"]
            for p in parcelles_existantes:
                lignes.append(f"  · {p.nom.upper()}")
            if not parcelles_existantes:
                lignes.append("  _(aucune pour l'instant)_")

            detail_parts = []
            if exposition:
                detail_parts.append(f"exposition : {exposition}")
            if superficie_m2 is not None:
                detail_parts.append(f"superficie : {superficie_m2} m²")
            detail_conf = f" ({', '.join(detail_parts)})" if detail_parts else ""
            lignes.append(
                f"\n➕ Créer la parcelle *{nom.upper()}*{detail_conf} ? _(oui / non)_"
            )

            ctx.user_data['mode'] = 'parcelle_confirm'
            ctx.user_data['parcelle_pending'] = {
                "nom": nom,
                "exposition": exposition,
                "superficie_m2": superficie_m2,
            }
            await update.message.reply_text("\n".join(lignes), parse_mode="Markdown")

        except Exception as e:
            log.error(f"[US_Plan_occupation_parcelles] cmd_parcelle ajouter erreur : {e}")
            await update.message.reply_text(f"❌ Erreur : {e}", reply_markup=MENU_KEYBOARD)
        finally:
            db.close()
        return

    # ── /parcelle renommer <ancien> <nouveau> ─────────────────────────────────
    if sous_cmd == "renommer":
        if len(ctx.args) < 3:
            await update.message.reply_text(
                "❌ Usage : /parcelle renommer \\<ancien\\_nom\\> \\<nouveau\\_nom\\>\n"
                "Exemple : /parcelle renommer sud carré\\-sud",
                parse_mode="MarkdownV2",
            )
            return
        ancien = ctx.args[1].strip()
        nouveau = " ".join(ctx.args[2:]).strip()  # supporte noms avec espaces
        db = SessionLocal()
        try:
            parc, nb = rename_parcelle(db, ancien, nouveau)
            await update.message.reply_text(
                f"✅ Parcelle renommée : *{ancien}* → *{parc.nom}* "
                f"({nb} événement{'s' if nb > 1 else ''} mis à jour)",
                parse_mode="Markdown",
            )
        except LookupError:
            await update.message.reply_text(
                f"❌ Parcelle introuvable : *{ancien}*",
                parse_mode="Markdown",
            )
        except ValueError:
            await update.message.reply_text(
                "❌ Ce nom est déjà utilisé par une autre parcelle",
                parse_mode="Markdown",
            )
        except Exception as e:
            log.error(f"[US-006] cmd_parcelle renommer erreur : {e}")
            await update.message.reply_text(f"❌ Erreur : {e}")
        finally:
            db.close()
        return

    # Sous-commande inconnue
    await update.message.reply_text(USAGE, parse_mode="Markdown")


async def _cmd_parcelles_lister(update, ctx) -> None:
    """Alias /parcelles → /parcelle lister."""
    ctx.args = ["lister"]
    await cmd_parcelle(update, ctx)


async def cmd_stats(update, ctx):
    """
    /stats — Statistiques rapides du potager.

    [US-003 / CA1] Cultures végétatives : affiche "X plants récoltés"
    [US-003 / CA2] Cultures reproductrices : affiche "X plants actifs, Y kg cumulés"
    [US-003 / CA3] Deux sections distinctes : végétatif vs reproducteur
    [US-002 / CA3] Calcul stock différencié selon type_organe_recolte
    [US-002 / CA4] Champs stock_plants + rendement_total distincts via /stats API
    [US_Stats_detail_par_variete / CA1] Sans argument → synthèse générale inchangée
    [US_Stats_detail_par_variete / CA3] Avec argument → détail par variété de la culture
    """
    from utils.stock import (
        calcul_stock_cultures, format_stock_ligne_telegram, calcul_semis,
        calcul_stock_par_variete, format_variete_bloc_telegram,
    )

    # [US_Stats_detail_par_variete / CA7] Insensible à la casse
    culture_arg: str | None = None
    if ctx and getattr(ctx, "args", None):
        culture_arg = ctx.args[0].lower()

    db = SessionLocal()
    try:
        # ── [US_Stats_detail_par_variete / CA3] Mode détail variété ──────────
        if culture_arg:
            varietes = calcul_stock_par_variete(db, culture_arg)

            # [CA6] Culture inconnue
            if not varietes:
                texte_final = f"_Aucune donnée pour {culture_arg}_"
                try:
                    await update.message.reply_text(
                        texte_final, parse_mode="Markdown", reply_markup=MENU_KEYBOARD
                    )
                except Exception:
                    await update.message.reply_text(texte_final, reply_markup=MENU_KEYBOARD)
                return

            # Emoji selon type_organe du premier résultat
            type_organe = varietes[0]["type_organe"]
            emoji = "🍅" if type_organe == "reproducteur" else "🥬"
            culture_display = culture_arg.capitalize()

            lines_out = [f"{emoji} *{culture_display} — détail par variété*\n"]
            for v in varietes:
                lines_out.append(format_variete_bloc_telegram(v))
                lines_out.append("")  # ligne vide entre variétés

            lines_out.append("_Pour revenir à la synthèse : /stats_")
            texte_final = "\n".join(lines_out)

            log.info(f"📊 STATS VARIETE  : culture='{culture_arg}', {len(varietes)} variété(s)")
            try:
                await update.message.reply_text(
                    texte_final, parse_mode="Markdown", reply_markup=MENU_KEYBOARD
                )
            except Exception:
                await update.message.reply_text(
                    texte_final.replace("*", "").replace("_", ""),
                    reply_markup=MENU_KEYBOARD,
                )
            await send_voice_reply(update, texte_final)
            return

        # ── [US_Stats_detail_par_variete / CA1] Mode synthèse (comportement existant) ──
        lines_out = ["📊 *Statistiques potager*\n"]

        # ── [US-002] Calcul stock agronomique différencié ──────────────────────
        stocks = calcul_stock_cultures(db)

        if stocks:
            # [US-003 / CA3] Séparer végétatif et reproducteur
            veg_stocks  = {c: s for c, s in stocks.items() if not s.is_reproducteur}
            repr_stocks = {c: s for c, s in stocks.items() if s.is_reproducteur}

            # [US-003 / CA1] Section végétatif — "cultures à récolte unique"
            if veg_stocks:
                lines_out.append("🥬 *Cultures végétatives (récolte destructive) :*")
                for culture, s in veg_stocks.items():
                    lines_out.append("  " + format_stock_ligne_telegram(s))

            # [US-003 / CA2] Section reproducteur — "cultures productives continues"
            if repr_stocks:
                lines_out.append("\n🍅 *Cultures reproductrices (récolte continue) :*")
                for culture, s in repr_stocks.items():
                    lines_out.append("  " + format_stock_ligne_telegram(s))

        else:
            lines_out.append("_Aucune plantation enregistrée._")

        # ── Semis ──────────────────────────────────────────────────────────────
        semis = calcul_semis(db)
        if semis:
            veg_semis  = {c: s for c, s in semis.items() if s["type_organe"] != "reproducteur"}
            repr_semis = {c: s for c, s in semis.items() if s["type_organe"] == "reproducteur"}

            lines_out.append("\n🌱 *Semis :*")

            if veg_semis:
                lines_out.append("  _→ Récolte destructive (végétatif)_")
                for culture, s in veg_semis.items():
                    if s["total_seme"] is not None and s["total_seme"] > 0:
                        ligne = f"  • {culture} : *{int(s['total_seme'])} {s['unite']}* ({s['nb_semis']} semis)"
                    else:
                        ligne = f"  • {culture} : *{s['nb_semis']} semis*"
                    if s["nb_recoltes"] > 0:
                        r_val = round(s["total_recolte"], 2)
                        r_u   = s["unite_recolte"] or "unités"
                        ligne += f" · {r_val} {r_u} récoltés ({s['nb_recoltes']} fois)"
                    lines_out.append(ligne)

            if repr_semis:
                lines_out.append("  _→ Récolte continue (reproducteur)_")
                for culture, s in repr_semis.items():
                    if s["total_seme"] is not None and s["total_seme"] > 0:
                        ligne = f"  • {culture} : *{int(s['total_seme'])} {s['unite']}* ({s['nb_semis']} semis)"
                    else:
                        ligne = f"  • {culture} : *{s['nb_semis']} semis*"
                    if s["nb_recoltes"] > 0:
                        r_val = round(s["total_recolte"], 2)
                        r_u   = s["unite_recolte"] or "unités"
                        ligne += f" · {r_val} {r_u} récoltés ({s['nb_recoltes']} fois)"
                    lines_out.append(ligne)

        # ── Arrosages (inchangé) ───────────────────────────────────────────────
        arrosages = (
            db.query(func.count(Evenement.id), func.sum(Evenement.duree))
            .filter(Evenement.type_action == "arrosage")
            .first()
        )
        if arrosages and arrosages[0]:
            lines_out.append(f"\n💧 *Arrosages :* {arrosages[0]} fois")
            if arrosages[1]:
                lines_out.append(f"  Durée totale : *{arrosages[1]} min*")

        # ── Traitements (bonus) ───────────────────────────────────────────────
        nb_traitements = (
            db.query(func.count(Evenement.id))
            .filter(Evenement.type_action == "traitement")
            .scalar()
        )
        if nb_traitements:
            lines_out.append(f"\n💊 *Traitements :* {nb_traitements} applications")

        # [US_Stats_detail_par_variete / CA2] Hint pour le détail par variété
        lines_out.append("\n_Pour le détail d'une variété : /stats [culture]_")

        texte_final = "\n".join(lines_out)

        try:
            await update.message.reply_text(
                texte_final,
                parse_mode="Markdown",
                reply_markup=MENU_KEYBOARD
            )
        except Exception:
            # Fallback sans Markdown si le texte contient des caractères problématiques
            await update.message.reply_text(
                texte_final.replace("*", "").replace("_", ""),
                reply_markup=MENU_KEYBOARD
            )

        # ── Synthèse vocale ───────────────────────────────────────────────────
        await send_voice_reply(update, texte_final)

    finally:
        db.close()



async def cmd_historique(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """20 derniers événements."""
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
            rang   = f" x{e.rang}rangs" if e.rang else ""
            trt    = f" ({e.traitement})" if e.traitement else ""
            lines.append(f"*{d}* — {action}\n  {cult} {qte} {parc}{rang}{trt}".strip())

        await update.message.reply_text(
            "\n\n".join(lines),
            parse_mode="Markdown",
            reply_markup=MENU_KEYBOARD
        )
        # ── Synthèse vocale de l'historique ───────────────────────────────────
        await send_voice_reply(update, "\n\n".join(lines))
    finally:
        db.close()


async def cmd_ask(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Commande /ask."""
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
    """Formate un événement en une ligne lisible."""
    d    = e.date.strftime("%d/%m") if e.date else "?"
    act  = e.type_action or "?"
    cult = f" {e.culture}" if e.culture else ""
    var  = f" ({e.variete})" if e.variete else ""
    qte  = f" {e.quantite}{e.unite or ''}" if e.quantite else ""
    parc = f" [{e.parcelle}]" if e.parcelle else ""
    rang = f" x{e.rang}rangs" if e.rang else ""
    trt  = f" ({e.traitement})" if e.traitement else ""
    return f"#{e.id} {d} — {act}{cult}{var}{qte}{rang}{parc}{trt}"


def _normalize_action_search(action: str) -> str:
    """Normalise une action retournée par Groq pour correspondre aux valeurs en base."""
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
    """Groq extrait les critères → SQL retrouve les événements."""
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
{{"action": string|null, "culture": string|null, "variete": string|null, "date_debut": "YYYY-MM-DD"|null, "date_fin": "YYYY-MM-DD"|null, "parcelle": string|null}}

RÈGLES :
- action SANS accent : recolte, plantation, semis, arrosage, paillage, traitement, desherbage, taille, observation, tuteurage, fertilisation, repiquage
- culture au singulier minuscule sans accent
- variete : mot ou groupe de mots décrivant la variété (ex: "ronde", "cerise", "noire de crimée"), null si non mentionné
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

    # Normaliser l'action
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
        if criteres.get("variete"):
            q = q.filter(Evenement.variete.ilike(f"%{criteres['variete']}%"))
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
    """Propose correction ou suppression du dernier événement."""
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
    """Étape 1 — Demande à l'utilisateur de décrire l'événement à corriger."""
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
    """Étape 2 — Recherche les candidats en base."""
    if "annuler" in texte.lower():
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    # Raccourci "1" → dernier événement
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
        # Un seul résultat → directement en mode corr_apply, sans étape intermédiaire
        e = candidates[0]
        ctx.user_data['corr_event_id'] = e.id
        ctx.user_data['mode'] = 'corr_apply'   # ← clé du fix
        await update.message.reply_text(
            f"✅ Événement trouvé :\n\n`{_fmt_event(e)}`\n\n"
            f"✏️ Dites-moi ce que vous souhaitez modifier :\n"
            f"_Ex : c'est 3 kg / la date c'est le 9 mars / ajouter parcelle nord_\n\n"
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
    """Étape 3 — L'utilisateur choisit l'action (corriger/supprimer) ou le numéro."""
    t = texte.strip().lower()

    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    # Si event_id déjà défini (un seul candidat) → action directe
    event_id = ctx.user_data.get('corr_event_id')

    # Sinon extraire le numéro
    if not event_id:
        try:
            num = int(t) - 1
            candidates = ctx.user_data.get('corr_candidates', [])
            event_id = candidates[num]
            ctx.user_data['corr_event_id'] = event_id
        except (ValueError, IndexError):
            await update.message.reply_text("❓ Tapez le numéro affiché (1, 2, 3...).")
            return

    # Relire l'événement
    db = SessionLocal()
    try:
        event = db.get(Evenement, event_id)
    finally:
        db.close()

    if not event:
        await update.message.reply_text("❌ Événement introuvable.")
        ctx.user_data['mode'] = None
        return

    # Bouton supprimer
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

    # Bouton corriger explicite
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

    # ── Cas clé : l'utilisateur décrit directement la correction sans passer par le bouton
    # Ex : "changer la date au 9 mars", "c'était 1.5 kg", "parcelle nord"
    # → on saute directement à corr_apply avec ce texte
    MOTS_CORRECTION = ("changer", "modifier", "mettre", "c'était", "c etait",
                       "il s'agit", "il s agit", "ajouter", "enlever", "suppr",
                       "corriger", "plutôt", "plutot", "non ", "pas ")
    if any(t.startswith(m) or m in t for m in MOTS_CORRECTION):
        log.info(f"⚡ CORRECTION DIRECTE : texte '{texte}' → saut vers corr_apply")
        ctx.user_data['mode'] = 'corr_apply'
        await _corr_apply(update, ctx, texte)
        return

    # Sinon : texte libre sans mot-clé → proposer les boutons
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
    """Confirmation suppression."""
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
    """Étape 4 — Groq identifie les champs à modifier → présente un résumé pour confirmation."""
    t = texte.strip().lower()
    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return
    # Suppression demandée depuis corr_apply (bouton 🗑)
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

    # ── Validation FK parcelle ────────────────────────────────────────────────
    nom_parcelle_corr = corrections.get("parcelle")
    if nom_parcelle_corr is not None:
        db_check = SessionLocal()
        try:
            parcelle_resolue = resolve_parcelle(db_check, nom_parcelle_corr)
        finally:
            db_check.close()
        if parcelle_resolue is None:
            log.warning(f"⚠️ CORRECTION BLOQUÉE : parcelle inconnue {nom_parcelle_corr!r}")
            await msg_wait.edit_text(
                f"❌ La parcelle *{nom_parcelle_corr}* n'existe pas dans votre potager.\n\n"
                f"Créez-la d'abord avec : `/parcelle ajouter {nom_parcelle_corr}`",
                parse_mode="Markdown"
            )
            # Rester en corr_apply pour permettre une nouvelle correction
            return
        # Normaliser le nom vers la forme canonique de la BDD
        corrections["parcelle"] = parcelle_resolue.nom
        corrections["_parcelle_id"] = parcelle_resolue.id
        log.info(f"✅ PARCELLE RÉSOLUE : {nom_parcelle_corr!r} → {parcelle_resolue.nom!r} (id={parcelle_resolue.id})")

    log.info(f"✏️ CORRECTIONS     : {corrections}")

    # Préparer le résumé lisible avant confirmation
    LABELS = {
        "action": "Action", "culture": "Culture", "variete": "Variété",
        "quantite": "Quantité", "unite": "Unité", "parcelle": "Parcelle",
        "rang": "Rangs", "duree_minutes": "Durée (min)", "traitement": "Traitement",
        "commentaire": "Commentaire", "date": "Date"
    }
    mapping = {
        "action": "type_action", "culture": "culture", "variete": "variete",
        "quantite": "quantite", "unite": "unite", "parcelle": "parcelle",
        "rang": "rang", "duree_minutes": "duree", "traitement": "traitement",
        "commentaire": "commentaire"
    }

    lines = [f"📋 *Résumé des modifications sur #{event_id} :*\n"]
    for champ, nouvelle_val in corrections.items():
        if champ.startswith("_"):   # champs internes (_parcelle_id…)
            continue
        ancienne_val = event_actuel.get(champ, "—") or "—"
        label = LABELS.get(champ, champ)
        lines.append(f"• *{label}* : `{ancienne_val}` → `{nouvelle_val if nouvelle_val is not None else 'supprimé'}`")

    lines.append("\nConfirmez-vous ces modifications ?")

    # Sauvegarder les corrections en attente + état avant modification
    ctx.user_data['corr_pending']      = corrections
    ctx.user_data['corr_event_actuel'] = event_actuel
    ctx.user_data['mode'] = 'corr_confirm'

    await msg_wait.edit_text(
        "\n".join(lines), parse_mode="Markdown"
    )
    await update.message.reply_text(
        "Confirmez ?",
        reply_markup=ReplyKeyboardMarkup(
            [["✅ Confirmer"], ["✏️ Modifier autre chose"], ["❌ Annuler"]],
            resize_keyboard=True, one_time_keyboard=True
        )
    )


async def _corr_confirm(update: Update, ctx: ContextTypes.DEFAULT_TYPE, texte: str):
    """Étape 5 — Confirmation finale avant UPDATE en base."""
    t = texte.strip().lower()

    if "annuler" in t:
        ctx.user_data['mode'] = None
        await update.message.reply_text("↩️ Correction annulée.", reply_markup=MENU_KEYBOARD)
        return

    if "modifier" in t or "autre" in t:
        # Retour à l'étape de saisie de correction
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
                if champ == "_parcelle_id":
                    # champ interne — géré ci-dessous avec "parcelle"
                    continue
                col = mapping.get(champ, champ)
                if champ == "date":
                    setattr(event, "date", parse_date(valeur))
                elif champ == "quantite":
                    setattr(event, col, _to_float(valeur))
                elif champ in ("rang", "duree_minutes"):
                    setattr(event, col, _to_int(valeur))
                elif champ == "parcelle":
                    # Mettre à jour le texte ET la FK parcelle_id
                    event.parcelle    = valeur
                    event.parcelle_id = corrections.get("_parcelle_id")
                elif hasattr(event, col):
                    setattr(event, col, valeur)

            # ── Trace de correction dans texte_original ───────────────────
            LABELS = {
                "action": "action", "culture": "culture", "variete": "variété",
                "quantite": "quantité", "unite": "unité", "parcelle": "parcelle",
                "rang": "rangs", "duree_minutes": "durée", "traitement": "traitement",
                "commentaire": "commentaire", "date": "date"
            }
            details = ", ".join(
                f"{LABELS.get(k, k)}: {event_actuel.get(k, '—') or '—'} → {v if v is not None else 'supprimé'}"
                for k, v in corrections.items()
                if not k.startswith("_")   # ignorer champs internes (_parcelle_id…)
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

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .read_timeout(30)
        .write_timeout(30)
        .connect_timeout(15)
        .pool_timeout(30)
        .build()
    )

    # Commandes
    app.add_handler(CommandHandler("start",      cmd_start))
    app.add_handler(CommandHandler("help",       cmd_help))
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

    # [US_Plan_occupation_parcelles / CA1, CA13] Plan et gestion des parcelles
    app.add_handler(CommandHandler("plan",      cmd_plan))
    app.add_handler(CommandHandler("parcelle",  cmd_parcelle))
    app.add_handler(CommandHandler("parcelles", _cmd_parcelles_lister))  # alias /parcelle lister

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
