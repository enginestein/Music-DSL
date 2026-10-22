"""Tests for the Music DSL.

Run with pytest, or standalone:  python3 tests/test_dsl.py
"""
import os, sys, math, warnings, subprocess, shutil, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from music.parser import load, _notes_beats
from music.models import Song, Track, Note
from music import lint, __version__

SAMPLES = Path(__file__).resolve().parent.parent / 'music' / 'samples'

def _pitches(tr):
    return [n.pitch for n in tr.notes if not n.rest and not n.pitch.startswith('$')]

def _render(src, tempo=None):
    s = load(src)
    if tempo: s.tempo = tempo
    return s, s.render()

# ---------------------------------------------------------------- parser basics

def test_notes_and_durations():
    s = load("-- t: piano 0.5 --\nC4 q D4 e E4 s F4 h\n")
    tr = s.tracks[0]
    assert [n.duration for n in tr.notes] == [1.0, 0.5, 0.25, 2.0]
    assert _pitches(tr) == ['C4', 'D4', 'E4', 'F4']

def test_rests_and_dotted():
    s = load("-- t: piano 0.5 --\nC4 q. R e D4 h.\n")
    durs = [n.duration for n in s.tracks[0].notes]
    assert durs == [1.5, 0.5, 3.0]

def test_chords_count_once_in_beats():
    s = load("-- t: piano 0.5 --\n(C4 E4 G4) q R q C5 q R q\n")
    assert abs(s.tracks[0].beats() - 4.0) < 1e-6

def test_chord_then_rest_regression():
    # chords followed by rests used to lose the chord duration
    s = load("-- t: piano 0.5 --\n(C4 E4 G4) w R h\n")
    assert abs(s.tracks[0].beats() - 6.0) < 1e-6

def test_ties_and_accents():
    s = load("-- t: piano 0.5 --\nC4 w ~ C4 q  >D4 q ^E4 q\n")
    notes = s.tracks[0].notes
    assert notes[0].duration == 4.0 and notes[1].duration == 1.0  # tied merged
    assert any(n.accent for n in notes)

def test_key_signature():
    s = load("key: F\n-- t: piano 0.5 --\nB4 q\n")
    assert _pitches(s.tracks[0]) == ['Bb4']

def test_dynamics_and_velocity():
    # bare dynamic applies to subsequent notes — including on later lines
    s = load("-- t: piano 0.5 --\nfff\nC4 q D4 q\n")
    vs = [n.velocity for n in s.tracks[0].notes]
    assert all(abs(v - 0.96) < 1e-6 for v in vs), vs
    # @N after a note sets that note's velocity
    s = load("-- t: piano 0.5 --\nC4 q @0.31 D4 q\n")
    vs = [n.velocity for n in s.tracks[0].notes]
    assert abs(vs[0] - 0.31) < 1e-6 and abs(vs[1] - 0.8) < 1e-6, vs
    s = load("-- t: piano 0.5 --\np\nC4 q\n")
    assert s.tracks[0].notes[0].velocity < 0.5

# ---------------------------------------------------------------- structure

def test_repeats():
    s = load("-- t: piano 0.5 --\n[ C4 q D4 q ] x3\n")
    assert len(_pitches(s.tracks[0])) == 6

def test_multiline_repeat():
    s = load("-- t: piano 0.5 --\n[\nC4 q\nD4 q\nE4 q\n] x2\n")
    assert len(_pitches(s.tracks[0])) == 6

def test_voltas():
    s = load("-- t: piano 0.5 --\n[1 C4 q ]\n[2 D4 q ]\n")
    assert _pitches(s.tracks[0]) == ['C4', 'D4']

def test_jump_and_done():
    # @jump repeats from the label; @done cuts everything after it
    s = load("-- t: piano 0.5 --\n[chorus] C5 q D5 q\n@jump chorus\n@done\nE5 q\n")
    assert _pitches(s.tracks[0]) == ['C5', 'D5', 'C5', 'D5']

def test_patterns_and_call():
    s = load("-- t: piano 0.5 --\n@pattern ost = C4 e D4 e E4 e\n@ost\n@ost\n")
    assert len(_pitches(s.tracks[0])) == 6

def test_steps():
    s = load("-- t: piano 0.5 --\nq @steps 4 { C4 D4 E4 F4 }\n")
    assert len(_pitches(s.tracks[0])) == 4

# ---------------------------------------------------------------- P0 fixes

