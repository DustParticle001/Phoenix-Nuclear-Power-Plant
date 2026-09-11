"""Check the RCP trip lockout: run it, read the output, see the interlock hold.

    python server/test_rcp_trip.py

Drives the real RcpPlant from rcp_sim.py, with io_state pointed at a temp file so
data/io_definitions.json is never touched. The casualties are the same ones
/fault and /component raise from the console.

The rule under test: a trip will not reset while a condition that would raise it
is still standing. You clear the casualty, then you reset - a protective lockout
does not hand back onto a live fault.

There is no test runner in this project, so it is a script: it prints what it
did, and exits non-zero with a list of what came out wrong.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from io_state import state

state._path = Path(tempfile.mkdtemp()) / "io_definitions.json"

from rcp_sim import (RcpPlant, SW_NORMAL, SW_START, SW_TRIP, TRIP_AUX_POWER,
                     TRIP_FDR_GROUND_FAULT, TRIP_MANUAL, TRIP_UNDERVOLTAGE,
                     run_lamp_uid)

failures = []
checks = [0]


def check(label, got, want):
    checks[0] += 1
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def press(plant, pump, end):
    """One momentary press of the control switch, and the ticks that see it.

    The real switch is held for a moment and springs back, which is what the
    server sees: an end for a tick or two, then centre again. Driving the
    position straight to an end and leaving it there would test a switch that
    does not exist.
    """
    state.set_switch(pump.spec["power"], position=end)
    plant.step(0.1)
    plant.step(0.1)
    state.set_switch(pump.spec["power"], position=SW_NORMAL)
    plant.step(0.1)


def fresh():
    """A plant with RCP 1 running and everything healthy.

    Started the way an operator starts one - a press of START - rather than by
    setting breaker_closed by hand.
    """
    plant = RcpPlant()
    pump = plant.pump("rcp-1")
    state.define_switch(pump.spec["power"], positions=[SW_TRIP, SW_NORMAL, SW_START],
                        position=SW_NORMAL, save=False)
    plant.step(0.1)        # supply picks a source
    press(plant, pump, SW_START)
    assert pump.breaker_closed, "the pump should be running before the test starts"
    return plant, pump


def reset(plant, pump):
    return plant.component(pump.key, "tripreset")


# ---------------------------------------------------------------------------
print("1. a clean trip resets")
plant, pump = fresh()
plant.component("rcp-1", "trip")
check("tripped", (pump.tripped, pump.trip_cause), (True, TRIP_MANUAL))
check("inhibits none", plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset", pump.tripped, False)

# ---------------------------------------------------------------------------
print("2. the user's case: MCC dead on both supplies seals the trip in")
plant, pump = fresh()
plant.add_fault("rcp-1-mcc-mpl")      # MCC main power loss
plant.add_fault("sbo-bus-1-trip")     # and the alternate is gone too
plant.step(0.1)
check("tripped on aux power loss",
      (pump.tripped, pump.trip_cause), (True, TRIP_AUX_POWER))
check("inhibited", plant.trip_inhibits(pump), [TRIP_AUX_POWER])
line = reset(plant, pump)
check("reset refused", pump.tripped, True)
check("and says why", "will not reset" in line and "MCC power loss" in line, True)

print("   restore the alternate -> the lockout hands back")
plant.clear_fault("sbo-bus-1-trip")
plant.step(0.1)
check("no longer inhibited", plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset", pump.tripped, False)

# ---------------------------------------------------------------------------
print("3. main power loss ALONE does not seal it in - the alternate carries it")
plant, pump = fresh()
plant.add_fault("rcp-1-mcc-mpl")
plant.step(0.1)
check("still running on the alternate", pump.breaker_closed, True)
plant.component("rcp-1", "trip")
check("inhibits none", plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset", pump.tripped, False)

# ---------------------------------------------------------------------------
print("4. a dead bus seals it in")
plant, pump = fresh()
plant.add_fault("nbus-1-trip")
plant.step(0.1)
check("tripped on undervoltage",
      (pump.tripped, pump.trip_cause), (True, TRIP_UNDERVOLTAGE))
# Only undervoltage: the bus is dead but the MCC has swung to its SBO
# alternate, so the aux supply is still there.
check("inhibited by the dead bus", plant.trip_inhibits(pump), [TRIP_UNDERVOLTAGE])
reset(plant, pump)
check("reset refused", pump.tripped, True)

plant.clear_fault("nbus-1-trip")
plant.step(0.1)
reset(plant, pump)
check("reset once the bus is back", pump.tripped, False)

# ---------------------------------------------------------------------------
print("5. an MCC ground fault swings to the alternate and seals nothing in")
# 50G at the LV main trips MCC-52 and stops there. The motor is behind FDR-52
# in another zone, so the pump runs straight through it and a trip taken for
# any other reason still resets with the ground fault standing.
plant, pump = fresh()
plant.add_fault("rcp-1-mcc-gft")
plant.step(0.1)
check("normal feed gone", plant.mcc_normal_available(pump), False)
check("carried on the alternate", pump.mcc_source, "alternate")
check("still running", pump.breaker_closed, True)
check("MCC/FDR Ground Fault window in", plant.ground_fault(pump), True)

plant.component("rcp-1", "trip")
check("nothing inhibits", plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset with the ground fault still in", pump.tripped, False)

# Take the alternate away too and the MCC is dead on both feeds. THAT trips
# the pump and blocks the reset - and giving the alternate back is enough to
# clear it, without touching the ground fault.
plant, pump = fresh()
plant.add_fault("sbo-bus-1-trip")
plant.step(0.1)
check("still on normal", pump.mcc_source, "normal")

plant.add_fault("rcp-1-mcc-gft")
plant.step(0.1)
check("MCC dead", pump.mcc_source, None)
check("tripped on aux power loss",
      (pump.tripped, pump.trip_cause), (True, TRIP_AUX_POWER))
check("inhibited while both feeds are gone",
      plant.trip_inhibits(pump), [TRIP_AUX_POWER])
reset(plant, pump)
check("reset refused", pump.tripped, True)

plant.clear_fault("sbo-bus-1-trip")
plant.step(0.1)
check("back on the alternate", pump.mcc_source, "alternate")
check("nothing inhibits now", plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset with the MCC ground fault still in", pump.tripped, False)

# ---------------------------------------------------------------------------
print("6. a FEEDER ground fault trip can still be reset")
# The trip makes its own MCC normal supply unavailable. If that counted as an
# inhibit the lockout would seal itself in with no way out, so it must not.
plant, pump = fresh()
plant.component("rcp-1", "tripfdrgft")
check("tripped", (pump.tripped, pump.trip_cause), (True, TRIP_FDR_GROUND_FAULT))
plant.step(0.1)
check("running on the alternate, so nothing inhibits",
      plant.trip_inhibits(pump), [])
reset(plant, pump)
check("reset", pump.tripped, False)

# ---------------------------------------------------------------------------
print("7. reset is not a restart, and a held START cannot sneak one in")
plant, pump = fresh()
plant.component("rcp-1", "trip")
check("breaker open", pump.breaker_closed, False)
line = reset(plant, pump)
check("reset", pump.tripped, False)
check("and points at START", "START" in line, True)
plant.step(0.1)
plant.step(0.1)
check("but nothing restarted it", pump.breaker_closed, False)
press(plant, pump, SW_START)
check("a press of START does", pump.breaker_closed, True)

# The case the out-of-correspondence rule used to cover, now covered by reading
# the switch for edges instead of levels: the operator is leaning on START when
# the trip clears, and a 7000 hp motor must not take that as a start command.
plant, pump = fresh()
state.set_switch(pump.spec["power"], position=SW_START)   # and held there
plant.step(0.1)
check("already running, so the press changes nothing", pump.breaker_closed, True)

plant.component("rcp-1", "trip")
check("tripped out from under a held START", pump.breaker_closed, False)
for _ in range(5):
    plant.step(0.1)
check("still open with START held down", pump.breaker_closed, False)

reset(plant, pump)
for _ in range(5):
    plant.step(0.1)
check("and clearing the trip under it does not restart it", pump.breaker_closed, False)

state.set_switch(pump.spec["power"], position=SW_NORMAL)
plant.step(0.1)
check("letting go is not a command either", pump.breaker_closed, False)
press(plant, pump, SW_START)
check("only a fresh press is", pump.breaker_closed, True)

# TRIP is the other end: it opens the breaker and latches nothing.
press(plant, pump, SW_TRIP)
check("TRIP stops it", pump.breaker_closed, False)
check("without latching a trip", pump.tripped, False)
press(plant, pump, SW_START)
check("so START picks it straight back up", pump.breaker_closed, True)

# ---------------------------------------------------------------------------
print("8. the run lamp is defined and follows the breaker")
# The module singleton, because that is what RcpSimulation publishes.
from rcp_sim import RcpSimulation, plant as live_plant

sim = RcpSimulation()
sim.ensure_definitions()

live_pump = live_plant.pump("rcp-1")
check("uid is the run lamp's own definition asset, not its object name",
      run_lamp_uid(live_pump), "92d1df45-7278-4ff4-a337-24bbb6767be3")
check("indicator defined",
      state.get_indicator(run_lamp_uid(live_pump)) is not None, True)
check("and carries a readable name",
      state.get_indicator(run_lamp_uid(live_pump))["id"], "RCP 1 Run Lamp")
check("all four defined, each with its own uid",
      len({run_lamp_uid(p) for p in live_plant.pumps}), 4)
check("all four defined",
      [state.get_indicator(run_lamp_uid(p)) is not None for p in live_plant.pumps],
      [True] * 4)

state.define_switch(live_pump.spec["power"],
                    positions=[SW_TRIP, SW_NORMAL, SW_START], position=SW_NORMAL,
                    save=False)
live_plant.step(0.1)
sim._publish()
check("dark while stopped", state.get_indicator(run_lamp_uid(live_pump))["state"], "off")
check("and the switch pair reads green",
      state.get_indicator(live_pump.spec["power"])["state"], "green")

press(live_plant, live_pump, SW_START)
sim._publish()
check("lit while running", state.get_indicator(run_lamp_uid(live_pump))["state"], "red")

live_plant.component("rcp-1", "trip")
sim._publish()
check("out again on a trip", state.get_indicator(run_lamp_uid(live_pump))["state"], "off")
check("and the switch pair goes green with it",
      state.get_indicator(live_pump.spec["power"])["state"], "green")

print()
if failures:
    print(f"{len(failures)} of {checks[0]} checks FAILED")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"all {checks[0]} checks passed")
