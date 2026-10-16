# Documentation des endpoints réseau

Les routes réseau sont montées sous le préfixe `/api/v1/projects/{project_id}/networks` (déclaré dans `app/features/networks/router.py` et assemblé dans `app/api/v1/router.py`). Elles permettent la gestion directe des réseaux de machines virtuelles au sein d'un projet IaaS (fonctionnalité F7, règles R21 et R22).

---

## Conventions générales

- **Format des échanges** : Toutes les requêtes et réponses utilisent le format JSON (`application/json`).
- **Authentification** : Requiert un jeton Bearer JWT passé dans l'en-tête `Authorization: Bearer <access_token>`.
  - `401 Unauthorized` (`unauthorized`) : Jeton absent, invalide ou expiré.
- **Autorisation** : L'accès est régi par la Figure 3 du document de conception (`app/shared/policies/access.py`) :
  - L'utilisateur doit être membre du projet visé (propriétaire ou invité).
  - Pour les actions de modification (création, renommage, suppression, rattachement, détachement), l'utilisateur doit être propriétaire du projet ou disposer du droit `vm.network`.
  - Pour les actions de consultation (liste, consultation unitaire), l'utilisateur doit être propriétaire ou disposer du droit `vm.view` ou `vm.network`.
  - `403 Forbidden` (`forbidden`) : Droit requis manquant, utilisateur non-membre ou ressource non visible dans le projet.
- **Ressources introuvables & Isolation des projets** :
  - `404 Not Found` (`not_found`) : Projet ou réseau inexistant, ou réseau n'appartenant pas au projet ciblé dans l'URL (aucun signalement de fuite entre projets).
- **Conflits d'état & d'unicité** :
  - `409 Conflict` (`conflict`) : Conflit de nom ou slug déjà utilisé par un autre réseau du système.
  - `409 Invalid State` (`invalid_state`) : VM en cours de suppression (`deleting`).
- **Validation** :
  - `422 Unprocessable Entity` (`validation_error`) : Corps JSON ou paramètres de requête invalides selon les contraintes Pydantic.
  - `400 Bad Request` (`bad_request`) : Tentative de mise en réseau d'un espace de stockage (interdiction stricte R22).
- **Disponibilité du service externe** :
  - `503 Service Unavailable` (`upstream_unavailable`) : Le service externe (port `NetworkPort`) ne répond pas ou est indisponible. Aucune modification partielle n'est appliquée en base de données.
- **Format d'erreur uniforme** :
  ```json
  {
    "error": {
      "code": "code_stable",
      "message": "Description lisible de l'erreur",
      "details": null
    }
  }
  ```
- **Format des listes paginées** :
  ```json
  {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20
  }
  ```

---

## Endpoints HTTP

### `POST /api/v1/projects/{project_id}/networks` : Créer un réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.network`.
- **Description** : Crée un nouveau réseau logique au sein du projet, appelle le port réseau externe de manière synchrone et persistante, puis enregistre un événement d'audit `network.created`.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant unique du projet (chaîne UUID ou code projet).
- **Corps (`NetworkCreateIn`)** :
  - `name` (chaîne, obligatoire) : Nom du réseau, longueur entre 1 et 128 caractères. Son slug normalisé doit être unique au sein du système.
  ```json
  {
    "name": "lan-production"
  }
  ```
- **Réponse `201 Created` (`NetworkOut`)** :
  ```json
  {
    "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
    "project_id": "p1",
    "name": "lan-production",
    "vm_ids": [],
    "created_at": "2026-10-16T10:15:30.123456Z"
  }
  ```
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Non membre du projet ou droit `vm.network` manquant.
  - `404` (`not_found`) : Projet `project_id` introuvable.
  - `409` (`conflict`) : Un réseau avec ce nom ou un slug équivalent existe déjà.
  - `422` (`validation_error`) : Nom vide ou supérieur à 128 caractères.
  - `503` (`upstream_unavailable`) : Port réseau externe indisponible. Aucune ligne n'est créée en base.

---

