"""Live control-room I/O: the state the Unity client syncs against.

Everything is keyed by the Unity definition UID - the GUID on a
SwitchDefinition / GaugeDefinition asset - so the server and the scene agree on
what "this control" means without caring about names or hierarchy.

Three collections, defined in data/io_definitions.json:

    switches    inputs.  The client reports the position each switch is in.
    indicators  outputs. Lamp state for a switch, keyed by that switch's uid.
    gauges      outputs. The server sets a value, the client's needle follows.

Use it from the simulation side like this:

    from io_state import state

    pump = state.get_switch("a250f6ec-0dab-4358-9525-72a699375448")
    if pump and pump["position"] == "on":
        state.set_gauge("33bee2dd-3a3d-4c17-ad22-a3933648f795", 50.0)
        state.set_indicator("a250f6ec-0dab-4358-9525-72a699375448", "red")

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
DEFAULT_REPORT_INTERVAL = 0.2

# Written back to the JSON; revision/updatedBy are runtime bookkeeping and stay
# out of the file so it remains comfortable to hand-edit.
SWITCH_PERSISTED = ["uid", "id", "name", "positions", "position", "powered", "available"]
INDICATOR_PERSISTED = ["uid", "id", "name", "state", "flashing"]
GAUGE_PERSISTED = ["uid", "id", "name", "units", "minValue", "maxValue", "value", "valid"]


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
            self._revision = 0

            for entry in document.get("switches", []):
                self._load_switch(entry)
            for entry in document.get("indicators", []):
                self._load_indicator(entry)
            for entry in document.get("gauges", []):
                self._load_gauge(entry)

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

    def remove_switch(self, uid, save=True):
        return self._remove(self._switches, uid, save)

    def remove_indicator(self, uid, save=True):
        return self._remove(self._indicators, uid, save)

    def remove_gauge(self, uid, save=True):
        return self._remove(self._gauges, uid, save)

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

    def switches(self):
        with self._lock:
            return [dict(e) for e in self._switches.values()]

    def indicators(self):
        with self._lock:
            return [dict(e) for e in self._indicators.values()]

    def gauges(self):
        with self._lock:
            return [dict(e) for e in self._gauges.values()]

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


def _persist(entry, fields):
    return {field: entry[field] for field in fields if field in entry}


def _clamp(value, low, high):
    if low > high:
        low, high = high, low
    return max(low, min(high, value))


# The instance the server and the simulation share.
state = IoState()
