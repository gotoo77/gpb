# gpb

[Français](README.md) | [English](README.en.md)

> Google ne fournit plus à une application tierce un accès automatique en lecture à
> l’intégralité d’une photothèque Google Photos via la Library API. Cet outil n’annonce une
> sauvegarde complète que lorsqu’elle est réalisée à partir d’un mécanisme officiellement capable
> de produire cette totalité, par exemple un export autorisé ou un ensemble d’archives Takeout.

`gpb` est un outil CLI Linux permettant de constituer et maintenir une archive locale, fiable et
reproductible de Google Photos. L’import d’une photothèque complète repose sur des archives Google
Takeout. Le chemin distant télécharge uniquement les médias que l’utilisateur sélectionne
explicitement avec l’API officielle Google Photos Picker.

## Installation et première utilisation

Prérequis : Python 3.12 ou version ultérieure et [uv](https://docs.astral.sh/uv/).

```console
uv sync
uv run gpb doctor
uv run gpb init --library ~/Photos/GooglePhotos
export GPB_LIBRARY=~/Photos/GooglePhotos
uv run gpb takeout check ~/Téléchargements/takeout-*.zip
uv run gpb takeout import ~/Downloads/takeout-1.zip ~/Downloads/takeout-2.zip
uv run gpb verify
uv run gpb status
uv run gpb export-manifest
```

La commande `takeout check` décompresse et contrôle le CRC de chaque entrée, poursuit le contrôle
si un volume est défectueux, puis liste précisément les archives à retélécharger. Chaque résultat
est mémorisé immédiatement : une relance ignore automatiquement les volumes inchangés et ne
contrôle que les fichiers nouveaux ou remplacés. `--force` impose un nouveau contrôle complet.
La commande ne nécessite pas de bibliothèque initialisée. Pendant le contrôle, la barre affiche
le numéro et le nom du volume ainsi que le fichier courant. Elle indique aussi le débit et le temps
restant estimé. Utilisez `--no-progress` pour la désactiver ou `--json` pour une sortie exploitable
par un script.

L’import est idempotent grâce au hash SHA-256. Aucun contenu existant n’est supprimé. Chaque
fichier est écrit progressivement dans un fichier `.partial`, puis renommé atomiquement après
calcul de son hash. Les sidecars sont conservés dans `metadata/`. Les dates du système de fichiers
ne sont modifiées qu’avec l’option explicite `--apply-file-times`.

Le rapport final ventile les imports par archive et par type de média. `gpb status` signale les
fichiers `.partial` abandonnés et expose le résultat du dernier traitement. Après `Ctrl+C` ou une
erreur de disque plein, relancez la même commande : les médias déjà terminés ne sont pas recopiés.

## Sélection explicite avec Picker

Suivez d’abord la procédure de [configuration Google Cloud](docs/google-cloud-setup.md), puis :

```console
uv run gpb auth login
uv run gpb picker create-session
# Ouvrez l’URL affichée et sélectionnez les médias
uv run gpb picker poll
uv run gpb picker download
```

L’exécutable long `gphotos-backup` reste disponible comme alias, mais `gpb` est la commande
recommandée.

Consultez également les documents sur les [limitations](docs/limitations.md), la
[récupération](docs/recovery.md), la [sécurité](docs/security.md) et la
[roadmap](docs/roadmap.md).
