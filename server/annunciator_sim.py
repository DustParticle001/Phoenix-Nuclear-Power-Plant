"""Test simulation: the alarm windows on the annunciator racks, and the SART
pushbuttons that work them.

Every window runs the same sequence, the one a real annunciator panel runs:

    clear             dark. Nothing wrong.
    alarm             the condition came up: lit, flashing fast, sounding.
    alarm, acked      acknowledged while it's still there: lit, steady, quiet.
    cleared-unacked   the condition went away again. Flashes slowly with a
                      sound of its own - ringback - and waits for RESET rather
                      than going quietly dark. A window reaches this whether or
                      not anyone acknowledged the alarm: "it happened, and it
                      is over" is worth a look even if somebody saw it come in.

A flashing window blinks at one of two rates, and which one is part of the
sequence rather than a decoration:

    announce   the alarm is in and unacknowledged. Fast.
    clear      ringback - it is over. Slow.

The blink itself still happens on the client, where every window flashing at
the same rate in a rack group blinks in step (see AnnunciatorFlashGroups.cs).
So this file says whether a window flashes and which of the two rates it uses;
the client owns the actual periods, per rack.

SART - the four pushbuttons on a panel
--------------------------------------

    SILENCE      quiet, and nothing else. Every window that is sounding stops
                 feeding the horn and goes on flashing exactly as it was. It
                 mutes what is in NOW: whatever comes in after it sounds,
                 because silence is a flag on each window rather than on the
                 panel.
    ACKNOWLEDGE  seen. Every unacknowledged alarm stops flashing and lights
                 steady, and the horn goes with the flash - the same contact
                 drives the lamp and the audible on a real panel. It clears
                 nothing, and it does not touch a ringback: a window whose
                 condition is still there stays lit until it goes away.
    RESET        every ringback out. That is the ringback's acknowledge - the
                 condition is gone, and now the window is too. A window still
                 in alarm is untouched: reset is not a way to make a live alarm
                 go away.
    TEST         held, every window on the panel reads as being in alarm, so
                 the panel comes up fast-flashing and sounding and can be
                 acknowledged or silenced like anything else. Let go and the
                 conditions are real again, so every window that isn't
                 genuinely in falls to ringback and waits for a RESET. The
                 whole sequence, from one button - and nothing here
                 special-cases it: TEST only makes the condition read true.

Which windows a cluster commands
--------------------------------

A SART cluster is four switches whose ids read like "<panel> Silence",
"<panel> Acknowledge", "<panel> Reset", "<panel> Test". What comes before the
action word is the SART GROUP it commands - the sartGroup its windows carry.
Spelling is loose: "RCP P1", "RCP_P1" and "rcp-p1" are one name.

THE SART GROUP IS NOT THE FLASH GROUP. A flash group is every rack that blinks
in step, which is a whole control room; a SART panel commands the one to three
racks standing in front of it. They are separate names on the rack definition
for that reason - tying them together would tie the panel an operator can
reach to the panel they can see.

Leave the prefix off - switches called plainly "Silence", "Acknowledge",
"Reset", "Test" - and the cluster commands EVERY window in the plant, whatever
group they are in. That is the right answer while there is one panel, and it is
what a plant-wide master cluster is once there are several.

A window whose rack names no sartGroup is reached only by a master cluster:
guessing which of several panels commands it would be worse than saying
nothing.

Nothing to register on either side. On the client the four buttons come from
one SartPanel component with the group typed into it, which names them without
any definition assets; here they simply turn up in the report. The buttons want
Trans2pSpring (momentary) - a latching switch would hold the panel in test - see
docs/interactable-api-usage-guide.md.

Acknowledging one window from outside the room:

    POST /api/io/set {"annunciators": [{"id": "RCP_1_TRIP",
                                        "acknowledged": true}]}

The conditions below come from what the other sims already produce, so the
panel has something to do the moment you start the server: trip an RCP or drop
a bus from the console and its windows come in, open the bypass valve and that
one does. Add a row to ALARMS to add an alarm - an id and something that
returns True when it's wrong. A system with a lot of them (rcp_sim) hands over
a whole block instead, so the conditions live next to the state they read.

A window with no row here is still a window: SILENCE, ACKNOWLEDGE, RESET and
TEST all reach it. Its condition simply never comes in on its own.

server.py starts it automatically; pass --no-sim to run the server bare.
"""

