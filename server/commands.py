"""The server console: typed commands that reach into the running simulation.

Everything here is an instructor's console rather than an operator's. The panel
in the client is what an operator gets; these are the things that happen TO a
plant - a bus that drops out, a relay that picks up, a breaker somebody racked
out - which have to come from somewhere and have no control in the control room.

    /turnswitch <switch> <position>   move any switch as if a hand had
    /fault add|clear <fault>          insert or clear a casualty
    /fault clearall                   clear the lot
    /component <component> <action>   act on one component
    /status                           what the console can see and the panel can't
    /rods [action]                    rod banks, reactivity and reactor power
    /rcs                              RCS temperatures, per loop
    /help [command]                   these lines, or detail on one

Names are matched loosely: case, spaces, hyphens and underscores are all the
same thing, so `RCP 1 Power`, `rcp-1-power` and `rcp_1_power` all find the same
switch. A switch position may be its name (`on`, `left`) or its 1-based number,
which is what `pos1/2/3` means for a three-position switch.

Commands take a leading slash or not, as you like. server.py reads lines off
stdin and hands each one to dispatch(); nothing else calls in here, so a command
can assume it is on the console thread and that printing is the way it answers.
"""

from io_state import state
from rcp_sim import COMPONENT_ACTIONS, FAULTS, plant
from rcs_thermal import rcs
from rod_sim import COMPONENT_ACTIONS as ROD_ACTIONS, core

# Ways of saying "stop the server", handled by server.py rather than here.
QUIT_WORDS = {"e", "q", "quit", "exit", "stop"}


class CommandError(Exception):
    """Bad input from the console. The message is for the person who typed it."""


def dispatch(line):
    """Run one console line. Returns the text to print back, or "" for nothing.

    Raises nothing: a CommandError becomes the answer, because a typo on a
    console shouldn't take the simulation down with it.
    """
    words = str(line).strip().split()
    if not words:
        return ""

    name = words[0].lstrip("/").lower()
    args = words[1:]

    handler = HANDLERS.get(name)
    if handler is None:
        return f"Unknown command '{name}'. /help lists them."

    try:
        return handler(args)
    except CommandError as error:
        return f"{error}"
    except ValueError as error:
        return f"{error}"


# ------------------------------------------------------------------ /turnswitch

def turnswitch(args):
    """/turnswitch <switch> <position> - move a switch server-side.

    The name may have spaces in it, so the position is the LAST word and
    everything before it is the name.
    """
    if len(args) < 2:
        raise CommandError("usage: /turnswitch <switch name> <position|1|2|3>")

    wanted, name = args[-1], " ".join(args[:-1])
    entry = _find_switch(name)
    position = _resolve_position(entry, wanted)

    if entry["position"] == position:
        return f"{entry['name']} is already in '{position}'"

    state.set_switch(entry["uid"], position=position, source="console")
    return f"{entry['name']}: {entry['position']} -> {position}"


def _find_switch(name):
    """By uid, then by id or name with spacing and case ignored."""
    entry = state.get_switch(name)
    if entry is not None:
        return entry

    wanted = _slug(name)
    matches = [e for e in state.switches()
               if _slug(e["id"]) == wanted or _slug(e["name"]) == wanted]
    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        raise CommandError(
            f"'{name}' matches {len(matches)} switches: "
            + ", ".join(sorted(e["name"] for e in matches)))

    known = ", ".join(sorted(e["name"] for e in state.switches())) or "none defined yet"
    raise CommandError(f"No switch called '{name}'. Known switches: {known}")


def _resolve_position(entry, wanted):
    """A position name, or its 1-based number - `pos1/2/3` on a three-way."""
    positions = entry["positions"]

    if wanted.isdigit():
        index = int(wanted)
        if not 1 <= index <= len(positions):
            raise CommandError(
                f"{entry['name']} has {len(positions)} positions "
                f"(1-{len(positions)}): {', '.join(positions)}")
        return positions[index - 1]

    for position in positions:
        if _slug(position) == _slug(wanted):
            return position

    raise CommandError(
        f"'{wanted}' is not a position of {entry['name']} ({', '.join(positions)})")


# ----------------------------------------------------------------------- /fault

def fault(args):
    """/fault add|clear <name>, or /fault clearall."""
    if not args:
        raise CommandError(_fault_usage())

    action = args[0].lower()

    if action == "clearall":
        return plant.clear_all_faults()

    if action not in {"add", "clear"}:
        raise CommandError(_fault_usage())

    if len(args) < 2:
        raise CommandError(_fault_usage())

    name = _slug(" ".join(args[1:]), joiner="-")
    if name not in FAULTS:
        raise CommandError(f"Unknown fault '{name}'.\n{_fault_list()}")

    return plant.add_fault(name) if action == "add" else plant.clear_fault(name)


