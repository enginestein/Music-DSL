import sys
import os
import tty
import termios
import select
import re
import time
from pathlib import Path
from .parser import load
from .logger import set_callback, default_logger_callback
from ._constants import _SD, _PA

C = {
    'R': '\033[0m',
    'BOLD': '\033[1m',
    'DIM': '\033[2m',
    'CYAN': '\033[36m',
    'GREEN': '\033[32m',
    'YELLOW': '\033[33m',
    'RED': '\033[31m',
    'MAGENTA': '\033[35m',
    'BLUE': '\033[34m',
    'BRIGHT_GREEN': '\033[92m',
    'BRIGHT_CYAN': '\033[96m',
    'BRIGHT_YELLOW': '\033[93m',
    'BRIGHT_MAGENTA': '\033[95m',
}

def self_strip_ansi(s):
    return re.sub(r'\033\[[0-9;]*m', '', s)

def prompt_input(prompt_text):
    sys.stdout.write('\033[?25h')  # Show cursor
    sys.stdout.flush()
    try:
        val = input(prompt_text).strip()
    except (KeyboardInterrupt, EOFError):
        val = ""
    sys.stdout.write('\033[?25l')  # Hide cursor
    sys.stdout.flush()
    return val

def read_key():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        rlist, _, _ = select.select([sys.stdin], [], [])
        if rlist:
            ch = os.read(fd, 1)
            if ch == b'\x1b':
                # Check for arrow keys
                rlist2, _, _ = select.select([sys.stdin], [], [], 0.05)
                if rlist2:
                    ch2 = os.read(fd, 1)
                    if ch2 == b'[':
                        rlist3, _, _ = select.select([sys.stdin], [], [], 0.05)
                        if rlist3:
                            ch3 = os.read(fd, 1)
                            if ch3 == b'A': return 'up'
                            elif ch3 == b'B': return 'down'
                            elif ch3 == b'C': return 'right'
                            elif ch3 == b'D': return 'left'
                            return '\x1b[' + ch3.decode('utf-8', errors='ignore')
                    return '\x1b' + ch2.decode('utf-8', errors='ignore')
                return 'esc'
            elif ch in (b'\r', b'\n'):
                return 'enter'
            elif ch in (b'\x7f', b'\x08'):
                return 'backspace'
            return ch.decode('utf-8', errors='ignore').lower()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
    return None

def draw_screen(lines):
    # Append clear-to-end-of-line \033[K to prevent trailing characters.
    formatted = [l + '\033[K' for l in lines]
    sys.stdout.write('\033[H' + '\n'.join(formatted))
    sys.stdout.flush()

def list_directory_contents(d):
    path = Path(d).resolve()
    items = []
    
    # Add parent directory if not at root
    if path.parent != path:
        items.append(("..", True, path.parent))
        
    try:
        for entry in path.iterdir():
            if entry.is_dir():
                if not entry.name.startswith('.'):
                    items.append((entry.name, True, entry))
            elif entry.suffix == '.music':
                items.append((entry.name, False, entry))
    except PermissionError:
        pass
        
    folders = sorted([x for x in items if x[1] and x[0] != ".."], key=lambda x: x[0].lower())
    files = sorted([x for x in items if not x[1]], key=lambda x: x[0].lower())
    
    parent = [x for x in items if x[0] == ".."]
    return parent + folders + files

