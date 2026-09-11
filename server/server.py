from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import argparse
import json
import sys
import threading
import time

from ann_panel_test import AnnPanelTest   # TEMPORARY: panel-wide flash test
from annunciator_sim import AnnunciatorSimulation
from cr_data import *
from rcp_sim import RcpSimulation
from rcs_thermal import RcsThermalSimulation
from rod_sim import RodSimulation
from turbine_sim import TurbineSimulation
from valve_sim import ValveSimulation
import api
import commands

BASE_DIR = Path(__file__).parent
INDEX_FILE = BASE_DIR / "index.html"
STYLE_FILE = BASE_DIR / "style.css"


class ServerManager:
    def __init__(self, host="0.0.0.0", port=8000):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
        self.running = False
        self.last_message = "Server is stopped."
        self.lock = threading.RLock()

    def configure(self, host=None, port=None):
        with self.lock:
            if host is not None:
                self.host = "0.0.0.0" if host in {"", "localhost"} else host
            if port is not None:
                self.port = int(port)
            return self.host, self.port

    def start(self, host=None, port=None):
        with self.lock:
            self.configure(host=host, port=port)
            if self.running and self.server is not None:
                self.stop()
                time.sleep(0.2)

            self.server = ThreadingHTTPServer((self.host, self.port), MyHandler)
            self.server.manager = self
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
            self.running = True
            self.last_message = f"Serving on http://{self.host}:{self.port}"
            return self.last_message

    def stop(self):
        with self.lock:
            if not self.running or self.server is None:
                self.running = False
                self.last_message = "Server is stopped."
                return self.last_message

            server = self.server
            self.server = None
            self.running = False
            self.last_message = "Server stopped."

        try:
            server.shutdown()
            server.server_close()
        except Exception:
            print("Error stopping server:", file=sys.stderr)

            pass

        if self.thread is not None:
            self.thread.join(timeout=2)
            self.thread = None

        return self.last_message

    def status(self):
        with self.lock:
            return {
                "running": self.running,
                "host": self.host,
                "port": self.port,
                "message": self.last_message,
            }


class MyHandler(BaseHTTPRequestHandler):
    # Keep-alive: the client syncs several times a second, and every response
    # here sets Content-Length, so 1.1 is safe and saves a reconnect per tick.
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        # /api/io traffic arrives several times a second per client — don't
        # narrate it. Everything else logs as usual.
        if not self.path.startswith("/api/io"):
            super().log_message(format, *args)

    def _send_cors_headers(self):
        # The Unity editor ignores CORS, but WebGL builds and the browser
        # control page don't.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _send_json(self, payload, status=200):
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self._send_cors_headers()
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text, content_type):
        body = text.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/status":
            self._send_json(self.server.manager.status())
            return

        if path == "/api" or path.startswith("/api/"):
            status, payload = api.handle_get(
                path,
                query=parse_qs(parsed.query, keep_blank_values=True),
                server_status=self.server.manager.status())
            self._send_json(payload, status=status)
            return

        if path == "/style.css":
            self._send_text(STYLE_FILE.read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return

        html = INDEX_FILE.read_text(encoding="utf-8")
        self._send_text(html, "text/html; charset=utf-8")

    def _read_body(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        return self.rfile.read(length).decode("utf-8") if length > 0 else ""

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api" or path.startswith("/api/"):
            raw = self._read_body()
            try:
                payload = json.loads(raw) if raw.strip() else {}
            except json.JSONDecodeError as error:
                self._send_json({"error": f"Body is not valid JSON: {error}"}, status=400)
                return

            status, response = api.handle_post(path, payload)
            self._send_json(response, status=status)
            return

        if path != "/control":
            self.send_error(404)
            return

        body = self._read_body()
        data = parse_qs(body, keep_blank_values=True)

        action = data.get("action", [""])[0].lower()
        host = data.get("host", [None])[0]
        port_value = data.get("port", [None])[0]

        try:
            port = int(port_value) if port_value not in (None, "") else None
        except ValueError:
            port = None

        manager = self.server.manager
        if action in {"start", "restart"}:
            manager.start(host=host, port=port)
        elif action == "stop":
            manager.stop()
        else:
            manager.last_message = "Unknown action."

        self._send_json(manager.status())


def parse_args():
    parser = argparse.ArgumentParser(description="Run the PNPP server with a browser-based control page")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-sim", action="store_true",
                        help="don't run the test simulations")
    parser.add_argument("--ann-test", action="store_true",
                        help="TEMPORARY: flash every labeled annunciator window "
                             "(ann_panel_test.py). Masks the real alarms, so it "
                             "is off unless you ask for it")
    return parser.parse_args()


def console():
    """Read commands off stdin until told to stop.

    Blocking on stdin is fine - the HTTP server and every simulation are on
    their own threads. Returning ends the server, so a quit word returns and
    EOF does not: a server started with nothing on stdin (a service, nohup)
    would otherwise shut down the moment it came up. Piped input therefore
    runs its commands and then leaves the server up, same as a terminal.
    """
    if sys.stdin is not None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            if line.lstrip("/").lower() in commands.QUIT_WORDS:
                return
            answer = commands.dispatch(line)
            if answer:
                print(answer, flush=True)

    print("Console closed; serving until interrupted.", flush=True)
    while True:
        time.sleep(0.5)


def main():
    args = parse_args()
    manager = ServerManager(host=args.host, port=args.port)
    manager.start()

    sims = []
    if not args.no_sim:
        # Valves before the turbine: the turbine's demand is a valve position,
        # and the rods chase the load the turbine makes of it. RCS temperatures
        # after the rods and the pumps, because they are power over flow.
        # Annunciators last - they alarm on what everything else has written.
        sims = [RcpSimulation(), ValveSimulation(), TurbineSimulation(),
                RodSimulation(), RcsThermalSimulation(), AnnunciatorSimulation()]
        # TEMPORARY, and now opt-in: it drives every dark labeled window to
        # alarm, which buries the RCP alarms the console is there to raise.
        if args.ann_test:
            sims.append(AnnPanelTest())
        for sim in sims:
            sim.start()

    display_host = "localhost" if manager.host in {"127.0.0.1", "0.0.0.0", "::"} else manager.host
    print(f"Serving on http://{display_host}:{manager.port}")
    if sims:
        print("Simulations running (4 RCPs with their electrical supply, turbine "
              "+ bypass valves, turbine run-up, rod control and the temporary "
              "reactor power model, RCS temperatures, annunciators; "
              "--no-sim to disable).")
    if args.ann_test:
        print("TEMPORARY: every labeled annunciator window flashes on client "
              "load (ann_panel_test.py).")
    print("Open the control page at http://localhost:<port>/ to change settings.")
    print("Type /help for the console commands, or 'e' to stop the server.")

    try:
        console()
    except KeyboardInterrupt:
        pass

    print("\nStopping server...")
    manager.stop()

    for sim in sims:
        sim.stop()

    print("Server stopped.")


if __name__ == "__main__":
    main()