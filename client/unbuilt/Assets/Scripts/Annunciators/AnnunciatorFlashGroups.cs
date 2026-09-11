// AnnunciatorFlashGroups.cs
using System.Collections.Generic;
using UnityEngine;

// The shared clocks that keep an annunciator panel in step - the lamps and the
// horns both.
//
// A window flashes at one of two RATES, which is how a real panel says two
// different things with one lamp:
//
//     announce   the alarm is in and nobody has acknowledged it. Fast.
//     clear      the condition went away before anyone acknowledged it -
//                ringback. Slow, so it reads as "this is over, but you still
//                haven't looked at it" rather than as a new alarm.
//
// Each rate has TWO clocks: a flash clock the lamps blink on, and a blip clock
// the horns pulse on. They are separate because the eye and the ear want
// different rates - a lamp at 0.2 s reads as urgent, an ear at 0.2 s reads as
// a fire alarm - but both are shared per group, which is the point. Every rack
// in a group plays its own horn, from its own position on the wall, and they
// all blip on the same frame because they all read this clock rather than
// counting for themselves.
//
// Phases are computed from the clock, not accumulated: nothing can drift apart
// because nothing is counting. A clock resyncs (origin moves to now) when the
// first window joins its rate - a new alarm comes in bright and sounds at once,
// and anything already flashing is by definition not flashing at that moment.
// Windows join and leave through AddFlashing/RemoveFlashing, which
// AnnunciatorTile calls.
//
// A window is counted TWICE, because SILENCE separates the eye from the ear:
// every flashing window counts towards the lamps, and only a window that is
// not silenced counts towards the horns. So silencing a panel leaves it
// flashing exactly as it was with nothing audible, and the next alarm to come
// in - which arrives un-silenced - takes the audible count from zero and
// resyncs the blip clock, so the horn sounds at once. That is the whole of
// "silence quiets what is in now but not what comes next".
public static class AnnunciatorFlashGroups
{
    public const string DefaultGroup = "default";

    // The two rates. These names are what the server puts on the wire, so they
    // are the vocabulary of the whole flash system - see io_state.py.
    public const string AnnounceRate = "announce";
    public const string ClearRate = "clear";

    // Half a flash cycle: lit for this long, dark for this long. 0.2 s is
    // roughly 150 flashes a minute, which is what a fast alarm flash looks
    // like; 0.8 s is a slow, unhurried ringback.
    public const float DefaultAnnounceHalfPeriod = 0.2f;
    public const float DefaultClearHalfPeriod = 0.8f;

    // One whole blip interval for the horn: two blips a second while an alarm
    // is unacknowledged, one a second for ringback.
    public const float DefaultAnnounceBlipSeconds = 0.5f;
    public const float DefaultClearBlipSeconds = 1.0f;

    // Below these a "flash" is a flicker and a "blip" is a buzz, and the phase
    // would alias against the frame rate rather than pulse.
    private const float MinimumHalfPeriod = 0.03f;
    private const float MinimumBlipSeconds = 0.05f;

    // A group and rate has one clock per channel: the lamps' and the horns'.
    private const string FlashChannel = "flash";
    private const string BlipChannel = "blip";

    private class Clock
    {
        public string Group;
        public string Rate;

        // Half a cycle for a flash clock; one whole blip interval for a blip
        // clock. A clock only ever belongs to one channel, so one field does.
        public float Seconds;

        public float Origin;
        public int Flashing;

        // Flashing windows that are not silenced. Never above Flashing.
        public int Audible;
        public bool PeriodDeclared;
    }

    private static readonly Dictionary<string, Clock> _clocks = new Dictionary<string, Clock>();
    private static readonly HashSet<string> _groupNames = new HashSet<string>();

