# Étude de faisabilité

[Français](feasibility.md) | [English](feasibility.en.md)

Date de consultation : **2026-07-27**. Seule la documentation officielle Google actuelle est
utilisée. Vocabulaire des statuts : `supported`, `unsupported`, `uncertain`,
`requires-verification`.

## Résultats

| # | Question et conclusion | Statut | Preuve officielle paraphrasée |
|---|---|---|---|
| 1 | La Library API peut-elle lister tous les médias préexistants ? **Non.** Elle peut uniquement lister, rechercher et récupérer les médias et albums créés par cette application. | `unsupported` | [Évolutions des API Photos](https://developers.google.com/photos/support/updates) : depuis le 31 mars 2025, ces opérations sont limitées au contenu créé par l’application. |
| 2 | Scopes supprimés | `unsupported` | [Évolutions des API Photos](https://developers.google.com/photos/support/updates) : `photoslibrary.readonly`, `photoslibrary.sharing` et `photoslibrary` ont été supprimés le 31 mars 2025. |
| 3 | Que peut encore lire la Library API ? Les albums et médias créés par l’application avec `photoslibrary.readonly.appcreateddata`. Les téléversements restent possibles avec `photoslibrary.appendonly`. | `supported` | [Accès aux éléments créés par l’application](https://developers.google.com/photos/library/guides/access-media-items) et [évolutions](https://developers.google.com/photos/support/updates). |
| 4 | Picker peut-il sélectionner toute la photothèque sans action explicite ? **Non.** L’utilisateur ouvre `pickerUri`, sélectionne les éléments et termine la sélection. Aucun « tout sélectionner » automatisé n’est documenté. | `unsupported` | [Cycle de vie d’une session](https://developers.google.com/photos/picker/guides/sessions) et [expérience de sélection](https://developers.google.com/photos/picker/guides/picking-experience). |
| 5 | Les URL de téléchargement sont-elles temporaires ? **Oui.** Les URL de base Picker durent 60 minutes et peuvent expirer plus tôt après révocation de l’accès. | `supported` | [Lister et récupérer des médias](https://developers.google.com/photos/picker/guides/media-items). Les identifiants, et non les URL, doivent constituer l’état durable. |
| 6 | Octets originaux ou représentation transformée ? Les photos avec `=d` conservent les EXIF sauf la localisation ; les vidéos avec `=dv` sont des versions **transcodées** de haute qualité. Il ne s’agit donc pas toujours d’un export bit à bit. | `supported` | [Paramètres des URL Picker](https://developers.google.com/photos/picker/guides/media-items). |
| 7 | Représentation des Motion Photos, RAW, vidéos et métadonnées | `requires-verification` | Le [schéma PickedMediaItem](https://developers.google.com/photos/picker/reference/rest/v1/mediaItems) expose PHOTO/VIDEO, le type MIME, les dimensions et certaines métadonnées. Le [guide des médias](https://developers.google.com/photos/picker/guides/media-items) expose séparément les composantes photo (`=d`) et vidéo (`=dv`) d’une Motion Photo. Les garanties propres au RAW et aux métadonnées originales complètes ne sont pas documentées. |
| 8 | Data Portability expose-t-elle Photos pour la cible — France, compte personnel ? La France est prise en charge, mais la liste actuelle des produits exportables ne contient **pas** Google Photos. | `unsupported` | [Aide Google Account sur la portabilité](https://support.google.com/accounts/answer/14452558) : la France est listée ; les produits disponibles sont Chrome, Maps, Play Store, Search, Shopping et YouTube. L’éligibilité dépend également du compte. |
| 9 | Validations Data Portability nécessaires | `requires-verification` | La [présentation Data Portability](https://developers.google.com/data-portability) impose une validation de l’application : marque, cas d’usage, vidéo de démonstration et audit de sécurité lorsque nécessaire. Les [exigences de validation](https://support.google.com/cloud/answer/13464321) détaillent les scopes sensibles et restreints. |
| 10 | Application personnelle non publiée ? Les tests sont possibles avec un compte contrôlé par l’organisation, mais la production et le renouvellement des jetons nécessitent le statut « In production » et une approbation. Ce chemin n’est pas immédiatement exploitable et Photos est absent. | `requires-verification` | La [configuration OAuth](https://developers.google.com/data-portability/user-guide/configure-oauth) indique que les jetons en mode Testing expirent après 7 jours et que le renouvellement nécessite la production ; le [guide de démarrage](https://developers.google.com/data-portability/user-guide/quickstart) utilise un compte contrôlé par l’organisation. |
| 11 | Export récurrent ou incrémental garanti ? Data Portability autorise un export toutes les 24 heures pendant un consentement de 30 ou 180 jours, mais Photos n’est pas proposé et les filtres temporels sont documentés seulement pour certaines ressources My Activity, Chrome History et Play. | `unsupported` | [Introduction](https://developers.google.com/data-portability/user-guide/introduction) et [filtres temporels](https://developers.google.com/data-portability/user-guide/time-filter). |
| 12 | Quotas, cache, consentement et OAuth | `requires-verification` | Les [sessions Picker](https://developers.google.com/photos/picker/guides/sessions) imposent de respecter l’intervalle et le délai retournés puis de supprimer les sessions terminées. Les [médias](https://developers.google.com/photos/picker/guides/media-items) limitent les URL à 60 minutes. [OAuth Data Portability](https://developers.google.com/data-portability/user-guide/configure-oauth) propose un consentement unique, de 30 ou 180 jours, limite les jetons Testing à 7 jours et interdit de mélanger ses scopes avec d’autres. Les quotas exacts doivent être vérifiés dans Cloud Console. |

## Conclusion

- La Library API ne permet pas de sauvegarde complète silencieuse ou sans surveillance.
- Picker est exploitable pour des sélections explicites, mais n’est ni exhaustif ni toujours
  identique bit à bit à l’original.
- Data Portability ne propose actuellement pas Photos dans le contexte ciblé.
- L’ingestion Google Takeout est le seul chemin complet, officiellement fourni et pleinement
  exploitable pour ce MVP. Picker complète ce chemin pour les sélections ponctuelles.

