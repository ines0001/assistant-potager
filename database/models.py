"""
database/models.py — Modèles SQLAlchemy pour l'Assistant Potager
-----------------------------------------------------------------
[US-001] Ajout colonne type_organe_recolte sur Evenement
[US-001] Ajout modèle CultureConfig (table culture_config)
"""
from sqlalchemy import Column, Integer, String, Float, DateTime
from database.db import Base


class Evenement(Base):
    __tablename__ = "evenements"

    id             = Column(Integer, primary_key=True, index=True)
    # ⚠️ Plus de server_default : on passe toujours la date explicitement
    # pour respecter "hier", "lundi dernier", etc.
    date           = Column(DateTime, nullable=True, index=True)

    # Action principale
    type_action    = Column(String, index=True)

    # Culture
    culture        = Column(String, index=True)
    variete        = Column(String)

    # Quantité
    quantite       = Column(Float)
    unite          = Column(String)

    # Localisation
    parcelle       = Column(String, index=True)
    rang           = Column(Integer)   # [migration_v3] INTEGER (pas String)

    # Détails
    duree          = Column(Integer)
    traitement     = Column(String)
    commentaire    = Column(String)

    # Texte original dicté (+ traces [CORR ...])
    texte_original = Column(String)

    # [US-001] Classification agronomique héritée depuis culture_config
    # Valeurs : "végétatif" | "reproducteur" | null
    type_organe_recolte = Column(String, nullable=True)


class CultureConfig(Base):
    """
    [US-001] Configuration des cultures avec leur type d'organe récolté.

    Permet de distinguer :
    - "végétatif"    : récolte destructive (salade, carotte, radis...)
                       → 1 récolte = 1 plant consommé/détruit
    - "reproducteur" : récolte continue (tomate, courgette, poivron...)
                       → la plante reste en vie, produit plusieurs fois
    """
    __tablename__ = "culture_config"

    id                      = Column(Integer, primary_key=True, index=True)
    nom                     = Column(String, unique=True, index=True, nullable=False)
    type_organe_recolte     = Column(String, nullable=False)   # "végétatif" | "reproducteur"
    description_agronomique = Column(String)
