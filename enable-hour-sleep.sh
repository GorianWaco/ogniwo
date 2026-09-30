#!/usr/bin/env bash
# Podnosi limit uśpienia OpenRazera z 15 minut do 60 i przebudowuje moduł.
# Uruchom: sudo ./enable-hour-sleep.sh
set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Potrzebny root: sudo $0" >&2
  exit 1
fi

SRC="/usr/src/openrazer-driver-3.12.4/driver/razerchromacommon.c"
if [[ ! -f "$SRC" ]]; then
  echo "Brak źródeł OpenRazer: $SRC" >&2
  exit 1
fi

python3 - "$SRC" << 'PY'
import pathlib, sys
path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = "idle_time = clamp_u16(idle_time, 60, 900);"
new = "idle_time = clamp_u16(idle_time, 60, 3600);"
if new in text:
    print("Limit 3600 s już jest w źródle.")
elif old not in text:
    raise SystemExit("Nie znalazłem clamp_u16(..., 60, 900) w sterowniku.")
else:
    text = text.replace(old, new, 1)
    text = text.replace("must be between 60sec-900sec", "must be between 60sec-3600sec", 1)
    path.write_text(text, encoding="utf-8")
    print("Źródło: czas uśpienia do 3600 s.")
PY

dkms install "openrazer-driver/3.12.4" --force
if modprobe -r razermouse; then
  modprobe razermouse
  echo "Moduł myszy przeładowany. W Ogniwie ustaw czas do 60 minut."
else
  echo "Moduł jest w użyciu. Po restarcie komputera limit godziny zacznie działać."
fi
