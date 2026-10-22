"""Interactive jamming session for the Music DSL.

Type note lines and hear them immediately. The session keeps a running
song; :save writes the whole jam to a .music file (serialized from the
parsed song, so loaded files and live-entered notes both survive).
"""
from __future__ import annotations
import sys
from pathlib import Path

from .models import Song, Track
from .parser import load

_HELP = """\
commands:
  :track NAME INST [VOL] [PAN]   select/create a track (e.g. :track lead organ 0.4)
  :tracks                        list session tracks
  :tempo BPM                     set tempo
  :key KEY                       set key (C, Am, F#m, ...)
  :time N/D                      set time signature
  :dyn DYN                       set dynamics for following notes (p, mf, fff, ...)
  :degrees on|off                scale-degree mode for the current track
  :fx reverb|delay|swing|filter ...   set an effect on the current track
  :play                          play everything entered so far
  :show                          summarize the session song
  :undo                          remove the last note you entered
  :clear                         clear all notes (keeps tracks/settings)
  :save FILE                     write the session to a .music file
  :help                          this help
  :quit                          exit

anything else is parsed as a note line and played immediately, e.g.:
  C4 q E4 q G4 q C5 q
  (C4 E4 G4) h
  1 q 4 q 5 q          (with :degrees on)
"""

_DUR_CODES = {4.0: 'w', 2.0: 'h', 1.0: 'q', 0.5: 'e',
              0.25: 's', 0.125: 't', 0.0625: 'x'}

def _fmt_dur(d):
    code = _DUR_CODES.get(d)
    if code: return code
    return '_' + format(d, '.6g')

_ACCENT_MARK = {1: '>', 2: '^', 3: '+'}

def _serialize_track(tr):
    """Serialize a Track back to .music DSL text (one track block)."""
    out = []
    hdr = f"-- {tr.name}: {tr.inst} {tr.vol:g} {tr.pan:g}"
    if tr.mute: hdr += " mute"
    out.append(hdr + " --")
    if tr.key_name and tr.key_name != 'C':
        out.append(f"key: {tr.key_name}")
    if tr.rev: out.append(f"reverb:{tr.rev:g}")
    if tr.delay: out.append(f"delay:{tr.delay:g}")
    if tr.sw: out.append(f"swing:{tr.sw:g}")
    if tr.filter_type:
        out.append(f"filter:{tr.filter_type} {tr.filter_freq:g} {tr.filter_q:g}")
    if tr.dist_amount: out.append(f"dist:{tr.dist_amount:g}")
    if tr.humanize_timing or tr.humanize_vel:
        out.append(f"humanize timing:{tr.humanize_timing:g} vel:{tr.humanize_vel:g}")
    if tr.sidechain_src:
        out.append(f"sidechain:{tr.sidechain_src} {tr.sidechain_amt:g}")
    if tr.degrees: out.append("degrees:on")

    notes = tr.notes
    i = 0
    while i < len(notes):
        n = notes[i]
        if n.pitch.startswith('$'):
            out.append(n.pitch); i += 1; continue
        if n.rest:
            out.append(f"R {_fmt_dur(n.duration)}"); i += 1; continue
        # gather a chord group (contiguous same-group notes)
        if n.group:
            run = [n]; j = i + 1
            while (j < len(notes) and notes[j].group == n.group
                   and not notes[j].rest and not notes[j].pitch.startswith('$')):
                run.append(notes[j]); j += 1
        else:
            run = [n]; j = i + 1
        dur = _fmt_dur(run[0].duration)
        if len(run) > 1:
            body = '(' + ' '.join(x.pitch for x in run) + f') {dur}'
            if all(abs(x.velocity - run[0].velocity) < 1e-9 for x in run) \
                    and abs(run[0].velocity - 0.8) > 1e-9:
                body += f' @{run[0].velocity:g}'
            out.append(body)
        else:
            s = _ACCENT_MARK.get(n.accent, '')
            s += n.pitch + ('.' if n.staccato else '') + f' {dur}'
            if abs(n.velocity - 0.8) > 1e-9:
                s += f' @{n.velocity:g}'
            out.append(s)
        i = j
    return '\n'.join(out)

class _Session:
    def __init__(self):
        self.song = Song()
        self.song.tempo = 120
        self.cur = None          # current Track
        self.key_acc = {}
        self.key_name = 'C'
        self.dyn = ''

    def _ensure_track(self):
        if self.cur is None:
            self._add_track('jam', 'piano', 0.5, 0.0)
        return self.cur

    def _add_track(self, name, inst, vol=0.5, pan=0.0):
        t = Track(name, inst, vol, pan)
        t.key_name = self.key_name
        t.beats_per_bar = self.song.beats_per_bar
        self.song.add(t)
        self.cur = t
        return t

    def _find(self, name):
        for t in self.song.tracks:
            if t.name == name: return t
        return None

