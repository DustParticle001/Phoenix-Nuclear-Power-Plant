"""Check the RCS temperatures against the reference plant numbers.

    python server/test_rcs_thermal.py

Drives the real RcsThermal from rcs_thermal.py, with io_state pointed at a temp
file so data/io_definitions.json is never touched. The pumps are started the way
an operator starts them - a press of the control switch - because the flow this
reads is whatever rcp_sim's flywheels are actually doing.

What is under test:

  * rated power on four pumps lands on the numbers in
    misc/systems/rcs/loop.json: Th ~618 F, Tc ~557 F, Tavg 587.5 F
  * no load is isothermal at 557 F, which is the same number as full-power Tc
  * core dT is power over FLOW, so losing half the pumps doubles it and pushes
    Th and Tc apart around a Tavg that hasn't moved
  * dT stays finite with every pump stopped, on the natural circulation floor
  * a stopped loop reads Tc on both legs - its flow has reversed
  * the ten gauges get the values the model holds

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

import rcp_sim
import rcs_thermal
from rcp_sim import RATED_FLOW_GPM, SW_NORMAL, SW_START, RcpSimulation, plant
from rcs_thermal import (CORE_DT, DT_RATED_F, LOOP_TC, LOOP_TH,
                         NATURAL_CIRC_FRACTION, RATED_TOTAL_FLOW_GPM, RCS_TAU,
                         TAVG, T_AVG_FULL_F, T_NO_LOAD_F, RcsThermal,
                         RcsThermalSimulation)
from rod_sim import RodSimulation, core

RcpSimulation().ensure_definitions()
RodSimulation().ensure_definitions()
RcsThermalSimulation().ensure_definitions()

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


def start_pump(key):
    """One press of START, and the ticks that see it."""
    pump = plant.pump(key)
    state.set_switch(pump.spec["power"], position=SW_START)
    plant.step(0.1)
    plant.step(0.1)
    state.set_switch(pump.spec["power"], position=SW_NORMAL)
    plant.step(0.1)


def run_pumps(seconds, dt=0.1):
    for _ in range(int(seconds / dt)):
        plant.step(dt)


def settle(rcs, seconds=8 * RCS_TAU, dt=1.0):
    """Long enough for Tavg to be on its programme rather than chasing it."""
    for _ in range(int(seconds / dt)):
        rcs.step(dt)


# ------------------------------------------------------------------ no load

print("\nNo load is isothermal at the programme's cold end")
rcs = RcsThermal()
core.power = 0.0
settle(rcs)
close("Tavg sits at no-load", rcs.tavg, T_NO_LOAD_F, 0.1)
close("no power, no dT", rcs.core_dt, 0.0, 0.01)
close("so Th is Tavg", rcs.t_hot, T_NO_LOAD_F, 0.1)
close("and so is Tc", rcs.t_cold, T_NO_LOAD_F, 0.1)

print("\nAnd with no pumps running dT stays finite")
close("flow is on the natural circulation floor",
      rcs.flow_fraction, NATURAL_CIRC_FRACTION, 1e-9)
core.power = 2.0
settle(rcs)
close("dT is power over the floor, not over zero", rcs.core_dt,
      DT_RATED_F * 0.02 / NATURAL_CIRC_FRACTION, 0.01)
check("which is a real number", rcs.core_dt < 1e6, True)

legs = rcs.legs()
check("every loop forward - natural circulation has no reverse loop",
      all(hot > cold for hot, cold in legs.values()), True)


# --------------------------------------------------------------- rated power

print("\nRated power on four pumps lands on the reference numbers")
for key in ("rcp-1", "rcp-2", "rcp-3", "rcp-4"):
    start_pump(key)
run_pumps(60.0)

close("all four pumps at rated flow", plant.pumps[0].flow, RATED_FLOW_GPM, 1.0)
close("so the plant is at rated flow", rcs.total_flow(), RATED_TOTAL_FLOW_GPM, 5.0)
close("which is 100 %", rcs.flow_fraction, 1.0, 1e-3)

core.power = 100.0
settle(rcs)
close("Tavg on the programme's hot end", rcs.tavg, T_AVG_FULL_F, 0.1)
close("core dT at its rated value", rcs.core_dt, DT_RATED_F, 0.1)
close("Th - misc/systems/rcs/loop.json says ~618 F", rcs.t_hot, 618.0, 0.2)
close("Tc - loop.json says ~557 F", rcs.t_cold, 557.0, 0.2)
close("and no-load Tavg is the same number as full-power Tc",
      T_NO_LOAD_F, rcs.t_cold, 0.2)

legs = rcs.legs()
check("all four hot legs carry the one mixed core outlet",
      [round(hot, 3) for hot, _ in legs.values()], [round(rcs.t_hot, 3)] * 4)
check("and all four cold legs the same Tc",
      [round(cold, 3) for _, cold in legs.values()], [round(rcs.t_cold, 3)] * 4)


# ------------------------------------------------------------- half the flow

print("\nHalf the pumps, the same power: dT doubles")
was_tavg = rcs.tavg
plant.component("rcp-3", "trip")
plant.component("rcp-4", "trip")
run_pumps(600.0)          # let the flywheels finish coasting

close("two loops of flow", rcs.total_flow(), RATED_TOTAL_FLOW_GPM / 2.0, 5.0)
settle(rcs)
close("dT is twice what it was", rcs.core_dt, 2.0 * DT_RATED_F, 0.5)
close("Tavg has not moved - it is programmed on power, not flow",
      rcs.tavg, was_tavg, 0.1)
close("so Th went up by half the extra dT", rcs.t_hot, 618.0 + DT_RATED_F / 2.0, 0.5)
close("and Tc came down by the other half",
      rcs.t_cold, 557.0 - DT_RATED_F / 2.0, 0.5)

print("\nA stopped loop has reversed, and reads Tc on both legs")
legs = rcs.legs()
for n in (1, 2):
    close(f"loop {n} still carries core outlet", legs[n][0], rcs.t_hot, 0.01)
for n in (3, 4):
    close(f"loop {n} hot leg reads Tc", legs[n][0], rcs.t_cold, 0.01)
    close(f"loop {n} cold leg too", legs[n][1], rcs.t_cold, 0.01)


# ------------------------------------------------------------------ the wire

print("\nEverything reaches its gauge")
sim = RcsThermalSimulation()
sim.rcs = rcs
sim._publish()

close("Tavg", state.get_gauge(TAVG)["value"], rcs.tavg, 0.01)
close("core dT", state.get_gauge(CORE_DT)["value"], rcs.core_dt, 0.01)
for n in sorted(LOOP_TH):
    close(f"loop {n} Th", state.get_gauge(LOOP_TH[n])["value"], legs[n][0], 0.01)
    close(f"loop {n} Tc", state.get_gauge(LOOP_TC[n])["value"], legs[n][1], 0.01)

units = {state.get_gauge(uid)["units"]
         for uid in [TAVG, CORE_DT] + list(LOOP_TH.values()) + list(LOOP_TC.values())}
check("all of them in degF", units, {"F"})


# ------------------------------------------------------------------ verdict

print(f"\n{checks[0]} checks, {len(failures)} failed")
if failures:
    print("\nFAILURES")
    for line in failures:
        print(f"  - {line}")
    sys.exit(1)

print("All good.")
