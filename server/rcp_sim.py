"""Test simulation: four RCPs whose speed follows their power switch.

Switch on (and powered) -> the pump runs up toward NOMINAL_HZ; switch off ->
it coasts down toward zero. First-order lag in both directions, with a longer
time constant for coastdown (the flywheel), so the gauges move like machinery
rather than snapping.

This is deliberately the smallest possible consumer of the io_state runtime
API - read a switch, write a gauge - and doubles as the reference for wiring
future systems: put your uids in a table, read inputs, write outputs on a tick.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import math
import threading
import time

from io_state import state

# One row per pump: the gauge it drives and the switch it listens to.
# uids are the Unity definition UIDs (SwitchDefinition / GaugeDefinition).
PUMPS = [
    {"name": "RCP 1",
     "power": "ff27d4bc-1f3d-480b-9189-fa683dfd6b72",
     "freq":  "ba6c1b83-fd01-4cd7-bcc5-402654aee148"},
    {"name": "RCP 2",
     "power": "ec026435-4b00-47e0-af59-5c69ec5e574c",
     "freq":  "370a8be9-2094-4bc8-ab74-5150b560a7f9"},
    {"name": "RCP 3",
     "power": "ca327d3d-c283-43d7-8801-1bd7845cf3c4",
     "freq":  "69418421-717f-4e20-a947-5b3fc91de638"},
    {"name": "RCP 4",
     "power": "b9a7d998-f202-47f3-9848-3b0c489fd103",
     "freq":  "5ca2be2d-df54-42e4-b17f-c3bf59975443"},
]

NOMINAL_HZ = 60.0       # supply frequency at speed (gauges are 0-80 Hz)
RUNUP_TAU = 6.0         # seconds to ~63% of nominal on start
COASTDOWN_TAU = 20.0    # flywheel coastdown - slower than the run-up
TICK_SECONDS = 0.1
SNAP_HZ = 0.05          # close enough to the target counts as at the target


class RcpSimulation:
    def __init__(self, pumps=None, nominal_hz=NOMINAL_HZ, runup_tau=RUNUP_TAU,
                 coastdown_tau=COASTDOWN_TAU, tick=TICK_SECONDS, snap_hz=SNAP_HZ):
        self.pumps = pumps if pumps is not None else PUMPS
        self.nominal_hz = nominal_hz
        self.runup_tau = runup_tau
        self.coastdown_tau = coastdown_tau
        self.tick = tick
        self.snap_hz = snap_hz

        self._stop = threading.Event()
        self._thread = None
        self._was_running = {}   # pump name -> bool, for the console lines

    def ensure_definitions(self):
        """Create any missing switch/gauge definitions (persists to the JSON)."""
        created = 0

        for pump in self.pumps:
            if state.get_switch(pump["power"]) is None:
                state.define_switch(
                    pump["power"], id=f"{pump['name']} Power", name=f"{pump['name']} Power",
                    positions=["off", "on"], position="off", save=False)
                created += 1
            if state.get_gauge(pump["freq"]) is None:
                state.define_gauge(
                    pump["freq"], id=f"{pump['name']} Freq", name=f"{pump['name']} Freq",
                    units="Hz", min_value=0.0, max_value=80.0, value=0.0, save=False)
                created += 1

        if created:
            state.save()
            print(f"[sim] defined {created} missing RCP entr{'y' if created == 1 else 'ies'}")

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="rcp-sim")
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
        for pump in self.pumps:
            switch = state.get_switch(pump["power"])
            gauge = state.get_gauge(pump["freq"])
            if switch is None or gauge is None:
                continue   # someone reloaded a JSON without them; nothing to drive

            running = switch["position"] == "on" and switch["powered"]
            if running != self._was_running.get(pump["name"]):
                self._was_running[pump["name"]] = running
                print(f"[sim] {pump['name']} {'running up' if running else 'coasting down'}")

            target = self.nominal_hz if running else 0.0
            tau = self.runup_tau if target > gauge["value"] else self.coastdown_tau

            value = gauge["value"] + (target - gauge["value"]) * (1.0 - math.exp(-dt / tau))
            if abs(target - value) < self.snap_hz:
                value = target

            state.set_gauge(pump["freq"], value)