def get_song_details(filepath, max_w):
    try:
        song = load(filepath)
        dur = song.dur_secs()
        beats = song.total_beats()
        num_tracks = len(song.tracks)
        notes_count = sum(len(t.notes) for t in song.tracks)
        
        lines = [
            f"{C['BOLD']}{C['BRIGHT_YELLOW']}SONG SUMMARY{C['R']}",
            f"  {C['CYAN']}Title:{C['R']}  {(song.name or filepath.name)[:max_w-12]}",
            f"  {C['CYAN']}Tempo:{C['R']}  {song.tempo} BPM",
            f"  {C['CYAN']}Key:{C['R']}    {getattr(song, 'key', 'C')}",
            f"  {C['CYAN']}Time:{C['R']}   {song.beats_per_bar}/{song.beat_unit}",
            f"  {C['CYAN']}Length:{C['R']} {dur:.1f}s ({beats:.1f} beats)",
            f"  {C['CYAN']}Tracks:{C['R']} {num_tracks}",
            f"  {C['CYAN']}Notes:{C['R']}  {notes_count}",
            "",
            f"{C['BOLD']}{C['BRIGHT_YELLOW']}TRACK DETAILS:{C['R']}"
        ]
        for i, t in enumerate(song.tracks, 1):
            lines.append(f"  {i}. {C['MAGENTA']}{t.name[:max_w-18]}{C['R']} ({t.inst}, {len(t.notes)} n)")
            if t.notes:
                notes_preview = " ".join(repr(n) for n in t.notes[:3])
                if len(t.notes) > 3:
                    notes_preview += " ..."
                lines.append(f"     {C['DIM']}{notes_preview[:max_w-8]}{C['R']}")
        return lines
    except Exception as e:
        err_msg = str(e)
        lines = [
            f"{C['BOLD']}{C['RED']}❌ PARSING ERROR{C['R']}",
            "",
        ]
        wrap_w = max(15, max_w - 4)
        for chunk in [err_msg[i:i+wrap_w] for i in range(0, len(err_msg), wrap_w)]:
            lines.append(f"  {C['RED']}{chunk}{C['R']}")
        return lines

def get_dir_details(dirpath, max_w):
    path_str = str(dirpath)
    if len(path_str) > max_w - 10:
        path_str = "..." + path_str[-(max_w - 13):]
    return [
        f"{C['BOLD']}{C['BRIGHT_YELLOW']}DIRECTORY{C['R']}",
        "",
        f"  {C['CYAN']}Name:{C['R']} {dirpath.name or '/'}",
        f"  {C['CYAN']}Path:{C['R']} {path_str}",
        "",
        f"  {C['DIM']}Press [Enter] to open this directory.{C['R']}"
    ]

def build_home_menu(select_idx, w, h):
    out = []
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╔{'═' * (w-2)}╗{C['R']}")
    
    # Check if we should display the ASCII logo or a simpler one based on resolution
    if h >= 18:
        logo = [
            "  __  ___           _      ___  ____  __   ",
            " /  |/  /_  _______(_)____/   \\/ ___// /   ",
            "/ /|_/ / / / / ___/ / ___/ /|  \\__ \\/ /    ",
            "/ /  / / /_/ (__  ) / /__/ ___  /__/ / /___",
            "/_/  /_/\\__,_/____/_/\\___/_/  |_/____/_____/"
        ]
        for row in logo:
            pad_l = (w - 2 - len(row)) // 2
            line = " " * pad_l + f"{C['BRIGHT_CYAN']}{C['BOLD']}{row}{C['R']}" + " " * (w - 2 - pad_l - len(row))
            out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{line}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
            
        subtitle = "-- Text-Based Music Programming Engine --"
        pad_s = (w - 2 - len(subtitle)) // 2
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_s}{C['DIM']}{subtitle}{C['R']}{' ' * (w - 2 - pad_s - len(subtitle))}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╠{'═' * (w-2)}╣{C['R']}")
        fixed_lines = 13
    else:
        title_text = "🎵  MUSIC DSL  🎵"
        pad_t = (w - 2 - len(title_text)) // 2
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_t}{C['BOLD']}{C['BRIGHT_CYAN']}{title_text}{C['R']}{' ' * (w - 2 - pad_t - len(title_text))}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
        subtitle = "-- Programming Engine --"
        pad_s = (w - 2 - len(subtitle)) // 2
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_s}{C['DIM']}{subtitle}{C['R']}{' ' * (w - 2 - pad_s - len(subtitle))}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╠{'═' * (w-2)}╣{C['R']}")
        fixed_lines = 9

    content_rows = h - fixed_lines
    menu_options = [
        "Browse Files & Directories",
        "Browse Built-in Samples",
        "Import MIDI File",
        "Exit"
    ]
    
    # Audio Driver Status
    driver_str = "Sounddevice" if _SD else ("PyAudio" if _PA else "aplay/pw-play")
    driver_color = C['BRIGHT_GREEN'] if (_SD or _PA) else C['YELLOW']
    status_line = f"Audio: {driver_color}{driver_str}{C['R']} | CWD: {C['CYAN']}{Path('.').resolve().name[:w-45]}{C['R']}"
    visual_status_len = len(self_strip_ansi(status_line))
    pad_st = (w - 2 - visual_status_len) // 2
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_st}{status_line}{' ' * (w - 2 - pad_st - visual_status_len)}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{' ' * (w-2)}║{C['R']}")
    
    menu_start_row = 2 + (content_rows - len(menu_options) - 2) // 2
    
    for i in range(2, content_rows):
        line_content = ""
        if menu_start_row <= i < menu_start_row + len(menu_options):
            opt_idx = i - menu_start_row
            pointer = "  ▶  " if opt_idx == select_idx else "     "
            color = C['BRIGHT_GREEN'] if opt_idx == select_idx else C['R']
            line_content = f"{pointer}{color}{menu_options[opt_idx]}{C['R']}"
        
        visual_len = len(self_strip_ansi(line_content))
        pad_l = (w - 2 - visual_len) // 2
        line_padded = " " * pad_l + line_content + " " * (w - 2 - pad_l - visual_len)
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{line_padded}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")

    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╠{'═' * (w-2)}╣{C['R']}")
    footer_text = " Use [▲/▼] to select | [Enter] to choose "
    pad_f = (w - 2 - len(footer_text)) // 2
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_f}{C['BOLD']}{C['YELLOW']}{footer_text}{C['R']}{' ' * (w - 2 - pad_f - len(footer_text))}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╚{'═' * (w-2)}╝{C['R']}")
    return out

