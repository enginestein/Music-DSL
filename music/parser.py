from __future__ import annotations
import re
import warnings
from pathlib import Path
from typing import Union, IO
from collections import OrderedDict

from .models import Song, Track, Note
from ._keys import _key_accidentals
from ._durations import _parse_dur
from ._pitch import clamp
from ._instruments import _INSTS

def _expand_dc_markers(song):
    for tr in song.tracks:
        fine_idx = -1; dc_indices = []
        for i, n in enumerate(tr.notes):
            if n.pitch == '$fine': fine_idx = i
            elif n.pitch == '$dc': dc_indices.append(i)
        if not dc_indices: continue
        end = fine_idx if fine_idx >= 0 else len(tr.notes)
        insert = []
        for n in tr.notes[:end]:
            if n.pitch.startswith('$'): continue
            c = Note(n.pitch, n.duration, n.velocity)
            c.group = n.group; insert.append(c)
        new_notes = []; skip = set(dc_indices)
        if fine_idx >= 0: skip.add(fine_idx)
        for i, n in enumerate(tr.notes):
            if i not in skip: new_notes.append(n)
            if i in dc_indices: new_notes.extend(insert)
        tr.notes = new_notes

def _expand_ds_markers(song):
    for tr in song.tracks:
        segno_idx = -1; coda_idx = -1; ds_idx = -1
        for i, n in enumerate(tr.notes):
            if n.pitch == '$segno': segno_idx = i
            elif n.pitch == '$coda': coda_idx = i
            elif n.pitch == '$ds': ds_idx = i
        if ds_idx < 0 or segno_idx < 0: continue
        before_ds = []
        for n in tr.notes[:ds_idx]:
            if not n.pitch.startswith('$'):
                c = Note(n.pitch, n.duration, n.velocity)
                c.group = n.group; before_ds.append(c)
        segno_to_coda = []
        end = coda_idx if coda_idx >= 0 else len(tr.notes)
        for n in tr.notes[segno_idx+1:end]:
            if not n.pitch.startswith('$'):
                c = Note(n.pitch, n.duration, n.velocity)
                c.group = n.group; segno_to_coda.append(c)
        after_coda = []
        if coda_idx >= 0:
            for n in tr.notes[coda_idx+1:]:
                if not n.pitch.startswith('$'):
                    c = Note(n.pitch, n.duration, n.velocity)
                    c.group = n.group; after_coda.append(c)
        tr.notes = before_ds + segno_to_coda + after_coda

def _expand_voltas(song):
    for tr in song.tracks:
        markers = [(i, n.pitch) for i, n in enumerate(tr.notes)
                    if n.pitch in ('$v1', '$v2')]
        if not markers: continue
        pairs = []
        for j in range(0, len(markers)-1, 2):
            idx1, p1 = markers[j]; idx2, _ = markers[j+1]
            pairs.append((idx1, idx2, p1))
        half = len(pairs) // 2
        keep = set()
        drop = set()
        for pi, (s, e, pt) in enumerate(pairs):
            rg = range(s+1, e)
            if pi < half:
                if pt == '$v1': keep.update(rg)
                else: drop.update(rg)
            else:
                if pt == '$v2': keep.update(rg)
                else: drop.update(rg)
        new = []
        for i, n in enumerate(tr.notes):
            if n.pitch in ('$v1','$v2'): continue
            if i in drop: continue
            new.append(n)
        tr.notes = new

def _expand_jump_markers(song):
    labels = {}
    for tr in song.tracks:
        labels.clear()
        for i, n in enumerate(tr.notes):
            if n.pitch.startswith('$label:'):
                labels[n.pitch.split(':',1)[1]] = i
        jumps = [i for i, n in enumerate(tr.notes) if n.pitch.startswith('$jump:')]
        if not jumps or not labels: continue
        new_notes = []
        skip = set()
        jump_dests = {}
        for ji in jumps:
            nm = tr.notes[ji].pitch.split(':',1)[1]
            if nm in labels:
                jump_dests[ji] = labels[nm]
        if not jump_dests: continue
        skip = set(jump_dests.keys())
        for i, n in enumerate(tr.notes):
            if i in skip:
                if i in jump_dests:
                    dest = jump_dests[i]
                    for j in range(dest + 1, len(tr.notes)):
                        if tr.notes[j].pitch.startswith('$'): continue
                        c = Note(tr.notes[j].pitch, tr.notes[j].duration, tr.notes[j].velocity)
                        c.group = tr.notes[j].group
                        new_notes.append(c)
                continue
            new_notes.append(n)
        tr.notes = [n for n in new_notes if not n.pitch.startswith('$label:')]

