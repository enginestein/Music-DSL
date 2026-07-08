import sys
from pathlib import Path
from .parser import load, _preprocess_voltas
from .models import Song, Track
from ._pitch import clamp

def _play_file(p):
    p = Path(p)
    if not p.exists(): print(f"not found: {p}"); return 1
    try: s = load(str(p))
    except Exception as e: print(f"error: {e}"); return 1
    s.show()
    do_wave = '--wave' in sys.argv
    if do_wave:
        from ._waveform import play_with_waveform
        try: play_with_waveform(s.render())
        except Exception as e: print(f"  playback error: {e}")
    else:
        try: s.play()
        except Exception as e: print(f"  playback error: {e}")
    return 0

def _export(path, out):
    p = Path(path)
    if p.exists():
        s = load(str(p)); s.show(); s.save(out)
        print(f"  saved to {out}")

def _repl():
    print("Music REPL — type notes. Commands:")
    print("  /play  /wave  /show  /save fn  /clear  /tempo  /inst  /quit")
    print()
    song = Song(tempo=120)
    tr = Track('default','sine')
    song.add(tr)
    while True:
        try: line = input('> ').strip()
        except (EOFError,KeyboardInterrupt): print(); break
        if not line: continue
        if line.startswith('/'):
            c = line[1:].split()
            if not c: continue
            if c[0] in ('q','quit','exit'): break
            elif c[0]=='play':
                if song.total_beats()>0:
                    song.show()
                    from ._waveform import play_with_waveform
                    play_with_waveform(song.render())
                else: print("  nothing to play")
            elif c[0]=='save':
                fn = c[1] if len(c)>1 else 'out.wav'
                try: song.save(fn); print(f"  saved to {fn}")
                except: print("  nothing to save")
            elif c[0]=='show': song.show()
            elif c[0]=='clear':
                song = Song(tempo=song.tempo)
                tr = Track('default','sine'); song.add(tr)
                print("  cleared")
            elif c[0]=='tempo' and len(c)>1:
                song.tempo = float(c[1])
                print(f"  tempo = {song.tempo}")
            elif c[0]=='inst' and len(c)>1:
                tr.inst = c[1]
                if len(c)>2: tr.vol = clamp(float(c[2]))
                print(f"  instrument = {tr.inst} vol={tr.vol}")
            elif c[0]=='midi' and len(c)>1:
                try: song.to_midi(c[1]); print(f"  midi saved to {c[1]}")
                except Exception as e: print(f"  error: {e}")
            else: print("  /play /show /save /clear /tempo /inst /midi /quit")
        elif line.startswith('tempo'):
            song.tempo = float(line.split(':',1)[-1].strip().split()[0])
        elif line.startswith('inst:'):
            p = line[5:].strip().split()
            tr.inst = p[0]
            if len(p)>1: tr.vol = clamp(float(p[1]))
        elif line.startswith('--'):
            inner = line.strip('- ')
            if ':' in inner:
                parts = inner.split(':',1)
                nm = parts[0].strip(); rest = parts[1].strip().split()
            else: nm = inner; rest = []
            i = rest[0] if rest else 'sine'
            v = float(rest[1]) if len(rest)>1 else 0.5
            p = float(rest[2]) if len(rest)>2 else 0.0
            tr = Track(nm, i, v, p); song.add(tr)
        else:
            try:
                pp = _preprocess_voltas(line)
                tr.line(pp)
            except Exception as e: print(f"  error: {e}")
    print("Bye!")

def _import_midi(path, out=None):
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
        do_wave = '--wave' in sys.argv
        if do_wave:
            from ._waveform import play_with_waveform
            play_with_waveform(s.render())
        else:
            s.play()
    return 0

def main():
    args = sys.argv[1:]
    if not args:
        print("music — program your own music")
        print()
        print("  python3 -m music song.music       play a song")
        print("  python3 -m music --midi S MIDI     export to MIDI")
        print("  python3 -m music --export F        save to WAV")
        print("  python3 -m music --repl             interactive mode")
        print("  python3 -m music --import-midi M    import & play MIDI")
        print("  python3 -m music --import-midi M O  import MIDI -> .music")
        print()
        return
    if args[0]=='--repl': _repl(); return
    if args[0]=='--midi' and len(args)>2:
        p = Path(args[1])
        if p.exists():
            s = load(str(p)); s.to_midi(args[2])
            print(f"  MIDI saved to {args[2]}"); return
        print(f"not found: {args[1]}"); return
    if args[0]=='--export' and len(args)>1:
        out = args[2] if len(args)>2 else 'output.wav'
        _export(args[1], out); return
    if args[0] == '--import-midi' and len(args) > 1:
        out = args[2] if len(args) > 2 else None
        _import_midi(args[1], out); return
    name = args[0]
    p = Path(name)
    if p.suffix in ('.mid', '.midi'):
        _import_midi(name); return
    if p.suffix=='.music' or p.exists():
        _play_file(name)
    else: print(f"not found: {name}")

if __name__=='__main__': main()
