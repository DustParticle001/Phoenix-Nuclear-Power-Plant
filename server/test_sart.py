"""Check the SART sequence: run it, read the output, see the panel behave.

    python server/test_sart.py

Drives the real state machine in annunciator_sim.py against the real io_state,
with the store pointed at a temp file so data/io_definitions.json is never
touched. Nothing here is mocked - the windows, the switches and the sequence are
the ones the server runs, with the alarm conditions replaced by two flags this
file flips by hand.

There is no test runner in this project, so it is a script: it prints what it
did, and exits non-zero with a list of what came out wrong.
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from io_state import state
from annunciator_sim import AnnunciatorSimulation, ALARM, CLEAR, RINGBACK

# Never write over the project's data file.
state._path = Path(tempfile.mkdtemp()) / "io_definitions.json"

failures = []
checks = [0]


def check(label, got, want):
    checks[0] += 1
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


def window(wid, sart_group, flash_group="MCR"):
    """A window in a rack: `flash_group` blinks it, `sart_group` commands it.

    Two different names on purpose - a whole control room flashes in step while
    one SART panel commands the racks in front of it - and every test below
    keeps them different so neither can quietly stand in for the other.
    """
    state.define_annunciator("u-" + wid, id=wid, group=flash_group,
                             sart_group=sart_group, save=False)


def win(wid):
    e = state.find_annunciator(wid)
    return (e["state"], e["flashing"], e["flashRate"], e["acknowledged"], e["silenced"])


def press(action, down=True):
    state.set_switch(f"sw-{action}", position="pressed" if down else "released")


# Exactly what SartPanel.cs puts on the wire: the flash group it commands (or
# "Annunciator" when it commands every window) and the button's canonical name.
# Spelled out here rather than built loosely, so renaming an action on either
# side of the wire breaks a test instead of quietly breaking a panel.
SART_ACTIONS = ("Silence", "Acknowledge", "Reset", "Test")
MASTER_PREFIX = "Annunciator"


def setup(prefix=""):
    for uid in list(state._annunciators):
        state.remove_annunciator(uid, save=False)
    for uid in list(state._switches):
        state.remove_switch(uid, save=False)

    for action in SART_ACTIONS:
        wire_id = f"{prefix or MASTER_PREFIX} {action}"
        state.define_switch(f"sw-{action.lower()}", id=wire_id, name=wire_id,
                            positions=["released", "pressed"], position="released",
                            save=False)


# Conditions we control by hand.
live = {"A_TRIP": False, "B_TRIP": False}
sim = AnnunciatorSimulation(
    alarms=[{"id": "A_TRIP", "condition": lambda: live["A_TRIP"]},
            {"id": "B_TRIP", "condition": lambda: live["B_TRIP"]}],
)

# ---------------------------------------------------------------------------
print("1. sequence: in -> silence -> ack -> clears -> silence -> reset")
setup()
window("A_TRIP", sart_group="RCP_P1")
window("B_TRIP", sart_group="RCP_P1")
# A window nobody wrote a condition for - SART must still reach it.
window("SPARE", sart_group="RCP_P1")

live["A_TRIP"] = True
sim._step()
check("comes in", win("A_TRIP"), (ALARM, True, "announce", False, False))

press("silence")
sim._step()
check("silence mutes only", win("A_TRIP"), (ALARM, True, "announce", False, True))
press("silence", False)

press("acknowledge")
sim._step()
check("ack -> steady lit", win("A_TRIP"), (ALARM, False, "announce", True, True))
press("acknowledge", False)

live["A_TRIP"] = False
sim._step()
check("acked alarm clearing -> ringback",
      win("A_TRIP"), (RINGBACK, True, "clear", False, False))

press("silence")
sim._step()
check("ringback silenced", win("A_TRIP"), (RINGBACK, True, "clear", False, True))
press("silence", False)

press("reset")
sim._step()
check("reset -> dark", win("A_TRIP"), (CLEAR, False, "clear", False, False))
press("reset", False)

# ---------------------------------------------------------------------------
print("2. unacknowledged alarm clearing also rings back")
live["A_TRIP"] = True
sim._step()
check("in again", win("A_TRIP")[0], ALARM)
live["A_TRIP"] = False
sim._step()
check("unacked clearing -> ringback",
      win("A_TRIP"), (RINGBACK, True, "clear", False, False))

# ---------------------------------------------------------------------------
print("3. ack does not clear a ringback; reset does not clear a live alarm")
press("acknowledge")
sim._step()
check("ack leaves ringback alone", win("A_TRIP")[0], RINGBACK)
press("acknowledge", False)

live["B_TRIP"] = True
sim._step()
check("B in", win("B_TRIP")[0], ALARM)
press("reset")
sim._step()
check("reset clears the ringback", win("A_TRIP")[0], CLEAR)
check("reset spares the live alarm", win("B_TRIP")[0], ALARM)
press("reset", False)

# ---------------------------------------------------------------------------
print("4. a new alarm sounds through an earlier silence")
press("silence")
sim._step()
check("B silenced", win("B_TRIP")[4], True)
press("silence", False)

live["A_TRIP"] = True
sim._step()
check("new alarm is audible", win("A_TRIP")[4], False)
check("old one stays silenced", win("B_TRIP")[4], True)

# ---------------------------------------------------------------------------
print("5. re-alarm during ringback restarts the sequence")
live["A_TRIP"] = False
sim._step()
check("A rings back", win("A_TRIP")[0], RINGBACK)
press("silence")
sim._step()
press("silence", False)
live["A_TRIP"] = True
sim._step()
check("back to fast flash, unacked, audible",
      win("A_TRIP"), (ALARM, True, "announce", False, False))
live["A_TRIP"] = False
live["B_TRIP"] = False
sim._step()
check("both ring back", [win(w)[0] for w in ("A_TRIP", "B_TRIP")], [RINGBACK, RINGBACK])
press("reset")
sim._step()
press("reset", False)
check("panel dark", [win(w)[0] for w in ("A_TRIP", "B_TRIP")], [CLEAR, CLEAR])

# ---------------------------------------------------------------------------
print("6. TEST held forces every window, including one with no condition")
press("test")
sim._step()
check("all in alarm, fast, unacked",
      [win(w) for w in ("A_TRIP", "B_TRIP", "SPARE")],
      [(ALARM, True, "announce", False, False)] * 3)

press("acknowledge")
sim._step()
check("test alarms can be acked", win("SPARE"), (ALARM, False, "announce", True, False))
press("acknowledge", False)

press("test", False)
sim._step()
check("release -> ringback everywhere",
      [win(w) for w in ("A_TRIP", "B_TRIP", "SPARE")],
      [(RINGBACK, True, "clear", False, False)] * 3)

press("reset")
sim._step()
press("reset", False)
check("reset clears the test", [win(w)[0] for w in ("A_TRIP", "B_TRIP", "SPARE")],
      [CLEAR] * 3)

# ---------------------------------------------------------------------------
print("7. a held button acts once (edge, not level)")
live["A_TRIP"] = True
sim._step()
press("acknowledge")
sim._step()
check("acked", win("A_TRIP")[3], True)
# Un-acknowledge behind the panel's back; a still-held button must not re-ack.
state.set_annunciator("u-A_TRIP", acknowledged=False, flashing=True)
sim._step()
check("held ack does not fire again", win("A_TRIP")[3], False)
press("acknowledge", False)

# ---------------------------------------------------------------------------
print("8. a cluster only commands its own SART group")
setup(prefix="RCP P1")
# Same flash group, different SART groups: one control room, two panels.
window("A_TRIP", sart_group="RCP_P1", flash_group="MCR")
window("B_TRIP", sart_group="TURBINE", flash_group="MCR")
live["A_TRIP"] = True
live["B_TRIP"] = True
sim._step()
check("both in", [win(w)[0] for w in ("A_TRIP", "B_TRIP")], [ALARM, ALARM])

press("acknowledge")
sim._step()
check("own SART group acked", win("A_TRIP")[3], True)
check("other SART group untouched", win("B_TRIP")[3], False)
press("acknowledge", False)

# ---------------------------------------------------------------------------
print("9. the SART group is not the flash group")
setup(prefix="MCR")
# A cluster named after the FLASH group must not command the room just because
# every rack in it blinks together. No rack names "MCR" as its SART group, so
# this falls back to master - which is the documented behaviour - and the check
# that matters is the one below: naming a flash group is not how you scope a
# panel.
window("A_TRIP", sart_group="RCP_P1", flash_group="MCR")
window("B_TRIP", sart_group="TURBINE", flash_group="MCR")
live["A_TRIP"] = True
live["B_TRIP"] = True
sim._step()
press("acknowledge")
sim._step()
check("unmatched name falls back to master, so both",
      [win(w)[3] for w in ("A_TRIP", "B_TRIP")], [True, True])
press("acknowledge", False)

setup(prefix="RCP P1")
window("A_TRIP", sart_group="RCP_P1", flash_group="MCR")
window("B_TRIP", sart_group="TURBINE", flash_group="MCR")
live["A_TRIP"] = True
live["B_TRIP"] = True
sim._step()
press("reset")
sim._step()
press("reset", False)
live["A_TRIP"] = False
live["B_TRIP"] = False
sim._step()
press("reset")
sim._step()
check("reset reached only its own SART group",
      [win(w)[0] for w in ("A_TRIP", "B_TRIP")], [CLEAR, RINGBACK])
press("reset", False)

# ---------------------------------------------------------------------------
print("10. a rack naming no SART group answers to the master alone")
setup(prefix="RCP P1")
window("A_TRIP", sart_group="RCP_P1")
window("B_TRIP", sart_group="")          # never assigned to a panel
live["A_TRIP"] = True
live["B_TRIP"] = True
sim._step()
press("acknowledge")
sim._step()
check("named cluster skips the unassigned rack",
      [win(w)[3] for w in ("A_TRIP", "B_TRIP")], [True, False])
press("acknowledge", False)

setup(prefix="")                          # master
window("A_TRIP", sart_group="RCP_P1")
window("B_TRIP", sart_group="")
sim._step()
press("acknowledge")
sim._step()
check("master reaches both", [win(w)[3] for w in ("A_TRIP", "B_TRIP")], [True, True])
press("acknowledge", False)

# ---------------------------------------------------------------------------
print("11. a regrouped rack corrects its windows without losing a live alarm")
setup(prefix="TURBINE")
window("A_TRIP", sart_group="RCP_P1")
# B is what makes "TURBINE" a group the server knows: a cluster whose name
# matches no rack at all falls back to commanding everything, so without this
# the check below would pass for the wrong reason.
window("B_TRIP", sart_group="TURBINE")
live["A_TRIP"] = True
live["B_TRIP"] = True
sim._step()
check("both in", [win(w)[0] for w in ("A_TRIP", "B_TRIP")], [ALARM, ALARM])
press("acknowledge")
sim._step()
check("the TURBINE cluster acked its own", win("B_TRIP")[3], True)
check("and could not reach the RCP_P1 rack", win("A_TRIP")[3], False)
press("acknowledge", False)
sim._step()          # the release has to be scanned before the next press is an edge

# The rack is moved to the TURBINE panel: the client re-reports the window,
# because the server's copy of the grouping has gone stale.
result = state.register_annunciators(
    [{"uid": "u-A_TRIP", "id": "A_TRIP", "group": "MCR", "sartGroup": "TURBINE"}])
check("server took the correction", "u-A_TRIP" in result["registered"], True)
check("grouping updated", state.find_annunciator("A_TRIP")["sartGroup"], "TURBINE")
check("the live alarm survived being regrouped", win("A_TRIP")[0], ALARM)

press("acknowledge")
sim._step()
check("now the TURBINE cluster reaches it", win("A_TRIP")[3], True)
press("acknowledge", False)

print()
if failures:
    print(f"{len(failures)} of {checks[0]} checks FAILED")
    for f in failures:
        print("  -", f)
    sys.exit(1)
print(f"all {checks[0]} checks passed")
