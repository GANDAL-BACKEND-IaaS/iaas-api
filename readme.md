# Backend IaaS

Backend métier d'une plateforme IaaS : les utilisateurs y gèrent des **projets** contenant des
**VMs** et des **espaces de stockage**, font des **demandes** traitées par des administrateurs,
et partagent leurs ressources entre leurs projets.


## Principes d'architecture

Le backend ne réalise aucune action technique lui-même. Chaque dépendance externe est isolée
derrière un **port** (interface propre au backend), pour qu'un changement chez un autre groupe
n'impacte pas la logique métier.

```
app/
├── main.py                  # Application FastAPI, lifespan (création des tables + seed)
├── core/                    # Configuration, base de données, jetons, injection de dépendances
├── application/ports/       # Ports (interfaces) : IAM aujourd'hui, hyperviseur/réseau/... à venir
├── infrastructure/          # Adaptateurs des ports (fake_iam pour l'instant)
│   ├── iam/  hypervisor/  network/  storage/  dns/  email/
├── features/                # Un dossier par fonctionnalité (router, service, schemas)
│   ├── auth/                # Connexion, profil utilisateur, mot de passe
│   └── profiles/            # Catalogue de droits et profils de droits (admin)
└── shared/
    ├── models/              # Modèles SQLAlchemy
    ├── policies/            # Règles d'accès (à venir)
    └── seed/                # Catalogue des droits et profils par défaut (JSON)
tests/                       # Miroir de la structure de app/
```

## Démarrage rapide

Prérequis : Python 3.11 ou plus récent.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows : .venv\Scripts\activate
pip install -r requirements-dev.txt

cp .env.example .env               # puis adapter les valeurs
uvicorn app.main:app --reload
```

L'API est disponible sur http://localhost:8000 et la documentation interactive (Swagger) sur
http://localhost:8000/docs.

Au démarrage, les tables sont créées automatiquement et le catalogue de droits ainsi que les
profils par défaut sont insérés. Alembic remplacera ce mécanisme provisoire.

### Lancer avec Docker Compose

Prérequis : Docker avec le plugin Compose.

```bash
cp -n .env.example .env
# Remplacer IAM_JWT_SECRET dans .env par une valeur longue et aléatoire.
docker compose up --build
```

L'API est ensuite disponible sur http://localhost:8000 et Swagger sur
http://localhost:8000/docs. Compose stocke la base SQLite dans le volume Docker `iaas-data` ;
elle reste donc présente après `docker compose down`. Pour la supprimer également, exécuter
`docker compose down --volumes`.

Les utilisateurs de démonstration sont activés par défaut pour le mock IAM, comme en démarrage
local. Ne pas conserver les identifiants et le secret de développement dans un déploiement.

### Comptes de démonstration

Avec `IAM_SEED_DEMO_USERS=true` (valeur par défaut), le mock IAM crée :

| Email | Mot de passe | Rôle |
|---|---|---|
| `admin@iaas.cm` | `admin123` | administrateur |
| `alice@iaas.cm` | `alice123` | utilisateur |
| `bob@iaas.cm` | `bob123` | utilisateur |

Ces comptes sont réservés au développement local mocké pour l'instant. Les mots de passe sont stockés par un simple
hash SHA-256.

## Configuration

Variables d'environnement (fichier `.env`) :

| Variable | Défaut | Description |
|---|---|---|
| `IAM_JWT_SECRET` | `dev-secret-change-me` | Secret de signature des jetons. **À changer hors développement** |
| `IAM_TOKEN_TTL_SECONDS` | `3600` | Durée de vie des jetons |
| `DATABASE_URL` | `sqlite:///./dev.db` | URL SQLAlchemy (ex. `postgresql+psycopg://user:pwd@host/db` en production) |
| `IAM_SEED_DEMO_USERS` | `true` | Crée les comptes de démo dans le mock IAM |

## API disponible

| Méthode | Route | Accès | Description |
|---|---|---|---|
| POST | `/api/v1/auth/login` | public | Connexion, renvoie un jeton Bearer |
| GET | `/api/v1/auth/me` | connecté | Identité de l'utilisateur courant |
| PATCH | `/api/v1/auth/me` | connecté | Modifier ses informations (renvoie un nouveau jeton) |
| POST | `/api/v1/auth/password` | connecté | Changer son mot de passe |
| DELETE | `/api/v1/auth/me` | connecté | Supprimer son compte |
| GET | `/api/v1/admin/rights` | connecté | Lister le catalogue de droits |
| GET | `/api/v1/admin/profiles` | connecté | Lister les profils de droits |
| POST | `/api/v1/admin/profiles` | admin | Créer un profil |
| PATCH | `/api/v1/admin/profiles/{id}` | admin | Modifier un profil |
| DELETE | `/api/v1/admin/profiles/{id}` | admin | Supprimer un profil |

Exemple :

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@iaas.cm","password":"alice123"}' | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

curl localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

## Modèle de droits (résumé)

- Un projet a un **propriétaire** (tous les droits) et des **invités**.
- Les droits d'un membre sont définis **une fois par projet** et valent pour **toutes les
  ressources du type concerné** : `vm.*`, `storage.*`, `project.invite`.
- Un invité qui peut inviter ne peut accorder que des droits **inclus dans les siens**.
- Un **partage** rend une ressource visible dans un autre projet du même propriétaire. Il ne
  transmet aucun droit : les membres du projet destinataire y exercent les droits qu'ils y ont déjà.
- Les **demandes** (création et modification) sont toujours traitées par un administrateur. Les
  suppressions et actions directes ne passent pas par une demande.

Le catalogue complet est dans `app/shared/seed/rights_catalog.json` et les profils par défaut dans
`app/shared/seed/default_profiles.json`.

## Tests et qualité

```bash
pytest          # lance toute la suite (asyncio_mode = auto)
ruff check .    # lint
```


## Documentation

- `conception_backend_IaaS.pdf` : conception métier (acteurs, domaine, fonctionnalités F1 à F17,
  cycles de vie, règles R1 à R24, exigences non fonctionnelles).