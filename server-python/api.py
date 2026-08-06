"""JSON API for the Unity client, served by server.py alongside the control page.

Read (GET):

    /api           list of endpoints + API version
    /api/info      handshake the client's join screen uses to validate a server
    /api/template  the control-room template (panels, annunciators, layout)
    /api/io        live I/O state; ?since=<revision> for just what changed

Write (POST, JSON bodies):

    /api/io/report  the client's periodic switch report; answers with its diff
    /api/io/set     server-authoritative write to gauges/indicators/switches
    /api/io/save    persist current I/O values to data/io_definitions.json

The template lives in data/control_room_template.json and is re-read per
request. Live I/O lives in io_state.py (backed by data/io_definitions.json),
keyed by Unity definition UID.

Key naming: responses use camelCase because the Unity client parses them with
JsonUtility, which maps JSON keys straight onto C# field names (so no hyphens -
"switchState", not "switch-state").
"""

from pathlib import Path
import json

from io_state import state

BASE_DIR = Path(__file__).parent
TEMPLATE_FILE = BASE_DIR / "data" / "control_room_template.json"

# Bump when the shape of a response changes in a way old clients can't read.
# Must stay in sync with ServerConnection.SupportedApiVersion on the client.
API_VERSION = 1

SERVER_NAME = "PNPP Python Server"
MAX_PLAYERS = 8

ENDPOINTS = [
    "/api",
    "/api/info",
    "/api/template",
    "/api/io",
    "/api/io/report",
    "/api/io/set",
    "/api/io/save",
]


class ApiError(Exception):
    """Raised for a request we can answer with a JSON error body."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


def load_template():
    """Read the control-room template from disk. Raises ApiError on bad input."""
    try:
        text = TEMPLATE_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ApiError(500, f"Template file not found: {TEMPLATE_FILE.name}")

    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise ApiError(500, f"Template file is not valid JSON: {error}")


def build_info(server_status=None):
    """Handshake payload: enough for the client to name the server and check it."""
    template = load_template()
    plant = template.get("plant", {})
    status = server_status or {}

    return {
        "server": SERVER_NAME,
        "apiVersion": API_VERSION,
        "templateVersion": template.get("templateVersion", 0),
        "plantName": plant.get("name", "Unknown plant"),
        "unit": plant.get("unit", 0),
        "reactorType": plant.get("reactorType", ""),
        "scene": plant.get("scene", ""),
        # No session tracking yet - the client only displays these.
        "players": 0,
        "maxPlayers": MAX_PLAYERS,
        "host": status.get("host", ""),
        "port": status.get("port", 0),
        "endpoints": ENDPOINTS,
    }


def handle_get(path, query=None, server_status=None):
    """Route a GET under /api. Returns (http_status, payload_dict).

    query is the parsed query string ({name: [values]}), as parse_qs returns it.
    """
    path = path.rstrip("/") or "/api"
    query = query or {}

    try:
        if path == "/api":
            return 200, {"apiVersion": API_VERSION, "endpoints": ENDPOINTS}

        if path == "/api/info":
            return 200, build_info(server_status)

        if path == "/api/template":
            return 200, load_template()

        if path == "/api/io":
            # No ?since= means a full sync; the client asks for that on connect
            # and whenever the server's session id changes under it.
            since = _query_int(query, "since")
            client_id = _query_str(query, "clientId")
            return 200, state.changes_since(since, exclude_client=client_id)

    except ApiError as error:
        return error.status, {"error": error.message}

    return 404, {"error": f"Unknown endpoint: {path}", "endpoints": ENDPOINTS}


def handle_post(path, body=None):
    """Route a POST under /api. body is the decoded JSON object (or None)."""
    path = path.rstrip("/") or "/api"
    body = body if isinstance(body, dict) else {}

    try:
        if path == "/api/io/report":
            return 200, io_report(body)

        if path == "/api/io/set":
            return 200, io_set(body)

        if path == "/api/io/save":
            path_written = state.save()
            return 200, {"saved": str(path_written), "revision": state.revision}

    except ApiError as error:
        return error.status, {"error": error.message}
    except ValueError as error:
        return 400, {"error": str(error)}

    return 404, {"error": f"Unknown endpoint: {path}", "endpoints": ENDPOINTS}


def io_report(body):
    """The client's periodic switch report, answered with everything it's missing.

    One round trip both ways: the client sends the position of every switch
    definition it holds, and gets back the switches other players moved, the
    indicator states and the gauge values it hasn't seen yet.
    """
    client_id = str(body.get("clientId") or "")
    since = body.get("since")
    since = int(since) if isinstance(since, (int, float)) and since >= 0 else None

    outcome = state.apply_report(body.get("switches"), client_id=client_id, since=since)

    payload = state.changes_since(since, exclude_client=client_id)
    payload["accepted"] = outcome["accepted"]
    payload["rejected"] = outcome["rejected"]
    payload["unknown"] = outcome["unknown"]
    payload["registered"] = outcome["registered"]
    return payload


def io_set(body):
    """Server-authoritative write. Any of switches / indicators / gauges.

        {"gauges": [{"uid": "...", "value": 47.5}],
         "indicators": [{"uid": "...", "state": "red", "flashing": true}],
         "switches": [{"uid": "...", "position": "on"}]}

    Unknown uids come back in "unknown" - this endpoint writes to definitions,
    it doesn't create them (define_* in io_state.py does that).
    """
    changed, unknown = [], []

    for item in _entries(body, "switches"):
        uid = item.get("uid")
        if state.get_switch(uid) is None:
            unknown.append(uid)
        elif state.set_switch(uid, position=item.get("position"),
                              powered=item.get("powered"), available=item.get("available")):
            changed.append(uid)

    for item in _entries(body, "indicators"):
        uid = item.get("uid")
        if state.get_indicator(uid) is None:
            unknown.append(uid)
        elif state.set_indicator(uid, state=item.get("state"), flashing=item.get("flashing")):
            changed.append(uid)

    for item in _entries(body, "gauges"):
        uid = item.get("uid")
        if state.get_gauge(uid) is None:
            unknown.append(uid)
        elif state.set_gauge(uid, value=item.get("value"), valid=item.get("valid")):
            changed.append(uid)

    return {"revision": state.revision, "changed": changed, "unknown": unknown}


def _entries(body, key):
    value = body.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _query_int(query, name):
    values = query.get(name)
    if not values:
        return None

    try:
        number = int(values[0])
    except (TypeError, ValueError):
        raise ApiError(400, f"'{name}' must be an integer")

    return number if number >= 0 else None


def _query_str(query, name):
    values = query.get(name)
    return str(values[0]) if values else None
