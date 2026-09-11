"""Reactor coolant pumps: motor, electrical supply, protection and casualties.

Four pumps, each a Westinghouse Model 93A-class machine (6-pole, ~7000 hp,
1190 rpm) hung off its own slice of the plant electrical system. The panel shows
three things per pump - the PUMP control switch with its lamp pair, an ammeter
and a loop flow gauge - and everything below exists to make those three agree
with each other the way the real ones do.

THE SUPPLY. Two levels, because they fail differently and the annunciator panel
distinguishes them:

    NBUS-{1,2}      6.9kV. NBUS-1 feeds RCP 1 and 2, NBUS-2 feeds RCP 3 and 4.
                    Each pump's motor breaker (FDR-52) AND the normal feed to
                    its auxiliary MCC come from here, so losing an NBUS takes
                    both at once - the motor stops and the auxiliaries have to
                    find power somewhere else.
    SBO-BUS-{1,2}   480V, diesel-backed. The ALTERNATE feed to the MCCs only:
                    SBO-1 backs RCP 1 and 2, SBO-2 backs RCP 3 and 4. Nothing
                    here can turn a pump; it only keeps the auxiliaries alive.

    RCP{n}-MCC      the auxiliaries - oil lift pump, lube oil, instrumentation.
                    A break-before-make transfer switch picks NORMAL (its NBUS)
                    when that is live and ALTERNATE (its SBO bus) when it isn't.
                    With neither available the MCC is dead, and a pump with no
                    auxiliaries is tripped: no jacking oil, no instruments.

THE MOTOR. Fixed speed - it follows bus frequency, there is nothing to control.
Closing FDR-52 draws locked-rotor inrush (~6x full-load amps) and the flywheel
holds the current up near it for most of a 15-25 s run-up, which is what makes
the ammeter peg against its 0-1000 A face instead of flicking. Opening it leaves
the flywheel to coast the pump down over minutes, and loop flow follows shaft
speed the whole way. That flywheel is a safety feature - it is what buys the
core forced flow through a loss of power - so the coastdown is deliberately slow.

THE SWITCH IS NOT THE BREAKER. The PUMP switch is a spring-return TRIP /
NORMAL / START controller: both ends are momentary commands and the switch
lives in the middle. The breaker holds its own state - START closes it if the
permissives are satisfied, TRIP opens it, and it stays where it was put until
something moves it. Only the MOVE onto an end counts as a command; the sim
never acts on the switch merely sitting somewhere, because the operator's hand
rests on an end for as long as it takes them to let go.

Because the switch carries no standing run request, nothing here can restart a
pump by itself. A trip opens the breaker and the switch is already back at
NORMAL; the operator clears the casualty, resets the trip, then presses START.
A maintained switch needed the out-of-correspondence rule to get that same
guarantee, which is why that rule is gone.

A trip will not reset while the condition that would raise it is still standing
- a dead bus, an MCC with neither supply - because a protective lockout does
not hand back onto a live casualty; clear it first.

Casualties come in through the server console rather than from anything
modelled upstream - see commands.py for /fault and /component. Alarms are
conditions here and windows in annunciator_sim.py, so they run the same
alarm/acknowledge/ringback sequence as everything else on the rack.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import math
import threading
import time

from io_state import state

# One row per pump. Every uid here is the _id of a SwitchDefinition asset in
# Controls/Definitions/RCS Section - rename the asset all you like, the uid is
# what binds. "power" is the PUMP switch (Rot2p, off/on) and doubles as the uid
# of its lamp pair, because SwitchLampIndicator answers to the switch it hangs
# under; "runlamp" is the separate run light on the panel, which hangs under
# nothing and so carries a definition of its own. "bus" is the NBUS feeding the
# motor and the MCC normal supply; "sbo" is the SBO bus backing the MCC
# alternate supply.
PUMPS = [
    {"n": 1, "name": "RCP 1", "key": "rcp-1", "bus": 1, "sbo": 1,
     "power":   "ff27d4bc-1f3d-480b-9189-fa683dfd6b72",
     "amps":    "cf7d4604-8216-4612-ab85-a449e4c25751",
     "flow":    "ba6c1b83-fd01-4cd7-bcc5-402654aee148",
     "runlamp": "92d1df45-7278-4ff4-a337-24bbb6767be3"},
    {"n": 2, "name": "RCP 2", "key": "rcp-2", "bus": 1, "sbo": 1,
     "power":   "ec026435-4b00-47e0-af59-5c69ec5e574c",
     "amps":    "50a869f8-f036-4519-abb9-f44c6d555d6d",
     "flow":    "370a8be9-2094-4bc8-ab74-5150b560a7f9",
     "runlamp": "b69a4a3d-d07b-4261-8739-5c5243aa1431"},
    {"n": 3, "name": "RCP 3", "key": "rcp-3", "bus": 2, "sbo": 2,
     "power":   "ca327d3d-c283-43d7-8801-1bd7845cf3c4",
     "amps":    "469fe400-758b-42ef-bf40-e7edc59500ed",
     "flow":    "69418421-717f-4e20-a947-5b3fc91de638",
     "runlamp": "d9d94cbd-a33f-4b2b-a91f-9dc08cd01471"},
    {"n": 4, "name": "RCP 4", "key": "rcp-4", "bus": 2, "sbo": 2,
     "power":   "b9a7d998-f202-47f3-9848-3b0c489fd103",
     "amps":    "da94965c-b6f9-4575-9d9c-fee9340f35f4",
     "flow":    "5ca2be2d-df54-42e4-b17f-c3bf59975443",
     "runlamp": "9a861d6a-5e7f-480a-81dc-4f0a385d5089"},
]

# Machine numbers, from misc/systems/rcs/rcp.json (Model 93A class, approx).
RATED_RPM = 1190.0          # 6-pole at 60 Hz, minus slip
FLA_AMPS = 500.0            # full-load current
LOCKED_ROTOR_AMPS = 3000.0  # ~6x FLA at standstill
RATED_FLOW_GPM = 96000.0    # one loop at rated speed

# Panel scales. The ammeter reads to twice FLA, so a run-up pegs it - real ones
# do, and an operator watching the needle come off the stop is how a start is
# judged. Flow reads to 125% of rated.
AMMETER_MAX_A = 1000.0
FLOW_GAUGE_MAX_GPM = 120000.0

# Run-up is a first-order lag, so it never quite arrives: tau 5 s puts the pump
# at 95% in 15 s and 98% in 20 s, which is the 15-25 s the flywheel makes of an
# otherwise 2-3 s start. Coastdown tau is set so flow halves at 25 s
# (25 / ln 2), the number the flywheel is actually specified by.
RUNUP_TAU = 5.0
COASTDOWN_TAU = 36.1
SNAP_RPM = 1.0              # close enough to the target counts as at it

# How sharply current falls away as the motor comes up to speed. An induction
# motor holds near locked-rotor current until it is most of the way there and
# then drops off a cliff, which a high exponent is the cheapest way to draw.
CURRENT_KNEE = 6.0

TICK_SECONDS = 0.1

# Switch positions. Rot3pSpring reports geometry rather than meaning - "left",
# "center", "right" - so one definition can move between a latching switch and
# a spring-return one without the server noticing. On the pump controller left
# is TRIP, right is START, and the spring puts it back in the middle.
SW_TRIP = "left"
SW_NORMAL = "center"
SW_START = "right"

# What each position reads as on the console.
SWITCH_LABELS = {SW_TRIP: "TRIP", SW_NORMAL: "NORMAL", SW_START: "START"}

# Lamp states SwitchLampIndicator understands. Red is the breaker closed, green
# is open. With a momentary switch these lamps are the only breaker indication
# there is - the switch itself is back at NORMAL whatever the breaker did.
LAMP_RUNNING = "red"
LAMP_STOPPED = "green"

# The run light on the panel is a single lamp, not a pair: it is lit while the
# pump runs and dark otherwise, so "green" would be a colour it cannot show.
LAMP_OFF = "off"

# Why a pump is tripped. The cause outlives the trip because it decides which
# window on the rack is in alongside RCP n TRIP, and it clears on tripreset.
TRIP_MANUAL = "manual"
TRIP_FDR_GROUND_FAULT = "fdr-ground-fault"
TRIP_FDR_MECH = "fdr-mech-relay"
TRIP_LUBE = "lube-system-trouble"
TRIP_UNDERVOLTAGE = "bus-undervoltage"
TRIP_AUX_POWER = "aux-power-loss"

# Trip causes that put the FDR/Mech. Relay Trip window in. Undervoltage belongs
# here because the 27 element sits in the same feeder protection package.
FDR_MECH_CAUSES = (TRIP_FDR_MECH, TRIP_UNDERVOLTAGE)

# What a trip cause reads as on the console.
TRIP_LABELS = {
    TRIP_MANUAL: "operator trip",
    TRIP_FDR_GROUND_FAULT: "feeder ground fault",
    TRIP_FDR_MECH: "feeder protection (electrical/mechanical)",
    TRIP_LUBE: "lube system trouble",
    TRIP_UNDERVOLTAGE: "bus undervoltage",
    TRIP_AUX_POWER: "MCC power loss",
}

# The casualties /fault can insert: the shared supplies, then the same two
# per-pump ones for each of the four. /help fault prints this list.
PUMP_FAULT_SUFFIXES = {
    "mcc-mpl": "MCC main (normal) power loss",
    "mcc-gft": "MCC ground fault - trips main power, lights MCC/FDR Ground Fault",
}
FAULTS = {
    "nbus-1-trip": "NBUS-1 de-energized (feeder + MCC main for RCP 1 and 2)",
    "nbus-2-trip": "NBUS-2 de-energized (feeder + MCC main for RCP 3 and 4)",
    "sbo-bus-1-trip": "SBO-BUS-1 de-energized (MCC alternate for RCP 1 and 2)",
    "sbo-bus-2-trip": "SBO-BUS-2 de-energized (MCC alternate for RCP 3 and 4)",
}
FAULTS.update({
    f"{pump['key']}-{suffix}": f"{pump['name']} {text}"
    for pump in PUMPS
    for suffix, text in PUMP_FAULT_SUFFIXES.items()
})

# What /component <pump> can be told to do, and the trip each action latches.
COMPONENT_ACTIONS = {
    "trip": "trip the pump (no reason given)",
    "tripreset": "reset the trip and let the switch work again",
    "tripfdrgft": "feeder ground fault - trips the pump and swings the MCC to alternate",
    "tripfdrmech": "feeder electrical/mechanical protection trip",
    "triplst": "lube system trouble trip",
}
ACTION_CAUSES = {
    "trip": TRIP_MANUAL,
    "tripfdrgft": TRIP_FDR_GROUND_FAULT,
    "tripfdrmech": TRIP_FDR_MECH,
    "triplst": TRIP_LUBE,
}


def run_lamp_uid(pump):
    """The uid of a pump's run light on the panel.

    Its own SwitchDefinition asset, the same as every other control on the
    panel: "RCP n Run Lamp" under Controls/Definitions/RCS Section, assigned
    to the lamp's prefab instance in MainScene.

    It used to answer to its own GameObject's name instead - a fallback in
    SwitchLampIndicator for a lamp that has no definition and hangs under no
    switch. That bound the wire protocol to a name in the hierarchy, so
    renaming the object in the editor silently unbound the lamp.
    """
    return pump.spec["runlamp"]


class Pump:
    """Everything that is true of one pump right now."""

    def __init__(self, spec):
        self.spec = spec
        self.name = spec["name"]
        self.key = spec["key"]

        self.speed = 0.0            # rpm
        self.breaker_closed = False  # FDR-52
        self.tripped = False
        self.trip_cause = None
        # The switch position seen on the previous tick. A spring-return
        # controller is read for its edges, not its level, and this is what
        # makes one press one command.
        self.last_switch = SW_NORMAL
        self.mcc_source = "normal"   # "normal", "alternate" or None when dead

    @property
    def running(self):
        return self.breaker_closed

    @property
    def amps(self):
        """Motor current. Locked-rotor inrush decaying as the motor comes up."""
        if not self.breaker_closed:
            return 0.0

        fraction = min(1.0, max(0.0, self.speed / RATED_RPM))
        return FLA_AMPS + (LOCKED_ROTOR_AMPS - FLA_AMPS) * (1.0 - fraction ** CURRENT_KNEE)

    @property
    def flow(self):
        """Loop flow. Proportional to shaft speed - no head-flow curve yet."""
        return RATED_FLOW_GPM * (self.speed / RATED_RPM)


class RcpPlant:
    """The RCP electrical system and the four machines on it.

    Module-level singleton (`plant`), the same shape as io_state.state: the sim
    thread ticks it, the console commands in commands.py write to it and the
    annunciator table reads it, so all three take the lock.
    """

    def __init__(self, pumps=None):
        self._lock = threading.RLock()
        self._faults = set()
        self.pumps = [Pump(spec) for spec in (pumps if pumps is not None else PUMPS)]
        self._by_key = {pump.key: pump for pump in self.pumps}

    # ------------------------------------------------------------- supplies

    def bus_energized(self, bus):
        """NBUS {bus}: the 6.9kV feeder supply, and the MCC normal supply."""
        with self._lock:
            return f"nbus-{bus}-trip" not in self._faults

    def sbo_energized(self, sbo):
        """SBO bus {sbo}: the 480V diesel-backed MCC alternate supply."""
        with self._lock:
            return f"sbo-bus-{sbo}-trip" not in self._faults

    def mcc_normal_available(self, pump):
        """The MCC's normal feed: its NBUS, through the group bus and its
        transformer. A feeder ground fault takes this with it - the fault is
        in the switchgear the MCC tap hangs off."""
        with self._lock:
            if not self.bus_energized(pump.spec["bus"]):
                return False
            if f"{pump.key}-mcc-mpl" in self._faults or f"{pump.key}-mcc-gft" in self._faults:
                return False
            return not (pump.tripped and pump.trip_cause == TRIP_FDR_GROUND_FAULT)

    def mcc_alternate_available(self, pump):
        return self.sbo_energized(pump.spec["sbo"])

    def ground_fault(self, pump):
        """Either kind of ground fault - the MCC casualty or the feeder trip."""
        with self._lock:
            return (f"{pump.key}-mcc-gft" in self._faults
                    or (pump.tripped and pump.trip_cause == TRIP_FDR_GROUND_FAULT))

    # ---------------------------------------------------------------- faults

    def faults(self):
        with self._lock:
            return sorted(self._faults)

    def add_fault(self, name):
        name = str(name).strip().lower()
        if name not in FAULTS:
            raise ValueError(f"unknown fault '{name}'")

        with self._lock:
            if name in self._faults:
                return f"{name} is already in"
            self._faults.add(name)

        print(f"[rcp] FAULT INSERTED: {name} - {FAULTS[name]}")
        return f"inserted {name} - {FAULTS[name]}"

    def clear_fault(self, name):
        name = str(name).strip().lower()
        if name not in FAULTS:
            raise ValueError(f"unknown fault '{name}'")

        with self._lock:
            if name not in self._faults:
                return f"{name} is not in"
            self._faults.discard(name)

        print(f"[rcp] fault cleared: {name}")
        return f"cleared {name}"

    def clear_all_faults(self):
        with self._lock:
            count = len(self._faults)
            self._faults.clear()

        if count:
            print(f"[rcp] all {count} fault(s) cleared")
        return f"cleared {count} fault(s)"

    # ------------------------------------------------------------ components

    def component(self, name, action):
        """Run a /component action against one pump. Returns a line to print."""
        key = str(name).strip().lower()
        action = str(action).strip().lower()

        pump = self._by_key.get(key)
        if pump is None:
            raise ValueError(f"unknown component '{name}'")
        if action not in COMPONENT_ACTIONS:
            raise ValueError(
                f"unknown action '{action}' for {key} "
                f"({', '.join(sorted(COMPONENT_ACTIONS))})")

        if action == "tripreset":
            return self._reset_trip(pump)

        return self._trip(pump, ACTION_CAUSES[action], operator=True)

    def _trip(self, pump, cause, operator=False):
        with self._lock:
            if pump.tripped and pump.trip_cause == cause:
                return f"{pump.name} is already tripped ({TRIP_LABELS[cause]})"

            was_running = pump.breaker_closed
            pump.tripped = True
            pump.trip_cause = cause
            pump.breaker_closed = False

        label = TRIP_LABELS[cause]
        print(f"[rcp] {pump.name} TRIPPED - {label}"
              + ("" if was_running else " (was already stopped)"))
        return (f"{pump.name} tripped - {label}"
                + (" (coasting down)" if was_running else " (was already stopped)"))

    def trip_inhibits(self, pump):
        """Standing conditions that seal a trip in, so it will not reset.

        A protective lockout does not hand back while the thing it operated on
        is still there - you clear the casualty, then you reset. So these are
        exactly what _step_protection trips on, read live rather than off the
        cached MCC source.

        Deliberately NOT included is anything that is only true BECAUSE the
        pump is tripped - a feeder ground fault trip makes its own MCC normal
        supply unavailable, and counting that would seal the trip in against
        itself and leave no way out.

        Nor is an MCC ground fault. 50G at the LV main trips MCC-52 and stops
        there - selectivity, and the motor sits in a different zone behind
        FDR-52 - so it never reaches the motor's protection and has no trip to
        seal in. It shows as MCC MAIN POWER LOSS with the ATS carrying the
        auxiliaries on the alternate, and the pump resets and restarts with
        that window still in. Only losing BOTH MCC feeds blocks a reset, and
        the aux-power case below already covers that.
        """
        reasons = []

        with self._lock:
            if not self.bus_energized(pump.spec["bus"]):
                reasons.append(TRIP_UNDERVOLTAGE)

            # The MCC dead on BOTH supplies, which is the aux power loss trip.
            # Main power loss alone is not: the alternate carries it, and
            # _step_protection doesn't trip on it either.
            if not (self.mcc_normal_available(pump) or self.mcc_alternate_available(pump)):
                reasons.append(TRIP_AUX_POWER)

        return reasons

    def _reset_trip(self, pump):
        with self._lock:
            if not pump.tripped:
                return f"{pump.name} is not tripped"

            inhibits = self.trip_inhibits(pump)
            if inhibits:
                reasons = ", ".join(TRIP_LABELS[cause] for cause in inhibits)
                print(f"[rcp] {pump.name} trip reset REFUSED - {reasons}")
                return (f"{pump.name} trip will not reset - {reasons}. "
                        "The lockout is sealed in while the condition is there; "
                        "clear it and reset again.")

            cause = pump.trip_cause
            pump.tripped = False
            pump.trip_cause = None

        print(f"[rcp] {pump.name} trip reset ({TRIP_LABELS[cause]})")
        return f"{pump.name} trip reset - START to restart"

    # ----------------------------------------------------------------- reads

    def pump(self, key):
        return self._by_key.get(str(key).strip().lower())

    def status_lines(self):
        """A console-readable dump of everything with no panel indication."""
        with self._lock:
            lines = [
                "  NBUS-1 {:<11}  NBUS-2 {}".format(
                    "ENERGIZED" if self.bus_energized(1) else "DEAD",
                    "ENERGIZED" if self.bus_energized(2) else "DEAD"),
                "  SBO-1  {:<11}  SBO-2  {}".format(
                    "ENERGIZED" if self.sbo_energized(1) else "DEAD",
                    "ENERGIZED" if self.sbo_energized(2) else "DEAD"),
                "",
                "  pump   switch  breaker    speed     amps      flow  MCC        trip",
            ]

            for pump in self.pumps:
                trip = TRIP_LABELS[pump.trip_cause] if pump.tripped else "-"

                lines.append(
                    "  {:<6} {:<7} {:<8} {:>5.0f} rpm {:>5.0f} A {:>6.0f}k  {:<10} {}".format(
                        pump.name, self._switch_label(pump),
                        "CLOSED" if pump.breaker_closed else "open",
                        pump.speed, pump.amps, pump.flow / 1000.0,
                        (pump.mcc_source or "DEAD").upper(), trip).rstrip())

            faults = sorted(self._faults)
            lines.append("")
            lines.append("  faults: " + (", ".join(faults) if faults else "none"))
            return lines

    # ------------------------------------------------------------------ tick

    def step(self, dt):
        """Advance the whole plant one tick. Called by RcpSimulation."""
        with self._lock:
            for pump in self.pumps:
                self._step_pump(pump, dt)

    def _step_pump(self, pump, dt):
        self._step_supply(pump)
        self._step_protection(pump)
        self._step_breaker(pump)
        self._step_speed(pump, dt)

    def _step_supply(self, pump):
        """Pick the MCC's source. Break-before-make, and fast enough that the
        contactors hold in, so there is no dead interval to model."""
        if self.mcc_normal_available(pump):
            source = "normal"
        elif self.mcc_alternate_available(pump):
            source = "alternate"
        else:
            source = None

        if source == pump.mcc_source:
            return

        was, pump.mcc_source = pump.mcc_source, source
        if source is None:
            print(f"[rcp] {pump.name} MCC DEAD - no normal, no alternate")
        elif was is None:
            print(f"[rcp] {pump.name} MCC re-energized on {source}")
        else:
            print(f"[rcp] {pump.name} MCC transferred {was} -> {source}")

    def _step_protection(self, pump):
        """Trips that come out of the plant rather than off the console."""
        if not pump.breaker_closed:
            return

        if not self.bus_energized(pump.spec["bus"]):
            self._trip(pump, TRIP_UNDERVOLTAGE)
        elif pump.mcc_source is None:
            # No jacking oil, no lube oil support, no machine instrumentation.
            self._trip(pump, TRIP_AUX_POWER)

    def _step_breaker(self, pump):
        """FDR-52, driven by the two momentary ends of the control switch.

        Edges, not levels. The switch springs back to NORMAL on its own, so one
        press shows up as several ticks parked on an end - acting on the level
        would re-close the breaker on every one of them. Worse, it would close
        it the moment a start permissive came back while the operator's hand
        was still on START, which is the unattended restart the maintained
        switch needed its out-of-correspondence rule to prevent.
        """
        position = self._switch_position(pump)
        moved, pump.last_switch = position != pump.last_switch, position

        # Sitting still, or springing back through the middle: not a command.
        if not moved or position == SW_NORMAL:
            return

        if position == SW_TRIP:
            # The control switch opens the breaker and latches nothing. Only
            # protection drives a lockout, and this is not protection.
            if pump.breaker_closed:
                pump.breaker_closed = False
                print(f"[rcp] {pump.name} stopped - coasting down")
            else:
                print(f"[rcp] {pump.name} TRIP pressed - already stopped")
            return

        if pump.breaker_closed:
            print(f"[rcp] {pump.name} START pressed - already running")
            return

        blocked = self._start_block_reason(pump)
        if blocked:
            print(f"[rcp] {pump.name} START refused - {blocked}")
            return

        pump.breaker_closed = True
        print(f"[rcp] {pump.name} started - running up")

    def _step_speed(self, pump, dt):
        """First-order lag both ways: motor torque up, flywheel down."""
        target = RATED_RPM if pump.breaker_closed else 0.0
        tau = RUNUP_TAU if target > pump.speed else COASTDOWN_TAU

        # Exponential approach, integrated exactly over the tick so the result
        # doesn't depend on how often we are called.
        pump.speed += (target - pump.speed) * (1.0 - math.exp(-dt / tau))
        if abs(target - pump.speed) < SNAP_RPM:
            pump.speed = target

    def _start_block_reason(self, pump):
        """Why START would not take, or None if it would.

        RCP{n}-START-PERM, trimmed to what this sim models. A reason rather
        than a bool because the switch is momentary: one that silently does
        nothing leaves the operator unable to tell a refused start from a press
        too short for the server to have seen at all.
        """
        if pump.tripped:
            return f"tripped ({TRIP_LABELS[pump.trip_cause]}) - reset it first"
        if not self.bus_energized(pump.spec["bus"]):
            return f"NBUS-{pump.spec['bus']} dead"
        if pump.mcc_source is None:
            return "MCC dead - no jacking oil, no lube oil support"
        return None

    def _start_permitted(self, pump):
        return self._start_block_reason(pump) is None

    @staticmethod
    def _switch_position(pump):
        entry = state.get_switch(pump.spec["power"])
        return entry["position"] if entry else SW_NORMAL

    def _switch_label(self, pump):
        return SWITCH_LABELS.get(self._switch_position(pump), "?")


plant = RcpPlant()


# ------------------------------------------------------------------- alarms

def _window(pump, suffix):
    """The rack id for one of this pump's windows: RCP 1 -> RCP_1_TRIP."""
    return f"{pump.name.upper().replace(' ', '_')}_{suffix}"


