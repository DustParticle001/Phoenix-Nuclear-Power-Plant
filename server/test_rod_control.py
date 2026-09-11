"""Check rod control: the overlap sequence, the rod stops, and the power model.

    python server/test_rod_control.py

Drives the real RodCore from rod_sim.py, with io_state pointed at a temp file so
data/io_definitions.json is never touched. The two switches are moved the way
the client moves them - a detent on the selector, a held lever - because that is
the whole interface the sim has.

What is under test, in order:

  * the control banks will not withdraw until all four shutdown banks are out
  * the overlap program - the next bank starts at 128 steps, never a third
    alongside, and insertion runs the same sequence backwards
  * a bank selected on its own moves alone and defeats the sequence
  * one bump of the lever is one whole step, because a magnetic jack has no
    smaller move than that
  * manual rod speed
  * the rod stops: C-2 on flux, C-5 on automatic withdrawal at low load, and
    that neither of them blocks insertion
  * the reactivity balance - all rods out at 100 % power is critical, all rods
    in leaves shutdown margin
  * boron: only the deviation from nominal carries reactivity, all rods out
    at nominal asks for more than rated, and borating brings it back to 100 %
  * RPS: two trip breakers in series, either one drops the rods, each resets
    on its own button and neither resets into high flux
  * the trip: every bank on the bottom, withdrawal blocked, and the reset
    sealed in while flux is still above the setpoint
  * fast withdraw: it multiplies the LEVER and leaves the automatic speed
    program alone, because that program is a real design parameter
  * the period indicator: the inverse of the startup rate, signed, pegged at
    the ends of the dial when the reactor is steady
  * the dial: engraved the way the real switch is, and agreeing with the
    RotNp in the scene about how many detents there are and where it starts
  * the panel: every bank position and reactor power reach their gauges, and
    the uids in rod_sim.py are the ones the Unity definition assets carry

There is no test runner in this project, so it is a script: it prints what it
did, and exits non-zero with a list of what came out wrong.
"""
import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from io_state import state

state._path = Path(tempfile.mkdtemp()) / "io_definitions.json"

import rod_sim
from rod_sim import (AUTOMATIC, AUTO_BLOCK_LOAD_PCT, AUTO_MAX_STEPS_PER_MIN,
                     BANKS, BANK_GAUGES, BANK_GAUGE_NAMES, CONTROL_BANKS,
                     CONTROL_BANK_OVERLAP, CORE_EXCESS_PCM,
                     DECADES_PER_MINUTE, DEFAULT_SELECTOR, FAST_WITHDRAW,
                     FAST_WITHDRAW_MULTIPLIER, FAST_WITHDRAW_ON,
                     HIGH_FLUX_TRIP_PCT, LEVER, LEVER_HOLD, LEVER_IN,
                     LEVER_OUT, MANUAL, MANUAL_STEPS_PER_MIN, PERIOD,
                     PERIOD_MAX_SECONDS, ROD_DROP_SECONDS, ROD_STOP_PCT,
                     RX_POWER, SELECTIONS, SELECTOR, SELECTOR_LABELS,
                     SELECTOR_POSITIONS, SHUTDOWN_BANKS, STEPS_FULL_OUT,
                     TOTAL_ROD_WORTH_PCM, ARO_POWER_PCT, BORIC_ACID,
                     BORON_NOMINAL_PCT, BORON_WORTH_PCM_PER_PCT, CVCS_BORATE,
                     CVCS_DILUTE, CVCS_HOLD, CVCS_RATE_PCT_PER_SEC,
                     CVCS_SWITCH, POWER_DEFECT_PCM, PRESSED, RPS_RESET,
                     RPS_TRAINS, RPS_TRIP, RodCore, RodSimulation)
from turbine_sim import GEN_LOAD, RATED_LOAD_MW

RodSimulation().ensure_definitions()

failures = []
checks = [0]


def check(label, got, want):
    checks[0] += 1
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def close(label, got, want, tolerance):
    checks[0] += 1
    if abs(got - want) > tolerance:
        failures.append(f"{label}: got {got!r}, want {want!r} +/- {tolerance}")
        print(f"  FAIL {label}: got {got!r}, want {want!r} +/- {tolerance}")


