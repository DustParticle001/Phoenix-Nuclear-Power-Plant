"""Rod control, and a deliberately trivial reactor power model hung off it.

TEMPORARY, and knowingly so. Two controls exist on the Rod Section of the
benchboard - the BANK SELECTOR and the IN / HOLD / OUT lever - and until there
is a secondary plant, a Tavg program, boron and instrumentation to control
against, the only thing they can drive is a stand-in. What is here is the
Westinghouse rod control SYSTEM done properly, because that part is cheap to
get right, plus the smallest reactivity-to-power model that behaves like a core
instead of like a lookup table. See "What this is not" at the bottom.

THE CONTROLS. Two, both on the Rod Section:

    Rod Bank Selector   RotNp, ten detents. MAN, the four shutdown banks, the
                        four control banks, AUTO - see SELECTIONS. A detent is
                        a state, so this is read as a level.
    Rod Control Lever   Rot3pSpring, IN / HOLD / OUT, spring-return to HOLD.
                        Also read as a LEVEL, unlike the RCP control switch:
                        the rods step for as long as the lever is held, so a
                        hold is not one command but a train of them. The one
                        edge that matters is the first, because a magnetic jack
                        cannot move less than a whole step - so however brief
                        the bump, the selected bank moves once.
    Fast Withdraw       Rot2p, off/on, and NOT a control any plant has - see
                        FAST_WITHDRAW_MULTIPLIER. On, every control an operator
                        HOLDS runs 20x - the lever and the boric acid control
                        below - so a startup takes a minute and a half instead
                        of half an hour. It touches nothing automatic.

and three more that belong to systems this module is only borrowing until they
get files of their own:

    Boric Acid Control  Rot3pSpring, BORATE / HOLD / DILUTE, on the CVCS
                        section. A level, like the rod lever. Chemical shim -
                        see the boron block below.
    RPS A/B Trip        Trans2pSpring pushbuttons, one per train. Read as
    RPS A/B Close       EDGES, unlike the levers: a button is one command
                        however long a thumb sits on it. CLOSE is the reset -
                        resetting a reactor trip is closing the trip breaker,
                        and see RPS_RESET for why it must not be called that.

THE INDICATION. Ten meters beside them: the APRM reading reactor power 0-120 %
of rated, a period meter, and one 0-228 step position meter per bank. The bank
meters stand in for two instruments a real plant has and this client has no
controller for - the group demand STEP COUNTERS, which are digital readouts,
and DRPI, which reads each rod individually off its CRDM coil stack. Everything
else the model knows (the reactivity balance, which rod stop is standing) has no
panel indication at all and lives on the console under /rods.

THE BANKS. Eight, four shutdown and four control, 53 rod cluster control
assemblies between them. Each bank has 228 steps of travel and a 5/8 in
magnetic-jack step, so full travel is the 12 ft core. Position is "steps
withdrawn": 0 is on the bottom, 228 is fully out.

    Shutdown banks  withdrawn first and left fully out for the whole run. They
                    move only when the selector names one of them; MAN and AUTO
                    never touch them, and the control banks will not withdraw
                    until all four are out.
    Control banks   the ones that move at power, in an overlap sequence: the
                    next bank starts out when the one before it reaches
                    CONTROL_BANK_OVERLAP, so for the last 100 steps of a bank's
                    travel two banks step together. At most two ever move at
                    once. Selecting a control bank on its own defeats the
                    sequence and moves that bank alone, which is what the
                    individual detents are for.

THE POWER MODEL. A reactivity balance and a period, which is the least that
behaves like a reactor:

    rho = core excess - worth still inserted - boron - power defect x power

Withdrawing rods recovers worth on the usual S-curve (differential worth is
zero at both ends where the flux is low, greatest at mid-core). Power feeds
back through the power defect, so rho falls as power rises and the core settles
rather than running: 16 pcm of rods is about 1 % of power.

The core excess is pinned to ARO_POWER_PCT, so all rods out at the nominal
boron concentration asks for 122 % rather than politely sitting on rated. Boron
is what brings it back, which is the whole reason chemical shim exists - and
which is why pulling everything out without borating trips the reactor on high
flux on the way up.

Power follows the period, the way an operator reads it - startup rate in
decades per minute, one-group delayed neutrons. Positive rho gives a positive
SUR and power climbs a decade at a time; negative rho decays it, floored at
-1/3 DPM, which is the real limit set by the longest-lived delayed group and
not a fudge. Rod worth is what limits how fast any of this happens: 48 steps a
minute against 7.5 pcm a step is about 6 pcm/s, so a continuous pull is 20-odd
%/min of power and not a step change. The period meter is the inverse of that
startup rate, which is why it pegs when nothing is going on - see
PERIOD_MAX_SECONDS for how the dial reads.

PROTECTION. Two trip breakers, RTA and RTB, in series in the rod drive supply,
so either one open drops every bank to the bottom in ROD_DROP_SECONDS. Each has
a trip and a reset pushbutton on the panel, and a breaker will not reset while
flux is still above the setpoint - the same sealed-in rule the RCP lockouts use.

One automatic function opens them both: power range neutron flux high. That is
a stand-in for RPS, which is a system of its own and not written yet - the real
thing has a couple of dozen inputs and these breakers are the last two inches
of it.

WHAT THIS IS NOT. Boron is here but only as a deviation from nominal, on a
percentage rather than in ppm, and moving 20-odd times faster than a real
charging path could shift a concentration. There is no Tavg, no xenon, no decay
heat, no source range instrumentation and no secondary plant. In particular the
causality is backwards from a real PWR at power, where steam demand sets power
and the rods only trim Tavg; here rod position sets power, because there is
nothing else to set it. AUTO papers over that by chasing the turbine's load,
which is what holding Tavg on program amounts to - when the SG and Tavg systems
land, that is the piece to delete first.

server.py starts it automatically; pass --no-sim to run the server bare.
Missing definitions are created on startup (persisting them to
data/io_definitions.json), so the sim also works before any client connects.
"""

import math
import threading
import time

from io_state import state
from turbine_sim import GEN_LOAD, RATED_LOAD_MW

