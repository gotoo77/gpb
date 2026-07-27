# ADR 0001: Google Photos access strategy

[Français](0001-google-photos-access-strategy.md) |
[English](0001-google-photos-access-strategy.en.md)

- Status: accepted
- Date: 2026-07-27

## Context

The feasibility study shows that Library API cannot enumerate pre-existing libraries, Picker
requires explicit selection, and Data Portability currently does not expose Google Photos among
its supported products.

## Decision

Choose **C—Takeout ingestion** as the authoritative complete-library path and **A—Picker** as the
supported remote path. Picker is always described as importing a user selection, never as a
complete backup.

Implement OAuth, session creation and polling, pagination, and streaming Picker downloads. Persist
provider IDs but never depend on the 60-minute base URL. Request a new selection after expiration
because the API does not document durable single-item refresh after the session is gone.

Do not implement Data Portability. Defer its adapter until Google documents Photos as a supported
resource and the application can satisfy production verification. Do not scan through Library
API. Keep Android directory import as a future source; the local model already includes the
`android` value.

## Consequences

Takeout can produce a complete archive, but exports remain user-initiated. Picker provides a
convenient but manual incremental workflow; downloaded photos omit location EXIF and videos are
transcoded. Both paths feed a single idempotent, hash-verified SQLite library.

