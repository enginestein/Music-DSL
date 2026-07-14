# MUSIC — PROGRAM YOUR OWN MUSIC

**Music DSL** is a text-based music programming language. Write songs in a plain text file, play them instantly through your speakers, or export to WAV/MIDI. No instruments, DAWs, or audio editing required.

```
tempo: 120   name: My Song   key: C

-- melody: organ 0.4 0.2 reverb:0.3 --
C4 q  E4 q  G4 q  C5 q

-- bass: sawtooth 0.3 -0.3 filter:lp 400 --
C3 h  F3 h  G3 h  C3 h
```

---

## Installation

### Prerequisites
- **Python 3.10+**
- **NumPy** (`pip install numpy`)
- **sounddevice** (optional, for playback): `pip install sounddevice`

### Install

```bash
cd music-dsl/
pip install .
pip install -e .        # editable mode (development)
```

### System-wide install (Linux)

```bash
sudo ./install.sh       # creates venv at /opt/music, installs dependencies
```

### Verify

```bash
music --help
music music/samples/night_drive.music   # play a sample
python3 -m music --help                 # alternative invocation
```

---

## Usage

```
music song.music                 play a song
music --midi song.music out.mid  export to MIDI
music --export song.music.wav    export to WAV
music --import-midi file.mid     import & play MIDI
music --import-midi file.mid out.music  import MIDI → .music
music song.music --wave          play with waveform visualizer
python3 -m music song.music      alternative invocation
```

---

## Python API

Use Music DSL programmatically from Python:

```python
from music import load, Song, Track, Note, midi_to_song, song_to_text

# Parse a .music file
song = load("path/to/song.music")

# Play through speakers
song.play()

# Export
song.save("out.wav")              # WAV file
song.to_midi("out.mid")           # Standard MIDI File

# Inspect
song.show()                       # print track summary to stdout
print(song.total_beats())         # total duration in beats
text = song.to_text()             # Song → .music DSL text (via MIDI roundtrip)
```

### Building a song in code

```python
from music import Song, Track, Note

song = Song()
song.tempo = 120
song.name = "Code Song"

track = Track("melody", "piano", vol=0.5, pan=0.0)
track.line("C4 q E4 q G4 q C5 q", key_acc={})
song.add(track)

song.save("code_song.wav")
```

### Importing MIDI

```python
from music import midi_to_song

song = midi_to_song("file.mid")   # returns a Song object
song.play()
```

---

## Language Reference

### File-level directives

Place these at the top of a `.music` file:

```
tempo: 120          # BPM (default 120)
name: My Song       # title
key: C              # major: C G D A E B F# C# F Bb Eb Ab Db Gb Cb
key: Am             # minor: Am Em Bm F#m C#m Dm Gm Cm Fm Bbm
key: none           # no key signature
time: 4/4           # time signature (default 4/4)
```

### Comments

```
# This is a full-line comment
C4 q  # This is an inline comment
```

### Tracks

A track has a name, instrument, volume, pan, and optional effects:

```
-- name: instrument vol pan options --
-- melody: organ 0.4 0.2 reverb:0.3 --
-- bass: sawtooth 0.3 -0.3 swing:0.6 --
-- rhythm: noise 0.15 0.0 mute --    # silenced track
```

Track header options:
| Option | Values | Description |
|--------|--------|-------------|
| `vol` | 0.0–1.0 | Volume |
| `pan` | -1.0–1.0 | Panning (left→right) |
| `reverb` | 0.0–1.0 | Reverb mix |
| `delay` | 0.0–1.0 | Delay mix |
| `swing` | 0.0–1.0 | Swing/shuffle amount |
| `mute` | — | Silences the track |

**Shorthand** — create a track with just an instrument name:

```
inst: piano 0.5 0.0     # name=instrument, vol=0.5, pan=0.0
```

Effect lines (placed inside the track body, one per line):

