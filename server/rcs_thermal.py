"""RCS temperatures: the programmed Tavg, the core dT, and each loop's legs.

Server only, and nothing displays it yet - the gauges are defined so the uids
exist for the Unity faces when they get baked. What this owes the rest of the
plant is that the numbers be RIGHT, because everything downstream of the
primary reads them: the subcooling margin monitor, the SG secondary side, the
low-flow and OTdT/OPdT trips, and the Tavg program the automatic rod controller
is currently faking with turbine load.

THE ONE RELATIONSHIP THAT MATTERS. Core power lands in the coolant, and how
much the coolant warms up crossing the core is that power divided by the mass
flow carrying it away:

    dT = dT_rated x (power / rated) / (flow / rated flow)

So dT is not a property of power alone. At rated power on four pumps it is
61 F. Lose two pumps and the same power has half the flow to carry it, so dT
doubles to 122 F - which is why full power on two loops is not a thing anyone
does, and why the low-flow trip exists. Losing flow raises Th and lowers Tc
around a Tavg that hasn't moved.

WHERE Tavg COMES FROM. It is PROGRAMMED, not derived: a Westinghouse plant
holds Tavg on a straight line against load, from 557 F at no load to 587.5 F at
full power, and the rods are what hold it there. The two ends are the same
number twice over - no-load Tavg is exactly full-power Tc - which is what makes
the reference numbers in misc/systems/rcs/loop.json come out at Th 618 / Tc 557
by construction rather than by tuning.

Here the program is driven off reactor POWER rather than turbine load, because
rod_sim currently makes power the independent variable (see its docstring).
When the secondary plant lands this inverts: steam demand sets load, the
program sets Tavg from load, and the rods chase it.

Tavg follows its program through a lag, because a couple of hundred tonnes of
water and steel do not change temperature the instant the flux does. dT is not
lagged - it is set by a ratio of two things that are themselves already slow.

THE LEGS. All four hot legs carry the same Th: the core outlet is one mixed
plenum. All four cold legs carry the same Tc when every loop is running.

A loop whose pump is stopped is the exception, and it does something people
find surprising: its flow REVERSES. The running pumps push water out of the
vessel through the idle loop's cold leg, backwards through its pump and steam
generator, and back into the vessel through its hot leg. So that loop's legs
BOTH read about Tc, its steam generator is being back-fed and removes
essentially nothing, and none of it shows up as core dT. With every pump
stopped there is no reverse flow to have - natural circulation is forward - so
the whole plant falls back to the flow floor below.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import math
import threading
import time

from io_state import state
from rcp_sim import RATED_FLOW_GPM, plant
from rod_sim import core

# Unity definition uids, generated here: none of these has a face yet. Paste
# them into the GaugeDefinitions when the dials are baked.
TAVG = "2da5252a-28ef-40c8-9731-91193f9abe45"
CORE_DT = "155edff7-fab1-46b2-9271-9d372e74a432"

# Per loop, matching the four RCPs one for one - loop n is the loop RCP n pumps.
LOOP_TH = {
    1: "13fe2e1c-701a-4f01-90c6-abf2bec71ce8",
    2: "9e8647dc-b905-44a7-92b5-981ddef1e865",
    3: "27b50ac6-67a9-4bfc-8ea9-87dc809f7610",
    4: "bc10d2dd-8841-4a19-919d-0f664b766a20",
}
LOOP_TC = {
    1: "c301b2a9-8e98-4644-9ee8-3de12f398e55",
    2: "86a37369-e7d3-48f0-ab4c-eaece126fb9b",
    3: "13eb0f17-f110-4298-8238-9d142748e9d1",
    4: "586678e0-6916-4c3c-a695-21085aa54969",
}

# ------------------------------------------------------------- the programme

# The Tavg programme's two ends, degF. No-load Tavg is deliberately the same
# number as full-power Tc: that is how the arrangement works, and it is what
# makes Th/Tc come out at the reference 618/557 without tuning anything.
T_NO_LOAD_F = 557.0
T_AVG_FULL_F = 587.5

# Core dT at rated power and rated flow, degF. 618 - 557.
DT_RATED_F = 61.0

# Rated total RCS flow: four loops of the number rcp_sim rates one pump at, so
# retuning the pump moves this with it rather than leaving two numbers to drift.
RATED_TOTAL_FLOW_GPM = 4.0 * RATED_FLOW_GPM

# Natural circulation, as a fraction of rated forced flow. With every pump
# stopped the core still moves water by buoyancy, and this is the floor that
# stops dT going to infinity when the flow term does to zero. Approximate - the
# real number depends on how much of the loop is above the core.
NATURAL_CIRC_FRACTION = 0.04

# Below this share of rated flow a loop counts as stopped, and its legs are
# read as reverse-flowing rather than carrying core outlet - see the docstring.
STAGNANT_LOOP_FRACTION = 0.05

# Seconds for Tavg to close ~63 % of the gap to its programme. The water and
# the steel both have to get there.
RCS_TAU = 90.0

# Gauge ranges. degF because the reference numbers in misc/systems are degF and
# the panel is a US benchboard - though the metric/imperial decision for the
# whole project is still open, see misc/systems/_manifest.json.
TEMP_MIN_F, TEMP_MAX_F = 500.0, 700.0
DT_MAX_F = 150.0

TICK_SECONDS = 0.1


def _clamp(value, low, high):
    return max(low, min(high, value))


class RcsThermal:
    """The primary side's temperatures. Module singleton (`rcs`)."""

    def __init__(self):
        self._lock = threading.RLock()

        # Cold and isothermal at the no-load programme, which is where a plant
        # sitting at hot standby with no power on it actually is.
        self.tavg = T_NO_LOAD_F
        self.core_dt = 0.0

    # ----------------------------------------------------------------- reads

    def loop_flows(self):
        """gpm per loop, straight off the pumps. Loop n is RCP n's loop."""
        return {pump.spec["n"]: pump.flow for pump in plant.pumps}

    def total_flow(self):
        return sum(pump.flow for pump in plant.pumps)

    @property
    def flow_fraction(self):
        """Total RCS flow as a fraction of rated, floored at natural circ."""
        with self._lock:
            return max(self.total_flow() / RATED_TOTAL_FLOW_GPM,
                       NATURAL_CIRC_FRACTION)

    @property
    def t_hot(self):
        with self._lock:
            return self.tavg + self.core_dt / 2.0

    @property
    def t_cold(self):
        with self._lock:
            return self.tavg - self.core_dt / 2.0

    def legs(self):
        """{loop: (Th, Tc)}. A stopped loop reads Tc on both - see the docstring."""
        with self._lock:
            flows = self.loop_flows()
            running = [n for n, flow in flows.items()
                       if flow >= STAGNANT_LOOP_FRACTION * RATED_FLOW_GPM]

            hot, cold = self.t_hot, self.t_cold

            # Nobody running means natural circulation, which is forward in
            # every loop: there is no reverse flow to have.
            if not running:
                return {n: (hot, cold) for n in flows}

            return {n: (hot, cold) if n in running else (cold, cold)
                    for n in flows}

    def tavg_program(self):
        """Where the programme wants Tavg, for the power the core is making."""
        return T_NO_LOAD_F + (T_AVG_FULL_F - T_NO_LOAD_F) * core.power / 100.0

    def status_lines(self):
        """A console dump - none of this is on the panel yet."""
        with self._lock:
            flows = self.loop_flows()
            legs = self.legs()
            lines = [
                "  Tavg  {:>6.1f} F  (programme {:>6.1f} F)   core dT {:>5.1f} F".format(
                    self.tavg, self.tavg_program(), self.core_dt),
                "  Th    {:>6.1f} F     Tc    {:>6.1f} F".format(
                    self.t_hot, self.t_cold),
                "",
                "  RCS flow {:>7.0f} gpm  ({:.0f} % of rated{})".format(
                    self.total_flow(), 100.0 * self.total_flow() / RATED_TOTAL_FLOW_GPM,
                    ", on the natural circulation floor"
                    if self.total_flow() / RATED_TOTAL_FLOW_GPM < NATURAL_CIRC_FRACTION
                    else ""),
                "",
                "  loop      flow        Th        Tc",
            ]
            for n in sorted(flows):
                hot, cold = legs[n]
                reverse = (flows[n] < STAGNANT_LOOP_FRACTION * RATED_FLOW_GPM
                           and any(f >= STAGNANT_LOOP_FRACTION * RATED_FLOW_GPM
                                   for f in flows.values()))
                lines.append("  {:<4} {:>9.0f} {:>9.1f} {:>9.1f}  {}".format(
                    n, flows[n], hot, cold,
                    "reverse flow - SG back-fed" if reverse else "").rstrip())
            return lines

    # ------------------------------------------------------------------ tick

    def step(self, dt):
        with self._lock:
            # Set by a ratio, not integrated: both things it divides are
            # already slow, and a pump coasting down moves it exactly as fast
            # as the flywheel lets the flow fall.
            self.core_dt = _clamp(
                DT_RATED_F * (core.power / 100.0) / self.flow_fraction,
                0.0, DT_MAX_F)

            target = self.tavg_program()
            self.tavg += (target - self.tavg) * (1.0 - math.exp(-dt / RCS_TAU))


