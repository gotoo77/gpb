# Google Cloud setup

[Français](google-cloud-setup.md) | [English](google-cloud-setup.en.md)

1. Create or select a Google Cloud project.
2. Enable **Google Photos Picker API**. Library API is not required.
3. Configure the OAuth consent screen. For personal testing, choose External and add your Google
   account as a test user. Request only
   `https://www.googleapis.com/auth/photospicker.mediaitems.readonly`.
4. Create a **Desktop app** OAuth client and download its JSON file.
5. Initialize the library, copy the file to
   `<library>/.gphotos-backup/credentials.json`, and run:

   ```console
   chmod 600 <library>/.gphotos-backup/credentials.json
   GPB_LIBRARY=<library> uv run gpb auth login
   ```

The browser opens Google's official consent flow and returns to a loopback address. Tokens are
stored in `.gphotos-backup/token.json` with mode `0600`. This portable MVP does not use the desktop
keyring yet. Never commit either file.

Revoke access through Google Account → Security → Third-party connections. Removing the local
token with `rm <library>/.gphotos-backup/token.json` does not revoke access at Google.

