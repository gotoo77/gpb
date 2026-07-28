# Récupération

[Français](recovery.md) | [English](recovery.en.md)

Un import Takeout interrompu laisse au plus un fichier au nom aléatoire avec le suffixe `.partial`
dans `.gphotos-backup/`. Les médias terminés sont déjà installés atomiquement et enregistrés.
`gpb` supprime son fichier temporaire lorsqu’il intercepte l’erreur ou l’interruption. `gpb status`
distingue les fichiers partiels d’un import actif des fichiers abandonnés et affiche le résultat
et les erreurs du dernier traitement. Un verrou empêche deux imports simultanés dans la même
bibliothèque. Supprimez manuellement un fichier partiel obsolète uniquement lorsqu’aucun processus
`gpb` ne tourne, puis relancez exactement le même import. SHA-256 empêche de recopier les contenus
terminés.

Une interruption affiche le code retour 130 et une instruction de reprise. Une erreur de disque,
notamment `ENOSPC`, termine le run en échec avec son message détaillé sans enregistrer le média
incomplet.

## Réconcilier les métadonnées entre volumes

Google Takeout peut placer une photo dans un volume et son fichier `supplemental-metadata.json`
dans un autre. Pour réparer une bibliothèque importée avant la prise en charge de cette situation :

```console
uv run gpb takeout reconcile ~/Téléchargements/takeout-*.zip
uv run gpb verify
```

La commande lit les médias pour retrouver leur SHA-256, rattache les sidecars déjà préservés,
corrige les dates dans SQLite et déplace atomiquement les fichiers mal classés, notamment ceux de
`media/1970/01/`. Elle ne recopie pas le contenu des médias. Conservez les archives jusqu’à la fin
de la réconciliation et de `verify`. Les mises à jour SQLite sont regroupées par archive pour
éviter le coût d’une validation par média ; en cas de `Ctrl+C`, les déplacements déjà effectués
dans l’archive courante sont validés avant l’arrêt.

La réconciliation suit une règle de non-dégradation : un JSON absent, malformé ou sans date
exploitable ne remplace jamais une date SQLite existante par une valeur vide. Les JSON malformés
sont conservés mais ignorés ; les sidecars orphelins, les associations ambiguës et les métadonnées
sans date disposent de compteurs distincts dans le rapport final.

La progression distingue le catalogue des métadonnées de la lecture des médias. Pendant le
catalogue, elle affiche `[volume/total]`, le volume courant, le nombre de JSON du volume, le cumul
et les octets traités. La phase média affiche en plus le fichier courant. Le rapport final détaille
les associations, mises à jour, déplacements, absences et anomalies ; `--json` retourne les mêmes
compteurs.

Attendez le retour au prompt après `reconcile`, puis lancez `verify` séparément. Si plusieurs
commandes sont collées ensemble, le shell démarre automatiquement la suivante après l’arrêt de la
précédente.

Après une interruption Picker, relancez `picker download` tant que la session et les URL restent
valides. Sinon, créez une nouvelle session et sélectionnez à nouveau les éléments. Les identifiants
fournisseur et les hashes empêchent les doublons.

Sauvegardez toute la bibliothèque, y compris `.gphotos-backup/state.sqlite3`. Lancez `gpb verify`
après une restauration du système de fichiers. `gpb scan` peut indexer les fichiers non suivis de
`media/` sans les déplacer. Les manifests utilisent JSON Lines et omettent volontairement les URL
distantes temporaires.

## Archive Takeout corrompue

Avant l’import, contrôlez tous les volumes en une seule commande :

```console
uv run gpb takeout check ~/Téléchargements/takeout-*.zip
```

Le contrôle lit et décompresse toutes les entrées, continue après un volume défectueux, puis donne
la liste complète des volumes à retélécharger. Il ne modifie aucune archive et ne nécessite pas de
bibliothèque initialisée. Les résultats sont mémorisés après chaque volume : après remplacement
des archives défectueuses, la même commande ne contrôle que les fichiers remplacés. Utilisez
`--force` uniquement pour imposer un nouveau contrôle complet.

`gpb` affiche le volume, l’entrée, son index, l’offset d’en-tête, les signatures ZIP attendue et
lue, les tailles, le CRC attendu et la commande `unzip -t` correspondante. Une signature lue
comme `00 00 00 00` accompagnée d’une zone non allouée indique généralement un téléchargement
partiel ou creux. Retéléchargez le volume concerné ; ne tentez pas de réparer ou d’utiliser
silencieusement ses entrées restantes. Les médias terminés dans les autres volumes restent valides.

Utilisez `--json` pour recevoir ces mêmes informations dans `error.context`.
