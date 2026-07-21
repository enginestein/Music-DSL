import sys
from pathlib import Path
from .parser import load
from .models import Song

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
    if not p.exists():
        print(f"not found: {p}")
        return 1
    out_p = Path(out)
    s = load(str(p)); s.show(); s.save(str(out_p))
    if not out_p.exists() or out_p.stat().st_size == 44:
        print(f"  warning: {out} appears to be empty (no audio data)")
    print(f"  saved to {out}")

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
        print("  python3 -m music --import-midi M    import & play MIDI")
        print("  python3 -m music --import-midi M O  import MIDI -> .music")
        print()
        return
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