import re
import threading
from collections import Counter

from io_state import ANNOUNCE_RATE, CLEAR_RATE, state
from rcp_sim import alarm_conditions
from rod_sim import alarm_conditions as rod_alarm_conditions
from turbine_sim import GEN_LOAD, GRID_FREQ, TURBINE_RPM
from valve_sim import BYPASS_VALVE_POS

# Alarms are slow next to the machinery driving them, and the flash is the
# client's job, so this doesn't need the tick rate the other sims run at.
TICK_SECONDS = 0.25

# The three states a window sits in. "clear" is dark on the client; every other
# name reads as lit, which is what keeps the state field free-form.
CLEAR = "clear"
ALARM = "alarm"
RINGBACK = "cleared-unacked"

# The four buttons.
SILENCE = "silence"
ACKNOWLEDGE = "acknowledge"
RESET = "reset"
TEST = "test"

# What the tail of a switch's id or name has to read like to be that button.
# The action word has to come last: "Reset" is a reset button, "Reset
# Permissive" is somebody else's switch. Longer words first so "Acknowledge"
# isn't read as an "ack" with "acknowled" in front of it.
SART_WORDS = (
    ("acknowledge", ACKNOWLEDGE),
    ("ack", ACKNOWLEDGE),
    ("silence", SILENCE),
    ("reset", RESET),
    ("test", TEST),
)

# Words that describe a panel rather than name one, so a prefix made only of
# them means "no group": "Alarm Ack" and "Annunciator Ack" are the master
# acknowledge, not a cluster for a group called "alarm".
PANEL_WORDS = ("alarm", "alarms", "annunciator", "annunciators", "ann",
               "panel", "horn", "sart")

# A switch is down in any of these. "pressed" is what Trans2pSpring reports and
# what these buttons should be; "on" is a latching Rot2p, which still works -
# it acts on the tick it goes on, and has to be flipped back to arm the next.
PRESSED_POSITIONS = ("pressed", "on")

# Above this many transitions in one tick, the log says how many rather than
# which: a TEST press moves every window on the panel at once, and a rack is
# dozens of windows.
BULK_LOG_THRESHOLD = 6

TURBINE_OVERSPEED_RPM = 1900.0
GEN_LOAD_HIGH_MW = 1600.0
GRID_FREQ_BAND = (59.5, 60.5)
BYPASS_OPEN_PCT = 5.0


def _gauge(uid, default=0.0):
    entry = state.get_gauge(uid)
    return entry["value"] if entry else default


def _slug(text):
    """Loose identity, so "RCP P1", "RCP_P1" and "rcp-p1" are one name."""
    return re.sub(r"[^a-z0-9]+", "", str(text or "").lower())


_PANEL_SLUGS = frozenset(_slug(word) for word in PANEL_WORDS)


def classify_sart_switch(text):
    """('acknowledge', 'RCP P1') for a switch called "RCP P1 Acknowledge".

    None for anything that doesn't read like a SART button. An empty prefix
    means the cluster commands every window there is.
    """
    name = str(text or "").strip().lower()
    if not name:
        return None

    for word, action in SART_WORDS:
        if name == word:
            return action, ""

        # Only on a separator, so "Fast Test" is a test button and
        # "Latest" is not.
        if len(name) > len(word) and name.endswith(word) \
                and name[-len(word) - 1] in " _-/.":
            prefix = name[: -len(word)].strip(" _-/.")
            return action, "" if _slug(prefix) in _PANEL_SLUGS else prefix

    return None


# One row per window: the id the client registered it under (the legend, slugged
# - "RCP 1 Trip" -> RCP_1_TRIP) and what makes it come in. Ids the racks in the
# scene don't have are skipped, so this table can name windows nobody has built
# yet.
#
# The RCP block comes from rcp_sim, which knows which of its pumps is tripped and
# which bus went away, and the rod block from rod_sim; both hand over conditions
# rather than driving their own windows so that every alarm on the rack runs the
# same sequence below.
ALARMS = [
    {"id": window, "condition": condition}
    for window, condition in alarm_conditions() + rod_alarm_conditions()
] + [
    {"id": "TURB_OVERSPEED",
     "condition": lambda: _gauge(TURBINE_RPM) > TURBINE_OVERSPEED_RPM},
    {"id": "GEN_LOAD_HI",
     "condition": lambda: _gauge(GEN_LOAD) > GEN_LOAD_HIGH_MW},
    {"id": "GRID_FREQ_ABNORM",
     "condition": lambda: not (GRID_FREQ_BAND[0] <= _gauge(GRID_FREQ, 60.0) <= GRID_FREQ_BAND[1])},
    {"id": "BYPASS_VLV_OPEN",
     "condition": lambda: _gauge(BYPASS_VALVE_POS) > BYPASS_OPEN_PCT},
]


