"""Test simulation: the turbine-generator set, from run-up to load.

Three things happen in sequence, and they're one system because each locks the
next:

  run-up   Valve position is the speed demand, straight through: 22.8 % asks for
           1800 RPM, half speed. Speed glides to the demand as a first-order lag
           - the rate of change is proportional to how far off it is, so the
           turbine pulls hard while it's a long way out and creeps in over the
           last few RPM.

  sync     The angle between the machine and the grid is carried forward every
           tick, whatever else is going on - it drifts at the slip between the
           two, one full turn per slip cycle, winding forward when the turbine
           is the quicker. The synchroscope doesn't create that offset, it only
           reads it out, so switching the instrument in lands the pointer on the
           offset as it already stands rather than resuming from wherever it was
           parked. It reads within SYNC_BAND_RPM of grid speed, where the drift
           is slow enough to follow. Shutting the generator breaker inside that
           band puts the machine on the grid, and the grid then holds it at
           synchronous speed - slip goes to zero and the offset stops where the
           breaker caught it.

  load     On the grid the turbine can't speed up, so demand above synchronous
           speed becomes torque instead: the valve position that asked for
           1800 RPM now makes exactly 0 MW, further open makes megawatts, and
           further shut makes negative ones. Nothing reacts to negative load yet
           - the gauge stops at zero and a reverse-current annunciator is what
           will show it.

Grid frequency is an input, not something this drives: it sits at 60 Hz and
everything downstream reads it, so dropping it to 59 later moves synchronous
speed and the load zero point on its own.

Note the two Unity gauge faces - "Turbine RPM" (0-2000) and "Turbine RPM Close"
(1795-1805, the expanded scale for synchronising) - share one uid. The server
holds a single value over the full range; each needle clips it to its own face.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import math
import threading
import time

from io_state import state
from valve_sim import TURBINE_VALVE_POS

# Unity definition uids. The two switches are two-position (Rot2p reports
# "off"/"on"), so "on" is the shut breaker and the live synchroscope.
TURBINE_RPM = "3eec464f-9dd1-437b-bc17-af5353b69b7c"
GRID_FREQ = "d4b07123-9cdc-44fc-abd1-177a8202515a"
GEN_BREAKER = "24652917-586c-4784-825c-c24941506d94"
GEN_LOAD = "5bda98ec-9015-46ed-b820-a923543e466b"
SYNCHROSCOPE = "5bbbde79-234b-4f1f-882f-c3e8813167cf"
SYNC_TOGGLE = "489d8134-f962-4918-a5db-99dde088f8b0"

# The design point the demand curve is pinned to: this much valve asks for this
# many RPM, and everything in between is proportional.
RATED_RPM = 1800.0        # half speed - the synchronising target
RATED_VALVE_PCT = 22.8

# 4-pole machine, so 1800 RPM is 60 Hz. Turns RPM into the electrical frequency
# the synchroscope compares against the grid, and grid Hz into synchronous speed.
RPM_PER_HZ = 30.0
NOMINAL_GRID_HZ = 60.0

RESPONSE_TAU = 30.0     # seconds to close ~63% of the gap to the demand
TICK_SECONDS = 0.1
SNAP_RPM = 0.5          # close enough to the demand counts as at the demand

# How near synchronous speed the machine has to be for the synchroscope to mean
# anything - and so for the breaker to catch.
SYNC_BAND_RPM = 10.0

# Arabelle's rating, reached with the valve wide open. Everything between there
# and the load zero point at RATED_VALVE_PCT is proportional.
RATED_LOAD_MW = 1800.0
RATED_LOAD_VALVE_PCT = 100.0

# Gauge ranges, matching the Unity definitions.
RPM_MIN, RPM_MAX = 0.0, 2000.0
LOAD_MIN, LOAD_MAX = 0.0, 2000.0
GRID_HZ_MIN, GRID_HZ_MAX = 57.0, 63.0


class TurbineSimulation:
    def __init__(self, valve_uid=TURBINE_VALVE_POS, rated_rpm=RATED_RPM,
                 rated_valve_pct=RATED_VALVE_PCT, tau=RESPONSE_TAU,
                 sync_band=SYNC_BAND_RPM, tick=TICK_SECONDS, snap_rpm=SNAP_RPM):
        self.valve_uid = valve_uid
        self.tau = tau
        self.sync_band = sync_band
        self.tick = tick
        self.snap_rpm = snap_rpm

        self.rpm_per_percent = rated_rpm / rated_valve_pct

        # Load per RPM of demand above synchronous speed. Derived rather than
        # given, so moving the rating or the design point keeps 0 MW sitting
        # exactly on the valve position that asks for synchronous speed.
        excess_at_rated = RATED_LOAD_VALVE_PCT * self.rpm_per_percent - rated_rpm
        self.mw_per_rpm = RATED_LOAD_MW / excess_at_rated

        # Degrees the machine leads the grid by. Live from startup and tracked
        # whether or not anything is displaying it.
        self._phase = 0.0

        self._stop = threading.Event()
        self._thread = None
        self._was_moving = None   # -1/0/1, for the console lines
        self._was_locked = None

    def ensure_definitions(self):
        """Create any missing gauge/switch definitions (persists to the JSON)."""
        created = 0

        gauges = [
            (TURBINE_RPM, "Turbine RPM", "RPM", RPM_MIN, RPM_MAX, 0.0),
            (GEN_LOAD, "Gen Load", "MW", LOAD_MIN, LOAD_MAX, 0.0),
            (SYNCHROSCOPE, "Gen Synchroscope", "", 0.0, 360.0, 0.0),
            # Held where the grid is, and left alone - see the module docstring.
            (GRID_FREQ, "Grid Freq.", "Hz", GRID_HZ_MIN, GRID_HZ_MAX, NOMINAL_GRID_HZ),
        ]
        for uid, name, units, low, high, value in gauges:
            if state.get_gauge(uid) is None:
                state.define_gauge(uid, id=name, name=name, units=units,
                                   min_value=low, max_value=high, value=value, save=False)
                created += 1

        for uid, name in ((GEN_BREAKER, "Gen Breaker"), (SYNC_TOGGLE, "Synchroscope Toggle")):
            if state.get_switch(uid) is None:
                state.define_switch(uid, id=name, name=name,
                                    positions=["off", "on"], position="off", save=False)
                created += 1

        if created:
            state.save()
            print(f"[sim] defined {created} missing turbine-generator "
                  f"entr{'y' if created == 1 else 'ies'}")

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="turbine-sim")
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
        valve = state.get_gauge(self.valve_uid)
        turbine = state.get_gauge(TURBINE_RPM)
        if valve is None or turbine is None:
            return   # someone reloaded a JSON without them; nothing to drive

        grid_rpm = self._grid_rpm()

        # Unclamped on purpose: the RPM needle stops at the end of its dial, but
        # load doesn't - past synchronous speed the surplus is what makes
        # megawatts, and clamping here would cap the machine at a few MW.
        demand = valve["value"] * self.rpm_per_percent

        was = turbine["value"]
        locked = self._is_on(GEN_BREAKER) and abs(was - grid_rpm) <= self.sync_band

        if locked:
            # The grid holds it there. Note this keeps itself true: once pinned
            # the machine is exactly at grid speed, so the band test above stays
            # satisfied for as long as the breaker is shut.
            rpm = grid_rpm
        else:
            # A demand off the end of the dial would have the needle sprinting
            # the last stretch instead of easing onto it, so the target stops
            # where the gauge does.
            target = _clamp(demand, turbine["minValue"], turbine["maxValue"])
            rpm = was + (target - was) * (1.0 - math.exp(-dt / self.tau))
            if abs(target - rpm) < self.snap_rpm:
                rpm = target

        state.set_gauge(TURBINE_RPM, rpm)
        self._advance_phase(dt, rpm, grid_rpm)
        self._show_phase(rpm, grid_rpm)
        self._step_load(locked, demand, grid_rpm)
        self._log(was, rpm, demand, locked)

    def _advance_phase(self, dt, rpm, grid_rpm):
        """Carry the angle between the machine and the grid forward.

        Every tick, whatever the instrument is doing: the offset is a fact about
        the two waveforms, and it goes on drifting while nobody is watching.
        Slip is the rate - one full turn per slip cycle, winding forward when
        the machine is the faster of the two.
        """
        slip_hz = (rpm - grid_rpm) / RPM_PER_HZ
        self._phase = (self._phase + slip_hz * 360.0 * dt) % 360.0

    def _show_phase(self, rpm, grid_rpm):
        """Put the offset on the dial, if there's anything there to read it.

        Written from the offset rather than nudged along from the last reading,
        so switching the synchroscope in lands the pointer on the phase as it
        already stands.
        """
        if state.get_gauge(SYNCHROSCOPE) is None or not self._is_on(SYNC_TOGGLE):
            return   # switched out - the pointer sits where it was left

        if abs(rpm - grid_rpm) > self.sync_band:
            # Further out the drift is an unreadable blur, and past ~75 RPM it
            # turns more than half a dial between syncs, so the pointer would
            # alias and read backwards. The offset itself keeps being tracked.
            return

        state.set_gauge(SYNCHROSCOPE, self._phase)

    def _step_load(self, locked, demand, grid_rpm):
        """Demand the machine can't turn into speed comes out as megawatts."""
        if state.get_gauge(GEN_LOAD) is None:
            return

        # Off the grid it's spinning against nothing, so it carries no load.
        load = (demand - grid_rpm) * self.mw_per_rpm if locked else 0.0

        # Below the load zero point this goes negative - the machine motoring on
        # the grid. The gauge stops at zero and nothing else reacts yet.
        state.set_gauge(GEN_LOAD, load)

    def _grid_rpm(self):
        grid = state.get_gauge(GRID_FREQ)
        grid_hz = grid["value"] if grid is not None else NOMINAL_GRID_HZ
        return grid_hz * RPM_PER_HZ

    @staticmethod
    def _is_on(uid):
        entry = state.get_switch(uid)
        return entry is not None and entry["position"] == "on" and entry["powered"]

    def _log(self, was, rpm, demand, locked):
        if locked != self._was_locked:
            self._was_locked = locked
            print(f"[sim] generator {'on the grid' if locked else 'off the grid'} "
                  f"at {rpm:.0f} RPM")

        moving = (rpm > was) - (rpm < was)
        if moving != self._was_moving:
            self._was_moving = moving
            motion = {1: "accelerating", -1: "decelerating"}.get(
                moving, f"steady at {rpm:.0f} RPM")
            print(f"[sim] turbine {motion} (demand {demand:.0f} RPM)")


def _clamp(value, low, high):
    return max(low, min(high, value))
