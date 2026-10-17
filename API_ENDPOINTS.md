# API IaaS — Catalogue des endpoints

## 1. Contrat général

### 1.1 Format, version et authentification

- Préfixe des routes métier : `/api/v1`.
- Corps et réponses métier : JSON (`Content-Type: application/json`), sauf réponse sans corps explicitement indiquée.
- Routes protégées : `Authorization: Bearer <access_token>`.
- `401 Unauthorized` si le jeton est absent, invalide ou expiré.
- `admin` désigne le rôle global administrateur ; il ne remplace pas les droits détenus au niveau d'un projet.

### 1.2 Contrôle d'accès aux ressources

Pour agir dans un projet `{project_id}`, l'appelant doit être membre de ce projet. Une ressource est accessible si elle a pour projet d'origine `{project_id}` ou si un partage actif la rend visible dans ce projet. Le propriétaire dispose de tous les droits sur son projet. Un invité doit détenir le droit requis dans le projet de l'URL. Un partage ne transmet aucun droit.

Un refus d'accès ne doit pas révéler si une ressource d'un autre projet existe. Selon la politique de visibilité retenue pour la route, elle répond `403 forbidden` (ressource non visible/droit insuffisant) ou `404 not_found` (ID inexistant ou ressource non rattachée au projet demandé). Ce comportement doit être appliqué uniformément par ressource.

### 1.3 Pagination et filtres

Tous les endpoints de liste utilisent les paramètres suivants, sauf indication contraire :

| Paramètre | Emplacement | Type | Défaut | Règle |
|---|---|---|---:|---|
| `page` | query | entier | `1` | `>= 1` |
| `page_size` | query | entier | `20` | de `1` à `100` |

Tous les résultats paginés ont cette enveloppe :

```json
{
  "items": [],
  "page": 1,
  "page_size": 20,
  "total_items": 0,
  "total_pages": 0
}
```

`total_items` est le nombre total d'éléments correspondant aux filtres avant pagination. `total_pages` vaut `0` si `total_items` vaut `0`, sinon `ceil(total_items / page_size)`. Si `page` dépasse `total_pages`, l'API renvoie `200 OK`, `items: []` et conserve les totaux calculés. Même une liste administrative ou une liste de profils utilise exactement ces noms de champs.

Un filtre est facultatif lorsqu'il est omis. Une valeur de filtre invalide renvoie `422 validation_error`; elle n'est jamais silencieusement ignorée. Les champs et valeurs filtrables sont définis explicitement dans chaque route concernée.

### 1.4 Format d'erreur

Toutes les erreurs métier suivent cette structure :

```json
{
  "error": {
    "code": "forbidden",
    "message": "Le droit vm.view est requis dans ce projet.",
    "details": null
  }
}
```

| HTTP | `error.code` | Sens |
|---:|---|---|
| `400` | `bad_request` | Corps incohérent, confirmation de suppression incorrecte ou manquante |
| `401` | `unauthorized` | Authentification manquante ou invalide |
| `403` | `forbidden` | Membre/droit requis manquant, action interdite |
| `404` | `not_found` | Identifiant inconnu ou ressource non visible dans le projet |
| `409` | `conflict` | Unicité en conflit ou opération incompatible déjà en cours |
| `409` | `invalid_state` | État courant ne permettant pas l'action |
| `422` | `validation_error` | Corps, paramètre de route ou filtre invalide |
| `503` | `upstream_unavailable` | Service externe indisponible ; aucun succès métier partiel n'est annoncé |

Exemple d'erreur de validation :

```json
{
  "error": {
    "code": "validation_error",
    "message": "Le champ page_size doit être compris entre 1 et 100.",
    "details": { "field": "page_size", "minimum": 1, "maximum": 100 }
  }
}
```

### 1.5 Suppression avec texte de confirmation

La suppression d'une **VM, d'un projet, d'un stockage ou d'un réseau** se fait toujours en deux appels sur la même route `POST .../deletion`. Il ne s'agit pas d'une demande de suppression soumise à l'administrateur.

1. **Prévisualisation** : le frontend envoie la route avec `{}` (ou sans `confirmation_text`). Le backend ne supprime rien et répond `200 OK` avec un avertissement et une chaîne `confirmation_text`.
2. **Confirmation** : le frontend renvoie exactement la valeur de `confirmation_text` dans le même champ. Le backend compare la chaîne à la valeur attendue pour cette ressource. Si elle correspond, il effectue la suppression et répond `200 OK` avec `deleted: true`. Sinon il répond `400 bad_request`, sans suppression.

Modèle de prévisualisation commun :

```json
{
  "confirmation_required": true,
  "confirmation_text": "SUPPRIMER vm-web-01",
  "warning": "La suppression de la VM vm-web-01 est définitive."
}
```

Corps de confirmation :

```json
{
  "confirmation_text": "SUPPRIMER vm-web-01"
}
```

Réponse en cas de réussite :

```json
{
  "deleted": true,
  "resource_type": "vm",
  "resource_id": "vm-123",
  "message": "La VM vm-web-01 a bien été supprimée."
}
```

La chaîne `SUPPRIMER <nom>` est lisible et non ambiguë. Le frontend doit afficher la chaîne renvoyée puis la soumettre sans la reconstruire ni la normaliser. Le backend compare la chaîne exactement et au contexte de la ressource visée par la route. Un mauvais texte ne supprime rien. Les effets externes nécessaires doivent réussir avant que la suppression soit confirmée ; en cas de panne, le backend répond `503` et ne renvoie jamais `{"deleted": true}`. La suppression est idempotente uniquement si elle est explicitement décidée ainsi pour la route ; par défaut, une nouvelle tentative sur une ressource supprimée renvoie `404`.

## 2. Modèles JSON communs

Les noms ci-dessous définissent les contrats de réponse et les corps utilisés dans les routes. Les champs sont obligatoires sauf mention `nullable` ou `optionnel`. Les identifiants sont des chaînes opaques, sauf `profile_id` et `request_id`, entiers.

### 2.1 Identité et jeton

`TokenOut` :

```json
{
  "access_token": "<jeton>",
  "token_type": "bearer",
  "expires_in": 3600
}
```