def test_humanize_renders():
    s = load("-- t: piano 0.5 humanize:timing:0.02 humanize:vel:0.2 --\nC4 q E4 q\n")
    s.render()  # used to crash with AttributeError

def test_arp_directions():
    assert _pitches(load("-- t: piano 0.5 --\n@arp up C q\n").tracks[0]) == ['C4', 'E4', 'G4']
    assert _pitches(load("-- t: piano 0.5 --\n@arp down Cmaj7 e\n").tracks[0]) == ['B4', 'G4', 'E4', 'C4']
    assert _pitches(load("-- t: piano 0.5 --\n@arp ud C q\n").tracks[0]) == ['C4', 'E4', 'G4', 'E4']

def test_arp_previous_chord():
    s = load("-- t: piano 0.5 --\n(C4 E4 G4) q\n@arp up\n")
    # previous chord is re-emitted as sequential notes
    assert len(_pitches(s.tracks[0])) >= 3

# ---------------------------------------------------------------- new features

def test_degrees_major_and_minor():
    s = load("key: C\n-- t: piano 0.5 --\ndegrees:on\n1 q 4 q 5 q\n")
    assert _pitches(s.tracks[0]) == ['C4', 'F4', 'G4']
    s = load("key: Am\n-- t: piano 0.5 --\ndegrees:on\n1 q b7 h\n")
    assert _pitches(s.tracks[0])[0] == 'A4'

def test_degree_chords():
    s = load("key: C\n-- t: piano 0.5 --\ndegrees:on\n6m q\n")
    assert _pitches(s.tracks[0]) == ['A4', 'C5', 'E5']

def test_degrees_in_track_header():
    s = load("-- t: piano 0.5 degrees:on --\nkey: C\n1 q 4 q\n")
    assert _pitches(s.tracks[0]) == ['C4', 'F4']

def test_sharp_degrees_are_not_comments():
    s = load("key: C\n-- t: piano 0.5 --\ndegrees:on\n#4 q\n1 q\n")
    assert _pitches(s.tracks[0]) == ['F#4', 'C4']
    s = load("key: C\n-- t: piano 0.5 --\ndegrees:on\n1 q #4 q\n")
    assert _pitches(s.tracks[0]) == ['C4', 'F#4']

def test_flat_degree_spelling():
    s = load("key: C\n-- t: piano 0.5 --\ndegrees:on\nb7 q\n")
    assert _pitches(s.tracks[0]) == ['Bb4']
    s = load("key: F\n-- t: piano 0.5 --\ndegrees:on\n4 q\n")
    assert _pitches(s.tracks[0]) == ['Bb4']

def test_comments_still_work():
    s = load("# leading comment\n-- t: piano 0.5 --\nC4 q # trailing\nD4 q\n")
    assert _pitches(s.tracks[0]) == ['C4', 'D4']

def test_progression_and_gen():
    s = load("progression: Cm Ab\n-- b: bass 0.4 --\n@gen bass 8ths\n"
             "-- p: pad 0.3 --\n@gen pad\n-- a: tri 0.3 --\n@gen arp up 8ths\n")
    # 2 chords = 2 bars = 8 beats each track
    for tr in s.tracks:
        assert abs(tr.beats() - 8.0) < 1e-6, tr.name

def test_gen_drums_deferred_over_arrangement():
    s = load("progression: Cm\narrange: a x4\n"
             "-- t: piano 0.4 --\n%a\nC4 q E4 q G4 q C5 q\n@gen drums four\n")
    names = {t.name for t in s.tracks}
    assert {'gen_kick', 'gen_snare', 'gen_hat'} <= names
    # drums cover the whole arranged song (4 x 4 beats = 16)
    kick = next(t for t in s.tracks if t.name == 'gen_kick')
    assert abs(kick.beats() - 16.0) < 1e-6

def test_sections_and_arrange_alignment():
    src = ("arrange: intro x2 chorus\n"
           "-- a: piano 0.5 --\n%intro\nC4 q E4 q\n%chorus\nG4 q C5 q E5 q G5 q\n"
           "-- b: bass 0.4 --\n%chorus\nC2 h G2 h\n")
    s = load(src)
    bs = [t.beats() for t in s.tracks]
    assert max(bs) - min(bs) < 1e-6          # every track aligned
    b = next(t for t in s.tracks if t.name == 'b')
    assert _pitches(b) == ['C2', 'G2']       # b rests through intro

def test_arrange_unknown_section_errors():
    try:
        load("arrange: nope\n-- t: piano 0.5 --\nC4 q\n")
        assert False, "expected ValueError"
    except ValueError as e:
        assert 'nope' in str(e)