# Unity definition uids. Unlike the RCP and turbine tables these were generated
# HERE rather than in Unity, because the controls went into the scene as
# placeholders with nothing assigned - the assets under
# Controls/Definitions/Rod Section carry these ids now.
SELECTOR = "0a796bbb-f077-4994-a5e1-7a7dda0a141b"   # Rod Bank Selector (RotNp)
LEVER = "e6c75ffc-9f04-40cf-9b6b-325a2f33473f"      # Rod Control Lever (Rot3pSpring)
FAST_WITHDRAW = "f1f6859a-1ff9-4087-9ffa-5849bfd05836"   # Fast Withdraw (Rot2p)
RX_POWER = "7ac28af5-c032-4b2f-b064-8c5da5ce9f38"   # APRM.asset, % of rated
PERIOD = "15001ded-baa5-4601-b1c1-bea403032f01"     # Period.asset, seconds

# CVCS, under Controls/Definitions/CVCS Section. One switch and one meter, and
# the whole of the chemical shim as far as this module is concerned.
CVCS_SWITCH = "02d05332-5bbd-47ab-86bb-9695a6979e29"    # boric acid control
BORIC_ACID = "47c04141-4b12-47f4-8586-ffba5a356ece"     # Boric Acid, % of range

# RPS, under Controls/Definitions/RPS Section. Two trains, a trip and a reset
# pushbutton each (Trans2pSpring, so released/pressed).
#
# The reset buttons are called CLOSE on both sides, which is what they do -
# resetting a reactor trip is closing the trip breaker. They are not called
# "reset" because annunciator_sim.py classifies SART buttons off the tail of a
# switch's name: anything ending in "Reset" reads as an alarm reset, and a
# cluster whose group matches no rack falls back to commanding every window on
# the plant. "RPS A Reset" would therefore have cleared every ringback in the
# control room. Anything not ending in acknowledge/ack/silence/reset/test is
# safe to rename these to.
RPS_TRIP = {"A": "bcc2377b-7888-422f-b6b6-e593db85bf9d",
            "B": "f0541f68-6757-4d71-a5ad-e9f5563b288b"}
RPS_RESET = {"A": "a05647e9-c7b0-4a43-8209-eac5a3719b7e",
             "B": "63388349-c123-433e-bd00-be525a84f918"}
RPS_TRAINS = ("A", "B")

# What the two pushbuttons per train are called on the wire and on the panel.
RPS_BUTTON_NAMES = {"trip": "Trip", "reset": "Close"}

# ---------------------------------------------------------------- the machine

STEPS_FULL_OUT = 228        # steps withdrawn with the bank fully out
STEP_INCHES = 0.625         # 5/8 in per magnetic-jack step; 228 steps = 12 ft

# Where the next control bank picks up. The sequence is written in terms of this
# one number: bank B starts out when bank A reaches 128 steps, so the two of
# them step together over A's last 100 steps and never a third alongside.
CONTROL_BANK_OVERLAP = 128

# Rod speeds. Manual is a fixed rate; the automatic controller has a speed
# program between these two ends.
MANUAL_STEPS_PER_MIN = 48.0     # 30 in/min
AUTO_MIN_STEPS_PER_MIN = 8.0
AUTO_MAX_STEPS_PER_MIN = 72.0   # 45 in/min

# FAST WITHDRAW is not a control any plant has. Withdrawing every bank from the
# bottom is 912 steps of shutdown bank and 612 of control bank demand, which at
# 48 steps a minute is a bit over half an hour - fine for the operator it is
# modelled on and useless for anyone testing the thing. Boration is the same
# problem from the other end: holding the core at rated with the rods out wants
# 4.4 % of boric acid, which is three quarters of a minute of holding a switch
# to reach and the same again to undo.
#
# On, this multiplies every control an operator HOLDS - the rod lever and the
# boric acid control - by the SAME factor, so their authority relative to each
# other is unchanged and the reactivity balance is still worked the same way.
# Speeding up only one would turn every startup into a race between a fast
# lever and a slow shim. What it deliberately does NOT touch:
#
#   the automatic controller  its 8-72 steps/min is a real design parameter,
#                             and scaling that would break the modelled
#                             behaviour rather than just hurry it along.
#   rod drop                  2.2 s already - gravity was never the slow part.
FAST_WITHDRAW_MULTIPLIER = 20.0

# Gravity, once the trip breakers open. The real number is a limit on time to
# dashpot entry rather than a fall rate, which is close enough at this fidelity.
ROD_DROP_SECONDS = 2.2

# Rated core thermal power (misc/Phoenix_Nuclear_Power_Plant_Documentation.md).
RATED_THERMAL_MWT = 3612.0

# ------------------------------------------------------------------ the banks

SHUTDOWN_BANKS = ["SA", "SB", "SC", "SD"]
CONTROL_BANKS = ["CA", "CB", "CC", "CD"]
BANKS = SHUTDOWN_BANKS + CONTROL_BANKS

BANK_NAMES = {
    "SA": "Shutdown Bank A", "SB": "Shutdown Bank B",
    "SC": "Shutdown Bank C", "SD": "Shutdown Bank D",
    "CA": "Control Bank A", "CB": "Control Bank B",
    "CC": "Control Bank C", "CD": "Control Bank D",
}

# Worth of each bank, pcm, fully inserted at hot zero power. Approximate: the
# shape is what matters here - the shutdown banks carry most of it and hold the
# shutdown margin, and worth rises through the control banks towards D, which is
# the one that sits in the core at power. Replaceable with COLR numbers once a
# reference plant is picked (see misc/systems/_manifest.json).
BANK_WORTH_PCM = {
    "SA": 1100.0, "SB": 1100.0, "SC": 1100.0, "SD": 1100.0,
    "CA": 350.0, "CB": 450.0, "CC": 700.0, "CD": 850.0,
}

TOTAL_ROD_WORTH_PCM = sum(BANK_WORTH_PCM.values())     # 6750 pcm