`IdentityOut` :

```json
{
  "user_id": "usr-123",
  "email": "alice@iaas.cm",
  "first_name": "Alice",
  "last_name": "Ngono",
  "role": "user"
}
```

`role` vaut `user` ou `admin`.

### 2.2 Projet, membre, invitation et profil

`ProjectOut` :

```json
{
  "id": "prj-alpha",
  "name": "Projet alpha",
  "owner_id": "usr-123",
  "current_user_role": "owner",
  "created_at": "2026-10-15T09:24:02Z"
}
```

`current_user_role` vaut `owner` ou `guest`; il apparaît dans les listes et lectures de projet adressées à l'utilisateur courant.

`ProjectMemberOut` :

```json
{
  "user_id": "usr-456",
  "role": "guest",
  "profile_id": 2,
  "rights": ["vm.view", "storage.view"],
  "joined_at": "2026-10-16T10:00:00Z"
}
```

`InvitationOut` :

```json
{
  "id": "inv-123",
  "project_id": "prj-alpha",
  "project_name": "Projet alpha",
  "inviter_id": "usr-123",
  "invitee_id": "usr-456",
  "status": "sent",
  "profile_id": 2,
  "additional_rights": ["vm.request_create"],
  "created_at": "2026-10-16T10:00:00Z",
  "updated_at": "2026-10-16T10:00:00Z"
}
```

`status` vaut `sent`, `accepted`, `refused` ou `cancelled`.
`invitee_id` désigne l'identité connue de l'IAM.

`RightOut` contient `code` et `description`.
`ProfileOut` contient `id` (entier), `name`, `description` et `rights` (liste de codes).

### 2.3 Ressources matérielles, adresse IP comprise

L'adresse IP est un attribut de première classe de la VM et du stockage. Les deux modèles ci-dessous l'exposent sous le nom stable `ip_address`. La valeur est une chaîne IPv4 ou IPv6 ; elle vaut `null` si l'adresse n'a pas encore été attribuée ou si le fournisseur ne l'a pas encore retournée. Les unités des ressources matérielles sont explicites : RAM, VRAM et SSD en Go, CPU en nombre de vCPU.

`VMOut` :

```json
{
  "id": "vm-123",
  "origin_project_id": "prj-alpha",
  "name": "web-01",
  "ip_address": "192.0.2.24",
  "ram_gb": 8,
  "vcpu": 4,
  "vram_gb": 0,
  "ssd_gb": 80,
  "state": "running",
  "shared": false,
  "created_at": "2026-10-16T10:00:00Z"
}
```

Valeurs possibles de `state` : `pending`, `creating`, `stopped`, `running`, `deleting`, `error`. Une valeur inconnue du backend est exposée comme `unknown`, sans être transformée en état de réussite.

`StorageOut` :

```json
{
  "id": "st-456",
  "origin_project_id": "prj-alpha",
  "name": "backup-alpha",
  "ip_address": "192.0.2.80",
  "size_gb": 50,
  "state": "available",
  "shared": false,
  "created_at": "2026-10-15T09:24:02Z"
}
```

`ip_address` désigne l'adresse IP associée au stockage.

`NetworkOut` :

```json
{
  "id": "net-789",
  "project_id": "prj-alpha",
  "name": "lan-production",
  "vm_ids": ["vm-123"],
  "created_at": "2026-10-16T10:15:30Z"
}
```

Un réseau ne contient que des VM visibles dans son projet. Les stockages ne sont jamais membres d'un réseau.

### 2.4 Demande et partage

`RequestOut` :

```json
{
  "id": 12,
  "project_id": "prj-alpha",
  "author_id": "usr-123",
  "kind": "storage_create",
  "status": "pending",
  "payload": { "name": "backup-alpha", "size_gb": 50 },
  "target_resource_type": null,
  "target_resource_id": null,
  "admin_note": null,
  "created_at": "2026-10-16T10:00:00Z",
  "updated_at": "2026-10-16T10:00:00Z",
  "decided_at": null
}
```

`kind` vaut `vm_create`, `vm_update`, `storage_create` ou `storage_update`.
`status` vaut `pending`, `accepted`, `refused` ou `cancelled`. `payload` est typé selon `kind`; une réponse de demande de VM acceptée peut aussi préciser la ressource résultante dans `target_resource_id`.

`ShareOut` :

```json
{
  "id": "shr-123",
  "resource_type": "storage",
  "resource_id": "st-456",
  "origin_project_id": "prj-alpha",
  "dest_project_id": "prj-beta",
  "created_by": "usr-123",
  "status": "active",
  "created_at": "2026-10-16T10:00:00Z"
}
```

`resource_type` vaut `vm` ou `storage`; `status` vaut `active` ou `revoked`.
Le partage est immédiat, ne transmet aucun droit et ne peut pas être réactivé après révocation.

### 2.5 Pack et pagination

`PackOut` :

```json
{
  "id": "pack-standard",
  "name": "Standard",
  "description": "Configuration générale",
  "ram_gb": 8,
  "vcpu": 4,
  "vram_gb": 0,
  "ssd_gb": 80,
  "created_at": "2026-10-15T09:24:02Z",
  "updated_at": "2026-10-15T09:24:02Z"
}
```

`Page[T]` signifie exactement :

```json
{
  "items": ["<éléments du type T>"],
  "page": 1,
  "page_size": 20,
  "total_items": 1,
  "total_pages": 1
}
```

## 3. Catalogue compact

Toutes les suppressions de projet, VM, stockage et réseau emploient `POST .../deletion` en deux temps (§1.5). Aucun endpoint de console n'est inclus.

