# ADR 0001 : stratégie d’accès à Google Photos

[Français](0001-google-photos-access-strategy.md) |
[English](0001-google-photos-access-strategy.en.md)

- Statut : accepté
- Date : 2026-07-27

## Contexte

L’étude de faisabilité démontre que la Library API ne peut pas énumérer les photothèques
préexistantes, que Picker exige une sélection explicite et que Data Portability ne propose
actuellement pas Google Photos parmi ses produits pris en charge.

## Décision

Choisir **C — ingestion Takeout** comme chemin de référence pour une photothèque complète et
**A — Picker** comme chemin distant pris en charge. Picker est toujours présenté comme l’import
d’une sélection utilisateur, jamais comme une sauvegarde complète.

Implémenter OAuth, la création et le polling des sessions, la pagination et le téléchargement
Picker en flux. Conserver les identifiants fournisseur, mais ne jamais dépendre de l’URL de base
valable 60 minutes. Demander une nouvelle sélection après expiration, car l’API ne documente pas
de rafraîchissement durable d’un élément lorsque la session a disparu.

Ne pas implémenter Data Portability. Son adaptateur est différé jusqu’à ce que Google documente
Photos comme ressource prise en charge et que l’application puisse satisfaire les validations de
production. Ne pas scanner avec Library API. Conserver l’import de répertoires Android comme
source future ; le modèle local possède déjà la valeur `android`.

## Conséquences

Takeout peut produire une archive complète, mais l’utilisateur doit toujours initier l’export.
Picker fournit un flux incrémental pratique mais manuel ; les photos téléchargées perdent la
localisation EXIF et les vidéos sont transcodées. Les deux chemins alimentent une même bibliothèque
SQLite idempotente et vérifiée par hash.

