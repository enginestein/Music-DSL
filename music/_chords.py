import re

_CHORD_INTERVALS = {
    '':    [0, 4, 7],
    'm':   [0, 3, 7],
    'min': [0, 3, 7],
    'maj': [0, 4, 7],
    'dim': [0, 3, 6],
    'aug': [0, 4, 8],
    '7':   [0, 4, 7, 10],
    'maj7': [0, 4, 7, 11],
    'M7':  [0, 4, 7, 11],
    'm7':  [0, 3, 7, 10],
    'dim7': [0, 3, 6, 9],
    'm7b5': [0, 3, 6, 10],
    'sus4': [0, 5, 7],
    'sus2': [0, 2, 7],
    'sus':  [0, 5, 7],
    '6':   [0, 4, 7, 9],
    'm6':  [0, 3, 7, 9],
    'add9': [0, 4, 7, 14],
    '9':   [0, 4, 7, 10, 14],
    'm9':  [0, 3, 7, 10, 14],
}

_SEMIS = {'C':0, 'C#':1, 'Db':1, 'D':2, 'D#':3, 'Eb':3, 'E':4,
          'F':5, 'F#':6, 'Gb':6, 'G':7, 'G#':8, 'Ab':8,
          'A':9, 'A#':10, 'Bb':10, 'B':11, 'Cb':11}

def parse_chord(text):
    text = text.strip()
    if not text: return None
    i = 0
    if text[0] not in 'ABCDEFG': return None
    i = 1
    if len(text) > i and text[i] in '#b': i += 1
    root = text[:i]
    rest = text[i:]
    ch_type = None
    oct_str = ''
    if not rest:
        ch_type = ''
    else:
        for ct in sorted(_CHORD_INTERVALS, key=len, reverse=True):
            if ct and rest.endswith(ct):
                ch_type = ct
                oct_str = rest[:-len(ct)]
                break
        else:
            if rest[0].isdigit():
                oct_str = rest
            elif rest in _CHORD_INTERVALS:
                ch_type = rest
    if ch_type is None and not oct_str:
        return None
    if ch_type is None:
        return None
    root_pc = _SEMIS.get(root, 0)
    intervals = _CHORD_INTERVALS[ch_type]
    octave = int(oct_str) if oct_str else 4
    midis = [(root_pc + iv) + (octave + 1) * 12 for iv in intervals]
    return midis
