"""Live terminal waveform visualization during playback."""

import sys, os, time, math, threading, tempfile, subprocess
from pathlib import Path
import numpy as np

from ._constants import SAMPLE_RATE, CHANNELS, MAX_AMP, _SD, _PA

BARS = (' ', '▁', '▂', '▃', '▄', '▅', '▆', '▇', '█')
PB = ('░', '▒', '▓', '█')
C = {
    'R': '\033[0m',
    'DIM': '\033[2m',
    'BOLD': '\033[1m',
    'BLACK': '\033[30m',
    'RED': '\033[31m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'BLUE': '\033[34m',
    'MAGENTA': '\033[35m',
    'CYAN': '\033[36m',
    'WHITE': '\033[37m',
    'BRIGHT_GREEN': '\033[92m',
    'BRIGHT_CYAN': '\033[96m',
    'BRIGHT_YELLOW': '\033[93m',
    'REV': '\033[7m',
    'BG_GREEN': '\033[42m',
    'BG_CYAN': '\033[46m',
    'BG_YELLOW': '\033[43m',
}


def _precompute(mix, width):
    mono = np.mean(mix[:, :CHANNELS], axis=1) if CHANNELS > 1 and mix.ndim > 1 else mix
    peak = max(np.max(np.abs(mono)), 1e-10)
    chunk = max(1, len(mix) // width)
    amps = np.zeros(width)
    for i in range(width):
        s = i * chunk
        e = min(s + chunk, len(mix))
        block = mono[s:e]
        amps[i] = min(1.0, np.sqrt(np.mean(block ** 2)) / peak * 3.0)
    return amps


def _draw(amps, progress, total_secs, width):
    played = int(progress * width)
    playhead = min(played, width - 1)

    parts = []
    for i in range(width):
        b = BARS[min(8, int(amps[i] * 8))]
        if i < playhead:
            d = (playhead - i) / max(width, 1)
            if d < 0.15:
                parts.append(f'{C["BRIGHT_CYAN"]}{b}{C["R"]}')
            elif d < 0.4:
                parts.append(f'{C["CYAN"]}{b}{C["R"]}')
            else:
                parts.append(f'{C["GREEN"]}{b}{C["R"]}')
        elif i == playhead:
            parts.append(f'{C["REV"]}{C["BRIGHT_YELLOW"]} {C["R"]}')
        else:
            parts.append(f'{C["DIM"]}{b}{C["R"]}')
    wf = ''.join(parts)

    pb_chars = []
    bw = width
    bp = int(progress * bw)
    for i in range(bw):
        if i < bp:
            f = (bp - i) / max(bw, 1)
            if f < 0.1:
                pb_chars.append(f'{C["BRIGHT_GREEN"]}{PB[3]}{C["R"]}')
            elif f < 0.3:
                pb_chars.append(f'{C["GREEN"]}{PB[3]}{C["R"]}')
            else:
                pb_chars.append(f'{C["GREEN"]}{PB[2]}{C["R"]}')
        elif i == bp:
            pb_chars.append(f'{C["REV"]}{C["BRIGHT_YELLOW"]} {C["R"]}')
        else:
            pb_chars.append(f'{C["DIM"]}{PB[0]}{C["R"]}')
    pb_line = ''.join(pb_chars)

    t = int(progress * total_secs)
    tt = int(total_secs)
    ts = f'{C["BOLD"]}{t // 60:02d}:{t % 60:02d}{C["R"]} / {tt // 60:02d}:{tt % 60:02d}'

    sys.stdout.write(f'\033[2K\r  {wf}\n')
    sys.stdout.write(f'\033[2K\r  {pb_line}\n')
    sys.stdout.write(f'\033[2K\r  {ts}')
    sys.stdout.write(f'\033[3A\r')
    sys.stdout.flush()


def _clear_display(lines=3):
    for _ in range(lines):
        sys.stdout.write('\033[2K\033[1A')
    sys.stdout.write('\033[2K\r')
    sys.stdout.flush()


def play_with_waveform(mix):
    try:
        width = min(80, os.get_terminal_size().columns - 4)
    except OSError:
        width = 60
    total_secs = len(mix) / SAMPLE_RATE
    amps = _precompute(mix, width)
    a = np.clip(mix * MAX_AMP * 0.95, -MAX_AMP, MAX_AMP).astype(np.int16)

    sys.stdout.write('\033[?25l')

    try:
        if _SD:
            import sounddevice as sd
            sd.play(a, SAMPLE_RATE)
            progress = 0.0
            stalled = 0
            while True:
                try:
                    st = sd.get_stream()
                    if st is None or not st.active:
                        stalled += 1
                        if stalled > 200:  # ~6s with no stream → assume finished
                            break
                        time.sleep(0.033)
                        continue
                    stalled = 0
                    pos = int(st.time * SAMPLE_RATE)
                    progress = min(1.0, pos / len(mix))
                except:
                    if progress >= 0.99:
                        break
                _draw(amps, progress, total_secs, width)
                time.sleep(0.033)
            _draw(amps, 1.0, total_secs, width)

        elif _PA:
            import pyaudio
            p = pyaudio.PyAudio()
            stream = p.open(
                format=pyaudio.paInt16,
                channels=CHANNELS,
                rate=SAMPLE_RATE,
                output=True,
            )
            pos = 0
            chunk = 4096
            while pos < len(a):
                c = min(chunk, len(a) - pos)
                stream.write(a[pos:pos + c].tobytes())
                pos += c
                _draw(amps, pos / len(a), total_secs, width)
            stream.stop_stream()
            stream.close()
            p.terminate()
            _draw(amps, 1.0, total_secs, width)

        else:
            from ._engine import _save
            tmp = tempfile.mktemp(suffix='.wav')
            _save(mix, tmp)
            player = None
            for c in ('pw-play', 'paplay', 'aplay'):
                if subprocess.run(['which', c], capture_output=True).returncode == 0:
                    player = c
                    break
            if player:
                proc = subprocess.Popen(
                    [player, tmp],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                start = time.time()
                while proc.poll() is None:
                    elapsed = time.time() - start
                    _draw(amps, min(1.0, elapsed / total_secs), total_secs, width)
                    time.sleep(0.033)
                _draw(amps, 1.0, total_secs, width)
                proc.wait()
            Path(tmp).unlink(missing_ok=True)

    except KeyboardInterrupt:
        if _SD:
            import sounddevice as sd
            sd.stop()
        _clear_display()
        sys.stdout.write('\033[?25h')
        print('  Stopped.')
        return

    sys.stdout.write('\033[?25h\n')
