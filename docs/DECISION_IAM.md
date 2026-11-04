# Le service de décision et de quota

`IamPort` dit **qui tu es** et **quels droits tu portes**. `DecisionPort` répond à
une autre question : **as-tu le droit de faire ceci, maintenant, et reste-t-il du
quota pour le faire ?**

---

## 1. Pourquoi deux ports

|  | `IamPort` | `DecisionPort` |
|---|---|---|
| Question | qui es-tu, quels droits portes-tu | as-tu le droit de faire **ceci**, maintenant |
| Dépend de | la personne et le projet | l'action, sa **taille**, l'heure, le second facteur, l'état du projet, le compteur |
| Effet | lit | **écrit** : il retient du quota |

Les mélanger obligerait `get_rights()` à rendre une réponse qui dépend de la
requête en cours — ce n'est plus un droit, c'est un verdict. Et un port qui lit
ne doit pas écrire.

## 2. La séquence, et les quatre fautes

```
autoriser → reserver → (le backend crée) → confirmer      ou      liberer
```

```
1. créer sans autoriser     n'importe qui fait n'importe quoi
2. autoriser sans réserver  deux requêtes simultanées passent toutes deux alors
                            qu'une seule tient dans le quota
3. créer sans confirmer     la réservation expire, le quota revient, et la
                            ressource existe toujours
4. échouer sans libérer     le quota reste retenu pour une ressource qui n'a
                            jamais existé, et la personne est bloquée
```

Les points 3 et 4 **ne se voient pas** : rien ne casse, les chiffres mentent.
D'où `transaction()`, qui confirme ou libère à la sortie — y compris quand le
corps lève, **et y compris si on oublie `confirmer`**.

```python
from app.application.ports.decision import DecisionPort
from app.core.dependencies import get_decision
from app.features.auth.dependencies import get_current_identity

@router.post("/projects/{project_id}/vms")
async def creer_vm(project_id: str, corps: VMCreateIn,
                   identity: Identity = Depends(get_current_identity),
                   decision: DecisionPort = Depends(get_decision)):
    # 1. la décision porte sur la PERSONNE, jamais sur le backend
    await decision.autoriser(
        sujet=identity.user_id, action="vm:create",
        ressource={"type": "vm", "id": corps.nom, "projet": project_id},
        contexte={"vcpu": corps.vcpu, "ram_gb": corps.ram_gb,
                  "disk_gb": corps.disk_gb})
    # 2. le quota est retenu AVANT de créer
    async with decision.transaction(
            sujet=identity.user_id, projet=project_id,
            ressources={"vm_count": 1, "vcpu": corps.vcpu,
                        "ram_gb": corps.ram_gb, "disk_gb": corps.disk_gb}) as t:
        vm = await hypervisor.create(corps)          # si ça lève → libéré
        await decision.confirmer(t, id_ressource=vm.id, type_ressource="vm")
    return vm
```

À la destruction, **`rendre`** : sans lui, le quota reste consommé par quelque
chose qui n'existe plus.

## 3. Le défaut est le refus

`ServiceIndisponible` **hérite** de `Refuse` : `except Refuse` attrape les deux.
Panne réseau, 503, réponse illisible → la requête est refusée. **Il n'existe
aucun chemin où une panne du service de décision rende « autorisé ».** Autoriser
par défaut ferait de chaque panne une levée générale des quotas, au moment précis
où personne ne regarde.

Un gestionnaire d'exceptions dans `main.py` traduit `Refuse` en RFC 9457
(`application/problem+json`), avec le **motif** d'IAM :

```json
{ "type": "https://gandal.internal/problemes/quota", "title": "Refuse",
  "status": 409, "detail": "il vous reste 2 vCPU sur 4", "motif": "quota" }
```

Sans ce gestionnaire, un refus de quota sortirait en 500 et l'utilisateur lirait
« erreur interne » là où IAM avait écrit une phrase utile. Et le code distingue
**403** (ne réessaie pas) de **503** (réessaie plus tard).

