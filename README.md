# Ogniwo

Poziom baterii myszy Razer w trayu GNOME i własny próg powiadomienia.

OpenRazer na tym komputerze wysyłał ostrzeżenie co 10 minut, gdy bateria była na 33% albo niżej. Ogniwo ten mechanizm wyłącza. Od tego momentu godzinę i procent ustawiasz w oknie.

Mysz Naga V2 HyperSpeed pokazuje poziom przez sterownik OpenRazer (surowa wartość 0–255, przeliczana na procent). Nie zgłasza, czy stoi na ładowarce — widać sam poziom.

## Co jest w oknie

- Duży procent i pasek.
- Włącznik powiadomienia i próg (domyślnie 15%).
- Jedno powiadomienie na zejście poniżej progu. Kolejne dopiero, gdy bateria wróci o 5 punktów ponad próg i znów spadnie.
- Opcjonalne przypominanie co kilka minut, dopóki poziom zostaje nisko.
- Wyciszenie na godzinę albo na 4 godziny.
- Po ilu minutach mysz ma się wyłączyć (1–60, domyślnie 5). To ten sam czas, który Razer trzyma w `device_idle_time`. Sam sterownik OpenRazer 3.12 obcina polecenie do 15 minut, dopóki nie podniesiesz limitu: `sudo ./enable-hour-sleep.sh`.
- Gdy mysz zaśnie, ikona i okno chowają procent. Ogniwo nie odpytuje wtedy baterii, bo odczyt budzi mysz. Ruch myszą przywraca poziom.
- Co ile sekund odświeżać poziom, kiedy mysz jest w użyciu (domyślnie 60).

Ikona w panelu to liczba procentów, dopóki mysz nie śpi. Po uśpieniu jest napis „wył”, bez liczby. Kolor zielony, bursztynowy albo czerwony mówi, czy jesteś nad progiem. Najazd pokazuje nazwę myszy. Tray Icons Reloaded musi być włączone — tak jak przy Focusrite Monitor.

Zamknięcie okna zostawia ikonę. Kończysz z menu ikony albo przyciskiem **Zakończ**.

## Instalacja

```bash
git clone https://github.com/GorianWaco/ogniwo.git ~/Projekty/ogniwo
~/Projekty/ogniwo/install.sh
```

| Co | Gdzie |
|----|--------|
| Program | `~/.local/share/ogniwo/` |
| Polecenie | `ogniwo` |
| Menu | Ogniwo |
| Ustawienia | `~/.config/ogniwo/config.json` |
| Autostart | po zalogowaniu, sama ikona |

Przy pierwszym uruchomieniu Ogniwo zapisuje w `~/.config/openrazer/razer.conf` `battery_notifier = False`, robi kopię `razer.conf.bak-ogniwo` i restartuje daemon OpenRazer oraz Razer Reactive. Podświetlenie klawiatury może na moment zgasnąć.

Żeby z powrotem oddać powiadomienia OpenRazerowi, ustaw `battery_notifier = True` w tym pliku i zrestartuj `openrazer-daemon.service`.

## Wymagania

Jesteś w grupie `openrazer`. Działają `openrazer-daemon`, GTK4, libadwaita, GTK3 (ikona) i `notify-send`.
