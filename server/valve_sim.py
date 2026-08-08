"""Test simulation: turbine and bypass valves driven by three-position switches.

Hold a switch left and its valve strokes closed, right and it strokes open,
centre and it stays where it is. Rot3p switches stay where they're put, so
"hold" here means "left there until someone clicks it back to centre".

Travel is linear at a fixed rate per switch - a valve actuator runs at its own
speed, it doesn't ease in - and the gauge clamps itself at 0/100 %.

The turbine valve has two switches on the same gauge: the main one, and the
"Close" fine control, an order of magnitude slower, for trimming load without
overshooting. Both feed the same rate sum, so using them together just adds.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import threading
import time

from io_state import state

# %/s of valve travel, per switch. Full stroke = 100 / rate seconds.
COARSE_RATE = 4.0    # turbine valve, main switch  - 25 s open to shut
FINE_RATE = 0.1      # turbine valve, "Close" fine - a vernier, not a stroke:
                     # 8 RPM of speed demand or 2.3 MW of load per second held
BYPASS_RATE = 5.0    # bypass valve                - 20 s

TICK_SECONDS = 0.1

# Which way each switch position drives the valve. Anything else (centre)
# holds; the switch's own position list is the authority on what's valid.
DIRECTION = {"left": -1.0, "right": 1.0}

# Named so downstream systems can take a valve position as their input rather
# than repeating the uid - turbine_sim reads TURBINE_VALVE_POS.
TURBINE_VALVE_POS = "d2abdb5e-33cd-4823-a253-20cb7197190b"
BYPASS_VALVE_POS = "4acc4604-0a08-4514-bce4-997a10bdfb97"

# One row per valve: the position gauge it drives, and every switch that
# strokes it. uids are the Unity definition UIDs (SwitchDefinition /
# GaugeDefinition).
VALVES = [
    {"name": "Turbine Valve",
     "gauge": TURBINE_VALVE_POS,
     "gauge_name": "Turbine Valve Pos",
     "switches": [
         {"name": "Turbine Valve",
          "uid": "a8f5e1af-ee37-4243-bfbc-f311c4511e96",
          "rate": COARSE_RATE},
         {"name": "Turbine Valve Close",
          "uid": "9e8846e0-cd3b-499f-aaa2-24f045dfcb54",
          "rate": FINE_RATE},
     ]},
    {"name": "Bypass Valve",
     "gauge": BYPASS_VALVE_POS,
     "gauge_name": "Bypass Valve Pos",
     "switches": [
         {"name": "Bypass Valve",
          "uid": "0ac4fee0-5337-457a-8e58-5bca5ad715c1",
          "rate": BYPASS_RATE},
     ]},
]

# Matches Rot3p._positionNames on the client - renaming one changes the wire
# format for every three-position switch.
POSITIONS = ["left", "center", "right"]


class ValveSimulation:
    def __init__(self, valves=None, tick=TICK_SECONDS):
        self.valves = valves if valves is not None else VALVES
        self.tick = tick

        self._stop = threading.Event()
        self._thread = None
        self._was_moving = {}   # valve name -> -1/0/1, for the console lines

    def ensure_definitions(self):
        """Create any missing switch/gauge definitions (persists to the JSON)."""
        created = 0

        for valve in self.valves:
            for switch in valve["switches"]:
                if state.get_switch(switch["uid"]) is None:
                    state.define_switch(
                        switch["uid"], id=switch["name"], name=switch["name"],
                        positions=list(POSITIONS), position="center", save=False)
                    created += 1

            if state.get_gauge(valve["gauge"]) is None:
                state.define_gauge(
                    valve["gauge"], id=valve["gauge_name"], name=valve["gauge_name"],
                    units="%", min_value=0.0, max_value=100.0, value=0.0, save=False)
                created += 1

        if created:
            state.save()
            print(f"[sim] defined {created} missing valve entr{'y' if created == 1 else 'ies'}")

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="valve-sim")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self):
        last = time.monotonic()
        while not self._stop.wait(self.tick):
            now = time.monotonic()
            self._step(now - last)
            last = now

    def _step(self, dt):
        for valve in self.valves:
            gauge = state.get_gauge(valve["gauge"])
            if gauge is None:
                continue   # someone reloaded a JSON without it; nothing to drive

            rate = 0.0
            for switch in valve["switches"]:
                entry = state.get_switch(switch["uid"])
                if entry is None or not entry["powered"]:
                    continue
                rate += DIRECTION.get(entry["position"], 0.0) * switch["rate"]

            moving = (rate > 0) - (rate < 0)
            if moving != self._was_moving.get(valve["name"]):
                self._was_moving[valve["name"]] = moving
                motion = {1: "opening", -1: "closing"}.get(moving, "holding")
                print(f"[sim] {valve['name']} {motion}")

            if rate == 0.0:
                continue

            # set_gauge clamps to the gauge's own min/max, so the valve stops
            # at its seat and at full open without any extra bookkeeping.
            state.set_gauge(valve["gauge"], gauge["value"] + rate * dt)
