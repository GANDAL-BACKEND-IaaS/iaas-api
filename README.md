# Backend IaaS

Backend metier d'une plateforme IaaS. Les utilisateurs y gerent des projets contenant des VMs et des espaces de stockage, deposent des demandes traitees par des administrateurs, et partagent leurs ressources entre leurs projets.

La specification de reference est [docs/conception-iaas-api.pdf](docs/conception-iaas-api.pdf). Elle prime sur toute autre description.

## Equipe et dossiers

Tout le monde travaille sur la branche `develop`. Chaque developpeur ne modifie que ses dossiers, pour eviter les conflits de merge.

| Developpeur | Port | Dossiers |
| --- | --- | --- |
| ZUCHUON | IAM | `app/application/ports/iam.py`, `app/infrastructure/iam/`, `app/features/auth/`, `app/features/profiles/`, `app/features/projects/`, `app/shared/models/projects.py` |
| NAOMI | VM | `app/features/vms/`, `app/features/packs/`, `app/application/ports/hypervisor.py`, `app/application/ports/dns.py`, `app/infrastructure/hypervisor/`, `app/infrastructure/dns/`, `app/shared/models/vms.py`, `app/shared/models/packs.py` |
| KOM | Reseau | `app/features/networks/`, `app/application/ports/network.py`, `app/infrastructure/network/`, `app/shared/models/networks.py` |
| TABA | Espaces | `app/features/storages/`, `app/application/ports/storage.py`, `app/infrastructure/storage/`, `app/shared/models/storages.py` |

Le socle partage (a ne modifier qu'ensemble) : `app/core/`, `app/api/`, `app/features/requests/`, `app/features/shares/`, `app/shared/policies/`, `app/shared/models/` hors fichiers nommes ci-dessus, `app/application/ports/notifications.py`, `app/infrastructure/notifications/`.

Toutes les routes metier decrites par le contrat sont implementees. Le seul endpoint conserve mais encore non reimplemente est `POST /api/v1/projects/{project_id}/vms/{vm_id}/console` : il repond selon le contrat actuel et sera rebranche sur une autre technologie ulterieurement. Deux routes de lecture sont ajoutees hors contrat : `GET /api/v1/shares` et `GET /api/v1/shares/{share_id}`.

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

- API : <http://localhost:8000>
- Documentation : <http://localhost:8000/docs>
- Schema OpenAPI : <http://localhost:8000/openapi.json>
- Sante : <http://localhost:8000/health> (alias versionne : `/api/v1/health`)
- Disponibilite : <http://localhost:8000/ready> ; verifie la connexion a la base et est documentee dans Swagger. Les groupes externes restent des mocks et ne sont pas sondes.

Les comptes de demonstration du mock IAM :

| Email | Mot de passe | Role |
| --- | --- | --- |
| `admin@iaas.cm` | `admin123` | administrateur |
| `alice@iaas.cm` | `alice123` | utilisateur |
| `bob@iaas.cm` | `bob123` | utilisateur |

Le secret JWT et le mot de passe PostgreSQL du fichier Compose sont reserves au developpement local.

## Contrat d'API

Toutes les routes sont sous `/api/v1`.

- Chaque corps de requete est un schema Pydantic.
- Chaque succes a un `response_model` (sauf `204`).
- Les listes sont des pages : `items`, `page`, `page_size`, `total_items`, `total_pages`. Une page vide renvoie `200` avec `items: []` et `total_pages: 0`.
- Toute erreur a la forme `{"error": {"code": "...", "message": "...", "details": ...}}`, avec `details` toujours present.
- Les codes stables sont `unauthorized`, `forbidden`, `not_found`, `conflict`, `validation_error`, `bad_request`, `invalid_state`, `upstream_unavailable`, `internal_error`.
- Les suppressions suivent un protocole en deux temps : un premier appel sans corps renvoie `confirmation_required`, `confirmation_text` et `warning` ; le second appel doit renvoyer exactement `{"confirmation_text": "SUPPRIMER <nom>"}` et produit `{"deleted": true, ...}`. Un texte errone renvoie `400`, une ressource deja supprimee `404`, une panne externe `503` sans suppression locale.
- Les actions d'alimentation renvoient `202` avec un etat transitoire (`starting`, `stopping`, `restarting`).
- Les dates sont en ISO 8601 UTC avec suffixe `Z`.
- Les identifiants d'objets sont des chaines UUID. Les unites sont explicites : RAM, VRAM et stockage en Go (`ram_gb`, `vram_gb`, `size_gb`, `ssd_gb`) et processeur en vCPU (`vcpu`).

### Choix d'implementation

- **Identifiants UUID partout** : `profile_id` et `request_id` sont aussi des chaines UUID, alors que le document de contrat les montre comme des entiers. C'est le seul ecart volontaire ; il est isole dans les schemas et les modeles pour pouvoir revenir au contrat si necessaire.
- **Unicite du nom de projet** : le nom est unique par proprietaire, a la creation comme au renommage (`409` en cas de doublon). Le proprietaire est le perimetre naturel puisqu'il est le seul a pouvoir partager entre ses projets.
- **Partages** : `GET /api/v1/shares` et `GET /api/v1/shares/{share_id}` sont des extensions de lecture. Un administrateur global ne voit pas les partages des utilisateurs : seul le membership d'un projet concerne donne acces.
- **Invitations** : `POST /api/v1/projects/{project_id}/invitations` accepte soit `email`, soit `invitee_id`, mais pas les deux. L'email est normalise puis resolu aupres de l'IAM ; un email inconnu renvoie `404`. La base conserve l'identifiant IAM canonique et un instantane `invitee_email` pour l'affichage.
- **Packs** : l'identifiant est un UUID opaque ; le nom est unique.
- **Droits** : `GET /api/v1/admin/rights` renvoie un tableau JSON simple, trie par `code`, sans pagination.

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
