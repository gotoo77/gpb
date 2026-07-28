# Active project context

## Current objective

- Maintenir une archive locale Google Photos fiable, reprenable et vérifiable.
- Prochaine étape immédiate : exporter un manifeste frais de la bibliothèque vérifiée.

## Current state

- Branche `main`, synchronisée avec `origin/main` au commit `a06ce3b`.
- P0/MVP terminé selon `docs/roadmap.md`.
- `gpb report` et `gpb rebuild` sont implémentés.
- La bibliothèque réelle contient 24 070 médias pour 82 925 245 636 octets.

## Decisions in force

- Français par défaut ; chaque document utilisateur possède une version `.en.md`.
- Toute opération longue expose une progression et un compte rendu final.
- Imports et contrôles doivent être idempotents et reprendre après interruption.
- Une reconstruction SQLite est atomique, sauvegarde la base remplacée et remet les
  vérifications à `pending`.
- Aucun média Google Photos n'est supprimé automatiquement.

## Verified facts

- `a06ce3b` ajoute rapports et reconstruction SQLite.
- `bf621fb` ajoute la reprise incrémentale de `verify`.
- Validation observée avant `a06ce3b` : Ruff OK, mypy OK, 50 tests réussis, paquet construit.
- Essai réel de `gpb report --json` : 24 070 médias, tous vérifiés, 82 925 245 636 octets,
  aucun doublon SHA-256, 558 médias sans date.
- MAT `project-handoff` est installé et son diagnostic est sain.

## Unverified hypotheses

- Les 62 fichiers rapportés avec l'extension `.mp` peuvent refléter les sources Takeout ou
  une anomalie de nommage ; leur origine n'a pas été examinée.
- Les 558 médias sans date peuvent nécessiter un enrichissement EXIF ; leur contenu n'a pas
  encore été échantillonné.

## Open questions

- Faut-il traiter d'abord les médias sans date ou commencer l'import Android/local P1 ?
- Les fichiers `.mp` sont-ils des formats réels, des noms tronqués ou des métadonnées erronées ?
- Quand fournir les unités systemd et la planification des contrôles ?

## Next recommended action

- Exécuter `uv run gpb export-manifest` après avoir configuré `GPB_LIBRARY`, puis sauvegarder
  ce manifeste avec la photothèque.
- Examiner ensuite un échantillon des 558 médias sans date via une évolution de `gpb report`.

## Authoritative references

- `README.md`
- `docs/roadmap.md`
- `docs/recovery.md`
- `docs/adr/0001-google-photos-access-strategy.md`
- `src/gphotos_backup/cli.py`
- `src/gphotos_backup/maintenance.py`
- `tests/test_core.py`
- Historique Git, notamment `a06ce3b` et `bf621fb`

## Last verification

- 2026-07-28, Europe/Paris.
- `git status --short --branch` : `main...origin/main`, aucun changement.
- `git log -6 --oneline --decorate` : `a06ce3b` en tête sur `main` et `origin/main`.
