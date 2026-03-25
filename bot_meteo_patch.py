"""
PATCH bot.py — Intégration météo quotidienne
=============================================
Ce fichier montre exactement les 3 modifications à apporter à bot.py.
NE PAS exécuter directement — copier les blocs dans bot.py.

Modification 1 : import
Modification 2 : commande /meteo
Modification 3 : job 5h00 + enregistrement dans main()
"""

# ══════════════════════════════════════════════════════════════════════════════
# MODIFICATION 1 — Import à ajouter en tête de bot.py
# Ajouter après : from utils.tts import send_voice_reply, set_tts_enabled, is_tts_enabled
# ══════════════════════════════════════════════════════════════════════════════

from utils.meteo import save_meteo_observation, fetch_meteo, format_meteo_commentaire


# ══════════════════════════════════════════════════════════════════════════════
# MODIFICATION 2 — Nouvelle commande /meteo
# Ajouter après cmd_tts_off() dans bot.py
# ══════════════════════════════════════════════════════════════════════════════

async def cmd_meteo(update, ctx):
    """
    /meteo — Déclenche manuellement la récupération météo et l'enregistre en base.
    Utile pour tester ou pour récupérer la météo hors du job automatique.
    """
    msg = await update.message.reply_text("🌤️ Récupération météo en cours...")
    db  = SessionLocal()
    try:
        meteo = save_meteo_observation(db)
        if meteo is None:
            # Peut être un doublon ou une erreur réseau
            # Tenter fetch sans sauvegarde pour afficher quand même
            meteo = fetch_meteo()
            if meteo:
                commentaire = format_meteo_commentaire(meteo)
                await msg.edit_text(
                    f"🌤️ *Météo du jour* _(déjà enregistrée)_\n\n{commentaire}",
                    parse_mode="Markdown"
                )
            else:
                await msg.edit_text("❌ Impossible de récupérer la météo. Vérifiez votre connexion.")
            return

        commentaire = format_meteo_commentaire(meteo)
        await msg.edit_text(
            f"🌤️ *Météo du jour enregistrée !*\n\n{commentaire}",
            parse_mode="Markdown"
        )
        log.info(f"🌤️  MÉTÉO MANUELLE  : déclenchée par /meteo")
    except Exception as e:
        log.error(f"❌ MÉTÉO COMMANDE   : {e}")
        await msg.edit_text(f"❌ Erreur : {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# MODIFICATION 3 — Job automatique à 05h00
# Ajouter le callback job_meteo AVANT la fonction main()
# Puis modifier main() pour enregistrer le job
# ══════════════════════════════════════════════════════════════════════════════

async def job_meteo_quotidienne(context):
    """
    Job planifié à 05h00 chaque matin.
    Récupère la météo Open-Meteo et l'enregistre silencieusement en base
    comme action 'observation' avec texte_original='[AUTO-METEO]'.
    Aucun message Telegram envoyé — enregistrement silencieux.
    """
    log.info("🌅 JOB MÉTÉO       : déclenchement automatique 05h00")
    db = SessionLocal()
    try:
        meteo = save_meteo_observation(db)
        if meteo:
            log.info(
                f"🌤️  MÉTÉO AUTO      : {meteo['emoji']} {meteo['label']} | "
                f"{meteo['temp_matin']}°C→{meteo['temp_aprem']}°C | "
                f"Pluie {meteo['precipitations']}mm"
            )
        else:
            log.warning("⚠️  MÉTÉO AUTO      : aucune donnée sauvée (doublon ou erreur réseau)")
    except Exception as e:
        log.error(f"❌ JOB MÉTÉO ERREUR : {e}")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# MODIFICATION 3b — Dans la fonction main(), ajouter AVANT app.run_polling()
#
# Remplacer :
#
#   app.run_polling(allowed_updates=Update.ALL_TYPES)
#
# Par :
#
#   # ── Job météo quotidien à 05h00 ─────────────────────────────────────────
#   import pytz
#   from datetime import time as dtime
#   tz_paris = pytz.timezone("Europe/Paris")
#   app.job_queue.run_daily(
#       job_meteo_quotidienne,
#       time=dtime(hour=5, minute=0, second=0, tzinfo=tz_paris),
#       name="meteo_quotidienne",
#   )
#   log.info("🌅 JOB MÉTÉO       : planifié à 05h00 Europe/Paris")
#
#   app.run_polling(allowed_updates=Update.ALL_TYPES)
#
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# MODIFICATION 3c — Handler commande /meteo dans main()
# Ajouter avec les autres CommandHandler :
#
#   app.add_handler(CommandHandler("meteo", cmd_meteo))
#
# ══════════════════════════════════════════════════════════════════════════════
