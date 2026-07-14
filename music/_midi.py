import struct
import warnings
from pathlib import Path
from .models import Song, Track, Note
from ._pitch import midi_to_name

_DUR_CODES = [(4.0, 'w'), (2.0, 'h'), (1.0, 'q'), (0.5, 'e'),
              (0.25, 's'), (0.125, 't'), (0.0625, 'x')]

# Channel index 9 (MIDI channel 10, 1-indexed) is the General MIDI
# percussion channel. Unlike melodic channels, the note number there
# selects *which drum/cymbal sound* plays -- it is not a pitch -- and
# percussion channels normally never send a Program Change message, so
# looking the "program" up in _GM_MAP (as melodic channels do) makes no
# sense and used to silently fall back to program 0 ('piano'), making
# every drum hit sound like an out-of-key piano note. Map each drum key
# to whichever built-in synth voice best approximates its character.
_GM_DRUM_MAP = {
    35: 'bass', 36: 'bass', 37: 'pluck', 38: 'pluck', 39: 'noise',
    40: 'pluck', 41: 'bass', 42: 'noise', 43: 'bass', 44: 'noise',
    45: 'bass', 46: 'noise', 47: 'bass', 48: 'bass', 49: 'noise',
    50: 'bass', 51: 'noise', 52: 'noise', 53: 'bell', 54: 'noise',
    55: 'noise', 56: 'bell', 57: 'noise', 58: 'noise', 59: 'noise',
    60: 'pluck', 61: 'pluck', 62: 'pluck', 63: 'pluck', 64: 'bass',
    65: 'bell', 66: 'bass', 67: 'bell', 68: 'bell', 69: 'noise',
    70: 'noise', 71: 'flute', 72: 'flute', 73: 'noise', 74: 'noise',
    75: 'pluck', 76: 'pluck', 77: 'pluck', 78: 'noise', 79: 'noise',
    80: 'bell', 81: 'bell',
}

_GM_DRUM_NAMES = {
    35: 'Acoustic Bass Drum', 36: 'Bass Drum', 37: 'Side Stick',
    38: 'Acoustic Snare', 39: 'Hand Clap', 40: 'Electric Snare',
    41: 'Low Floor Tom', 42: 'Closed Hi-Hat', 43: 'High Floor Tom',
    44: 'Pedal Hi-Hat', 45: 'Low Tom', 46: 'Open Hi-Hat',
    47: 'Low-Mid Tom', 48: 'Hi-Mid Tom', 49: 'Crash Cymbal 1',
    50: 'High Tom', 51: 'Ride Cymbal 1', 52: 'Chinese Cymbal',
    53: 'Ride Bell', 54: 'Tambourine', 55: 'Splash Cymbal',
    56: 'Cowbell', 57: 'Crash Cymbal 2', 58: 'Vibraslap',
    59: 'Ride Cymbal 2', 60: 'Hi Bongo', 61: 'Low Bongo',
    62: 'Mute Hi Conga', 63: 'Open Hi Conga', 64: 'Low Conga',
    65: 'High Timbale', 66: 'Low Timbale', 67: 'High Agogo',
    68: 'Low Agogo', 69: 'Cabasa', 70: 'Maracas',
    71: 'Short Whistle', 72: 'Long Whistle', 73: 'Short Guiro',
    74: 'Long Guiro', 75: 'Claves', 76: 'Hi Wood Block',
    77: 'Low Wood Block', 78: 'Mute Cuica', 79: 'Open Cuica',
    80: 'Mute Triangle', 81: 'Open Triangle',
}