def _expand_done_markers(song):
    for tr in song.tracks:
        done_idx = -1
        for i, n in enumerate(tr.notes):
            if n.pitch == '$done':
                done_idx = i
                break
        if done_idx >= 0:
            tr.notes = tr.notes[:done_idx]

def _preprocess_voltas(text):
    result = []
    i = 0
    while i < len(text):
        if (i+1 < len(text) and text[i] == '['
                and text[i+1] in ('1', '2')
                and (i+2 >= len(text) or text[i+2] in (' ', ']'))):
            vn = text[i+1]
            depth = 0; j = i + 2
            while j < len(text):
                if text[j] == '[': depth += 1
                elif text[j] == ']':
                    if depth == 0: break
                    depth -= 1
                j += 1
            content = text[i+2:j].strip()
            v1 = '$v1' if vn == '1' else '$v2'
            v2 = '$v2' if vn == '1' else '$v1'
            result.append(f'{v1} {content} {v2}')
            i = j + 1
        else:
            result.append(text[i])
            i += 1
    return ''.join(result)

def load(text_or_file: Union[str, Path, IO]) -> Song:
    if hasattr(text_or_file,'read'): text = text_or_file.read()
    else:
        p = Path(str(text_or_file))
        if not '\n' in str(text_or_file) and len(str(text_or_file))<260 and p.exists():
            text = p.read_text()
        else: text = str(text_or_file)

    text = _preprocess_voltas(text)
    song = Song(); tr = None; key_acc = {}
    patterns = OrderedDict()
    in_repeat = False; repeat_count = 1; repeat_notes = []
    pat_def = False; pat_name = ''

    def _tr():
        nonlocal tr
        if tr is None:
            tr = Track('default','sine'); song.add(tr)
        return tr

    def _new_tr(name='', inst='sine', vol=0.5, pan=0.0):
        nonlocal tr
        tr = Track(name, inst, vol, pan)
        tr.beats_per_bar = song.beats_per_bar; song.add(tr)
        return tr

    lines = text.split('\n')
    for lineno, rl in enumerate(lines, 1):
        l = rl.strip()
        if not l or l.startswith('#'): continue
        _cm = re.search(r'(?:^|\s)#', l)
        if _cm:
            l = l[:_cm.start()].strip()
            if not l: continue

        try:
            if l.startswith('--') and '--' in l[2:]:
                inner = l.strip('- ')
                name = ''; inst_name = 'sine'; vol = 0.5; pan = 0.0
                rev = 0.0; dly = 0.0; swng = 0.0
                ft = ''; ff = 1000.0; fq = 0.7; da = 0.0
                ht_t = 0.0; ht_v = 0.0; lr = 0.0; ld = 0.0
                mute_flag = False
                if ':' in inner:
                    parts = inner.split(':',1)
                    name = parts[0].strip(); raw = parts[1].strip()
                else: name = inner; raw = ''
                vol_set = False; pan_set = False
                _rawtokens = raw.split()
                _ti = 0
                if _rawtokens and _rawtokens[0] not in _INSTS and not any(
                    _rawtokens[0].startswith(p) for p in ('vol:', 'pan:', 'reverb:', 'delay:', 'swing:', 'filter:', 'dist:', 'lfo:', 'humanize')):
                    warnings.warn(f"unknown instrument '{_rawtokens[0]}' at line {lineno}, falling back to 'sine'")
                while _ti < len(_rawtokens):
                    tok = _rawtokens[_ti]; _ti += 1
                    if tok in _INSTS: inst_name = tok
                    elif tok.startswith('vol:'): vol = clamp(float(tok[4:])); vol_set = True
                    elif tok.startswith('pan:'): pan = clamp(float(tok[4:]),-1,1); pan_set = True
                    elif tok.startswith('reverb:'): rev = clamp(float(tok[7:]))
                    elif tok.startswith('delay:'): dly = clamp(float(tok[6:]))
                    elif tok.startswith('swing:'): swng = clamp(float(tok[6:]))
                    elif tok == 'mute':
                        mute_flag = True
                    elif tok.startswith('filter:'):
                        p = tok.split(':',1)[1].split()
                        if p: ft = p[0]
                        if len(p)>1: ff = float(p[1])
                        if len(p)>2: fq = float(p[2])
                    elif tok.startswith('dist:'):
                        try: da = clamp(float(tok.split(':')[1]),0,1)
                        except (ValueError, TypeError): pass
                    elif tok == 'humanize' or tok.startswith('humanize:'):
                        params = tok.split(':',1)[1:]  # gets ['timing:0.02 vel:0.1'] or []
                        if not params and _ti < len(_rawtokens):
                            params = [_rawtokens[_ti]]; _ti += 1
                        for ht in (params[0].split() if params else []):
                            if ':' in ht:
                                hp = ht.split(':')
                                if hp[0]=='timing': ht_t = clamp(float(hp[1]),0,0.1)
                                elif hp[0]=='vel': ht_v = clamp(float(hp[1]),0,0.5)
                    elif tok.startswith('lfo:'):
                        ps = [tok.split(':',1)[1].strip()]
                        while _ti < len(_rawtokens) and len(ps) < 4:
                            try: float(_rawtokens[_ti]); ps.append(_rawtokens[_ti]); _ti += 1
                            except (ValueError, TypeError): break
                        if len(ps)>=1 and ps[0]=='filter' and len(ps)>=3:
                            lr = float(ps[1]); ld = float(ps[2])
                            if len(ps)>=4: ff = float(ps[3])
                    else:
                        try:
                            f = float(tok)
                            if not vol_set: vol = clamp(f); vol_set = True
                            elif not pan_set: pan = clamp(f,-1,1); pan_set = True
                        except (ValueError, TypeError): pass
                tr = _new_tr(name, inst_name, vol, pan)
                tr.mute = mute_flag
                tr.rev = rev; tr.delay = dly; tr.sw = swng
                if ft: tr.filter_type = ft; tr.filter_freq = ff; tr.filter_q = fq
                if da: tr.dist_amount = da
                if ht_t: tr.humanize_timing = ht_t
                if ht_v: tr.humanize_vel = ht_v
                if lr: tr.lfo_filter_rate = lr; tr.lfo_filter_depth = ld
                continue

            if l.startswith('inst:'):
                parts = l[5:].strip().split()
                nm = parts[0]
                v = float(parts[1]) if len(parts)>1 else 0.5
                p = float(parts[2]) if len(parts)>2 else 0.0
                _new_tr(nm, nm, v, p); continue

            if l.startswith('tempo'):
                rest = l.split(':',1)[-1].strip().split()
                if len(rest) == 1 and rest[0].replace('.','').replace('-','').isdigit():
                    song.tempo = float(rest[0]); continue
            if l.startswith('name'):
                song.name = l.split(':',1)[-1].strip().strip('\'"'); continue
            if l.startswith('key'):
                k = l.split(':',1)[-1].strip()
                if k.lower() in ('none','c'): key_acc = {}
                else: key_acc = _key_accidentals(k)
                continue
            if l.startswith('time'):
                v = l.split(':',1)[-1].strip().split()[0]
                parts = v.split('/')
                if len(parts) == 2:
                    song.beats_per_bar = int(parts[0]); song.beat_unit = int(parts[1])
                    _tr().beats_per_bar = song.beats_per_bar; _tr()._bar_pos = 0.0
                continue
            if l.startswith('reverb'):
                _tr().rev = clamp(float(l.split(':',1)[-1].strip())); continue
            if l.startswith('delay'):
                _tr().delay = clamp(float(l.split(':',1)[-1].strip())); continue
            if l.startswith('swing'):
                _tr().sw = clamp(float(l.split(':',1)[-1].strip())); continue
            if l.startswith('adsr'):
                v = l.split(':',1)[-1].strip().split()
                if len(v)>=4:
                    t = _tr()
                    t.adsr = {'a':float(v[0]),'d':float(v[1]),
                              's':float(v[2]),'r':float(v[3])}
                continue
            if l.startswith('filter:'):
                parts = l.split(':',1)[1].strip().split()
                if parts:
                    _tr().filter_type = parts[0]
                    if len(parts)>1: _tr().filter_freq = float(parts[1])
                    if len(parts)>2: _tr().filter_q = float(parts[2])
                continue
            if l.startswith('dist:'):
                try: _tr().dist_amount = clamp(float(l.split(':',1)[1].strip()),0,1)
                except (ValueError, TypeError): pass
                continue
            if l.startswith('humanize:'):
                h = l.split(':',1)[1].strip().split()
                for tok in h:
                    if ':' in tok:
                        p = tok.split(':')
                        if p[0]=='timing': _tr().humanize_timing = clamp(float(p[1]),0,0.1)
                        elif p[0]=='vel': _tr().humanize_vel = clamp(float(p[1]),0,0.5)
                continue

            if l.startswith('@include'):
                fn = l.split(None,1)[-1].strip().strip('"\'')
                p = Path(fn)
                if p.exists():
                    sub = load(str(p))
                    cur_inst = _tr().inst
                    for st in sub.tracks:
                        if cur_inst != 'sine':
                            st.inst = cur_inst
                        song.add(st)
                continue

            if l.startswith('@pattern') or (l.startswith('@') and '=' in l):
                if '=' in l:
                    pat_name = l.split('=')[0].strip().lstrip('@').strip()
                    pat_text = l.split('=',1)[1].strip()
                else: pat_name = l.split(None,1)[1].strip(); pat_text = ''; pat_def = True; continue
                pat_t = Track('pattern','sine')
                pat_t.line(pat_text, key_acc)
                patterns[pat_name] = pat_t.notes; continue

            if pat_def:
                if l.startswith('@end') or l.startswith('--'): pat_def = False; continue
                pat_t = Track('pattern','sine')
                pat_t.line(l, key_acc)
                if pat_name in patterns: patterns[pat_name].extend(pat_t.notes)
                else: patterns[pat_name] = pat_t.notes; continue

            if l.startswith('@') and l[1:] in patterns:
                for n in patterns[l[1:]]:
                    c = Note(n.pitch,n.duration,n.velocity)
                    c.group = n.group; _tr().notes.append(c)
                continue

            if l.startswith('@jump'):
                nm = l.split(None,1)[-1].strip()
                _tr().notes.append(Note(f'$jump:{nm}', 0, 0))
                continue

            if l == '@done' or l.startswith('@done') and len(l) == 5:
                _tr().notes.append(Note('$done', 0, 0))
                continue

            if l.startswith('[') and ']' in l and not l.startswith('[1') and not l.startswith('[2'):
                inner = l[1:].split(']')[0].strip()
                after = l.split(']',1)[1].strip()
                is_label = (inner and ' ' not in inner
                            and not inner[0].isdigit()
                            and not (inner[0].isupper() and ':' in inner)
                            and not after.startswith('x'))
                if is_label:
                    _tr().notes.append(Note(f'$label:{inner}', 0, 0))
                    if after: _tr().line(after, key_acc)
                    continue

            if '[1' in l or '[2' in l:
                _tr().line(l.strip(), key_acc)
                continue

            if '[' in l and ']' in l:
                before, rest = l.split('[', 1)
                if before.strip(): _tr().line(before.strip(), key_acc)
                content, after = rest.split(']', 1)
                cnt = 1; after = after.strip()
                if after.startswith('x'):
                    m = re.match(r'x(\d+)(.*)', after)
                    if m:
                        try: cnt = int(m.group(1))
                        except (ValueError, TypeError): pass
                        after = m.group(2).strip()
                    else:
                        after = after[1:].strip()
                if content.strip():
                    t2 = Track(inst=_tr().inst)
                    t2.line(content.strip(), key_acc)
                    for _ in range(cnt):
                        for n in t2.notes:
                            c = Note(n.pitch,n.duration,n.velocity)
                            c.group = n.group; _tr().notes.append(c)
                if after: _tr().line(after, key_acc)
                continue

            if l.startswith('['):
                in_repeat = True; repeat_notes = []
                rp = l.lstrip('[').strip()
                if rp:
                    t2 = Track(inst=_tr().inst)
                    t2.line(rp, key_acc); repeat_notes.extend(t2.notes)
                continue
            if in_repeat:
                if ']' in l:
                    before, rest = l.split(']',1)
                    if before.strip():
                        t2 = Track(inst=_tr().inst)
                        t2.line(before.strip(), key_acc)
                        repeat_notes.extend(t2.notes)
                    rest = rest.strip(); cnt = 1
                    if rest.startswith('x'):
                        try: cnt = int(rest[1:].strip())
                        except (ValueError, TypeError): pass
                    for _ in range(cnt):
                        for n in repeat_notes:
                            c = Note(n.pitch,n.duration,n.velocity)
                            c.group = n.group; _tr().notes.append(c)
                    in_repeat = False; repeat_notes = []
                    continue
                t2 = Track(inst=_tr().inst)
                t2.line(l, key_acc); repeat_notes.extend(t2.notes)
                continue

            if not l.startswith('['):
                _tr().line(l, key_acc)
        except Exception as e:
            if str(e).startswith('error at line'): raise
            raise ValueError(f"error at line {lineno}: {e}")

    if in_repeat: raise ValueError("error at end: unclosed repeat bracket '['")
    if pat_def: raise ValueError(f"error at end: unclosed @pattern {pat_name}")
    _expand_done_markers(song)
    _expand_dc_markers(song)
    _expand_ds_markers(song)
    _expand_voltas(song)
    _expand_jump_markers(song)
    if not song.total_beats(): raise ValueError("error: no notes found")
    return song