rcs = RcsThermal()


class RcsThermalSimulation:
    def __init__(self, tick=TICK_SECONDS):
        self.rcs = rcs
        self.tick = tick

        self._stop = threading.Event()
        self._thread = None

    def ensure_definitions(self):
        """Create the ten gauges if they're missing. No Unity faces yet."""
        created = 0

        created += self._ensure_gauge(TAVG, "RCS Tavg", TEMP_MIN_F, TEMP_MAX_F,
                                      "F", T_NO_LOAD_F)
        created += self._ensure_gauge(CORE_DT, "Core dT", 0.0, DT_MAX_F, "F", 0.0)

        for n in sorted(LOOP_TH):
            created += self._ensure_gauge(
                LOOP_TH[n], f"Loop {n} Th", TEMP_MIN_F, TEMP_MAX_F, "F", T_NO_LOAD_F)
            created += self._ensure_gauge(
                LOOP_TC[n], f"Loop {n} Tc", TEMP_MIN_F, TEMP_MAX_F, "F", T_NO_LOAD_F)

        if created:
            state.save()
            print(f"[rcs] defined {created} RCS temperature "
                  f"entr{'y' if created == 1 else 'ies'}")

    @staticmethod
    def _ensure_gauge(uid, name, min_value, max_value, units, value):
        entry = state.get_gauge(uid)
        if (entry is not None and entry["minValue"] == min_value
                and entry["maxValue"] == max_value and entry["units"] == units):
            return 0

        state.define_gauge(uid, id=name, name=name, units=units,
                           min_value=min_value, max_value=max_value,
                           value=value, save=False)
        return 1

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="rcs-thermal-sim")
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
            self.rcs.step(now - last)
            last = now
            self._publish()

    def _publish(self):
        state.set_gauge(TAVG, self.rcs.tavg)
        state.set_gauge(CORE_DT, self.rcs.core_dt)

        for n, (hot, cold) in self.rcs.legs().items():
            state.set_gauge(LOOP_TH[n], hot)
            state.set_gauge(LOOP_TC[n], cold)
