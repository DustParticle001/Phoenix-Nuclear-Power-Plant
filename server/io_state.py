"""Live control-room I/O: the state the Unity client syncs against.

Everything is keyed by the Unity definition UID - the GUID on a
SwitchDefinition / GaugeDefinition asset - so the server and the scene agree on
what "this control" means without caring about names or hierarchy.

Four collections, defined in data/io_definitions.json:

    switches      inputs.  The client reports the position each switch is in.
    indicators    outputs. Lamp state for a switch, keyed by that switch's uid.
    gauges        outputs. The server sets a value, the client's needle follows.
    annunciators  outputs. One alarm window on a rack - lit/dark, flashing or
                  not, and at which of the two flash rates, keyed by the uid
                  of that tile in the client's rack definition.

Use it from the simulation side like this:

    from io_state import state

    pump = state.get_switch("a250f6ec-0dab-4358-9525-72a699375448")
    if pump and pump["position"] == "on":
        state.set_gauge("33bee2dd-3a3d-4c17-ad22-a3933648f795", 50.0)
        state.set_indicator("a250f6ec-0dab-4358-9525-72a699375448", "red")

    window = state.find_annunciator("RCP_1_TRIP")   # by uid, or by readable id
    if window:
        state.set_annunciator(window["uid"], "alarm", flashing=True,
                              flash_rate=ANNOUNCE_RATE)

    state.save()   # persist current values back to the JSON

Every write returns True when something actually changed. Changed entries get
the next revision number, which is how clients receive only what they haven't
seen (see changes_since).

Persistence: definition changes (define_*, remove_*, auto-registration) are
written to the JSON immediately. Value changes are not - they'd rewrite the file
hundreds of times a minute - so call save() when you want them on disk. The
values in the JSON are the state the server starts up in.

Thread safety: a ThreadingHTTPServer handler and a simulation thread can both be
in here at once, so every public method takes the lock. Returned dicts are
copies; mutating them does nothing.
"""

from pathlib import Path
import json
import os
import threading
import uuid

BASE_DIR = Path(__file__).parent
IO_FILE = BASE_DIR / "data" / "io_definitions.json"

# Values closer than this count as unchanged, so a simulation writing a gauge
# every tick doesn't burn a revision per tick.
VALUE_EPSILON = 1e-6

DEFAULT_POSITIONS = ["off", "on"]
# An annunciator window is dark in this state (and in "off"/"normal"); every
# other name reads as lit on the client, which is what makes the state free-form.
DEFAULT_ANNUNCIATOR_STATE = "clear"
# The two flash rates a window can blink at. They are states of the alarm
# sequence, not just speeds: announce is an alarm nobody has acknowledged
# (fast), clear is ringback - the condition went away before anyone did
# (slow). The client owns the actual periods, per rack; see
# AnnunciatorFlashGroups.cs. Anything unrecognised reads as announce, so a
# sim that sets flashing without saying how gets an alarm, not a ringback.
ANNOUNCE_RATE = "announce"
CLEAR_RATE = "clear"
FLASH_RATES = (ANNOUNCE_RATE, CLEAR_RATE)
DEFAULT_FLASH_RATE = ANNOUNCE_RATE
# TEMPORARY: 0.2 normally. Effectively "every frame" - a fast-turning
# synchroscope needs the samples not to alias, see LIMIT_SCOPE_TO_SYNC_BAND in
# turbine_sim.py. The real ceiling is the client's frame rate: its sync loop is
# a coroutine, so it can't run more than once a frame however small this gets.
DEFAULT_REPORT_INTERVAL = 0.005

# The parts of a window that belong to the CLIENT'S rack definition rather than
# to the server. A client may correct these on a window already registered -
# the rack is the authority on what it physically holds, and a rack renamed or
# moved to another SART panel would otherwise keep the grouping it had when it
# first reported. Everything else about a window is the server's, so a live
# alarm survives its rack being regrouped underneath it.
ANNUNCIATOR_DESCRIBED = ["name", "text", "color", "group", "sartGroup"]

# Written back to the JSON; revision/updatedBy are runtime bookkeeping and stay
# out of the file so it remains comfortable to hand-edit.
SWITCH_PERSISTED = ["uid", "id", "name", "positions", "position", "powered", "available"]
INDICATOR_PERSISTED = ["uid", "id", "name", "state", "flashing"]
GAUGE_PERSISTED = ["uid", "id", "name", "units", "minValue", "maxValue", "value", "valid"]
ANNUNCIATOR_PERSISTED = ["uid", "id", "name", "text", "color", "group",
                         "sartGroup", "state", "flashing", "flashRate",
                         "acknowledged", "silenced"]


