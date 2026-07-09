# ♪ MUSIC — PROGRAM YOUR OWN MUSIC

**Music DSL** is a text-based music programming language. Write songs in a plain text file, play them instantly through your speakers, or export to WAV/MIDI. No instruments, DAWs, or audio editing required.

```
tempo: 120   name: My Song   key: C

-- melody: organ 0.4 0.2 reverb:0.3 --
C4 q  E4 q  G4 q  C5 q

-- bass: sawtooth 0.3 -0.4 filter:lp 400 --
C3 h  F3 h  G3 h  C3 h
```

---

## 📦 Installation

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

### Verify

```bash
music --help
music music/samples/night_drive.music   # play a sample
```

---

## 🎮 Usage

```
music song.music                 play a song
music --midi song.music out.mid  export to MIDI
music --export song.music.wav    export to WAV
music --import-midi file.mid     import & play MIDI
music --import-midi file.mid out.music  import MIDI → .music
music song.music --wave          play with waveform visualizer
```
---

## 📝 Language Reference

### File-level directives

```
tempo: 120          # BPM
name: My Song       # title
key: C              # major: C G D A E B F# C# F Bb Eb Ab Db Gb Cb
key: Am             # minor: Am Em Bm F#m C#m Dm Gm Cm Fm Bbm
key: none           # no key signature
time: 4/4           # time signature
```

### Tracks

```
-- name: instrument vol pan options --

-- melody: organ 0.4 0.2 reverb:0.3 --
-- bass: sawtooth 0.3 -0.3 swing:0.6 --
```

Track options: `vol:0.5` `pan:-0.3` `reverb:0.3` `delay:0.2` `swing:0.5`

Track effect lines (inside a track block):
```
reverb:0.3
delay:0.2
swing:0.5
adsr:0.01 0.05 0.8 0.1   # attack decay sustain release
filter:lp 800 0.7         # lowpass/highpass/bandpass + freq + Q
dist:0.3                  # waveshaping distortion
lfo:filter 2 200 500      # LFO → filter (rate depth base)
humanize timing:0.02 vel:0.1  # random variation
```

### Notes

```
C4 q    D#4 e    Bb3 h    F4 w
```

**Pitch:** A–G, `#`/`b` accidentals, octave number (4 = middle C).

**Durations** (sticky):
| Code | Beats | Code | Beats |
|------|-------|------|-------|
| `w` | 4 (whole) | `e` | 0.5 (eighth) |
| `h` | 2 (half) | `s` | 0.25 (sixteenth) |
| `q` | 1 (quarter) | `t` | 0.125 / `x` | 0.0625 |

**Modifiers:** `q.` = dotted (1.5×), `q..` = double-dotted (1.75×), `qt` = triplet (2/3×), `_1.5` = raw beats

**Rests:** `R q` / `R e` / `R _2` / `rest` / `_`

### Chords

```
(C4 E4 G4) q         # simultaneous notes
Cmaj7 2  Dm7 2  G7 2  # chord symbols → voicing
```

Supported: `maj7` `m7` `7` `m` `m7b5` `dim7` `dim` `aug` `sus4` `sus2` `6` `add9` `9`

### Ties, articulations, expression

```
C4 w ~ C4 q          # tie
C4. q                # staccato (50% duration)
C4~ q                # legato (no gap)
ppp pp p mp mf f ff fff sffz   # dynamics
vibrato:5            # pitch LFO (Hz)
tremolo:3            # amplitude LFO (Hz)
portamento:0.15      # pitch slide (seconds)
```

### Tuplets & grace notes

```
3:2 {C4 D4 E4}           # triplets
5:4 {C4 D4 E4 F4 G4}    # quintuplets
{C4 D4} E4 q             # acciaccatura (grace notes)
```


---

## 🎸 Instruments

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
| `noise` | — | White noise |

---

## 🎵 Sample Songs

Located in `music/samples/`:

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

```bash
music music/samples/night_drive.music
```

---

## 🔄 MIDI Import/Export

### Import MIDI → play or convert

```bash
music --import-midi song.mid              # import & play
music --import-midi song.mid out.music    # import → .music DSL file
```

The importer maps General MIDI programs:
**Piano→piano** **Guitar→guitar** **Bass→bass** **Strings→strings/pad** **Organ→organ** **Flute→flute** **Percussion→noise**

Polyphonic voices within a MIDI channel are automatically split into separate tracks.

### Export to MIDI / WAV

```bash
music --midi song.music out.mid    # export to Standard MIDI File
music --export song.music out.wav  # export to WAV audio file
```

---

## 🎚️ Audio Engine

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

## 📁 Project Structure

```
├── music/                  # Python package
│   ├── __init__.py         # Public API
│   ├── __main__.py         # Entry point
│   ├── cli.py              # Command-line interface
│   ├── parser.py           # DSL parser
│   ├── models.py           # Song, Track, Note + renderer
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
├── setup.py / setup.cfg
└── README.md
```

---

## 📜 License

MIT — use it, tweak it, make music with it.