| Méthode | Route exacte | Fonction |
|---|---|---|
| POST | `/api/v1/auth/login` | Connexion |
| GET | `/api/v1/auth/me` | Lire son identité |
| PATCH | `/api/v1/auth/me` | Modifier son compte |
| DELETE | `/api/v1/auth/me` | Supprimer son compte IAM |
| POST | `/api/v1/auth/password` | Changer le mot de passe |
| GET | `/api/v1/admin/rights` | Catalogue des droits |
| GET | `/api/v1/admin/profiles` | Lister les profils |
| POST | `/api/v1/admin/profiles` | Créer un profil |
| PATCH | `/api/v1/admin/profiles/{profile_id}` | Modifier un profil |
| DELETE | `/api/v1/admin/profiles/{profile_id}` | Supprimer un profil |
| GET | `/api/v1/projects` | Lister les projets |
| POST | `/api/v1/projects` | Créer un projet |
| GET | `/api/v1/projects/{project_id}` | Lire un projet |
| PATCH | `/api/v1/projects/{project_id}` | Renommer un projet |
| POST | `/api/v1/projects/{project_id}/deletion` | Prévisualiser/confirmer suppression projet |
| GET | `/api/v1/projects/{project_id}/members` | Lister les membres |
| PUT | `/api/v1/projects/{project_id}/members/{user_id}/rights` | Remplacer les droits d'un membre |
| DELETE | `/api/v1/projects/{project_id}/members/{user_id}` | Retirer un membre invité |
| GET | `/api/v1/projects/{project_id}/invitations` | Lister les invitations émises |
| POST | `/api/v1/projects/{project_id}/invitations` | Envoyer une invitation |
| GET | `/api/v1/invitations` | Lister les invitations reçues |
| POST | `/api/v1/invitations/{invitation_id}/accept` | Accepter une invitation |
| POST | `/api/v1/invitations/{invitation_id}/refuse` | Refuser une invitation |
| POST | `/api/v1/invitations/{invitation_id}/cancel` | Annuler une invitation |
| GET | `/api/v1/projects/{project_id}/shares` | Lister les partages reçus dans un projet |
| POST | `/api/v1/projects/{project_id}/vms` | Demander la création d'une VM |
| GET | `/api/v1/projects/{project_id}/vms` | Lister les VM visibles |
| GET | `/api/v1/projects/{project_id}/vms/{vm_id}` | Lire une VM |
| POST | `/api/v1/projects/{project_id}/vms/{vm_id}/update-requests` | Demander la modification d'une VM |
| POST | `/api/v1/projects/{project_id}/vms/{vm_id}/power` | Démarrer/arrêter/redémarrer une VM |
| POST | `/api/v1/projects/{project_id}/vms/{vm_id}/deletion` | Prévisualiser/confirmer suppression VM |
| POST | `/api/v1/projects/{project_id}/networks` | Créer un réseau |
| GET | `/api/v1/projects/{project_id}/networks` | Lister les réseaux |
| GET | `/api/v1/projects/{project_id}/networks/{network_id}` | Lire un réseau |
| PATCH | `/api/v1/projects/{project_id}/networks/{network_id}` | Renommer un réseau |
| POST | `/api/v1/projects/{project_id}/networks/{network_id}/vms` | Rattacher une VM au réseau |
| DELETE | `/api/v1/projects/{project_id}/networks/{network_id}/vms/{vm_id}` | Détacher une VM du réseau |
| POST | `/api/v1/projects/{project_id}/networks/{network_id}/deletion` | Prévisualiser/confirmer suppression réseau |
| POST | `/api/v1/projects/{project_id}/storages` | Demander la création d'un stockage |
| GET | `/api/v1/projects/{project_id}/storages` | Lister les stockages |
| GET | `/api/v1/projects/{project_id}/storages/{storage_id}` | Lire un stockage |
| POST | `/api/v1/projects/{project_id}/storages/{storage_id}/update-requests` | Demander la modification d'un stockage |
| POST | `/api/v1/projects/{project_id}/storages/{storage_id}/deletion` | Prévisualiser/confirmer suppression stockage |
| POST | `/api/v1/projects/{project_id}/storages/{storage_id}/shares` | Créer un partage de stockage |
| GET | `/api/v1/projects/{project_id}/storages/{storage_id}/shares` | Lister les partages d'un stockage |
| POST | `/api/v1/projects/{project_id}/vms/{vm_id}/shares` | Créer un partage de VM |
| GET | `/api/v1/projects/{project_id}/vms/{vm_id}/shares` | Lister les partages d'une VM |
| POST | `/api/v1/shares/{share_id}/revoke` | Révoquer un partage |
| GET | `/api/v1/requests` | Lister les demandes |
| GET | `/api/v1/requests/{request_id}` | Lire une demande |
| POST | `/api/v1/requests/{request_id}/cancel` | Annuler une demande |
| POST | `/api/v1/requests/{request_id}/accept` | Accepter une demande |
| POST | `/api/v1/requests/{request_id}/refuse` | Refuser une demande |
| GET | `/api/v1/packs` | Lister les packs |
| GET | `/api/v1/packs/{pack_id}` | Lire un pack |
| POST | `/api/v1/admin/packs` | Créer un pack |
| PATCH | `/api/v1/admin/packs/{pack_id}` | Modifier un pack |
| DELETE | `/api/v1/admin/packs/{pack_id}` | Supprimer un pack |

Les ressources de projet (membres, invitations, VM et stockage) sont listées dans leurs propres routes ; un endpoint agrégé `/resources` n'est pas retenu pour éviter deux contrats de visibilité/pagination.

## 4. Authentification, compte et droits

### `POST /api/v1/auth/login` — Connexion

- Accès : public.
- Corps `LoginIn` : `email` (chaîne, minimum 3 caractères) et `password` (chaîne non vide).

  ```json
  { "email": "alice@iaas.cm", "password": "alice123" }
  ```

- Réponse `200 OK` : `TokenOut`.
- Erreurs : `401` identifiants incorrects ; `422` champ manquant/invalide.
- Un premier login peut créer la référence locale à l'identité. Durée du jeton par défaut : 3600 secondes, configurable.

### `GET /api/v1/auth/me` — Identité courante

- Accès : authentifié.
- Corps : aucun.
- Réponse `200 OK` : `IdentityOut`.
- Erreur : `401`.

### `PATCH /api/v1/auth/me` — Modifier son compte

- Accès : authentifié.
- Corps `UserUpdateIn`, tous champs optionnels :

  ```json
  { "email": "alice2@iaas.cm", "first_name": "Alice", "last_name": "Ngono" }
  ```

