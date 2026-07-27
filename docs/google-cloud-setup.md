# Configuration Google Cloud

[Français](google-cloud-setup.md) | [English](google-cloud-setup.en.md)

1. Créez ou sélectionnez un projet Google Cloud.
2. Activez **Google Photos Picker API**. La Library API n’est pas nécessaire.
3. Configurez l’écran de consentement OAuth. Pour un test personnel, choisissez External et
   ajoutez votre compte Google comme utilisateur test. Demandez uniquement le scope
   `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`.
4. Créez un client OAuth de type **Desktop app** et téléchargez son fichier JSON.
5. Initialisez la bibliothèque, copiez le fichier vers
   `<bibliothèque>/.gphotos-backup/credentials.json`, puis lancez :

   ```console
   chmod 600 <bibliothèque>/.gphotos-backup/credentials.json
   GPB_LIBRARY=<bibliothèque> uv run gpb auth login
   ```

Le navigateur ouvre le flux de consentement officiel Google puis revient vers une adresse locale.
Les jetons sont stockés dans `.gphotos-backup/token.json` avec le mode `0600`. Ce MVP portable
n’utilise pas encore le keyring du bureau. Ne versionnez jamais ces deux fichiers.

Révoquez l’accès depuis Compte Google → Sécurité → Connexions avec des applications tierces.
Supprimer le jeton local avec
`rm <bibliothèque>/.gphotos-backup/token.json` ne révoque pas l’accès chez Google.

