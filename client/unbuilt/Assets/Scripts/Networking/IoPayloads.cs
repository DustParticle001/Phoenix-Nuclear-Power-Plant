// IoPayloads.cs
using System;

// Wire format for the live I/O sync (GET /api/io, POST /api/io/report). Field
// names match the JSON keys exactly - JsonUtility maps keys onto field names -
// so renaming one here changes the protocol.
//
// The server always sends whole entries, never partial ones, so applying an
// entry never needs to know which field changed.

[Serializable]
public class IoSwitchEntry
{
    public string uid;
    public string id;
    public string name;
    public string[] positions;
    public string position;
    public bool powered;
    public bool available;
    public int revision;
}

[Serializable]
public class IoIndicatorEntry
{
    public string uid;
    public string id;
    public string name;
    public string state;      // "red" / "green" / anything else = dark
    public bool flashing;
    public int revision;
}

[Serializable]
public class IoGaugeEntry
{
    public string uid;
    public string id;
    public string name;
    public string units;
    public float minValue;
    public float maxValue;
    public float value;
    public bool valid;
    public int revision;
}

// What the server sends back: everything this client hasn't seen yet.
[Serializable]
public class IoSyncPayload
{
    // Changes when the server restarts or reloads its definitions - the client
    // resyncs from scratch when it sees a new one, because revisions restart too.
    public string sessionId;
    public int revision;
    public float reportIntervalSeconds;

    public IoSwitchEntry[] switches;
    public IoIndicatorEntry[] indicators;
    public IoGaugeEntry[] gauges;

    // Report outcome (absent on a plain GET).
    public string[] accepted;
    public string[] rejected;    // stale - the current value is in switches
    public string[] unknown;     // uid the server has no definition for
    public string[] registered;  // uid the server just auto-registered
}

// One switch in a report: the uid, where it is, and enough to auto-register it.
[Serializable]
public class IoSwitchReport
{
    public string uid;
    public string id;
    public string name;
    public string[] positions;
    public string position;
}

[Serializable]
public class IoReportRequest
{
    public string clientId;
    public int since;
    public IoSwitchReport[] switches;
}