def test_master_directive():
    s = load("master: vol 0.8 comp 0.5 4 reverb 0.2\n-- t: piano 0.5 --\nC4 q\n")
    assert s.master_vol == 0.8
    assert s.master_comp == (0.5, 4.0)
    assert s.rev == 0.2

def test_sidechain_changes_signal():
    import numpy as np
    base = ("-- kick: kick 0.7 --\nC2 q C2 q C2 q C2 q\n"
            "-- bass: saw 0.5 --\nC2 w\n")
    m1 = load(base).render()
    # both header and body syntax must engage ducking
    for variant in (base.replace("-- bass: saw 0.5 --",
                                 "-- bass: saw 0.5 sidechain:kick:0.6 --"),
                    base.replace("-- bass: saw 0.5 --\n",
                                 "-- bass: saw 0.5 --\nsidechain:kick 0.6\n")):
        s = load(variant)
        b = next(t for t in s.tracks if t.name == 'bass')
        assert b.sidechain_src == 'kick' and abs(b.sidechain_amt - 0.6) < 1e-9
        m2 = s.render()
        assert not np.allclose(m1, m2)
        # ducking only ever reduces level, never boosts
        assert np.abs(m2).max() <= np.abs(m1).max() + 1e-9

def test_drums_shorthand():
    s = load("-- hat: hihat 0.4 --\nq @drums 8 { x . x X . g x . }\n")
    hits = sum(1 for n in s.tracks[0].notes if not n.rest)
    assert hits == 5   # x . x X . g x . -> 5 hits

def test_humanize_render_audio():
    s, mix = _render("-- t: organ 0.5 humanize:timing:0.02 --\nC4 q D4 q E4 q\n")
    import numpy as np
    assert np.abs(mix).max() > 0

# ---------------------------------------------------------------- engine

def test_compressor_reduces_peak():
    from music._engine import _compress
    import numpy as np
    x = np.ones((44100, 2)) * 0.9
    y = _compress(x, 0.5, 4.0)
    assert np.abs(y).max() < 0.9

def test_render_is_normalized():
    s, mix = _render("-- t: piano 0.9 --\nC4 w\n")
    assert np_abs_max(mix) <= 1.0

def np_abs_max(m):
    import numpy as np
    return float(np.abs(m).max())

def test_save_wav(tmp_path=None):
    d = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    s = load("-- t: piano 0.5 --\nC4 q\n")
    out = d / 't.wav'
    s.save(str(out))
    assert out.exists() and out.stat().st_size > 44

def test_save_mp3_or_error():
    d = Path(tempfile.mkdtemp())
    s = load("-- t: piano 0.5 --\nC4 q\n")
    out = d / 't.mp3'
    has_ff = shutil.which('ffmpeg') is not None
    try:
        s.save(str(out))
        assert has_ff, "mp3 save succeeded without ffmpeg?"
        assert out.exists() and out.stat().st_size > 0
    except RuntimeError as e:
        assert not has_ff and 'ffmpeg' in str(e)

# ---------------------------------------------------------------- midi

def test_midi_roundtrip(tmp_path=None):
    d = Path(tmp_path) if tmp_path else Path(tempfile.mkdtemp())
    s = load("-- t: piano 0.5 --\nC4 q E4 q G4 q C5 q\n")
    mid = d / 't.mid'
    s.to_midi(str(mid))
    assert mid.exists()
    s2 = Song.from_midi(str(mid))
    assert s2.total_beats() > 0

# ---------------------------------------------------------------- lint / cli

def test_lint_ok():
    errs, warns = lint_str("-- t: piano 0.5 --\nC4 q\n")
    assert not errs and not warns

def lint_str(src):
    d = Path(tempfile.mkdtemp())
    f = d / 'x.music'
    f.write_text(src)
    return lint(f)

def test_lint_catches_errors():
    errs, _ = lint_str("-- t: piano 0.5 --\n[ C4 q\n")
    assert errs and 'unclosed' in errs[0]

def test_lint_warns_track_length():
    src = ("-- a: piano 0.5 --\nC4 q\n"
           "-- b: piano 0.5 --\nC4 q E4 q G4 q C5 q E5 q G5 q C6 q\n")
    _, warns = lint_str(src)
    assert any('shorter' in w for w in warns)

def test_cli_help():
    r = subprocess.run([sys.executable, '-m', 'music', '--help'],
                       capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent.parent))
    assert r.returncode == 0 and 'usage' in r.stdout

