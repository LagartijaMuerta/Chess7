"""led_control.py
Ansteuerung von zwei NeoPixel‑Streifen (GPIO 12 und GPIO 13).

Konzept:
- field_leds.csv / FieldConfig.FIELD_STATIC enthält für jedes Feld zwei Gruppen
  (LED_group_1 = Ecken, LED_group_2 = Seitenmitten). Jede Gruppe ist eine
  Liste von Paaren [index, gpio_pin].
- Über GPIO 12 sind 104 LEDs angeschlossen, über GPIO 13 sind 121 LEDs.
- Die Feld‑Grundfarbe (light/dark) wird auf alle LEDs des Felds gesetzt.
- Highlight‑Zustände: "move" -> LED_group_1; "selected","capture","invalid" -> LED_group_2

Dieses Modul verwendet die CircuitPython NeoPixel API (neopixel + board).
Falls die Bibliothek nicht installiert ist, läuft eine Simulations‑Fallback.
"""

from typing import Tuple, Dict, List, Optional
import logging
import os

try:
    import board
    import neopixel
    _HARDWARE_AVAILABLE = True
except Exception:
    board = None
    neopixel = None
    _HARDWARE_AVAILABLE = False

from . import FieldConfig

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())

# Default pins / lengths
PIN_1 = 12
PIN_2 = 13
LEN_1 = 104
LEN_2 = 121

# Channel mapping: CSV channelID -> hardware strip
# Channel 1 -> GPIO 12 (strip1), Channel 2 -> GPIO 13 (strip2)
# pair format in CSV: [ledIndex, channelID]

# explicit channel map: CSV channelID -> internal channel number (1 or 2)
CHANNEL_MAP = {
    1: 1,
    2: 2,
}


def _to_color_tuple(col) -> Tuple[int, int, int]:
    """Sichere Konvertierung in (r,g,b) (0-255)."""
    if isinstance(col, tuple) and len(col) == 3:
        return tuple(int(max(0, min(255, c))) for c in col)
    # falls Farben als Namen übergeben werden: einfache mapping
    return (0, 0, 0)


class _FakeStrip:
    def __init__(self, n: int):
        self.n = n
        self.pixels = [(0, 0, 0)] * n

    def __setitem__(self, idx: int, color: Tuple[int, int, int]):
        if 0 <= idx < self.n:
            self.pixels[idx] = color

    def show(self):
        # Simpler Debug‑Ausgabe
        LOGGER.debug("FakeStrip show: %d pixels", self.n)

    def fill(self, color: Tuple[int, int, int]):
        self.pixels = [color] * self.n