### `GET /api/v1/projects/{project_id}/networks` : Lister les réseaux du projet

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.view` ou `vm.network`.
- **Description** : Retourne la liste paginée des réseaux configurés dans le projet, avec les identifiants des VMs qui y sont rattachées. Fonctionne même en cas de panne du service réseau externe (lecture du dernier état connu en base).
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant unique du projet.
  - `page` (requête, optionnel, défaut `1`, minimum `1`) : Numéro de la page demandée.
  - `page_size` (requête, optionnel, défaut `20`, minimum `1`, maximum `100`) : Nombre d'éléments par page.
- **Corps** : Aucun.
- **Réponse `200 OK` (`Page[NetworkOut]`)** :
  ```json
  {
    "items": [
      {
        "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
        "project_id": "p1",
        "name": "lan-production",
        "vm_ids": ["vm-app-1", "vm-db-1"],
        "created_at": "2026-10-16T10:15:30.123456Z"
      }
    ],
    "total": 1,
    "page": 1,
    "page_size": 20
  }
  ```
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Non membre du projet ou droits manquants.
  - `404` (`not_found`) : Projet introuvable.
  - `422` (`validation_error`) : Paramètres de pagination non conformes (ex: `page_size > 100`).

---

### `GET /api/v1/projects/{project_id}/networks/{network_id}` : Consulter un réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.view` ou `vm.network`.
- **Description** : Renvoie le détail d'un réseau spécifique au sein du projet, avec la liste de ses VMs rattachées.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant du projet.
  - `network_id` (chemin, obligatoire) : Identifiant du réseau.
- **Corps** : Aucun.
- **Réponse `200 OK` (`NetworkOut`)** :
  ```json
  {
    "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
    "project_id": "p1",
    "name": "lan-production",
    "vm_ids": ["vm-app-1", "vm-db-1"],
    "created_at": "2026-10-16T10:15:30.123456Z"
  }
  ```
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Non membre du projet ou droits insuffisants.
  - `404` (`not_found`) : Projet ou réseau introuvable, ou réseau rattaché à un autre projet.

---

### `PATCH /api/v1/projects/{project_id}/networks/{network_id}` : Renommer un réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.network`.
- **Description** : Met à jour le nom d'un réseau existant dans le projet. Journalise l'audit `network.renamed` avec l'ancien et le nouveau nom.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant du projet.
  - `network_id` (chemin, obligatoire) : Identifiant du réseau.
- **Corps (`NetworkUpdateIn`)** :
  - `name` (chaîne, obligatoire) : Nouveau nom (1 à 128 caractères). Le slug doit être unique dans le système.
  ```json
  {
    "name": "lan-production-v2"
  }
  ```
- **Réponse `200 OK` (`NetworkOut`)** :
  ```json
  {
    "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
    "project_id": "p1",
    "name": "lan-production-v2",
    "vm_ids": ["vm-app-1", "vm-db-1"],
    "created_at": "2026-10-16T10:15:30.123456Z"
  }
  ```
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Non membre ou droit `vm.network` manquant.
  - `404` (`not_found`) : Projet ou réseau introuvable.
  - `409` (`conflict`) : Nouveau nom en conflit avec un réseau existant.
  - `422` (`validation_error`) : Contraintes de nom non respectées.

---

### `POST /api/v1/projects/{project_id}/networks/{network_id}/vms` : Rattacher une VM au réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.network`.
- **Description** : Rattache une machine virtuelle au réseau. La VM doit être visible dans le projet (soit créée dans le projet, soit partagée activement vers celui-ci via `resource_shares`). Tout espace de stockage est refusé. L'opération est idempotente (aucun effet de bord ni erreur si déjà rattachée). Journalise `network.vm_attached`.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant du projet.
  - `network_id` (chemin, obligatoire) : Identifiant du réseau.
- **Corps (`NetworkMembershipIn`)** :
  - `vm_id` (chaîne, obligatoire, 1 à 36 caractères) : Identifiant de la VM à rattacher.
  ```json
  {
    "vm_id": "vm-app-1"
  }
  ```
- **Réponse `200 OK` (`NetworkOut`)** :
  ```json
  {
    "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
    "project_id": "p1",
    "name": "lan-production",
    "vm_ids": ["vm-app-1"],
    "created_at": "2026-10-16T10:15:30.123456Z"
  }
  ```
- **Erreurs** :
  - `400` (`bad_request`) : L'identifiant correspond à un espace de stockage (interdiction R22).
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Droit `vm.network` manquant, ou VM non visible dans le projet.
  - `404` (`not_found`) : Projet, réseau ou VM introuvable.
  - `409` (`invalid_state`) : La VM est en cours de suppression (`deleting`).
  - `503` (`upstream_unavailable`) : Port réseau externe indisponible. Aucun lien n'est enregistré.

---