- Les champs omis ou `null` restent inchangés. `email` minimum 3 caractères ; prénom et nom non vides. Le mot de passe se change séparément.
- Réponse `200 OK` : nouveau `TokenOut`.
- Erreurs : `401`, `409` email déjà utilisé, `422`.

### `POST /api/v1/auth/password` — Changer le mot de passe

- Accès : authentifié.
- Corps `PasswordChangeIn` : ancien mot de passe non vide et nouveau mot de passe d'au moins 6 caractères.

  ```json
  { "old_password": "ancien-secret", "new_password": "nouveau-secret" }
  ```

- Réponse `204 No Content`, corps vide.
- Erreurs : `400` ancien mot de passe incorrect ; `401` ; `422`.

### `DELETE /api/v1/auth/me` — Supprimer son compte IAM

- Accès : authentifié.
- Corps : aucun.
- Effet : demande de suppression auprès de l'IAM puis suppression de la référence locale.
- Réponse `204 No Content`, corps vide.
- Erreur : `401`.

### `GET /api/v1/admin/rights` — Catalogue des droits

- Accès : authentifié.
- Query : aucune.
- Corps : aucun.
- Réponse `200 OK` : tableau `RightOut`, trié par `code`.
- Erreur : `401`.

### Profils `/api/v1/admin/profiles`

`ProfileCreateIn` : `name` requis (1–64 caractères), `description` optionnelle (maximum 255, défaut `""`), `rights` optionnel (défaut `[]`, chaque code doit exister). `ProfileUpdateIn` accepte les mêmes champs facultatifs ; `rights: []` retire tous les droits. Un champ omis ou `null` n'est pas modifié.

#### `GET /api/v1/admin/profiles`

- Accès : authentifié.
- Query : `page`, `page_size`; tri par `name` ascendant.
- Corps : aucun.
- Réponse `200 OK` : `Page[ProfileOut]`.
- Erreurs : `401`, `422`.

#### `POST /api/v1/admin/profiles`

- Accès : `admin`.
- Corps :

  ```json
  { "name": "Gestion VM", "description": "Droits VM", "rights": ["vm.view", "vm.power"] }
  ```

- Réponse `201 Created` : `ProfileOut`.
- Erreurs : `401`, `403`, `409` nom existant, `422` ou droit inconnu.

#### `PATCH /api/v1/admin/profiles/{profile_id}`

- Accès : `admin`.
- Paramètre : `profile_id` entier positif.
- Corps : `ProfileUpdateIn`.
- Réponse `200 OK` : `ProfileOut` modifié.
- Erreurs : `401`, `403`, `404`, `409`, `422`.

#### `DELETE /api/v1/admin/profiles/{profile_id}`

- Accès : `admin`.
- Paramètre : `profile_id` entier positif.
- Corps : aucun.
- Réponse `204 No Content`, corps vide.
- Erreurs : `401`, `403`, `404`.

## 5. Projets, membres et invitations

### Projets

#### `GET /api/v1/projects`

- Accès : utilisateur authentifié ; ne retourne que les projets dont il est propriétaire ou membre.
- Query : `page`, `page_size`; tri `name` ascendant.
- Corps : aucun.
- Réponse `200 OK` : `Page[ProjectOut]`.
- Erreurs : `401`, `422`.

#### `POST /api/v1/projects`

- Accès : utilisateur authentifié.
- Corps `ProjectCreateIn` : `name`, chaîne non vide (1–128 caractères).

  ```json
  { "name": "Projet alpha" }
  ```

- Réponse `201 Created` : `ProjectOut`; l'utilisateur est propriétaire.
- Erreurs : `401`, `422`.

#### `GET /api/v1/projects/{project_id}`

- Accès : membre du projet.
- Paramètre : `project_id`, identifiant opaque.
- Corps : aucun.
- Réponse `200 OK` : `ProjectOut`.
- Erreurs : `401`, `403`, `404`.

#### `PATCH /api/v1/projects/{project_id}`

- Accès : propriétaire.
- Corps `ProjectUpdateIn` :

  ```json
  { "name": "Projet alpha v2" }
  ```

- Le nom est unique parmi les projets du propriétaire.
- Réponse `200 OK` : `ProjectOut` mis à jour.
- Erreurs : `401`, `403`, `404`, `409` nom déjà utilisé par un autre projet du propriétaire, `422`.

#### `POST /api/v1/projects/{project_id}/deletion`

- Accès : propriétaire.
- Paramètre : `project_id`.
- Corps phase 1 : `{}`. Réponse `200 OK` : modèle commun de prévisualisation ; `confirmation_text` est `SUPPRIMER <nom du projet>`. L'avertissement précise le nombre de VM, stockages, réseaux et partages affectés.
- Corps phase 2 : `{"confirmation_text": "SUPPRIMER Projet alpha"}` avec la chaîne exacte reçue à l'étape 1.
- Réponse phase 2 `200 OK` :

  ```json
  {
    "deleted": true,
    "resource_type": "project",
    "resource_id": "prj-alpha",
    "message": "Le projet Projet alpha et ses ressources ont bien été supprimés."
  }
  ```

- Effets : suppression en cascade des ressources originaires du projet avec leurs effets propres, réseaux, invitations, appartenances, demandes en attente et partages concernés. Les ressources d'autres projets partagées vers celui-ci restent intactes ; seuls les partages vers le projet supprimé sont révoqués.
- Erreurs : `400` texte manquant/incorrect, `401`, `403`, `404`, `503` si une dépendance nécessaire échoue. Aucun élément local n'est marqué supprimé en cas d'échec externe.

### Membres

#### `GET /api/v1/projects/{project_id}/members`

- Accès : membre du projet.
- Query : `page`, `page_size`; filtre `role` optionnel, valeurs `owner` ou `guest`. Au plus un propriétaire par projet.
- Corps : aucun.
- Réponse `200 OK` : `Page[ProjectMemberOut]`.
- Erreurs : `401`, `403`, `404`, `422`.

#### `PUT /api/v1/projects/{project_id}/members/{user_id}/rights`

- Accès : propriétaire ; le membre modifiant les droits d'un autre doit être propriétaire, pas seulement invité habilité à inviter.
- Corps `MemberRightsUpdateIn` :

  ```json
  { "profile_id": 2, "additional_rights": ["vm.request_create"] }
  ```

