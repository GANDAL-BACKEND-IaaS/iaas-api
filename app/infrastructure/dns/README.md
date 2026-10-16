# Port DNS

Proprietaire : TABA.

Quand une VM est supprimee, le backend demande a l'equipe DNS de supprimer son nom de domaine
(R24). Il n'envoie que l'identifiant de la VM : il ne porte aucune donnee de nom de domaine.

## Fichiers

| Fichier | Role |
|---|---|
| `app/application/ports/dns.py` | Le contrat : `delete_domain(vm_id)` et ses erreurs |
| `fake_dns.py` | Mock en memoire, utilise par defaut. Sait simuler les pannes |
| `http_dns.py` | Client HTTP pour l'integration avec l'equipe DNS |
| `factory.py` | Choisit le mock ou le client HTTP selon `DNS_MODE` |

## Erreurs du port

| Erreur | Signification | Conduite attendue de l'appelant |
|---|---|---|
| `DnsUnavailable` | L'equipe DNS ne repond pas, ou la reponse s'est perdue | Refuser l'action (503, `upstream_unavailable`) sans l'appliquer a moitie. La rejouer plus tard est sans risque |
| `DnsRejected` | L'equipe DNS refuse de facon definitive | Refuser l'action ; la rejouer ne changera rien |

Les deux heritent de `DnsError`. Un nom deja supprime n'est pas une erreur.

## Mock et pannes simulees

```python
dns = FakeDns()
dns.fail_next()            # la prochaine demande echoue avant d'arriver (DnsUnavailable)
dns.lose_next_responses()  # la prochaine est prise en compte, mais l'appelant recoit DnsUnavailable
dns.reject_next()          # la prochaine est refusee (DnsRejected)
dns.deleted                # VMs dont le nom est supprime, sans doublon
dns.received               # nombre de demandes recues par VM, renvois compris
```

`FakeDns(available=False)` rend l'equipe DNS indisponible en permanence.

## Contrat HTTP propose a l'equipe DNS

A faire valider par l'equipe DNS :

```
DELETE {DNS_BASE_URL}/v1/vms/{vm_id}/domain
Authorization: Bearer <DNS_TOKEN>            (si configure)
Idempotency-Key: delete-domain-{vm_id}
```

| Reponse | Effet |
|---|---|
| `2xx`, `404`, `410` | Succes : le nom est supprime, ou l'etait deja |
| `408`, `429`, `5xx`, delai depasse, service injoignable | Une nouvelle tentative rapide, puis `DnsUnavailable` |
| autre `4xx` | `DnsRejected`, sans nouvelle tentative |

La cle d'idempotence ne depend que de la VM : apres une reponse perdue, le renvoi est reconnu
comme la meme demande.

## Configuration

| Variable | Defaut | Role |
|---|---|---|
| `DNS_MODE` | `fake` | `fake` (mock) ou `http` (equipe DNS reelle) |
| `DNS_BASE_URL` | `http://localhost:9000` | Adresse de l'API de l'equipe DNS |
| `DNS_TOKEN` | vide | Jeton de service envoye a l'equipe DNS |
| `DNS_TIMEOUT_SECONDS` | `5` | Delai d'attente d'une reponse |
| `DNS_ATTEMPTS` | `2` | Tentatives avant `DnsUnavailable` |

## Branchement

`app/core/dependencies.get_dns()` (socle partage) retourne encore `FakeDns()`. Pour utiliser la
configuration ci-dessus, il suffira, avec l'accord de l'equipe, de remplacer son corps par
`return build_dns()` (import depuis `app.infrastructure.dns.factory`).

## Questions pour l'equipe DNS

1. Le contrat ci-dessus lui convient-il, et a quelle adresse l'appeler ?
2. Comment authentifie-t-elle le backend ?
3. Confirme-t-elle qu'un nom deja supprime repond `404` ou `410`, et qu'un renvoi portant la
   meme `Idempotency-Key` est ignore ?