def build_browse_screen(title, items, select_idx, detail_lines, current_dir, w, h):
    out = []
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╔{'═' * (w-2)}╗{C['R']}")
    
    path_info = f" {title.upper()} "
    if current_dir:
        path_display = str(current_dir)
        if len(path_display) > w - len(path_info) - 15:
            path_display = "..." + path_display[-(w - len(path_info) - 18):]
        path_info += f"| Path: {path_display} "
        
    padding = (w - 2 - len(path_info)) // 2
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{' ' * padding}{C['BRIGHT_YELLOW']}{path_info}{C['R']}{' ' * (w - 2 - padding - len(path_info))}║{C['R']}")
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╚{'═' * (w-2)}╝{C['R']}")

    content_h = h - 6
    col1_w = 32
    col2_w = w - col1_w - 3

    start_idx = 0
    if len(items) > content_h:
        if select_idx >= content_h - 2:
            start_idx = select_idx - (content_h - 3)
            
    for i in range(content_h):
        file_line = ""
        item_idx = start_idx + i
        if item_idx < len(items):
            name, is_dir, _ = items[item_idx]
            pointer = " ▶ " if item_idx == select_idx else "   "
            color = C['BRIGHT_GREEN'] if item_idx == select_idx else C['R']
            
            icon = "📁 " if is_dir else "🎵 "
            suffix = "/" if is_dir and name != ".." else ""
            display_name = icon + name + suffix
            
            fn_display = display_name[:col1_w - 6]
            if len(display_name) > col1_w - 6:
                fn_display += ".."
            file_line = f"{pointer}{color}{fn_display}{C['R']}"
        
        file_line_padded = file_line + " " * (col1_w - len(self_strip_ansi(file_line)))
        
        detail_line = ""
        if i < len(detail_lines):
            detail_line = detail_lines[i]
        detail_line_padded = detail_line + " " * (col2_w - len(self_strip_ansi(detail_line)))
        
        out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']} {file_line_padded} {C['BOLD']}{C['BRIGHT_CYAN']}│{C['R']} {detail_line_padded} {C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
    
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╠{'═' * (w-2)}╣{C['R']}")
    footer_text = " [▲/▼] Navigate | [Enter/P] Play/Open | [W] Waveform | [E] WAV | [M] MIDI | [Esc/B] Back "
    pad_f = (w - 2 - len(footer_text)) // 2
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}{' ' * pad_f}{C['BOLD']}{C['YELLOW']}{footer_text}{C['R']}{' ' * (w - 2 - pad_f - len(footer_text))}{C['BOLD']}{C['BRIGHT_CYAN']}║{C['R']}")
    out.append(f"{C['BOLD']}{C['BRIGHT_CYAN']}╚{'═' * (w-2)}╝{C['R']}")
    return out

