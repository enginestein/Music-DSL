import numpy as np
import math
from ._constants import SAMPLE_RATE

_INSTS = {}
_INST_ADSR = {}

def inst(name):
    def w(fn): _INSTS[name] = fn; return fn
    return w


# ---------------------------------------------------------------------------
# Anti-aliasing
# ---------------------------------------------------------------------------

def _polyblep(t, dt):
    """Vectorized polyBLEP for smoothing waveform discontinuities."""
    out = np.zeros_like(t)
    mask_lo = t < dt
    if np.any(mask_lo):
        t_n = t[mask_lo] / dt
        out[mask_lo] = t_n + t_n - t_n * t_n - 1.0
    mask_hi = t > (1.0 - dt)
    if np.any(mask_hi):
        t_n = (t[mask_hi] - 1.0) / dt
        out[mask_hi] = t_n * t_n + t_n + t_n + 1.0
    return out


# ---------------------------------------------------------------------------
# Simple one-pole filters (for percussion noise shaping)
# ---------------------------------------------------------------------------

def _hpf(x, fc):
    a = math.exp(-2.0 * math.pi * fc / SAMPLE_RATE)
    y = np.empty_like(x)
    y[0] = 0.0
    for i in range(1, len(x)):
        y[i] = a * (y[i - 1] + x[i] - x[i - 1])
    return y

def _lpf(x, fc):
    a = math.exp(-2.0 * math.pi * fc / SAMPLE_RATE)
    y = np.empty_like(x)
    y[0] = (1.0 - a) * x[0]
    for i in range(1, len(x)):
        y[i] = a * y[i - 1] + (1.0 - a) * x[i]
    return y


# ---------------------------------------------------------------------------
# Karplus-Strong plucked-string synthesis
# ---------------------------------------------------------------------------

def _ks(f, n, sr=SAMPLE_RATE, brightness=0.5):
    delay = sr / max(f, 1.0)
    if delay < 2:
        delay = 2.0
    buf_len = int(delay) + 1
    buf = np.random.uniform(-1.0, 1.0, buf_len)
    out = np.empty(n)
    alpha = max(0.0, min(1.0, brightness))
    for i in range(n):
        idx = i % buf_len
        out[i] = buf[idx]
        buf[idx] = alpha * buf[idx] + (1.0 - alpha) * buf[(idx + 1) % buf_len]
    return out


# ===================================================================
#  BASIC WAVEFORMS  (with polyBLEP anti-aliasing on discontinuous ones)
# ===================================================================

@inst('sine')
def _sine(t, f):
    return np.sin(2.0 * np.pi * f * t)

@inst('square')
def _square(t, f):
    ph = (f * t) % 1.0
    dt = f / SAMPLE_RATE
    sig = np.where(ph < 0.5, 1.0, -1.0)
    sig += _polyblep(ph, dt)
    sig -= _polyblep((ph + 0.5) % 1.0, dt)
    return sig

@inst('saw')
@inst('sawtooth')
def _saw(t, f):
    ph = (f * t) % 1.0
    dt = f / SAMPLE_RATE
    return 2.0 * ph - 1.0 - _polyblep(ph, dt)

@inst('tri')
@inst('triangle')
def _tri(t, f):
    return 2.0 * np.abs(2.0 * (f * t - np.floor(f * t + 0.5))) - 1.0

@inst('noise')
def _noise(t, f):
    return np.random.uniform(-1.0, 1.0, len(t))


# ===================================================================
#  ORGAN
# ===================================================================

@inst('organ')
def _organ(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.80 * np.sin(2*np.pi*f*2*t)
         + 0.50 * np.sin(2*np.pi*f*3*t)
         + 0.60 * np.sin(2*np.pi*f*4*t)
         + 0.30 * np.sin(2*np.pi*f*6*t)
         + 0.40 * np.sin(2*np.pi*f*8*t))
    leslie = 1.0 + 0.04 * np.sin(2*np.pi*5.5*t)
    return s * leslie


# ===================================================================
#  BELL  (inharmonic metal resonances)
# ===================================================================

