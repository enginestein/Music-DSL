from __future__ import annotations
import math, re, warnings, random
from pathlib import Path
from collections import OrderedDict
from typing import Optional, Union, IO
import numpy as np

from ._pitch import pitch_to_midi, midi_to_name, name_to_freq, clamp
from ._keys import _apply_key, _key_tonic_and_scale
from ._durations import _parse_dur
from ._instruments import _INSTS, _INST_ADSR
from ._engine import _play, _save, _reverb, _delay, _compress
from ._constants import SAMPLE_RATE, CHANNELS
from ._chords import parse_chord

try:
    from scipy.signal import lfilter as _scipy_lfilter
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

_DYN_MAP = {'ppp':0.15,'pp':0.25,'p':0.35,'mp':0.50,'mf':0.70,
            'f':0.85,'ff':1.00,'fff':1.20,'sffz':1.30,'fp':(0.85,0.35)}

def _dyn_vel(m):
    v = _DYN_MAP.get(m)
    if isinstance(v, tuple): return v
    return v

def _lpf(x, fc, fs=SAMPLE_RATE):
    a = math.exp(-2*math.pi*fc/fs)
    if _HAS_SCIPY:
        return _scipy_lfilter([1.0-a], [1.0, -a], x)
    y = np.zeros_like(x)
    for i in range(len(x)):
        y[i] = a*y[i-1] + (1-a)*x[i] if i>0 else (1-a)*x[i]
    return y

def _hpf(x, fc, fs=SAMPLE_RATE):
    a = math.exp(-2*math.pi*fc/fs)
    if _HAS_SCIPY:
        return _scipy_lfilter([1.0-a, -(1.0-a)], [1.0, -a], x)
    y = np.zeros_like(x)
    for i in range(len(x)):
        y[i] = a*(y[i-1] + x[i] - x[i-1]) if i>0 else 0
    return y

def _bpf(x, fc, q, fs=SAMPLE_RATE):
    w0 = 2*math.pi*fc/fs
    alpha = math.sin(w0)/(2*q)
    b0 = alpha; b1 = 0; b2 = -alpha
    a0 = 1+alpha; a1 = -2*math.cos(w0); a2 = 1-alpha
    if _HAS_SCIPY:
        return _scipy_lfilter([b0/a0, b1/a0, b2/a0], [1.0, a1/a0, a2/a0], x)
    y = np.zeros_like(x)
    x1=x2=y1=y2=0.0
    for i in range(len(x)):
        xi = x[i]; yi = (b0*xi + b1*x1 + b2*x2 - a1*y1 - a2*y2)/a0
        x2,x1 = x1,xi; y2,y1 = y1,yi; y[i] = yi
    return y

class Note:
    __slots__ = ('pitch','duration','velocity','freq','rest','group',
                 'voice','staccato','legato','dynamic','vibrato','tremolo',
                 'portamento','grace','tie','tied','humanize_toff','humanize_voff',
                 'accent','probability')
    def __init__(self, pitch: str = 'R', duration: float = 1.0, velocity: float = 0.8) -> None:
        self.pitch = str(pitch)
        self.duration = float(duration)
        self.velocity = clamp(float(velocity))
        self.rest = self.pitch.lower() in ('r','rest','_','')
        self.freq = 0.0 if self.rest else name_to_freq(self.pitch)
        self.group = 0
        self.voice = 0
        self.staccato = False
        self.legato = False
        self.dynamic = ''
        self.vibrato = 0.0
        self.tremolo = 0.0
        self.portamento = 0.0
        self.grace = 0.0
        self.tie = False
        self.tied = False
        self.humanize_toff = 0.0
        self.humanize_voff = 0.0
        self.accent = 0
        self.probability = 1.0
    def __repr__(self) -> str:
        if self.rest: return f"R({self.duration:.3f})"
        return f"{self.pitch}({self.duration:.3f})"
    def copy(self) -> Note:
        c = Note(self.pitch, self.duration, self.velocity)
        for s in self.__slots__:
            if s not in ('pitch','duration','velocity'):
                setattr(c, s, getattr(self, s))
        return c

