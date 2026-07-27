# Feasibility study

[Français](feasibility.md) | [English](feasibility.en.md)

Consulted on: **2026-07-27**. Only current, official Google documentation is used.
Status vocabulary: `supported`, `unsupported`, `uncertain`, `requires-verification`.

## Findings

| # | Question and conclusion | Status | Official evidence, paraphrased |
|---|---|---|---|
| 1 | Can Library API list all pre-existing media? **No.** It can list, search, and retrieve only media and albums created by this application. | `unsupported` | [Photos API updates](https://developers.google.com/photos/support/updates): after 31 March 2025 these operations are restricted to app-created content. |
| 2 | Removed scopes | `unsupported` | [Photos API updates](https://developers.google.com/photos/support/updates): `photoslibrary.readonly`, `photoslibrary.sharing`, and `photoslibrary` were removed on 31 March 2025. |
| 3 | What can Library API still read? App-created albums and media through `photoslibrary.readonly.appcreateddata`; uploads remain possible with `photoslibrary.appendonly`. | `supported` | [Access app-created items](https://developers.google.com/photos/library/guides/access-media-items) and [updates](https://developers.google.com/photos/support/updates). |
| 4 | Can Picker select the entire library without explicit user action? **No.** A user opens `pickerUri`, selects items, and completes the selection. No automated select-all operation is documented. | `unsupported` | [Session lifecycle](https://developers.google.com/photos/picker/guides/sessions) and [picking experience](https://developers.google.com/photos/picker/guides/picking-experience). |
| 5 | Are download URLs temporary? **Yes.** Picker base URLs last 60 minutes and can expire sooner after access is revoked. | `supported` | [List and retrieve media](https://developers.google.com/photos/picker/guides/media-items). IDs, not base URLs, must form durable state. |
| 6 | Original bytes or transformed representation? Photos using `=d` retain EXIF except location metadata; videos using `=dv` are high-quality **transcoded** versions. This is therefore not always a bit-for-bit original export. | `supported` | [Picker base URL parameters](https://developers.google.com/photos/picker/guides/media-items). |
| 7 | Motion Photo, RAW, video, and metadata representation | `requires-verification` | The [PickedMediaItem schema](https://developers.google.com/photos/picker/reference/rest/v1/mediaItems) exposes PHOTO/VIDEO, MIME type, dimensions, and selected metadata. The [media guide](https://developers.google.com/photos/picker/guides/media-items) exposes photo (`=d`) and video (`=dv`) Motion Photo components separately. RAW-specific and complete original metadata guarantees are not documented. |
| 8 | Does Data Portability expose Photos for the target—France, consumer account? France is supported, but the current supported-product list does **not** include Google Photos. | `unsupported` | [Google Account portability help](https://support.google.com/accounts/answer/14452558): France is listed; available products are Chrome, Maps, Play Store, Search, Shopping, and YouTube. Account eligibility can also vary. |
| 9 | Required Data Portability validation | `requires-verification` | The [Data Portability overview](https://developers.google.com/data-portability) requires app verification covering branding, use case, demo video, and a security assessment where necessary. [Verification requirements](https://support.google.com/cloud/answer/13464321) describe sensitive and restricted scopes. |
| 10 | Personal, unpublished application? Testing is possible with an organization-controlled account, but production access and token renewal require “In production” status and approval. This route is not immediately usable, and Photos is absent anyway. | `requires-verification` | [OAuth configuration](https://developers.google.com/data-portability/user-guide/configure-oauth) says Testing tokens expire after 7 days and renewal requires production; the [quickstart](https://developers.google.com/data-portability/user-guide/quickstart) uses an organization-controlled account. |
| 11 | Guaranteed recurring or incremental export? Data Portability permits an export every 24 hours during 30- or 180-day consent, but Photos is unavailable and time filters are documented only for selected My Activity, Chrome History, and Play resources. | `unsupported` | [Introduction](https://developers.google.com/data-portability/user-guide/introduction) and [time filters](https://developers.google.com/data-portability/user-guide/time-filter). |
| 12 | Quotas, caching, consent, and OAuth | `requires-verification` | [Picker sessions](https://developers.google.com/photos/picker/guides/sessions) require respecting returned polling intervals and timeouts and deleting completed sessions. [Media items](https://developers.google.com/photos/picker/guides/media-items) limit URLs to 60 minutes. [Data Portability OAuth](https://developers.google.com/data-portability/user-guide/configure-oauth) offers one-time, 30-day, or 180-day consent, limits Testing tokens to 7 days, and prohibits mixing its scopes with others. Exact quotas must be checked in Cloud Console. |

## Conclusion

- Library API does not provide silent or unattended complete backup.
- Picker supports explicit selections but is neither exhaustive nor always bit-for-bit original.
- Data Portability does not currently offer Photos in the target context.
- Google Takeout ingestion is the only complete, officially supplied, fully usable path for this
  MVP. Picker complements it for occasional explicit selections.