# What the dial is engraved is the panel's business and it has been reordered
# once already, so nothing below names a detent: it asks for MANUAL, AUTOMATIC
# or a bank and gets whichever detent selects it.
DETENTS = {selects: detent for detent, selects in SELECTIONS.items()}


def fresh(selects=MANUAL, power=None):
    """A core with every rod on the bottom and the lever at HOLD."""
    core = RodCore()
    state.set_switch(SELECTOR, position=DETENTS[selects])
    state.set_switch(LEVER, position=LEVER_HOLD)
    state.set_switch(FAST_WITHDRAW, position="off")
    state.set_switch(CVCS_SWITCH, position=CVCS_HOLD)
    for train in RPS_TRAINS:
        state.set_switch(RPS_TRIP[train], position="released")
        state.set_switch(RPS_RESET[train], position="released")
    state.set_gauge(GEN_LOAD, 0.0)
    if power is not None:
        core.power = power
    return core


def turn(selects):
    state.set_switch(SELECTOR, position=DETENTS[selects])


def run(core, seconds, dt=0.25):
    """Tick the core for a while, at a step the whole loop is stable at."""
    ticks = max(1, int(round(seconds / dt)))
    for _ in range(ticks):
        core.step(dt)


def hold(core, end, seconds, dt=0.25):
    """Hold the lever one way for a while, then let it spring back."""
    state.set_switch(LEVER, position=end)
    run(core, seconds, dt=dt)
    state.set_switch(LEVER, position=LEVER_HOLD)
    core.step(dt)


def hold_at_power(core, end, seconds, power, dt=0.25):
    """Hold the lever with power pinned where the test wants it.

    The core recomputes power off the reactivity balance every tick, so a
    single assignment washes out inside a second or two. The rod stops are
    what is under test here, not the power model, so power is held by hand.
    """
    state.set_switch(LEVER, position=end)
    for _ in range(max(1, int(round(seconds / dt)))):
        core.power = power
        core.step(dt)
    state.set_switch(LEVER, position=LEVER_HOLD)
    core.power = power
    core.step(dt)


def press(core, uid, dt=0.02):
    """One push of a pushbutton, and the ticks that see it come and go."""
    state.set_switch(uid, position=PRESSED)
    core.step(dt)
    state.set_switch(uid, position="released")
    core.step(dt)


def park_shutdown_banks_out(core):
    for bank in SHUTDOWN_BANKS:
        core.banks[bank] = STEPS_FULL_OUT


def park_all_out(core):
    for bank in core.banks:
        core.banks[bank] = STEPS_FULL_OUT


# Long enough to run a bank from one stop to the other and have time over.
FULL_TRAVEL_SECONDS = 60.0 * STEPS_FULL_OUT / MANUAL_STEPS_PER_MIN + 30.0


# ---------------------------------------------------------------- the dial

print("\nThe dial is engraved the way the real switch is")

# Pinned rather than derived, because this is the panel's layout and not a
# consequence of anything: shutdown banks at one end, control banks at the
# other, MAN and AUTO in the middle where the switch stands at power.
check("ten detents, in the engraved order",
      [SELECTOR_LABELS[detent] for detent in SELECTOR_POSITIONS],
      ["SA", "SB", "SC", "SD", "MAN", "AUTO", "CA", "CB", "CC", "CD"])
check("every detent selects something", sorted(SELECTIONS) == sorted(SELECTOR_POSITIONS), True)
check("the switch starts on shutdown bank A", SELECTIONS[DEFAULT_SELECTOR], "SA")


# --------------------------------------------------------------- permissive

print("\nThe control banks wait for the shutdown banks")
core = fresh()
hold(core, LEVER_OUT, 30.0)
check("control banks moved with the shutdown banks in",
      [core.banks[bank] for bank in CONTROL_BANKS], [0, 0, 0, 0])
check("the block says why", core.withdrawal_blocked(),
      "shutdown banks not fully withdrawn")