```
reverb:0.3
delay:0.2
swing:0.5
adsr:0.01 0.05 0.8 0.1   # attack decay sustain release
filter:lp 800 0.7         # lowpass/highpass/bandpass + freq + Q
dist:0.3                  # waveshaping distortion
lfo:filter 2 200 500      # LFO → filter (rate depth base)
humanize timing:0.02 vel:0.1  # random timing & velocity variation
```

Effects are additive across lines (multiple `reverb:` lines sum, multiple `filter:` lines replace).

### Notes

```
C4 q    D#4 e    Bb3 h    F4 w
```

**Pitch:** `A B C D E F G` with optional `#`/`b` accidental, followed by an octave number (4 = middle C, range 0–9).

**Durations** (sticky — applies to subsequent notes until changed):

| Code | Beats | Code | Beats |
|------|-------|------|-------|
| `w` | 4 (whole) | `e` | 0.5 (eighth) |
| `h` | 2 (half) | `s` | 0.25 (sixteenth) |
| `q` | 1 (quarter) | `t` | 0.125 |
| | | `x` | 0.0625 (sixty-fourth) |

**Duration modifiers:**
```
C4 q.           # dotted (1.5x)
C4 q..          # double-dotted (1.75x)
C4 qt           # triplet (2/3x)
C4 _1.5         # raw duration in beats
C4 _0.253       # fractional beats (e.g. from MIDI import)
```

**Rests:**
```
R q    R e    R _2    rest q    _ q
```

### Bar lines

```
|             # bar line (warns if bar overflows)
||            # double bar line
```

### Sections & Repeats

```
[verse]
C4 q  E4 q  G4 q
@jump verse       # repeat indefinitely

@done              # stop playback here
```

`[label]` marks a position, `@jump label` jumps back to it. `@done` stops playback.

Repeat a block N times:
```
[ C4 q E4 q G4 q ] x4
[ C4 e R e ] x32
```

**Multi-line repeats:**
```
[ C4 q E4 q
  G4 q C5 q ] x3
```

**Volta endings** (1st and 2nd endings):
```
[1 C4 q D4 q E4 q]      # play on first pass
[2 C4 q D4 q F4 q]      # play on second pass
```

### Chords

**Simultaneous notes** (parenthesized group):
```
(C4 E4 G4) q        # C major chord
(C4 E4 G4 C5) h     # add octave
```

**Chord symbols** (shorthand):
```
C  q    Cm  q    C7  q    Cmaj7  q
```

A letter alone (`C`) is a major triad. Chord type is appended directly (no space):

| Symbol | Type | Symbol | Type |
|--------|------|--------|------|
| (none) | Major | `m` / `min` | Minor |
| `maj7` / `M7` | Major 7th | `m7` | Minor 7th |
| `7` | Dominant 7th | `dim` | Diminished |
| `dim7` | Diminished 7th | `aug` | Augmented |
| `sus4` / `sus` | Suspended 4th | `sus2` | Suspended 2nd |
| `6` | Major 6th | `m6` | Minor 6th |
| `9` | Dominant 9th | `add9` | Add 9 |
| `m7b5` | Half-diminished | `m9` | Minor 9th |

Chord voicing starts at octave 4 by default. To specify octave, use the parenthesized form.

**Note:** Pitch names ending in a digit (`C7`, `F#7`, `Bb9`) are parsed as single notes, not chord symbols. Use `G7` for the note G at octave 7; use `(G B D F) q` for a G7 chord.

### Ties & Articulations

```
C4 w ~ C4 q          # tie (sustain across barline)
C4~ q                # legato (no gap between notes)
C4. q                # staccato (50% duration)
```

| Modifier | Effect |
|----------|--------|
| `.` after pitch | Staccato (shorten by 50%) |
| `~` after pitch | Legato (no gap before next) |
| `~` between notes | Tie (sustain through) |

### Dynamics

```
ppp  pp  p  mp  mf  f  ff  fff  sffz
```

Set global dynamics for subsequent notes. `fp` starts loud then soft.

