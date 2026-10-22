import sys, argparse
from pathlib import Path
from .parser import load
from .models import Song, Track, _DYN_MAP

def _add_play_flags(p):
    p.add_argument('--wave', action='store_true', help='play with waveform visualizer')
    p.add_argument('--loop', type=int, default=1, metavar='N', help='play N times (0 = forever)')
    p.add_argument('--from', dest='from_sec', type=float, default=0.0, metavar='SEC',
                   help='start playback at SEC seconds')
    p.add_argument('--to', dest='to_sec', type=float, default=None, metavar='SEC',
                   help='stop playback at SEC seconds')

def _do_play(s, args):
    if getattr(args, 'wave', False):
        from ._waveform import play_with_waveform
        mix = s.render()
        a = int(args.from_sec * 44100)
        b = len(mix) if args.to_sec is None else min(len(mix), int(args.to_sec * 44100))
        try: play_with_waveform(mix[a:b])
        except Exception as e: print(f"  playback error: {e}")
    else:
        try: s.play(True, args.from_sec, args.to_sec, args.loop or 1)
        except KeyboardInterrupt: pass
        except Exception as e: print(f"  playback error: {e}")

def _play_file(p, args):
    p = Path(p)
    if not p.exists(): print(f"not found: {p}"); return 1
    try: s = load(str(p))
    except Exception as e: print(f"error: {e}"); return 1
    s.show()
    _do_play(s, args)
    return 0

def _export(path, out):
    p = Path(path)
    if not p.exists():
        print(f"not found: {p}")
        return 1
    out_p = Path(out)
    try:
        s = load(str(p)); s.show(); s.save(str(out_p))
    except Exception as e:
        print(f"error: {e}"); return 1
    if out_p.suffix.lower() == '.wav' and (not out_p.exists() or out_p.stat().st_size == 44):
        print(f"  warning: {out} appears to be empty (no audio data)")
    print(f"  saved to {out}")
    return 0

def _import_midi(path, out=None, args=None):
    p = Path(path)
    if not p.exists():
        print(f"not found: {p}")
        return 1
    try:
        s = Song.from_midi(str(p))
    except Exception as e:
        print(f"error: {e}")
        return 1
    print(f"  imported {len(s.tracks)} tracks, {s.total_beats():.1f} beats, {s.dur_secs():.1f}s")
    s.show()
    if out:
        text = s.to_text()
        Path(out).write_text(text)
        print(f"  saved to {out}")
    else:
        if args is not None and args.wave:
            from ._waveform import play_with_waveform
            play_with_waveform(s.render())
        else:
            try: s.play()
            except Exception as e: print(f"  playback error: {e}")
    return 0

def _check(path):
    from . import lint
    p = Path(path)
    errs, warns = lint(p)
    if errs and errs[0].startswith('not found'):
        print(errs[0]); return 1
    print(f"── check: {p} " + "─" * max(1, 40 - len(str(p))))
    for e in errs:  print(f"  error:   {e}")
    for w in warns: print(f"  warning: {w}")
    if not errs and not warns:
        print("  OK — no issues found")
        print("─" * 56)
        return 0
    print("─" * 56)
    print(f"  {len(errs)} error(s), {len(warns)} warning(s)")
    return 1 if errs else 0

_TEMPLATES = {
    'synthwave': {
        'tempo': 94, 'key': 'Cm', 'prog': 'Cm Ab Eb Bb',
        'arrange': 'intro verse chorus chorus outro',
        'title': 'Neon Nights',
        'body': '''\
@gen drums four

-- bass: sawtooth 0.35 -0.3 filter:lp 800 --
%intro
R w
%verse
@gen bass 8ths
%chorus
@gen bass 8ths oct
%outro
C2 w

-- pad: strings 0.18 0.0 reverb:0.6 delay:0.3 --
%verse
@gen pad
%chorus
@gen pad oct

-- lead: organ 0.4 0.25 reverb:0.4 delay:0.2 --
%chorus
C5 e Eb5 e G5 e C6 e  G5 q Eb5 e C5 e
Bb4 e Eb5 e G5 e Bb5 e  G5 q Eb5 q
'''},
    'rock': {
        'tempo': 132, 'key': 'Em', 'prog': 'Em C G D',
        'arrange': 'intro verse chorus chorus outro',
        'title': 'Thunder Road',
        'body': '''\
@gen drums rock

-- bass: bass 0.5 0.0 --
%intro
R w
%verse
@gen bass quarters root
%chorus
@gen bass 8ths
%outro
E2 w

-- gtr: guitar 0.4 0.15 dist:0.3 --
%verse
Em q Em q C q C q  G q G q D q D q
%chorus
Em h C h  G h D h
'''},
    'jazz': {
        'tempo': 140, 'key': 'C', 'prog': 'Cmaj7 Am7 Dm7 G7',
        'arrange': 'intro verse verse outro',
        'title': 'Blue Hour',
        'body': '''\
@gen drums shuffle

-- bass: bass 0.45 -0.1 --
%intro
R w
%verse
@gen bass quarters
%outro
C2 w

-- keys: piano 0.45 0.1 reverb:0.25 --
%verse
Cmaj7 q R q Am7 q R q  Dm7 q R q G7 q R q
'''},
    'ambient': {
        'tempo': 70, 'key': 'D', 'prog': 'Dmaj7 Bm7 Gmaj7 A',
        'arrange': 'drone swell swell drone',
        'title': 'Still Water',
        'body': '''\
-- pad: pad 0.25 0.0 reverb:0.75 delay:0.4 humanize:timing:0.03 --
%drone
D3 w
%swell
@gen pad
'''},
    'hiphop': {
        'tempo': 88, 'key': 'Fm', 'prog': 'Fm Db Ab Eb',
        'arrange': 'intro verse chorus chorus outro',
        'title': 'Downtown',
        'body': '''\
@gen drums break

-- bass: bass 0.55 -0.2 filter:lp 600 --
%intro
R w
%verse
@gen bass 8ths root
%chorus
@gen bass 8ths root8
%outro
F2 w

-- keys: clavinet 0.35 0.2 --
%verse
[
Fm2 e R e R e Fm2 e
Db2 e R e Ab2 e R e
] x2
'''},
    'blank': None,
}