_GM_MAP = {
    0: 'piano', 1: 'piano', 2: 'piano', 3: 'piano',
    4: 'piano', 5: 'piano', 6: 'piano', 7: 'piano',
    8: 'bell', 9: 'bell',
    10: 'bell', 11: 'bell', 12: 'bell', 13: 'bell',
    14: 'bell', 15: 'bell',
    16: 'organ', 17: 'organ', 18: 'organ', 19: 'organ',
    20: 'organ', 21: 'organ', 22: 'organ', 23: 'organ',
    24: 'guitar', 25: 'guitar', 26: 'guitar', 27: 'guitar',
    28: 'guitar', 29: 'guitar', 30: 'guitar', 31: 'guitar',
    32: 'bass', 33: 'bass', 34: 'bass', 35: 'bass',
    36: 'bass', 37: 'bass', 38: 'bass', 39: 'bass',
    40: 'strings', 41: 'strings', 42: 'strings', 43: 'strings',
    44: 'strings', 45: 'strings', 46: 'sine', 47: 'sine',
    48: 'saw', 49: 'saw', 50: 'pad', 51: 'pad',
    52: 'saw', 53: 'saw', 54: 'saw', 55: 'saw',
    56: 'brass', 57: 'brass', 58: 'brass', 59: 'brass',
    60: 'brass', 61: 'brass', 62: 'brass', 63: 'brass',
    64: 'reed', 65: 'reed', 66: 'reed', 67: 'reed',
    68: 'reed', 69: 'reed', 70: 'reed', 71: 'reed',
    72: 'flute', 73: 'flute', 74: 'flute', 75: 'flute',
    76: 'flute', 77: 'flute', 78: 'flute', 79: 'flute',
    80: 'saw', 81: 'saw', 82: 'saw', 83: 'saw',
    84: 'saw', 85: 'saw', 86: 'saw', 87: 'saw',
    88: 'pad', 89: 'pad', 90: 'pad', 91: 'pad',
    92: 'pad', 93: 'pad', 94: 'pad', 95: 'pad',
    96: 'noise', 97: 'noise', 98: 'noise', 99: 'noise',
    100: 'noise', 101: 'noise', 102: 'noise', 103: 'noise',
    104: 'guitar', 105: 'guitar', 106: 'guitar', 107: 'guitar',
    108: 'guitar', 109: 'guitar', 110: 'guitar', 111: 'guitar',
    112: 'noise', 113: 'noise', 114: 'noise', 115: 'noise',
    116: 'noise', 117: 'noise', 118: 'noise', 119: 'noise',
    120: 'noise', 121: 'noise', 122: 'noise', 123: 'noise',
    124: 'noise', 125: 'noise', 126: 'noise', 127: 'noise',
}

_CHANNEL_NAMES = [
    'Acoustic Piano', 'Bright Piano', 'Electric Piano', 'Honkytonk',
    'Electric Piano 2', 'Harpsichord', 'Clavinet', 'Celesta',
    'Glockenspiel', 'Music Box',
    'Vibraphone', 'Marimba', 'Xylophone', 'Tubular Bells',
    'Dulcimer', 'Drawbar Organ',
    'Percussive Organ', 'Rock Organ', 'Church Organ', 'Reed Organ',
    'Accordion', 'Harmonica', 'Bandoneon', 'Nylon Guitar',
    'Steel Guitar', 'Jazz Guitar', 'Clean Guitar', 'Muted Guitar',
    'Overdrive Guitar', 'Distortion Guitar', 'Guitar Harmonics',
    'Acoustic Bass', 'Fingered Bass', 'Picked Bass', 'Fretless Bass',
    'Slap Bass 1', 'Slap Bass 2', 'Synth Bass 1', 'Synth Bass 2',
    'Violin', 'Viola', 'Cello', 'Contrabass',
    'Tremolo Strings', 'Pizzicato Strings', 'Orchestral Harp', 'Timpani',
    'String Ensemble', 'Slow Strings', 'Synth Strings 1', 'Synth Strings 2',
    'Choir Aahs', 'Voice Oohs', 'Synth Voice', 'Orchestra Hit',
    'Trumpet', 'Trombone', 'Tuba', 'Muted Trumpet',
    'French Horn', 'Brass Section', 'Synth Brass 1', 'Synth Brass 2',
    'Soprano Sax', 'Alto Sax', 'Tenor Sax', 'Baritone Sax',
    'Oboe', 'English Horn', 'Bassoon', 'Clarinet',
    'Piccolo', 'Flute', 'Recorder', 'Pan Flute',
    'Blown Bottle', 'Shakuhachi', 'Whistle', 'Ocarina',
    'Square Lead', 'Saw Lead', 'Calliope', 'Chiff',
    'Charang', 'Voice Lead', 'Fifths', 'Bass Lead',
    'New Age Pad', 'Warm Pad', 'Polysynth', 'Choir Pad',
    'Bowed Pad', 'Metallic Pad', 'Halo Pad', 'Sweep Pad',
    'Ice Rain', 'Soundtrack', 'Crystal', 'Atmosphere',
    'Brightness', 'Goblins', 'Echo Drops', 'Star Theme',
    'Sitar', 'Banjo', 'Shamisen', 'Koto',
    'Kalimba', 'Bagpipe', 'Fiddle', 'Shanai',
    'Tinkle Bell', 'Agogo', 'Steel Drums', 'Woodblock',
    'Taiko', 'Melodic Tom', 'Synth Drum', 'Reverse Cymbal',
    'Guitar Fret Noise', 'Breath Noise', 'Seashore', 'Bird Tweet',
    'Telephone Ring', 'Helicopter', 'Applause', 'Gunshot',
]