# One position meter per bank, 0-228 steps, on the Rod Section beside the
# selector. The panel engraves the control banks A-D and the shutdown banks
# SA-SD, so the meters and their definition assets read that way rather than
# using the CA-CD shorthand these tables key on.
#
# This is a stand-in for two instruments a real plant has and the client has no
# controller for: the group demand STEP COUNTERS (digital readouts) and DRPI
# (individual rod position, off the CRDM coil stack). An analog bank position
# meter is a real thing to have on the board, but it is not the whole picture.
BANK_GAUGES = {
    "SA": "d5e5e3d3-32db-441c-808d-8cc3d9255b0d",
    "SB": "214974d1-54cd-4ab0-ad00-6333924adfae",
    "SC": "f3f13f45-e7d4-4329-84bd-0492b95d3edd",
    "SD": "8bb25c98-b39f-40a0-8bcd-ece36160215e",
    "CA": "f150eb78-4511-44bf-8247-a8a5742f62a0",
    "CB": "6c9e5419-38f9-42a1-abcd-685288ce1f22",
    "CC": "54b74a88-5e3b-4f3d-931c-d2f704f89952",
    "CD": "87d21520-eb4e-4f55-a7f2-130407ff8986",
}

# What each meter's face and its definition asset are called: "SA Bank
# Position", "A Bank Position".
BANK_GAUGE_NAMES = {
    bank: f"{bank[1:] if bank.startswith('C') else bank} Bank Position"
    for bank in BANKS
}

# ------------------------------------------------------------------ the core

# Hot zero power to hot full power. Doppler plus the moderator, ~1.6 % dk/k.
POWER_DEFECT_PCM = 1600.0

# What all rods out at the nominal boron concentration asks for. Deliberately
# MORE than rated: a core with every rod out and nothing else holding it down
# is not sitting politely on 100 %, and boron is what brings it back - which is
# the whole reason chemical shim exists.
#
# Note what this means with the trip where it is: 122 % is above the 118 %
# power range high flux setpoint, so pulling everything out at nominal boron
# TRIPS the reactor on the way up. Borate about 4.4 % above nominal and it
# settles on 100 % instead. Move this number if you would rather watch it sit
# at 122 % than watch it trip.
ARO_POWER_PCT = 122.0

# Everything the rods are holding down at nominal boron: burnup, and the boron
# itself. Derived from the two numbers above rather than given, so the ARO
# power point stays where it says however the power defect is retuned. With
# every bank in, this still leaves 4800 pcm of shutdown margin.
CORE_EXCESS_PCM = POWER_DEFECT_PCM * ARO_POWER_PCT / 100.0

BETA_EFF = 0.0065           # delayed neutron fraction
LAMBDA_EFF = 0.1            # 1/s, one-group effective precursor decay constant
PROMPT_LIFETIME = 1.0e-4    # s, mean generation time

# Decades per minute per e-fold per second: 60 / ln(10).
DECADES_PER_MINUTE = 26.0577

# The floor on negative startup rate. Once prompt neutrons are gone, power can
# only fall as fast as the longest-lived precursor decays - about 80 s, which is
# -1/3 DPM. A one-group period doesn't know that, so it is imposed.
SUR_MIN_DPM = -1.0 / 3.0

# The ceiling is not physics: above prompt critical the one-group period means
# nothing, and a reactor there has been on its protection for a while. It only
# stops the exponent running away between ticks.
SUR_MAX_DPM = 5.0

# Source neutrons, as a fraction of rated. Nothing else is holding power up down
# here - subcritical multiplication is not modelled, the floor stands in for it.
POWER_FLOOR_PCT = 1.0e-8
POWER_CEILING_PCT = 200.0   # numeric guard; the trip is far below it

# The ends of the period dial, which is linear in seconds with 0 at the centre.
# Note what that means to read: period runs to infinity as the reactor settles,
# so a STEADY reactor pegs the needle at an end and comes off it as reactivity
# appears - the same way the RCP ammeter is read off its stop. The catch is that
# both ends mean the same thing, so the needle crosses the whole dial when the
# sign flips. A real period meter avoids that by putting infinity at the CENTRE
# and labelling a reciprocal scale (+/-10, +/-30, +/-100, inf); if the face is
# ever re-baked that way, publish DECADES_PER_MINUTE / period instead of this.
PERIOD_MAX_SECONDS = 180.0

# ------------------------------------------------------------------ setpoints

# Power range neutron flux, high setting: the trip.
HIGH_FLUX_TRIP_PCT = 118.0

# C-2: power range flux high blocks rod withdrawal, manual and automatic.
ROD_STOP_PCT = 103.0

# C-5: no AUTOMATIC withdrawal below this much turbine load. The automatic
# controller has nothing sensible to hold down there; the operator's lever is
# unaffected, which is how the plant is taken up to load in the first place.
AUTO_BLOCK_LOAD_PCT = 15.0

# The automatic controller's deadband and speed program. Stands in for the real
# thing's +/-1.5 degF of Tavg error: inside the band it holds, outside it the
# speed is proportional to the error and clamped to the speed program's ends.
AUTO_DEADBAND_PCT = 1.0
AUTO_STEPS_PER_MIN_PER_PCT = 14.4    # 5 % of error asks for full speed

# --------------------------------------------------------------------- boron

# TEMPORARY, like everything else here, and the smallest thing that gives the
# CVCS switch a job. Real chemical shim is a boron concentration in ppm moved by
# borating and diluting through the charging path, worth about -10 pcm/ppm; when
# CVCS lands as its own system it takes all of this with it.
#
# The meter reads a PERCENTAGE of the range this models rather than ppm, and
# only the DEVIATION from nominal carries reactivity - nominal boron is already
# inside CORE_EXCESS_PCM, which is what makes that number mean "all rods out at
# the normal concentration".
BORON_NOMINAL_PCT = 50.0
BORON_WORTH_PCM_PER_PCT = 80.0

# Deliberately compressed, the same way FAST_WITHDRAW is: real boration moves a
# concentration over tens of minutes. At this rate the switch is worth 8 pcm/s,
# about the same authority as the rod lever, which is what makes it usable -
# and FAST_WITHDRAW multiplies the two of them together, so that stays true.
CVCS_RATE_PCT_PER_SEC = 0.1

# ------------------------------------------------------------------- switches

# RotNp reports geometry, not meaning - "p1".."p10" - so what each detent
# selects lives here. The dial is laid out the way the real switch is: the four
# shutdown banks at one end, the four control banks at the other, and MAN and
# AUTO in the middle - which is where the switch stands for the whole run, with
# the startup banks behind it and the at-power banks ahead of it.
MANUAL = "manual"
AUTOMATIC = "automatic"

