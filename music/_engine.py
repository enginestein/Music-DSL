import math
import numpy as np
import wave, threading, tempfile, subprocess
from pathlib import Path

from ._constants import SAMPLE_RATE, CHANNELS, BITS, MAX_AMP, _SD, _PA, _SF

if _SD:
    import sounddevice as sd
if _PA:
    import pyaudio
if _SF:
    import soundfile as sf

try:
    from scipy.signal import lfilter as _scipy_lfilter
    _HAS_SCIPY = True
except ImportError:
    _HAS_SCIPY = False

def _reverb(signal, mix=0.0, decay=0.4):
    if mix <= 0: return signal
    delay = int(0.04 * SAMPLE_RATE)
    if _HAS_SCIPY:
        b = np.zeros(delay + 1); b[0] = 1.0
        a = np.zeros(delay + 1); a[0] = 1.0; a[delay] = -decay
        wet = _scipy_lfilter(b, a, signal)
        return signal * (1 - mix) + wet * mix
    out = signal.copy()
    buf = np.zeros(delay)
    for i in range(len(signal)):
        s = signal[i] + buf[-1]*decay
        buf[1:] = buf[:-1]
        buf[0] = s
        out[i] = signal[i]*(1-mix) + buf[-1]*mix
    return out

def _delay(signal, mix=0.0, time=0.3, fb=0.3):
    if mix <= 0: return signal
    d = int(time * SAMPLE_RATE)
    if d >= len(signal): return signal
    if _HAS_SCIPY:
        b = np.zeros(d + 1); b[0] = 1.0
        a = np.zeros(d + 1); a[0] = 1.0; a[d] = -fb
        wet = _scipy_lfilter(b, a, signal)
        peak = np.max(np.abs(wet))
        if peak > 1: wet /= peak * 1.1
        return signal * (1 - mix) + wet * mix
    out = signal.copy()
    for i in range(d, len(signal)):
        out[i] += fb * out[i-d]
    peak = np.max(np.abs(out))
    if peak > 1: out /= peak * 1.1
    out = signal*(1-mix) + out*mix
    return out

def _play(mix, wait=True):
    a = np.clip(mix*MAX_AMP*0.95, -MAX_AMP, MAX_AMP).astype(np.int16)
    if _SD:
        sd.play(a, SAMPLE_RATE)
        if wait: sd.wait()
        return
    if _PA:
        def r():
            try:
                p = pyaudio.PyAudio()
                s = p.open(format=pyaudio.paInt16, channels=CHANNELS,
                           rate=SAMPLE_RATE, output=True)
                pos = 0; bs = 4096
                while pos < len(a):
                    c = min(bs, len(a)-pos)
                    s.write(a[pos:pos+c].tobytes()); pos += c
                s.stop_stream(); s.close(); p.terminate()
            except Exception:
                pass  # PyAudio may be incompatible (PY_SSIZE_T_CLEAN on Py3.10+)
        if wait: r()
        else: threading.Thread(target=r,daemon=True).start()
        return
    tmp = tempfile.mktemp(suffix='.wav')
    _save(mix, tmp)
    for c in ('pw-play','paplay','aplay'):
        if subprocess.run(['which',c],capture_output=True).returncode==0:
            subprocess.run([c,tmp]); break
    if Path(tmp).exists(): Path(tmp).unlink()

def _compress(signal, thresh=0.5, ratio=4.0, attack=0.008, release=0.12):
    """Simple feed-forward compressor with smoothed gain reduction.

    The envelope is tracked on ~1.5ms blocks (fast in pure NumPy), then the
    gain curve is smoothed with separate attack/release time constants.
    """
    if thresh <= 0 or ratio <= 1: return signal
    mono = np.max(np.abs(signal), axis=1) if signal.ndim > 1 else np.abs(signal)
    BLOCK = 64
    nb = len(mono) // BLOCK
    if nb == 0: return signal
    peaks = mono[:nb*BLOCK].reshape(nb, BLOCK).max(axis=1)
    over = np.maximum(peaks, 1e-9) / thresh
    target = np.where(over > 1.0, over ** (1.0/ratio - 1.0), 1.0)
    # smooth on blocks: two one-pole passes (fast attack, slow release),
    # take the min -> tracks down fast, recovers slowly
    a_att = math.exp(-BLOCK/(attack*SAMPLE_RATE))
    a_rel = math.exp(-BLOCK/(release*SAMPLE_RATE))
    def _pole(a):
        g = np.empty(nb); prev = 1.0
        for i in range(nb):
            prev = a*prev + (1-a)*target[i]; g[i] = prev
        return g
    g = np.minimum(_pole(a_att), _pole(a_rel))
    # upsample gain to full length (held per block; linear-ish via repeat)
    g_full = np.repeat(g, BLOCK)
    tail = np.full(len(mono) - nb*BLOCK, g[-1])
    g_full = np.concatenate([g_full, tail])
    if signal.ndim > 1: g_full = g_full[:, None]
    return signal * g_full

def _save(mix, fn):
    a = np.clip(mix*MAX_AMP*0.95, -MAX_AMP, MAX_AMP).astype(np.int16)
    f = str(fn)
    ext = Path(f).suffix.lower()
    if ext == '.wav':
        with wave.open(f,'w') as w:
            w.setnchannels(CHANNELS); w.setsampwidth(BITS//8)
            w.setframerate(SAMPLE_RATE); w.writeframes(a.tobytes())
        return
    if _SF:
        sf.write(f, mix, SAMPLE_RATE)
        return
    # no soundfile: compressed formats go through ffmpeg with a temp WAV
    import shutil, subprocess, tempfile
    if ext in ('.mp3', '.ogg', '.flac', '.m4a', '.opus') and shutil.which('ffmpeg'):
        tmp = tempfile.mktemp(suffix='.wav')
        _save(mix, tmp)
        try:
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-i', tmp,
                            f], check=True)
        finally:
            if Path(tmp).exists(): Path(tmp).unlink()
        return
    if ext in ('.mp3', '.ogg', '.flac', '.m4a', '.opus'):
        raise RuntimeError(f"can't write {ext} without soundfile or ffmpeg "
                           f"(pip install soundfile, or install ffmpeg)")
    raise RuntimeError(f"can't save {f}")