def _read_vlq(data, offset):
    value = 0
    while True:
        b = data[offset]
        offset += 1
        value = (value << 7) | (b & 0x7F)
        if not (b & 0x80):
            break
    return value, offset


def _parse_midi_track(trk_data, ticks_per_qn):
    events = []
    offset = 0
    abs_ticks = 0
    status = 0
    program_changes = {}

    while offset < len(trk_data):
        delta, offset = _read_vlq(trk_data, offset)
        abs_ticks += delta

        if offset >= len(trk_data):
            break

        byte = trk_data[offset]

        if byte == 0xFF:
            offset += 1
            if offset >= len(trk_data):
                break
            meta_type = trk_data[offset]
            offset += 1
            length, offset = _read_vlq(trk_data, offset)
            meta_data = trk_data[offset:offset+length]
            offset += length
            events.append((abs_ticks, 'meta', meta_type, meta_data))

        elif byte == 0xF0 or byte == 0xF7:
            offset += 1
            length, offset = _read_vlq(trk_data, offset)
            offset += length

        elif byte & 0x80:
            status = byte
            offset += 1
            channel = status & 0x0F
            event_type = status & 0xF0

            if event_type == 0x90:
                if offset + 1 >= len(trk_data): break
                note = trk_data[offset]
                vel = trk_data[offset + 1]
                offset += 2
                events.append((abs_ticks, 'note_on', channel, note, vel))

            elif event_type == 0x80:
                if offset + 1 >= len(trk_data): break
                note = trk_data[offset]
                vel = trk_data[offset + 1]
                offset += 2
                events.append((abs_ticks, 'note_off', channel, note, vel))

            elif event_type == 0xC0:
                prog = trk_data[offset]
                offset += 1
                program_changes[channel] = (abs_ticks, prog)
                events.append((abs_ticks, 'program', channel, prog))

            elif event_type == 0xB0:
                offset += 2
            elif event_type == 0xA0:
                offset += 2
            elif event_type == 0xD0:
                offset += 1
            elif event_type == 0xE0:
                offset += 2
            else:
                continue
        else:
            if status & 0x80:
                channel = status & 0x0F
                event_type = status & 0xF0
                if event_type == 0x90:
                    note = byte
                    offset += 1
                    if offset >= len(trk_data): break
                    vel = trk_data[offset]
                    offset += 1
                    events.append((abs_ticks, 'note_on', channel, note, vel))
                elif event_type == 0x80:
                    note = byte
                    offset += 1
                    if offset >= len(trk_data): break
                    vel = trk_data[offset]
                    offset += 1
                    events.append((abs_ticks, 'note_off', channel, note, vel))
                else:
                    offset += 1
                    if offset < len(trk_data):
                        offset += 1
            else:
                break

    return events, program_changes


def _dur_to_code(d, max_dots=2):
    for val, code in _DUR_CODES:
        if abs(d - val) < 1e-9:
            return code
        for nd in range(1, max_dots + 1):
            dotted = val * (2 - 0.5 ** nd)
            if abs(d - dotted) < 1e-9:
                return code + '.' * nd
        triplet = val * 2 / 3
        if abs(d - triplet) < 1e-9:
            return code + 't'
    s = f"{d:.6f}".rstrip('0').rstrip('.')
    return f"_{s}"