turn("SA")
hold(core, LEVER_OUT, FULL_TRAVEL_SECONDS)
check("shutdown bank A withdrew on its own detent", core.banks["SA"], STEPS_FULL_OUT)
check("and took nothing else with it",
      [core.banks[bank] for bank in ("SB", "SC", "SD")], [0, 0, 0])

park_shutdown_banks_out(core)
check("permissive satisfied with all four out", core.shutdown_banks_withdrawn, True)
check("and the block is gone", core.withdrawal_blocked(), None)


# ------------------------------------------------------------------ overlap

print("\nThe overlap program")
core = fresh()
park_shutdown_banks_out(core)
# Fully borated for the duration. Withdrawing every control bank now asks for
# more than rated, so without this the C-2 rod stop comes in part way through
# and the test would be measuring the interlock instead of the sequence.
core.boron = 100.0

state.set_switch(LEVER, position=LEVER_OUT)
started = {}
most_moving = 0
previous = dict(core.banks)

for _ in range(int(4 * FULL_TRAVEL_SECONDS / 0.25)):
    core.step(0.25)

    moved = [bank for bank in CONTROL_BANKS if core.banks[bank] != previous[bank]]
    most_moving = max(most_moving, len(moved))

    for bank in moved:
        # The position the bank BEFORE this one was at when this one first
        # moved: the overlap, if the sequence is doing its job.
        if bank in started:
            continue
        index = CONTROL_BANKS.index(bank)
        started[bank] = previous[CONTROL_BANKS[index - 1]] if index else 0

    previous = dict(core.banks)

state.set_switch(LEVER, position=LEVER_HOLD)

check("every control bank ends fully withdrawn",
      [core.banks[bank] for bank in CONTROL_BANKS],
      [STEPS_FULL_OUT] * 4)
check("never more than two banks stepping at once", most_moving <= 2, True)
for bank in CONTROL_BANKS[1:]:
    check(f"{bank} started at the overlap", started.get(bank), CONTROL_BANK_OVERLAP)

print("\nInsertion runs the same sequence backwards")
core = fresh()
park_all_out(core)
core.boron = 100.0                 # as above: geometry, not reactivity

state.set_switch(LEVER, position=LEVER_IN)
handover = {}
previous = dict(core.banks)

for _ in range(int(4 * FULL_TRAVEL_SECONDS / 0.25)):
    core.step(0.25)
    for bank in CONTROL_BANKS:
        if core.banks[bank] == previous[bank] or bank in handover:
            continue
        index = CONTROL_BANKS.index(bank)
        # Mirror of the withdrawal: this bank starts back in when the one AFTER
        # it has come down to the last `overlap` steps of its own travel.
        handover[bank] = (previous[CONTROL_BANKS[index + 1]]
                          if index + 1 < len(CONTROL_BANKS) else 0)
    previous = dict(core.banks)

state.set_switch(LEVER, position=LEVER_HOLD)

check("every control bank ends on the bottom",
      [core.banks[bank] for bank in CONTROL_BANKS], [0, 0, 0, 0])
check("the shutdown banks stayed out",
      [core.banks[bank] for bank in SHUTDOWN_BANKS], [STEPS_FULL_OUT] * 4)
for bank in CONTROL_BANKS[:-1]:
    check(f"{bank} picked up when the next bank reached the overlap",
          handover.get(bank), STEPS_FULL_OUT - CONTROL_BANK_OVERLAP)


# -------------------------------------------------------- individual detents

print("\nA control bank on its own detent defeats the sequence")
core = fresh("CD")                 # control bank D alone
park_shutdown_banks_out(core)
hold(core, LEVER_OUT, 30.0)
check("bank D moved", core.banks["CD"] > 0, True)
check("and A, B and C did not",
      [core.banks[bank] for bank in ("CA", "CB", "CC")], [0, 0, 0])


# --------------------------------------------------------------- whole steps

print("\nOne bump of the lever is one whole step")
core = fresh("SA")                 # shutdown bank A, nothing in the way

# Shorter than the 1.25 s a step takes at manual speed, so only the
# jack-pulses-in-whole-steps rule can move anything at all.
hold(core, LEVER_OUT, 0.06, dt=0.02)
check("a brief bump stepped once", core.banks["SA"], 1)

