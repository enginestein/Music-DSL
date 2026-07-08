import struct
from pathlib import Path
from .models import Song, Track, Note
from ._pitch import midi_to_name

_DUR_CODES = [(4.0, 'w'), (2.0, 'h'), (1.0, 'q'), (0.5, 'e'),
              (0.25, 's'), (0.125, 't'), (0.0625, 'x')]

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
    56: 'square', 57: 'square', 58: 'square', 59: 'square',
    60: 'square', 61: 'square', 62: 'square', 63: 'square',
    64: 'sine', 65: 'sine', 66: 'sine', 67: 'sine',
    68: 'sine', 69: 'sine', 70: 'sine', 71: 'sine',
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

    all_events.sort(key=lambda x: x[0])
    tempos.sort(key=lambda x: x[0])

    song_tempo = 120.0
    if tempos:
        song_tempo = tempos[0][1]

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

        prog = channel_programs.get(ch, (0, 0))[1]
        inst = _GM_MAP.get(prog, 'sine')
        name = _CHANNEL_NAMES[prog] if prog < len(_CHANNEL_NAMES) else f'Channel {ch + 1}'

        # Split overlapping notes into separate voices (polyphonic tracks)
        voices = []  # list of tracks, each track is a list of (start_tick, end_tick, midi_note, velocity)
        for note_data in notes_data:
            start_tick, end_tick, midi_note, velocity = note_data
            placed = False
            # Try to place in an existing voice whose last note ends before this one starts
            for voice in voices:
                if not voice or voice[-1][1] <= start_tick:
                    voice.append(note_data)
                    placed = True
                    break
            if not placed:
                voices.append([note_data])

        # Create a Song track for each voice
        for vi, voice in enumerate(voices):
            tr = Track(name=f"{name} v{vi+1}" if vi > 0 else name, inst=inst, vol=0.5, pan=0.0)
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

            if tr.notes:
                song.add(tr)

    if not song.tracks:
        raise ValueError("No notes found in MIDI file")

    return song


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
                line_notes.append(f"{n.pitch} {dc}")
            pos += n.duration

        if line_notes:
            lines.append(" ".join(line_notes))
        lines.append("")

    return "\n".join(lines)