SELECTOR_POSITIONS = [f"p{index}" for index in range(1, 11)]
SELECTIONS = {
    "p1": "SA", "p2": "SB", "p3": "SC", "p4": "SD",
    "p5": MANUAL,
    "p6": AUTOMATIC,
    "p7": "CA", "p8": "CB", "p9": "CC", "p10": "CD",
}

# What the detent reads as, engraved on the panel and printed on the console.
SELECTOR_LABELS = dict(SELECTIONS, p5="MAN", p6="AUTO")

# The detent the switch is left in with the plant shut down and every rod on the
# bottom: shutdown bank A, the first thing withdrawn on the way up, and the far
# end of the dial. Has to agree with Default Position on the RotNp in the scene,
# which the client reports over this on its first sync.
DEFAULT_SELECTOR = "p1"

# Rot3pSpring, same wire format as Rot3p. Left drives the rods in and right
# drives them out, matching the valve switches - left shuts, right opens.
LEVER_IN = "left"
LEVER_HOLD = "center"
LEVER_OUT = "right"

LEVER_LABELS = {LEVER_IN: "IN", LEVER_HOLD: "HOLD", LEVER_OUT: "OUT"}
LEVER_DIRECTION = {LEVER_IN: -1, LEVER_HOLD: 0, LEVER_OUT: 1}

# Rot2p, so "off"/"on". Its lamp pair follows the switch on the client without
# the server saying anything, which is why no indicator is defined for it.
FAST_WITHDRAW_ON = "on"
FAST_WITHDRAW_POSITIONS = ["off", FAST_WITHDRAW_ON]

# The boric acid control, a Rot3pSpring on the same wire format as the rod
# lever. Right borates and left dilutes, so right raises the reading - the same
# way right opens a valve and right withdraws a rod.
CVCS_DILUTE = "left"
CVCS_HOLD = "center"
CVCS_BORATE = "right"

CVCS_LABELS = {CVCS_DILUTE: "DILUTE", CVCS_HOLD: "HOLD", CVCS_BORATE: "BORATE"}
CVCS_DIRECTION = {CVCS_DILUTE: -1.0, CVCS_HOLD: 0.0, CVCS_BORATE: 1.0}

# Trans2pSpring, so "released"/"pressed". Unlike the rod lever these are read as
# EDGES - a pushbutton is one command however long a thumb stays on it.
PRESSED = "pressed"
BUTTON_POSITIONS = ["released", PRESSED]

# Well under the lever's Minimum Hold Seconds in the scene (0.05 s), because the
# lever is sampled rather than latched: a hold shorter than one tick could fall
# between two of them and never be seen at all.
TICK_SECONDS = 0.02

# What /rods can be told to do.
COMPONENT_ACTIONS = {
    "trip": "trip the reactor - every bank to the bottom",
    "reset": "reset the trip, once flux is back below the setpoint",
}


def _clamp(value, low, high):
    return max(low, min(high, value))


def integral_worth(fraction):
    """Fraction of a bank's worth recovered by withdrawing it this far.

    The S-curve every rod worth curve is: differential worth is 1 - cos(2 pi x),
    zero at both ends where the flux is low and greatest at mid-core, and this
    is its integral. 0 fully inserted, 1 fully withdrawn.
    """
    x = _clamp(fraction, 0.0, 1.0)
    return x - math.sin(2.0 * math.pi * x) / (2.0 * math.pi)


def startup_rate(rho):
    """Decades per minute for a reactivity of `rho` (dk/k), one delayed group.

    The period is the prompt term plus the delayed one; the delayed term is what
    you feel for anything short of prompt critical, so +100 pcm is a 55 s period
    and about half a decade a minute.
    """
    if rho >= BETA_EFF:
        return SUR_MAX_DPM      # prompt critical; see SUR_MAX_DPM
    if rho == 0.0:
        return 0.0

    period = (PROMPT_LIFETIME / (BETA_EFF - rho)
              + (BETA_EFF - rho) / (LAMBDA_EFF * rho))
    return _clamp(DECADES_PER_MINUTE / period, SUR_MIN_DPM, SUR_MAX_DPM)