def _fault_usage():
    return "usage: /fault add|clear <fault>, or /fault clearall\n" + _fault_list()


def _fault_list():
    lines = ["Faults:"]
    lines += [f"  {name:<18} {text}" for name, text in sorted(FAULTS.items())]
    return "\n".join(lines)


# ------------------------------------------------------------------- /component

def component(args):
    """/component <component> <action>."""
    if len(args) < 2:
        raise CommandError(_component_usage())

    return plant.component(_slug(" ".join(args[:-1]), joiner="-"), args[-1])


def _component_usage():
    lines = ["usage: /component <component> <action>",
             "Components: " + ", ".join(pump.key for pump in plant.pumps),
             "Actions (rcp-n):"]
    lines += [f"  {name:<12} {text}" for name, text in sorted(COMPONENT_ACTIONS.items())]
    return "\n".join(lines)


# ---------------------------------------------------------------------- /status

def status(args):
    """/status - the RCP electrical picture, which has no panel indication."""
    return "\n".join(["RCP plant:"] + plant.status_lines())


# ------------------------------------------------------------------------ /rods

def rods(args):
    """/rods - bank positions, the reactivity balance and reactor power.

    Almost none of this is on the panel: the two rod controls are there but the
    step counters and the nuclear instruments aren't, so the console is the only
    place to read what the lever just did. With an action it drives the reactor
    trip, which is likewise a control the room hasn't got yet.
    """
    if not args:
        return "\n".join(["Rod control:"] + core.status_lines())

    if len(args) > 1:
        raise CommandError(_rods_usage())

    return core.component(args[0])


def _rods_usage():
    lines = ["usage: /rods, or /rods <action>",
             "Actions:"]
    lines += [f"  {name:<8} {text}" for name, text in sorted(ROD_ACTIONS.items())]
    return "\n".join(lines)


# ------------------------------------------------------------------------- /rcs

def rcs_command(args):
    """/rcs - Tavg, core dT and each loop's legs.

    None of this is on the panel yet: the gauges exist on the wire so the Unity
    faces have uids to bind to, but no dial has been baked for them.
    """
    return "\n".join(["RCS temperatures:"] + rcs.status_lines())


# ------------------------------------------------------------------------ /help

HELP = {
    "turnswitch": "/turnswitch <switch name> <position|1|2|3>\n"
                  "  Move a switch server-side, as if a hand had. The client\n"
                  "  animates it into place on its next sync.\n"
                  "  e.g. /turnswitch RCP 1 Power on\n"
                  "       /turnswitch Turbine Valve 3",
    "status": "/status\n  Bus, MCC, breaker, speed and trip state for all four RCPs.",
    "rcs": "/rcs\n  Tavg and its programme, core dT, and Th/Tc for each loop.\n"
           "  Core dT is power over flow, so losing a pump raises Th and drops\n"
           "  Tc around a Tavg that hasn't moved.",
    "help": "/help [command]\n  This list, or the detail for one command.",
}

# /fault, /component and /rods aren't in HELP because their detail IS the list
# of what they accept, and that comes out of the simulation rather than being
# typed here a second time and left to rot.
GENERATED_HELP = {
    "fault": _fault_usage,
    "component": _component_usage,
    "rods": _rods_usage,
}


def help_command(args):
    if args:
        name = args[0].lstrip("/").lower()
        if name in GENERATED_HELP:
            return GENERATED_HELP[name]()
        if name in HELP:
            return HELP[name]
        return f"No such command '{name}'. /help lists them."

    return "\n".join([
        "Console commands:",
        "  /turnswitch <switch> <position>   move a switch (name, or 1/2/3)",
        "  /fault add|clear <fault>          insert or clear a casualty",
        "  /fault clearall                   clear every fault",
        "  /component <name> <action>        act on one component",
        "  /status                           RCP electrical + machine state",
        "  /rods [action]                    rod banks, reactivity, reactor power",
        "  /rcs                              RCS temperatures, per loop",
        "  /help [command]                   detail on one command",
        "",
        "  e                                 stop the server",
        "",
        "/help fault, /help component and /help rods list what they accept.",
    ])


HANDLERS = {
    "turnswitch": turnswitch,
    "fault": fault,
    "component": component,
    "status": status,
    "rods": rods,
    "rcs": rcs_command,
    "help": help_command,
}


def _slug(text, joiner=" "):
    """Fold case, and treat spaces, hyphens, underscores and dots as the same.

    Lets "RCP 1 Power", "rcp-1-power" and "RCP_1_POWER" all be one name, which
    matters because switch ids come from Unity asset names while the fault and
    component names in this console are hyphenated.
    """
    cleaned = "".join(character if character.isalnum() else " " for character in str(text))
    return joiner.join(cleaned.lower().split())
