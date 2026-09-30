#!/usr/bin/env bash
# Instalator Ogniwa — domyślnie do katalogu użytkownika.

set -euo pipefail

APP_ID="pl.gorian.Ogniwo"
APP_NAME="Ogniwo"
VERSION="$(cat "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/VERSION")"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MODE="user"
PREFIX=""

usage() {
  cat <<EOF
Użycie: $0 [opcje]

  (domyślnie)   Instalacja dla użytkownika (~/.local)
  --system      Instalacja do /usr/local (wymaga root)
  -h, --help    Ta pomoc
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --system) MODE="system"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Nieznana opcja: $1" >&2; usage >&2; exit 1 ;;
  esac
done

if [[ "$MODE" == "system" ]]; then
  if [[ "$(id -u)" -ne 0 ]]; then
    echo "Instalacja systemowa wymaga root: sudo $0 --system" >&2
    exit 1
  fi
  PREFIX="/usr/local"
else
  PREFIX="${HOME}/.local"
fi

BIN_DIR="${PREFIX}/bin"
APP_DIR="${PREFIX}/share/ogniwo"
DESKTOP_DIR="${PREFIX}/share/applications"
ICON_DIR="${PREFIX}/share/icons/hicolor/scalable/apps"

echo "==> ${APP_NAME} v${VERSION}"
echo "    prefiks: ${PREFIX}"

missing=()
python3 -c "import gi; gi.require_version('Gtk','4.0'); gi.require_version('Adw','1')" 2>/dev/null \
  || missing+=("gtk4 + libadwaita + python-gobject")
python3 -c "import gi, cairo; gi.require_version('Gtk','3.0')" 2>/dev/null \
  || missing+=("gtk3 + python-cairo")
command -v notify-send >/dev/null 2>&1 || missing+=("libnotify")
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "Brakuje zależności:"
  for item in "${missing[@]}"; do echo "  - ${item}"; done
  echo "Arch/CachyOS: sudo pacman -S python-gobject python-cairo gtk4 libadwaita gtk3 libnotify"
  exit 1
fi

rm -rf "${APP_DIR}"
mkdir -p "${APP_DIR}/ogniwo" "${BIN_DIR}" "${DESKTOP_DIR}" "${ICON_DIR}"
cp "${SCRIPT_DIR}/src/ogniwo/"*.py "${APP_DIR}/ogniwo/"
install -m 755 "${SCRIPT_DIR}/src/tray_helper.py" "${APP_DIR}/tray_helper.py"
install -m 644 "${SCRIPT_DIR}/icons/ogniwo.svg" "${ICON_DIR}/${APP_ID}.svg"
install -m 644 "${SCRIPT_DIR}/README.md" "${APP_DIR}/README.md"

cat > "${BIN_DIR}/ogniwo" <<EOF
#!/usr/bin/env bash
export PYTHONPATH="${APP_DIR}\${PYTHONPATH:+:\$PYTHONPATH}"
exec python3 -m ogniwo "\$@"
EOF
chmod 755 "${BIN_DIR}/ogniwo"

cat > "${DESKTOP_DIR}/${APP_ID}.desktop" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=${APP_NAME}
GenericName=Bateria myszy
Comment=Poziom baterii myszy w trayu i próg powiadomienia
Exec=${BIN_DIR}/ogniwo
Icon=${APP_ID}
Terminal=false
Categories=Settings;Hardware;
Keywords=bateria;mysz;razer;naga;tray;powiadomienie;
StartupNotify=true
StartupWMClass=ogniwo
X-GNOME-UsesNotifications=true
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "${DESKTOP_DIR}" 2>/dev/null || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1 && [[ -w "${PREFIX}/share/icons/hicolor" ]]; then
  gtk-update-icon-cache -f -t "${PREFIX}/share/icons/hicolor" 2>/dev/null || true
fi

if [[ "$MODE" == "user" ]]; then
  AUTOSTART_DIR="${HOME}/.config/autostart"
  mkdir -p "${AUTOSTART_DIR}"
  cat > "${AUTOSTART_DIR}/${APP_ID}.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=${APP_NAME}
GenericName=Bateria myszy
Comment=Poziom baterii myszy w trayu i próg powiadomienia
Exec=${BIN_DIR}/ogniwo --background
Icon=${APP_ID}
Terminal=false
Categories=Settings;Hardware;
X-GNOME-Autostart-enabled=true
X-GNOME-Autostart-Delay=4
EOF
fi

echo
echo "Zainstalowano ${APP_NAME} v${VERSION}"
echo "  Uruchom:  ogniwo"
echo "  Pliki:    ${APP_DIR}"
echo