def alarm_conditions():
    """(window id, condition) rows for the annunciator table.

    Conditions, not windows: annunciator_sim.py owns the alarm/acknowledge/
    ringback sequence, so an alarm raised here behaves like every other one on
    the rack instead of being driven straight to lit from the side.
    """
    rows = []

    for bus in (1, 2):
        rows.append((f"NBUS_{bus}_POWER_LOSS",
                     lambda bus=bus: not plant.bus_energized(bus)))

    for pump in plant.pumps:
        rows += [
            (_window(pump, "TRIP"),
             lambda p=pump: p.tripped),
            (_window(pump, "FDR_MECH_RELAY_TRIP"),
             lambda p=pump: p.tripped and p.trip_cause in FDR_MECH_CAUSES),
            (_window(pump, "MCC_FDR_GROUND_FAULT"),
             lambda p=pump: plant.ground_fault(p)),
            (_window(pump, "LUBE_SYSTEM_TROUBLE"),
             lambda p=pump: p.tripped and p.trip_cause == TRIP_LUBE),
            (_window(pump, "MCC_MAIN_POWER_LOSS"),
             lambda p=pump: not plant.mcc_normal_available(p)),
            (_window(pump, "MCC_AUX_POWER_LOSS"),
             lambda p=pump: not plant.mcc_alternate_available(p)),
        ]

    return rows