class RodCore:
    """Where every bank is, how much reactivity that leaves, and what power is.

    Module-level singleton (`core`), the same shape as RcpPlant: the sim thread
    ticks it, the console reads and writes it and the annunciator table reads
    it, so all three take the lock.
    """

    def __init__(self):
        self._lock = threading.RLock()

        # Steps withdrawn, per bank. Everything on the bottom - cold shutdown,
        # which is where a plant that has just been loaded starts.
        self.banks = {bank: 0 for bank in BANKS}

        self.power = POWER_FLOOR_PCT    # % of rated thermal
        self.sur = 0.0                  # decades per minute

        # Boron, as the meter reads it. Starts at nominal, which carries no
        # reactivity of its own - see BORON_NOMINAL_PCT.
        self.boron = BORON_NOMINAL_PCT

        # The reactor trip breakers, RTA and RTB. They sit in SERIES in the rod
        # drive supply, so either one open drops every rod - which is what
        # makes `tripped` a property over the pair rather than a flag.
        self.rps_closed = {train: True for train in RPS_TRAINS}

        # Pushbuttons are edges. What each was doing on the previous tick.
        self._last_button = {}

        # Whole steps owed. A magnetic jack moves in steps, not fractions, so
        # the rate is accumulated here and spent a step at a time.
        self._credit = 0.0
        # The command the credit belongs to: (selection, direction). A new one
        # gets its first step at once, because the first jack pulse isn't
        # delayed by the rate either.
        self._command = None

        self._drop_credit = 0.0
        self._last_selector = None
        self._last_fast_withdraw = None
        self._last_cvcs = None
        self._last_block = None
        self._was_moving = None

    # ----------------------------------------------------------------- reads

    @property
    def shutdown_banks_withdrawn(self):
        """All four shutdown banks fully out - the control bank permissive."""
        with self._lock:
            return all(self.banks[bank] >= STEPS_FULL_OUT for bank in SHUTDOWN_BANKS)

    @property
    def rod_worth_inserted(self):
        """pcm of worth still in the core, summed over every bank."""
        with self._lock:
            return sum(
                worth * (1.0 - integral_worth(self.banks[bank] / STEPS_FULL_OUT))
                for bank, worth in BANK_WORTH_PCM.items())

    @property
    def power_defect(self):
        """pcm the core is holding down because it is making power."""
        with self._lock:
            return POWER_DEFECT_PCM * self.power / 100.0

    @property
    def boron_worth(self):
        """pcm the boron is holding down, over and above nominal.

        Signed: above nominal it is positive and comes off the balance, below
        nominal it is negative and adds reactivity. Nominal itself is already
        inside CORE_EXCESS_PCM, so it contributes nothing here.
        """
        with self._lock:
            return BORON_WORTH_PCM_PER_PCT * (self.boron - BORON_NOMINAL_PCT)

    @property
    def tripped(self):
        """Either trip breaker open. They are in series - see rps_closed."""
        with self._lock:
            return not all(self.rps_closed.values())

    @property
    def reactivity(self):
        """Net pcm. Zero is critical, and it is what the period comes from."""
        with self._lock:
            return (CORE_EXCESS_PCM - self.rod_worth_inserted
                    - self.boron_worth - self.power_defect)

    @property
    def thermal_mwt(self):
        with self._lock:
            return RATED_THERMAL_MWT * self.power / 100.0

    @property
    def period(self):
        """Reactor period in seconds, clamped to the dial - see the constant.

        The inverse of the startup rate, so it runs away to infinity as the
        core settles and shortens as reactivity appears. Sign is the direction
        power is going. Exactly critical has no period at all; it reads at the
        positive end, which is the "nothing is happening" end.
        """
        with self._lock:
            if self.sur == 0.0:
                return PERIOD_MAX_SECONDS
            return _clamp(DECADES_PER_MINUTE / self.sur,
                          -PERIOD_MAX_SECONDS, PERIOD_MAX_SECONDS)

    def detent(self):
        """The detent the bank selector is in, as the client reports it."""
        entry = state.get_switch(SELECTOR)
        return entry["position"] if entry else DEFAULT_SELECTOR

    def selection(self):
        """What the bank selector is on: MANUAL, AUTOMATIC or a bank id."""
        return SELECTIONS.get(self.detent(), MANUAL)

    def lever(self):
        entry = state.get_switch(LEVER)
        if entry is None or not entry["powered"]:
            return LEVER_HOLD
        return entry["position"] if entry["position"] in LEVER_DIRECTION else LEVER_HOLD

    def fast_withdraw(self):
        """Is the test switch in? Multiplies the lever AND the boric acid
        control - see FAST_WITHDRAW_MULTIPLIER."""
        entry = state.get_switch(FAST_WITHDRAW)
        return (entry is not None
                and entry["position"] == FAST_WITHDRAW_ON
                and entry["powered"])

    def cvcs(self):
        """BORATE / HOLD / DILUTE, read as a level like the rod lever."""
        entry = state.get_switch(CVCS_SWITCH)
        if entry is None or not entry["powered"]:
            return CVCS_HOLD
        return entry["position"] if entry["position"] in CVCS_DIRECTION else CVCS_HOLD

    def _button_pressed(self, uid):
        entry = state.get_switch(uid)
        return (entry is not None and entry["position"] == PRESSED
                and entry["powered"])

    def _button_edge(self, uid):
        """True on the tick a button goes down, and only then."""
        down = self._button_pressed(uid)
        was, self._last_button[uid] = self._last_button.get(uid, False), down
        return down and not was

    def load_demand_pct(self):
        """Turbine load as a percentage of the machine's rating.

        The automatic controller's setpoint, standing in for the Tavg program -
        see the module docstring. Off the grid this is 0, which is why C-5 keeps
        automatic withdrawal out of it.
        """
        entry = state.get_gauge(GEN_LOAD)
        load = entry["value"] if entry else 0.0
        return 100.0 * load / RATED_LOAD_MW

    # ------------------------------------------------------------ the console

    def component(self, action):
        """Run a /rods action. Returns a line to print."""
        action = str(action).strip().lower()
        if action not in COMPONENT_ACTIONS:
            raise ValueError(
                f"unknown action '{action}' "
                f"({', '.join(sorted(COMPONENT_ACTIONS))})")

        return self._reset() if action == "reset" else self.trip("operator trip")

    def trip(self, cause):
        """Open both trip breakers. What the console and protection both use."""
        with self._lock:
            if self.tripped:
                return "the reactor is already tripped"
            for train in RPS_TRAINS:
                self.open_breaker(train, cause, announce=False)

        print(f"[rod] REACTOR TRIP - {cause}")
        return f"reactor tripped - {cause}; every bank to the bottom"

    def open_breaker(self, train, cause, announce=True):
        """Open one trip breaker. Either one on its own drops the rods."""
        with self._lock:
            if not self.rps_closed[train]:
                return f"RPS {train} is already tripped"

            self.rps_closed[train] = False
            self._drop_credit = 0.0
            self._credit = 0.0
            self._command = None

        if announce:
            print(f"[rod] RPS {train} TRIPPED - {cause}")
        return f"RPS {train} tripped - {cause}; every bank to the bottom"

    def close_breaker(self, train):
        """Reset one trip breaker, unless the flux that opened it is still up."""
        with self._lock:
            if self.rps_closed[train]:
                return f"RPS {train} is not tripped"

            # Sealed in while the condition that raised it is still standing,
            # the same rule the RCP lockouts follow.
            if self.power >= HIGH_FLUX_TRIP_PCT:
                print(f"[rod] RPS {train} reset REFUSED - flux still above the setpoint")
                return (f"RPS {train} will not reset - power is {self.power:.0f} %, "
                        f"still at or above the {HIGH_FLUX_TRIP_PCT:.0f} % setpoint")

            self.rps_closed[train] = True
            still_open = [t for t in RPS_TRAINS if not self.rps_closed[t]]

        print(f"[rod] RPS {train} reset")
        if still_open:
            return (f"RPS {train} reset - RPS {', '.join(still_open)} is still "
                    "tripped, and the breakers are in series")
        return f"RPS {train} reset - the banks will withdraw again"

    def _reset(self):
        with self._lock:
            if not self.tripped:
                return "the reactor is not tripped"
            open_trains = [t for t in RPS_TRAINS if not self.rps_closed[t]]

        replies = [self.close_breaker(train) for train in open_trains]
        return "\n".join(replies)

    def status_lines(self):
        """A console-readable dump; almost none of this is on the panel yet."""
        with self._lock:
            detent = self.detent()
            lines = [
                "  selector  {:<4} ({:<3})    lever  {:<4}    fast withdraw  {}".format(
                    SELECTOR_LABELS.get(detent, "?"), detent,
                    LEVER_LABELS.get(self.lever(), "?"),
                    "IN ({:.0f}x)".format(FAST_WITHDRAW_MULTIPLIER)
                    if self.fast_withdraw() else "out"),
                "",
                "  bank     " + " ".join(f"{bank:>5}" for bank in BANKS),
                "  steps    " + " ".join(f"{self.banks[bank]:>5}" for bank in BANKS),
                "  worth    " + " ".join(f"{BANK_WORTH_PCM[bank]:>5.0f}" for bank in BANKS),
                "",
                "  core excess      {:>+8.0f} pcm   (all rods out at "
                "{:.0f} % boron asks for {:.0f} % power)".format(
                    CORE_EXCESS_PCM, BORON_NOMINAL_PCT, ARO_POWER_PCT),
                "  rods inserted    {:>+8.0f} pcm".format(-self.rod_worth_inserted),
                "  boron            {:>+8.0f} pcm   ({:.1f} %, nominal "
                "{:.0f} %, {} at {:.2f} %/s)".format(
                    -self.boron_worth, self.boron, BORON_NOMINAL_PCT,
                    CVCS_LABELS.get(self.cvcs(), "?"),
                    CVCS_RATE_PCT_PER_SEC * (FAST_WITHDRAW_MULTIPLIER
                                             if self.fast_withdraw() else 1.0)),
                "  power defect     {:>+8.0f} pcm".format(-self.power_defect),
                "  net reactivity   {:>+8.0f} pcm".format(self.reactivity),
                "",
                "  startup rate     {:>+8.2f} dpm".format(self.sur),
                "  period           {:>+8.0f} s{}".format(
                    self.period,
                    "  (off scale - nothing much is happening)"
                    if abs(self.period) >= PERIOD_MAX_SECONDS else ""),
                "  reactor power    {:>8.3f} %   ({:.0f} MWt)".format(
                    self.power, self.thermal_mwt),
                "",
                "  RPS      " + "   ".join(
                    "{}: {}".format(train, "closed" if closed else "TRIPPED")
                    for train, closed in sorted(self.rps_closed.items())),
                "  reactor {}".format("TRIPPED" if self.tripped else "not tripped"),
            ]

            block = self.withdrawal_blocked()
            lines.append("  rod stop: " + (block or "none"))
            if not self.shutdown_banks_withdrawn:
                lines.append("  shutdown banks are NOT fully withdrawn - "
                             "the control banks will not come out")
            return lines

    # ------------------------------------------------------------------ tick

    def step(self, dt):
        """Advance the core one tick. Called by RodSimulation."""
        with self._lock:
            self._log_selector()
            self._log_fast_withdraw()
            self._step_rps()
            self._step_boron(dt)

            if self.tripped:
                self._step_drop(dt)
            else:
                self._step_jack(dt)

            self._step_power(dt)
            self._step_protection()

    def _step_drop(self, dt):
        """Free fall. Every bank to the bottom, together, and then nothing."""
        self._drop_credit += dt * STEPS_FULL_OUT / ROD_DROP_SECONDS
        steps = int(self._drop_credit)
        if steps <= 0:
            return

        self._drop_credit -= steps
        for bank in BANKS:
            self.banks[bank] = max(0, self.banks[bank] - steps)

    def _step_jack(self, dt):
        """Rod motion the operator or the automatic controller asked for."""
        selection = self.selection()

        if selection == AUTOMATIC:
            # The lever is bypassed in AUTO - the controller has the jacks, and
            # its speed program is left alone by FAST WITHDRAW.
            direction, rate = self._auto_program()
        else:
            direction = LEVER_DIRECTION[self.lever()]
            rate = MANUAL_STEPS_PER_MIN
            if self.fast_withdraw():
                rate *= FAST_WITHDRAW_MULTIPLIER

        if direction == 0:
            self._credit = 0.0
            self._command = None
            self._note_motion(0, selection)
            return

        # Decided once a tick, before any credit is spent, so a standing block
        # reads as a block for as long as it stands rather than flickering
        # between refused and moving every time a step comes due.
        moving = self._banks_for(selection, direction)
        blocked = self._motion_block(selection, moving, direction)
        if blocked is not None:
            self._credit = 0.0
            # Cleared, so the first step after the block lifts is immediate -
            # the same rule as a fresh command below.
            self._command = None
            self._note_block(blocked)
            self._note_motion(0, selection)
            return

        self._note_block(None)

        # A command the last tick didn't have gets its step now: a jack pulse is
        # a whole step whenever it comes, so the briefest bump of the lever
        # moves the bank once rather than nothing at all.
        command = (selection, direction)
        if command != self._command:
            self._command = command
            self._credit = 1.0

        self._credit += rate * dt / 60.0

        while self._credit >= 1.0:
            self._credit -= 1.0
            for bank in moving:
                self.banks[bank] = _clamp(self.banks[bank] + direction,
                                          0, STEPS_FULL_OUT)

            # The overlap can hand the sequence to another bank mid-tick, and a
            # bank can reach its stop, so ask again rather than reusing the set.
            moving = self._banks_for(selection, direction)
            if not moving:
                self._credit = 0.0
                break

        self._note_motion(direction, selection)

    def _auto_program(self):
        """(direction, steps per minute) the automatic rod controller asks for.

        Proportional to how far reactor power is from the turbine's load, with
        the speed clamped to the ends of the speed program. Standing in for the
        Tavg program - see the module docstring.
        """
        error = self.load_demand_pct() - self.power

        if abs(error) <= AUTO_DEADBAND_PCT:
            return 0, 0.0

        rate = _clamp(abs(error) * AUTO_STEPS_PER_MIN_PER_PCT,
                      AUTO_MIN_STEPS_PER_MIN, AUTO_MAX_STEPS_PER_MIN)
        return (1 if error > 0 else -1), rate

    def _banks_for(self, selection, direction):
        """The banks a jack pulse would actually move, given the selector.

        One named bank moves alone; MAN and AUTO hand the choice to the overlap
        sequence. Either way a bank already against its stop is dropped, so an
        empty list means there is nothing left to move.
        """
        if selection in BANK_WORTH_PCM:
            banks = [selection]
        else:
            banks = self._sequence_banks(direction)

        stop = STEPS_FULL_OUT if direction > 0 else 0
        return [bank for bank in banks if self.banks[bank] != stop]

    def _motion_block(self, selection, moving, direction):
        """Why this tick's rod motion won't happen, or None if it will."""
        if not moving:
            if selection in BANK_WORTH_PCM:
                return (f"{BANK_NAMES[selection]} is already "
                        + ("fully withdrawn" if direction > 0 else "on the bottom"))
            return ("every control bank is already out" if direction > 0
                    else "every control bank is already in")

        if direction > 0:
            return self._withdrawal_block(moving, selection == AUTOMATIC)

        # Nothing blocks insertion. Rods going in is the safe direction, and the
        # interlocks that exist are all rod STOPS.
        return None

    def _sequence_banks(self, direction):
        """Which control banks step together, per the overlap program.

        Read off the bank positions rather than a group counter, so a bank moved
        out of sequence on its own detent doesn't leave the sequencer confused
        about where it is: withdrawing always picks up the lowest bank that
        isn't out yet, and inserting the highest that isn't in.
        """
        if direction > 0:
            for index, bank in enumerate(CONTROL_BANKS):
                if self.banks[bank] >= STEPS_FULL_OUT:
                    continue
                moving = [bank]
                # Far enough out for the next bank to have started with it.
                if (self.banks[bank] >= CONTROL_BANK_OVERLAP
                        and index + 1 < len(CONTROL_BANKS)):
                    moving.append(CONTROL_BANKS[index + 1])
                return moving
            return []

        for index in range(len(CONTROL_BANKS) - 1, -1, -1):
            bank = CONTROL_BANKS[index]
            if self.banks[bank] <= 0:
                continue
            moving = [bank]
            # The mirror of the withdrawal overlap: the two banks that came out
            # together go back in together.
            if (self.banks[bank] <= STEPS_FULL_OUT - CONTROL_BANK_OVERLAP
                    and index > 0):
                moving.append(CONTROL_BANKS[index - 1])
            return moving
        return []

    def withdrawal_blocked(self):
        """Why rod withdrawal is blocked right now, or None if it isn't.

        Read against whatever the selector is on rather than against a
        particular pulse, because that is what a ROD STOP is: the interlock is
        either standing or it isn't, whether or not there is anything left to
        withdraw.
        """
        with self._lock:
            selection = self.selection()
            moving = [selection] if selection in BANK_WORTH_PCM else CONTROL_BANKS
            return self._withdrawal_block(moving, selection == AUTOMATIC)

    def _withdrawal_block(self, moving, automatic):
        """Why these banks will not withdraw, or None if they will.

        The reasons carry no live readings in them on purpose: the console logs
        one line per distinct reason, and a percentage inside the text would
        make every tick a new reason and every tick a new line. What the numbers
        actually are is on the gauge and under /rods.
        """
        if self.tripped:
            return "the reactor is tripped"

        if self.power >= ROD_STOP_PCT:
            return (f"C-2 rod stop - power range flux at or above "
                    f"{ROD_STOP_PCT:.0f} % of rated")

        if automatic and self.load_demand_pct() < AUTO_BLOCK_LOAD_PCT:
            return (f"C-5 rod stop - turbine load below {AUTO_BLOCK_LOAD_PCT:.0f} %, "
                    "which is as low as automatic withdrawal goes")

        if (any(bank in CONTROL_BANKS for bank in moving)
                and not self.shutdown_banks_withdrawn):
            return "shutdown banks not fully withdrawn"

        return None

    def _step_power(self, dt):
        """Period, then power. The whole neutronics of the thing."""
        self.sur = startup_rate(self.reactivity / 1.0e5)
        self.power = _clamp(self.power * 10.0 ** (self.sur * dt / 60.0),
                            POWER_FLOOR_PCT, POWER_CEILING_PCT)

    def _step_protection(self):
        if not self.tripped and self.power >= HIGH_FLUX_TRIP_PCT:
            self.trip(f"power range neutron flux high ({self.power:.0f} % of rated)")

    def _step_rps(self):
        """The four pushbuttons, on the tick each one goes down.

        One button per train, which is not quite the real arrangement: a
        Westinghouse manual trip is two pushbuttons either of which
        de-energizes BOTH trains. Per-train is what the four buttons on this
        panel are for, and the series breakers make the result the same - a
        single press still drops every rod.
        """
        for train in RPS_TRAINS:
            if self._button_edge(RPS_TRIP[train]):
                self.open_breaker(train, f"manual trip, train {train}")
            if self._button_edge(RPS_RESET[train]):
                self.close_breaker(train)

    def _step_boron(self, dt):
        """Borate or dilute for as long as the switch is held."""
        position = self.cvcs()
        self._log_cvcs(position)

        direction = CVCS_DIRECTION[position]
        if direction == 0.0:
            return

        rate = CVCS_RATE_PCT_PER_SEC
        if self.fast_withdraw():
            rate *= FAST_WITHDRAW_MULTIPLIER

        self.boron = _clamp(self.boron + direction * rate * dt, 0.0, 100.0)

    # ------------------------------------------------------------------- logs

    def _log_selector(self):
        detent = self.detent()
        if detent == self._last_selector:
            return

        self._last_selector = detent
        print(f"[rod] bank selector -> {SELECTOR_LABELS.get(detent, detent)}")

    def _log_fast_withdraw(self):
        """Loudly, because it is a test switch and not a plant control."""
        fast = self.fast_withdraw()
        if fast == self._last_fast_withdraw:
            return

        self._last_fast_withdraw = fast
        if fast:
            print(f"[rod] FAST WITHDRAW IN - the lever and the boric acid "
                  f"control both run {FAST_WITHDRAW_MULTIPLIER:.0f}x, which no "
                  f"plant does")
        else:
            print(f"[rod] fast withdraw out - back to "
                  f"{MANUAL_STEPS_PER_MIN:.0f} steps/min and "
                  f"{CVCS_RATE_PCT_PER_SEC:.2f} % boric acid a second")

    def _log_cvcs(self, position):
        if position == self._last_cvcs:
            return

        self._last_cvcs = position
        if position == CVCS_HOLD:
            print(f"[rod] boric acid holding at {self.boron:.1f} %")
        else:
            print(f"[rod] {CVCS_LABELS[position].lower()} - boric acid "
                  f"{'rising' if position == CVCS_BORATE else 'falling'} from "
                  f"{self.boron:.1f} %")

    def _note_block(self, reason):
        """One line per distinct refusal, not one per tick."""
        if reason == self._last_block:
            return

        self._last_block = reason
        if reason:
            print(f"[rod] rod withdrawal refused - {reason}")

    def _note_motion(self, direction, selection):
        moving = (direction, selection if direction else None)
        if moving == self._was_moving:
            return

        self._was_moving = moving
        if direction == 0:
            print("[rod] rods holding")
            return

        what = {MANUAL: "control banks", AUTOMATIC: "control banks (auto)"}.get(
            selection, BANK_NAMES.get(selection, str(selection)))
        print(f"[rod] {what} {'withdrawing' if direction > 0 else 'inserting'}")