hold(core, LEVER_OUT, 0.06, dt=0.02)
check("a second bump stepped once more", core.banks["SA"], 2)

hold(core, LEVER_IN, 0.06, dt=0.02)
check("a bump the other way stepped back", core.banks["SA"], 1)


print("\nManual rod speed")
core = fresh("SA")
state.set_switch(LEVER, position=LEVER_OUT)
core.step(0.02)                    # the immediate first step
before = core.banks["SA"]
run(core, 60.0)
state.set_switch(LEVER, position=LEVER_HOLD)
close("steps in a minute of holding", core.banks["SA"] - before,
      MANUAL_STEPS_PER_MIN, 1)


# ------------------------------------------------------------ fast withdraw

print("\nFast withdraw multiplies the lever")
core = fresh("SA")
state.set_switch(FAST_WITHDRAW, position=FAST_WITHDRAW_ON)
check("the core sees the switch", core.fast_withdraw(), True)

state.set_switch(LEVER, position=LEVER_OUT)
core.step(0.02)                    # the immediate first step
before = core.banks["SA"]
run(core, 6.0, dt=0.02)
state.set_switch(LEVER, position=LEVER_HOLD)
close("six seconds of holding, at the multiplied rate",
      core.banks["SA"] - before,
      6.0 * MANUAL_STEPS_PER_MIN * FAST_WITHDRAW_MULTIPLIER / 60.0, 2)

print("\nAnd the boric acid control with it")
core = fresh()
state.set_switch(FAST_WITHDRAW, position=FAST_WITHDRAW_ON)
state.set_switch(CVCS_SWITCH, position=CVCS_BORATE)
before = core.boron
run(core, 10.0, dt=0.1)
close("ten seconds of borating, at the multiplied rate", core.boron - before,
      10.0 * CVCS_RATE_PCT_PER_SEC * FAST_WITHDRAW_MULTIPLIER, 0.05)

state.set_switch(CVCS_SWITCH, position=CVCS_DILUTE)
before = core.boron
run(core, 10.0, dt=0.1)
close("and diluting comes back down just as fast", core.boron - before,
      -10.0 * CVCS_RATE_PCT_PER_SEC * FAST_WITHDRAW_MULTIPLIER, 0.05)

state.set_switch(FAST_WITHDRAW, position="off")
before = core.boron
run(core, 10.0, dt=0.1)
close("and out, the shim is back to its own rate", core.boron - before,
      -10.0 * CVCS_RATE_PCT_PER_SEC, 0.05)


print("\nBut it leaves the automatic speed program alone")
core = fresh(AUTOMATIC, power=20.0)
park_shutdown_banks_out(core)
core.banks.update(CA=STEPS_FULL_OUT, CB=STEPS_FULL_OUT, CC=STEPS_FULL_OUT, CD=40)
state.set_gauge(GEN_LOAD, RATED_LOAD_MW * 0.90)   # a big error, so full speed
state.set_switch(FAST_WITHDRAW, position=FAST_WITHDRAW_ON)

before = core.banks["CD"]
run(core, 10.0, dt=0.02)
moved = core.banks["CD"] - before
check("the controller withdrew", moved > 0, True)
check("at its own top speed, not 20x it",
      moved <= 10.0 * AUTO_MAX_STEPS_PER_MIN / 60.0 + 2, True)


# ---------------------------------------------------------------- the period

print("\nThe period indicator")
core = fresh()
park_all_out(core)
core.power = ARO_POWER_PCT
core.step(0.02)
check("all rods out at the ARO power point is steady", core.sur, 0.0)
check("so the needle sits at the long-period end", core.period, PERIOD_MAX_SECONDS)

core = fresh()                     # every rod in: deeply subcritical
core.power = 50.0
core.step(0.02)
check("power falling reads negative", core.period < 0, True)
close("and it is the inverse of the startup rate",
      core.period, DECADES_PER_MINUTE / core.sur, 0.01)