```
ppp = 0.15   pp = 0.25   p = 0.35   mp = 0.50
mf = 0.70    f = 0.85    ff = 1.00  fff = 1.20
sffz = 1.30  fp = (1.00 → 0.35)
```

### Accent markings

```
>C4 q    ^D4 q    +E4 q
```

Apply directly before a pitch name. Boosts note velocity:

| Mark | Name | Velocity multiplier |
|------|------|-------------------|
| `>` | Accent | ×1.3 |
| `^` | Marcato | ×1.5 |
| `+` | Sforzando | ×1.8 |

### Note velocity override

```
C4 q @0.63     # set C4 velocity to 0.63 (overrides default 0.8)
```

`@N` after a note sets its velocity directly (0.0–1.0).

### Expression effects

```
vibrato:5            # pitch LFO rate (Hz)
tremolo:3            # amplitude LFO rate (Hz)
portamento:0.15      # pitch slide duration (seconds)
```

Set per-track. Values persist until changed.

### Note probability

```
C4 q ?0.5 D4 q E4 q   # D4 has 50% chance of silence
```

`?N` sets the probability (0.0–1.0) for all subsequent notes in that track. Notes roll against the probability each time they play; skipped notes become rests of equal duration. Reset with `?1.0`.

### Crescendo & Diminuendo

```
< C4 q D4 q E4 q >   # notes get progressively louder
```

`<` starts a velocity ramp (starting velocity → ×1.4), `>` ends it. All non-rest notes between receive linearly increasing velocity.

### Inline tempo changes

```
C4 q D4 q tempo:160 E4 q F4 q
```

`tempo:BPM` inside a note sequence changes playback speed from that point forward. Also works as a file-level directive.

### Tuplets

```
3:2 {C4 D4 E4}           # triplet (3 notes in the space of 2)
5:4 {C4 D4 E4 F4 G4}    # quintuplet (5 in the space of 4)
6:4 {C4 D4 E4 F4 G4 A4} # sextuplet
```

The first number is how many notes, the second is the base duration (in units of the current sticky duration). Grace notes:

```
{C4 D4} E4 q    # acciaccatura (grace notes, very short)
```

### Key signature

Key signatures apply accidentals automatically:

```
key: D             # F# and C# are raised
key: Bb            # Bb and Eb
key: Fm            # Bb, Eb, Ab, Db
```

Use `key: none` or `key: C` for no accidentals. Accidentals on individual notes (`C#4`, `Bb3`) override the key signature.

### Transpose

```
@ transpose 2     # all subsequent notes up 2 semitones
@ transpose -12   # down one octave
```

### Voice assignment

```
voice:2           # assign subsequent notes to MIDI voice 2
```

Used for MIDI roundtrip fidelity when a channel contains multiple independent lines.

### Patterns

Reusable note sequences:

**Single-line definition:**
```
@pattern arp = C4 e E4 e G4 e C5 e
```

**Multi-line definition:**
```
@pattern bassline
C2 e G2 e C3 e G2 e
Ab1 e Eb2 e Ab2 e Eb2 e
@end
```

**Invocation:**
```
@arp
@bassline
```

### Step sequencer

```
@steps 8 { C4 . D4 . E4 . F4 . }
```

Each step gets `current_duration / nsteps` duration. Dots (`.`) or `R` produce rests within the step pattern.

### Random / stochastic commands

```
@coin C4 D4 E4          # 50% chance to play one random note
@coin 0.3 C4 D4         # 30% chance
@rand C4 D4 E4 F4       # always play one random note from the list
@choose C4 D4 E4        # play ALL notes, each shortened proportionally
@shuffle C4 D4 E4 F4    # play all notes in random order
```

### Include

```
@include other_song.music    # import tracks from another .music file
```

Tracks from the included file are added to the current song using the current track's instrument.

### Track mute

```
-- rhythm: guitar 0.3 mute --
```

Add `mute` anywhere in the track header to silence it during playback. Useful for arranging or A/B testing parts without deleting them.