class IoState:
    def __init__(self, path=IO_FILE):
        self._path = Path(path)
        self._lock = threading.RLock()

        # Clients resync from scratch when the session changes, so a server
        # restart can't leave them waiting on revisions that no longer exist.
        self._session_id = uuid.uuid4().hex

        self._switches = {}
        self._indicators = {}
        self._gauges = {}
        self._annunciators = {}
        self._revision = 0
        self._readme = []
        self._io_version = 1
        self._report_interval = DEFAULT_REPORT_INTERVAL
        self._auto_register = True

        self.reload()

    # ------------------------------------------------------------ properties

    @property
    def session_id(self):
        return self._session_id

    @property
    def revision(self):
        with self._lock:
            return self._revision

    @property
    def report_interval(self):
        with self._lock:
            return self._report_interval

    @property
    def auto_register(self):
        with self._lock:
            return self._auto_register

    # ----------------------------------------------------------- persistence

    def reload(self):
        """Re-read the JSON, dropping all runtime state. Safe to call live."""
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            document = {}
        except json.JSONDecodeError as error:
            raise ValueError(f"{self._path.name} is not valid JSON: {error}")

        if not isinstance(document, dict):
            raise ValueError(f"{self._path.name} must contain a JSON object")

        with self._lock:
            # Revisions restart from scratch, so connected clients have to
            # resync - a new session id is what tells them to.
            self._session_id = uuid.uuid4().hex

            self._readme = document.get("_readme", [])
            self._io_version = document.get("ioVersion", 1)
            self._report_interval = float(
                document.get("reportIntervalSeconds", DEFAULT_REPORT_INTERVAL))
            self._auto_register = bool(document.get("autoRegisterFromClients", True))

            self._switches = {}
            self._indicators = {}
            self._gauges = {}
            self._annunciators = {}
            self._revision = 0

            for entry in document.get("switches", []):
                self._load_switch(entry)
            for entry in document.get("indicators", []):
                self._load_indicator(entry)
            for entry in document.get("gauges", []):
                self._load_gauge(entry)
            for entry in document.get("annunciators", []):
                self._load_annunciator(entry)

    def save(self):
        """Write definitions and current values back to the JSON, atomically."""
        with self._lock:
            document = {
                "_readme": self._readme,
                "ioVersion": self._io_version,
                "reportIntervalSeconds": self._report_interval,
                "autoRegisterFromClients": self._auto_register,
                "switches": [_persist(e, SWITCH_PERSISTED) for e in self._switches.values()],
                "indicators": [_persist(e, INDICATOR_PERSISTED) for e in self._indicators.values()],
                "gauges": [_persist(e, GAUGE_PERSISTED) for e in self._gauges.values()],
                "annunciators": [_persist(e, ANNUNCIATOR_PERSISTED)
                                 for e in self._annunciators.values()],
            }

            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp = self._path.with_suffix(".json.tmp")
            temp.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            os.replace(temp, self._path)

        return self._path

    # ---------------------------------------------------------- definitions

    def define_switch(self, uid, id=None, name="", positions=None, position=None,
                      powered=True, available=True, save=True):
        """Add or replace a switch definition. Returns the stored entry."""
        if not uid:
            raise ValueError("a switch definition needs a uid")

        positions = list(positions) if positions else list(DEFAULT_POSITIONS)
        if position is None:
            position = positions[0] if positions else "off"

        with self._lock:
            entry = {
                "uid": uid,
                "id": id or uid,
                "name": name or id or uid,
                "positions": positions,
                "position": position,
                "powered": bool(powered),
                "available": bool(available),
                "revision": self._next_revision(),
                "updatedBy": "server",
            }
            self._switches[uid] = entry
            if save:
                self.save()
            return dict(entry)

    def define_indicator(self, uid, id=None, name="", state="off", flashing=False, save=True):
        """Add or replace an indicator. uid is the SWITCH definition's uid."""
        if not uid:
            raise ValueError("an indicator definition needs a uid")

        with self._lock:
            entry = {
                "uid": uid,
                "id": id or uid,
                "name": name or id or uid,
                "state": state,
                "flashing": bool(flashing),
                "revision": self._next_revision(),
                "updatedBy": "server",
            }
            self._indicators[uid] = entry
            if save:
                self.save()
            return dict(entry)

    def define_gauge(self, uid, id=None, name="", units="", min_value=0.0, max_value=100.0,
                     value=0.0, valid=True, save=True):
        """Add or replace a gauge definition. Returns the stored entry."""
        if not uid:
            raise ValueError("a gauge definition needs a uid")

        with self._lock:
            entry = {
                "uid": uid,
                "id": id or uid,
                "name": name or id or uid,
                "units": units,
                "minValue": float(min_value),
                "maxValue": float(max_value),
                "value": float(value),
                "valid": bool(valid),
                "revision": self._next_revision(),
                "updatedBy": "server",
            }
            self._gauges[uid] = entry
            if save:
                self.save()
            return dict(entry)

    def define_annunciator(self, uid, id=None, name="", text="", color="white", group="",
                           sart_group="", state=DEFAULT_ANNUNCIATOR_STATE, flashing=False,
                           flash_rate=DEFAULT_FLASH_RATE, acknowledged=False,
                           silenced=False, save=True):
        """Add or replace an alarm window. uid is the rack tile's definition UID.

        text/color/group/sart_group describe the physical tile and belong to the
        client's rack definition - they are here so the JSON reads like the rack
        looks. The server only ever writes state/flashing/acknowledged/silenced.

        group is the FLASH group: every rack that blinks in step, usually a
        whole control room. sart_group is which cluster of
        silence/acknowledge/reset/test buttons commands it, which is a finer
        grouping - one panel works the one to three racks in front of it. Empty
        means only a master cluster reaches the window.
        """
        if not uid:
            raise ValueError("an annunciator definition needs a uid")

        with self._lock:
            entry = {
                "uid": uid,
                "id": id or uid,
                "name": name or id or uid,
                "text": text,
                "color": color or "white",
                "group": group or "",
                "sartGroup": sart_group or "",
                "state": state or DEFAULT_ANNUNCIATOR_STATE,
                "flashing": bool(flashing),
                "flashRate": normalize_flash_rate(flash_rate),
                "acknowledged": bool(acknowledged),
                "silenced": bool(silenced),
                "revision": self._next_revision(),
                "updatedBy": "server",
            }
            self._annunciators[uid] = entry
            if save:
                self.save()
            return dict(entry)

    def remove_switch(self, uid, save=True):
        return self._remove(self._switches, uid, save)

    def remove_indicator(self, uid, save=True):
        return self._remove(self._indicators, uid, save)

    def remove_gauge(self, uid, save=True):
        return self._remove(self._gauges, uid, save)

    def remove_annunciator(self, uid, save=True):
        return self._remove(self._annunciators, uid, save)

    # ---------------------------------------------------------------- reads

    def get_switch(self, uid):
        with self._lock:
            entry = self._switches.get(uid)
            return dict(entry) if entry else None

    def get_indicator(self, uid):
        with self._lock:
            entry = self._indicators.get(uid)
            return dict(entry) if entry else None

    def get_gauge(self, uid):
        with self._lock:
            entry = self._gauges.get(uid)
            return dict(entry) if entry else None

    def get_annunciator(self, uid):
        with self._lock:
            entry = self._annunciators.get(uid)
            return dict(entry) if entry else None

    def find_annunciator(self, ident):
        """Look a window up by uid, or by the readable id it registered under.

        Tile uids are GUIDs generated in Unity and one rack holds dozens of
        them, so a simulation names windows by id ("RCP_1_TRIP") instead.
        Returns the entry - whose "uid" is what set_annunciator wants - or None.
        """
        if not ident:
            return None

        with self._lock:
            entry = self._annunciators.get(ident)
            if entry is not None:
                return dict(entry)

            text = str(ident).lower()
            for entry in self._annunciators.values():
                if str(entry["id"]).lower() == text:
                    return dict(entry)

        return None

    def switches(self):
        with self._lock:
            return [dict(e) for e in self._switches.values()]

    def indicators(self):
        with self._lock:
            return [dict(e) for e in self._indicators.values()]

    def gauges(self):
        with self._lock:
            return [dict(e) for e in self._gauges.values()]

    def annunciators(self):
        with self._lock:
            return [dict(e) for e in self._annunciators.values()]

    # --------------------------------------------------------------- writes

    def set_switch(self, uid, position=None, powered=None, available=None, source="server"):
        """Server-authoritative switch write. Pushed to every client on its next poll."""
        with self._lock:
            entry = self._switches.get(uid)
            if entry is None:
                return False

            changes = {}
            if position is not None and position != entry["position"]:
                resolved = self._resolve_position(entry, position)
                if resolved is None:
                    raise ValueError(
                        f"'{position}' is not a position of switch {uid} "
                        f"({', '.join(entry['positions'])})")
                if resolved != entry["position"]:
                    changes["position"] = resolved
            if powered is not None and bool(powered) != entry["powered"]:
                changes["powered"] = bool(powered)
            if available is not None and bool(available) != entry["available"]:
                changes["available"] = bool(available)

            return self._apply(entry, changes, source)

    def set_indicator(self, uid, state=None, flashing=None, source="server"):
        """Drive a switch's lamp. state is free-form; the client knows red/green/off."""
        with self._lock:
            entry = self._indicators.get(uid)
            if entry is None:
                return False

            changes = {}
            if state is not None and state != entry["state"]:
                changes["state"] = state
            if flashing is not None and bool(flashing) != entry["flashing"]:
                changes["flashing"] = bool(flashing)

            return self._apply(entry, changes, source)

    def set_gauge(self, uid, value=None, valid=None, source="server"):
        """Set a gauge value - this is the command the client's needle follows."""
        with self._lock:
            entry = self._gauges.get(uid)
            if entry is None:
                return False

            changes = {}
            if value is not None:
                clamped = _clamp(float(value), entry["minValue"], entry["maxValue"])
                if abs(clamped - entry["value"]) > VALUE_EPSILON:
                    changes["value"] = clamped
            if valid is not None and bool(valid) != entry["valid"]:
                changes["valid"] = bool(valid)

            return self._apply(entry, changes, source)

    def set_annunciator(self, uid, state=None, flashing=None, acknowledged=None,
                        flash_rate=None, silenced=None, source="server"):
        """Drive one alarm window.

        state is free-form: "clear", "off" and "normal" read as dark on the
        client, everything else ("alarm", "cleared-unacked", ...) as lit.
        flashing blinks it, in step with every other window flashing at the
        same rate in its rack group. flash_rate picks which of the two clocks
        it blinks on - ANNOUNCE_RATE for an unacknowledged alarm, CLEAR_RATE
        for ringback - and is worth setting whenever you set flashing, since a
        window that changes state usually changes rate with it. acknowledged is
        bookkeeping for whoever runs the alarm sequence - the client doesn't
        read it.

        silenced splits the lamp from the horn: a silenced window goes on
        flashing exactly as it was, and stops feeding the audible. It is per
        window rather than per panel on purpose - that is what makes the
        SILENCE pushbutton quiet what is in now without deafening the panel
        to what comes in next. A window is silenced by the operator and
        un-silenced by the sequence, never the other way round: every
        transition that starts a new audible event (a new alarm, a ringback)
        clears it. See annunciator_sim.py.
        """
        with self._lock:
            entry = self._annunciators.get(uid)
            if entry is None:
                return False

            changes = {}
            if state is not None and state != entry["state"]:
                changes["state"] = state
            if flashing is not None and bool(flashing) != entry["flashing"]:
                changes["flashing"] = bool(flashing)
            if flash_rate is not None:
                rate = normalize_flash_rate(flash_rate)
                if rate != entry.get("flashRate"):
                    changes["flashRate"] = rate
            if acknowledged is not None and bool(acknowledged) != entry["acknowledged"]:
                changes["acknowledged"] = bool(acknowledged)
            if silenced is not None and bool(silenced) != entry.get("silenced", False):
                changes["silenced"] = bool(silenced)

            return self._apply(entry, changes, source)

    # ---------------------------------------------------------- client sync

    def apply_report(self, reported, client_id="", since=None):
        """Take a client's switch report.

        Clients report every switch definition they hold every tick, so most of
        a report is already-known state. A reported change is only accepted if
        the client had seen the current value of that switch (its revision is
        <= the revision the client is reporting against) - otherwise two clients
        with different stale views would flip the switch back and forth. A
        rejected uid is returned so the caller can tell the client to correct
        itself; the corrected value is already in the same response.

        Returns {"accepted", "rejected", "unknown", "registered"} - lists of uids.
        """
        accepted, rejected, unknown, registered = [], [], [], []

        with self._lock:
            for item in reported or []:
                uid = (item or {}).get("uid")
                if not uid:
                    continue

                position = item.get("position")
                entry = self._switches.get(uid)

                if entry is None:
                    if not self._auto_register:
                        unknown.append(uid)
                        continue

                    self.define_switch(
                        uid,
                        id=item.get("id") or uid,
                        name=item.get("name") or "",
                        positions=item.get("positions"),
                        position=position,
                        save=False)
                    self._switches[uid]["updatedBy"] = client_id or "client"
                    registered.append(uid)
                    accepted.append(uid)
                    continue

                if position is None:
                    continue

                resolved = self._resolve_position(entry, position)
                if resolved is None or resolved == entry["position"]:
                    continue

                # since=None means "I haven't synced yet" - such a client would
                # be reporting scene defaults over live state.
                if since is None or entry["revision"] > since:
                    rejected.append(uid)
                    continue

                self._apply(entry, {"position": resolved}, client_id or "client")
                accepted.append(uid)

            if registered:
                # New definitions appeared, so the file on disk is now stale.
                self.save()
                for uid in registered:
                    print(f"[io] registered switch {uid} "
                          f"('{self._switches[uid]['name']}') from client {client_id or '?'}")

        return {
            "accepted": accepted,
            "rejected": rejected,
            "unknown": unknown,
            "registered": registered,
        }

    def register_annunciators(self, reported, client_id=""):
        """Take a client's annunciator definitions: the windows its racks hold.

        Definition-only. Annunciators are outputs, so a client has no state to
        report - it sends a window while the server disagrees with the rack about
        it, and stops once the server has taken it.

        A uid the server already holds has its DESCRIPTION corrected
        (ANNUNCIATOR_DESCRIBED) and nothing else: the rack is the authority on
        what it physically holds, so a rack renamed or moved to another SART
        panel takes its windows with it, while a live alarm on one of them
        survives being regrouped underneath it. Nothing a client sends can reach
        the state.

        Returns {"registered", "unknown"} - lists of uids. A corrected window
        counts as registered: either way the server has taken it and the client
        can stop sending it.
        """
        registered, unknown = [], []
        created, corrected = [], []

        with self._lock:
            for item in reported or []:
                uid = (item or {}).get("uid")
                if not uid:
                    continue

                entry = self._annunciators.get(uid)
                if entry is not None:
                    # Already ours, so this is a correction, not a new window.
                    # Taken either way - it is in the map, and telling the client
                    # otherwise would have it report the same window every tick.
                    if self._auto_register and self._redescribe(entry, item):
                        corrected.append(uid)
                    registered.append(uid)
                    continue

                if not self._auto_register:
                    unknown.append(uid)
                    continue

                # Left as "server" rather than stamped with the client, unlike a
                # registered switch: a window is an output, so there's nothing
                # to keep from echoing back, and a client filtered out of its
                # own windows would think they never registered and report them
                # again on every tick.
                self.define_annunciator(
                    uid,
                    id=item.get("id") or uid,
                    name=item.get("name") or "",
                    text=item.get("text") or "",
                    color=item.get("color") or "white",
                    group=item.get("group") or "",
                    sart_group=item.get("sartGroup") or "",
                    save=False)
                registered.append(uid)
                created.append(uid)

            if created or corrected:
                # The map changed, so the file on disk is now stale.
                self.save()
                changed = created or corrected
                what = "registered" if created else "regrouped"
                names = ", ".join(self._annunciators[uid]["id"] for uid in changed[:8])
                print(f"[io] {what} {len(changed)} annunciator window(s) from client "
                      f"{client_id or '?'}: {names}"
                      + (", ..." if len(registered) > 8 else ""))

        return {"registered": registered, "unknown": unknown}

    def changes_since(self, since=None, exclude_client=None):
        """Payload for a client: everything it hasn't seen, in wire form.

        since=None returns the full map (a first sync). Entries last written by
        exclude_client are left out - that client already has them, and echoing
        them back could fight a control it is still animating.
        """
        with self._lock:
            return {
                "sessionId": self._session_id,
                "revision": self._revision,
                "reportIntervalSeconds": self._report_interval,
                "switches": self._select(self._switches, since, exclude_client),
                "indicators": self._select(self._indicators, since, exclude_client),
                "gauges": self._select(self._gauges, since, exclude_client),
                "annunciators": self._select(self._annunciators, since, exclude_client),
            }

    def snapshot(self):
        """The whole map, unfiltered."""
        return self.changes_since(None, None)

    # -------------------------------------------------------------- internals

    def _next_revision(self):
        self._revision += 1
        return self._revision

    def _apply(self, entry, changes, source):
        if not changes:
            return False

        entry.update(changes)
        entry["revision"] = self._next_revision()
        entry["updatedBy"] = source or "server"
        return True

    def _remove(self, collection, uid, save):
        with self._lock:
            if uid not in collection:
                return False
            del collection[uid]
            self._next_revision()
            if save:
                self.save()
            return True

    def _select(self, collection, since, exclude_client):
        """Entries newer than `since`, in wire form (updatedBy stays server-side:
        it's an opaque client id, and the client's own changes are filtered out
        here anyway)."""
        entries = []
        for entry in collection.values():
            if since is not None and entry["revision"] <= since:
                continue
            if exclude_client and entry.get("updatedBy") == exclude_client:
                continue
            entries.append({key: value for key, value in entry.items() if key != "updatedBy"})

        entries.sort(key=lambda e: e["revision"])
        return entries

    @staticmethod
    def _resolve_position(entry, position):
        """Match a reported position against the switch's own list, loosely."""
        if position is None:
            return None

        text = str(position)
        for known in entry["positions"]:
            if known.lower() == text.lower():
                return known

        return None

    def _load_switch(self, entry):
        if not isinstance(entry, dict) or not entry.get("uid"):
            return
        self.define_switch(
            entry["uid"],
            id=entry.get("id"),
            name=entry.get("name", ""),
            positions=entry.get("positions"),
            position=entry.get("position"),
            powered=entry.get("powered", True),
            available=entry.get("available", True),
            save=False)

    def _load_indicator(self, entry):
        if not isinstance(entry, dict) or not entry.get("uid"):
            return
        self.define_indicator(
            entry["uid"],
            id=entry.get("id"),
            name=entry.get("name", ""),
            state=entry.get("state", "off"),
            flashing=entry.get("flashing", False),
            save=False)

    def _load_gauge(self, entry):
        if not isinstance(entry, dict) or not entry.get("uid"):
            return
        self.define_gauge(
            entry["uid"],
            id=entry.get("id"),
            name=entry.get("name", ""),
            units=entry.get("units", ""),
            min_value=entry.get("minValue", 0.0),
            max_value=entry.get("maxValue", 100.0),
            value=entry.get("value", 0.0),
            valid=entry.get("valid", True),
            save=False)

    def _load_annunciator(self, entry):
        if not isinstance(entry, dict) or not entry.get("uid"):
            return
        self.define_annunciator(
            entry["uid"],
            id=entry.get("id"),
            name=entry.get("name", ""),
            text=entry.get("text", ""),
            color=entry.get("color", "white"),
            group=entry.get("group", ""),
            state=entry.get("state", DEFAULT_ANNUNCIATOR_STATE),
            flashing=entry.get("flashing", False),
            flash_rate=entry.get("flashRate", DEFAULT_FLASH_RATE),
            acknowledged=entry.get("acknowledged", False),
            silenced=entry.get("silenced", False),
            save=False)

    def _redescribe(self, entry, item):
        """Correct what a client says about a window the server already holds.

        Only ANNUNCIATOR_DESCRIBED - the rack's own description of its tile.
        Stamped "server" rather than with the client, like a fresh definition:
        a client filtered out of its own windows would never see the correction
        land and would report it forever.
        """
        changes = {}

        for field in ANNUNCIATOR_DESCRIBED:
            value = item.get(field)
            if value is None:
                continue

            value = str(value)

            # An empty name or colour is a report that has nothing to say about
            # them, not a request to blank them out. An empty GROUP is
            # meaningful: it is how a rack says "no panel commands this".
            if not value and field in ("name", "text", "color"):
                continue

            if value != entry.get(field, ""):
                changes[field] = value

        return self._apply(entry, changes, "server") if changes else False


def normalize_flash_rate(value):
    """One of FLASH_RATES. Anything else - None, "", a typo - is an announce.

    Defaulting to announce rather than rejecting keeps a sim that only says
    flashing=True working, and errs towards "this is a live alarm" rather
    than towards the quieter ringback.
    """
    text = str(value or "").strip().lower()
    return text if text in FLASH_RATES else DEFAULT_FLASH_RATE


def _persist(entry, fields):
    return {field: entry[field] for field in fields if field in entry}


def _clamp(value, low, high):
    if low > high:
        low, high = high, low
    return max(low, min(high, value))


# The instance the server and the simulation share.
state = IoState()
