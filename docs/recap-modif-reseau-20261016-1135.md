# Récapitulatif des modifications — Partie Réseau (KOM)
**Date et horodatage** : 16 octobre 2026, 11:35 (Fuseau horaire : Africa/Lagos, UTC+1)  
**Branche** : `feature/network`  
**Développeur** : KOM  

---

## 1. Résumé en quelques lignes
La fonctionnalité Réseau (F7, règles R21 et R22) a été entièrement implémentée dans le respect strict de l'architecture Ports/Mocks et du contrat d'API du projet. Les routes permettent désormais de créer, lister de manière paginée, consulter, renommer et supprimer des réseaux au sein d'un projet, ainsi que d'y rattacher ou en détacher des machines virtuelles (d'origine ou partagées activement). La fiabilité en cas de défaillance du port réseau externe (`upstream_unavailable`), la stricte atomicité des opérations sans écriture partielle, le refus catégorique des stockages (R22), l'unicité globale des slugs de noms, l'auditabilité de chaque action et l'idempotence des appels ont été implémentés et validés par une suite de 58 tests automatisés (230 tests au total sur le projet, 0 régression, 0 erreur de lint).

---

## 2. Ce qui existait déjà et a été conservé tel quel
- **Socle partagé intact** : Aucun fichier interdit (`app/core/`, `app/api/`, `app/shared/policies/`, `app/shared/models/` hors `networks.py`, `app/shared/seed/`, `app/main.py`, `tests/conftest.py`, `tests/support.py`) n'a été altéré.
- **Modèle relationnel et migrations** : La migration initiale `alembic/versions/f60e7764b833_initial.py` définissait déjà rigoureusement les tables `networks` et `network_vms`. Aucune nouvelle migration de schéma n'a été nécessaire.
- **Signatures existantes de `NetworkPort`** : Les 5 méthodes abstraites initiales (`create_network`, `attach_vm`, `detach_vm`, `detach_vm_from_project`, `delete_network`) ont été conservées avec leurs signatures et types d'origine (`NetworkRef`, `VmRef`).
- **Contrat d'API initial** : Les schémas Pydantic `NetworkCreateIn`, `NetworkMembershipIn` et `NetworkOut` ont été conservés avec leurs types et contraintes exactes.
- **Tests existants** : Le fichier d'infrastructure `tests/infrastructure/network/test_detach_vm_from_project.py` a été conservé tel quel et continue de passer avec succès.

---

## 3. Fichiers créés ou modifiés

| Fichier | Nature du changement | Raison |
|---|---|---|
| `app/application/ports/network.py` | Modification | Ajout de l'exception `NetworkNotFound(NetworkError)` pour signaler proprement les réseaux inconnus côté infrastructure. |
| `app/infrastructure/network/fake_network.py` | Modification | Ajout de la vérification de l'existence du réseau (`NetworkNotFound`), d'un délai simulé optionnel, de la méthode de réinitialisation `reset()` pour l'isolation des tests, et de la prise en compte du fichier drapeau `.fake_network_down` pour la simulation de panne manuelle. |
| `app/shared/models/networks.py` | Modification | Déclaration de la relation ORM `members: Mapped[list[NetworkVm]]` et de la propriété `@property vm_ids` sur le modèle `Network` pour alimenter nativement le schéma de sortie `NetworkOut`. |
| `app/features/networks/schemas.py` | Modification | Ajout du schéma `NetworkUpdateIn` validant le renommage d'un réseau (`min_length=1, max_length=128`). |
| `app/features/networks/router.py` | Modification | Passage des endpoints en asynchrone (`async def`), injection des dépendances `IamPort` et `NetworkPort` (`get_network_port` sans collision de nom), ajout des routes `GET /{network_id}` et `PATCH /{network_id}`, documentation OpenAPI des erreurs. |
| `app/features/networks/service.py` | Modification (implémentation complète) | Logique métier F7 : contrôles d'accès Figure 3, vérification de visibilité R21, rejet stockage R22, unicité des slugs de noms, audit systématique, résilience aux pannes du port, et 4 fonctions d'intégration pour les équipes partenaires. |
| `tests/features/networks/conftest.py` | Création | Fixture autouse `fake_network` garantissant un mock vierge et isolé pour chaque test unitaire réseau. |
| `tests/features/networks/test_create_network.py` | Modification | Remplacement du test 501 par 8 tests de création : cas nominal propriétaire, invité avec droit, refus sans droit, refus non-membre, projet inconnu, conflit de slug, panne du port (503) et audit. |
| `tests/features/networks/test_list_networks.py` | Modification | Remplacement du test 501 par 6 tests de consultation paginée : page vide, pagination page/page_size, invité avec `vm.view`, non-membre, résilience en cas de panne du port. |
| `tests/features/networks/test_get_network.py` | Création | 5 tests de consultation unitaire : nominal, jeton absent, réseau inexistant, étanchéité inter-projet (404), résilience en cas de panne du port. |
| `tests/features/networks/test_update_network.py` | Création | 5 tests de renommage : propriétaire OK, invité avec `vm.network` OK, invité sans droit refusé, conflit de slug 409, audit vérifié. |
| `tests/features/networks/test_attach_vm_to_network.py` | Modification | Remplacement du test 501 par 10 tests de rattachement : VM d'origine, VM partagée active, refus VM non partagée, refus partage révoqué, refus stockage (R22), refus VM en suppression, idempotence, panne du port (503). |
| `tests/features/networks/test_detach_vm_from_network.py` | Modification | Remplacement du test 501 par 5 tests de détachement : nominal, idempotence si absent, droit manquant, panne du port (503 et lien conservé). |
| `tests/features/networks/test_delete_network.py` | Modification | Remplacement du test 501 par 6 tests de suppression : 204 et cascade sur `network_vms`, droits requis, étanchéité inter-projet, panne du port (503 et réseau conservé). |
| `tests/features/networks/test_network_integrations.py` | Création | 5 tests d'intégration interne : suppression de VM (`detach_vm_from_all_networks`), retrait de partage (`detach_vm_from_project_networks`), suppression de projet (`delete_project_networks`), recherche des réseaux d'une VM, gestion des pannes. |
| `tests/infrastructure/network/test_fake_network.py` | Création | 7 tests validant le comportement du mock : cycle de vie, idempotence, erreur réseau inexistant, interrupteur de panne, réinitialisation `reset()`, simulation de latence, interrupteur par fichier drapeau. |
| `tests/infrastructure/network/toggle_network_failure.py` | Création | Script utilitaire en ligne de commande permettant d'activer/désactiver la panne du mock réseau en cours d'exécution manuelle (`uvicorn`). |
| `docs/API_ENDPOINTS_RESEAU.md` | Création | Livrable 2 : Documentation exhaustive des endpoints réseau et fonctions d'intégration. |
| `docs/recap-modif-reseau-20261016-1135.md` | Création | Livrable 1 : Le présent document de synthèse. |

---

## 4. Décisions de conception et hypothèses

1. **Stratégie de fiabilité et ordre Port -> Base de données** :
   Pour satisfaire l'exigence formelle *"JAMAIS d'action appliquée à moitié"*, chaque opération mutante contacte d'abord le port réseau externe (`NetworkPort`).
   - Si le port externe lève `NetworkUnavailable`, l'exception est immédiatement traduite en `AppError(ErrorCode.UPSTREAM_UNAVAILABLE)`. Aucune transaction de base de données n'est validée (`db.commit()` n'est jamais atteint), ce qui garantit qu'aucun état orphelin n'est créé en base.
   - Ce n'est qu'une fois la confirmation du port externe reçue que les écritures et l'événement d'audit sont commités en base.
2. **Consultation autonome en mode dégradé** :
   Les opérations de lecture (`list_networks`, `get_network`) interrogent uniquement la base de données locale (dernier état connu). Elles continuent ainsi de fonctionner avec un code HTTP 200 même si le groupe Réseau externe est totalement indisponible.
3. **Idempotence des actions techniques** :
   - Rattacher une VM déjà présente dans le réseau ne génère aucune erreur et renvoie immédiatement l'objet `NetworkOut` avec le code HTTP 200.
   - Détacher une VM absente du réseau ne génère aucune erreur et renvoie l'objet avec le code 200.
   - Supprimer un réseau déjà absent côté port ne bloque pas la suppression en base.
4. **Visibilité et éligibilité des VMs (Règles F7 et R21)** :
   Une VM est éligible au rattachement dans le projet P si et seulement si `origin_project_id == P` ou si elle fait l'objet d'un `ResourceShare` actif (`status == "active"` et `dest_project_id == P`). La révocation du partage ou l'absence de partage entraîne un rejet `403 Forbidden`.
5. **Rejet strict des espaces de stockage (Règle R22)** :
   Si un identifiant transmis à `attach_vm` correspond à une entrée de la table `storages`, l'appel est formellement rejeté avec l'erreur `400 Bad Request` (`bad_request : Un espace de stockage ne peut pas etre mis en reseau (R22)`).
6. **Étanchéité des projets (Pas de fuite d'information)** :
   Si un utilisateur tente d'accéder à un réseau via une URL dont le `project_id` ne correspond pas au propriétaire réel du réseau, l'API renvoie `404 Not Found` plutôt que `403 Forbidden`, évitant ainsi de confirmer l'existence d'une ressource d'un projet tiers.
7. **Unicité globale des slugs de noms de réseaux** :
   Afin de garantir une différenciation visuelle et d'éviter les collisions, chaque création ou renommage applique la fonction `slugify()` et vérifie qu'aucun réseau du système ne possède un slug identique (renvoi d'un code `409 Conflict` en cas de doublon).

---

## 5. Fonctions d'intégration exposées aux autres équipes

Le service `app.features.networks.service` expose 4 fonctions d'intégration réutilisables, idempotentes et rejouables :

```python
async def detach_vm_from_all_networks(
    db: Session, network_port: NetworkPort, *, vm_id: str
) -> None:
    """Appelé lors de la suppression d'une VM (NAOMI - F6, R21). Idempotent."""

async def detach_vm_from_project_networks(
    db: Session, network_port: NetworkPort, *, vm_id: str, project_id: str
) -> None:
    """Appelé lors du retrait d'un partage de VM (socle shares - F14, R21). Idempotent."""

async def delete_project_networks(
    db: Session, network_port: NetworkPort, *, project_id: str
) -> None:
    """Appelé lors de la suppression d'un projet en cascade (ZUCHUON - F12, R23). Idempotent."""

def list_vm_networks(
    db: Session, *, vm_id: str, project_id: str | None = None
) -> list[Network]:
    """Retourne la liste des réseaux auxquels une VM est rattachée (filtrable par projet)."""
```

### Points d'accroche identifiés dans le code existant (non modifiés) :
1. **Équipe VM (NAOMI)** :
   - Fichier : `app/features/vms/service.py`, ligne 40 (`delete_vm`).
   - Raccordement à faire : Lors de la confirmation de suppression de la VM, avant la destruction finale, appeler `await detach_vm_from_all_networks(db, network, vm_id=vm_id)`.
2. **Équipe Projets (ZUCHUON)** :
   - Fichier : `app/features/projects/service.py`, ligne 30 (`delete_project`).
   - Raccordement à faire : Lors de la suppression en cascade du projet, appeler `await delete_project_networks(db, network, project_id=project_id)`.
3. **Moteur de partages (`shares`)** :
   - Fichier : `app/features/shares/service.py`, lignes 156-161 (`revoke_share`).
   - Raccordement possible : Remplacer l'appel direct `network.detach_vm_from_project` et la fonction locale `_drop_dest_links` par l'appel unifié `await detach_vm_from_project_networks(db, network, vm_id=row.resource_id, project_id=row.dest_project_id)`.

---

## 6. Résultats des tests et commandes

### Commandes exécutées :
```bash
# Lancement de la suite réseau
pytest tests/features/networks tests/infrastructure/network -v

# Lancement de la suite complète
pytest

# Linter de référence
ruff check .
```

### Comparaison Avant / Après :

| Métrique | État initial (Phase 1) | État final (Phase 3) | Évolution |
|---|---|---|---|
| Tests réseau | 12 passants (tous en 501 not_implemented) | **58 passants** (tests réels exhaustifs) | +46 tests réels |
| Suite globale `pytest` | 183 passants | **230 passants**, 0 échec | +47 tests au total |
| `ruff check .` | All checks passed! (0 erreur) | **All checks passed! (0 erreur)** | 0 régression |
| Contrat OpenAPI | 2 passants | **2 passants** | Contrat 100% respecté |

### Justification des modifications de tests existants :
Les 5 fichiers `test_create_network.py`, `test_list_networks.py`, `test_attach_vm_to_network.py`, `test_detach_vm_from_network.py` et `test_delete_network.py` contenaient uniquement des assertions temporaires `assert response.status_code == 501` et `body["error"]["code"] == "not_implemented"`. Ces tests d'attente ont été naturellement remplacés par les tests nominaux et aux limites validant l'implémentation métier réelle.

---

## 7. Procédure de vérification manuelle et automatique

### A. Vérification automatique
Exécuter dans le terminal :
```bash
.\.venv\Scripts\pytest tests/features/networks tests/infrastructure/network -v
.\.venv\Scripts\pytest
.\.venv\Scripts\ruff check .
```
- **Comment lire un échec éventuel** :
  - `assert response.status_code == 201` échoue : vérifier si l'utilisateur possède bien le droit `vm.network` ou s'il y a collision de slug (code 409).
  - `assert response.status_code == 403` échoue : vérifier la politique d'accès `authorize()` et la visibilité de la VM (`is_resource_visible()`).
  - `assert response.status_code == 503` : correspond au test de résilience à la panne du mock. Si ce n'est pas le comportement attendu, vérifier si le fichier `.fake_network_down` n'est pas resté actif.

---

### B. Vérification manuelle sans Docker (Local)

#### 1. Démarrage de l'application
Dans un premier terminal :
```bash
# 1. Créer le fichier .env local avec la base SQLite
echo "DATABASE_URL=sqlite:///./dev.db" > .env
echo "IAM_JWT_SECRET=dev-secret-change-me" >> .env
echo "IAM_SEED_DEMO_USERS=true" >> .env

# 2. Appliquer les migrations Alembic sur SQLite
.\.venv\Scripts\alembic upgrade head

# 3. Démarrer le serveur API
.\.venv\Scripts\uvicorn app.main:app --reload
```
L'API est accessible sur `http://localhost:8000`, et Swagger sur `http://localhost:8000/api/v1/docs`.

---

#### 2. Scénario 1 : Via Swagger UI (`http://localhost:8000/api/v1/docs`)
1. **Authentification** :
   - Dérouler `POST /api/v1/auth/login`. Cliquer sur *Try it out*.
   - Corps : `{"email": "alice@iaas.cm", "password": "alice123"}`. Exécuter.
   - Copier la valeur de `access_token`.
   - Cliquer sur le bouton **Authorize** en haut à droite, coller le token et valider.
2. **Création d'un projet & d'une VM** :
   - Comme les routes de création directe de projet/VM sont réservées à ZUCHUON et NAOMI (501), utiliser le script d'injection rapide ou une session Python locale pour insérer le projet `p1` (propriétaire Alice) et deux VMs `vm-1` et `vm-2`.
3. **Création d'un réseau** :
   - Dérouler `POST /api/v1/projects/{project_id}/networks`.
   - `project_id` = `p1`, corps = `{"name": "lan-swagger"}`.
   - Exécuter -> Réponse attendue : `201 Created` avec l'objet JSON du réseau.
4. **Rattachement de VMs** :
   - Dérouler `POST /api/v1/projects/{project_id}/networks/{network_id}/vms`.
   - `network_id` = ID obtenu à l'étape 3, corps = `{"vm_id": "vm-1"}`.
   - Exécuter -> Réponse attendue : `200 OK` avec `"vm_ids": ["vm-1"]`.
5. **Consultation et Liste** :
   - Dérouler `GET /api/v1/projects/{project_id}/networks`. Exécuter -> Réponse `200 OK` avec pagination.
   - Dérouler `GET /api/v1/projects/{project_id}/networks/{network_id}`. Exécuter -> Réponse `200 OK`.
6. **Renommage** :
   - Dérouler `PATCH /api/v1/projects/{project_id}/networks/{network_id}`.
   - Corps = `{"name": "lan-swagger-renomme"}`. Exécuter -> Réponse `200 OK`.
7. **Retrait et suppression** :
   - Dérouler `DELETE /api/v1/projects/{project_id}/networks/{network_id}/vms/{vm_id}` -> Réponse `200 OK`.
   - Dérouler `DELETE /api/v1/projects/{project_id}/networks/{network_id}` -> Réponse `204 No Content`.

---

#### 3. Scénario 2 : Script cURL complet (compatible Bash)

Pour préparer le projet `p1` et les VMs de test dans la base locale `dev.db`, exécuter d'abord :
```bash
python -c "
from app.core.database import SessionLocal
from tests.support import add_project, add_vm, add_storage
with SessionLocal() as db:
    add_project(db, 'alice-id', 'p1', 'Projet Alice')
    add_vm(db, 'p1', 'vm-1', name='web')
    add_vm(db, 'p1', 'vm-2', name='db')
    add_storage(db, 'p1', 'st-1', name='disque-backup')
print('Donnees de demonstration injectees dans dev.db.')
"
```

Exécuter ensuite le scénario cURL étape par étape :

```bash
# 1. Connexion Alice (propriétaire de p1)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"alice@iaas.cm","password":"alice123"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "Token Alice : $TOKEN"

# 2. Création d'un réseau
# Code HTTP attendu : 201 Created
NET_RES=$(curl -s -w "\nHTTP_STATUS:%{http_code}" -X POST http://localhost:8000/api/v1/projects/p1/networks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"lan-principal"}')
echo "$NET_RES"
NET_ID=$(echo "$NET_RES" | grep -v "HTTP_STATUS" | python -c "import sys, json; print(json.load(sys.stdin)['id'])")
echo "Réseau créé avec l'ID : $NET_ID"

# 3. Rattachement de deux VMs
# Code HTTP attendu : 200 OK
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8000/api/v1/projects/p1/networks/$NET_ID/vms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vm_id":"vm-1"}'

curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8000/api/v1/projects/p1/networks/$NET_ID/vms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vm_id":"vm-2"}'

# 4. Liste paginée des réseaux
# Code HTTP attendu : 200 OK
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X GET "http://localhost:8000/api/v1/projects/p1/networks?page=1&page_size=10" \
  -H "Authorization: Bearer $TOKEN"

# 5. Consultation unitaire du réseau
# Code HTTP attendu : 200 OK
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X GET http://localhost:8000/api/v1/projects/p1/networks/$NET_ID \
  -H "Authorization: Bearer $TOKEN"

# 6. Renommage du réseau
# Code HTTP attendu : 200 OK
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X PATCH http://localhost:8000/api/v1/projects/p1/networks/$NET_ID \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"lan-principal-renomme"}'

# 7. Retrait d'une VM
# Code HTTP attendu : 200 OK
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X DELETE http://localhost:8000/api/v1/projects/p1/networks/$NET_ID/vms/vm-1 \
  -H "Authorization: Bearer $TOKEN"

# 8. Cas d'échecs contrôlés :
# A. Rejet d'un stockage (R22) -> Code HTTP attendu : 400 Bad Request
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8000/api/v1/projects/p1/networks/$NET_ID/vms \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"vm_id":"st-1"}'

# B. Jeton absent -> Code HTTP attendu : 401 Unauthorized
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X GET http://localhost:8000/api/v1/projects/p1/networks

# C. Droit manquant (Bob, non membre de p1) -> Code HTTP attendu : 403 Forbidden
BOB_TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"bob@iaas.cm","password":"bob123"}' \
  | python -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8000/api/v1/projects/p1/networks \
  -H "Authorization: Bearer $BOB_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"lan-interdit"}'

# D. Réseau introuvable -> Code HTTP attendu : 404 Not Found
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X GET http://localhost:8000/api/v1/projects/p1/networks/faux-reseau-id \
  -H "Authorization: Bearer $TOKEN"

# 9. Simulation de panne du service réseau externe :
# Activer la panne dans un autre terminal via le script utilitaire :
python tests/infrastructure/network/toggle_network_failure.py down

# Tentative de création pendant la panne -> Code HTTP attendu : 503 Service Unavailable
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X POST http://localhost:8000/api/v1/projects/p1/networks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"lan-pendant-panne"}'

# Consultation pendant la panne -> Code HTTP attendu : 200 OK (mode dégradé réussi)
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X GET http://localhost:8000/api/v1/projects/p1/networks \
  -H "Authorization: Bearer $TOKEN"

# Rétablissement du service réseau :
python tests/infrastructure/network/toggle_network_failure.py up

# 10. Suppression du réseau
# Code HTTP attendu : 204 No Content
curl -s -w "\nHTTP_STATUS:%{http_code}\n" -X DELETE http://localhost:8000/api/v1/projects/p1/networks/$NET_ID \
  -H "Authorization: Bearer $TOKEN"
```

---

### C. Diagnostic des pannes : "Comment savoir que ça ne va pas"

| Symptôme observé | Cause probable | Où regarder & Comment diagnostiquer |
|---|---|---|
| Réponse HTTP 503 (`upstream_unavailable`) | Le groupe Réseau externe est injoignable ou le flag `.fake_network_down` est resté présent. | Vérifier la présence du fichier `.fake_network_down` à la racine ou exécuter `python tests/infrastructure/network/toggle_network_failure.py status`. |
| Réponse HTTP 403 (`forbidden`) lors du rattachement d'une VM | La VM n'est pas dans son projet d'origine et aucun partage actif n'existe vers ce projet. | Consulter la table `resource_shares` en base : `SELECT * FROM resource_shares WHERE resource_id = '...' AND dest_project_id = '...'`. |
| Réponse HTTP 409 (`conflict`) à la création | Collision de slug (un réseau porte déjà un nom similaire comme "LAN PROD" et "lan-prod"). | Exécuter `SELECT id, name FROM networks;` pour vérifier les doublons de slugs. |
| Réponse HTTP 400 (`bad_request`) lors de `attach_vm` | L'identifiant fourni est un espace de stockage (`Storage`) et non une VM (règle R22). | Vérifier la table `storages`. |
| Écritures partielles suspectées après échec | Le service aurait commité en base avant l'appel port. | Vérifier `audit_logs` : aucune ligne `network.created` ou `network.vm_attached` ne doit exister pour une opération ayant renvoyé une erreur 503. |

---

## 8. Points ouverts, dettes connues et questions pour l'équipe

1. **Raccordement effectif des collègues** :
   Les fonctions `detach_vm_from_all_networks` et `delete_project_networks` sont prêtes et testées, mais dépendent de l'implémentation future de `delete_vm` par NAOMI et `delete_project` par ZUCHUON.
2. **Synchronisation du renommage avec le port externe** :
   `NetworkPort` ne propose actuellement pas de méthode `rename_network()`. Le renommage est donc purement logique au niveau du backend IaaS (base de données et audit). Si le groupe Réseau technique souhaite être notifié des renommages, il conviendra d'ajouter cette méthode au port ultérieurement.
