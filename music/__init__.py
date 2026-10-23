__version__ = '3.0.0'

from .models import Note, Track, Song
from .parser import load
from .cli import main
from ._midi import midi_to_song, song_to_text

def lint(path):
    """Check a .music file for issues. Returns (errors, warnings) lists."""
    import warnings as _w
    from pathlib import Path as _P
    errs, warns = [], []
    p = _P(str(path))
    if not p.exists():
        return [f"not found: {p}"], []
    with _w.catch_warnings(record=True) as caught:
        _w.simplefilter('always')
        try:
            s = load(str(p))
        except Exception as e:
            errs.append(str(e)); s = None
        for c in caught:
            warns.append(str(c.message))
    if s is not None:
        beats = [t.beats() for t in s.tracks]
        mx = max(beats, default=0)
        for t, b in zip(s.tracks, beats):
            if mx - b > 0.01 and len(s.tracks) > 1:
                warns.append(f"track '{t.name}' is {mx-b:.2f} beats shorter than the longest track")
        if s.arrange:
            used = {n for n, _ in s.arrange}
            unused = sorted(s.defined_sections - used)
            if unused:
                warns.append(f"sections defined but never used in arrange: {', '.join(unused)}")
    return errs, warns
