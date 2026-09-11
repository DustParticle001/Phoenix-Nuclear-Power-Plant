"""TEMPORARY: hold every labeled annunciator window in alarm, flashing.

A panel-wide flash test with no conditions behind it. Any labeled window that is
dark gets driven straight to alarm, so a rack comes in fully alight and flashing
the moment a client connects and registers its windows - which is what makes
this fire "on client load" without needing a connect hook: the windows only
exist once the client has reported them.

Windows with no legend are left alone (a blanked-off cell has nothing to say),
which is what "labeled" means here - see _wanted.

Acknowledging still behaves: an acked window goes steady and stays lit, because
this only ever drives windows that are DARK. To re-arm the panel, set the
windows back to clear (POST /api/io/set with "state": "clear") or restart the
server.

Two things this deliberately does not do, because neither lives on this side:

  THE FLASH PERIOD. The wire now carries WHICH of the two rates a window
  blinks at - this drives every window at the announce rate, the fast one an
  unacknowledged alarm uses - but not how long that rate's cycle is. The
  periods belong to the rack definition
  (Assets/Controls/Annunciators/Definitions/RCP_P1.asset -> Inspector ->
  Flashing): 0.2 s announce, 0.8 s ringback.

  THE AUDIBLE. The horn is client-side and needs nothing from here:
  AnnunciatorHorn.cs sounds while anything is flashing at the rate it watches,
  which is the announce rate this file drives. Ringback gets its own sound
  later - a second horn on the clear rate - and until then it flashes silently.

TO REMOVE: delete this file and the two AnnPanelTest lines in server.py.
"""

import threading
import time

from io_state import ANNOUNCE_RATE, DEFAULT_ANNUNCIATOR_STATE, state

# Alarms are slow and this one never changes its mind, so it doesn't need the
# tick rate the machinery sims run at. It stays running rather than firing once
# because windows appear late: a client registers them on its first report.
TICK_SECONDS = 0.5

# Dark on the client. Per io_state: every other state name reads as lit, which
# is what keeps the field free-form.
DARK_STATES = (DEFAULT_ANNUNCIATOR_STATE, "off", "normal", "")

ALARM = "alarm"

# Flash groups to drive. Empty means every window on every rack, which is what
# you want today: the only rack (RCP_P1) declares no group, so its windows
# arrive in the client's default group and there is nothing to single out. Once
# there is a second panel, set flashGroup to "RCS" on the rack definition and
# put ("RCS",) here.
PANEL_GROUPS = ()


class AnnPanelTest:
    def __init__(self, groups=PANEL_GROUPS, tick=TICK_SECONDS):
        self.groups = tuple(str(g).strip().lower() for g in groups)
        self.tick = tick

        self._stop = threading.Event()
        self._thread = None
        self._driven = set()   # uids already reported, to keep the log to once each

    def ensure_definitions(self):
        """Nothing to create - annunciator windows belong to the client's racks.

        Same as annunciator_sim: a window's uid comes out of a Unity rack
        definition, so a uid the server invented would name a window no rack
        answers to.
        """

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ann-panel-test")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self):
        while not self._stop.wait(self.tick):
            self._step()

    def _step(self):
        fresh = []

        for window in state.annunciators():
            if not self._wanted(window):
                continue
            if str(window["state"]).strip().lower() not in DARK_STATES:
                continue   # already lit - leave it, including an acked one

            state.set_annunciator(window["uid"], state=ALARM, flashing=True,
                                  flash_rate=ANNOUNCE_RATE, acknowledged=False)

            if window["uid"] not in self._driven:
                self._driven.add(window["uid"])
                fresh.append(window["id"])

        if fresh:
            names = ", ".join(fresh[:8]) + (", ..." if len(fresh) > 8 else "")
            print(f"[ann-test] flashing {len(fresh)} labeled window(s): {names}")

    def _wanted(self, window):
        """Labeled, and on a panel we were asked to drive."""
        if not str(window.get("text") or "").strip():
            return False   # blanked-off cell or a window with no legend

        if not self.groups:
            return True

        return str(window.get("group") or "").strip().lower() in self.groups
