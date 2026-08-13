import numpy as np

SAMPLE_RATE = 44100
BITS = 16
CHANNELS = 2
MAX_AMP = 2**15 - 1

try:
    import sounddevice as sd
    _SD = True
except ImportError:
    _SD = False
try:
    import pyaudio
    _PA = True
except ImportError:
    _PA = False
try:
    import soundfile as sf
    _SF = True
except ImportError:
    _SF = False
