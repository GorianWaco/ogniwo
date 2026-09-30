#!/usr/bin/env bash
set -euo pipefail

APP_ID="pl.gorian.Ogniwo"
MODE="user"
if [[ "${1:-}" == "--system" ]]; then
  MODE="system"
elif [[ -n "${1:-}" ]]; then
  echo "Użycie: $0 [--system]" >&2
  exit 1
fi

if [[ "$MODE" == "system" ]]; then
  PREFIX="/usr/local"
else
  PREFIX="${HOME}/.local"
fi

rm -rf "${PREFIX}/share/ogniwo"
rm -f "${PREFIX}/bin/ogniwo"
rm -f "${PREFIX}/share/applications/${APP_ID}.desktop"
rm -f "${PREFIX}/share/icons/hicolor/scalable/apps/${APP_ID}.svg"
if [[ "$MODE" == "user" ]]; then
  rm -f "${HOME}/.config/autostart/${APP_ID}.desktop"
fi

echo "Usunięto Ogniwo z ${PREFIX}."
echo "Zostały ustawienia w ~/.config/ogniwo i kopia ~/.config/openrazer/razer.conf.bak-ogniwo."