class LEDController:
    """Steuert zwei NeoPixel‑Strips entsprechend der FieldConfig.

    Usage:
      ctl = LEDController()
      ctl.initialize()  # optional Parameter für Pins/Längen
      ctl.clear()
      ctl.set_field_state('d2','selected')
      ctl.show()
    """

    def __init__(self, pin1: int = PIN_1, len1: int = LEN_1, pin2: int = PIN_2, len2: int = LEN_2, brightness: float = 1.0):
        self.pin1 = pin1
        self.len1 = len1
        self.pin2 = pin2
        self.len2 = len2
        # overall hardware brightness kept at 1.0; per-color brightness applied when setting pixels
        self.brightness = float(brightness)

        # user requested brightness levels
        self.base_brightness = 0.25  # 25% for base field color
        self.highlight_brightness = 0.5  # 50% for highlights

        self.strip1 = None
        self.strip2 = None

        # Aktueller Puffer (für Simulation oder Batch‑Updates)
        self._buf1: List[Tuple[int, int, int]] = [(0, 0, 0)] * self.len1
        self._buf2: List[Tuple[int, int, int]] = [(0, 0, 0)] * self.len2

        # Mapping aus FieldConfig
        self.field_map = FieldConfig.FIELD_STATIC

        # Standardfarben (Grundfarbe light/dark) — laut Anforderung beides weiß
        self.base_light = (255, 255, 255)
        self.base_dark = (255, 255, 255)

    def initialize(self, auto_init: bool = True):
        """Initialisiert die Hardware‑Strips. Wenn libs fehlen, nutzt Fallback."""
        # refresh mapping from FieldConfig in case CSV was reloaded after import
        try:
            # reload FieldConfig to pick up changes to CSV made at runtime
            import importlib
            import RaspberryChessBoard.FieldConfig as FC
            importlib.reload(FC)
            self.field_map = FC.FIELD_STATIC
        except Exception:
            try:
                self.field_map = FieldConfig.FIELD_STATIC
            except Exception:
                self.field_map = {}

        # If FieldConfig didn't provide data (e.g., not yet parsed), try to parse CSV directly
        if not self.field_map:
            try:
                import csv, ast
                module_dir = os.path.dirname(__file__)
                csv_path = os.path.join(module_dir, 'field_leds.csv')
                if os.path.exists(csv_path):
                    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
                        sn = csv.Sniffer()
                        sample = f.read(2048)
                        f.seek(0)
                        try:
                            dialect = sn.sniff(sample)
                        except Exception:
                            dialect = csv.excel
                        reader = csv.DictReader(f, dialect=dialect)
                        # normalize headers
                        if reader.fieldnames:
                            reader.fieldnames = [fn.lstrip('\ufeff').strip() for fn in reader.fieldnames]
                        # try semicolon fallback
                        if not reader.fieldnames or 'coord' not in [fn.lower() for fn in (reader.fieldnames or [])]:
                            f.seek(0)
                            reader = csv.DictReader(f, delimiter=';')
                        # detect header names
                        actual_names = {fn.lower(): fn for fn in (reader.fieldnames or [])}
                        def find_header(token):
                            token = token.lower().replace('_', '').replace(' ', '')
                            for low, orig in actual_names.items():
                                key = low.replace('_', '').replace(' ', '')
                                if token in key or key in token:
                                    return orig
                            return None
                        hdr_coord = find_header('coord') or (reader.fieldnames[0] if reader.fieldnames else 'coord')
                        hdr_g1 = find_header('led_group_1') or reader.fieldnames[1]
                        hdr_g2 = find_header('led_group_2') or reader.fieldnames[2]
                        hdr_color = find_header('fieldcolor') or None
                        fm = {}
                        for row in reader:
                            coord = (row.get(hdr_coord) or '').strip()
                            if not coord or len(coord) != 2:
                                continue
                            try:
                                g1_raw = (row.get(hdr_g1) or '').strip()
                                g2_raw = (row.get(hdr_g2) or '').strip()
                                g1 = ast.literal_eval(g1_raw) if g1_raw else None
                                g2 = ast.literal_eval(g2_raw) if g2_raw else None
                                # normalize to lists of [index,channel]
                                g1_list = [[int(x[0]), int(x[1])] for x in g1] if g1 else [[0,1]]*4
                                g2_list = [[int(x[0]), int(x[1])] for x in g2] if g2 else [[0,1]]*4
                                color = (row.get(hdr_color) or '').strip().lower() if hdr_color else 'light'
                                if color not in ('light','dark'):
                                    color = 'light'
                                fm[coord] = {'LED_group_1': g1_list, 'LED_group_2': g2_list, 'fieldColor': color}
                            except Exception:
                                continue
                        if fm:
                            self.field_map = fm
            except Exception:
                pass
        if _HARDWARE_AVAILABLE and auto_init:
            try:
                # board pin Namen wie board.D12/board.D13
                pin_obj1 = getattr(board, f"D{self.pin1}", None)
                pin_obj2 = getattr(board, f"D{self.pin2}", None)
                if pin_obj1 is None or pin_obj2 is None:
                    raise RuntimeError("Board pins nicht verfügbar (board.D12/13 nicht gefunden)")
                # set hardware brightness to 1.0 and apply per-color scaling in software
                self.strip1 = neopixel.NeoPixel(pin_obj1, self.len1, brightness=1.0, auto_write=False)
                self.strip2 = neopixel.NeoPixel(pin_obj2, self.len2, brightness=1.0, auto_write=False)
                LOGGER.info("Neopixel Strips initialisiert: D%d (%d), D%d (%d)", self.pin1, self.len1, self.pin2, self.len2)
            except Exception as e:
                LOGGER.warning("Fehler beim Initialisieren von NeoPixel, fallback: %s", e)
                self.strip1 = _FakeStrip(self.len1)
                self.strip2 = _FakeStrip(self.len2)
        else:
            # Simulation
            LOGGER.info("Hardware nicht verfügbar, verwende FakeStrip (Simulation)")
            self.strip1 = _FakeStrip(self.len1)
            self.strip2 = _FakeStrip(self.len2)

        # setze initial alle Felder auf Grundfarbe
        self._apply_base_colors()
        self.show()

    def _apply_base_colors(self):
        # Set only LED_group_1 to base color; LED_group_2 remains off
        off = (0, 0, 0)
        for coord, entry in self.field_map.items():
            base = entry.get('fieldColor')
            col = self.base_light if base == 'light' else self.base_dark
            # group 1 -> base color
            for pair in entry.get('LED_group_1', []):
                try:
                    idx0 = int(pair[0])  # CSV provides 0-based index
                    channel = int(pair[1])
                except Exception:
                    continue
                # apply scaled base color
                scaled = tuple(int(max(0, min(255, round(c * self.base_brightness)))) for c in col)
                self._set_pixel_buffer(channel, idx0, scaled)
            # group 2 -> off
            for pair in entry.get('LED_group_2', []):
                try:
                    idx0 = int(pair[0])
                    channel = int(pair[1])
                except Exception:
                    continue
                self._set_pixel_buffer(channel, idx0, off)

    def _set_pixel_buffer(self, channel: int, index0: int, color: Tuple[int, int, int]):
        """Setzt Farbe in internen Puffer.

        channel: CSV channelID (1 => strip1 (GPIO12), 2 => strip2 (GPIO13))
        index0: 0-basierter LED‑Index auf dem jeweiligen Strip
        """
        idx0 = int(index0)
        mapped = CHANNEL_MAP.get(int(channel))
        if mapped is None:
            LOGGER.debug("Unmapped channel %s for idx %s on field", channel, index0)
            return
        if mapped == 1:
            if 0 <= idx0 < self.len1:
                self._buf1[idx0] = _to_color_tuple(color)
            else:
                LOGGER.debug("Index %d außerhalb von strip1 (len=%d)", idx0, self.len1)
        elif mapped == 2:
            if 0 <= idx0 < self.len2:
                self._buf2[idx0] = _to_color_tuple(color)
            else:
                LOGGER.debug("Index %d außerhalb von strip2 (len=%d)", idx0, self.len2)
        else:
            LOGGER.debug("Mapped channel %s not supported for idx %s", mapped, index0)

    def _set_field_pixels(self, coord: str, color: Tuple[int, int, int], both_groups: bool = False):
        """Setzt Pixel für ein Feld; wenn both_groups True werden LED_group_1 und _2 gesetzt."""
        coord = coord.strip()
        entry = self.field_map.get(coord)
        if not entry:
            LOGGER.debug("Feld %s nicht in FieldConfig", coord)
            return
        groups = []
        if both_groups:
            groups = [entry.get('LED_group_1', []), entry.get('LED_group_2', [])]
        else:
            # Standard: move -> group1, others -> group2
            # Der Aufrufer entscheidet welche Gruppe er möchte. Diese Funktion ist generisch.
            groups = [entry.get('LED_group_1', []), entry.get('LED_group_2', [])]
        # wenn both_groups True, beide nutzen; andernfalls caller filtert
        for g in groups:
            for pair in g:
                try:
                    idx = int(pair[0])
                    channel = int(pair[1])
                except Exception:
                    continue
                self._set_pixel_buffer(channel, idx, color)

    def set_field_state(self, coord: str, state: str):
        """Setzt ein Feld in einen Highlight‑Zustand.

        state in: 'selected','move','capture','invalid' oder 'base' (setzt Grundfarbe)
        """
        coord = coord.strip()
        entry = self.field_map.get(coord)
        if not entry:
            return

        def apply_and_scale(pairs, brightness_factor: float, color_tuple: Tuple[int, int, int]):
            scaled = tuple(int(max(0, min(255, round(c * brightness_factor)))) for c in color_tuple)
            for pair in pairs:
                try:
                    idx = int(pair[0])
                    channel = int(pair[1])
                except Exception:
                    continue
                self._set_pixel_buffer(channel, idx, scaled)

        if state == 'base':
            base = entry.get('fieldColor')
            col = self.base_light if base == 'light' else self.base_dark
            # LED_group_1 -> base color at base_brightness
            apply_and_scale(entry.get('LED_group_1', []), self.base_brightness, col)
            # LED_group_2 -> turned off
            off = (0, 0, 0)
            apply_and_scale(entry.get('LED_group_2', []), 1.0, off)
            # sofort anzeigen
            self.show()
            return

        rgb = FieldConfig.get_highlight_color(state)
        if state == 'move':
            apply_and_scale(entry.get('LED_group_1', []), self.highlight_brightness, rgb)
        else:
            # selected, capture, invalid -> LED_group_2
            apply_and_scale(entry.get('LED_group_2', []), self.highlight_brightness, rgb)
            # Wenn LED_group_2 eine Farbe erhält (nicht 'move'), schalte LED_group_1 aus für dieses Feld.
            # Ausnahme: falls die gesetzte Farbe genau die 'move' Farbe ist, dann nicht ausschalten.
            move_raw = FieldConfig.get_highlight_color('move')
            if rgb != move_raw:
                off = (0, 0, 0)
                # set group1 LEDs of this field to off, BUT only when no other highlight
                # currently drives that LED (dominance rule). If the buffer already
                # contains a non-base color (e.g., another field's move highlight), leave it.
                # Compute this field's scaled base color for comparison
                base = entry.get('fieldColor')
                base_col = self.base_light if base == 'light' else self.base_dark
                base_scaled = tuple(int(max(0, min(255, round(c * self.base_brightness)))) for c in base_col)
                for pair in entry.get('LED_group_1', []):
                    try:
                        idx = int(pair[0])
                        channel = int(pair[1])
                    except Exception:
                        continue
                    # read current buffer color
                    curr = (0, 0, 0)
                    if channel == 1:
                        if 0 <= idx < self.len1:
                            curr = self._buf1[idx]
                    elif channel == 2:
                        if 0 <= idx < self.len2:
                            curr = self._buf2[idx]
                    # only turn off if current color equals the base color (i.e., not claimed by another highlight)
                    if curr == base_scaled:
                        self._set_pixel_buffer(channel, idx, off)

        # sofort anzeigen nach Änderung
        self.show()

    def show(self):
        """Schreibt den internen Puffer auf die Hardware (oder Sim)."""
        # Übertragen auf Strip1
        if self.strip1 is None or self.strip2 is None:
            LOGGER.debug("Strip noch nicht initialisiert, rufe initialize() auf")
            return
        # set pixels
        if isinstance(self.strip1, _FakeStrip):
            self.strip1.pixels = list(self._buf1)
            self.strip1.show()
        else:
            for i, c in enumerate(self._buf1):
                self.strip1[i] = c
            try:
                self.strip1.show()
            except Exception as e:
                LOGGER.warning("Fehler beim Schreiben strip1: %s", e)

        if isinstance(self.strip2, _FakeStrip):
            self.strip2.pixels = list(self._buf2)
            self.strip2.show()
        else:
            for i, c in enumerate(self._buf2):
                self.strip2[i] = c
            try:
                self.strip2.show()
            except Exception as e:
                LOGGER.warning("Fehler beim Schreiben strip2: %s", e)

    def clear(self):
        self._buf1 = [(0, 0, 0)] * self.len1
        self._buf2 = [(0, 0, 0)] * self.len2
        self.show()


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    ctl = LEDController()
    ctl.initialize(auto_init=False)  # in tests nutze Simulation
    # Beispiel: setze d2 als selected, d4 als move
    ctl.set_field_state('d2', 'selected')
    ctl.set_field_state('d4', 'move')
    ctl.show()


# Module level default controller (created lazily)
DEFAULT_CONTROLLER: Optional[LEDController] = None


def get_default_controller() -> LEDController:
    """Gibt den Modul‑Default LEDController zurück (lazy instantiation)."""
    global DEFAULT_CONTROLLER
    if DEFAULT_CONTROLLER is None:
        DEFAULT_CONTROLLER = LEDController()
    return DEFAULT_CONTROLLER