- `profile_id` entier positif ou `null`; `additional_rights` est une liste de codes de droits. Les droits effectifs sont l'union profil + droits additionnels. Le propriétaire n'est pas modifiable comme un invité.
- Réponse `200 OK` : `ProjectMemberOut` mis à jour.
- Erreurs : `401`, `403`, `404`, `422`.

#### `DELETE /api/v1/projects/{project_id}/members/{user_id}`

- Accès : propriétaire.
- Corps : aucun.
- Effet : retire un membre invité et ses droits. Le propriétaire ne peut pas être retiré (`409 invalid_state`).
- Réponse `204 No Content`, corps vide.
- Erreurs : `401`, `403`, `404`, `409`.

### Invitations

#### `POST /api/v1/projects/{project_id}/invitations`

- Accès : propriétaire ou membre disposant de `project.invite`.
- Corps `InvitationCreateIn` :

  ```json
  {
    "invitee_id": "usr-456",
    "profile_id": 2,
    "additional_rights": ["vm.request_create"]
  }
  ```

- Un utilisateur invité ne peut octroyer que les droits qu'il détient lui-même. `invitee_id` doit être une identité valide auprès de l'IAM. Invitation envoyée en état `sent`; l'invité doit l'accepter avant de devenir membre.
- Réponse `201 Created` : `InvitationOut`.
- Erreurs : `401`, `403`, `404` projet/profil/identité, `409` déjà membre ou invitation `sent` déjà existante, `422`.

#### `GET /api/v1/projects/{project_id}/invitations`

- Accès : propriétaire ou membre avec `project.invite`.
- Query : `page`, `page_size`; `status` optionnel parmi `sent`, `accepted`, `refused`, `cancelled`; `invitee_id` optionnel pour filtrer une identité précise. Les filtres se combinent en ET.
- Corps : aucun.
- Réponse `200 OK` : `Page[InvitationOut]`.
- Erreurs : `401`, `403`, `404`, `422`.

#### `GET /api/v1/invitations`

- Accès : utilisateur authentifié ; retourne les invitations dont il est le destinataire.
- Query : `page`, `page_size`; `status` optionnel parmi `sent`, `accepted`, `refused`, `cancelled`.
- Corps : aucun.
- Réponse `200 OK` : `Page[InvitationOut]`.
- Erreurs : `401`, `422`.

#### `POST /api/v1/invitations/{invitation_id}/accept`

- Accès : destinataire uniquement ; `invitation_id` chaîne opaque.
- Corps : aucun.
- Réponse `200 OK` : `InvitationOut` avec `status: "accepted"`. L'acceptation crée l'appartenance au projet avec les droits inscrits dans l'invitation.
- Erreurs : `401`, `403`, `404`, `409` invitation non `sent`.

#### `POST /api/v1/invitations/{invitation_id}/refuse`

- Accès : destinataire uniquement ; `invitation_id` chaîne opaque.
- Corps : aucun.
- Réponse `200 OK` : `InvitationOut` avec `status: "refused"`.
- Erreurs : `401`, `403`, `404`, `409` invitation non `sent`.

#### `POST /api/v1/invitations/{invitation_id}/cancel`

- Accès : auteur de l'invitation ou propriétaire du projet.
- Corps : aucun.
- Réponse `200 OK` : `InvitationOut` avec `status: "cancelled"`.
- Erreurs : `401`, `403`, `404`, `409` invitation non `sent`.

## 6. Machines virtuelles

Les routes de VM incluent l'adresse IP `ip_address` dans toutes les réponses `VMOut`, y compris les éléments de liste. Les IP ne sont pas des filtres par défaut, mais la liste permet explicitement le filtre exact `ip_address`.

### `POST /api/v1/projects/{project_id}/vms` — Demander création VM

- Accès : propriétaire ou invité avec `vm.request_create`.
- Corps `VMCreateRequestIn` : `name` non vide, et exactement un des champs `pack_id` ou `configuration`.

  ```json
  { "name": "web-01", "pack_id": "pack-standard" }
  ```

  ou :

  ```json
  {
    "name": "web-01",
    "configuration": {
      "ram_gb": 8,
      "vcpu": 4,
      "vram_gb": 0,
      "ssd_gb": 80
    }
  }
  ```