def midi_to_song(fn):
    with open(fn, 'rb') as f:
        data = f.read()

    if data[:4] != b'MThd':
        raise ValueError("Not a valid MIDI file")

    header_len = struct.unpack('>I', data[4:8])[0]
    format_type = struct.unpack('>H', data[8:10])[0]
    num_tracks = struct.unpack('>H', data[10:12])[0]
    division = struct.unpack('>H', data[12:14])[0]

    if division & 0x8000:
        raise ValueError("SMPTE-based MIDI files not supported")
    ticks_per_qn = division

    pos = 14
    all_events = []
    tempos = []
    channel_programs = {}

    for track_idx in range(num_tracks):
        if pos + 8 > len(data):
            break
        if data[pos:pos+4] != b'MTrk':
            pos += 1
            continue
        trk_len = struct.unpack('>I', data[pos+4:pos+8])[0]
        trk_data = data[pos+8:pos+8+trk_len]
        pos += 8 + trk_len

        events, prog_changes = _parse_midi_track(trk_data, ticks_per_qn)
        for ch, (abs_t, prog) in prog_changes.items():
            if ch not in channel_programs:
                channel_programs[ch] = (abs_t, prog)

        for ev in events:
            if ev[1] == 'meta' and ev[2] == 0x51:
                md = ev[3]
                if len(md) >= 3:
                    micros = (md[0] << 16) | (md[1] << 8) | md[2]
                    bpm = 60_000_000.0 / micros
                    tempos.append((ev[0], bpm))
            elif ev[1] in ('note_on', 'note_off'):
                all_events.append(ev)

    # Break ties at the same tick with note_off before note_on, so a
    # same-tick retrigger of a note (off then on) doesn't get processed
    # out of order and silently swallow the note that's ending.
    all_events.sort(key=lambda x: (x[0], 0 if x[1] == 'note_off' else 1))
    tempos.sort(key=lambda x: x[0])

    # This DSL has no concept of a mid-song tempo change (a Song has one
    # constant tempo), so previously only the *first* tempo event's BPM
    # was used, even if it covered a handful of ticks before changing.
    # Use a tick-duration-weighted average across the whole file instead,
    # which tracks the source file's overall pacing much more closely.
    end_tick = max((ev[0] for ev in all_events), default=0)
    if len(tempos) <= 1:
        song_tempo = tempos[0][1] if tempos else 120.0
    else:
        weighted = 0.0
        for idx, (t_tick, bpm) in enumerate(tempos):
            seg_end = tempos[idx + 1][0] if idx + 1 < len(tempos) else end_tick
            weighted += max(0, seg_end - t_tick) * bpm
        span = max(1, end_tick - tempos[0][0])
        song_tempo = weighted / span
        warnings.warn(
            f"MIDI file has {len(tempos)} tempo changes; this format only "
            f"supports a single constant tempo, so a duration-weighted "
            f"average of {song_tempo:.1f} BPM is used instead"
        )

    song = Song(tempo=song_tempo)
    song.name = Path(fn).stem

    active_notes = {}
    channel_note_data = {}

    for ev in all_events:
        if ev[1] == 'note_on':
            _, _, ch, note, vel = ev
            key = (ch, note)
            if vel > 0:
                active_notes[key] = (ev[0], vel)
            else:
                if key in active_notes:
                    st, sv = active_notes.pop(key)
                    channel_note_data.setdefault(ch, []).append((st, ev[0], note, sv))
        elif ev[1] == 'note_off':
            _, _, ch, note, vel = ev
            key = (ch, note)
            if key in active_notes:
                st, sv = active_notes.pop(key)
                channel_note_data.setdefault(ch, []).append((st, ev[0], note, sv))

    max_tick = max((ev[0] for ev in all_events), default=0) + ticks_per_qn
    for key, (st, sv) in active_notes.items():
        ch, note = key
        channel_note_data.setdefault(ch, []).append((st, max_tick, note, sv))

    for ch in sorted(channel_note_data):
        notes_data = channel_note_data[ch]
        notes_data.sort(key=lambda x: x[0])

        if ch == 9:
            # Percussion channel: the note number picks a drum/cymbal
            # sound, not a pitch, so group by drum key (not by temporal
            # overlap+program) and give each key its own fitting voice.
            by_key = {}
            for note_data in notes_data:
                by_key.setdefault(note_data[2], []).append(note_data)
            for key in sorted(by_key):
                inst = _GM_DRUM_MAP.get(key, 'noise')
                name = _GM_DRUM_NAMES.get(key, f'Drum {key}')
                for vi, voice in enumerate(_split_voices(by_key[key])):
                    tr = Track(name=f"{name} v{vi+1}" if vi > 0 else name,
                               inst=inst, vol=0.5, pan=0.0)
                    _fill_track_from_voice(tr, voice, ticks_per_qn)
                    if tr.notes:
                        song.add(tr)
            continue

        prog = channel_programs.get(ch, (0, 0))[1]
        inst = _GM_MAP.get(prog, 'sine')
        name = _CHANNEL_NAMES[prog] if prog < len(_CHANNEL_NAMES) else f'Channel {ch + 1}'

        # Split overlapping notes into separate voices (polyphonic tracks),
        # then build a Song track per voice.
        for vi, voice in enumerate(_split_voices(notes_data)):
            tr = Track(name=f"{name} v{vi+1}" if vi > 0 else name, inst=inst, vol=0.5, pan=0.0)
            _fill_track_from_voice(tr, voice, ticks_per_qn)
            if tr.notes:
                song.add(tr)

    if not song.tracks:
        raise ValueError("No notes found in MIDI file")

    return song


