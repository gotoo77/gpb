# Sécurité

[Français](security.md) | [English](security.en.md)

## Modèle de menace et protections

- ZIP/Tar Slip : chaque membre est normalisé comme chemin POSIX relatif. Les chemins absolus, `..`,
  NUL et liens tar sont refusés ou ignorés. Les archives sont lues en flux, sans extraction globale.
- Bombes de décompression : des limites configurables par membre et par volume décompressé sont
  vérifiées. L’opérateur doit néanmoins prévoir un quota disque adapté.
- Corruption et interruption : SHA-256 est calculé pendant l’écriture temporaire et l’installation
  utilise un renommage atomique. La vérification relit chaque octet.
- Collisions et destruction : les noms sont assainis et un suffixe de hash distingue les
  collisions. Un doublon suspecté n’est jamais supprimé.
- Secrets : identifiants client et jetons se trouvent sous un répertoire d’état en mode `0700`,
  avec des fichiers en `0600`. Git les ignore. Les manifests omettent les URL distantes. N’activez
  pas les logs HTTP de débogage.
- OAuth : seul le scope Picker en lecture est demandé. Aucun cookie navigateur, scraping, API
  privée ou mot de passe n’est utilisé.
- Originaux : les octets importés et les EXIF ne sont jamais modifiés. Les dates du système de
  fichiers changent uniquement avec une option explicite.

La base SQLite contient noms, dates et chemins locaux ; elle doit être protégée comme les médias.
Le fichier de jeton portable protège moins qu’un keyring système déverrouillé : utilisez le
chiffrement intégral du disque et des permissions de compte strictes.

