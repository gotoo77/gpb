# Roadmap

[Français](roadmap.md) | [English](roadmap.en.md)

Cette roadmap décrit les évolutions prévues après le MVP. Elle ne promet aucune capacité que les
API Google ne permettent pas officiellement.

## Principes de priorité

1. Protéger les nouvelles photos avant leur envoi vers un service cloud.
2. Garantir l’intégrité et la récupérabilité de la bibliothèque locale.
3. Améliorer les performances sans réduire la sûreté ou l’idempotence.
4. N’ajouter une intégration Google que lorsqu’elle est officiellement documentée et testable.

## P0 — Stabilisation du MVP

Statut : **terminé**

- [x] Import Takeout ZIP, TGZ, TAR et répertoire.
- [x] Import multipart et détection des contenus déjà présents.
- [x] Écriture temporaire, renommage atomique et SHA-256 calculé pendant le flux.
- [x] Association et conservation des sidecars JSON.
- [x] Barre de progression globale avec débit et temps restant.
- [x] Vérification d’intégrité et manifeste JSONL.
- [x] Tester une interruption réelle par `SIGINT` à différentes phases.
- [x] Simuler un disque plein pendant une copie.
- [x] Nettoyer ou signaler explicitement les fichiers `.partial` abandonnés.
- [x] Produire un rapport de fin détaillé par archive et type de média.
- [x] Ajouter une commande de diagnostic des archives avant import.

Critère de sortie : une interruption ou une erreur disque ne perd aucune donnée terminée, et la
commande suivante explique précisément comment reprendre.

Critère validé par des tests d’interruption avant et pendant la copie, pendant la conservation
d’un sidecar, ainsi que par une injection d’erreur `ENOSPC`.

## P1 — Import Android et dossiers locaux

Statut : **prévu**

- [ ] Ajouter `gpb android import <répertoire-monté>`.
- [ ] Importer depuis MTP, stockage USB ou répertoire synchronisé sans dépendre de Google Photos.
- [ ] Détecter les nouveaux médias sans rescanner intégralement les contenus déjà connus.
- [ ] Conserver le chemin et l’appareil d’origine dans la provenance.
- [ ] Prendre en charge DCIM, captures d’écran, vidéos et dossiers configurables.
- [ ] Ajouter un mode `watch` pour surveiller un répertoire local.
- [ ] Documenter une exécution périodique avec un timer systemd utilisateur.

Critère de sortie : brancher ou monter un téléphone puis relancer la commande ne copie que les
nouveaux fichiers, sans suppression sur l’appareil.

## P2 — Métadonnées et formats complexes

Statut : **prévu**

- [ ] Enrichir les médias avec `exiftool` lorsqu’il est disponible.
- [ ] Extraire dimensions, codec et durée avec `ffprobe`.
- [ ] Mieux associer les composantes des Motion/Live Photos.
- [ ] Identifier et conserver correctement les formats RAW.
- [ ] Produire un rapport pour les dates absentes, ambiguës ou contradictoires.
- [ ] Ajouter une politique configurable de choix de date sans modifier les EXIF originaux.

Critère de sortie : chaque décision de métadonnée possède une provenance explicite et reste
réversible.

## P3 — Performance et téléchargements Picker

Statut : **prévu**

- [ ] Rendre `--jobs` effectif avec une concurrence bornée.
- [ ] Tester les vidéos volumineuses sans chargement complet en mémoire.
- [ ] Renouveler les URL temporaires expirées lorsque la session Picker le permet.
- [ ] Ajouter des retries testés pour `401`, `429` et erreurs serveur.
- [ ] Respecter strictement les intervalles de polling fournis par Google.
- [ ] Supprimer proprement les sessions Picker terminées.

Critère de sortie : quatre téléchargements concurrents peuvent être interrompus et relancés sans
corruption ni doublon.

## P4 — Exploitation et restauration

Statut : **envisagé**

- [ ] Ajouter `gpb report` avec volumes, années, formats, doublons et anomalies.
- [ ] Ajouter une vérification incrémentale et une vérification complète planifiable.
- [ ] Exporter une bibliothèque vers un autre disque en conservant le manifeste.
- [ ] Restaurer ou reconstruire la base SQLite depuis un manifeste et les médias.
- [ ] Comparer deux bibliothèques locales sans supprimer automatiquement les différences.
- [ ] Fournir des unités systemd utilisateur pour les tâches périodiques.
- [ ] Stocker les jetons OAuth dans le keyring système avec fallback documenté.

Critère de sortie : une perte de la base SQLite n’empêche pas de reconstruire un état local
cohérent à partir des fichiers et manifests.

## P5 — Assistance à la réduction du stockage Google

Statut : **envisagé, sans suppression automatisée**

- [ ] Générer un rapport local par année et mois après vérification.
- [ ] Identifier les périodes entièrement présentes et vérifiées localement.
- [ ] Produire une checklist de suppression manuelle et de restauration.
- [ ] Empêcher toute conclusion « supprimable » si un média est manquant ou corrompu.

`gpb` ne supprimera pas automatiquement les médias Google Photos : aucune API officielle actuelle
ne permet de supprimer en masse les éléments préexistants de la photothèque. Aucun scraping,
cookie de navigateur ou automatisme de clic ne sera ajouté.

## Bloqué par Google

### Data Portability pour Google Photos

Statut : **bloqué**

L’adaptateur ne sera implémenté que si Google Photos apparaît officiellement parmi les ressources
Data Portability disponibles dans la région ciblée et si les exigences de validation sont
raisonnablement accessibles à une application personnelle.

### Sauvegarde complète automatique via Library API

Statut : **non réalisable**

Depuis le 31 mars 2025, la Library API ne permet plus à une application tierce de parcourir les
médias préexistants d’une photothèque. Cette capacité ne fait donc pas partie de la roadmap.
