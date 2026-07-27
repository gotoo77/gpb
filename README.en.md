# gpb

[Français](README.md) | [English](README.en.md)

> Google no longer provides third-party applications with automatic read access to an entire
> Google Photos library through the Library API. This tool only claims to provide a complete
> backup when it uses a mechanism officially capable of producing that complete dataset, such as
> an authorized export or a set of Takeout archives.

`gpb` is a Linux CLI for building and maintaining a reliable, reproducible local Google Photos
archive. Complete-library imports rely on Google Takeout archives. The remote workflow downloads
only the media explicitly selected by the user through the official Google Photos Picker API.

## Installation and first use

Requirements: Python 3.12 or later and [uv](https://docs.astral.sh/uv/).

```console
uv sync
uv run gpb doctor
uv run gpb init --library ~/Photos/GooglePhotos
export GPB_LIBRARY=~/Photos/GooglePhotos
uv run gpb takeout check ~/Downloads/takeout-*.zip
uv run gpb takeout import ~/Downloads/takeout-1.zip ~/Downloads/takeout-2.zip
uv run gpb verify
uv run gpb status
uv run gpb export-manifest
```

The `takeout check` command decompresses every member and checks its CRC, continues when a volume is
damaged, then lists the exact archives that need to be downloaded again. Each result is saved
immediately: subsequent runs automatically skip unchanged volumes and only check new or replaced
files. `--force` requests a new full check. It does not require an
initialized library. During checks, the progress bar displays the current volume number and name
as well as the current file. It shows processed bytes, throughput, and estimated
remaining time. Use `--no-progress` to disable it or `--json` for script-friendly output.

Imports are idempotent through SHA-256 content hashes. Existing content is never deleted. Each
file is streamed to a `.partial` file and atomically renamed after hashing. Sidecars are preserved
under `metadata/`. Filesystem timestamps are changed only when the explicit `--apply-file-times`
option is used.

The completion report breaks imports down by archive and media type. `gpb status` distinguishes
active `.partial` files from abandoned ones and exposes the latest run result. A lock prevents two
simultaneous imports into the same library. After Ctrl+C or a full-disk error, rerun the same
command: already completed media are not copied again.

## Explicit Picker selection

First follow the [Google Cloud setup guide](docs/google-cloud-setup.en.md), then run:

```console
uv run gpb auth login
uv run gpb picker create-session
# Open the displayed URL and select media
uv run gpb picker poll
uv run gpb picker download
```

The longer `gphotos-backup` executable remains available as an alias, but `gpb` is the recommended
command.

See also the documentation covering [limitations](docs/limitations.en.md),
[recovery](docs/recovery.en.md), [security](docs/security.en.md), and the
[roadmap](docs/roadmap.en.md).
