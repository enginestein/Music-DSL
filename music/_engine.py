import numpy as np
import wave, threading, tempfile, subprocess
from pathlib import Path

from ._constants import SAMPLE_RATE, CHANNELS, BITS, MAX_AMP, _SD, _PA, _SF

if _SD:
    import sounddevice as sd
if _PA:
    import pyaudio

def _reverb(signal, mix=0.0, decay=0.4):
    if mix <= 0: return signal
    delay = int(0.04 * SAMPLE_RATE)
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

def _save(mix, fn):
    a = np.clip(mix*MAX_AMP*0.95, -MAX_AMP, MAX_AMP).astype(np.int16)
    f = str(fn)
    if f.lower().endswith('.wav'):
        with wave.open(f,'w') as w:
            w.setnchannels(CHANNELS); w.setsampwidth(BITS//8)
            w.setframerate(SAMPLE_RATE); w.writeframes(a.tobytes())
    elif _SF: sf.write(f, mix, SAMPLE_RATE)
    else: raise RuntimeError(f"can't save {f}")
