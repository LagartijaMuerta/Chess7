# FieldConfig.py
# Lädt statische Feld‑Zuweisungen (LED‑Gruppen + Grundfarbe) aus CSV.
# Erwartetes CSV-Format (Header): coord,LED_group_1,LED_group_2[,fieldColor]
# LED_group_* Spalten enthalten Python‑listen, z.B. [[1,1],[3,1],[3,2],[1,2]]

import os
import csv
import ast

FILES = "abcdefgh"

# Highlight‑Zustände als RGB‑Tuples
HIGHLIGHT_COLORS = {
    # Auswahl der eigenen Figur
    "selected": (0, 0, 255),         # blau
    # Normale gültige Züge
    "move": (255, 255, 0),           # gelb
    # Capture / Feld mit gegnerischer Figur
    "capture": (0, 255, 0),          # grün
    # Ungültige Auswahl (muss erst zurückgesetzt werden)
    "invalid": (255, 0, 0),          # rot
    # Board base colors (falls UI benötigt, z.B. erase overlay)
    "default_light": (255, 255, 255),
    "default_dark": (128, 128, 128),
}

def get_highlight_color(state: str):
    """
    Rückgabe: RGB‑Triple (r,g,b) für einen Highlight‑Zustand.
    Erwartete states: 'selected','move','capture','invalid','default_light','default_dark'
    Falls unbekannt, wird (0,0,0) zurückgegeben.
    """
    return HIGHLIGHT_COLORS.get(state, (0, 0, 0))

# Default‑Eintrag
def _default_field_entry(row, col):
    base_color = "light" if ((row + col) % 2 == 0) else "dark"
    return {
        "LED_group_1": [[0, 0], [0, 0], [0, 0], [0, 0]],
        "LED_group_2": [[0, 0], [0, 0], [0, 0], [0, 0]],
        "fieldColor": base_color,
    }

FIELD_STATIC = {}

# Mögliche CSV‑pfade (prüft Projekt‑Root und den von dir angegebenen absoluten Pfad)
module_dir = os.path.dirname(__file__)
CANDIDATE_PATHS = [
    os.path.join(module_dir, "field_leds.csv"),
    "field_leds.csv",
    r"F:\Projekte\RaspberryChessBoard\field_leds.csv",
]

csv_path = next((p for p in CANDIDATE_PATHS if os.path.exists(p)), None)