def _new_file(path, style, title=None, tempo=None):
    p = Path(path)
    if p.exists():
        print(f"refusing to overwrite existing {p}")
        return 1
    if style == 'blank':
        t = tempo if tempo is not None else 120
        nm = title or 'Untitled'
        body = f"""tempo: {t}
name: {nm}
key: C

-- melody: piano 0.5 0.0 --
C4 q  E4 q  G4 q  C5 q
"""
    else:
        tpl = _TEMPLATES.get(style)
        if tpl is None:
            print(f"unknown style '{style}' (choose from: {', '.join(k for k in _TEMPLATES if _TEMPLATES[k])}, blank)")
            return 1
        t = tempo if tempo is not None else tpl['tempo']
        nm = title or tpl['title']
        body = f"""# {nm} — {style}
tempo: {t}
name: {nm}
key: {tpl['key']}
progression: {tpl['prog']}
arrange: {tpl['arrange']}

{tpl['body']}"""
    p.write_text(body)
    print(f"  created {p} ({style} template)")
    print(f"  play it:  music {p}")
    return 0

def _list_instruments():
    from ._instruments import _INSTS
    names = sorted(k for k in _INSTS if not k.startswith('_'))
    print(f"{len(names)} instruments:")
    for i in range(0, len(names), 6):
        print('  ' + '  '.join(f"{n:<14}" for n in names[i:i+6]))
    return 0

def _live(file=None):
    from ._live import live_repl
    return live_repl(file)

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog='music',
        description='Music DSL — write songs in plain text, play or export them.',
        epilog="examples:\n"
               "  music song.music                play a song\n"
               "  music song.music --loop 0       loop forever (Ctrl-C to stop)\n"
               "  music --export song.music out.mp3\n"
               "  music --check song.music        lint without playing\n"
               "  music --new song.music --style synthwave\n"
               "  music --live                    jam interactively\n",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('file', nargs='?', help='.music file to play (or .mid to import)')
    ap.add_argument('--version', action='store_true', help='show version')
    ap.add_argument('--midi', nargs=2, metavar=('IN', 'OUT'), help='export .music to MIDI')
    ap.add_argument('--export', nargs='+', metavar=('IN', 'OUT'),
                    help='export to WAV/MP3/OGG (OUT optional, default IN.wav)')
    ap.add_argument('--import-midi', nargs='+', metavar=('IN', 'OUT'),
                    help='import MIDI; optionally save as .music')
    ap.add_argument('--check', metavar='FILE', help='lint a .music file and report issues')
    ap.add_argument('--new', metavar='FILE', help='create a new song from a template')
    ap.add_argument('--style', default='synthwave', help='template style for --new')
    ap.add_argument('--title', default=None, help='song title for --new')
    ap.add_argument('--tempo', type=float, default=None, help='tempo override for --new')
    ap.add_argument('--live', nargs='?', const=True, default=False, metavar='FILE',
                    help='interactive jamming session')
    ap.add_argument('--list-instruments', action='store_true', help='list all instruments')
    _add_play_flags(ap)
    args = ap.parse_args(argv)

    if args.version:
        from . import __version__
        print(f"music-dsl {__version__}")
        return 0
    if args.list_instruments: return _list_instruments()
    if args.check: return _check(args.check)
    if args.new: return _new_file(args.new, args.style, args.title, args.tempo)
    if args.live is not False:
        return _live(None if args.live is True else args.live)
    if args.midi:
        p = Path(args.midi[0])
        if not p.exists(): print(f"not found: {args.midi[0]}"); return 1
        try:
            s = load(str(p)); s.to_midi(args.midi[1])
            print(f"  MIDI saved to {args.midi[1]}")
        except Exception as e: print(f"error: {e}"); return 1
        return 0
    if args.export:
        out = args.export[1] if len(args.export) > 1 else str(Path(args.export[0]).with_suffix('.wav'))
        return _export(args.export[0], out)
    if args.import_midi:
        out = args.import_midi[1] if len(args.import_midi) > 1 else None
        return _import_midi(args.import_midi[0], out, args)
    if args.file:
        name = args.file
        p = Path(name)
        if p.suffix in ('.mid', '.midi'):
            return _import_midi(name, None, args)
        if p.suffix == '.music' or p.exists():
            return _play_file(name, args)
        print(f"not found: {name}")
        return 1
    ap.print_help()
    return 0

if __name__=='__main__': main()