check("inside the dial", abs(core.period) <= PERIOD_MAX_SECONDS, True)

core = fresh()                     # all rods out, well under the ARO point
park_all_out(core)
core.power = 90.0
core.step(0.02)
check("power rising reads positive", core.period > 0, True)
close("and it is the inverse of the startup rate",
      core.period, DECADES_PER_MINUTE / core.sur, 0.01)
check("inside the dial", core.period < PERIOD_MAX_SECONDS, True)

core = fresh()                     # nearly there: a period longer than the dial
park_all_out(core)
core.power = ARO_POWER_PCT - 1.0
core.step(0.02)
check("a period past the end of the dial reads at the end",
      core.period, PERIOD_MAX_SECONDS)
check("even though the reactor is genuinely rising", core.sur > 0, True)


# ---------------------------------------------------------------- rod stops

print("\nC-2: flux high blocks withdrawal, not insertion")
core = fresh(power=ROD_STOP_PCT + 2.0)
park_shutdown_banks_out(core)
core.banks.update(CA=STEPS_FULL_OUT, CB=STEPS_FULL_OUT, CC=STEPS_FULL_OUT, CD=100)

check("the rod stop is in", core.withdrawal_blocked() is not None, True)
check("and it is C-2 that says so",
      "C-2" in (core.withdrawal_blocked() or ""), True)

was = core.banks["CD"]
hold_at_power(core, LEVER_OUT, 10.0, ROD_STOP_PCT + 2.0)
check("withdrawal refused", core.banks["CD"], was)

hold_at_power(core, LEVER_IN, 10.0, ROD_STOP_PCT + 2.0)
check("insertion allowed", core.banks["CD"] < was, True)

print("\nC-5: no automatic withdrawal at low load")
core = fresh(AUTOMATIC, power=20.0)
park_shutdown_banks_out(core)
core.banks.update(CA=STEPS_FULL_OUT, CB=STEPS_FULL_OUT, CC=STEPS_FULL_OUT, CD=100)
state.set_gauge(GEN_LOAD, 0.0)             # generator off the grid

check("C-5 is in with the machine off the grid",
      core.withdrawal_blocked() is not None, True)
check("and it is C-5 that says so",
      "C-5" in (core.withdrawal_blocked() or ""), True)

state.set_gauge(GEN_LOAD, RATED_LOAD_MW * (AUTO_BLOCK_LOAD_PCT + 20.0) / 100.0)
check("C-5 clears above the load", core.withdrawal_blocked(), None)

print("\nIn AUTO the lever is bypassed and the controller chases the load")
core = fresh(AUTOMATIC, power=35.0)
park_shutdown_banks_out(core)
core.banks.update(CA=STEPS_FULL_OUT, CB=STEPS_FULL_OUT, CC=STEPS_FULL_OUT, CD=110)
state.set_gauge(GEN_LOAD, RATED_LOAD_MW * 0.60)

# The lever held the WRONG way: the controller wants power up, and it gets it.
hold(core, LEVER_IN, 900.0)
close("automatic control settled on the turbine's load", core.power, 60.0, 2.0)
check("selector still reads AUTO", core.selection(), AUTOMATIC)


# -------------------------------------------------------------------- boron

print("\nBoron carries only its deviation from nominal")
core = fresh()
park_all_out(core)
core.power = 0.0
close("nominal boron is worth nothing", core.boron_worth, 0.0, 0.01)

core.boron = BORON_NOMINAL_PCT + 10.0
close("borating above nominal holds the core down",
      core.boron_worth, 10.0 * BORON_WORTH_PCM_PER_PCT, 0.01)
core.boron = BORON_NOMINAL_PCT - 10.0
close("diluting below it adds reactivity",
      core.boron_worth, -10.0 * BORON_WORTH_PCM_PER_PCT, 0.01)

print("\nAll rods out at nominal boron asks for more than rated")
core = fresh()
park_all_out(core)
core.power = ARO_POWER_PCT
close("which is where it is critical", core.reactivity, 0.0, 1.0)
check("and that is above the high flux trip, so it trips on the way",
      ARO_POWER_PCT > HIGH_FLUX_TRIP_PCT, True)