if csv_path:
    # Versuche mehrere Encodings, entscheide das passende
    encodings_to_try = ["utf-8", "utf-8-sig", "cp1252", "iso-8859-1"]
    encoding_used = None
    detected_dialect = None
    for enc in encodings_to_try:
        try:
            with open(csv_path, newline="", encoding=enc) as testf:
                # schneller Probelauf: header lesen
                sniffer = csv.Sniffer()
                sample = testf.read(2048)
                testf.seek(0)
                # optional sniff dialect (nicht zwingend)
                try:
                    dialect = sniffer.sniff(sample)
                except Exception:
                    dialect = csv.excel
                reader = csv.DictReader(testf, dialect=dialect)
                # iterate one row to force decoding
                _ = next(iter(reader), None)
            encoding_used = enc
            detected_dialect = dialect
            break
        except Exception:
            continue

    if encoding_used is None:
        raise RuntimeError(f"CSV '{csv_path}' konnte mit getesteten Encodings nicht gelesen werden. Speichere die Datei als UTF-8 oder UTF-8‑SIG.")

    # Nun mit dem ermittelten Encoding vollständig parsen
    with open(csv_path, newline="", encoding=encoding_used) as csvfile:
        # use detected dialect from sniff phase when available
        if detected_dialect is not None:
            reader = csv.DictReader(csvfile, dialect=detected_dialect)
        else:
            reader = csv.DictReader(csvfile)
        # If header parsing failed (e.g., semicolon delimiter), retry with ';'
        if not reader.fieldnames or "coord" not in [fn.lower() for fn in (reader.fieldnames or [])]:
            csvfile.seek(0)
            reader = csv.DictReader(csvfile, delimiter=';')
        # Normalize fieldnames (remove BOM and whitespace)
        if reader.fieldnames:
            reader.fieldnames = [fn.lstrip('\ufeff').strip() for fn in reader.fieldnames]
        # Build a mapping from expected column keys to actual header names
        # Expected keys: coord, LED_group_1, LED_group_2, fieldColor
        actual_names = {fn.lower(): fn for fn in (reader.fieldnames or [])}
        def find_header(token):
            token = token.lower().replace('_', '').replace(' ', '')
            for low, orig in actual_names.items():
                key = low.replace('_', '').replace(' ', '')
                if token in key or key in token:
                    return orig
            return None
        hdr_coord = find_header('coord') or 'coord'
        hdr_g1 = find_header('led_group_1') or find_header('ledgroup1') or 'LED_group_1'
        hdr_g2 = find_header('led_group_2') or find_header('ledgroup2') or 'LED_group_2'
        hdr_color = find_header('fieldcolor') or find_header('field_color') or 'fieldColor'
        for row in reader:
            coord = (row.get(hdr_coord) or "").strip()
            if not coord or len(coord) != 2:
                continue
            # determine board indices for fallback color
            file_idx = ord(coord[0].lower()) - ord("a")
            rank = int(coord[1])
            r = 8 - rank
            c = file_idx
            try:
                g1_raw = (row.get(hdr_g1) or "").strip()
                g2_raw = (row.get(hdr_g2) or "").strip()
                g1 = ast.literal_eval(g1_raw) if g1_raw else _default_field_entry(r, c)["LED_group_1"]
                g2 = ast.literal_eval(g2_raw) if g2_raw else _default_field_entry(r, c)["LED_group_2"]
                # validate shape (4 pairs)
                if not (isinstance(g1, (list, tuple)) and len(g1) == 4):
                    g1 = _default_field_entry(r, c)["LED_group_1"]
                if not (isinstance(g2, (list, tuple)) and len(g2) == 4):
                    g2 = _default_field_entry(r, c)["LED_group_2"]
                color = (row.get(hdr_color) or "").strip().lower()
                if color not in ("light", "dark"):
                    color = _default_field_entry(r, c)["fieldColor"]
                FIELD_STATIC[coord] = {
                    "LED_group_1": [[int(x[0]), int(x[1])] for x in g1],
                    "LED_group_2": [[int(x[0]), int(x[1])] for x in g2],
                    "fieldColor": color,
                }
            except Exception:
                FIELD_STATIC[coord] = _default_field_entry(r, c)
else:
    # keine CSV gefunden: defaults füllen
    for row in range(8):
        for col in range(8):
            coord = FILES[col] + str(8 - row)
            FIELD_STATIC[coord] = _default_field_entry(row, col)

# Aktuelle Auswahl (coord als String, z.B. 'd2' oder None)
CURRENT_SELECTED = None


def select_field(coord: str):
    """
    Wählt ein Feld als 'selected' aus.

    Rückgabe: dict mit folgenden Schlüsseln:
      - coord: gewähltes Feld (string)
      - LED_group_1: Liste der Eckkoordinaten
      - LED_group_2: Liste der Seitenmittenkoordinaten
      - color: RGB Triple der Highlight‑Farbe für 'selected'
    Bei ungültigem Feld wird None zurückgegeben.
    """
    global CURRENT_SELECTED
    if not coord or not isinstance(coord, str):
        return None
    coord = coord.strip().lower()
    if coord not in FIELD_STATIC:
        return None
    CURRENT_SELECTED = coord
    entry = FIELD_STATIC[coord]
    return {
        "coord": coord,
        "LED_group_1": entry.get("LED_group_1"),
        "LED_group_2": entry.get("LED_group_2"),
        "color": get_highlight_color("selected"),
    }


def deselect_field():
    """Hebt die aktuelle Auswahl auf."""
    global CURRENT_SELECTED
    prev = CURRENT_SELECTED
    CURRENT_SELECTED = None
    # Versuche, zugehörige LED auf Grundfarbe zurückzusetzen (falls LED‑Controller vorhanden)
    try:
        # Lokaler Import, um zirkuläre Imports zu vermeiden
        from . import led_control

        ctl = led_control.get_default_controller()
        # Falls Controller noch nicht initialisiert ist, initialisiere im Simulationsmodus nicht automatisch
        try:
            ctl.initialize(auto_init=True)
        except Exception:
            pass
        if prev:
            try:
                ctl.set_field_state(prev, 'base')
            except Exception:
                pass
    except Exception:
        # kein Controller verfügbar: still ignorieren
        pass
    return True


def get_selected():
    """Gibt die aktuell ausgewählte Feldkennung oder None zurück."""
    return CURRENT_SELECTED