## 4. Pourquoi le SDK ne suffit pas

Le SDK a sa propre garde (`gandal_sdk.garde.GardeIam`). Elle est utile et elle
**n'est pas** le contrôle d'accès : un garde-fou dans un client est contournable
— il suffit d'appeler ce backend directement.

|  | SDK | **ici** |
|---|---|---|
| Refuse tôt, avec le motif | oui | oui |
| Retient et confirme le quota | oui | oui |
| **Ne peut pas être contourné** | non | **oui** |

## 5. Réglages

```bash
DECISION_BACKEND=gandal                       # defaut. « fake » pour le dev
DECISION_URL=https://10.30.0.30:8081/v1
DECISION_KEY_FILE=/etc/gandal/cle-iam         # deux lignes, mode 600 VERIFIE
DECISION_CA_FILE=/etc/gandal/gandal-ca.crt
DECISION_ROLE=backend                         # politique : iam:decision:delegate
DECISION_TIMEOUT_SECONDS=5.0
```

**Le défaut est `gandal`, et c'est voulu.** Avec `fake` par défaut, on se
retrouverait un jour en production avec des quotas en mémoire sans l'avoir
décidé — et personne ne le verrait, puisque rien ne casse.

Le rôle doit avoir une politique accordant **`iam:decision:delegate`** : le
backend n'a pas de second facteur, il endosse donc un rôle, et c'est ce qui lui
permet de décider **au nom de** quelqu'un. Sans cela, la décision porterait sur
le service, et tout le monde pourrait ce que le service peut.

## 6. Installation de la bibliothèque

```bash
pip install -e /chemin/vers/Gandal/iam/garde-serveur
```

`gandal_garde` n'est **pas** sur PyPI : elle décide des autorisations d'une
plateforme précise, et la publier inviterait à l'installer sans le service de
décision qui va avec. Elle n'a **aucune dépendance** — les trois hôtes n'ont pas
de sortie internet, et un service qui exige `httpx` pour démarrer est un service
qu'on ne peut pas réparer sur place.

En mode `fake`, le backend démarre **sans** elle : l'import est fait dans la
fabrique, pas en tête de module.

## 7. Le stockage objet : Drive, S3, Supabase

**Un projet peut l'utiliser ou pas, et il n'y a rien de plus à brancher.** La
limite par défaut d'un projet est **zéro** : un projet sans quota de stockage est
refusé par défaut.

```
accorder le quota  = activer le stockage
le remettre à zéro = le retirer
```

Pas de drapeau `peut-utiliser-stockage`. Deux interrupteurs pour une même porte
finissent par diverger, et ce jour-là personne ne sait lequel décide. **La porte
est le quota.**

| Ressource | Nature | Ce qu'elle attrape |
|---|---|---|
| `storage_buckets` | stock | combien de seaux |
| `storage_gb` | stock | la capacité occupée |
| `storage_objects` | stock | le **nombre** d'objets |
| `storage_egress_gb_month` | période | ce qui **sort**, par mois |

Le nombre d'objets n'est pas du zèle : dix millions de fichiers de 1 Kio coûtent
plus cher en requêtes qu'un seul de 10 Gio, et la capacité ne le voit pas. La
**sortie** est l'axe qui se facture, et le seul qu'une boucle peut faire exploser
en une nuit — une capacité pleine se voit, une facture d'egress ne se voit qu'au
relevé.

**Quel fournisseur n'est pas un quota.** `drive`, `s3`, `supabase` : ce n'est pas
une quantité, c'est un **attribut du projet** (`stockage-fournisseur`), que les
politiques lisent pour dire « ce projet va sur S3, pas sur Supabase ». Il voyage
dans la `ressource` de la décision, pas dans les quotas.

## 8. Quand le quota bouge, et quand il ne bouge pas

