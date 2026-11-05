"""Configuration lue depuis l'environnement et le fichier .env."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Parametres de l'application. Les valeurs d'environnement ecrasent les defauts."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    iam_jwt_secret: str = "dev-secret-change-me"
    iam_token_ttl_seconds: int = 3600

    database_url: str = "sqlite:///./dev.db"   # en prod : postgresql+psycopg://user:pwd@host/db
    iam_seed_demo_users: bool = True   # comptes de démo dans le mock IAM (dev uniquement)

    # ─── service de DECISION et de QUOTA (distinct de l'IAM d'identité) ──────
    #
    # `IamPort` dit QUI tu es et quels DROITS tu portes. Il ne dit pas s'il reste
    # du QUOTA, ni si une politique autorise cette action-ci maintenant. Sans ce
    # second port, rien ne compte ce que la plateforme distribue.
    #
    # LE DEFAUT EST « gandal », ET C'EST VOULU. Avec « fake » par défaut, on se
    # retrouverait un jour en production avec des quotas en mémoire sans l'avoir
    # décidé — et personne ne le verrait, puisque rien ne casse : les chiffres
    # mentent, simplement.
    # TROIS VALEURS, et le defaut est « off » — ce qui demande une explication.
    #
    #   off      aucune decision n est demandee, aucun quota n est compte.
    #            C est EXACTEMENT le comportement d avant cette greffe.
    #   fake     quotas en memoire, plan ci-dessous. Developpement seulement.
    #   gandal   le vrai service de decision. Production.
    #
    # POURQUOI PAS « gandal » PAR DEFAUT, alors que c est le reglage sur. Parce
    # que ce backend existe deja, avec ses tests, et qu un defaut strict les
    # ferait tous echouer sur une machine qui n a ni cle ni « gandal_garde ». Une
    # greffe qui casse la suite au premier `git am` est une greffe qu on annule
    # sans la lire.
    #
    # POURQUOI « gandal » PAR DEFAUT, ET PAS « off ».
    #
    # J AVAIS MIS « off », ET LE RAISONNEMENT ETAIT A L ENVERS. L argument
    # etait : « gandal » par defaut ferait echouer la suite sur toute machine
    # sans cle ni autorite, et une greffe qui casse les tests au premier essai
    # est annulee sans etre lue. C est vrai — mais c est un probleme DES TESTS,
    # pas de la production, et le resoudre en production etait la mauvaise
    # moitie du compromis.
    #
    # UNE AUTORISATION QUI TOMBE EN PANNE **OUVERTE** EST PIRE QU UN SERVICE
    # QUI REFUSE DE DEMARRER. Avec « off » par defaut, un deploiement qui
    # oublie la variable sert toutes les routes SANS demander une seule
    # decision et SANS compter un seul quota — et il le fait en silence, en
    # repondant 200 a tout. Personne ne decouvre ca avant de manquer de place.
    #
    # Avec « gandal » par defaut, le meme oubli fait echouer les appels avec un
    # 503 qui nomme la cause. Bruyant, immediat, et du bon cote.
    #
    # C EST DONC AUX TESTS DE DIRE QU ILS NE VEULENT PAS D IAM, et ils le font :
    # « tests/conftest.py » pose DECISION_BACKEND=off avant tout import de
    # « app ». 280 tests passent sans cle, sans autorite et sans reseau.
    #
    # « fake » n est jamais un defaut : il RESSEMBLE a quelque chose. Un
    # deploiement qui l oublierait compterait des quotas en memoire, remis a
    # zero a chaque redemarrage — rien ne casse, les chiffres mentent.
    #
    # « off » reste possible, et reste annonce : au demarrage, et dans
    # « /api/v1/ready ». C est une sortie de secours explicite, plus un defaut.
    decision_backend: str = "gandal"           # off | fake | gandal
    decision_url: str = "https://10.30.0.30:8081/v1"
    # Fichier à deux lignes (identifiant, secret), mode 600 — VERIFIE par la
    # bibliothèque : une clé lisible par les autres comptes n'est plus un secret.
    decision_key_file: str = "/etc/gandal/cle-iam"
    decision_ca_file: str = "/etc/gandal/gandal-ca.crt"
    # Le rôle qu'endosse le backend. Sa politique doit accorder
    # « iam:decision:delegate » : sans quoi il ne peut pas décider AU NOM d'un
    # utilisateur, et la décision porterait sur le service lui-même.
    decision_role: str = "backend"
    decision_timeout_seconds: float = 5.0
    # EN MODE « fake » SEULEMENT : le plan accordé d'office à chaque projet.
    # Sans lui, aucun projet n'a de quota et tout est refusé — bon comportement
    # du vrai service, mais `fake` deviendrait inutilisable pour le Front.
    decision_fake_quota: dict[str, int] = {
        "vm_count": 5, "vcpu": 16, "ram_gb": 32, "disk_gb": 500,
        "gpu_count": 1, "gpu_mem_mb": 8192,
        "storage_buckets": 3, "storage_gb": 100, "storage_objects": 100000,
        "storage_egress_gb_month": 50,
    }


@lru_cache
def get_settings() -> Settings:
    """Retourne la configuration memorisee pour le processus."""
    return Settings()