import numpy as np

_INSTS = {}

def inst(name):
    def w(fn): _INSTS[name] = fn; return fn
    return w

@inst('sine')
def _sine(t, f): return np.sin(2*np.pi*f*t)

@inst('square')
def _square(t, f): return np.sign(np.sin(2*np.pi*f*t))

@inst('saw')
@inst('sawtooth')
def _saw(t, f): return 2.0*(f*t-np.floor(0.5+f*t))

@inst('tri')
@inst('triangle')
def _tri(t, f): return 2.0*np.abs(2.0*(f*t-np.floor(f*t+0.5)))-1.0

@inst('noise')
def _noise(t, f): return np.random.uniform(-1,1,len(t))

@inst('organ')
def _organ(t, f):
    s = np.sin(2*np.pi*f*t)
    return s + 0.5*np.sign(s)

@inst('bass')
def _bass(t, f): return np.sin(2*np.pi*f*t) + 0.3*np.sin(4*np.pi*f*t)

@inst('bell')
def _bell(t, f): return np.sin(2*np.pi*f*t)*np.exp(-3*t)

@inst('pluck')
def _pluck(t, f): return np.random.uniform(-1,1,len(t))*np.exp(-10*t)

@inst('guitar')
@inst('nylon')
def _guitar(t, f):
    """Steel/nylon string guitar tone with harmonics."""
    s = np.sin(2*np.pi*f*t) * np.exp(-2*t)
    s += 0.5 * np.sin(2*np.pi*f*2*t) * np.exp(-4*t)
    s += 0.25 * np.sin(2*np.pi*f*3*t) * np.exp(-6*t)
    s += 0.15 * np.sin(2*np.pi*f*4*t) * np.exp(-8*t)
    s += 0.05 * np.random.uniform(-1, 1, len(t)) * np.exp(-15*t)
    return s / np.max(np.abs(s)) if np.max(np.abs(s)) > 0 else s

@inst('piano')
def _piano(t, f):
    """Piano-like with harmonics and velocity-sensitive decay."""
    s = np.sin(2*np.pi*f*t) * np.exp(-0.8*t)
    s += 0.6 * np.sin(2*np.pi*f*2*t) * np.exp(-1.5*t)
    s += 0.4 * np.sin(2*np.pi*f*3*t) * np.exp(-2.5*t)
    s += 0.2 * np.sin(2*np.pi*f*4*t) * np.exp(-4*t)
    s += 0.1 * np.sin(2*np.pi*f*5*t) * np.exp(-6*t)
    return s / np.max(np.abs(s)) if np.max(np.abs(s)) > 0 else s

@inst('strings')
@inst('pad')
def _strings(t, f):
    """Warm string ensemble pad."""
    s = np.sin(2*np.pi*f*t) * (1 - 0.5*np.exp(-2*t))
    s += 0.3 * np.sin(2*np.pi*f*2*t) * (1 - 0.5*np.exp(-3*t))
    s += 0.15 * np.sin(2*np.pi*f*3*t) * (1 - 0.5*np.exp(-4*t))
    s += 0.08 * np.sin(2*np.pi*f*4*t)
    # Slow attack
    env = np.minimum(1.0, t / 0.05)
    s = s * env
    return s / np.max(np.abs(s)) if np.max(np.abs(s)) > 0 else s

@inst('flute')
def _flute(t, f):
    """Flute-like with soft harmonics."""
    s = np.sin(2*np.pi*f*t) + 0.3*np.sin(2*np.pi*f*2*t)
    env = np.minimum(1.0, t / 0.03) * np.exp(-0.5*t)
    return s * env