Le contrat du SDK ne crée pas une VM : il **dépose une demande**, qu'un
administrateur accepte. Les deux temps ne sont donc pas le même moment pour IAM :

| | décision | quota |
|---|---|---|
| `POST /projects/{id}/vms` — déposer | **demandée** | rien |
| `POST /requests/{id}/accept` — accepter | **redemandée** | **retenu, puis confirmé** |
| `refuse` / `cancel` | rien | rien |
| `POST .../deletion` — supprimer | demandée | **rendu** |

**Pourquoi séparer.** Retenir le quota au dépôt le bloquerait pendant les trois
jours où la demande attend : dix demandes en attente épuiseraient un quota sans
qu'aucune VM n'existe. Mais ne rien demander au dépôt serait pire — l'auteur
apprendrait trois jours plus tard que son rôle ne lui permet pas de créer de VM.
**On décide tôt, on compte tard.**

**Pourquoi la décision est redemandée à l'acceptation.** Entre les deux, le rôle
de l'auteur a pu expirer, son projet être archivé, une politique changer.
Accepter sur la foi d'une décision de trois jours, c'est appliquer un droit
périmé. Un test le tient.

**La modification compte l'écart**, pas la taille entière : l'acceptation d'une
demande `vm_update` appelle `redimensionner`, et c'est IAM qui soustrait.

**Un projet non vide ne se supprime pas** (`409`). Le supprimer en cascade
rendrait le quota de ses VM sans passer par `rendre`, et IAM continuerait de les
compter — un quota consommé par ce qui n'existe plus.

## 9. Le mode `fake` a un plan par défaut

`DECISION_FAKE_QUOTA` accorde d'office un plan modeste à **chaque** projet.

Sans lui, aucun projet n'a de quota et tout est refusé. C'est le bon
comportement du *vrai* service — un projet sans quota accordé est refusé par
défaut — mais ça rend `DECISION_BACKEND=fake` inutilisable pour développer le
Front. Le plan est écrit dans les réglages pour que personne ne le prenne pour
une levée des quotas, et il **n'a aucun effet** en mode `gandal`.

Le faux refuse pour de vrai au-delà de ce plan : le chemin de refus s'exécute en
développement, au lieu d'être découvert au premier refus réel.

## 10. Les tests

```bash
pytest tests/unit/test_decision.py                 # 13 : la sequence et ses refus
pytest tests/features/test_projects.py             # 22 : projets, VM, demandes
pytest tests/integration/test_decision_reelle.py   #  7 : la chaine vers IAM
pytest tests/integration/test_sdk_bout_en_bout.py  #  7 : le VRAI SDK, ce backend
```

**Le dernier est le seul qui prouve que le SDK est utilisable.** Les tests du
backend valident *ses* schémas, ceux du SDK *les siens*, et personne ne vérifie
que les deux coïncident — c'est précisément là que les contrats divergent, en
silence, jusqu'à ce qu'un appelant lève une exception Pydantic en production.

Il tourne **sans serveur** : `TestClient` de Starlette *est* un `httpx.Client`, et
le `HttpTransport` du SDK accepte qu'on lui en passe un. Le SDK parle donc à
l'application en mémoire, par son vrai code de transport. Il s'ignore si le SDK
n'est pas installé.

Un écart réel qu'il a attrapé du premier coup : `/members` rendait une **liste
nue** là où le SDK attend une `Page`. Aucune relecture ne l'aurait vu.

Les tests d'intégration montent un **vrai serveur HTTP** qui vérifie la signature
GANDAL4-HMAC-SHA256. Entre ce backend et le service de décision il y a quatre
maillons — la bibliothèque, la signature, l'endossement de rôle, le pont
asynchrone — et chacun peut casser sans qu'aucun test unitaire ne bouge. Ils sont
ignorés automatiquement si `gandal_garde` n'est pas installée.