- Les valeurs de configuration doivent être positives ou nulles selon la ressource : `ram_gb >= 1`, `vcpu >= 1`, `vram_gb >= 0`, `ssd_gb >= 1`. En mode pack, les valeurs proviennent du pack au dépôt.
- Réponse `201 Created` : `RequestOut` (`kind: "vm_create"`, `status: "pending"`, `payload` contenant le nom et le pack ou la configuration, cible nulle jusqu'à création).
- Erreurs : `401`, `403`, `404` projet/pack, `422` si ni les deux modes ou les deux modes sont fournis.

### `GET /api/v1/projects/{project_id}/vms`

- Accès : propriétaire ou invité avec `vm.view`.
- Query :
  - pagination commune ;
  - `state` optionnel : état exact (`pending`, `creating`, `stopped`, `running`, `deleting`, `error`, `unknown`) ;
  - `shared` optionnel : `true` pour uniquement les VM partagées vers le projet, `false` pour uniquement les VM originaires du projet ;
  - `ip_address` optionnel : correspondance exacte d'adresse IPv4 ou IPv6 ;
  - `name` optionnel : recherche insensible à la casse par préfixe.
  Les filtres se combinent en ET. Tri par `name` puis `id`, ascendant.
- Corps : aucun.
- Réponse `200 OK` : `Page[VMOut]`; chaque VM expose son IP.
- Erreurs : `401`, `403`, `404` projet, `422` filtre/pagination invalide.

### `GET /api/v1/projects/{project_id}/vms/{vm_id}`

- Accès : propriétaire ou invité avec `vm.view`; VM visible dans le projet.
- Corps : aucun.
- Réponse `200 OK` : `VMOut`, avec `ip_address`.
- Erreurs : `401`, `403`, `404`.

### `POST /api/v1/projects/{project_id}/vms/{vm_id}/update-requests`

- Accès : propriétaire ou invité avec `vm.request_update`.
- Corps `VMUpdateRequestIn` :

  ```json
  { "configuration": { "ram_gb": 16, "vcpu": 8, "vram_gb": 0, "ssd_gb": 120 } }
  ```

- La configuration proposée représente l'état complet souhaité des caractéristiques modifiables. La VM existante reste inchangée avant décision.
- Réponse `202 Accepted` : `RequestOut` (`kind: "vm_update"`, `status: "pending"`, `target_resource_type: "vm"`, `target_resource_id: "{vm_id}"`).
- Erreurs : `401`, `403`, `404`, `409 invalid_state` VM en suppression, `409 conflict` demande identique déjà en attente, `422`.

### `POST /api/v1/projects/{project_id}/vms/{vm_id}/power`

- Accès : propriétaire ou invité avec `vm.power`.
- Corps `VMPowerIn` : `{"action": "start"}`, `action` étant exactement `start`, `stop` ou `restart`.
- Réponse `202 Accepted` :

  ```json
  { "vm_id": "vm-123", "action": "start", "state": "starting" }
  ```

- Erreurs : `401`, `403`, `404`, `409 invalid_state`, `422`, `503` hyperviseur indisponible.

### `POST /api/v1/projects/{project_id}/vms/{vm_id}/deletion`

- Accès : propriétaire ou invité avec `vm.delete`.
- Corps et réponses : protocole §1.5. Phase 1 donne `confirmation_text` du type `SUPPRIMER web-01`; phase 2 reçoit exactement cette valeur et répond au succès avec `resource_type: "vm"`.
- Avant succès, révoque les partages, retire la VM de tous ses réseaux et demande au service DNS tiers la suppression du nom de domaine associé. Ces effets sont orchestrés en interne.
- Erreurs : `400`, `401`, `403`, `404`, `409 invalid_state`, `503` dépendance indisponible. En cas d'échec, aucune réponse `deleted: true`.

## 7. Réseaux

Base : `/api/v1/projects/{project_id}/networks`. Écriture : propriétaire ou `vm.network`. Lecture : propriétaire ou `vm.view` ou `vm.network`. Le réseau peut relier les VM originaires du projet et les VM partagées activement vers ce projet. Il est impossible d'y rattacher un stockage.

### `POST /api/v1/projects/{project_id}/networks`

- Accès : propriétaire ou invité avec `vm.network`.
- Corps `NetworkCreateIn` : `{"name": "lan-production"}` ; chaîne 1–128 caractères, non blanche après trim.
- Réponse `201 Created` : `NetworkOut`, avec `vm_ids: []`.
- Erreurs : `401`, `403`, `404` projet, `409` nom/slug déjà pris, `422`, `503` service réseau indisponible.

### `GET /api/v1/projects/{project_id}/networks`

- Accès : propriétaire ou invité avec `vm.view` ou `vm.network`.
- Query : pagination commune ; filtre `name` optionnel, recherche insensible à la casse par préfixe. Tri par `name` puis `id`, ascendant.
- Corps : aucun.
- Réponse `200 OK` : `Page[NetworkOut]`. La lecture renvoie l'état local connu et n'exige pas que le service externe soit disponible.
- Erreurs : `401`, `403`, `404` projet, `422`.

### `GET /api/v1/projects/{project_id}/networks/{network_id}`

- Accès : propriétaire ou invité avec `vm.view` ou `vm.network`.
- Corps : aucun.
- Réponse `200 OK` : `NetworkOut`.
- Erreurs : `401`, `403`, `404` projet/réseau ou réseau non associé au projet fourni.

### `PATCH /api/v1/projects/{project_id}/networks/{network_id}`

- Accès : propriétaire ou invité avec `vm.network`.
- Corps `NetworkUpdateIn` : `{"name": "lan-production-v2"}`, nom de 1–128 caractères non blancs après trim.
- Réponse `200 OK` : `NetworkOut` mis à jour.
- Erreurs : `401`, `403`, `404`, `409` nom/slug en conflit, `422`, `503` si le renommage externe échoue.

### `POST /api/v1/projects/{project_id}/networks/{network_id}/vms`

- Accès : propriétaire ou invité avec `vm.network`.
- Corps `NetworkMembershipIn` : `{"vm_id": "vm-123"}`.
- La VM doit être visible dans le projet. Ajout idempotent.
- Réponse `200 OK` : `NetworkOut` à jour.
- Erreurs : `400` ID identifié comme stockage, `401`, `403`, `404`, `409 invalid_state` VM en suppression, `422`, `503`.

### `DELETE /api/v1/projects/{project_id}/networks/{network_id}/vms/{vm_id}`

- Accès : propriétaire ou invité avec `vm.network`.
- Corps : aucun.
- Retrait idempotent.
- Réponse `200 OK` : `NetworkOut` à jour.
- Erreurs : `401`, `403`, `404`, `503`. En cas d'échec externe, le rattachement local est conservé.

### `POST /api/v1/projects/{project_id}/networks/{network_id}/deletion`

- Accès : propriétaire ou invité avec `vm.network`.
- Corps/réponses : protocole §1.5. Le texte est construit à partir du nom du réseau ; l'avertissement indique combien de VM seront déconnectées.
- Phase 2 réussie : `200 OK`, réponse commune, `resource_type: "network"`.
- Erreurs : `400`, `401`, `403`, `404`, `503`. Une panne du service réseau ne supprime ni le réseau local ni ses associations.

Les fonctions d'intégration réseau (détachement à la suppression VM/projet ou à la révocation d'un partage) sont des services internes, pas des routes HTTP.

## 8. Stockages

Base : `/api/v1/projects/{project_id}/storages`. Écriture/lecture selon les droits `storage.*` dans le projet. `StorageOut` comprend toujours `ip_address` (§2.3), y compris dans les éléments paginés.

### `POST /api/v1/projects/{project_id}/storages` — Demander une création

- Accès : propriétaire ou invité avec `storage.request_create`.
- Corps `StorageCreateRequestIn` :

  ```json
  { "name": "backup-alpha", "size_gb": 50 }
  ```

