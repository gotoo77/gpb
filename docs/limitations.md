# Limitations

[Français](limitations.md) | [English](limitations.en.md)

- La lecture de toute la photothèque par Library API a été supprimée le 31 mars 2025.
- Picker exige une sélection utilisateur. Il n’existe pas de « tout sélectionner » automatisé.
- Les photos Picker perdent la localisation EXIF. Les vidéos sont des transcodages de haute
  qualité, sans garantie d’octets originaux. Les médias animés peuvent avoir plusieurs composantes ;
  le MVP télécharge la représentation correspondant au type PHOTO/VIDEO retourné.
- Les URL Picker durent environ 60 minutes. Une sélection expirée doit être recommencée.
- Data Portability ne propose actuellement pas Google Photos comme produit exportable.
- Les noms et sidecars Takeout varient. Les associations ambiguës sont signalées, jamais devinées.
- `--jobs` est accepté et borné, mais le téléchargeur MVP reste séquentiel.
- L’enrichissement facultatif avec `ffprobe`/`exiftool` et l’import Android sont prévus plus tard.