def test_cli_version():
    r = subprocess.run([sys.executable, '-m', 'music', '--version'],
                       capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent.parent))
    assert r.returncode == 0 and __version__ in r.stdout

def test_cli_new_and_check():
    d = Path(tempfile.mkdtemp())
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
    for style in ('synthwave', 'rock', 'jazz', 'ambient', 'hiphop', 'blank'):
        f = d / f'{style}.music'
        r = subprocess.run([sys.executable, '-m', 'music', '--new', str(f),
                            '--style', style],
                           capture_output=True, text=True, env=env,
                           cwd=str(Path(__file__).resolve().parent.parent))
        assert r.returncode == 0 and f.exists(), f"{style}: {r.stdout}{r.stderr}"
        r = subprocess.run([sys.executable, '-m', 'music', '--check', str(f)],
                           capture_output=True, text=True, env=env,
                           cwd=str(Path(__file__).resolve().parent.parent))
        assert r.returncode == 0 and 'error' not in r.stdout, f"{style}: {r.stdout}"

def test_cli_list_instruments():
    r = subprocess.run([sys.executable, '-m', 'music', '--list-instruments'],
                       capture_output=True, text=True,
                       cwd=str(Path(__file__).resolve().parent.parent))
    assert r.returncode == 0 and 'piano' in r.stdout and 'kick' in r.stdout

def test_instrument_suggestion():
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter('always')
        load("-- t: pianoa 0.5 --\nC4 q\n")
    assert any('did you mean' in str(x.message) for x in w)

# ---------------------------------------------------------------- live REPL

def test_serialize_track_roundtrip():
    from music._live import _serialize_track
    src = ("tempo: 100\n"
           "-- a: piano 0.5 0.0 reverb:0.3 --\nC4 q E4 q G4 h\n"
           "-- b: saw 0.4 -0.3 --\nkey: Am\nC2 h\n")
    s = load(src)
    text = '\n'.join(_serialize_track(t) for t in s.tracks)
    r = load(text + '\n')
    assert [t.name for t in r.tracks] == ['a', 'b']
    assert _pitches(r.tracks[0]) == ['C4', 'E4', 'G4']
    assert [n.duration for n in r.tracks[1].notes] == [2.0]
    assert abs(r.tracks[0].rev - 0.3) < 1e-9
    assert r.tracks[1].key_name == 'Am'

def test_serializer_chords_and_markers():
    from music._live import _serialize_track
    s = load("-- t: piano 0.5 --\ntempo: 90\n(C4 E4 G4) h R q C5 q\n")
    text = _serialize_track(s.tracks[0])
    r = load(text + '\n')
    t = r.tracks[0]
    assert _pitches(t) == ['C4', 'E4', 'G4', 'C5']
    assert sum(1 for n in t.notes if n.rest) == 1
    assert t.beats() == 4.0

def test_live_save_roundtrip():
    d = Path(tempfile.mkdtemp()); out = d / 'jam.music'
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parent.parent))
    script = (":track mel piano 0.5\n:degrees on\n1 q 4 q 5 q\n"
              ":track bass bass 0.4\nC2 h\n:tempo 90\n"
              f":save {out}\n:quit\n")
    r = subprocess.run([sys.executable, '-m', 'music', '--live'],
                       input=script, capture_output=True, text=True,
                       env=env, cwd=str(Path(__file__).resolve().parent.parent),
                       timeout=60)
    assert out.exists(), r.stdout + r.stderr
    s = load(str(out))
    assert [t.name for t in s.tracks] == ['mel', 'bass']
    assert _pitches(s.tracks[0]) == ['C4', 'F4', 'G4']
    assert s.tempo == 90

# ---------------------------------------------------------------- samples

def test_all_samples_load_and_render():
    if not SAMPLES.exists():
        return
    for f in sorted(SAMPLES.glob('*.music')):
        with warnings.catch_warnings(record=True):
            warnings.simplefilter('always')
            s = load(str(f))
        assert s.tracks, f"{f.name} has no tracks"
        mix = s.render()
        assert mix.shape[0] > 0

# ---------------------------------------------------------------- runner

def _run():
    import traceback
    tests = [(k, v) for k, v in sorted(globals().items())
             if k.startswith('test_') and callable(v)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS {name}")
        except Exception:
            failed += 1
            print(f"  FAIL {name}")
            traceback.print_exc()
    print(f"\n{len(tests)-failed}/{len(tests)} passed")
    return 1 if failed else 0

if __name__ == '__main__':
    sys.exit(_run())
