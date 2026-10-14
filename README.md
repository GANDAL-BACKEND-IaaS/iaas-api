# Backend IaaS

Backend metier d'une plateforme IaaS. Les utilisateurs y gerent des projets contenant des VMs et des espaces de stockage, deposent des demandes traitees par des administrateurs, et partagent leurs ressources entre leurs projets.

La specification de reference est [docs/conception-iaas-api.pdf](docs/conception-iaas-api.pdf). Elle prime sur toute autre description.

## Equipe et dossiers

Tout le monde travaille sur la branche `develop`. Chaque developpeur ne modifie que ses dossiers, pour eviter les conflits de merge.

| Developpeur | Port | Dossiers |
|---|---|---|
| ZUCHUON | IAM | `app/application/ports/iam.py`, `app/infrastructure/iam/`, `app/features/auth/`, `app/features/profiles/`, `app/features/projects/`, `app/shared/models/projects.py` |
| NAOMI | VM | `app/features/vms/`, `app/features/packs/`, `app/application/ports/hypervisor.py`, `app/application/ports/dns.py`, `app/infrastructure/hypervisor/`, `app/infrastructure/dns/`, `app/shared/models/vms.py`, `app/shared/models/packs.py` |
| KOM | Reseau | `app/features/networks/`, `app/application/ports/network.py`, `app/infrastructure/network/`, `app/shared/models/networks.py` |
| TABA | Espaces | `app/features/storages/`, `app/application/ports/storage.py`, `app/infrastructure/storage/`, `app/shared/models/storages.py` |

Le socle partage (a ne modifier qu'ensemble) : `app/core/`, `app/api/`, `app/features/requests/`, `app/features/shares/`, `app/shared/policies/`, `app/shared/models/` hors fichiers nommes ci-dessus, `app/application/ports/notifications.py`, `app/infrastructure/notifications/`.

Les routes orientees ressource (projets, VMs, packs, reseaux, stockages) repondent `501` tant que leur proprietaire ne les a pas implementees. Le contrat (schemas, erreurs) est deja publie. Les moteurs `POST /api/v1/requests` et `POST /api/v1/shares` sont operationnels.

## Architecture

Le backend ne realise aucune action technique. Chaque dependance externe est un port, aujourd'hui branche sur un mock.

```
app/
  main.py                      # FastAPI, seed, handlers d'erreurs
  api/v1/router.py             # Prefixe /api/v1
  core/                        # Config, base, erreurs, pagination, audit, jetons
  application/ports/           # Contrats IAM, hyperviseur, reseau, stockage, DNS, notifications
  infrastructure/              # Mocks de ces ports
  features/                    # auth, profiles, projects, vms, packs, networks, storages, requests, shares
  shared/models/               # Modele du domaine
  shared/policies/             # Controle d'acces (figure 3)
  shared/seed/                 # Droits, profils et packs de reference
tests/                         # Miroir de app/, un fichier par fonction publique
```

## Lancer tout le projet

Une seule commande construit l'image, demarre PostgreSQL, applique les migrations, insere le seed et sert l'API :

```bash
docker compose up --build
```

- API : http://localhost:8000
- Documentation : http://localhost:8000/api/v1/docs
- Schema OpenAPI : http://localhost:8000/api/v1/openapi.json
- Sante : http://localhost:8000/api/v1/health

Les comptes de demonstration du mock IAM :

| Email | Mot de passe | Role |
|---|---|---|
| `admin@iaas.cm` | `admin123` | administrateur |
| `alice@iaas.cm` | `alice123` | utilisateur |
| `bob@iaas.cm` | `bob123` | utilisateur |

Le secret JWT et le mot de passe PostgreSQL du fichier Compose sont reserves au developpement local.

## Contrat d'API

Toutes les routes sont sous `/api/v1`.

- Chaque corps de requete est un schema Pydantic.
- Chaque succes a un `response_model` (sauf `204`).
- Les listes sont des pages : `items`, `total`, `page`, `page_size`.
- Toute erreur a la forme `{"error": {"code": "...", "message": "...", "details": ...}}`.
- Les codes stables sont `unauthorized`, `forbidden`, `not_found`, `conflict`, `validation_error`, `bad_request`, `invalid_state`, `upstream_unavailable`, `not_implemented`, `internal_error`.

Exemple :

```bash
TOKEN=$(curl -s -X POST localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@iaas.cm","password":"alice123"}' \
  | python -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl localhost:8000/api/v1/auth/me -H "Authorization: Bearer $TOKEN"
```

## Developpement local sans Docker

Python 3.11 ou plus recent.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload
```

Les tests utilisent SQLite en memoire et n'ont pas besoin de PostgreSQL.

```bash
pytest
ruff check .
```

## Modele de droits (resume)

- Un projet a un proprietaire (tous les droits) et des invites.
- Les droits d'un membre sont definis une fois par projet et valent pour toutes les ressources du type : `vm.*`, `storage.*`, `project.invite`.
- Un invite qui invite ne peut accorder que des droits inclus dans les siens.
- Un partage rend une ressource visible dans un autre projet du meme proprietaire. Il ne transmet aucun droit.
- Seules les creations et modifications passent par une demande. Les suppressions et actions directes n'en passent pas.

Le catalogue est dans `app/shared/seed/rights_catalog.json` et les profils dans `app/shared/seed/default_profiles.json`.
