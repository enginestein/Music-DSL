_SHARP_ORDER = ['F', 'C', 'G', 'D', 'A', 'E', 'B']
_FLAT_ORDER = ['B', 'E', 'A', 'D', 'G', 'C', 'F']

_MINOR_TO_RELATIVE = {
    'A': 'C', 'Bb': 'Db', 'B': 'D',
    'C': 'Eb', 'C#': 'E', 'D': 'F',
    'Eb': 'Gb', 'E': 'G', 'F': 'Ab',
    'F#': 'A', 'G': 'Bb', 'G#': 'B',
    'Ab': 'Cb', 'A#': 'C#', 'D#': 'F#',
}

def _key_accidentals(key):
    k = key.strip().lower().replace(' ', '')
    if k in ('none', '', 'c'):
        return {}
    is_minor = k.endswith('m')
    base = k.rstrip('m').upper()
    base = base[0].upper() + base[1:].lower() if len(base) > 1 else base.upper()
    if is_minor:
        rel = _MINOR_TO_RELATIVE.get(base)
        if rel:
            return _key_accidentals(rel)
        return {}
    if base == 'C': return {}
    if base == 'G': acc = {'F': 'F#'}
    elif base == 'D': acc = {'F': 'F#', 'C': 'C#'}
    elif base == 'A': acc = {'F': 'F#', 'C': 'C#', 'G': 'G#'}
    elif base == 'E': acc = {'F': 'F#', 'C': 'C#', 'G': 'G#', 'D': 'D#'}
    elif base == 'B': acc = {'F': 'F#', 'C': 'C#', 'G': 'G#', 'D': 'D#', 'A': 'A#'}
    elif base == 'F#': acc = {'F': 'F#', 'C': 'C#', 'G': 'G#', 'D': 'D#', 'A': 'A#', 'E': 'E#'}
    elif base == 'C#': acc = {'F': 'F#', 'C': 'C#', 'G': 'G#', 'D': 'D#', 'A': 'A#', 'E': 'E#', 'B': 'B#'}
    elif base == 'F': acc = {'B': 'Bb'}
    elif base == 'Bb': acc = {'B': 'Bb', 'E': 'Eb'}
    elif base == 'Eb': acc = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab'}
    elif base == 'Ab': acc = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab', 'D': 'Db'}
    elif base == 'Db': acc = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab', 'D': 'Db', 'G': 'Gb'}
    elif base == 'Gb': acc = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab', 'D': 'Db', 'G': 'Gb', 'C': 'Cb'}
    elif base == 'Cb': acc = {'B': 'Bb', 'E': 'Eb', 'A': 'Ab', 'D': 'Db', 'G': 'Gb', 'C': 'Cb', 'F': 'Fb'}
    else: return {}
    return acc

def _apply_key(pitch, acc_map):
    if not acc_map or len(pitch) < 2:
        return pitch
    note = pitch[0]
    if len(pitch) > 1 and pitch[1] in '#b':
        return pitch
    if note in acc_map:
        return acc_map[note] + pitch[1:]
    return pitch
