#!/usr/bin/env python3
"""
Music DSL — GNOME/Adwaita GUI
==============================

A native-looking GTK3 front end for the Music-DSL package
(https://github.com/enginestein/Music-DSL). Lets you write, play, and
export ``.music`` files without touching the command line.

Run it from the repository root:

    python3 gui/main.py [optional/path/to/song.music]

Requires PyGObject (GTK 3) plus the ``music`` package itself. Playback
uses whatever backend ``music`` picks (sounddevice is preferred; the
Stop button only works when sounddevice is the active backend, since
that's the only one this DSL exposes a way to interrupt).
"""

import os
import re
import sys
import tempfile
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, Gdk, GLib, Gio, Pango  # noqa: E402

# GtkSourceView gives us a proper, battle-tested line-number gutter (plus
# current-line highlighting) instead of hand-drawing one with cairo.
# Try the newer API version first, then the older one, then fall back to
# a plain Gtk.TextView (no line numbers, but the app still works).
GtkSource = None
for _ver in ("4", "3.0"):
    try:
        gi.require_version("GtkSource", _ver)
        from gi.repository import GtkSource as _GtkSource

        GtkSource = _GtkSource
        break
    except (ValueError, ImportError):
        continue
HAS_GTKSOURCE = GtkSource is not None

# ---------------------------------------------------------------------------
# Make the `music` package importable when running straight out of the repo
# (gui/main.py -> repo root -> music/).  If the package is pip-installed this
# is a harmless no-op fallback.
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

_IMPORT_ERROR = None
try:
    from music import load, midi_to_song, song_to_text
except Exception as exc:  # pragma: no cover - surfaced in the UI instead
    load = midi_to_song = song_to_text = None
    _IMPORT_ERROR = exc

try:
    import sounddevice as _sd
except Exception:
    _sd = None

APP_ID = "io.github.enginestein.MusicDSL"
APP_NAME = "Music DSL"

DEFAULT_SONG = """tempo: 120   name: New Song   key: C

-- melody: piano 0.5 0.0 --
C4 q  E4 q  G4 q  C5 q
"""

KEY_LINE_RE = re.compile(r"^\s*key\s*:\s*(.+?)\s*$", re.MULTILINE)


# ---------------------------------------------------------------------------
# Text editor with lightweight regex-based syntax highlighting
# ---------------------------------------------------------------------------
_MATCHED_SCHEME_ID = "musicdsl-matched"


def _rgba_hex(rgba):
    return "#{:02x}{:02x}{:02x}".format(
        max(0, min(255, round(rgba.red * 255))),
        max(0, min(255, round(rgba.green * 255))),
        max(0, min(255, round(rgba.blue * 255))),
    )


def _blend(c1, c2, t):
    """Blend RGBA c1 toward c2 by fraction t (0 = c1, 1 = c2)."""
    out = Gdk.RGBA()
    out.red = c1.red + (c2.red - c1.red) * t
    out.green = c1.green + (c2.green - c1.green) * t
    out.blue = c1.blue + (c2.blue - c1.blue) * t
    out.alpha = 1.0
    return out


def _theme_color(ctx, name, fallback_hex):
    ok, rgba = ctx.lookup_color(name)
    if ok:
        return rgba
    fallback = Gdk.RGBA()
    fallback.parse(fallback_hex)
    return fallback