### `DELETE /api/v1/projects/{project_id}/networks/{network_id}/vms/{vm_id}` : Retirer une VM du réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.network`.
- **Description** : Déconnecte la VM du réseau. L'opération est idempotente : si la VM n'était pas dans le réseau, l'appel réussit sans modification. Journalise `network.vm_detached`.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant du projet.
  - `network_id` (chemin, obligatoire) : Identifiant du réseau.
  - `vm_id` (chemin, obligatoire) : Identifiant de la VM à retirer.
- **Corps** : Aucun.
- **Réponse `200 OK` (`NetworkOut`)** :
  ```json
  {
    "id": "e917d0c3-f661-414f-9a40-271d4cb80479",
    "project_id": "p1",
    "name": "lan-production",
    "vm_ids": [],
    "created_at": "2026-10-16T10:15:30.123456Z"
  }
  ```
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Droit `vm.network` manquant ou non membre.
  - `404` (`not_found`) : Projet ou réseau introuvable.
  - `503` (`upstream_unavailable`) : Port externe indisponible. Le lien en base reste conservé.

---

### `DELETE /api/v1/projects/{project_id}/networks/{network_id}` : Supprimer un réseau

- **Accès** : Propriétaire du projet ou invité avec le droit `vm.network`.
- **Description** : Supprime le réseau de l'infrastructure externe puis de la base de données locale. Supprime en cascade toutes les associations de rattachement de VMs (`network_vms`). Journalise `network.deleted`.
- **Paramètres de route / Query params** :
  - `project_id` (chemin, obligatoire) : Identifiant du projet.
  - `network_id` (chemin, obligatoire) : Identifiant du réseau.
- **Corps** : Aucun.
- **Réponse `204 No Content`** : Corps vide.
- **Erreurs** :
  - `401` (`unauthorized`) : Jeton absent ou invalide.
  - `403` (`forbidden`) : Droit `vm.network` manquant ou non membre.
  - `404` (`not_found`) : Projet ou réseau introuvable.
  - `503` (`upstream_unavailable`) : Port externe indisponible. Le réseau et ses liaisons restent conservés.

---

## Fonctions d'intégration internes

Ces fonctions Python sont exposées par `app.features.networks.service` pour permettre aux modules partenaires d'orchestrer la cohérence globale du système sans couplage HTTP direct :

1. `detach_vm_from_all_networks(db: Session, network_port: NetworkPort, *, vm_id: str) -> None` :
   - **Appelant prévu** : Équipe VM (NAOMI, lors de `delete_vm` F6, R21).
   - **Comportement** : Déconnecte la VM de tous les réseaux auxquels elle appartient (tous projets confondus) sur le port externe et en base. Idempotent et rejouable.
2. `detach_vm_from_project_networks(db: Session, network_port: NetworkPort, *, vm_id: str, project_id: str) -> None` :
   - **Appelant prévu** : Moteur de partages (`shares.service`, lors de `revoke_share` F14, R21).
   - **Comportement** : Déconnecte la VM de tous les réseaux du projet spécifié.
3. `delete_project_networks(db: Session, network_port: NetworkPort, *, project_id: str) -> None` :
   - **Appelant prévu** : Équipe Projets / IAM (ZUCHUON, lors de `delete_project` F12, R23).
   - **Comportement** : Supprime tous les réseaux du projet et leurs liaisons.
4. `list_vm_networks(db: Session, *, vm_id: str, project_id: str | None = None) -> list[Network]` :
   - **Appelant prévu** : Toute fonctionnalité devant inspecter l'appartenance réseau d'une machine.

---

## Périmètre actuel

- **Entièrement couvert et validé** :
  - Création, liste paginée, consultation unitaire, renommage et suppression de réseau.
  - Rattachement et détachement de VMs (d'origine ou partagées).
  - Contrôle d'accès rigoureux via `app/shared/policies/access.py` (Figure 3).
  - Traçabilité complète via `app/core/audit.py`.
  - Résilience aux pannes et atomicité (aucun état à moitié appliqué en cas de panne réseau).
  - Fonctions d'intégration prêtes pour NAOMI, ZUCHUON et le socle partagé.
- **Hors périmètre du sous-système réseau** :
  - Gestion du cycle de vie des VMs (création/démarrage/extinction : responsabilité de NAOMI).
  - Gestion des espaces de stockage (responsabilité de TABA).
  - Attribution des adresses IP / sous-réseaux IP fins (gérés par le groupe Réseau en aval du port).
