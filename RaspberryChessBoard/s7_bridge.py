# s7_bridge.py
# Einfacher S7-DB-Poller, der fallende Flanken als "Mausklick" interpretiert
# Verwendung: siehe Beispiel am Ende der Datei.

import threading
import time
from typing import Optional, Callable

try:
    from snap7.client import Client
except Exception:
    Client = None  # snap7 nicht installiert

from .FieldConfig import select_field, FILES


class S7FieldBridge:
    """
    Liest ein DB (8 Bytes) und erkennt fallende Flanken (1->0) pro Bit.
    Jeder erkannte Fall löst select_field(coord) aus.

    Mapping (wie besprochen):
    - Byte 0 -> Rank 1, Byte 7 -> Rank 8
    - Bit 0 -> File 'a', Bit 7 -> File 'h'

    Beispiel: DB1.DBX0.0 == a1
    """

    def __init__(self, ip: str, rack: int = 0, slot: int = 1, db_number: int = 1, poll_interval: float = 0.02, on_select: Optional[Callable[[str], None]] = None):
        self.ip = ip
        self.rack = rack
        self.slot = slot
        self.db_number = db_number
        self.poll_interval = float(poll_interval)
        self.on_select = on_select or (lambda coord: select_field(coord))

        self._client = Client() if Client is not None else None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._prev_bytes: Optional[bytes] = None

        # Software-Schalter: True = lokales Steuern (Maus/Tastatur aktiv)
        # False = Steuereingaben kommen aus dem S7-DB
        self.software_switch = True

    def set_software_switch(self, enabled: bool):
        """Setzt den Software‑Schalter. True = lokale Steuerung aktiv."""
        self.software_switch = bool(enabled)

    def get_software_switch(self) -> bool:
        return self.software_switch

    def connect(self):
        if self._client is None:
            raise RuntimeError("snap7.Client nicht verfügbar. Installiere python-snap7 oder verwende Simulation.")
        if not self._client.get_connected():
            try:
                self._client.connect(self.ip, self.rack, self.slot)
            except Exception as e:
                raise RuntimeError(f"Verbindung zur PLC fehlgeschlagen: {e}")

    def disconnect(self):
        if self._client is not None and self._client.get_connected():
            try:
                self._client.disconnect()
            except Exception:
                pass

    def _read_db8(self) -> bytes:
        """Liest 8 Bytes vom Anfang des konfigurierten DBs."""
        if self._client is None:
            raise RuntimeError("snap7.Client nicht verfügbar.")
        data = self._client.db_read(self.db_number, 0, 8)
        # sicherstellen, dass wir 8 Bytes haben
        if len(data) < 8:
            data = bytes(list(data) + [0] * (8 - len(data)))
        return data[:8]

    def _handle_falling_edges(self, prev: bytes, curr: bytes):
        # prev und curr sind bytes mit Länge >=8
        for byte_idx in range(8):
            p = prev[byte_idx]
            c = curr[byte_idx]
            changed = p & (~c)  # bits die von 1 -> 0 gingen
            if changed == 0:
                continue
            for bit in range(8):
                if (changed >> bit) & 1:
                    file = FILES[bit]
                    rank = byte_idx + 1
                    coord = f"{file}{rank}"
                    try:
                        self.on_select(coord)
                    except Exception:
                        # Callback darf nicht die Polling-Schleife killen
                        pass

    def _poll_loop(self):
        while self._running:
            try:
                if self.software_switch:
                    # lokale Steuerung aktiv -> nichts vom PLC verarbeiten
                    self._prev_bytes = None
                    time.sleep(self.poll_interval)
                    continue

                curr = self._read_db8()
                if self._prev_bytes is None:
                    # initialer Zustand: setzen, aber keine Flanken melden
                    self._prev_bytes = curr
                else:
                    if curr != self._prev_bytes:
                        self._handle_falling_edges(self._prev_bytes, curr)
                        self._prev_bytes = curr
                time.sleep(self.poll_interval)
            except Exception:
                # Fehler im Polling — einfach warten und erneut probieren
                time.sleep(self.poll_interval)

    def start(self, connect_now: bool = True):
        if connect_now:
            try:
                self.connect()
            except Exception as e:
                raise
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        try:
            self.disconnect()
        except Exception:
            pass


# ------- Beispiel / Nutzung -------
#
# from RaspberryChessBoard.s7_bridge import S7FieldBridge
# bridge = S7FieldBridge(ip='192.168.0.10', rack=0, slot=1, db_number=1)
# bridge.set_software_switch(False)  # Steuereingaben aus PLC
# bridge.start()
#
# bridge.stop()
#
# Hinweis: Installiere python-snap7 (pip install python-snap7) auf dem System, das die Verbindung zur CPU
# herstellt. Alternativ kannst du eine kleine Wrapper-Implementierung schreiben, die die DB-Bytes aus einer
# Testdatei liest, falls du offline testen möchtest.