def _build_theme_matched_scheme(widget):
    """Build (and load) a GtkSourceView scheme whose colors are read
    straight off the app's own live GTK theme — i.e. whatever a tool
    like matugen has set — instead of a color scheme of our own. This
    makes the editor's background/text/gutter match the rest of the
    app exactly, rather than standing out as its own thing.
    """
    if not HAS_GTKSOURCE:
        return None
    try:
        ctx = widget.get_style_context()
        bg = _theme_color(ctx, "theme_base_color", "#1e1e20")
        fg = _theme_color(ctx, "theme_text_color", "#e6e6e6")
        sel_bg = _theme_color(ctx, "theme_selected_bg_color", "#3584e4")
        sel_fg = _theme_color(ctx, "theme_selected_fg_color", "#ffffff")

        # Gutter/line-numbers: same background as the text (so it
        # reads as one continuous surface, matching matugen exactly),
        # with numbers dimmed by blending the text color toward the
        # background rather than using a fixed gray.
        gutter_bg = bg
        gutter_fg = _blend(fg, bg, 0.45)
        current_line_bg = _blend(bg, fg, 0.06)

        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<style-scheme id="{_MATCHED_SCHEME_ID}" _name="Music DSL (theme-matched)" version="1.0">
  <author>Music DSL</author>
  <_description>Colors mirrored from the active GTK theme</_description>
  <color name="bg" value="{_rgba_hex(bg)}"/>
  <color name="fg" value="{_rgba_hex(fg)}"/>
  <color name="gutter-bg" value="{_rgba_hex(gutter_bg)}"/>
  <color name="gutter-fg" value="{_rgba_hex(gutter_fg)}"/>
  <color name="selection-bg" value="{_rgba_hex(sel_bg)}"/>
  <color name="selection-fg" value="{_rgba_hex(sel_fg)}"/>
  <color name="current-line-bg" value="{_rgba_hex(current_line_bg)}"/>

  <style name="text" foreground="fg" background="bg"/>
  <style name="selection" foreground="selection-fg" background="selection-bg"/>
  <style name="current-line" background="current-line-bg"/>
  <style name="line-numbers" foreground="gutter-fg" background="gutter-bg"/>
  <style name="current-line-number" foreground="fg" background="gutter-bg" bold="true"/>
  <style name="background-pattern" background="bg"/>
  <style name="bracket-match" foreground="fg" background="selection-bg"/>