---

## Instruments

| Name | Aliases | Description |
|------|---------|-------------|
| `sine` | — | Pure sine wave |
| `square` | — | Square wave (hollow, video-game) |
| `sawtooth` | `saw` | Buzzy saw wave |
| `triangle` | `tri` | Mellow triangle wave |
| `organ` | — | Classic organ (sine + clipped square) |
| `bass` | — | Synth bass (fundamental + octave) |
| `bell` | — | Tonal bell (exponential decay) |
| `pluck` | — | Percussive noise pluck (drums) |
| `guitar` | `nylon` | Steel-string guitar (harmonics + decay) |
| `piano` | — | Acoustic piano (5 partials + decay) |
| `strings` | `pad` | Warm string pad (slow attack) |
| `flute` | — | Soft breathy flute |
| `brass` | — | Bright sustained brass (trumpet/trombone) |
| `reed` | `sax` | Nasal woodwind (sax/oboe/clarinet) |
| `noise` | — | White noise |

---

## Sample Songs

Located in `music/samples/`:

```
music music/samples/night_drive.music
```

| File | Tempo | Duration | Style |
|------|-------|----------|-------|
| `night_drive.music` | 94 BPM | 165s | Synthwave / retrowave |
| `empire_fire.music` | 174 BPM | 66s | War march / orchestral |
| `chaos.music` | 178 BPM | — | Storm of iron / battle |
| `skybound.music` | — | — | Cinematic |
| `machine.music` | — | — | Industrial |
| `iron_clash.music` | — | — | Percussive |
| `last_stand.music` | 162 BPM | 95s | Epic finale |
| `tragedy.music` | — | — | Dark / melancholic |

---

## MIDI Import/Export

### Import MIDI → play or convert

```bash
music --import-midi song.mid              # import & play
music --import-midi song.mid out.music    # import → .music DSL file
```

The importer maps General MIDI programs:

**Piano→piano** **Guitar→guitar** **Bass→bass** **Strings→strings/pad** **Organ→organ** **Flute→flute** **Percussion→noise**

Polyphonic voices within a MIDI channel are automatically split into separate tracks. Duration codes use the raw `_N.NNN` format to preserve exact MIDI timing.

### Export to MIDI / WAV

```bash
music --midi song.music out.mid    # export to Standard MIDI File
music --export song.music out.wav  # export to WAV audio file
```

---

## Audio Engine

### Playback backends (auto-detected)
1. **sounddevice** — preferred, low-latency
2. **PyAudio** — fallback
3. **aplay / paplay / pw-play** — system audio tools

### Per-track effects chain
1. Waveform synthesis (oscillator)
2. ADSR envelope
3. Staccato / legato articulation
4. Vibrato, tremolo, portamento
5. Volume & pan
6. Filter (lowpass / highpass / bandpass)
7. LFO-modulated filter
8. Waveshaping distortion
9. Reverb
10. Delay
11. Humanization (random timing & velocity)

---

## Project Structure

```
├── music/                  # Python package
│   ├── __init__.py         # Public API
│   ├── __main__.py         # Entry point
│   ├── cli.py              # Command-line interface
│   ├── parser.py           # DSL parser (load/loads)
│   ├── models.py           # Song, Track, Note + audio renderer
│   ├── _engine.py          # Audio playback & effects
│   ├── _waveform.py        # Terminal waveform visualizer
│   ├── _instruments.py     # Sound synthesis (oscillators)
│   ├── _midi.py            # MIDI import / export
│   ├── _pitch.py           # Pitch → MIDI → frequency
│   ├── _keys.py            # Key signature accidentals
│   ├── _durations.py       # Duration string parser
│   ├── _chords.py          # Chord symbol voicings
│   ├── _constants.py       # Audio constants (44100Hz, 16-bit, stereo)
│   └── samples/            # Demo song files
├── pyproject.toml
└── README.md
```

---

## License

MIT — use it, tweak it, make music with it.