class Track:
    def __init__(self, name: str = '', inst: str = 'sine', vol: float = 0.5, pan: float = 0.0) -> None:
        self.name = name or inst
        self.inst = inst
        self.vol = clamp(float(vol))
        self.pan = clamp(float(pan), -1, 1)
        self.notes = []
        self.sw = 0.0
        self.rev = 0.0
        self.delay = 0.0
        default = _INST_ADSR.get(inst, {'a':0.01,'d':0.05,'s':0.8,'r':0.10})
        self.adsr = dict(default)
        self.transpose = 0
        self.beats_per_bar = 0
        self._bar_pos = 0.0
        self._cur_group = 0
        self.filter_type = ''
        self.filter_freq = 1000.0
        self.filter_q = 0.7
        self.dist_amount = 0.0
        self.humanize_timing = 0.0
        self.humanize_vel = 0.0
        self.lfo_filter_rate = 0.0
        self.lfo_filter_depth = 0.0
        self.mute = False
        # current global dynamic ('mf', 'ff', ...) — persists across lines
        self.cur_dyn = ''
        # %section blocks: name -> note list (filled by the parser)
        self.sections = OrderedDict()
        # scale-degree mode (Nashville-style '1 4 5 6m' relative to key)
        self.degrees = False
        self.key_name = 'C'
        # sidechain ducking: duck this track by another track's onsets
        self.sidechain_src = ''
        self.sidechain_amt = 0.0

    _DEG_RE = re.compile(r'^([#b]?)([1-7])([\',]*)$')

    def _deg_to_pitch(self, tok):
        """Resolve a scale-degree token ('1', '#4', 'b7,', '5''') to a pitch
        name relative to the track's key. Returns None if not a degree token.
        Degree 1 sits at octave 4; ' raises an octave, ',' lowers one."""
        m = self._DEG_RE.match(tok)
        if not m: return None
        acc, deg, octmarks = m.groups()
        tonic, scale, prefer_flat = _key_tonic_and_scale(self.key_name)
        pc = (tonic + scale[int(deg) - 1]) % 12
        midi = (4 + 1) * 12 + pc
        midi += 12 * octmarks.count("'") - 12 * octmarks.count(',')
        if acc == '#': midi += 1
        elif acc == 'b': midi -= 1
        # spell with flats when the user wrote 'b' or the key prefers flats
        return midi_to_name(midi, flat=(acc == 'b' or (acc != '#' and prefer_flat)))

    def line(self, text: str, key_acc: dict[str, str] = {}) -> Track:
        text = text.replace('|', ' | ').replace('||', ' || ')
        text = text.replace('(', ' ( ').replace(')', ' ) ')
        text = text.replace('{', ' { ').replace('}', ' } ')
        # Only pad a standalone '@' (command form, e.g. '@ transpose 2').
        # An '@' directly followed by a number is a note/chord velocity
        # suffix (e.g. 'C4 q @0.63') and must stay attached to its digits
        # so it survives as a single token -- padding it here used to
        # silently strip the velocity from every annotated note.
        text = re.sub(r'@(?![\d.])', ' @ ', text)
        def _pad_dots(m):
            run = m.group(0)
            if m.start() == 0:
                return ' . ' * len(run)
            prev = m.string[m.start()-1]
            if prev in 'whqestx':
                return run
            if prev.isdigit():
                idx = m.start() - 1
                while idx >= 0 and (m.string[idx].isdigit() or m.string[idx] == '.'):
                    idx -= 1
                if idx >= 0 and m.string[idx] in ('_', '@', ':'):
                    return run
            return ' . ' * len(run)
        text = re.sub(r'\.+', _pad_dots, text)
        text = text.replace('~', ' ~ ')
        toks = text.split()
        i = 0; cur = 1.0; cur_dyn = self.cur_dyn; tuplet_n = 0; cur_voice = 0
        cur_vib = 0.0; cur_tre = 0.0; cur_port = 0.0; cur_tie = False
        cur_prob = 1.0; cresc_notes = []
        while i < len(toks):
            t = toks[i]
            # inline comment — but '#4' is a scale degree token
            if t.startswith('#') and not re.match(r"^#[1-7][',]*$", t):
                i+=1; continue
            if t in _DYN_MAP:
                # bare dynamics token ('mf', 'ff', ...) sets the dynamic
                # level for all subsequent notes on this line
                cur_dyn = t; i+=1; continue
            if ':' in t and tuplet_n == 0:
                if t.startswith('voice:'):
                    try: cur_voice = int(t.split(':')[1]); i+=1; continue
                    except (ValueError, TypeError): pass
                if t.startswith('vibrato:'):
                    try: cur_vib = float(t.split(':')[1]); i+=1; continue
                    except (ValueError, TypeError): pass
                if t.startswith('tremolo:'):
                    try: cur_tre = float(t.split(':')[1]); i+=1; continue
                    except (ValueError, TypeError): pass
                if t.startswith('portamento:'):
                    try: cur_port = float(t.split(':')[1]); i+=1; continue
                    except (ValueError, TypeError): pass
                if t.startswith('filter:'):
                    rest = t.split(':',1)[1].split()
                    if rest:
                        self.filter_type = rest[0]
                        if len(rest)>1: self.filter_freq = float(rest[1])
                        if len(rest)>2: self.filter_q = float(rest[2])
                    i+=1; continue
                if t.startswith('dist:'):
                    try: self.dist_amount = clamp(float(t.split(':')[1]),0,1); i+=1; continue
                    except (ValueError, TypeError): pass
                if t.startswith('lfo:'):
                    ps = t.split(':',1)[1].strip().split()
                    if len(ps)>=1 and ps[0]=='filter' and len(ps)>=3:
                        self.lfo_filter_rate = float(ps[1]); self.lfo_filter_depth = float(ps[2])
                        if len(ps)>=4: self.filter_freq = float(ps[3])
                    i+=1; continue
                if t.startswith('tempo:'):
                    try:
                        v = float(t.split(':')[1])
                        self.notes.append(Note(f'$tempo:{v}', 0, 0))
                    except (ValueError, TypeError): pass
                    i+=1; continue
                if t.startswith('time:'):
                    try:
                        v = t.split(':',1)[1].strip()
                        parts = v.split('/')
                        if len(parts)==2 and int(parts[0])>0 and int(parts[1])>0:
                            self.notes.append(Note(f'$time:{int(parts[0])}/{int(parts[1])}', 0, 0))
                    except (ValueError, TypeError): pass
                    i+=1; continue
                if not any(t.startswith(p) for p in ('reverb:','delay:','swing:')):
                    try:
                        tn, tm = t.split(':',1)
                        tn = int(tn); tm = int(tm)
                        if tn > 0 and tm > 0:
                            tuplet_n = tn; tuplet_m = tm; i+=1; continue
                    except (ValueError, TypeError): pass
            if t in ('|','||'):
                if self.beats_per_bar > 0 and self._bar_pos > self.beats_per_bar + 0.001:
                    warnings.warn(f'bar overflow: {self._bar_pos:.3f}/{self.beats_per_bar} beats in {self.name}')
                self._bar_pos = 0.0; i+=1; continue
            if t in (',',''): i+=1; continue
            if t.startswith('$'):
                self.notes.append(Note(t, 0, 0)); i+=1; continue
            if t in ('[1', '[2]') or t.startswith('[1') or t == '[1]':
                self.notes.append(Note('$v1', 0, 0)); i+=1; continue
            if t in ('[2', '[2]') or t.startswith('[2'):
                self.notes.append(Note('$v2', 0, 0)); i+=1; continue
            if t == ']' or t.startswith(']'):
                i+=1; continue
            if t == '~':
                if self.notes:
                    self.notes[-1].tie = True
                cur_tie = True; i+=1; continue
            if t == '@':
                i+=1
                if i >= len(toks): continue
                tok = toks[i]
                if tok == 'transpose':
                    i+=1
                    if i < len(toks):
                        try: self.transpose = int(toks[i]); i+=1
                        except (ValueError, TypeError): pass
                    continue
                if tok in ('arp','arpeggio'):
                    i+=1; direction = 'up'
                    if i < len(toks) and toks[i] in ('up','down','ud','downup','rand'):
                        direction = toks[i]; i+=1
                    arp_pitches = []
                    if i < len(toks) and toks[i] == '(':
                        i+=1
                        while i < len(toks) and toks[i] != ')':
                            if toks[i] not in ('|','||',','): arp_pitches.append(toks[i])
                            i+=1
                        i+=1
                    elif i < len(toks):
                        ch = parse_chord(toks[i])
                        if ch is not None:
                            arp_pitches = [midi_to_name(m) for m in ch]; i+=1
                        elif re.match(r'^[A-G][b#]?\d+$', toks[i]):
                            arp_pitches = [toks[i]]; i+=1
                    nd = cur
                    if i < len(toks):
                        nd2 = _parse_dur(toks[i])
                        if nd2 is not None: nd = nd2; i+=1
                    if arp_pitches:
                        mids = sorted((pitch_to_midi(p) for p in arp_pitches
                                       if pitch_to_midi(p) is not None))
                        names = [midi_to_name(m) for m in mids]
                        if direction == 'down': names = names[::-1]
                        elif direction == 'ud': names = names + names[-2:0:-1]
                        elif direction == 'downup': names = names[::-1] + names[1:-1]
                        elif direction == 'rand': random.shuffle(names)
                        for p in names:
                            self._emit_note(_apply_key(p, key_acc), nd,
                                            cur_dyn, cur_voice, cur_vib, cur_tre,
                                            cur_port, prob=cur_prob)
                            self._bar_pos += nd
                    continue
                if tok == 'humanize':
                    i+=1
                    while i < len(toks) and ':' in toks[i]:
                        parts = toks[i].split(':')
                        if parts[0]=='timing': self.humanize_timing = clamp(float(parts[1]),0,0.1)
                        elif parts[0]=='vel': self.humanize_vel = clamp(float(parts[1]),0,0.5)
                        i+=1
                    continue
                if tok == 'steps':
                    i+=1
                    if i < len(toks):
                        try: nsteps = int(toks[i]); i+=1
                        except (ValueError, TypeError): nsteps = 8
                    if i < len(toks) and toks[i]=='{':
                        i+=1; steps = []
                        while i < len(toks) and toks[i] != '}':
                            if toks[i] not in (',',''):
                                ste = toks[i]
                                if ste in _DYN_MAP:
                                    cur_dyn = ste
                                elif ste.startswith('voice:'):
                                    try: cur_voice = int(ste.split(':')[1])
                                    except (ValueError, TypeError): pass
                                else:
                                    steps.append(ste)
                            i+=1
                        i+=1
                        nd = cur / max(nsteps,1)
                        for ste in steps:
                            if ste == '.' or ste.lower() in ('r','rest','_',''):
                                self.notes.append(Note('R', nd, 0))
                            else:
                                p = _apply_key(ste, key_acc)
                                n = self._mknote(p, nd, 0.8, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                                if n:
                                    if cur_tie: n.tie = True; cur_tie = False
                                    self.notes.append(n)
                                    if n.rest or n.pitch.startswith('$'): pass
                                    elif cresc_notes is not None: cresc_notes.append(n)
                    continue
                if tok == 'drums':
                    # @drums 16 { x . x x . x . x x . x . x x . x }
                    # or shorthand bars:  @drums x-x-x-x | x-x-x-x
                    i+=1; nsteps = None
                    if i < len(toks):
                        try: nsteps = int(toks[i]); i+=1
                        except (ValueError, TypeError): nsteps = None
                    steps = []
                    if i < len(toks) and toks[i] == '{':
                        i+=1
                        while i < len(toks) and toks[i] != '}':
                            if toks[i] not in (',','|','||'): steps.append(toks[i])
                            i+=1
                        i+=1
                    else:
                        while i < len(toks) and toks[i] not in ('|','||','@'):
                            if toks[i] not in (',',''): steps.append(toks[i])
                            i+=1
                    if steps:
                        if nsteps is None: nsteps = len(steps)
                        nd = cur / max(nsteps, 1)
                        for ste in steps:
                            if ste in ('x', 'X', 'o', 'hit'):
                                acc = 1.3 if ste == 'X' else 1.0
                                n = self._mknote('C2', nd, min(1.0, 0.9*acc), cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                                if n: self.notes.append(n)
                            elif ste in ('g', 'ghost'):
                                n = self._mknote('C2', nd, 0.35, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                                if n: self.notes.append(n)
                            else:
                                self.notes.append(Note('R', nd, 0))
                            self._bar_pos += nd
                    continue
                if tok in ('coin','rand','choose','shuffle'):
                    cmd = tok; i+=1; ps = []
                    while i < len(toks) and toks[i] not in ('|','||','@',')','}'):
                        if toks[i] not in (',','','.','~','#'): ps.append(toks[i])
                        i+=1
                    if ps:
                        if cmd == 'coin':
                            prob = 0.5
                            try: prob = float(ps[0]); ps = ps[1:]
                            except (ValueError, TypeError): pass
                            if random.random() < prob and ps:
                                self._emit_note(random.choice(ps), cur, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, pea='·' if not cur_tie else '~', prob=cur_prob)
                                if cur_tie: cur_tie = False
                        elif cmd == 'rand':
                            self._emit_note(random.choice(ps), cur, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, prob=cur_prob)
                        elif cmd == 'choose':
                            for p in ps:
                                self._emit_note(p, cur/len(ps), cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, prob=cur_prob)
                        elif cmd == 'shuffle':
                            random.shuffle(ps)
                            for p in ps:
                                self._emit_note(p, cur, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, prob=cur_prob)
                    continue
                try: cur = float(tok); i+=1
                except (ValueError, TypeError): pass
                continue
            if t == '(':
                ps = []; i+=1
                while i < len(toks) and toks[i] != ')':
                    if toks[i] not in ('|','||',','): ps.append(toks[i])
                    i+=1
                i+=1; nd = cur
                if i < len(toks) and toks[i] not in ('|','||',',','(',')','@',')','}'):
                    nd2 = _parse_dur(toks[i])
                    if nd2 is not None: nd = nd2; i+=1
                self._cur_group += 1
                for p in ps:
                    n = self._mknote(p, nd, 0.8, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                    if n:
                        n.group = self._cur_group
                        if cur_tie: n.tie = True; cur_tie = False
                        self.notes.append(n)
                        if n.rest or n.pitch.startswith('$'): pass
                        elif cresc_notes is not None: cresc_notes.append(n)
                self._bar_pos += nd; cur = nd; continue
            if t == '{':
                if i+1 < len(toks) and tuplet_n > 0:
                    ps = []; i+=1
                    while i < len(toks) and toks[i] != '}':
                        if toks[i] not in ('|','||',','): ps.append(toks[i])
                        i+=1
                    i+=1; scale = tuplet_m / max(tuplet_n, 1); nd = cur * scale
                    for p in ps:
                        self._emit_note(p, nd, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, prob=cur_prob)
                        if cur_tie: self.notes[-1].tie = True; cur_tie = False
                    self._bar_pos += nd * len(ps); tuplet_n = 0
                elif i+1 < len(toks) and toks[i+1] != '}':
                    i+=1; ps = []
                    while i < len(toks) and toks[i] != '}':
                        if toks[i] not in ('|','||',','): ps.append(toks[i])
                        i+=1
                    i+=1; gdur = cur * 0.25
                    for p in ps:
                        n = self._mknote(p, gdur, 0.5, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                        if n: n.grace = gdur; self.notes.append(n)
                else: i+=1
                continue
            if t.lower() in ('r','rest','_',''):
                nd = cur
                if i+1 < len(toks):
                    nd2 = _parse_dur(toks[i+1])
                    if nd2 is not None: nd = nd2; i+=1
                n = Note('R', nd, 0)
                if cur_tie: n.tie = True; cur_tie = False
                self.notes.append(n)
                self._bar_pos += nd; i+=1; continue
            if t == '~' and cur_tie:
                cur_tie = False; i+=1; continue
            if t.startswith('?'):
                parts = [t[1:]]
                while i+1 < len(toks) and (toks[i+1] == '.' or toks[i+1].replace('.','').isdigit()):
                    i+=1; parts.append(toks[i])
                val = ''.join(parts) or '1'
                try: cur_prob = clamp(float(val))
                except (ValueError, TypeError): cur_prob = 1.0
                if cur_prob < 0: cur_prob = 0
                i+=1; continue
            if t == '<':
                cresc_notes.clear()
                i+=1; continue
            if t == '>':
                if cresc_notes:
                    nnotes = len(cresc_notes)
                    for ci, cn in enumerate(cresc_notes):
                        if not cn.rest:
                            cn.velocity *= 1.0 + 0.4 * (ci / max(nnotes - 1, 1))
                cresc_notes.clear()
                i+=1; continue
            p = t
            accent_lvl = 0
            if p and p[0] in ('>','^','+'):
                accent_lvl = {'>':1,'^':2,'+':3}[p[0]]
                p = p[1:]
            if self.degrees and p and (p[0].isdigit() or p[:2] in ('#1','#2','#3','#4','#5','#6','#7','b1','b2','b3','b4','b5','b6','b7')):
                dm = re.match(r'^([#b]?[1-7][\'.]*)([A-Za-z0-9]*)$', p)
                if dm:
                    degtok, qual = dm.group(1), dm.group(2)
                    root_name = self._deg_to_pitch(degtok)
                    if root_name is not None:
                        root_midi = pitch_to_midi(root_name)
                        if qual:
                            from ._chords import _CHORD_INTERVALS
                            ivs = _CHORD_INTERVALS.get(qual)
                            if ivs is not None:
                                nd = cur; vel = 0.8; pea = '·'; i+=1
                                if i < len(toks):
                                    nt = toks[i]
                                    if nt == '.':
                                        pea = '.'; i+=1
                                        if i < len(toks):
                                            nd2 = _parse_dur(toks[i])
                                            if nd2 is not None: nd = nd2; i+=1
                                    elif nt == '~':
                                        pea = '~'; i+=1
                                        if i < len(toks):
                                            nd2 = _parse_dur(toks[i])
                                            if nd2 is not None: nd = nd2; i+=1
                                    else:
                                        nd2 = _parse_dur(nt)
                                        if nd2 is not None: nd = nd2; i+=1
                                if i < len(toks) and toks[i].startswith('@') and len(toks[i])>1:
                                    try: vel = clamp(float(toks[i][1:])); i+=1
                                    except (ValueError, TypeError): pass
                                self._cur_group += 1
                                # spell chord tones with flats if the degree
                                # resolved to a flat spelling (or flat key)
                                _, _, _pf = _key_tonic_and_scale(self.key_name)
                                _flat = 'b' in root_name or (_pf and '#' not in root_name)
                                for iv in ivs:
                                    n = self._mknote(midi_to_name(root_midi + iv, flat=_flat), nd, vel, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                                    if n:
                                        n.group = self._cur_group
                                        if pea == '.': n.staccato = True
                                        elif pea == '~': n.tie = True
                                        if accent_lvl: n.accent = accent_lvl
                                        self.notes.append(n)
                                        if n.rest or n.pitch.startswith('$'): pass
                                        elif cresc_notes is not None: cresc_notes.append(n)
                                self._bar_pos += nd; cur = nd; continue
                            # unknown quality: fall through as single degree note
                        p = root_name
            if not p or not p[0].isupper(): i+=1; continue

            m = re.match(r'^[A-G][b#]?(\d+)$', p)
            if m and 0 <= int(m.group(1)) <= 9:
                ch = None
            else:
                ch = parse_chord(p)
            if ch is not None:
                nd = cur; vel = 0.8; pea = '·'; i+=1
                if i < len(toks):
                    nt = toks[i]
                    if nt == '.':
                        pea = '.'; i+=1
                        if i < len(toks):
                            nd2 = _parse_dur(toks[i])
                            if nd2 is not None: nd = nd2; i+=1
                    elif nt == '~':
                        pea = '~'; i+=1
                        if i < len(toks):
                            nd2 = _parse_dur(toks[i])
                            if nd2 is not None: nd = nd2; i+=1
                    else:
                        nd2 = _parse_dur(nt)
                        if nd2 is not None: nd = nd2; i+=1
                if i < len(toks) and toks[i].startswith('@') and len(toks[i])>1:
                    try: vel = clamp(float(toks[i][1:])); i+=1
                    except (ValueError, TypeError): pass
                self._cur_group += 1
                for midi_val in ch:
                    nm = midi_to_name(midi_val)
                    nm = _apply_key(nm, key_acc)
                    n = self._mknote(nm, nd, vel, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
                    if n:
                        n.group = self._cur_group
                        if pea == '.': n.staccato = True
                        elif pea == '~': n.tie = True
                        if accent_lvl: n.accent = accent_lvl
                        self.notes.append(n)
                        if n.rest or n.pitch.startswith('$'): pass
                        elif cresc_notes is not None: cresc_notes.append(n)
                self._bar_pos += nd; cur = nd; continue

            nd = cur; vel = 0.8; pea = '·'; i+=1
            if i < len(toks):
                nt = toks[i]
                if nt == '.':
                    pea = '.'; i+=1
                    if i < len(toks):
                        nd2 = _parse_dur(toks[i])
                        if nd2 is not None: nd = nd2; i+=1
                elif nt == '~':
                    pea = '~'; i+=1
                    if i < len(toks):
                        nd2 = _parse_dur(toks[i])
                        if nd2 is not None: nd = nd2; i+=1
                else:
                    nd2 = _parse_dur(nt)
                    if nd2 is not None: nd = nd2; i+=1
            if i < len(toks) and toks[i].startswith('@') and len(toks[i])>1:
                try: vel = clamp(float(toks[i][1:])); i+=1
                except (ValueError, TypeError): pass
            p = _apply_key(p, key_acc)
            n = self._mknote(p, nd, vel, cur_dyn, cur_voice, cur_vib, cur_tre, cur_port, cur_prob)
            if n:
                if pea == '.': n.staccato = True
                elif pea == '~': n.tie = True
                if cur_tie: n.tie = True; cur_tie = False
                if accent_lvl: n.accent = accent_lvl
                self.notes.append(n)
                if n.rest or n.pitch.startswith('$'): pass
                elif cresc_notes is not None: cresc_notes.append(n)
            cur = nd
        # dynamics are global: persist to the track so a bare 'mf' line
        # keeps applying to all subsequent lines
        self.cur_dyn = cur_dyn
        return self

    def _emit_note(self, p, d, dyn='', voice=0, vib=0, tre=0, port=0, vel=0.8, pea='·', prob=1.0):
        n = self._mknote(p, d, vel, dyn, voice, vib, tre, port, prob)
        if n:
            if pea == '.': n.staccato = True
            elif pea == '~': n.tie = True
            self.notes.append(n)

    def _mknote(self, p, d, v=0.8, dyn='', voice=0, vib=0, tre=0, port=0, prob=1.0):
        p = p.strip()
        if not p or p.lower() in ('r','rest','_',''):
            n = Note('R', d, 0); n.voice = voice; self.notes.append(n); return None
        m = pitch_to_midi(p)
        if m is not None:
            if self.transpose: m += self.transpose; p = midi_to_name(m)
            n = Note(p, d, v)
            n.voice = voice; n.vibrato = vib; n.tremolo = tre; n.portamento = port
            n.probability = prob
            if dyn:
                dv = _dyn_vel(dyn)
                if isinstance(dv, tuple): n.velocity *= dv[0]
                elif dv is not None: n.velocity *= dv
            return n
        return None

    def beats(self) -> float:
        bp = 0.0; prev = 0; pdur = 0.0
        for n in self.notes:
            if n.pitch.startswith('$'): continue
            if n.rest:
                if prev != 0: bp += pdur; pdur = 0.0
                if n.group == 0 or n.group != prev: bp += n.duration
                prev = n.group; continue
            if n.group != 0 and n.group == prev: continue
            if prev != 0: bp += pdur
            if n.group == 0: bp += n.duration
            else: pdur = n.duration
            prev = n.group
        if prev != 0: bp += pdur
        return bp

    def copy(self) -> Track:
        t = Track(self.name, self.inst, self.vol, self.pan)
        t.notes = [n.copy() for n in self.notes]
        t.sw = self.sw; t.rev = self.rev; t.delay = self.delay
        t.transpose = self.transpose; t.beats_per_bar = self.beats_per_bar
        t._bar_pos = self._bar_pos; t.adsr = dict(self.adsr)
        t.filter_type = self.filter_type; t.filter_freq = self.filter_freq
        t.filter_q = self.filter_q; t.dist_amount = self.dist_amount
        t.humanize_timing = self.humanize_timing; t.humanize_vel = self.humanize_vel
        t.lfo_filter_rate = self.lfo_filter_rate; t.lfo_filter_depth = self.lfo_filter_depth
        t.mute = self.mute
        t.sections = OrderedDict((k, [n.copy() for n in v]) for k, v in self.sections.items())
        t.degrees = self.degrees; t.key_name = self.key_name
        t.cur_dyn = self.cur_dyn
        t.sidechain_src = self.sidechain_src; t.sidechain_amt = self.sidechain_amt
        return t

    def __repr__(self) -> str:
        return f"Track({self.name},{len(self.notes)} notes)"


class Song:
    def __init__(self, tempo: float = 120, name: str = '') -> None:
        self.tempo = float(tempo)
        self.name = name or 'Untitled'
        self.tracks = []
        self.rev = 0.0
        self.delay = 0.0
        self.beats_per_bar = 4
        self.beat_unit = 4
        # arrangement: list of (section_name, repeat_count); empty = linear song
        self.arrange = []
        self.defined_sections = set()
        # chord progression: list of (root_midi, [chord_midis]); one bar each
        self.progression = []
        # master bus: volume and soft-knee compressor (threshold, ratio)
        self.master_vol = 1.0
        self.master_comp = None
        self._render_cache = None
        self._cache_key = None

    def add(self, t): self.tracks.append(t); self._render_cache = None; return self
    @property
    def beat_secs(self): return 60.0/self.tempo
    def total_beats(self) -> float:
        return max((t.beats() for t in self.tracks), default=0.0)
    def dur_secs(self) -> float: return self.total_beats() * self.beat_secs

    def _cache_fingerprint(self):
        return (self.tempo, self.rev, self.delay, self.beats_per_bar,
                self.beat_unit, len(self.tracks), self.master_vol,
                self.master_comp, self.arrange and tuple(self.arrange) or (),
                tuple((id(t), t.sidechain_src, t.sidechain_amt, t.mute,
                       t.filter_type, t.filter_freq, t.dist_amount) for t in self.tracks))

    def render(self, extra: float = 0.5) -> np.ndarray:
        fp = self._cache_fingerprint()
        if self._render_cache is not None and self._cache_key == fp:
            return self._render_cache
        tb = self.total_beats()
        if tb == 0: raise ValueError("empty song")
        ex = int(extra*SAMPLE_RATE)
        ns = int(tb*self.beat_secs*SAMPLE_RATE)+ex
        mix = np.zeros((ns, CHANNELS), dtype=np.float64)
        rendered = []
        for tr in self.tracks:
            if tr.mute: continue
            trk = self._render_track(tr, ns)
            if tr.filter_type and tr.filter_type in ('lp','hp','bp'):
                fc = tr.filter_freq
                for ch in range(CHANNELS):
                    if tr.filter_type == 'lp': trk[:,ch] = _lpf(trk[:,ch], fc)
                    elif tr.filter_type == 'hp': trk[:,ch] = _hpf(trk[:,ch], fc)
                    elif tr.filter_type == 'bp': trk[:,ch] = _bpf(trk[:,ch], fc, tr.filter_q)
            if tr.dist_amount > 0:
                gain = 1 + tr.dist_amount * 10
                trk = np.tanh(trk * gain) / np.tanh(gain) if gain > 0 else trk
            rendered.append((tr, trk))
        # sidechain ducking: duck target tracks by the source track's onsets
        duck_cache = {}
        for tr, trk in rendered:
            if tr.sidechain_src and tr.sidechain_amt > 0:
                key = tr.sidechain_src
                if key not in duck_cache:
                    src = next((t for t in self.tracks if t.name == key and not t.mute), None)
                    duck_cache[key] = (self._duck_envelope(src, ns)
                                       if src is not None else None)
                env = duck_cache[key]
                if env is not None:
                    # env is a full-depth dip shape; scale by the target's amount
                    amt = min(0.9, max(0.0, tr.sidechain_amt))
                    trk = trk * (1.0 - (1.0 - env[:, None]) * (amt / 0.9))
            mix += trk
        if self.master_comp:
            mix = _compress(mix, *self.master_comp)
        peak = np.max(np.abs(mix))
        if peak > 1.0: mix = mix/peak*0.95
        if self.master_vol != 1.0: mix = mix * self.master_vol
        if self.rev > 0: mix = _reverb(mix, self.rev)
        if self.delay > 0: mix = _delay(mix, self.delay)
        self._render_cache = mix
        self._cache_key = self._cache_fingerprint()
        return mix

    def _note_onsets(self, tr):
        """Return [(time_sec, velocity)] note-on events for a track."""
        res = []; t = 0.0; bs = self.beat_secs; prev_group = 0
        for n in tr.notes:
            if n.pitch.startswith('$'): continue
            if n.group and n.group == prev_group:
                res.append((t, n.velocity)); continue
            if n.rest:
                t += n.duration; prev_group = n.group; continue
            res.append((t, n.velocity))
            t += n.duration; prev_group = n.group
        return [(ti*bs, v) for ti, v in res]

    def _duck_envelope(self, src, ns, release=0.15):
        """Build a gain envelope that dips to 0.1 on each source onset and
        recovers; callers scale the dip depth by the target track's amount."""
        env = np.ones(ns)
        rel_n = max(1, int(release * SAMPLE_RATE))
        rec = np.exp(-np.arange(rel_n) / (release * SAMPLE_RATE / 3.0))
        duck = 0.1 + 0.9 * rec
        for tsec, vel in self._note_onsets(src):
            st = int(tsec * SAMPLE_RATE)
            if st >= ns: continue
            end = min(ns, st + rel_n)
            env[st:end] = np.minimum(env[st:end], duck[:end-st])
        return env

    def _humanize_notes(self, notes, timing, vel):
        if not notes or (timing <= 0 and vel <= 0):
            return notes
        res = []
        for n in notes:
            c = n.copy()
            if timing > 0:
                c.humanize_toff = random.uniform(-timing, timing)
            if vel > 0:
                c.humanize_voff = random.uniform(-vel, vel)
                c.velocity = clamp(c.velocity + c.humanize_voff)
            res.append(c)
        return res

    def _merge_tied(self, notes):
        if not notes: return notes
        res = []
        i = 0
        while i < len(notes):
            n = notes[i]
            if n.rest or n.pitch.startswith('$'):
                res.append(n); i+=1; continue
            if n.tie and i+1 < len(notes):
                nn = notes[i+1]
                if not nn.rest and n.pitch == nn.pitch:
                    n.duration += nn.duration
                    nn.tied = True
                    res.append(n); i+=2; continue
            res.append(n); i+=1
        return [n for n in res if not n.tied]

    _ACCENT_VEL = {0:1.0, 1:1.3, 2:1.5, 3:1.8}

    def _synthesize_note(self, n, out, ns, time_sec, bs, wf, a, lg, rg, tr, last_freq, last_end):
        acc_vel = self._ACCENT_VEL.get(n.accent, 1.0)
        toff = n.humanize_toff * bs
        st = int((time_sec + toff) * SAMPLE_RATE)
        if st < 0: st = 0
        nsp = int(n.duration * bs * SAMPLE_RATE)
        if st >= ns: return last_freq, last_end, True
        if st+nsp > ns: nsp = ns-st
        if nsp <= 0: return last_freq, last_end, True
        t = np.arange(nsp, dtype=np.float64)/SAMPLE_RATE
        sig = wf(t, n.freq)
        env = self._env(nsp, a['a'], a['d'], a['s'], a['r'])
        if n.staccato: h = int(nsp*0.5); env[h:] = 0.0
        if n.legato and not n.tie:
            env = np.ones(nsp)
            env[:int(0.01*SAMPLE_RATE)] = np.linspace(0,1,int(0.01*SAMPLE_RATE))
        if n.vibrato > 0:
            sig = np.sin(2*np.pi*n.freq*(1.0+0.005*np.sin(2*np.pi*n.vibrato*t))*t)
        if n.tremolo > 0:
            sig *= 1.0 + 0.3 * np.sin(2*np.pi*n.tremolo*t)
        if n.portamento > 0 and last_freq is not None and st >= last_end:
            glide = min(nsp, int(n.portamento*SAMPLE_RATE))
            if glide > 0:
                freqs = np.linspace(last_freq, n.freq, glide)
                sig[:glide] = wf(t[:glide], freqs)
        sig = sig * env * n.velocity * acc_vel * tr.vol
        if tr.lfo_filter_rate > 0 and tr.lfo_filter_depth > 0 and tr.filter_type == 'lp':
            lfo_fc = tr.filter_freq + tr.lfo_filter_depth*np.sin(2*np.pi*tr.lfo_filter_rate*t)
            lfo_fc = np.maximum(lfo_fc, 20)
            BLOCK = 256
            for ch in range(CHANNELS):
                sig_ch = sig*(lg if ch==0 else rg)
                filtered = np.zeros_like(sig_ch)
                y_prev = 0.0
                for blk_start in range(0, len(sig_ch), BLOCK):
                    blk_end = min(blk_start + BLOCK, len(sig_ch))
                    fc_avg = np.mean(lfo_fc[blk_start:blk_end])
                    a_lfo = math.exp(-2*math.pi*fc_avg/SAMPLE_RATE) if fc_avg > 0 else 0
                    b = np.array([1.0 - a_lfo])
                    a = np.array([1.0, -a_lfo])
                    blk = sig_ch[blk_start:blk_end]
                    if _HAS_SCIPY:
                        filtered[blk_start:blk_end] = _scipy_lfilter(b, a, blk)
                    else:
                        for j in range(blk_start, blk_end):
                            filtered[j] = a_lfo*filtered[j-1] + (1-a_lfo)*sig_ch[j] if j > blk_start else a_lfo*y_prev + (1-a_lfo)*sig_ch[j]
                    y_prev = filtered[blk_end - 1]
                out[st:st+nsp,ch] += filtered
            return n.freq, st + nsp, False
        out[st:st+nsp,0] += sig*lg; out[st:st+nsp,1] += sig*rg
        return n.freq, st + nsp, False

    def _render_track(self, tr, ns):
        out = np.zeros((ns, CHANNELS), dtype=np.float64)
        bs = self.beat_secs; time_sec = 0.0
        wf = _INSTS.get(tr.inst, _INSTS['sine'])
        lg, rg = self._pan(tr.pan); a = tr.adsr
        notes_copy = [n.copy() for n in tr.notes]
        notes_copy = self._merge_tied(notes_copy)
        if tr.humanize_timing > 0 or tr.humanize_vel > 0:
            notes_copy = self._humanize_notes(notes_copy, tr.humanize_timing, tr.humanize_vel)
        if tr.sw > 0 and tr.sw != 0.5:
            notes_copy = self._swing_notes(notes_copy, tr.sw)
        last_freq = None; last_end = 0
        prev_group = 0; chord_dur = 0.0
        for n in notes_copy:
            if n.pitch.startswith('$'):
                if n.pitch.startswith('$tempo:'):
                    try: bs = 60.0 / float(n.pitch.split(':')[1])
                    except (ValueError, TypeError): pass
                if n.pitch.startswith('$time:'):
                    try:
                        num, den = n.pitch.split(':')[1].split('/')
                        tr.beats_per_bar = int(num); tr._bar_pos = 0.0
                    except (ValueError, TypeError): pass
                continue
            if n.probability < 1.0 and random.random() > n.probability:
                if n.group and not prev_group:
                    prev_group = n.group; chord_dur = n.duration
                    continue
                if n.group and n.group == prev_group:
                    continue
                prev_group = 0; chord_dur = 0
                time_sec += n.duration * bs
                continue
            if prev_group and n.group != prev_group:
                time_sec += chord_dur * bs; chord_dur = 0; prev_group = 0
            if n.rest:
                if prev_group:
                    time_sec += chord_dur * bs; chord_dur = 0; prev_group = 0
                time_sec += n.duration * bs; continue
            if n.group and n.group == prev_group:
                last_freq, last_end, _ = self._synthesize_note(n, out, ns, time_sec, bs, wf, a, lg, rg, tr, last_freq, last_end)
                continue
            last_freq, last_end, skipped = self._synthesize_note(n, out, ns, time_sec, bs, wf, a, lg, rg, tr, last_freq, last_end)
            if not skipped:
                if n.group:
                    chord_dur = n.duration; prev_group = n.group
                else:
                    time_sec += n.duration * bs
            else:
                time_sec += n.duration * bs
        if prev_group: time_sec += chord_dur * bs
        return out

    def _swing_notes(self, notes, amount):
        if amount <= 0 or amount >= 1 or amount == 0.5: return notes
        res = []; i = 0
        while i < len(notes):
            n = notes[i]
            bp = sum(notes[j].duration for j in range(i))
            ph = bp - math.floor(bp)
            if (ph < 0.01 and i+1 < len(notes) and n.duration <= 0.5
                    and notes[i+1].duration <= 0.5 and not (n.rest and notes[i+1].rest)
                    and n.group == 0 and notes[i+1].group == 0):
                nn = notes[i+1]; tot = n.duration + nn.duration
                d1 = tot*amount; d2 = tot*(1.0-amount)
                n1 = n.copy(); n1.duration = d1
                n2 = nn.copy(); n2.duration = d2
                res.append(n1); res.append(n2); i += 2
            else:
                res.append(n.copy()); i += 1
        return res

    def _env(self, n, at, de, su, re):
        env = np.ones(n)
        a = max(1, int(at*SAMPLE_RATE))
        d = max(1, int(de*SAMPLE_RATE))
        r = max(1, int(re*SAMPLE_RATE))
        if a > n: a = n
        dd = min(a+d, n)
        rs = max(a, n-r)
        if a: env[:a] = np.linspace(0,1,a)
        if dd > a: env[a:dd] = np.linspace(1,su,dd-a)
        if rs < n: env[rs:] = np.linspace(su,0,n-rs)
        return env

    def _pan(self, p):
        a = (p+1)*math.pi/4
        return math.cos(a), math.sin(a)

    @classmethod
    def from_midi(cls, fn: Union[str, Path]) -> Song:
        from ._midi import midi_to_song
        return midi_to_song(fn)

    def to_text(self) -> str:
        from ._midi import song_to_text
        return song_to_text(self)

    def play(self, wait: bool = True, start: float = 0.0,
             end: float = None, loop: int = 1) -> None:
        """Play the song. start/end are in seconds; loop >= 1 repeats it."""
        mix = self.render()
        sr = SAMPLE_RATE
        a = max(0, int(start * sr))
        b = len(mix) if end is None else min(len(mix), int(end * sr))
        if b <= a: return
        seg = mix[a:b]
        for _ in range(max(1, loop)):
            _play(seg, wait)
    def save(self, fn: Union[str, Path]) -> Path: _save(self.render(), str(fn)); return Path(fn).resolve()

    def show(self) -> None:
        d = self.dur_secs(); n = len(self.tracks)
        print(f"{'─'*56}")
        print(f"  {self.name}  ({d:.0f}s, {self.tempo} BPM)")
        print(f"{'─'*56}")
        for i,t in enumerate(self.tracks,1):
            extra = ''
            if t.mute: extra += ' [MUTED]'
            if t.filter_type: extra += f' filter:{t.filter_type}'
            if t.dist_amount > 0: extra += f' dist:{t.dist_amount:.2f}'
            if t.humanize_timing > 0: extra += f' hum:{t.humanize_timing:.3f}'
            print(f"  [{i}] {t.name}: {t.inst} vol={t.vol:.2f}{extra} ({len(t.notes)} notes)")
            if t.notes:
                pre = '  '.join(repr(x) for x in t.notes[:6])
                if len(t.notes)>6: pre += '  ...'
                print(f"      {pre}")
        print(f"{'─'*56}")

    def to_midi(self, fn: Union[str, Path]) -> None:
        import struct
        tb = self.total_beats()
        if tb == 0: raise ValueError("empty song")
        tempo_us = int(60.0/self.tempo*1000000)
        tpb = 480
        tracks_data = []
        for ch, tr in enumerate(self.tracks):
            notes = [n.copy() for n in tr.notes]
            notes = self._merge_tied(notes)
            events = []; bp = 0.0; prev = 0
            for n in notes:
                if n.pitch.startswith('$'): continue
                if n.rest:
                    if n.group==0 or n.group!=prev: bp+=n.duration
                    prev=n.group; continue
                if n.group!=0 and n.group==prev:
                    events.append((bp,'note',n.pitch,n.velocity,n.duration))
                    continue
                if prev!=0: bp+=pdur
                events.append((bp,'note',n.pitch,n.velocity,n.duration))
                if n.group==0: bp+=n.duration
                else: pdur=n.duration
                prev=n.group
            if prev!=0: bp+=pdur
            events.sort(key=lambda x:x[0])
            trk=self._midi_track(events,tempo_us,tpb,ch)
            tracks_data.append(trk)
        self._write_midi(fn,tracks_data,tpb)

    def _midi_track(self, events, tempo_us, tpb, channel=0):
        import struct
        trk = bytearray()
        trk.extend(b'MTrk')
        trk.extend(struct.pack('>I',0))
        self._write_vlq(trk,0)
        trk.extend([0xFF,0x51,0x03])
        trk.extend(struct.pack('>I',tempo_us)[1:])
        last_tick=0
        for bp,typ,pitch,vel,dur in events:
            tick=int(bp*tpb); dt=tick-last_tick; last_tick=tick
            if typ=='note':
                m=pitch_to_midi(pitch)
                if m is None: continue
                self._write_vlq(trk,dt)
                trk.extend([0x90 | (channel & 0x0F),m,int(vel*127)])
                self._write_vlq(trk,int(dur*tpb))
                trk.extend([0x80 | (channel & 0x0F),m,0])
        self._write_vlq(trk,0)
        trk.extend([0xFF,0x2F,0x00])
        length=len(trk)-8
        trk[4:8]=struct.pack('>I',length)
        return bytes(trk)

    def _write_vlq(self, buf, value):
        v=[value&0x7F]; value>>=7
        while value>0:
            v.append(0x80|(value&0x7F)); value>>=7
        v.reverse(); buf.extend(v)
        return len(v)

    def _write_midi(self, fn, tracks, tpb):
        import struct
        with open(fn,'wb') as f:
            f.write(b'MThd')
            f.write(struct.pack('>I',6))
            f.write(struct.pack('>HHH',1,len(tracks),tpb))
            for trk in tracks: f.write(trk)