# --------------------------------------------------------------- the thread

class RcpSimulation:
    def __init__(self, tick=TICK_SECONDS):
        # The module singleton rather than one of its own: commands.py writes to
        # it and alarm_conditions() reads it, and a second model would leave the
        # console driving a plant nobody is publishing.
        self.plant = plant
        self.tick = tick

        self._stop = threading.Event()
        self._thread = None

    def ensure_definitions(self):
        """Create or correct the switch, lamp and gauge definitions.

        Gauges are checked against their scale rather than just their presence:
        these two used to be 0-80 Hz frequency dials, and an entry left over
        from that in data/io_definitions.json would clamp flow to 80 gpm.
        """
        written = 0

        for pump in self.plant.pumps:
            spec = pump.spec
            if state.get_switch(spec["power"]) is None:
                state.define_switch(
                    spec["power"], id=f"{pump.name} Power", name=f"{pump.name} Power",
                    positions=[SW_TRIP, SW_NORMAL, SW_START],
                    position=SW_NORMAL, save=False)
                written += 1

            # The lamp pair answers to the switch's own uid (SwitchLampIndicator
            # binds to the switch it hangs under), so indicator and switch share
            # one. Green from the start: the breaker is open.
            if state.get_indicator(spec["power"]) is None:
                state.define_indicator(
                    spec["power"], id=f"{pump.name} Lamps", name=f"{pump.name} Lamps",
                    state=LAMP_STOPPED, save=False)
                written += 1

            # The run light standing on the panel, which is its own lamp rather
            # than half of the switch's pair - so it has a uid of its own.
            run_lamp = run_lamp_uid(pump)
            if state.get_indicator(run_lamp) is None:
                state.define_indicator(
                    run_lamp, id=f"{pump.name} Run Lamp",
                    name=f"{pump.name} Run Lamp", state=LAMP_OFF, save=False)
                written += 1

            written += self._ensure_gauge(
                spec["amps"], f"{pump.name} Current", "A", AMMETER_MAX_A)
            written += self._ensure_gauge(
                spec["flow"], f"{pump.name} Flow", "gpm", FLOW_GAUGE_MAX_GPM)

        if written:
            state.save()
            print(f"[rcp] defined {written} RCP entr{'y' if written == 1 else 'ies'}")

    @staticmethod
    def _ensure_gauge(uid, name, units, max_value):
        entry = state.get_gauge(uid)
        if entry is not None and entry["maxValue"] == max_value and entry["units"] == units:
            return 0

        state.define_gauge(uid, id=name, name=name, units=units,
                           min_value=0.0, max_value=max_value, value=0.0, save=False)
        return 1

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
            self.plant.step(now - last)
            last = now
            self._publish()

    def _publish(self):
        """Push the model onto the panel: two gauges and two lamps per pump."""
        for pump in self.plant.pumps:
            spec = pump.spec
            state.set_gauge(spec["amps"], pump.amps)
            state.set_gauge(spec["flow"], pump.flow)

            # The switch's pair: red closed, green open. The switch is back
            # at NORMAL either way, so these lamps are the breaker indication.
            state.set_indicator(
                spec["power"], LAMP_RUNNING if pump.breaker_closed else LAMP_STOPPED)

            # The run light: lit while the machine is actually turning its
            # breaker, dark otherwise. One lamp, so it has no "stopped" colour.
            state.set_indicator(
                run_lamp_uid(pump), LAMP_RUNNING if pump.breaker_closed else LAMP_OFF)
