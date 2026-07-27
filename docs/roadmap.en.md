# Roadmap

[Français](roadmap.md) | [English](roadmap.en.md)

This roadmap describes planned work after the MVP. It does not promise any capability that the
official Google APIs do not provide.

## Prioritization principles

1. Protect new photos before they are sent to a cloud service.
2. Guarantee the integrity and recoverability of the local library.
3. Improve performance without reducing safety or idempotency.
4. Add a Google integration only when it is officially documented and testable.

## P0 — MVP stabilization

Status: **complete**

- [x] Takeout ZIP, TGZ, TAR, and directory import.
- [x] Multipart import and existing-content detection.
- [x] Temporary writing, atomic rename, and in-stream SHA-256.
- [x] JSON sidecar association and preservation.
- [x] Global progress bar with throughput and remaining time.
- [x] Integrity verification and JSONL manifest.
- [x] Test real `SIGINT` interruptions during different phases.
- [x] Simulate a full disk during copying.
- [x] Clean up or explicitly report abandoned `.partial` files.
- [x] Produce a detailed completion report by archive and media type.
- [x] Add an archive diagnostic command that runs before import.

Exit criterion: an interruption or disk error loses no completed data, and the following command
explains exactly how to resume.

The criterion is validated by interruption tests before and during media copying, while preserving
a sidecar, and by an injected `ENOSPC` error.

## P1 — Android and local-directory import

Status: **planned**

- [ ] Add `gpb android import <mounted-directory>`.
- [ ] Import from MTP, USB storage, or a synchronized directory without Google Photos.
- [ ] Detect new media without fully rescanning known content.
- [ ] Preserve the original path and device in provenance.
- [ ] Support DCIM, screenshots, videos, and configurable directories.
- [ ] Add a `watch` mode for local directories.
- [ ] Document periodic execution through a user systemd timer.

Exit criterion: connecting or mounting a phone and rerunning the command copies only new files and
does not delete anything from the device.

## P2 — Metadata and complex formats

Status: **planned**

- [ ] Enrich media with `exiftool` when available.
- [ ] Extract dimensions, codec, and duration through `ffprobe`.
- [ ] Improve association of Motion/Live Photo components.
- [ ] Correctly identify and preserve RAW formats.
- [ ] Report missing, ambiguous, or contradictory dates.
- [ ] Add a configurable date-selection policy without changing original EXIF.

Exit criterion: every metadata decision has explicit provenance and remains reversible.

## P3 — Performance and Picker downloads

Status: **planned**

- [ ] Make `--jobs` effective with bounded concurrency.
- [ ] Test large videos without loading them entirely into memory.
- [ ] Renew expired temporary URLs when the Picker session permits it.
- [ ] Add tested retries for `401`, `429`, and server errors.
- [ ] Strictly honor polling intervals returned by Google.
- [ ] Cleanly delete completed Picker sessions.

Exit criterion: four concurrent downloads can be interrupted and restarted without corruption or
duplication.

## P4 — Operations and restoration

Status: **considered**

- [ ] Add `gpb report` with volumes, years, formats, duplicates, and anomalies.
- [ ] Add incremental and schedulable full verification.
- [ ] Export a library to another disk while preserving its manifest.
- [ ] Restore or rebuild SQLite from a manifest and media files.
- [ ] Compare two local libraries without automatically deleting differences.
- [ ] Provide user systemd units for periodic tasks.
- [ ] Store OAuth tokens in the system keyring with a documented fallback.

Exit criterion: loss of SQLite does not prevent rebuilding consistent local state from files and
manifests.

## P5 — Google storage reduction assistance

Status: **considered, without automated deletion**

- [ ] Generate a verified local report by year and month.
- [ ] Identify periods that are entirely present and verified locally.
- [ ] Produce a manual deletion and recovery checklist.
- [ ] Never describe a period as removable when any media is missing or corrupt.

`gpb` will not automatically delete Google Photos media: no current official API supports bulk
deletion of pre-existing library items. Browser scraping, browser cookies, and automated clicking
will not be added.

## Blocked by Google

### Data Portability for Google Photos

Status: **blocked**

The adapter will be implemented only if Google Photos officially appears among Data Portability
resources available in the target region and its verification requirements are reasonably
accessible to a personal application.

### Automatic complete backup through Library API

Status: **not feasible**

Since 31 March 2025, Library API no longer lets third-party applications enumerate pre-existing
library media. This capability is therefore not part of the roadmap.
