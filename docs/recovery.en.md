# Recovery

[Français](recovery.md) | [English](recovery.en.md)

An interrupted Takeout import leaves at most one randomly named `.partial` file under
`.gphotos-backup/`. Completed media are already atomically installed and recorded. `gpb` removes
its temporary file when it catches the error or interruption. `gpb status` distinguishes partial
files belonging to an active import from abandoned files and displays the latest run result and
errors. A lock prevents simultaneous imports into the same library. Manually remove a stale
partial only while no `gpb` process is running, then rerun the exact same import. SHA-256 prevents
completed content from being copied again.

An interruption reports exit code 130 and a resume instruction. A disk error, including `ENOSPC`,
finishes the run as failed with its detailed message without recording the incomplete media.

## Reconcile metadata across volumes

Google Takeout may place a photo in one volume and its `supplemental-metadata.json` file in another.
To repair a library imported before this situation was supported:

```console
uv run gpb takeout reconcile ~/Downloads/takeout-*.zip
uv run gpb verify
```

The command reads media to recover their SHA-256, links preserved sidecars, corrects dates in
SQLite, and atomically moves misplaced files, including files under `media/1970/01/`. It does not
copy media content again. Keep the archives until both reconciliation and `verify` have completed.

After a Picker interruption, rerun `picker download` while the session and URLs remain valid.
Otherwise create a new session and select the items again. Provider IDs and hashes prevent
duplicates.

Back up the entire library, including `.gphotos-backup/state.sqlite3`. Run `gpb verify` after
filesystem restoration. `gpb scan` can index untracked files in `media/` without moving them.
Manifests use JSON Lines and intentionally omit temporary remote URLs.

## Corrupt Takeout archive

Before importing, check all volumes with one command:

```console
uv run gpb takeout check ~/Downloads/takeout-*.zip
```

The check reads and decompresses every member, continues after a damaged volume, then gives the
complete list of volumes to download again. It does not modify any archive and does not require an
initialized library. Results are saved after each volume: after replacing damaged archives, the
same command only checks the replaced files. Use `--force` only to request a new full check.

`gpb` displays the volume, member, member index, header offset, expected and actual ZIP
signatures, sizes, expected CRC, and the corresponding `unzip -t` command. An actual signature of
`00 00 00 00` together with an unallocated region generally indicates a partial or sparse
download. Re-download the affected volume; do not attempt to repair it or silently use its
remaining entries. Completed media from other volumes remain valid.

Use `--json` to receive the same information under `error.context`.