print("\nBorating brings it back to rated")
core = fresh()
park_all_out(core)
core.power = 100.0
core.boron = BORON_NOMINAL_PCT + (
    (ARO_POWER_PCT - 100.0) * POWER_DEFECT_PCM / 100.0 / BORON_WORTH_PCM_PER_PCT)
close("critical at 100 %", core.reactivity, 0.0, 1.0)
run(core, 600.0, dt=1.0)
close("and it stays there", core.power, 100.0, 0.2)

print("\nThe CVCS switch borates and dilutes while it is held")
core = fresh()
state.set_switch(CVCS_SWITCH, position=CVCS_BORATE)
before = core.boron
run(core, 20.0, dt=0.1)
close("borating raises the reading", core.boron - before,
      20.0 * CVCS_RATE_PCT_PER_SEC, 0.05)

state.set_switch(CVCS_SWITCH, position=CVCS_DILUTE)
before = core.boron
run(core, 20.0, dt=0.1)
close("diluting lowers it", core.boron - before,
      -20.0 * CVCS_RATE_PCT_PER_SEC, 0.05)

state.set_switch(CVCS_SWITCH, position=CVCS_HOLD)
before = core.boron
run(core, 20.0, dt=0.1)
check("and centre holds it", core.boron, before)

core.boron = 99.9
state.set_switch(CVCS_SWITCH, position=CVCS_BORATE)
run(core, 30.0, dt=0.1)
check("the reading stops at the top of its range", core.boron, 100.0)


# ---------------------------------------------------------------------- RPS

print("\nTwo trip breakers, in series")
core = fresh()
park_all_out(core)
core.power = 50.0
check("both closed to start", core.rps_closed, {"A": True, "B": True})
check("so not tripped", core.tripped, False)

press(core, RPS_TRIP["A"])
check("A's button opens A", core.rps_closed, {"A": False, "B": True})
check("and one open breaker is a trip", core.tripped, True)

run(core, ROD_DROP_SECONDS + 0.5, dt=0.05)
check("every bank on the bottom", sorted(set(core.banks.values())), [0])

press(core, RPS_RESET["B"])
check("B's reset does nothing to A", core.rps_closed, {"A": False, "B": True})
press(core, RPS_RESET["A"])
check("A's reset closes A", core.rps_closed, {"A": True, "B": True})
check("and the reactor is back", core.tripped, False)

press(core, RPS_TRIP["B"])
check("B's button opens B", core.rps_closed, {"A": True, "B": False})
check("which is equally a trip", core.tripped, True)
press(core, RPS_RESET["B"])
check("and resets", core.rps_closed, {"A": True, "B": True})

print("\nA breaker will not reset into high flux")
core = fresh()
park_all_out(core)
core.power = 50.0
press(core, RPS_TRIP["A"])
core.power = HIGH_FLUX_TRIP_PCT + 1.0
press(core, RPS_RESET["A"])
check("refused while the flux that would trip it is still there",
      core.rps_closed["A"], False)
core.power = 1.0
press(core, RPS_RESET["A"])
check("and taken once it is down", core.rps_closed["A"], True)

print("\nA button held down is still one command")
core = fresh()
park_all_out(core)
core.power = 50.0
state.set_switch(RPS_TRIP["A"], position=PRESSED)
run(core, 5.0, dt=0.02)
press(core, RPS_RESET["A"])       # reset with the trip button still down
check("the held trip button did not re-open it", core.rps_closed["A"], True)
state.set_switch(RPS_TRIP["A"], position="released")


# -------------------------------------------------------- reactivity balance

print("\nThe reactivity balance")
core = fresh()
park_all_out(core)
core.power = ARO_POWER_PCT
close("all rods out at nominal boron is critical at the ARO power point",
      core.reactivity, 0.0, 1.0)
close("no worth left inserted", core.rod_worth_inserted, 0.0, 1.0)

core = fresh()
core.power = 0.0
close("all rods in is the whole rod worth", core.rod_worth_inserted,
      TOTAL_ROD_WORTH_PCM, 1.0)