def run_tui():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        # Switch to alternate screen, hide cursor, clear screen, move home
        sys.stdout.write('\033[?1049h\033[?25l\033[2J\033[H')
        sys.stdout.flush()
        
        state = "main_menu"
        select_idx = 0
        
        current_dir = Path('.').resolve()
        file_items = []
        sample_items = []
        
        while True:
            # Query terminal size dynamically on each iteration
            try:
                size = os.get_terminal_size()
                w = size.columns
                h = size.lines
            except:
                w, h = 80, 24

            w = max(60, w)
            h = max(12, h)

            if state == "browse_files":
                file_items = list_directory_contents(current_dir)
                if not file_items:
                    file_items = [("(Empty folder)", False, current_dir)]
            elif state == "browse_samples":
                sample_dir = Path(__file__).parent / 'samples'
                sample_files = sorted([f.name for f in sample_dir.glob('*.music')])
                sample_items = [(f, False, sample_dir / f) for f in sample_files]
                if not sample_items:
                    sample_items = [("(No samples found)", False, sample_dir)]

            if state == "main_menu":
                lines = build_home_menu(select_idx, w, h)
                draw_screen(lines)
                key = read_key()
                if key == 'up':
                    select_idx = (select_idx - 1) % 4
                elif key == 'down':
                    select_idx = (select_idx + 1) % 4
                elif key == 'enter':
                    if select_idx == 0:
                        state = "browse_files"
                        select_idx = 0
                    elif select_idx == 1:
                        state = "browse_samples"
                        select_idx = 0
                    elif select_idx == 2:
                        os.system('clear')
                        sys.stdout.write('\033[?25h')
                        sys.stdout.flush()
                        print(f"{C['BOLD']}{C['CYAN']}=== IMPORT MIDI FILE ==={C['R']}\n")
                        mid_file = prompt_input("Enter path to input MIDI file: ")
                        if mid_file:
                            out_music = prompt_input("Enter output path (e.g. song.music, Enter to play directly): ")
                            print()
                            set_callback(default_logger_callback)
                            try:
                                from .cli import _import_midi
                                _import_midi(mid_file, out_music if out_music else None)
                            except Exception as e:
                                print(f"{C['RED']}Error importing MIDI: {e}{C['R']}")
                            except KeyboardInterrupt:
                                print(f"\n{C['YELLOW']}MIDI import cancelled by user.{C['R']}")
                            set_callback(None)
                            print(f"\nPress any key to return to menu...")
                            read_key()
                        sys.stdout.write('\033[?25l')
                        sys.stdout.flush()
                        state = "main_menu"
                        select_idx = 2
                    elif select_idx == 3:
                        break
                elif key == 'esc' or key == 'q':
                    break

            elif state == "browse_files" or state == "browse_samples":
                items = file_items if state == "browse_files" else sample_items
                title = "File Explorer" if state == "browse_files" else "Built-in Samples"
                
                if select_idx >= len(items):
                    select_idx = max(0, len(items) - 1)
                
                name, is_dir, path = items[select_idx] if items else ("", False, None)

                # Set right side column width dynamically
                col2_w = w - 32 - 3

                detail_lines = []
                if path and path.exists():
                    if is_dir:
                        detail_lines = get_dir_details(path, col2_w)
                    else:
                        detail_lines = get_song_details(path, col2_w)
                else:
                    detail_lines = [f"{C['DIM']}Select an item to view preview details.{C['R']}"]
                    
                lines = build_browse_screen(title, items, select_idx, detail_lines, 
                                            current_dir if state == "browse_files" else None, w, h)
                draw_screen(lines)
                
                key = read_key()
                if key == 'up':
                    select_idx = (select_idx - 1) % len(items) if items else 0
                elif key == 'down':
                    select_idx = (select_idx + 1) % len(items) if items else 0
                elif key == 'esc' or key == 'b' or key == 'q':
                    state = "main_menu"
                    select_idx = 0 if state == "browse_files" else 1
                elif key == 'enter' or key == 'p':
                    if is_dir and path:
                        current_dir = path
                        select_idx = 0
                    elif path and path.exists() and path.suffix == '.music':
                        os.system('clear')
                        sys.stdout.write('\033[?25h')
                        sys.stdout.flush()
                        print(f"{C['BOLD']}{C['CYAN']}=== RENDERING & PLAYING: {path.name} ==={C['R']}\n")
                        set_callback(default_logger_callback)
                        try:
                            song = load(path)
                            song.play(wait=True)
                            set_callback(None)
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                        except KeyboardInterrupt:
                            if _SD:
                                try:
                                    import sounddevice as sd
                                    sd.stop()
                                except: pass
                            set_callback(None)
                            print(f"\n{C['YELLOW']}Playback interrupted. Returning to home menu...{C['R']}")
                            time.sleep(1.0)
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                            prev_state = state
                            state = "main_menu"
                            select_idx = 0 if prev_state == "browse_files" else 1
                        except Exception as e:
                            set_callback(None)
                            print(f"\n{C['RED']}Playback Error: {e}{C['R']}")
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                elif key == 'w':
                    if not is_dir and path and path.exists() and path.suffix == '.music':
                        os.system('clear')
                        sys.stdout.write('\033[?25h')
                        sys.stdout.flush()
                        print(f"{C['BOLD']}{C['CYAN']}=== RENDERING WITH WAVEFORM: {path.name} ==={C['R']}\n")
                        set_callback(default_logger_callback)
                        try:
                            song = load(path)
                            mix = song.render()
                            set_callback(None)
                            print(f"{C['BOLD']}{C['GREEN']}Launching Live Waveform Visualizer...{C['R']}\n")
                            from ._waveform import play_with_waveform
                            play_with_waveform(mix)
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                        except KeyboardInterrupt:
                            if _SD:
                                try:
                                    import sounddevice as sd
                                    sd.stop()
                                except: pass
                            set_callback(None)
                            print(f"\n{C['YELLOW']}Waveform visualization interrupted. Returning to home menu...{C['R']}")
                            time.sleep(1.0)
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                            prev_state = state
                            state = "main_menu"
                            select_idx = 0 if prev_state == "browse_files" else 1
                        except Exception as e:
                            set_callback(None)
                            print(f"\n{C['RED']}Waveform Error: {e}{C['R']}")
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                elif key == 'e':
                    if not is_dir and path and path.exists() and path.suffix == '.music':
                        os.system('clear')
                        sys.stdout.write('\033[?25h')
                        sys.stdout.flush()
                        print(f"{C['BOLD']}{C['CYAN']}=== EXPORT TO WAV: {path.name} ==={C['R']}\n")
                        default_wav = path.with_suffix('.wav').name
                        wav_name = prompt_input(f"Enter output WAV name (default: {default_wav}): ")
                        if not wav_name:
                            wav_name = default_wav
                        
                        set_callback(default_logger_callback)
                        try:
                            song = load(path)
                            song.save(wav_name)
                            print(f"\n{C['BOLD']}{C['GREEN']}Export successful: {wav_name}{C['R']}")
                            set_callback(None)
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                        except KeyboardInterrupt:
                            set_callback(None)
                            print(f"\n{C['YELLOW']}WAV export cancelled. Returning to home menu...{C['R']}")
                            time.sleep(1.0)
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                            prev_state = state
                            state = "main_menu"
                            select_idx = 0 if prev_state == "browse_files" else 1
                        except Exception as e:
                            set_callback(None)
                            print(f"\n{C['RED']}Export Error: {e}{C['R']}")
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                elif key == 'm':
                    if not is_dir and path and path.exists() and path.suffix == '.music':
                        os.system('clear')
                        sys.stdout.write('\033[?25h')
                        sys.stdout.flush()
                        print(f"{C['BOLD']}{C['CYAN']}=== EXPORT TO MIDI: {path.name} ==={C['R']}\n")
                        default_mid = path.with_suffix('.mid').name
                        mid_name = prompt_input(f"Enter output MIDI name (default: {default_mid}): ")
                        if not mid_name:
                            mid_name = default_mid
                        
                        set_callback(default_logger_callback)
                        try:
                            song = load(path)
                            song.to_midi(mid_name)
                            print(f"\n{C['BOLD']}{C['GREEN']}Export successful: {mid_name}{C['R']}")
                            set_callback(None)
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                        except KeyboardInterrupt:
                            set_callback(None)
                            print(f"\n{C['YELLOW']}MIDI export cancelled. Returning to home menu...{C['R']}")
                            time.sleep(1.0)
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
                            prev_state = state
                            state = "main_menu"
                            select_idx = 0 if prev_state == "browse_files" else 1
                        except Exception as e:
                            set_callback(None)
                            print(f"\n{C['RED']}Export Error: {e}{C['R']}")
                            print(f"\nPress any key to return to menu...")
                            read_key()
                            sys.stdout.write('\033[?25l')
                            sys.stdout.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        # Switch back to normal screen and show cursor
        sys.stdout.write('\033[?1049l\033[?25h')
        sys.stdout.flush()
