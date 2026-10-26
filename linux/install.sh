#!/usr/bin/env bash
# Installs Pulse for the current user (no root).   ./install.sh            install / update
#                                                  ./install.sh --uninstall
# Needs python3 with PyGObject + Cairo + GTK 3 (preinstalled on DGX OS / Ubuntu desktop):
#   sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0
set -e
cd "$(dirname "$0")"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
APP="$DATA/pulse"
BIN="$HOME/.local/bin/pulse"
DESKTOP="$DATA/applications/pulse.desktop"
ICON_DIR="$DATA/icons/hicolor/512x512/apps"
AUTOSTART="${XDG_CONFIG_HOME:-$HOME/.config}/autostart/pulse.desktop"

if [[ "$1" == "--uninstall" ]]; then
  pkill -f "python3 -m pulse" 2>/dev/null || true
  rm -rf "$APP" "$BIN" "$DESKTOP" "$ICON_DIR/pulse.png" "$AUTOSTART"
  echo "Pulse removed. Settings stay in ~/.config/pulse (delete it if you like)."
  exit 0
fi

if ! python3 -c "import gi, cairo; gi.require_version('Gtk','3.0'); from gi.repository import Gtk, Gdk" 2>/dev/null; then
  echo "Missing GTK 3 bindings for python3. Install them with:" >&2
  echo "  sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-3.0" >&2
  exit 1
fi

SRC=pulse; [[ -d "$SRC" ]] || { echo "run this from the linux/ folder (or the unpacked tarball)"; exit 1; }
ICON=icon.png; [[ -f "$ICON" ]] || ICON=../assets/icon-512.png

rm -rf "$APP"; mkdir -p "$APP" "$(dirname "$BIN")" "$(dirname "$DESKTOP")" "$ICON_DIR"
cp -r "$SRC" "$APP/pulse"
find "$APP" -name __pycache__ -prune -exec rm -rf {} +
cp "$ICON" "$ICON_DIR/pulse.png"

cat > "$BIN" <<LAUNCH
#!/usr/bin/env bash
cd "$APP" && exec python3 -m pulse "\$@"
LAUNCH
chmod +x "$BIN"

cat > "$DESKTOP" <<DESK
[Desktop Entry]
Type=Application
Name=Pulse
Comment=Pixel system monitor with Claude Code usage
Exec=$BIN
Icon=pulse
Categories=System;Monitor;
StartupNotify=false
DESK

command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "$DATA/icons/hicolor" 2>/dev/null || true
echo "Installed. Start it with:  pulse      (or find Pulse in your app grid)"
case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) echo "Note: add ~/.local/bin to your PATH to use the 'pulse' command." ;; esac
echo "Right-click the widget → Launch at Login to start it with your session."
