# Instructions du dépôt

- Toute documentation destinée aux utilisateurs est rédigée en français par défaut.
- Le fichier français conserve le nom canonique sans suffixe, par exemple `README.md` ou
  `docs/recovery.md`.
- Chaque document français possède une traduction anglaise portant le suffixe `.en.md`.
- Les deux versions affichent immédiatement sous leur titre le sélecteur
  `[Français](...) | [English](...)`.
- Toute modification documentaire met à jour les deux langues dans le même changement.
- Toute commande CLI potentiellement longue expose une progression utile et une option
  `--progress/--no-progress`.
- Les attentes réseau courtes affichent au minimum un indicateur d’activité.
- `--json` désactive toute animation afin de conserver une sortie strictement exploitable.
- Toute opération CLI longue expose sa phase courante, sa position globale, l’élément traité et une
  progression mesurable. Elle produit un compte rendu final lisible et une sortie JSON structurée.