    // Statics survive a play-mode exit when domain reloading is off, and a
    // stale flashing count would stop the next run's first alarm resyncing.
    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.SubsystemRegistration)]
    private static void ResetStatics()
    {
        _clocks.Clear();
        _groupNames.Clear();
    }

    // Anything unrecognised is an announce: a window the server told to flash
    // without saying how should come in as an alarm, not as a ringback.
    public static string NormalizeRate(string rate)
    {
        if (string.IsNullOrWhiteSpace(rate))
            return AnnounceRate;

        return rate.Trim().ToLowerInvariant() == ClearRate ? ClearRate : AnnounceRate;
    }

    public static float DefaultHalfPeriodFor(string rate) =>
        NormalizeRate(rate) == ClearRate ? DefaultClearHalfPeriod : DefaultAnnounceHalfPeriod;

    public static float DefaultBlipSecondsFor(string rate) =>
        NormalizeRate(rate) == ClearRate ? DefaultClearBlipSeconds : DefaultAnnounceBlipSeconds;

    // ------------------------------------------------------------ flash clock

    // Called by each rack as it comes up, once per rate. The first rack in a
    // group sets that rate; a later one asking for a different one would pull
    // the group apart, so it's told rather than obeyed.
    public static void Declare(string name, string rate, float halfPeriod)
    {
        Declare(name, rate, FlashChannel, Mathf.Max(MinimumHalfPeriod, halfPeriod), "flash");
    }

    // Where the flash clock is in its cycle right now. Unscaled time: a paused
    // simulation doesn't freeze an alarm mid-blink.
    public static bool IsLit(string name, string rate)
    {
        Clock clock = Resolve(name, rate, FlashChannel);
        float period = Mathf.Max(MinimumHalfPeriod, clock.Seconds) * 2f;
        return Mathf.Repeat(Time.unscaledTime - clock.Origin, period) < period * 0.5f;
    }

    // Start the cycle over, lit.
    public static void Resync(string name, string rate)
    {
        Resolve(name, rate, FlashChannel).Origin = Time.unscaledTime;
    }

    public static float HalfPeriod(string name, string rate) =>
        Resolve(name, rate, FlashChannel).Seconds;

    // ------------------------------------------------------------- blip clock

    public static void DeclareBlip(string name, string rate, float blipSeconds)
    {
        Declare(name, rate, BlipChannel, Mathf.Max(MinimumBlipSeconds, blipSeconds), "blip");
    }

    // Which blip the group is on: a counter that steps once per interval. Every
    // horn in the group reads the same number on the same frame, so they sound
    // together however many racks there are and whenever each one was built.
    // A horn plays a blip when this changes under it.
    public static int BlipIndex(string name, string rate)
    {
        Clock clock = Resolve(name, rate, BlipChannel);
        float seconds = Mathf.Max(MinimumBlipSeconds, clock.Seconds);
        return Mathf.FloorToInt((Time.unscaledTime - clock.Origin) / seconds);
    }

    public static float BlipSeconds(string name, string rate) =>
        Resolve(name, rate, BlipChannel).Seconds;

    // ---------------------------------------------------------------- joining

    // A window joining its rate. `audible` is false for a silenced one: it
    // still flashes, and the horns no longer hear it.
    public static void AddFlashing(string name, string rate, bool audible = true)
    {
        Clock clock = Resolve(name, rate, FlashChannel);

        // Nothing was on this rate, so nothing is in phase to disturb: bring
        // the new window in on a fresh cycle.
        if (clock.Flashing == 0)
            clock.Origin = Time.unscaledTime;

        clock.Flashing++;

        if (!audible)
            return;

        // Same reasoning, one channel over. Resyncing the blip clock as the
        // audible count leaves zero is what makes the horn sound the instant an
        // alarm arrives rather than up to an interval later - and it is what
        // re-sounds a silenced panel the moment something new comes in.
        if (clock.Audible == 0)
            Resolve(name, rate, BlipChannel).Origin = Time.unscaledTime;

        clock.Audible++;
    }

    public static void RemoveFlashing(string name, string rate, bool audible = true)
    {
        Clock clock = Resolve(name, rate, FlashChannel);
        clock.Flashing = Mathf.Max(0, clock.Flashing - 1);

        if (audible)
            clock.Audible = Mathf.Max(0, clock.Audible - 1);
    }

    // Move one window between the audible and the silent count, leaving the
    // flash count alone. Silencing must not disturb the LAMPS: taking the
    // window out of its group and putting it back would let the flash count
    // touch zero on a panel with one window flashing, which resyncs the phase -
    // and the blink would visibly hitch on a press that is only about sound.
    public static void SetAudible(string name, string rate, bool audible)
    {
        Clock clock = Resolve(name, rate, FlashChannel);

        if (!audible)
        {
            clock.Audible = Mathf.Max(0, clock.Audible - 1);
            return;
        }

        // Coming back from silence is a new audible event like any other, so
        // the horn starts its blip cycle here rather than mid-interval.
        if (clock.Audible == 0)
            Resolve(name, rate, BlipChannel).Origin = Time.unscaledTime;

        clock.Audible = Mathf.Min(clock.Flashing, clock.Audible + 1);
    }

    public static int FlashingCount(string name, string rate) =>
        Resolve(name, rate, FlashChannel).Flashing;

    public static int AudibleCount(string name, string rate) =>
        Resolve(name, rate, FlashChannel).Audible;

    // Is anything flashing - on one clock, at one rate anywhere, or at all. The
    // horns ask these every frame, so none of them allocate: Dictionary's
    // enumerator is a struct and Resolve is a lookup.
    public static bool AnyFlashing(string name, string rate) =>
        Resolve(name, rate, FlashChannel).Flashing > 0;

    public static bool AnyFlashingRate(string rate)
    {
        string wanted = NormalizeRate(rate);

        foreach (KeyValuePair<string, Clock> pair in _clocks)
        {
            if (pair.Value.Flashing > 0 && pair.Value.Rate == wanted)
                return true;
        }

        return false;
    }

    public static bool AnyFlashing()
    {
        foreach (KeyValuePair<string, Clock> pair in _clocks)
        {
            if (pair.Value.Flashing > 0)
                return true;
        }

        return false;
    }

    // The same three questions the horns ask, of the audible count: a silenced
    // window is flashing but not sounding.
    public static bool AnyAudible(string name, string rate) =>
        Resolve(name, rate, FlashChannel).Audible > 0;

    public static bool AnyAudibleRate(string rate)
    {
        string wanted = NormalizeRate(rate);

        foreach (KeyValuePair<string, Clock> pair in _clocks)
        {
            if (pair.Value.Audible > 0 && pair.Value.Rate == wanted)
                return true;
        }

        return false;
    }

    public static bool AnyAudible()
    {
        foreach (KeyValuePair<string, Clock> pair in _clocks)
        {
            if (pair.Value.Audible > 0)
                return true;
        }

        return false;
    }

    public static IEnumerable<string> Names => _groupNames;

    // ----------------------------------------------------------------- shared

    private static void Declare(string name, string rate, string channel,
                                float seconds, string what)
    {
        Clock clock = Resolve(name, rate, channel);

        if (!clock.PeriodDeclared)
        {
            clock.Seconds = seconds;
            clock.PeriodDeclared = true;
            return;
        }

        if (!Mathf.Approximately(clock.Seconds, seconds))
            Debug.LogWarning(
                $"[AnnunciatorFlashGroups] group '{Key(name)}' already {what}es " +
                $"{NormalizeRate(rate)} at {clock.Seconds:0.###}s; keeping that rather " +
                $"than {seconds:0.###}s. Everything in one group shares a rate - that is " +
                "what keeps the panel in step - so give them the same setting, or put " +
                "this one in a group of its own.");
    }

    private static Clock Resolve(string name, string rate, string channel)
    {
        string group = Key(name);
        string normalized = NormalizeRate(rate);

        // A separator no group name can contain, so "RCS" + "announce" can
        // never collide with a group actually called "RCSannounce".
        string key = group + "\u0001" + normalized + "\u0001" + channel;

        if (!_clocks.TryGetValue(key, out Clock clock))
        {
            clock = new Clock
            {
                Group = group,
                Rate = normalized,
                Seconds = channel == BlipChannel
                    ? DefaultBlipSecondsFor(normalized)
                    : DefaultHalfPeriodFor(normalized),
                Origin = Time.unscaledTime,
            };
            _clocks[key] = clock;
            _groupNames.Add(group);
        }

        return clock;
    }

    private static string Key(string name) =>
        string.IsNullOrWhiteSpace(name) ? DefaultGroup : name.Trim();
}
