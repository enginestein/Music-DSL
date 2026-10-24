# Changelog

All notable changes to this project are documented in this file.

## [3.0.0] - 2026-10-24

### Added

- **Song structure**: `%section` blocks and file-level `arrange: intro verse x2 chorus` with automatic rest-padding to keep tracks aligned; unknown sections in `arrange:` are reported by `--check`.
- **Generators**: `progression:` + `@gen bass/pad/arp/drums` (bass styles `root`/`root5`/`root8`, durations `8ths`/`quarters`/`16ths`/`half`/`whole`, `@gen drums` deferred until after arrangement). Drum styles: `four`, `rock`, `half`, `break`, `shuffle`.
- **Scale degrees**: `degrees:on` (Nashville-style) relative to `key:`, with `#`/`b` accidentals, octave marks `'`/`,`, chord qualities (`6m`, `1maj7`), and correct flat spelling in flat keys. Supported on track headers and in-track.
- **Arpeggiator**: `@arp up/down/ud/downup/rand` over chords or note lists.
- **Drum shorthand**: `@drums N { x . X g }` step patterns (`X` accent, `g` ghost).
- **Mix bus**: `master: vol/comp/reverb/delay`, sidechain ducking via `sidechain:NAME[:AMT]` in track headers or body (stereo-safe envelope).
- **CLI**: `--check`, `--new --style <style> [--title] [--tempo]`, `--live`, `--loop N`, `--from/--to SEC`, `--list-instruments`, `--version`; MP3/OGG export via `soundfile` or `ffmpeg`.
- **Templates**: `synthwave`, `rock`, `jazz`, `ambient`, `hiphop`, `blank` via `--new`.
- **Live REPL**: interactive jamming (`:track`, `:tempo`, `:key`, `:time`, `:dyn`, `:degrees`, `:fx`, `:play`, `:show`, `:undo`, `:clear`, `:save`, `:help`); structural `:save` round-trips loaded multi-track songs.
- **Editor support**: VS Code extension (`editors/vscode/`) and Vim/Neovim syntax/ftdetect (`editors/vim/`).
- **Tests**: 47-test suite (`pytest` and standalone `tests/test_dsl.py`), `lint()` API, editor README.

### Changed

- **README**: complete rewrite covering all features, CLI usage, live mode, editors, and testing.
- **Dynamics**: bare dynamics words on their own line now persist across lines per track; `@N` velocity override semantics documented correctly.
- **Patterns**: both `@pattern name = ...` and `@name = ...` forms supported.
- **Comments**: `#N` scale-degree tokens no longer confused with comments in degrees mode.

### Fixed

- **Timing**: `Track.beats()` no longer drops pending chord durations before rests (fixed render truncation and arrangement alignment).
- **Audio/rendering**: fixed missing `soundfile` import for MP3 paths; `_live.py` `s.song` attribute; `humanize:` header crash.
- **Parsing**: sidechain in track headers was previously parsed as pan (now correct); `@pattern` name extraction; degrees/chord spelling in flat keys.
- **Tooling**: `--new` now creates parent directories.

## [2.0.3] - 2026-10-22

Initial PyPI release baseline.