close("which leaves this much shutdown margin", core.reactivity,
      CORE_EXCESS_PCM - TOTAL_ROD_WORTH_PCM, 1.0)
check("comfortably more than the 1770 pcm a W plant needs",
      core.reactivity < -1770.0, True)

print("\nPulled rods make power, and C-2 stops the pull")
core = fresh()
park_shutdown_banks_out(core)
state.set_switch(LEVER, position=LEVER_OUT)
run(core, 4 * FULL_TRAVEL_SECONDS)
state.set_switch(LEVER, position=LEVER_HOLD)
run(core, 60.0)
# Holding the lever out at nominal boron does NOT get you to all rods out any
# more: the banks ask for more than rated on the way, and C-2 blocks the
# withdrawal at 103 % with a bank still part way there. The interlock beats the
# operator, which is what it is for - the ways past it are to borate first, or
# to cheat with FAST WITHDRAW, which outruns the power rise.
# A little ABOVE the setpoint, not on it: the reactivity already withdrawn goes
# on pushing after the block lands, until the power defect balances it.
check("power stalls above the C-2 setpoint", core.power > ROD_STOP_PCT, True)
check("and short of the trip", core.power < HIGH_FLUX_TRIP_PCT, True)
check("with the rod stop standing",
      "C-2" in (core.withdrawal_blocked() or ""), True)
check("a control bank still short of the top",
      any(core.banks[bank] < STEPS_FULL_OUT for bank in CONTROL_BANKS), True)
check("and no trip - the rod stop got there first", core.tripped, False)


# -------------------------------------------------------------------- trip

print("\nThe trip")
core = fresh()
park_all_out(core)
core.power = 100.0
core.trip("test")

check("tripped", core.tripped, True)
run(core, ROD_DROP_SECONDS + 0.5, dt=0.05)
check("every bank on the bottom", sorted(set(core.banks.values())), [0])
check("withdrawal blocked while tripped",
      core.withdrawal_blocked(), "the reactor is tripped")

was = dict(core.banks)
hold(core, LEVER_OUT, 30.0)
check("and the lever does nothing", core.banks, was)

core.power = HIGH_FLUX_TRIP_PCT + 1.0
reply = core.component("reset")
check("reset refused while flux is still up", core.tripped, True)
check("and it says so", "will not reset" in reply, True)

core.power = 1.0
core.component("reset")
check("reset once flux is down", core.tripped, False)

turn("SA")
hold(core, LEVER_OUT, 30.0)
check("and the banks withdraw again", core.banks["SA"] > 0, True)

print("\nThe protection picks the trip up on its own")
core = fresh()
park_all_out(core)
# Put power over the setpoint and let the sim take its own tick: the trip has
# to come out of _step_protection rather than out of the test.
core.power = HIGH_FLUX_TRIP_PCT + 0.5
core.step(0.02)
check("tripped on power range flux high", core.tripped, True)


# ------------------------------------------------------------------- panel

print("\nEvery bank reaches its position meter, and power reaches the APRM")
sim = RodSimulation()
park_all_out(sim.core)
sim.core.banks.update(CC=140, CD=17)
sim.core.power = 87.5
sim._publish()

for bank in BANKS:
    entry = state.get_gauge(BANK_GAUGES[bank])
    check(f"{bank} on {BANK_GAUGE_NAMES[bank]}",
          entry["value"], float(sim.core.banks[bank]))
    check(f"{BANK_GAUGE_NAMES[bank]} reads to full travel",
          (entry["minValue"], entry["maxValue"], entry["units"]),
          (0.0, float(STEPS_FULL_OUT), "STEPS"))

power = state.get_gauge(RX_POWER)
check("reactor power on the APRM", power["value"], 87.5)
check("the APRM reads 0-120 %",
      (power["minValue"], power["maxValue"], power["units"]), (0.0, 120.0, "%"))

period = state.get_gauge(PERIOD)
check("the period on its own dial", period["value"], sim.core.period)
check("which is the only gauge here that goes negative",
      (period["minValue"], period["maxValue"], period["units"]),
      (-PERIOD_MAX_SECONDS, PERIOD_MAX_SECONDS, "s"))

