import re

_SEMIS = {'C':0,'C#':1,'Db':1,'D':2,'D#':3,'Eb':3,'E':4,
          'F':5,'F#':6,'Gb':6,'G':7,'G#':8,'Ab':8,
          'A':9,'A#':10,'Bb':10,'B':11,'Cb':11}
_NOTE_RE = re.compile(r'^([A-G][b#]?)(-?\d+)$')
_NOTE_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']

def pitch_to_midi(name):
    m = _NOTE_RE.match(name)
    if not m: return None
    return (int(m.group(2))+1)*12 + _SEMIS[m.group(1)]

def midi_to_freq(m):
    return 440.0 * 2.0**((m-69)/12.0)

def name_to_freq(name):
    m = pitch_to_midi(name)
    return midi_to_freq(m) if m else 0.0

def midi_to_name(m):
    return _NOTE_NAMES[m % 12] + str(m // 12 - 1)

def clamp(v, lo=0, hi=1):
    return max(lo, min(hi, v))
