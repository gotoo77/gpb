# Limitations

[Français](limitations.md) | [English](limitations.en.md)

- Library API full-library reading was removed on 31 March 2025.
- Picker requires user selection. There is no automated select-all operation.
- Picker photos omit location EXIF. Videos are high-quality transcodes without an original-byte
  guarantee. Motion media can contain multiple components; the MVP downloads the representation
  matching the returned PHOTO/VIDEO type.
- Picker URLs last about 60 minutes. An expired selection must be repeated.
- Data Portability does not currently offer Google Photos as an exportable product.
- Takeout names and sidecars vary. Ambiguous associations are reported and never guessed.
- `--jobs` is accepted and bounded, but the MVP downloader remains sequential.
- Optional `ffprobe`/`exiftool` enrichment and Android import are planned for later.