class AnnunciatorSimulation:
    def __init__(self, alarms=None, tick=TICK_SECONDS):
        self.alarms = alarms if alarms is not None else ALARMS
        self.tick = tick

        # By window id, so the step loop can walk WINDOWS rather than alarms.
        # That is what lets SART reach a window nobody wrote a condition for -
        # a blank rack still tests, silences and resets.
        self._conditions = {row["id"]: row["condition"] for row in self.alarms}

        self._stop = threading.Event()
        self._thread = None

        # (group, action) -> was it down last tick. The three momentary actions
        # fire on the edge; a held button acts once.
        self._was_pressed = {}
        self._warned_groups = set()

    def ensure_definitions(self):
        """Nothing to create - annunciator windows belong to the client.

        A window's uid is the uid of a tile in a Unity rack definition, so the
        server inventing one would only produce a window no rack answers to.
        Racks register themselves on their first report (register_annunciators
        in io_state.py) and this sim drives whichever of its ids have turned up,
        skipping the rest. That's the opposite way round from the other sims,
        whose switches and gauges are single controls the server can define.
        """

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="annunciator-sim")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self):
        while not self._stop.wait(self.tick):
            self._step()

    # ------------------------------------------------------------------- tick

    def _step(self):
        windows = state.annunciators()
        groups = {_slug(w.get("sartGroup")) for w in windows if w.get("sartGroup")}
        panels = self._read_panels(groups)

        # Buttons first, then the sequence on a FRESH read of the windows:
        # acknowledging writes flags the stepping has to see, or it would put
        # the flash it just stopped straight back on.
        for commands, actions in panels.items():
            self._press(commands, actions, windows)

        moved = []
        for window in state.annunciators():
            transition = self._step_window(window, self._active(window, panels))
            if transition is not None:
                moved.append(transition)

        self._log(moved)

    def _read_panels(self, groups):
        """The SART clusters in the scene: group slug -> {action: is it down}.

        Rebuilt every tick rather than cached, because switches appear when a
        client registers them - and it is a handful of switches against a 4 Hz
        tick. Two clusters resolving to the same windows merge, so a master
        cluster and a panel's own both work the panel.
        """
        panels = {}

        for entry in state.switches():
            found = (classify_sart_switch(entry["id"])
                     or classify_sart_switch(entry["name"]))
            if found is None:
                continue

            action, prefix = found
            commands = self._resolve_group(prefix, groups)
            down = entry["position"] in PRESSED_POSITIONS and entry["powered"]

            actions = panels.setdefault(commands, {})
            actions[action] = actions.get(action, False) or down

        return panels

    def _resolve_group(self, prefix, groups):
        """Which windows a cluster commands: a sartGroup slug, or "" for all."""
        slug = _slug(prefix)
        if not slug or slug in groups:
            return slug

        # A prefix naming no group is far more likely a rack that hasn't been
        # given a Sart Group yet than a panel meant to command nothing, so it
        # commands everything - and says so, once.
        if slug not in self._warned_groups:
            self._warned_groups.add(slug)
            known = ", ".join(sorted(groups)) or "no rack names one yet"
            print(f"[ann] SART cluster '{prefix}' matches no rack's Sart Group "
                  f"({known}); commanding every window instead")

        return ""

    @staticmethod
    def _reaches(commands, window):
        """Does a cluster commanding `commands` reach this window?

        A master cluster ("") reaches everything. Anything else reaches the
        windows whose rack names it - and a rack that names no group is
        reached by the master alone.
        """
        return commands == "" or _slug(window.get("sartGroup")) == commands

    def _press(self, commands, actions, windows):
        """The three momentary actions, on the tick their button goes down."""
        owned = [w for w in windows if self._reaches(commands, w)]

        for action, run in ((SILENCE, self.silence),
                            (ACKNOWLEDGE, self.acknowledge),
                            (RESET, self.reset)):
            down = actions.get(action, False)
            if down and not self._was_pressed.get((commands, action), False):
                run(owned)
            self._was_pressed[(commands, action)] = down

    def _active(self, window, panels):
        """Is this window's condition in - really, or because TEST is held?"""
        for commands, actions in panels.items():
            if actions.get(TEST) and self._reaches(commands, window):
                return True

        condition = self._conditions.get(window["id"])
        return bool(condition()) if condition is not None else False

    # ------------------------------------------------------------- the buttons

    def silence(self, windows):
        """Mute what is sounding. The lamps carry on exactly as they were.

        Only a flashing window is audible, so only a flashing window has
        anything to silence. Every transition that starts a new audible event
        un-silences the window it happens to, which is what stops one press
        from deafening the panel to everything after it.
        """
        count = 0
        for window in windows:
            if window["flashing"] and not window.get("silenced"):
                state.set_annunciator(window["uid"], silenced=True)
                count += 1

        if count:
            print(f"[ann] silenced {count} window(s)")

    def acknowledge(self, windows):
        """Seen: every unacknowledged alarm goes steady, and quiet with it.

        Acknowledging never clears a window - one whose condition has gone
        stays lit until it goes, and then rings back like any other. It leaves
        a ringback alone too: RESET is the ringback's acknowledge.
        """
        count = 0
        for window in windows:
            if window["state"] == ALARM and not window["acknowledged"]:
                state.set_annunciator(window["uid"], flashing=False,
                                      acknowledged=True)
                count += 1

        if count:
            print(f"[ann] acknowledged {count} window(s)")

    def reset(self, windows):
        """Every ringback out: the condition is gone, and now the window is.

        A window still in alarm is untouched. Reset is not a way to put a live
        alarm out - only the condition going away does that.
        """
        count = 0
        for window in windows:
            if window["state"] == RINGBACK:
                state.set_annunciator(window["uid"], state=CLEAR, flashing=False,
                                      acknowledged=False, silenced=False)
                count += 1

        if count:
            print(f"[ann] reset {count} window(s)")

    # ---------------------------------------------------------- the sequence

    def _step_window(self, window, active):
        """One window, one tick. Returns (id, new state) if it moved."""
        current = window["state"]
        acked = window["acknowledged"]

        if active:
            if current == ALARM:
                # Acknowledging stops the flash; the window stays lit for as
                # long as the condition is there.
                state.set_annunciator(window["uid"], flashing=not acked,
                                      flash_rate=ANNOUNCE_RATE)
                return None

            # New alarm - from clear, or a condition that came back during its
            # own ringback, which starts the sequence over and moves the window
            # off the slow clock back onto the fast one. Un-silenced: a new
            # alarm sounds whatever the operator silenced before it.
            return self._transition(window, ALARM, flashing=True,
                                    acknowledged=False,
                                    flash_rate=ANNOUNCE_RATE, silenced=False)

        if current == ALARM:
            # Ringback, acknowledged or not: the condition going away is its own
            # event on the panel. Slow clock, its own sound, and it waits for
            # RESET rather than going quietly dark. The acknowledge is dropped
            # because it was for the alarm, not for this - which is also what
            # keeps "cleared-unacked" an honest name for the state.
            return self._transition(window, RINGBACK, flashing=True,
                                    acknowledged=False,
                                    flash_rate=CLEAR_RATE, silenced=False)

        # Clear stays clear, and a ringback holds until somebody resets it.
        return None

    def _transition(self, window, new_state, flashing=None, acknowledged=None,
                    flash_rate=None, silenced=None):
        state.set_annunciator(window["uid"], state=new_state,
                              flashing=flashing, acknowledged=acknowledged,
                              flash_rate=flash_rate, silenced=silenced)
        return window["id"], new_state

    @staticmethod
    def _log(moved):
        if not moved:
            return

        if len(moved) > BULK_LOG_THRESHOLD:
            counts = Counter(new_state for _, new_state in moved)
            print("[ann] " + ", ".join(f"{count} window(s) -> {new_state}"
                                       for new_state, count in counts.items()))
            return

        for window_id, new_state in moved:
            print(f"[ann] {window_id} -> {new_state}")
