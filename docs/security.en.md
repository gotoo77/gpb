# Security

[Français](security.md) | [English](security.en.md)

## Threat model and controls

- ZIP/Tar Slip: every member is normalized as a relative POSIX path. Absolute paths, `..`, NULs,
  and tar links are rejected or ignored. Archives are streamed without global extraction.
- Decompression bombs: configurable per-member and total uncompressed-size limits are checked.
  Operators must still provide an appropriate disk quota.
- Corruption and interruption: SHA-256 is computed during temporary writing, and installation uses
  an atomic rename. Verification rereads every byte.
- Collisions and destruction: names are sanitized and a hash suffix distinguishes collisions.
  Suspected duplicates are never deleted.
- Secrets: client credentials and tokens live under a mode-`0700` state directory with mode-`0600`
  files. Git ignores them. Manifests omit remote URLs. Do not enable HTTP debug logs.
- OAuth: only the read-only Picker scope is requested. No browser cookies, scraping, private API,
  or passwords are used.
- Originals: imported bytes and EXIF are never modified. Filesystem timestamps change only through
  an explicit option.

The SQLite database contains names, dates, and local paths and must be protected like the media.
The portable token file is less protective than an unlocked system keyring; use full-disk
encryption and strict account permissions.
