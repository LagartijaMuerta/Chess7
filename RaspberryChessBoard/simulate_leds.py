"""Simulationsskript für LED‑Controller (FakeStrip).

Starten aus Projektroot:
  python -m RaspberryChessBoard.simulate_leds

Das Skript initialisiert den Default‑Controller im Simulationsmodus
und führt eine kleine Sequenz aus: Basisfarben setzen, einige Highlights,
danach Deselektion, mit Ausgabe des internen Buffers (erste LEDs).
"""
import time
import logging

from . import led_control
from . import FieldConfig

logging.basicConfig(level=logging.DEBUG)


def dump_strip(name, strip):
    # Robust: FakeStrip hat .pixels; echte NeoPixel ist indexierbar
    if strip is None:
        print(f"{name}: <uninitialized>")
        return
    if hasattr(strip, 'pixels'):
        pixels = strip.pixels
    else:
        # try to read via indexing
        try:
            pixels = [strip[i] for i in range(len(strip))]
        except Exception:
            print(f"{name}: <cannot read pixels>")
            return
    nonzero = [(i, c) for i, c in enumerate(pixels) if c != (0, 0, 0)]
    print(f"{name}: length={len(pixels)} nonzero={len(nonzero)} samples={nonzero[:10]}")


def main():
    ctl = led_control.get_default_controller()
    # Simulation: force FakeStrip (auto_init=False)
    ctl.initialize(auto_init=False)

    print("Initial state (nach base colors):")
    dump_strip('strip1', ctl.strip1)
    dump_strip('strip2', ctl.strip2)

    time.sleep(0.5)

    # Set some highlights
    print('\nSetze d2 -> selected (LED_group_2)')
    ctl.set_field_state('d2', 'selected')
    time.sleep(0.2)
    dump_strip('strip1', ctl.strip1)
    dump_strip('strip2', ctl.strip2)

    print('\nSetze d3 und d4 -> move (LED_group_1)')
    ctl.set_field_state('d3', 'move')
    ctl.set_field_state('d4', 'move')
    time.sleep(0.2)
    dump_strip('strip1', ctl.strip1)
    dump_strip('strip2', ctl.strip2)

    # Keine Deselektion mehr in der Simulation (bleibt markiert)

    # Setze zusätzlich capture auf e3
    print('\nSetze e3 -> capture (LED_group_2)')
    ctl.set_field_state('e3', 'capture')

    # Gebe die Farben für d2, d3, d4, e3 (LED_group_1 und LED_group_2) aus
    for fld in ('d2', 'd3', 'd4', 'e3'):
        entry = ctl.field_map.get(fld)
        print(f"\nFeld {fld}:")
        if not entry:
            print('  kein Eintrag in field_map')
            continue
        for group_name in ('LED_group_1', 'LED_group_2'):
            pairs = entry.get(group_name, [])
            print(f"  {group_name}:")
            for pair in pairs:
                idx = int(pair[0])
                channel = int(pair[1])
                # read buffer value
                if channel == 1:
                    color = ctl._buf1[idx] if 0 <= idx < ctl.len1 else (0,0,0)
                else:
                    color = ctl._buf2[idx] if 0 <= idx < ctl.len2 else (0,0,0)
                print(f"    index={idx} channel={channel} color={color}")

    print('\nFertig.')


if __name__ == '__main__':
    main()