@inst('bell')
def _bell(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-2*t)
         + 0.60 * np.sin(2*np.pi*f*2.40*t) * np.exp(-3*t)
         + 0.30 * np.sin(2*np.pi*f*4.60*t) * np.exp(-5*t)
         + 0.15 * np.sin(2*np.pi*f*6.80*t) * np.exp(-8*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s


# ===================================================================
#  PLUCK  (percussive noise burst)
# ===================================================================

@inst('pluck')
def _pluck(t, f):
    return np.random.uniform(-1, 1, len(t)) * np.exp(-10 * t)


# ===================================================================
#  PIANO  (rich harmonics with inharmonicity)
# ===================================================================

@inst('piano')
def _piano(t, f):
    B = 0.0005
    s = np.zeros_like(t)
    for h in range(1, 8):
        fh = f * h * math.sqrt(1.0 + B * h * h)
        amp = 1.0 / (h ** 0.8)
        decay = np.exp(-t * (0.5 + 0.3 * h))
        s += amp * np.sin(2.0 * np.pi * fh * t) * decay
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s


# ===================================================================
#  GUITAR / NYLON  (Karplus-Strong)
# ===================================================================

def _guitar_core(t, f, brightness=0.55):
    n = len(t)
    sig = _ks(f, n, brightness=brightness)
    env = np.exp(-2.0 * t)
    return sig * env

@inst('guitar')
def _guitar(t, f):
    return _guitar_core(t, f, 0.55)

@inst('nylon')
def _nylon(t, f):
    return _guitar_core(t, f, 0.40)


# ===================================================================
#  BASS  (sub-oscillator + warmth saturation)
# ===================================================================

@inst('bass')
def _bass(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.50 * np.sin(2*np.pi*f*0.5*t)
         + 0.20 * np.sin(2*np.pi*f*2*t)
         + 0.10 * np.sin(2*np.pi*f*3*t))
    s = np.tanh(s * 1.5) / np.tanh(1.5)
    return s


# ===================================================================
#  STRINGS / PAD  (detuned ensemble chorus)
# ===================================================================

@inst('strings')
@inst('pad')
def _strings(t, f):
    s = np.zeros_like(t)
    for v in (-1, 0, 1):
        d = 1.0 + v * 0.003
        s += (np.sin(2*np.pi*f*d*t) * 0.40
              + 0.20 * np.sin(2*np.pi*f*2*d*t)
              + 0.10 * np.sin(2*np.pi*f*3*d*t))
    env = np.minimum(1.0, t / 0.10)
    return s * env


# ===================================================================
#  FLUTE  (pure tone + breath noise)
# ===================================================================

@inst('flute')
def _flute(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.15 * np.sin(2*np.pi*f*2*t)
         + 0.05 * np.sin(2*np.pi*f*3*t))
    breath = np.random.uniform(-1, 1, len(t)) * 0.08
    env = np.minimum(1.0, t / 0.03)
    return (s + breath) * env


# ===================================================================
#  BRASS  (bright harmonics with attack blip)
# ===================================================================

@inst('brass')
def _brass(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.60 * np.sin(2*np.pi*f*2*t)
         + 0.40 * np.sin(2*np.pi*f*3*t)
         + 0.25 * np.sin(2*np.pi*f*4*t)
         + 0.15 * np.sin(2*np.pi*f*5*t)
         + 0.08 * np.sin(2*np.pi*f*6*t))
    blip = 0.30 * np.sin(2*np.pi*f*6*t) * np.exp(-20*t)
    env = np.minimum(1.0, t / 0.015)
    return (s + blip) * env


# ===================================================================
#  REED / SAX  (nasal odd-harmonic emphasis + breath)
# ===================================================================

@inst('reed')
@inst('sax')
def _reed(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.70 * np.sin(2*np.pi*f*2*t)
         + 0.60 * np.sin(2*np.pi*f*3*t)
         + 0.30 * np.sin(2*np.pi*f*4*t)
         + 0.40 * np.sin(2*np.pi*f*5*t)
         + 0.15 * np.sin(2*np.pi*f*6*t)
         + 0.20 * np.sin(2*np.pi*f*7*t))
    breath = np.random.uniform(-1, 1, len(t)) * 0.05
    env = np.minimum(1.0, t / 0.02)
    return (s + breath) * env


# ===================================================================
#  NEW MELODIC INSTRUMENTS
# ===================================================================

# --- Harp (Karplus-Strong, longer decay) ---
@inst('harp')
def _harp(t, f):
    n = len(t)
    sig = _ks(f, n, brightness=0.50)
    env = np.exp(-1.5 * t)
    return sig * env

# --- Banjo (bright, twangy KS) ---
@inst('banjo')
def _banjo(t, f):
    n = len(t)
    sig = _ks(f, n, brightness=0.70)
    env = np.exp(-3.0 * t)
    return sig * env

# --- Harpsichord (very bright KS) ---
@inst('harpsichord')
def _harpsichord(t, f):
    n = len(t)
    sig = _ks(f, n, brightness=0.75)
    env = np.exp(-3.0 * t)
    return sig * env

# --- Accordion (free-reed + wet tremolo) ---
@inst('accordion')
def _accordion(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.80 * np.sin(2*np.pi*f*2*t)
         + 0.60 * np.sin(2*np.pi*f*3*t)
         + 0.50 * np.sin(2*np.pi*f*4*t)
         + 0.30 * np.sin(2*np.pi*f*5*t)
         + 0.20 * np.sin(2*np.pi*f*6*t))
    trem = 1.0 + 0.08 * np.sin(2*np.pi*5.0*t)
    return s * trem

# --- Clavinet (funky bright keyboard) ---
@inst('clavinet')
def _clavinet(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.70 * np.sin(2*np.pi*f*2*t)
         + 0.50 * np.sin(2*np.pi*f*3*t)
         + 0.40 * np.sin(2*np.pi*f*4*t)
         + 0.30 * np.sin(2*np.pi*f*5*t))
    env = np.exp(-3.0 * t)
    return s * env

# --- Celesta (soft bell-keyboard, slightly inharmonic) ---
@inst('celesta')
def _celesta(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-2*t)
         + 0.60 * np.sin(2*np.pi*f*2.00*t) * np.exp(-3*t)
         + 0.30 * np.sin(2*np.pi*f*3.01*t) * np.exp(-4*t)
         + 0.15 * np.sin(2*np.pi*f*4.98*t) * np.exp(-5*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s

# --- Marimba (wooden bar, short inharmonic) ---
@inst('marimba')
def _marimba(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-6*t)
         + 0.50 * np.sin(2*np.pi*f*4.00*t) * np.exp(-10*t)
         + 0.20 * np.sin(2*np.pi*f*10.0*t) * np.exp(-18*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s

# --- Xylophone (brighter, shorter than marimba) ---
@inst('xylophone')
def _xylophone(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-8*t)
         + 0.60 * np.sin(2*np.pi*f*4.00*t) * np.exp(-14*t)
         + 0.35 * np.sin(2*np.pi*f*10.0*t) * np.exp(-22*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s

# --- Vibraphone (metal bar + motor tremolo) ---
@inst('vibraphone')
def _vibraphone(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.50 * np.sin(2*np.pi*f*2.76*t)
         + 0.30 * np.sin(2*np.pi*f*5.40*t))
    env = np.exp(-1.5 * t)
    trem = 1.0 + 0.50 * np.sin(2*np.pi*5.5*t)
    return s * env * trem

# --- Steel Drums (inharmonic metallic pan) ---
@inst('steel_drums')
def _steel_drums(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-2*t)
         + 0.70 * np.sin(2*np.pi*f*2.02*t) * np.exp(-2.5*t)
         + 0.50 * np.sin(2*np.pi*f*3.01*t) * np.exp(-3*t)
         + 0.30 * np.sin(2*np.pi*f*4.20*t) * np.exp(-4*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s

# --- Kalimba (thumb piano, soft metallic) ---
@inst('kalimba')
def _kalimba(t, f):
    s = (np.sin(2*np.pi*f*t) * np.exp(-3*t)
         + 0.50 * np.sin(2*np.pi*f*2.76*t) * np.exp(-4*t)
         + 0.25 * np.sin(2*np.pi*f*5.40*t) * np.exp(-6*t))
    mx = np.max(np.abs(s))
    return s / mx if mx > 0 else s

# --- Sitar (buzzing jawari + sympathetic resonance) ---
@inst('sitar')
def _sitar(t, f):
    s = (np.sin(2*np.pi*f*t)
         + 0.70 * np.sin(2*np.pi*f*2*t)
         + 0.50 * np.sin(2*np.pi*f*3*t)
         + 0.30 * np.sin(2*np.pi*f*4*t))
    buzz = np.random.uniform(-1, 1, len(t)) * np.abs(s) * 0.20
    s += buzz
    env = np.exp(-1.5*t) + 0.30 * np.exp(-0.5*t)
    return s * env

# --- Choir (formant-shaped vocal ensemble) ---
@inst('choir')
def _choir(t, f):
    formants = [(700, 130), (1200, 200), (2500, 250)]
    s = np.zeros_like(t)
    rng = np.random.RandomState(int(f * 1000) % (2**31))
    for h in range(1, 10):
        hf = f * h
        amp = sum(math.exp(-((hf - fc) / bw) ** 2) for fc, bw in formants) / len(formants)
        detune = 1.0 + rng.uniform(-0.003, 0.003)
        s += amp * np.sin(2.0 * np.pi * f * h * detune * t)
    env = np.minimum(1.0, t / 0.15)
    mx = np.max(np.abs(s * env))
    return s * env / mx if mx > 0 else s * env


# ===================================================================
#  PERCUSSION
# ===================================================================

@inst('kick')
def _kick(t, f):
    n = len(t); sr = SAMPLE_RATE
    lo = max(f, 30.0)
    sweep_len = min(n, int(0.05 * sr))
    sw_t = np.arange(sweep_len, dtype=np.float64) / sr
    f_inst = lo * (1.0 + 3.0 * np.exp(-40.0 * sw_t))
    phase = np.cumsum(f_inst / sr) * 2.0 * np.pi
    tone = np.sin(phase)
    if n > sweep_len:
        rest = np.arange(n - sweep_len, dtype=np.float64) / sr
        tone = np.concatenate([tone, np.sin(2.0*np.pi*lo*rest)])
    env = np.exp(-4.0 * t)
    click_len = min(n, int(0.005 * sr))
    click = np.zeros(n)
    c = np.random.uniform(-0.5, 0.5, click_len) * np.exp(-500.0*np.arange(click_len)/sr)
    click[:click_len] = c
    return tone * 0.70 * env + click * 0.30

@inst('snare')
def _snare(t, f):
    n = len(t)
    tone_f = min(f, 300.0)
    tone = np.sin(2.0*np.pi*tone_f*t) * np.exp(-15.0*t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 1000)
    noise = _lpf(noise, 6000)
    noise *= np.exp(-10.0 * t)
    return tone * 0.40 + noise * 0.60

@inst('hihat')
def _hihat(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 6000)
    env = np.exp(-40.0 * t)
    return noise * env * 0.40

@inst('hihat_open')
def _hihat_open(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 5000)
    env = np.exp(-8.0 * t)
    return noise * env * 0.40

@inst('cymbal')
def _cymbal(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 3000)
    noise = _lpf(noise, 12000)
    env = np.exp(-3.0 * t)
    return noise * env * 0.50

@inst('ride')
def _ride(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 4000)
    ping = 0.30 * np.sin(2.0*np.pi*3500*t) * np.exp(-5.0*t)
    env = np.exp(-2.0 * t)
    return (noise * 0.70 + ping * 0.30) * env * 0.50

@inst('tom')
def _tom(t, f):
    n = len(t); sr = SAMPLE_RATE
    tf = max(min(f, 300.0), 60.0)
    sw_len = min(n, int(0.03 * sr))
    sw_t = np.arange(sw_len, dtype=np.float64) / sr
    f_inst = tf * (1.0 + 2.0 * np.exp(-30.0 * sw_t))
    phase = np.cumsum(f_inst / sr) * 2.0 * np.pi
    tone = np.sin(phase)
    if n > sw_len:
        rest = np.arange(n - sw_len, dtype=np.float64) / sr
        tone = np.concatenate([tone, np.sin(2.0*np.pi*tf*rest)])
    env = np.exp(-8.0 * t)
    click_len = min(n, int(0.01 * sr))
    click = np.zeros(n)
    c = np.random.uniform(-1, 1, click_len) * np.exp(-200.0*np.arange(click_len)/sr)
    click[:click_len] = c
    return tone * 0.70 * env + click * 0.30

@inst('clap')
def _clap(t, f):
    n = len(t); sr = SAMPLE_RATE
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 1000)
    noise = _lpf(noise, 4000)
    env = np.zeros(n)
    spacing = int(0.007 * sr)
    for i in range(5):
        start = int(i * spacing * 0.70)
        bl = min(n - start, int(0.025 * sr))
        if bl > 0:
            env[start:start+bl] += np.exp(-30.0 * np.arange(bl) / sr)
    return noise * env * 0.50

@inst('rimshot')
def _rimshot(t, f):
    n = len(t); sr = SAMPLE_RATE
    click_len = min(n, int(0.003 * sr))
    click = np.zeros(n)
    click[:click_len] = np.random.uniform(-1, 1, click_len) * np.exp(-500.0*np.arange(click_len)/sr)
    tone = np.sin(2.0*np.pi*800*t) * np.exp(-50.0*t)
    return click * 0.60 + tone * 0.40

@inst('cowbell')
def _cowbell(t, f):
    s = np.sin(2.0*np.pi*560*t) + 0.70 * np.sin(2.0*np.pi*845*t)
    env = np.exp(-15.0 * t)
    return s * env * 0.50

@inst('tambourine')
def _tambourine(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 2000)
    jingle = 0.30 * np.sin(2.0*np.pi*8000*t) * np.exp(-20.0*t)
    env = np.exp(-10.0 * t)
    return (noise + jingle) * env * 0.50

@inst('maracas')
def _maracas(t, f):
    n = len(t)
    noise = np.random.uniform(-1, 1, n)
    noise = _hpf(noise, 3000)
    env = np.exp(-30.0 * t)
    return noise * env * 0.50


# ===================================================================
#  DEFAULT ADSR ENVELOPES  (per instrument)
# ===================================================================

_INST_ADSR = {
    'sine':       {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'square':     {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'saw':        {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'sawtooth':   {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'tri':        {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'triangle':   {'a': 0.010, 'd': 0.05, 's': 0.80, 'r': 0.10},
    'noise':      {'a': 0.005, 'd': 0.02, 's': 0.60, 'r': 0.05},
    'organ':      {'a': 0.010, 'd': 0.02, 's': 1.00, 'r': 0.05},
    'bell':       {'a': 0.005, 'd': 0.80, 's': 0.30, 'r': 0.50},
    'pluck':      {'a': 0.005, 'd': 0.15, 's': 0.30, 'r': 0.10},
    'piano':      {'a': 0.005, 'd': 0.30, 's': 0.60, 'r': 0.30},
    'guitar':     {'a': 0.005, 'd': 0.20, 's': 0.50, 'r': 0.20},
    'nylon':      {'a': 0.005, 'd': 0.20, 's': 0.50, 'r': 0.20},
    'bass':       {'a': 0.005, 'd': 0.10, 's': 0.70, 'r': 0.10},
    'strings':    {'a': 0.150, 'd': 0.30, 's': 0.85, 'r': 0.40},
    'pad':        {'a': 0.300, 'd': 0.50, 's': 0.80, 'r': 0.50},
    'flute':      {'a': 0.030, 'd': 0.10, 's': 0.70, 'r': 0.15},
    'brass':      {'a': 0.020, 'd': 0.15, 's': 0.80, 'r': 0.20},
    'reed':       {'a': 0.015, 'd': 0.10, 's': 0.75, 'r': 0.15},
    'sax':        {'a': 0.015, 'd': 0.10, 's': 0.75, 'r': 0.15},
    'harp':       {'a': 0.005, 'd': 0.30, 's': 0.40, 'r': 0.30},
    'banjo':      {'a': 0.003, 'd': 0.10, 's': 0.30, 'r': 0.10},
    'harpsichord':{'a': 0.005, 'd': 0.15, 's': 0.30, 'r': 0.15},
    'accordion':  {'a': 0.020, 'd': 0.10, 's': 0.80, 'r': 0.20},
    'clavinet':   {'a': 0.005, 'd': 0.10, 's': 0.40, 'r': 0.10},
    'celesta':    {'a': 0.005, 'd': 0.50, 's': 0.30, 'r': 0.30},
    'marimba':    {'a': 0.002, 'd': 0.15, 's': 0.00, 'r': 0.05},
    'xylophone':  {'a': 0.002, 'd': 0.08, 's': 0.00, 'r': 0.03},
    'vibraphone': {'a': 0.005, 'd': 0.30, 's': 0.60, 'r': 0.30},
    'steel_drums':{'a': 0.005, 'd': 0.40, 's': 0.30, 'r': 0.30},
    'kalimba':    {'a': 0.002, 'd': 0.30, 's': 0.20, 'r': 0.20},
    'sitar':      {'a': 0.005, 'd': 0.20, 's': 0.50, 'r': 0.30},
    'choir':      {'a': 0.150, 'd': 0.30, 's': 0.80, 'r': 0.40},
    'kick':       {'a': 0.002, 'd': 0.20, 's': 0.00, 'r': 0.05},
    'snare':      {'a': 0.002, 'd': 0.15, 's': 0.00, 'r': 0.05},
    'hihat':      {'a': 0.001, 'd': 0.05, 's': 0.00, 'r': 0.02},
    'hihat_open': {'a': 0.001, 'd': 0.30, 's': 0.00, 'r': 0.05},
    'cymbal':     {'a': 0.005, 'd': 0.80, 's': 0.10, 'r': 0.30},
    'ride':       {'a': 0.005, 'd': 0.50, 's': 0.20, 'r': 0.30},
    'tom':        {'a': 0.002, 'd': 0.20, 's': 0.00, 'r': 0.05},
    'clap':       {'a': 0.002, 'd': 0.10, 's': 0.00, 'r': 0.10},
    'rimshot':    {'a': 0.001, 'd': 0.05, 's': 0.00, 'r': 0.02},
    'cowbell':    {'a': 0.002, 'd': 0.10, 's': 0.00, 'r': 0.05},
    'tambourine': {'a': 0.002, 'd': 0.10, 's': 0.00, 'r': 0.05},
    'maracas':    {'a': 0.001, 'd': 0.05, 's': 0.00, 'r': 0.02},
}