- `name` : 1–128 caractères après trim et non blanc. `size_gb` : entier strictement positif. Le stockage n'existe pas avant acceptation de la demande ; son adresse IP est inconnue à ce stade.
- Réponse `201 Created` : `RequestOut`, `kind: "storage_create"`, `status: "pending"`, payload reprenant `name` et `size_gb`.
- Erreurs : `401`, `403`, `404` projet, `422`.

### `GET /api/v1/projects/{project_id}/storages`

- Accès : propriétaire ou invité avec `storage.view`.
- Query :
  - pagination commune ;
  - `state` optionnel : `available` ou `deleting` ;
  - `shared` optionnel : `true` uniquement les partages reçus, `false` uniquement les ressources d'origine ;
  - `ip_address` optionnel : adresse exacte IPv4/IPv6 ;
  - `name` optionnel : préfixe insensible à la casse.
  Les filtres se combinent en ET. Tri par `name` puis `id`, ascendant.
- Corps : aucun.
- Réponse `200 OK` : `Page[StorageOut]`; `ip_address` vaut `null` si pas encore fournie. Les partages révoqués sont exclus.
- Erreurs : `401`, `403`, `404` projet, `422`.

### `GET /api/v1/projects/{project_id}/storages/{storage_id}`

- Accès : propriétaire ou invité avec `storage.view`; stockage visible dans le projet de l'URL.
- Corps : aucun.
- Réponse `200 OK` : `StorageOut`, avec `ip_address`.
- Erreurs : `401`, `403`, `404`.

### `POST /api/v1/projects/{project_id}/storages/{storage_id}/update-requests`

- Accès : propriétaire ou invité avec `storage.request_update`.
- Corps `StorageUpdateRequestIn` : `{"size_gb": 200}` ; entier strictement positif.
- Réponse `202 Accepted` : `RequestOut` (`kind: "storage_update"`, `status: "pending"`, `target_resource_type: "storage"`, `target_resource_id: "{storage_id}"`). La taille actuelle n'est pas modifiée.
- Erreurs : `400` taille identique à l'actuelle, `401`, `403`, `404`, `409 conflict` demande déjà en attente (retourner son `request_id` dans `details`), `409 invalid_state` stockage en suppression, `422`.

### `POST /api/v1/projects/{project_id}/storages/{storage_id}/deletion`

- Accès : propriétaire ou invité avec `storage.delete`.
- Corps/réponses : protocole §1.5. Phase 1 renvoie une chaîne formée avec le nom du stockage et un avertissement indiquant que les données seront perdues, même si le stockage est non vide, et le nombre de partages actifs révoqués.
- Phase 2 : texte exact dans `confirmation_text`.
- Réponse phase 2 `200 OK` : commune, `resource_type: "storage"`.
- Effets : suppression auprès du fournisseur, révocation de tous les partages.
- Erreurs : `400`, `401`, `403`, `404`, `503`. Si le fournisseur échoue, rien n'est marqué supprimé localement.

## 9. Partages

Un partage rend une ressource visible dans un autre projet du même propriétaire. Il est actif dès sa création, ne transmet aucun droit et n'a pas de plafond de ressources. Un partage révoqué n'est jamais réactivé : il faut en créer un autre.

### `GET /api/v1/projects/{project_id}/shares` — Partages reçus par un projet

- Accès : membre du projet. Les détails d'une ressource ne sont retournés que si l'appelant possède aussi le droit de lecture correspondant (`vm.view` ou `storage.view`).
- Query : pagination commune ; filtre `resource_type` optionnel (`vm` ou `storage`) ; filtre `status` optionnel (`active` ou `revoked`). Par défaut, `status=active`. Filtres combinés en ET ; tri par `created_at` décroissant.
- Corps : aucun.
- Réponse `200 OK` : `Page[ShareOut]` des partages dont `dest_project_id` correspond au projet de la route.
- Erreurs : `401`, `403`, `404` projet, `422`.

### `POST /api/v1/projects/{project_id}/storages/{storage_id}/shares`

- Accès : propriétaire ou invité avec `storage.share` dans le projet d'origine ; l'appelant doit être membre du projet destinataire.
- `{project_id}` doit être le projet d'origine du stockage.
- Corps `ShareCreateIn` : `{"dest_project_id": "prj-beta"}`.
- Réponse `201 Created` : `ShareOut`, état `active`.
- Erreurs : `400` mauvais projet d'origine (détail `origin_project_id`), `401`, `403` droit/membership/propriétaire incompatibles, `404`, `409` partage actif déjà existant ou projet destinataire identique à l'origine, `409 invalid_state` stockage en suppression, `422`.

### `GET /api/v1/projects/{project_id}/storages/{storage_id}/shares`

- Accès : propriétaire ou invité avec `storage.view`.
- Query : pagination commune ; filtre `status` facultatif, `active` ou `revoked`; `dest_project_id` facultatif pour ne retenir que les partages vers ce projet. Filtres combinés en ET ; tri par `created_at` décroissant.
- Corps : aucun.
- Réponse `200 OK` : `Page[ShareOut]`.
- Erreurs : `401`, `403`, `404`, `422`.

### `POST /api/v1/projects/{project_id}/vms/{vm_id}/shares`

- Mêmes paramètres de chemin et corps que le partage stockage.
- Accès : propriétaire ou invité avec `vm.share` dans le projet d'origine et membre du destinataire.
- Réponse `201 Created` : `ShareOut`, `resource_type: "vm"`.
- Erreurs : `400`, `401`, `403`, `404`, `409` partage déjà actif ou VM en suppression, `422`.

### `GET /api/v1/projects/{project_id}/vms/{vm_id}/shares`

- Accès : propriétaire ou invité avec `vm.view`.
- Query : pagination commune ; filtres `status` (`active`/`revoked`) et `dest_project_id` facultatifs. `status` vaut `active` par défaut. Filtres combinés en ET ; date décroissante.
- Corps : aucun.
- Réponse `200 OK` : `Page[ShareOut]`.
- Erreurs : `401`, `403`, `404`, `422`.

### `POST /api/v1/shares/{share_id}/revoke`