def live_repl(file=None):
    s = _Session()
    if file:
        p = Path(file)
        if not p.exists():
            print(f"not found: {p}"); return 1
        try:
            loaded = load(str(p))
        except Exception as e:
            print(f"error: {e}"); return 1
        s.song = loaded
        s.cur = loaded.tracks[0] if loaded.tracks else None
        if s.cur is not None:
            from ._keys import _key_accidentals
            s.key_name = s.cur.key_name
            s.key_acc = _key_accidentals(s.key_name)
        loaded.show()
        print(f"loaded {p} — type note lines to add to it, :help for commands")

    print("music live — type notes and press Enter to hear them (:help, :quit)")
    while True:
        try:
            raw = input('music> ').strip()
        except (EOFError, KeyboardInterrupt):
            print(); break
        if not raw: continue
        if raw.startswith(':'):
            cmd = raw[1:].split()
            if not cmd: continue
            name = cmd[0].lower(); args = cmd[1:]
            try:
                if name in ('quit','q','exit'): break
                elif name == 'help': print(_HELP)
                elif name == 'track':
                    if len(args) < 2:
                        print("  usage: :track NAME INST [VOL] [PAN]"); continue
                    t = s._find(args[0])
                    if t is None:
                        vol = float(args[2]) if len(args) > 2 else 0.5
                        pan = float(args[3]) if len(args) > 3 else 0.0
                        t = s._add_track(args[0], args[1], vol, pan)
                        print(f"  created track {t.name} ({t.inst})")
                    else:
                        s.cur = t
                        print(f"  switched to {t.name} ({t.inst})")
                elif name == 'tracks':
                    for t in s.song.tracks:
                        mark = ' *' if t is s.cur else ''
                        print(f"  {t.name}: {t.inst} vol={t.vol:.2f} ({len(t.notes)} notes){mark}")
                elif name == 'tempo':
                    s.song.tempo = float(args[0])
                    print(f"  tempo = {args[0]}")
                elif name == 'key':
                    from ._keys import _key_accidentals
                    s.key_name = args[0]
                    s.key_acc = _key_accidentals(args[0])
                    if s.cur is not None: s.cur.key_name = args[0]
                    print(f"  key = {args[0]}")
                elif name == 'time':
                    parts = args[0].split('/')
                    if len(parts) != 2 or int(parts[0]) <= 0 or int(parts[1]) <= 0:
                        print("  usage: :time N/D (e.g. :time 3/4)"); continue
                    s.song.beats_per_bar = int(parts[0])
                    s.song.beat_unit = int(parts[1])
                    if s.cur is not None:
                        s.cur.beats_per_bar = s.song.beats_per_bar
                        s.cur._bar_pos = 0.0
                    print(f"  time = {args[0]}")
                elif name == 'dyn':
                    s.dyn = args[0] if args else ''
                    print(f"  dynamics = {s.dyn or '(none)'}")
                elif name == 'degrees':
                    t = s._ensure_track()
                    v = args[0].lower() if args else 'on'
                    t.degrees = v not in ('off','none','0','false','no')
                    print(f"  {t.name}: degrees {'on' if t.degrees else 'off'}")
                elif name == 'fx':
                    if not args: print("  usage: :fx reverb 0.3 | :fx filter:lp 800"); continue
                    t = s._ensure_track()
                    kind = args[0]
                    if kind == 'reverb': t.rev = float(args[1])
                    elif kind == 'delay': t.delay = float(args[1])
                    elif kind == 'swing': t.sw = float(args[1])
                    elif kind.startswith('filter:'):
                        parts = ' '.join(args).split(':')
                        t.filter_type = parts[1] if len(parts) > 1 else 'lp'
                        nums = parts[-1].split()
                        if nums: t.filter_freq = float(nums[0])
                        if len(nums) > 1: t.filter_q = float(nums[1])
                    else: print(f"  unknown effect '{kind}'"); continue
                    print(f"  {kind} set on {t.name}")
                elif name == 'play':
                    if not s.song.tracks or not s.song.total_beats():
                        print("  nothing to play yet"); continue
                    print("  playing session...")
                    try: s.song.play()
                    except Exception as e: print(f"  playback error: {e}")
                elif name == 'show':
                    if not s.song.tracks: print("  empty session"); continue
                    s.song.show()
                elif name == 'undo':
                    removed = False
                    for t in reversed(s.song.tracks):
                        if t.notes:
                            t.notes.pop(); removed = True
                            print(f"  removed last note from {t.name}")
                            break
                    if not removed: print("  nothing to undo")
                elif name == 'clear':
                    for t in s.song.tracks: t.notes = []
                    print("  cleared all notes")
                elif name == 'save':
                    if not args: print("  usage: :save FILE.music"); continue
                    tracks = [t for t in s.song.tracks if t.notes]
                    if not tracks: print("  nothing to save yet"); continue
                    out = [f"# {s.song.name or 'Jam'} — jammed with music --live",
                           f"tempo: {s.song.tempo:g}"]
                    if s.song.name: out.append(f"name: {s.song.name}")
                    if s.song.beats_per_bar != 4 or s.song.beat_unit != 4:
                        out.append(f"time: {s.song.beats_per_bar}/{s.song.beat_unit}")
                    for t in tracks:
                        out.append('')
                        out.append(_serialize_track(t))
                    Path(args[0]).write_text('\n'.join(out) + '\n')
                    print(f"  saved to {args[0]} ({len(tracks)} tracks)")
                else:
                    print(f"  unknown command :{name} — :help for commands")
            except (ValueError, IndexError, KeyError) as e:
                print(f"  error: {e}")
            continue

        # a note line: preview it, then keep it in the session
        t = s._ensure_track()
        preview = Track(t.name, t.inst, t.vol, t.pan)
        preview.adsr = dict(t.adsr)
        preview.rev = t.rev; preview.delay = t.delay; preview.sw = t.sw
        preview.filter_type = t.filter_type; preview.filter_freq = t.filter_freq
        preview.filter_q = t.filter_q; preview.dist_amount = t.dist_amount
        preview.key_name = t.key_name; preview.degrees = t.degrees
        try:
            text = f"{s.dyn} {raw}" if s.dyn else raw
            preview.line(text, s.key_acc)
        except Exception as e:
            print(f"  {e}"); continue
        if not preview.notes:
            print("  (no notes recognized)"); continue
        tmp = Song(s.song.tempo, 'preview')
        tmp.beats_per_bar = s.song.beats_per_bar
        tmp.add(preview)
        try:
            tmp.play()
        except Exception as e:
            print(f"  playback error: {e}")
        t.notes.extend(preview.notes)
    print("bye")
    return 0
