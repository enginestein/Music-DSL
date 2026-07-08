import re

_DURS = {'w':4,'h':2,'q':1,'e':0.5,'s':0.25,'t':0.125,'x':0.0625}
_DUR_RE = re.compile(r'^([whqestx])(\.*)(t?)$')

def _parse_dur(val):
    if val is None: return None
    v = str(val).strip()
    if v.startswith('_'): return float(v[1:].replace('p', '.'))
    if v in _DURS: return _DURS[v]
    m = _DUR_RE.match(v)
    if m:
        b = _DURS[m.group(1)]
        d = len(m.group(2)); t = bool(m.group(3))
        if t: b *= 2/3
        if d: b *= 2 - 0.5**d
        return b
    try: return float(v)
    except: return None