</style-scheme>
"""
        scheme_dir = Path(tempfile.gettempdir()) / "musicdsl-gtksource-styles"
        scheme_dir.mkdir(parents=True, exist_ok=True)
        scheme_file = scheme_dir / f"{_MATCHED_SCHEME_ID}.xml"
        scheme_file.write_text(xml)
        mgr = GtkSource.StyleSchemeManager.get_default()
        mgr.append_search_path(str(scheme_dir))
        mgr.force_rescan()
        return mgr.get_scheme(_MATCHED_SCHEME_ID)
    except Exception:
        return None


class Editor(Gtk.ScrolledWindow):
    def __init__(self, on_changed):
        super().__init__()
        self.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        self.get_style_context().add_class("view")

        if HAS_GTKSOURCE:
            self.buffer = GtkSource.Buffer()
            self.view = GtkSource.View.new_with_buffer(self.buffer)
            # Colors are matched against self.view's own style context
            # (not self, the ScrolledWindow) since that's the widget
            # whose theme the text area should mirror.
            scheme = _build_theme_matched_scheme(self.view)
            if scheme is not None:
                self.buffer.set_style_scheme(scheme)
            self.view.set_show_line_numbers(True)
            # NOTE: highlight-current-line is intentionally left off.
            # GtkSourceView has a known bug (seen across several
            # themes/versions) where the current-line highlight can
            # render as a giant rectangle filling the rest of the
            # widget instead of a single line's height, particularly
            # when the cursor sits on the last/an empty line. Not worth
            # the visual glitch for a nice-to-have.
            self.view.set_highlight_current_line(False)
            self.view.set_auto_indent(True)
            self.view.set_tab_width(4)
            self.view.set_insert_spaces_instead_of_tabs(True)
        else:
            # No GtkSourceView on this system: fall back to a plain
            # editor. It still fully works, it just won't have a
            # line-number gutter.
            self.buffer = Gtk.TextBuffer()
            self.view = Gtk.TextView.new_with_buffer(self.buffer)

        self.view.set_monospace(True)
        self.view.set_wrap_mode(Gtk.WrapMode.NONE)
        self.view.set_left_margin(6)
        self.view.set_right_margin(10)
        self.view.set_top_margin(8)
        self.view.set_bottom_margin(8)

        self._make_tags()
        self.add(self.view)

        self._highlight_id = None
        self._on_changed_cb = on_changed
        self.buffer.connect("changed", self._queue_highlight)

    def _make_tags(self):
        tb = self.buffer
        tb.create_tag("comment", foreground="#9a9996", style=Pango.Style.ITALIC)
        tb.create_tag("directive", foreground="#1c71d8", weight=Pango.Weight.BOLD)
        tb.create_tag("track", foreground="#9141ac", weight=Pango.Weight.BOLD)
        tb.create_tag("command", foreground="#e66100", weight=Pango.Weight.BOLD)
        tb.create_tag("note", foreground="#26a269")
        tb.create_tag("dynamic", foreground="#c64600")

    def _queue_highlight(self, *_a):
        if self._highlight_id:
            GLib.source_remove(self._highlight_id)
        self._highlight_id = GLib.timeout_add(250, self._apply_highlight)
        if self._on_changed_cb:
            self._on_changed_cb()

    def _apply_highlight(self):
        self._highlight_id = None
        tb = self.buffer
        start, end = tb.get_bounds()
        text = tb.get_text(start, end, True)
        for tag in ("comment", "directive", "track", "command", "note", "dynamic"):
            tb.remove_tag_by_name(tag, start, end)

        def apply(tagname, pattern, flags=0):
            for m in re.finditer(pattern, text, flags):
                s = tb.get_iter_at_offset(m.start())
                e = tb.get_iter_at_offset(m.end())
                tb.apply_tag_by_name(tagname, s, e)

        apply("track", r"^\s*--.*--\s*$", re.MULTILINE)
        apply(
            "directive",
            r"^\s*(tempo|name|key|time|reverb|delay|swing|adsr|filter|dist|humanize|inst)\s*:",
            re.MULTILINE,
        )
        apply("command", r"@\S+")
        apply("dynamic", r"\b(ppp|pp|p|mp|mf|f|ff|fff|sffz|fp)\b")
        apply("note", r"\b[A-G][b#]?\d(?:\.{1,2}|t)?\b")
        apply("comment", r"#.*$", re.MULTILINE)
        return False

    def get_text(self):
        s, e = self.buffer.get_bounds()
        return self.buffer.get_text(s, e, True)

    def set_text(self, text):
        self.buffer.set_text(text)
        self.buffer.set_modified(False)
        self._apply_highlight()

    def is_modified(self):
        return self.buffer.get_modified()

    def set_modified(self, val):
        self.buffer.set_modified(val)


# ---------------------------------------------------------------------------
# One row in the track list sidebar
# ---------------------------------------------------------------------------
class TrackRow(Gtk.ListBoxRow):
    def __init__(self, track, index, on_mute_toggle):
        super().__init__()
        self.set_activatable(False)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        box.set_border_width(8)

        icon = Gtk.Image.new_from_icon_name(
            "audio-x-generic-symbolic", Gtk.IconSize.BUTTON
        )
        box.pack_start(icon, False, False, 0)

        vbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=1)
        name_lbl = Gtk.Label(label=f"{index + 1}. {track.name}", xalign=0)
        name_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.pack_start(name_lbl, False, False, 0)

        details = f"{track.inst} · vol {track.vol:.2f} · pan {track.pan:+.2f} · {len(track.notes)} notes"
        sub_lbl = Gtk.Label(xalign=0)
        sub_lbl.set_markup(f"<small>{GLib.markup_escape_text(details)}</small>")
        sub_lbl.get_style_context().add_class("dim-label")
        sub_lbl.set_ellipsize(Pango.EllipsizeMode.END)
        vbox.pack_start(sub_lbl, False, False, 0)

        box.pack_start(vbox, True, True, 0)

        mute_switch = Gtk.Switch()
        mute_switch.set_valign(Gtk.Align.CENTER)
        mute_switch.set_active(not track.mute)
        mute_switch.set_tooltip_text("Include this track in preview playback")
        mute_switch.connect(
            "notify::active",
            lambda sw, _p: on_mute_toggle(index, not sw.get_active()),
        )
        box.pack_start(mute_switch, False, False, 0)

        self.add(box)


# ---------------------------------------------------------------------------
# Sidebar: song summary + track list
# ---------------------------------------------------------------------------
class Sidebar(Gtk.Box):
    INFO_FIELDS = ("Name", "Tempo", "Key", "Time", "Duration", "Tracks")

    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_size_request(300, -1)

        info_grid = Gtk.Grid(row_spacing=6, column_spacing=12)
        info_grid.set_border_width(12)
        self._info_values = {}
        for i, key in enumerate(self.INFO_FIELDS):
            k_lbl = Gtk.Label(label=key, xalign=0)
            k_lbl.get_style_context().add_class("dim-label")
            v_lbl = Gtk.Label(label="—", xalign=0)
            v_lbl.set_ellipsize(Pango.EllipsizeMode.END)
            v_lbl.set_hexpand(True)
            info_grid.attach(k_lbl, 0, i, 1, 1)
            info_grid.attach(v_lbl, 1, i, 1, 1)
            self._info_values[key] = v_lbl

        tracks_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        tracks_label = Gtk.Label(label="Tracks", xalign=0)
        tracks_label.get_style_context().add_class("heading")
        tracks_label.set_margin_start(12)
        tracks_label.set_margin_top(6)
        tracks_label.set_margin_bottom(4)
        tracks_header.pack_start(tracks_label, True, True, 0)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.get_style_context().add_class("boxed-list")

        placeholder = Gtk.Label(
            label="Write or open a song to see its tracks here."
        )
        placeholder.set_line_wrap(True)
        placeholder.get_style_context().add_class("dim-label")
        placeholder.set_margin_top(24)
        placeholder.set_margin_start(16)
        placeholder.set_margin_end(16)
        placeholder.show()
        self.listbox.set_placeholder(placeholder)

        scroller = Gtk.ScrolledWindow()
        scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scroller.add(self.listbox)
        scroller.set_margin_start(10)
        scroller.set_margin_end(10)
        scroller.set_margin_bottom(10)

        self.pack_start(info_grid, False, False, 0)
        self.pack_start(Gtk.Separator(), False, False, 0)
        self.pack_start(tracks_header, False, False, 0)
        self.pack_start(scroller, True, True, 0)

    def clear(self):
        for lbl in self._info_values.values():
            lbl.set_text("—")
        for child in self.listbox.get_children():
            self.listbox.remove(child)

    def update(self, song, key_str, on_mute_toggle):
        if song is None:
            self.clear()
            return
        self._info_values["Name"].set_text(song.name or "Untitled")
        self._info_values["Tempo"].set_text(f"{song.tempo:g} BPM")
        self._info_values["Key"].set_text(key_str or "—")
        self._info_values["Time"].set_text(f"{song.beats_per_bar}/{song.beat_unit}")
        self._info_values["Duration"].set_text(f"{song.dur_secs():.1f}s")
        self._info_values["Tracks"].set_text(str(len(song.tracks)))

        for child in self.listbox.get_children():
            self.listbox.remove(child)
        for i, tr in enumerate(song.tracks):
            row = TrackRow(tr, i, on_mute_toggle)
            row.show_all()
            self.listbox.add(row)


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------
class MusicDSLWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title=APP_NAME)
        self.set_default_size(1150, 720)
        self.set_icon_name("audio-x-generic")

        self.current_path = None
        self.song = None
        self.playing = False
        self.busy = False
        self._analyze_id = None

        self._build_headerbar()
        self._build_body()
        self._build_css()

        self.connect("delete-event", self._on_delete_event)

        self.editor.set_text(DEFAULT_SONG)
        self._update_title()

        # Widgets are hidden by default in GTK3 until shown explicitly.
        # show_all() reveals the whole tree we just built; the error
        # InfoBar stays invisible afterwards since it lives inside a
        # Gtk.Revealer with reveal-child still False.
        self.show_all()

        if _IMPORT_ERROR is not None:
            self.show_error(
                "Couldn't import the 'music' package: "
                f"{_IMPORT_ERROR}. Make sure gui/main.py is run from "
                "inside the Music-DSL project (or that 'music' is installed)."
            )
        elif not HAS_GTKSOURCE:
            self.show_error(
                "GtkSourceView isn't installed, so the editor has no line "
                "numbers. Install it (e.g. 'sudo pacman -S gtksourceview4' "
                "on Arch/CachyOS) and restart to enable them — everything "
                "else still works without it.",
                message_type=Gtk.MessageType.WARNING,
            )

    # -- UI construction ---------------------------------------------------
    def _build_headerbar(self):
        hb = Gtk.HeaderBar()
        hb.set_show_close_button(True)
        hb.set_title(APP_NAME)
        self.headerbar = hb

        new_btn = self._toolbutton("document-new-symbolic", "New song (Ctrl+N)")
        new_btn.connect("clicked", self.action_new)
        hb.pack_start(new_btn)

        open_btn = self._toolbutton("document-open-symbolic", "Open… (Ctrl+O)")
        open_btn.connect("clicked", self.action_open)
        hb.pack_start(open_btn)

        save_btn = self._toolbutton("document-save-symbolic", "Save (Ctrl+S)")
        save_btn.connect("clicked", self.action_save)
        hb.pack_start(save_btn)
        self.save_btn = save_btn

        save_as_btn = self._toolbutton(
            "document-save-as-symbolic", "Save As… (Ctrl+Shift+S)"
        )
        save_as_btn.connect("clicked", self.action_save_as)
        hb.pack_start(save_as_btn)

        # Right side: play / export / menu
        menu_btn = Gtk.MenuButton()
        menu_btn.set_image(
            Gtk.Image.new_from_icon_name("open-menu-symbolic", Gtk.IconSize.BUTTON)
        )
        menu_btn.set_tooltip_text("Main menu")
        primary_menu = Gio.Menu()
        primary_menu.append("Keyboard Shortcuts", "app.shortcuts")
        primary_menu.append("About Music DSL", "app.about")
        primary_menu.append("Quit", "app.quit")
        menu_btn.set_menu_model(primary_menu)
        hb.pack_end(menu_btn)

        export_btn = Gtk.MenuButton()
        export_btn.set_image(
            Gtk.Image.new_from_icon_name(
                "document-send-symbolic", Gtk.IconSize.BUTTON
            )
        )
        export_btn.set_tooltip_text("Import / Export")
        export_menu = Gio.Menu()
        export_menu.append("Export to WAV…", "app.export_wav")
        export_menu.append("Export to MIDI…", "app.export_midi")
        export_menu.append("Import MIDI…", "app.import_midi")
        export_btn.set_menu_model(export_menu)
        hb.pack_end(export_btn)

        self.spinner = Gtk.Spinner()
        hb.pack_end(self.spinner)

        play_btn = self._toolbutton(
            "media-playback-start-symbolic", "Play (Ctrl+Return)"
        )
        play_btn.connect("clicked", self.action_play_stop)
        hb.pack_end(play_btn)
        self.play_btn = play_btn

        self.set_titlebar(hb)

    def _toolbutton(self, icon_name, tooltip):
        btn = Gtk.Button()
        btn.set_image(Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.BUTTON))
        btn.set_tooltip_text(tooltip)
        return btn

    def _build_body(self):
        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(root)

        # Error banner (hidden by default)
        self.error_bar = Gtk.InfoBar()
        self.error_bar.set_message_type(Gtk.MessageType.ERROR)
        self.error_bar.set_show_close_button(True)
        self.error_bar.connect("response", lambda b, r: self.hide_error())
        self.error_label = Gtk.Label(xalign=0)
        self.error_label.set_line_wrap(True)
        self.error_bar.get_content_area().pack_start(
            self.error_label, True, True, 0
        )
        self.error_revealer = Gtk.Revealer()
        self.error_revealer.set_transition_type(
            Gtk.RevealerTransitionType.SLIDE_DOWN
        )
        self.error_revealer.add(self.error_bar)
        root.pack_start(self.error_revealer, False, False, 0)

        paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        paned.set_position(800)
        root.pack_start(paned, True, True, 0)

        self.editor = Editor(on_changed=self._on_editor_changed)
        paned.pack1(self.editor, True, False)

        self.sidebar = Sidebar()
        paned.pack2(self.sidebar, False, False)

        # Status bar
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        status_box.set_border_width(6)
        self.status_label = Gtk.Label(label="Ready", xalign=0)
        self.status_label.get_style_context().add_class("dim-label")
        status_box.pack_start(self.status_label, True, True, 0)
        root.pack_start(Gtk.Separator(), False, False, 0)
        root.pack_start(status_box, False, False, 0)

    def _build_css(self):
        css = b"""
        .boxed-list { border-radius: 10px; }
        """
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        Gtk.StyleContext.add_provider_for_screen(
            Gdk.Screen.get_default(),
            provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    # -- helpers -------------------------------------------------------
    def set_status(self, text):
        self.status_label.set_text(text)

    def show_error(self, message, message_type=Gtk.MessageType.ERROR):
        self.error_bar.set_message_type(message_type)
        self.error_label.set_text(message)
        self.error_revealer.set_reveal_child(True)

    def hide_error(self):
        self.error_revealer.set_reveal_child(False)

    def set_busy(self, is_busy, status=None):
        self.busy = is_busy
        for w in (self.save_btn, self.play_btn):
            w.set_sensitive(not is_busy)
        if is_busy:
            self.spinner.start()
        else:
            self.spinner.stop()
        if status:
            self.set_status(status)

    def run_async(self, work, on_success, on_error):
        def worker():
            try:
                result = work()
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(on_error, exc)
            else:
                GLib.idle_add(on_success, result)

        threading.Thread(target=worker, daemon=True).start()

    def _update_title(self):
        name = self.current_path.name if self.current_path else "Untitled Song"
        prefix = "• " if self.editor.is_modified() else ""
        self.headerbar.set_title(f"{prefix}{name}")
        self.headerbar.set_subtitle(
            str(self.current_path.parent) if self.current_path else "Not saved yet"
        )

    def confirm_discard(self):
        if not self.editor.is_modified():
            return True
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.NONE,
            text="Discard unsaved changes?",
        )
        dialog.format_secondary_text(
            "Your current song has unsaved changes that will be lost."
        )
        dialog.add_buttons(
            "_Cancel", Gtk.ResponseType.CANCEL, "_Discard", Gtk.ResponseType.OK
        )
        discard_widget = dialog.get_widget_for_response(Gtk.ResponseType.OK)
        discard_widget.get_style_context().add_class("destructive-action")
        resp = dialog.run()
        dialog.destroy()
        return resp == Gtk.ResponseType.OK

    def _on_delete_event(self, *_a):
        return not self.confirm_discard()

    # -- analysis (parse the DSL text as the user types) ---------------
    def _on_editor_changed(self):
        self._update_title()
        if self._analyze_id:
            GLib.source_remove(self._analyze_id)
        self._analyze_id = GLib.timeout_add(450, self._do_analyze)

    def _do_analyze(self):
        self._analyze_id = None
        if load is None:
            return False
        text = self.editor.get_text()
        if not text.strip():
            self.song = None
            self.sidebar.clear()
            self.hide_error()
            self.set_status("Empty song")
            return False
        try:
            song = load(text)
        except Exception as exc:  # noqa: BLE001
            self.song = None
            self.sidebar.clear()
            self.show_error(str(exc))
            self.set_status("Parse error")
            return False
        self.song = song
        m = KEY_LINE_RE.search(text)
        key_str = m.group(1) if m else "—"
        self.sidebar.update(song, key_str, self.on_track_mute_toggle)
        self.hide_error()
        self.set_status(
            f"Parsed OK — {len(song.tracks)} track(s), {song.dur_secs():.1f}s"
        )
        return False

    def on_track_mute_toggle(self, index, muted):
        if self.song and 0 <= index < len(self.song.tracks):
            self.song.tracks[index].mute = muted

    # -- File actions ----------------------------------------------------
    def action_new(self, *_a):
        if not self.confirm_discard():
            return
        self.editor.set_text(DEFAULT_SONG)
        self.current_path = None
        self._update_title()
        self._do_analyze()

    def action_open(self, *_a):
        if not self.confirm_discard():
            return
        dialog = Gtk.FileChooserNative.new(
            "Open Song", self, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel"
        )
        f = Gtk.FileFilter()
        f.set_name("Music DSL files")
        f.add_pattern("*.music")
        dialog.add_filter(f)
        all_f = Gtk.FileFilter()
        all_f.set_name("All files")
        all_f.add_pattern("*")
        dialog.add_filter(all_f)
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            self._open_path(Path(dialog.get_filename()))
        dialog.destroy()

    def _open_path(self, path):
        try:
            text = path.read_text()
        except Exception as exc:  # noqa: BLE001
            self.show_error(f"Couldn't open {path.name}: {exc}")
            return
        self.editor.set_text(text)
        self.current_path = path
        self._update_title()
        self._do_analyze()
        self.set_status(f"Opened {path.name}")

    def action_save(self, *_a):
        if self.current_path is None:
            self.action_save_as()
            return
        self._write_to(self.current_path)

    def action_save_as(self, *_a):
        dialog = Gtk.FileChooserNative.new(
            "Save Song", self, Gtk.FileChooserAction.SAVE, "_Save", "_Cancel"
        )
        dialog.set_current_name(
            (self.current_path.name if self.current_path else "song.music")
        )
        f = Gtk.FileFilter()
        f.set_name("Music DSL files")
        f.add_pattern("*.music")
        dialog.add_filter(f)
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            path = Path(dialog.get_filename())
            if path.suffix != ".music":
                path = path.with_suffix(path.suffix + ".music") if path.suffix else path.with_suffix(".music")
            self._write_to(path)
        dialog.destroy()

    def _write_to(self, path):
        try:
            path.write_text(self.editor.get_text())
        except Exception as exc:  # noqa: BLE001
            self.show_error(f"Couldn't save {path.name}: {exc}")
            return
        self.current_path = path
        self.editor.set_modified(False)
        self._update_title()
        self.set_status(f"Saved {path.name}")

    # -- Playback ----------------------------------------------------------
    def action_play_stop(self, *_a):
        if self.playing:
            self._stop_playback()
        else:
            self._start_playback()

    def _start_playback(self):
        if self.song is None:
            self.show_error("Fix the errors in your song before playing it.")
            return
        self.playing = True
        self.play_btn.set_image(
            Gtk.Image.new_from_icon_name(
                "media-playback-stop-symbolic", Gtk.IconSize.BUTTON
            )
        )
        self.play_btn.set_tooltip_text("Stop playback")
        self.spinner.start()
        self.set_status("Playing…")
        song = self.song

        def worker():
            try:
                song.play(wait=True)
            except Exception as exc:  # noqa: BLE001
                GLib.idle_add(self.show_error, f"Playback failed: {exc}")
            finally:
                GLib.idle_add(self._finish_playback)

        threading.Thread(target=worker, daemon=True).start()

    def _stop_playback(self):
        if _sd is not None:
            try:
                _sd.stop()
            except Exception:  # noqa: BLE001
                pass
        else:
            self.set_status(
                "Stop isn't available with the current audio backend — "
                "let the song finish playing."
            )

    def _finish_playback(self):
        self.playing = False
        self.play_btn.set_image(
            Gtk.Image.new_from_icon_name(
                "media-playback-start-symbolic", Gtk.IconSize.BUTTON
            )
        )
        self.play_btn.set_tooltip_text("Play")
        self.spinner.stop()
        self.set_status("Ready")
        return False

    # -- Export / Import ---------------------------------------------------
    def action_export_wav(self, *_a):
        if self.song is None:
            self.show_error("Fix the errors in your song before exporting.")
            return
        dialog = Gtk.FileChooserNative.new(
            "Export to WAV", self, Gtk.FileChooserAction.SAVE, "_Export", "_Cancel"
        )
        dialog.set_current_name(f"{self.song.name or 'song'}.wav")
        f = Gtk.FileFilter()
        f.set_name("WAV audio")
        f.add_pattern("*.wav")
        dialog.add_filter(f)
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            if not path.lower().endswith(".wav"):
                path += ".wav"
            song = self.song
            self.set_busy(True, "Exporting WAV…")
            self.run_async(
                lambda: song.save(path),
                lambda _r: self.set_busy(False, f"Exported to {Path(path).name}"),
                lambda exc: (
                    self.set_busy(False, "Ready"),
                    self.show_error(f"Export failed: {exc}"),
                ),
            )
        dialog.destroy()

    def action_export_midi(self, *_a):
        if self.song is None:
            self.show_error("Fix the errors in your song before exporting.")
            return
        dialog = Gtk.FileChooserNative.new(
            "Export to MIDI", self, Gtk.FileChooserAction.SAVE, "_Export", "_Cancel"
        )
        dialog.set_current_name(f"{self.song.name or 'song'}.mid")
        f = Gtk.FileFilter()
        f.set_name("Standard MIDI files")
        f.add_pattern("*.mid")
        f.add_pattern("*.midi")
        dialog.add_filter(f)
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            if not path.lower().endswith((".mid", ".midi")):
                path += ".mid"
            song = self.song
            self.set_busy(True, "Exporting MIDI…")
            self.run_async(
                lambda: song.to_midi(path),
                lambda _r: self.set_busy(False, f"Exported to {Path(path).name}"),
                lambda exc: (
                    self.set_busy(False, "Ready"),
                    self.show_error(f"Export failed: {exc}"),
                ),
            )
        dialog.destroy()

    def action_import_midi(self, *_a):
        if midi_to_song is None:
            self.show_error("The 'music' package isn't available.")
            return
        if not self.confirm_discard():
            return
        dialog = Gtk.FileChooserNative.new(
            "Import MIDI File", self, Gtk.FileChooserAction.OPEN, "_Open", "_Cancel"
        )
        f = Gtk.FileFilter()
        f.set_name("MIDI files")
        f.add_pattern("*.mid")
        f.add_pattern("*.midi")
        dialog.add_filter(f)
        resp = dialog.run()
        if resp == Gtk.ResponseType.ACCEPT:
            path = dialog.get_filename()
            self.set_busy(True, "Importing MIDI…")

            def work():
                song = midi_to_song(path)
                return song_to_text(song)

            def done(text):
                self.editor.set_text(text)
                self.current_path = None
                self.editor.set_modified(True)
                self._update_title()
                self._do_analyze()
                self.set_busy(False, f"Imported {Path(path).name}")

            def fail(exc):
                self.set_busy(False, "Ready")
                self.show_error(f"Couldn't import MIDI: {exc}")

            self.run_async(work, done, fail)
        dialog.destroy()


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------
class MusicDSLApplication(Gtk.Application):
    def __init__(self):
        super().__init__(
            application_id=APP_ID,
            flags=Gio.ApplicationFlags.HANDLES_OPEN,
        )
        self.window = None

    def do_startup(self):
        Gtk.Application.do_startup(self)

        actions = {
            "new": lambda *a: self.window.action_new(),
            "open": lambda *a: self.window.action_open(),
            "save": lambda *a: self.window.action_save(),
            "save_as": lambda *a: self.window.action_save_as(),
            "play_stop": lambda *a: self.window.action_play_stop(),
            "export_wav": lambda *a: self.window.action_export_wav(),
            "export_midi": lambda *a: self.window.action_export_midi(),
            "import_midi": lambda *a: self.window.action_import_midi(),
            "about": self.on_about,
            "shortcuts": self.on_shortcuts,
            "quit": lambda *a: self.quit(),
        }
        for name, handler in actions.items():
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        self.set_accels_for_action("app.new", ["<Ctrl>n"])
        self.set_accels_for_action("app.open", ["<Ctrl>o"])
        self.set_accels_for_action("app.save", ["<Ctrl>s"])
        self.set_accels_for_action("app.save_as", ["<Ctrl><Shift>s"])
        self.set_accels_for_action("app.play_stop", ["<Ctrl>Return"])
        self.set_accels_for_action("app.quit", ["<Ctrl>q"])

    def do_activate(self):
        if self.window is None:
            self.window = MusicDSLWindow(self)
        self.window.present()

    def do_open(self, files, n_files, hint):
        if self.window is None:
            self.window = MusicDSLWindow(self)
        if n_files:
            path = Path(files[0].get_path())
            self.window._open_path(path)
        self.window.present()

    def on_about(self, *_a):
        dialog = Gtk.AboutDialog(transient_for=self.window, modal=True)
        dialog.set_program_name(APP_NAME)
        dialog.set_logo_icon_name("audio-x-generic")
        dialog.set_version("1.0")
        dialog.set_comments(
            "A GNOME front end for Music-DSL — write music as text, "
            "play it instantly, and export to WAV or MIDI."
        )
        dialog.set_website("https://github.com/enginestein/Music-DSL")
        dialog.set_website_label("Music-DSL on GitHub")
        dialog.set_license_type(Gtk.License.MIT_X11)
        dialog.run()
        dialog.destroy()

    def on_shortcuts(self, *_a):
        text = (
            "Ctrl+N — New song\n"
            "Ctrl+O — Open song\n"
            "Ctrl+S — Save\n"
            "Ctrl+Shift+S — Save As\n"
            "Ctrl+Return — Play / Stop\n"
            "Ctrl+Q — Quit"
        )
        dialog = Gtk.MessageDialog(
            transient_for=self.window,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text="Keyboard Shortcuts",
        )
        dialog.format_secondary_text(text)
        dialog.run()
        dialog.destroy()


def main():
    app = MusicDSLApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