core = RodCore()


# ------------------------------------------------------------------- alarms

def alarm_conditions():
    """(window id, condition) rows for the annunciator table.

    Conditions, not windows: annunciator_sim.py owns the alarm/acknowledge/
    ringback sequence. None of these windows is on a rack in the scene yet,
    which is fine - the table skips the ids no rack registered.
    """
    return [
        ("RX_TRIP", lambda: core.tripped),
        ("PWR_RANGE_HI_FLUX", lambda: core.power >= ROD_STOP_PCT),
        ("ROD_STOP", lambda: core.withdrawal_blocked() is not None),
    ]


# --------------------------------------------------------------- the thread

class RodSimulation:
    def __init__(self, tick=TICK_SECONDS):
        # The module singleton rather than one of its own: commands.py writes to
        # it and alarm_conditions() reads it.
        self.core = core
        self.tick = tick

        self._stop = threading.Event()
        self._thread = None

    def ensure_definitions(self):
        """Create the two switches and the nine gauges if they're missing.

        The selector's ten detents are settled here rather than by
        auto-registration, because the server takes a switch's position list
        once: a client that registered it first with a different count would
        leave reports of the detents beyond that being dropped.
        """
        created = 0

        if state.get_switch(SELECTOR) is None:
            state.define_switch(
                SELECTOR, id="Rod Bank Selector", name="Rod Bank Selector",
                positions=list(SELECTOR_POSITIONS), position=DEFAULT_SELECTOR,
                save=False)
            created += 1

        if state.get_switch(LEVER) is None:
            state.define_switch(
                LEVER, id="Rod Control Lever", name="Rod Control Lever",
                positions=[LEVER_IN, LEVER_HOLD, LEVER_OUT],
                position=LEVER_HOLD, save=False)
            created += 1

        if state.get_switch(FAST_WITHDRAW) is None:
            state.define_switch(
                FAST_WITHDRAW, id="Fast Withdraw", name="Fast Withdraw",
                positions=list(FAST_WITHDRAW_POSITIONS), position="off",
                save=False)
            created += 1

        if state.get_switch(CVCS_SWITCH) is None:
            state.define_switch(
                CVCS_SWITCH, id="Boric Acid Control", name="Boric Acid Control",
                positions=[CVCS_DILUTE, CVCS_HOLD, CVCS_BORATE],
                position=CVCS_HOLD, save=False)
            created += 1

        for train in RPS_TRAINS:
            for uid, what in ((RPS_TRIP[train], RPS_BUTTON_NAMES["trip"]),
                              (RPS_RESET[train], RPS_BUTTON_NAMES["reset"])):
                if state.get_switch(uid) is not None:
                    continue
                name = f"RPS {train} {what}"
                state.define_switch(uid, id=name, name=name,
                                    positions=list(BUTTON_POSITIONS),
                                    position="released", save=False)
                created += 1

        created += self._ensure_gauge(RX_POWER, "APRM", "%", 120.0)
        created += self._ensure_gauge(BORIC_ACID, "Boric Acid", "%", 100.0,
                                      value=BORON_NOMINAL_PCT)
        created += self._ensure_gauge(PERIOD, "Period", "s",
                                      PERIOD_MAX_SECONDS,
                                      min_value=-PERIOD_MAX_SECONDS,
                                      value=PERIOD_MAX_SECONDS)
        for bank, uid in BANK_GAUGES.items():
            created += self._ensure_gauge(
                uid, BANK_GAUGE_NAMES[bank], "STEPS", float(STEPS_FULL_OUT),
                value=float(self.core.banks[bank]))

        if created:
            state.save()
            print(f"[rod] defined {created} rod control "
                  f"entr{'y' if created == 1 else 'ies'}")

    @staticmethod
    def _ensure_gauge(uid, name, units, max_value, min_value=0.0, value=0.0):
        """Create a gauge, or correct one whose scale has moved under it.

        Checked against the scale rather than just presence, the same way
        rcp_sim does: an entry left in data/io_definitions.json from an earlier
        range would silently clamp everything written to it - and the period
        dial in particular is the only one here that goes negative, so an old
        0-based entry would flatten half of it.
        """
        entry = state.get_gauge(uid)
        if (entry is not None and entry["minValue"] == min_value
                and entry["maxValue"] == max_value and entry["units"] == units):
            return 0

        state.define_gauge(uid, id=name, name=name, units=units,
                           min_value=min_value, max_value=max_value,
                           value=value, save=False)
        return 1

    def start(self):
        self.ensure_definitions()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="rod-sim")
        self._thread.start()

    def stop(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _run(self):
        last = time.monotonic()
        while not self._stop.wait(self.tick):
            now = time.monotonic()
            self.core.step(now - last)
            last = now
            self._publish()

    def _publish(self):
        """Reactor power, the period, and every bank on its position meter.

        set_gauge is a no-op when nothing moved, so writing all ten every tick
        costs a comparison each rather than a revision - and a bank that only
        steps once a second is nine tenths of a second of nothing.
        """
        state.set_gauge(RX_POWER, self.core.power)
        state.set_gauge(PERIOD, self.core.period)
        state.set_gauge(BORIC_ACID, self.core.boron)

        for bank, uid in BANK_GAUGES.items():
            state.set_gauge(uid, float(self.core.banks[bank]))