- Accès : propriétaire du projet d'origine ou créateur du partage.
- Corps : aucun.
- Réponse `200 OK` :

  ```json
  { "share": { "id": "shr-123", "status": "revoked" }, "message": "Le partage a été révoqué." }
  ```

- Une VM partagée est retirée des réseaux du projet destinataire avant la révocation effective. Un stockage partagé disparaît immédiatement de la liste de ce projet.
- Erreurs : `401`, `403`, `404`, `409 invalid_state` déjà révoqué, `503` détachement externe impossible (partage conservé actif).

## 10. Demandes

Une demande porte toujours sur un projet. Seules la création et la modification de ressources passent par ce mécanisme. Un administrateur accepte ou refuse la demande sans la modifier ; la remarque de décision est facultative.

### `GET /api/v1/requests`

- Accès : utilisateur authentifié. Un utilisateur voit ses demandes et les demandes des projets dont il est membre ; un `admin` voit toutes les demandes.
- Query :
  - pagination commune ;
  - `status` facultatif parmi `pending`, `accepted`, `refused`, `cancelled` ;
  - `kind` facultatif parmi `vm_create`, `vm_update`, `storage_create`, `storage_update` ;
  - `project_id` facultatif : identifiant exact d'un projet auquel l'utilisateur a accès ; ignoré pour `admin` seulement si non fourni, jamais si invalide ;
  - `author_id` facultatif, administrateur uniquement.
  Filtres combinés en ET. Tri `created_at` décroissant puis `id` décroissant.
- Corps : aucun.
- Réponse `200 OK` : `Page[RequestOut]`.
- Erreurs : `401`, `403` filtre `author_id` sans rôle admin ou projet hors périmètre, `422`.

### `GET /api/v1/requests/{request_id}`

- Accès : auteur, membre du projet concerné ou administrateur.
- Corps : aucun.
- Réponse `200 OK` : `RequestOut`.
- Erreurs : `401`, `403`, `404`.

### `POST /api/v1/requests/{request_id}/cancel`

- Accès : auteur uniquement.
- Corps : aucun.
- Réponse `200 OK` : `RequestOut` avec `status: "cancelled"`.
- Erreurs : `401`, `403`, `404`, `409` demande autre que `pending`.

### `POST /api/v1/requests/{request_id}/accept`

- Accès : `admin`.
- Corps `RequestDecisionIn` :

  ```json
  { "note": "Conforme au besoin." }
  ```

  `note` est facultatif, maximum 1000 caractères ; `{}` est valide.
- Réponse `200 OK` : `RequestOut` avec `status: "accepted"`, `admin_note` et `decided_at`. Pour une création, `target_resource_id` référence la ressource créée. Une VM/un stockage reçoit ses attributs `ip_address` dès qu'ils sont disponibles.
- Erreurs : `401`, `403`, `404`, `409` demande non pending, `503` système externe indisponible (demande demeure pending).

### `POST /api/v1/requests/{request_id}/refuse`

- Accès : `admin`.
- Corps : même `RequestDecisionIn` que l'acceptation.
- Réponse `200 OK` : `RequestOut` avec `status: "refused"`, `admin_note` et `decided_at`.
- Erreurs : `401`, `403`, `404`, `409` demande non pending.

## 11. Packs

### `GET /api/v1/packs`

- Accès : utilisateur authentifié.
- Query : pagination commune ; `name` facultatif, préfixe insensible à la casse ; `min_ram_gb`, `max_ram_gb`, `min_vcpu`, `max_vcpu` facultatifs. Les valeurs sont inclusives et filtres combinés en ET. Tri `name` puis `id`.
- Corps : aucun.
- Réponse `200 OK` : `Page[PackOut]`.
- Erreurs : `401`, `422` (min supérieur à max ou valeur négative).

### `GET /api/v1/packs/{pack_id}`

- Accès : utilisateur authentifié.
- Corps : aucun.
- Réponse `200 OK` : `PackOut`.
- Erreurs : `401`, `404`.

### `POST /api/v1/admin/packs`

- Accès : `admin`.
- Corps `PackCreateIn` :

  ```json
  {
    "name": "Standard",
    "description": "Configuration générale",
    "ram_gb": 8,
    "vcpu": 4,
    "vram_gb": 0,
    "ssd_gb": 80
  }
  ```

- Contraintes : nom 1–64 caractères, `ram_gb >= 1`, `vcpu >= 1`, `vram_gb >= 0`, `ssd_gb >= 1`.
- Réponse `201 Created` : `PackOut`.
- Erreurs : `401`, `403`, `409` nom existant, `422`.

### `PATCH /api/v1/admin/packs/{pack_id}`

- Accès : `admin`.
- Corps `PackUpdateIn` : champs `name`, `description`, `ram_gb`, `vcpu`, `vram_gb`, `ssd_gb` optionnels ; au moins un champ requis.
- Réponse `200 OK` : `PackOut`. Les demandes `vm_create` encore pending qui référencent ce pack sont mises à jour avec la nouvelle configuration et renvoyées à l'administrateur pour nouvelle validation. Les VMs existantes restent inchangées.
- Erreurs : `401`, `403`, `404`, `409`, `422`.

### `DELETE /api/v1/admin/packs/{pack_id}`

- Accès : `admin`.
- Corps : aucun.
- Réponse `204 No Content`, corps vide.
- Erreurs : `401`, `403`, `404`, `409` si une demande pending dépend de ce pack.

## 12. Droits métier

- VM : `vm.view`, `vm.console`, `vm.power`, `vm.request_create`, `vm.request_update`, `vm.network`, `vm.delete`, `vm.share`.
- Stockage : `storage.view`, `storage.request_create`, `storage.request_update`, `storage.delete`, `storage.share`.
- Projet : `project.invite`.

Profils prédéfinis :

- `Lecteur` : `vm.view`, `storage.view`.
- `Opérateur` : droits de Lecteur + `vm.console`, `vm.power`.
- `Gestionnaire` : droits d'Opérateur + `vm.request_update`, `vm.network`, `storage.request_update`.

Les droits `vm.request_create`, `storage.request_create`, `vm.delete`, `storage.delete`, `vm.share`, `storage.share`, `project.invite` ne sont pas inclus dans ces profils prédéfinis et s'ajoutent individuellement.