def _split_voices(notes_data):
    """Split possibly-overlapping (start_tick, end_tick, note, vel) tuples
    into non-overlapping voices, each a chronological list with no two
    notes playing at once (so it can become one monophonic Track)."""
    voices = []
    for note_data in notes_data:
        start_tick = note_data[0]
        placed = False
        for voice in voices:
            if not voice or voice[-1][1] <= start_tick:
                voice.append(note_data)
                placed = True
                break
        if not placed:
            voices.append([note_data])
    return voices


def _fill_track_from_voice(tr, voice, ticks_per_qn):
    """Append rests/notes to `tr` reproducing the timing of `voice`."""
    current_tick = 0
    for start_tick, end_tick, midi_note, velocity in voice:
        if start_tick > current_tick:
            rd = (start_tick - current_tick) / ticks_per_qn
            if rd > 0.001:
                tr.notes.append(Note('R', rd, 0))

        dur = (end_tick - start_tick) / ticks_per_qn
        if dur <= 0.001:
            current_tick = end_tick
            continue

        note_name = midi_to_name(midi_note)
        vel = min(1.0, velocity / 127.0)
        tr.notes.append(Note(note_name, dur, vel))
        current_tick = end_tick


def song_to_text(song):
    lines = []
    lines.append(f"tempo: {song.tempo:.1f}")
    lines.append(f'name: "{song.name}"')
    if song.beats_per_bar != 4 or song.beat_unit != 4:
        lines.append(f"time: {song.beats_per_bar}/{song.beat_unit}")
    lines.append("")

    for tr in song.tracks:
        if not tr.notes:
            continue
        parts = [f"-- {tr.name}: {tr.inst}"]
        parts.append(f"vol:{tr.vol:.2f}")
        parts.append(f"pan:{tr.pan:.2f}")
        if tr.rev > 0:
            parts.append(f"reverb:{tr.rev}")
        if tr.delay > 0:
            parts.append(f"delay:{tr.delay}")
        if tr.sw > 0:
            parts.append(f"swing:{tr.sw}")
        lines.append(" ".join(parts) + " --")

        pos = 0.0
        line_notes = []
        for n in tr.notes:
            if n.pitch.startswith('$'):
                if line_notes:
                    lines.append(" ".join(line_notes))
                    line_notes = []
                lines.append(n.pitch)
                continue
            dc = _dur_to_code(n.duration) if not n.rest else _dur_to_code(n.duration)
            if n.rest:
                line_notes.append(f"R {dc}")
            else:
                # Preserve velocity (e.g. from MIDI) via the "@vel" note
                # suffix the parser already supports -- without this, every
                # re-imported note silently reverted to the default 0.8
                # velocity, so a .music export always played back flatter/
                # different than the Song rendered straight from the MIDI.
                line_notes.append(f"{n.pitch} {dc} @{n.velocity:.2f}")
            pos += n.duration

        if line_notes:
            lines.append(" ".join(line_notes))
        lines.append("")

    return "\n".join(lines)