print("\nThe uids here are the ones the Unity definitions carry")

# Reads the SwitchDefinition / GaugeDefinition assets straight off disk. Every
# uid in this module is hand-maintained on both sides, and a typo in one is
# invisible until you are standing in the control room wondering why a needle
# never moves - so it is worth a check that costs nothing.
#
# The whole Definitions tree, NOT one named folder: the rod section has already
# been renamed once (Rod Section -> MRCS Section), and a check keyed on the
# folder name went quiet instead of failing. Sections get renamed; uids don't.
DEFINITIONS = (Path(__file__).resolve().parent.parent
               / "client" / "unbuilt" / "Assets" / "Controls" / "Definitions")

if not DEFINITIONS.is_dir():
    print(f"  SKIPPED - no {DEFINITIONS} (server checked out on its own?)")
else:
    assets, homes = {}, {}
    for path in sorted(DEFINITIONS.rglob("*.asset")):
        if path.parent.name in ("images", "materials"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        found = re.search(r"^  _id: (\S*)\s*$", text, re.MULTILINE)
        assets[path.stem] = found.group(1) if found else ""
        homes[path.stem] = path.parent.name

    wanted = dict(
        [("Rod Bank Selector", SELECTOR),
         ("Rod Control Lever", LEVER),
         ("Fast Withdraw", FAST_WITHDRAW),
         ("APRM", RX_POWER),
         ("Period", PERIOD),
         ("boric acid control switch", CVCS_SWITCH),
         ("Boric Acid", BORIC_ACID)]
        + [(BANK_GAUGE_NAMES[bank], BANK_GAUGES[bank]) for bank in BANKS]
        + [(f"RPS {train} Trip", RPS_TRIP[train]) for train in RPS_TRAINS]
        + [(f"RPS {train} Close", RPS_RESET[train]) for train in RPS_TRAINS])

    for name, uid in wanted.items():
        check(f"{name}.asset carries the uid rod_sim.py uses",
              assets.get(name), uid)

    # Only the sections this module owns: a definition elsewhere with no uid is
    # somebody else's unfinished business, not a failure here.
    mine = {name for name in assets if name in wanted}
    unassigned = sorted(name for name in mine if not assets[name])
    check("none of them is left without a uid", unassigned, [])

    # Period shipped once as a copy of APRM, uid and all, which puts two
    # needles on one signal and reads reactor power on a period dial. Nothing
    # in the client complains: gauges are allowed to share a uid on purpose.
    counts = {}
    for name in mine:
        counts.setdefault(assets[name], []).append(name)
    shared = sorted(sorted(names) for uid, names in counts.items() if len(names) > 1)
    check("and no two of them share a uid", shared, [])

    # The client reports its own detent on the first sync, so a RotNp whose
    # count or start detent has drifted from this module beats the server
    # silently: too few detents and the far end of the dial is unreachable,
    # the wrong start and the plant loads with the selector somewhere else.
    scene = DEFINITIONS.parent.parent / "Scenes" / "MainScene.unity"
    if not scene.is_file():
        print(f"  SKIPPED - no {scene}")
    else:
        rotnp = scene.read_text(encoding="utf-8", errors="replace").split(
            "m_EditorClassIdentifier: Assembly-CSharp::RotNp")
        check("exactly one RotNp in the scene", len(rotnp), 2)

        fields = dict(re.findall(r"^  (_positionCount|_defaultPosition): (\d+)$",
                                 rotnp[-1], re.MULTILINE))
        check("the scene's RotNp has as many detents as the dial has",
              fields.get("_positionCount"), str(len(SELECTOR_POSITIONS)))
        check("and starts on the detent this module starts on",
              fields.get("_defaultPosition"),
              str(SELECTOR_POSITIONS.index(DEFAULT_SELECTOR) + 1))


# ------------------------------------------------------------------ verdict

print(f"\n{checks[0]} checks, {len(failures)} failed")
if failures:
    print("\nFAILURES")
    for line in failures:
        print(f"  - {line}")
    sys.exit(1)

print("All good.")
