import sys
import time

_callback = None

def set_callback(cb):
    global _callback
    _callback = cb

def trigger(event_name, *args, **kwargs):
    if _callback:
        _callback(event_name, *args, **kwargs)

# Default ANSI colors
C = {
    'R': '\033[0m',
    'BOLD': '\033[1m',
    'CYAN': '\033[36m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'RED': '\033[31m',
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'DIM': '\033[2m',
    'BRIGHT_GREEN': '\033[92m',
    'BRIGHT_CYAN': '\033[96m',
}

def log(icon, message, color=C['CYAN'], delay=0.06):
    sys.stdout.write(f" {color}[{icon}]{C['R']} {message}\n")
    sys.stdout.flush()
    if delay > 0:
        time.sleep(delay)

def default_logger_callback(event, *args, **kwargs):
    if event == 'load_start':
        log('🔍', f"Locating file: {C['BOLD']}{args[0]}{C['R']}", C['CYAN'])
        log('📂', "Reading DSL source file...", C['CYAN'])
        log('📝', "Starting parsing pipeline...", C['CYAN'])
    elif event == 'parse_metadata':
        log('⚙️ ', f"Parser: Headers resolved -> tempo={args[0]} BPM, key={args[1]}, time={args[2]}", C['YELLOW'])
    elif event == 'parse_track':
        log('🧩', f"Parser: Discovered track {C['BOLD']}{args[0]}{C['R']} (instrument: {args[1]}, vol: {args[2]:.2f}, pan: {args[3]:.2f})", C['MAGENTA'])
    elif event == 'expand_markers':
        log('🔗', "Parser: Expanding voltas, repeats, patterns, and D.C./D.S. markers...", C['YELLOW'])
    elif event == 'load_done':
        log('✅', f"Parser: Completed! Found {C['BOLD']}{args[0]}{C['R']} tracks, {C['BOLD']}{args[1]}{C['R']} total notes.", C['GREEN'])
    elif event == 'render_start':
        log('🎛️ ', f"Render: Compiling audio waveform -> {args[0]:.1f} beats, {args[1]:.1f}s duration", C['CYAN'])
    elif event == 'render_track_start':
        log('🎹', f"Render: Synthesizing notes for track {C['BOLD']}{args[0]}{C['R']} (instrument: {args[1]})...", C['MAGENTA'])
    elif event == 'render_track_filter':
        log('🎛️ ', f"Render: Applying track filter -> type={args[0]}, fc={args[1]}Hz, Q={args[2]}", C['YELLOW'])
    elif event == 'render_track_dist':
        log('🔥', f"Render: Applying waveshaping distortion -> amount={args[0]:.2f}", C['RED'])
    elif event == 'render_mix':
        log('🎚️ ', "Render: Mixing tracks and applying master normalization...", C['CYAN'])
    elif event == 'render_master_reverb':
        log('🔮', f"Render: Applying master reverb -> mix={args[0]:.2f}", C['BLUE'])
    elif event == 'render_master_delay':
        log('⏳', f"Render: Applying master delay -> mix={args[0]:.2f}", C['BLUE'])
    elif event == 'render_done':
        log('✨', f"Render: Compilation finished successfully!", C['GREEN'])
    elif event == 'play_start':
        backend = args[0]
        log('🔊', f"Audio: Initializing playback engine (backend: {C['BOLD']}{backend}{C['R']})...", C['BRIGHT_GREEN'])
