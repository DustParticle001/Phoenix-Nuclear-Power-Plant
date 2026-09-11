// IoSync.cs
using System.Collections;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;

// Keeps the scene and the server in step, on a timer:
//
//   up    every switch definition in the scene, with the position it is in
//   down  switches other players moved, indicator lamp states, gauge values,
//         annunciator windows
//
// One request does both (POST /api/io/report), so a tick is a single round trip.
// Everything is matched by definition UID - SwitchDefinition.Id for switches and
// indicators, GaugeDefinition.Id for gauges, the tile uid for annunciator
// windows - so nothing depends on names or hierarchy. Controls with no
// definition assigned are skipped.
//
// Annunciators are the one thing the client defines rather than the server:
// their uids live in the rack definitions here, so a window rides up with the
// report once, until the server has registered it, and after that only ever
// comes down.
//
// Lives on the ServerConnection object (created by the join screen, kept across
// scene loads), so nothing has to be wired up in a scene. After every scene load
// it re-scans and pulls the full state again.
[DisallowMultipleComponent]
public class IoSync : MonoBehaviour
{
    private const int TimeoutSeconds = 5;
    // TEMPORARY: 0.05f normally. It floors whatever interval the server asks
    // for, so it has to come down too for a faster rate to take effect. At this
    // value the floor is gone and the loop runs as often as frames allow.
    private const float MinInterval = 0.001f;
    private const int FailureLogEvery = 20;

    [Header("Timing")]
    [Tooltip("Seconds between exchanges, until the server states its own interval.")]
    [SerializeField] private float _interval = 0.2f;

    [Header("Debug")]
    [Tooltip("Log every applied change. Noisy - for tracking down sync problems.")]
    [SerializeField] private bool _verbose = false;

    // Identifies this client to the server, so its own changes aren't echoed
    // back to it. New each run; nothing persists it.
    public string ClientId { get; private set; }

    // Highest server revision applied so far; -1 until the first full sync.
    public int Revision { get; private set; } = -1;
    public bool HasSynced => Revision >= 0;

    public int SwitchCount => _switches.Count;
    public int GaugeCount => _gaugeCount;
    public int IndicatorCount => _indicators.Count;
    public int AnnunciatorCount => _annunciatorCount;

    private readonly Dictionary<string, ISwitchControl> _switches =
        new Dictionary<string, ISwitchControl>();
    // Several needles per UID: one signal can have more than one face. The
    // turbine tachometer is read on a 0-2000 dial and on an expanded 1795-1805
    // one for synchronising - same value, and each needle clips it to its own
    // definition's range. Switches can't work that way (two controls reporting
    // one UID would fight over it), so they stay one-to-one.
    private readonly Dictionary<string, List<GaugeNeedle>> _gauges =
        new Dictionary<string, List<GaugeNeedle>>();
    private readonly Dictionary<string, SwitchLampIndicator> _indicators =
        new Dictionary<string, SwitchLampIndicator>();
    // Windows, like gauges, are outputs, so several may answer to one uid - the
    // same alarm repeated on a second rack is a repeater, not a clash.
    private readonly Dictionary<string, List<AnnunciatorTile>> _annunciators =
        new Dictionary<string, List<AnnunciatorTile>>();

    private int _gaugeCount;
    private int _annunciatorCount;

    // Windows the server has no definition for. They go up with the report
    // until it registers them and then stop: a rack is dozens of windows and
    // the report goes out several times a second.
    private readonly HashSet<string> _unregisteredAnnunciators = new HashSet<string>();

    private readonly HashSet<string> _reportedUnknown = new HashSet<string>();
    private string _sessionId;
    private int _consecutiveFailures;
    private Coroutine _loop;

    private void Awake()
    {
        ClientId = System.Guid.NewGuid().ToString("N");
        SceneManager.sceneLoaded += OnSceneLoaded;
        RebuildRegistry();
    }

    private void OnDestroy()
    {
        SceneManager.sceneLoaded -= OnSceneLoaded;
    }

    private void OnEnable()
    {
        _loop = StartCoroutine(SyncLoop());
    }

    private void OnDisable()
    {
        if (_loop != null)
            StopCoroutine(_loop);

        _loop = null;
    }

    private void OnSceneLoaded(Scene scene, LoadSceneMode mode)
    {
        RebuildRegistry();

        // New controls start at their scene defaults, so pull the real state
        // instead of reporting the defaults over it.
        RequestFullSync();
    }

    // Forget where we were and pull everything again on the next tick.
    public void RequestFullSync()
    {
        Revision = -1;
    }

    // --------------------------------------------------------------- registry

    // Finds every control in the loaded scenes and indexes it by definition UID.
    // Called on scene load; call it again after spawning controls at runtime.
    public void RebuildRegistry()
    {
        _switches.Clear();
        _gauges.Clear();
        _gaugeCount = 0;
        _indicators.Clear();
        _annunciators.Clear();
        _annunciatorCount = 0;

        // FindObjectsByType can't search for an interface, so the switch scan
        // goes wide and filters. Once per scene load, not per tick.
        foreach (var behaviour in FindObjectsByType<MonoBehaviour>(FindObjectsInactive.Include))
        {
            if (behaviour is ISwitchControl control)
                Register(_switches, control.Id, control, "switch", behaviour);
        }

        foreach (var gauge in FindObjectsByType<GaugeNeedle>(FindObjectsInactive.Include))
            RegisterGauge(gauge);

        foreach (var indicator in FindObjectsByType<SwitchLampIndicator>(FindObjectsInactive.Include))
            Register(_indicators, indicator.Id, indicator, "indicator", indicator);

        foreach (var tile in FindObjectsByType<AnnunciatorTile>(FindObjectsInactive.Include))
            RegisterAnnunciator(tile);

        if (_verbose)
            Debug.Log($"[IoSync] {_switches.Count} switches, {_indicators.Count} indicators, " +
                      $"{_gaugeCount} gauge needles on {_gauges.Count} UIDs, " +
                      $"{_annunciatorCount} annunciator windows on {_annunciators.Count} UIDs bound.");
    }

    // Gauges are read-only on the client, so sharing a UID is a feature rather
    // than a clash: every needle bound to it gets the value.
    private void RegisterGauge(GaugeNeedle gauge)
    {
        string uid = gauge.Id;
        if (string.IsNullOrEmpty(uid) || uid == "unassigned")
            return;   // no definition assigned yet - nothing the server can key on

        if (!_gauges.TryGetValue(uid, out List<GaugeNeedle> needles))
        {
            needles = new List<GaugeNeedle>(1);
            _gauges[uid] = needles;
        }

        needles.Add(gauge);
        _gaugeCount++;
    }

    // Same reasoning as gauges: a window is an output, so two of them on one
    // uid both light rather than fighting over it.
    private void RegisterAnnunciator(AnnunciatorTile tile)
    {
        string uid = tile.Id;
        if (string.IsNullOrEmpty(uid) || uid == "unassigned")
            return;   // the rack builder never gave it a uid

        if (!_annunciators.TryGetValue(uid, out List<AnnunciatorTile> windows))
        {
            windows = new List<AnnunciatorTile>(1);
            _annunciators[uid] = windows;
        }

        windows.Add(tile);
        _annunciatorCount++;
    }

    private void Register<T>(Dictionary<string, T> into, string uid, T item,
        string kind, MonoBehaviour owner)
    {
        if (string.IsNullOrEmpty(uid) || uid == "unassigned")
            return;   // no definition assigned yet - nothing the server can key on

        if (into.TryGetValue(uid, out T existing))
        {
            Debug.LogWarning(
                $"[IoSync] two {kind}s share UID {uid} ('{owner.name}' and " +
                $"'{(existing as MonoBehaviour)?.name}'). Keeping the first; give one a " +
                "definition of its own.");
            return;
        }

        into[uid] = item;
    }

    // ------------------------------------------------------------------- loop

    private IEnumerator SyncLoop()
    {
        while (true)
        {
            var connection = ServerConnection.Instance;

            if (connection == null || !connection.IsConnected)
            {
                Revision = -1;
                yield return Wait();
                continue;
            }

            if (Revision < 0)
                yield return FullSync(connection.BaseUrl);
            else
                yield return Report(connection.BaseUrl);

            yield return Wait();
        }
    }

    // Realtime: the sync must keep running even if the sim pauses time.
    private WaitForSecondsRealtime Wait() =>
        new WaitForSecondsRealtime(Mathf.Max(MinInterval, _interval));

    private IEnumerator FullSync(string baseUrl)
    {
        string url = $"{baseUrl}/api/io?clientId={UnityWebRequest.EscapeURL(ClientId)}";

        using (var request = UnityWebRequest.Get(url))
        {
            request.timeout = TimeoutSeconds;
            yield return request.SendWebRequest();

            if (!Succeeded(request, "full sync"))
                yield break;

            // A full sync is authoritative, so take it whatever session it's from.
            IoSyncPayload payload = Parse(request.downloadHandler.text);
            if (payload == null)
                yield break;

            _sessionId = payload.sessionId;
            Apply(payload);
            Revision = payload.revision;

            MarkStaleAnnunciators(payload);

            Debug.Log($"[IoSync] synced with {baseUrl} at revision {Revision}: " +
                      $"{Count(payload.switches)} switches, {Count(payload.indicators)} indicators, " +
                      $"{Count(payload.gauges)} gauges, {Count(payload.annunciators)} annunciators " +
                      $"from the server; {_switches.Count}/{_indicators.Count}/{_gaugeCount}/" +
                      $"{_annunciatorCount} bound in the scene" +
                      (_unregisteredAnnunciators.Count > 0
                          ? $"; reporting {_unregisteredAnnunciators.Count} window(s) the " +
                            "server has no definition for or has grouped stale."
                          : "."));
        }
    }

    private IEnumerator Report(string baseUrl)
    {
        string body = JsonUtility.ToJson(BuildReport());

        using (var request = new UnityWebRequest($"{baseUrl}/api/io/report", "POST"))
        {
            request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            request.timeout = TimeoutSeconds;

            yield return request.SendWebRequest();

            if (!Succeeded(request, "report"))
                yield break;

            IoSyncPayload payload = Parse(request.downloadHandler.text);
            if (payload == null)
                yield break;

            // Server restarted or reloaded its definitions: revisions started
            // over, so this diff means nothing to us. Resync instead of applying.
            if (!string.IsNullOrEmpty(_sessionId) && payload.sessionId != _sessionId)
            {
                Debug.Log("[IoSync] server session changed - resyncing from scratch.");
                RequestFullSync();
                yield break;
            }

            Apply(payload);
            Revision = payload.revision;
            ReportDiagnostics(payload);
        }
    }

    private IoReportRequest BuildReport()
    {
        var switches = new List<IoSwitchReport>(_switches.Count);

        foreach (var pair in _switches)
        {
            ISwitchControl control = pair.Value;

            // Interface references don't get Unity's destroyed-object ==, so
            // check through the component.
            if (!(control is MonoBehaviour behaviour) || behaviour == null)
                continue;

            SwitchDefinition definition = control.Definition;

            switches.Add(new IoSwitchReport
            {
                uid = pair.Key,
                // id/name/positions only matter the first time the server sees
                // this uid (auto-registration), but they're cheap to keep sending
                // and they're what makes the JSON readable.
                id = definition != null ? definition.name : pair.Key,
                name = definition != null && !string.IsNullOrEmpty(definition.displayName)
                    ? definition.displayName
                    : behaviour.name,
                positions = control.Positions,
                position = control.Position,
            });
        }

        return new IoReportRequest
        {
            clientId = ClientId,
            since = Revision,
            switches = switches.ToArray(),
            annunciators = BuildAnnunciatorReports(),
        };
    }

    // The windows the server hasn't registered yet, with everything it needs to
    // write them into its I/O map: the legend it will show, the lens colour and
    // the flash group. Empty on every tick after the first.
    private IoAnnunciatorReport[] BuildAnnunciatorReports()
    {
        if (_unregisteredAnnunciators.Count == 0)
            return new IoAnnunciatorReport[0];

        var windows = new List<IoAnnunciatorReport>(_unregisteredAnnunciators.Count);

        foreach (string uid in _unregisteredAnnunciators)
        {
            if (!_annunciators.TryGetValue(uid, out List<AnnunciatorTile> tiles))
                continue;

            AnnunciatorTile tile = tiles.Count > 0 ? tiles[0] : null;
            if (tile == null)
                continue;

            string legend = tile.Legend ?? "";

            windows.Add(new IoAnnunciatorReport
            {
                uid = uid,
                id = !string.IsNullOrEmpty(tile.ReadableId) ? tile.ReadableId : uid,
                // One line, for the places a name is read rather than printed.
                name = legend.Replace("\r", " ").Replace("\n", " ").Trim(),
                text = legend,
                color = tile.ColorName,
                group = tile.FlashGroup,
                sartGroup = tile.SartGroup,
            });
        }

        return windows.ToArray();
    }

    // A full sync is the whole map, so a window missing from it is one the
    // server doesn't have. A window that IS in it but grouped wrongly counts
    // too: the grouping belongs to the rack definition here, and the copy the
    // server took when the window first registered goes stale the moment a rack
    // is renamed or moved to another SART panel. Either way the fix is the same
    // - ride up with the report until the server has taken it.
    private void MarkStaleAnnunciators(IoSyncPayload payload)
    {
        _unregisteredAnnunciators.Clear();

        foreach (string uid in _annunciators.Keys)
            _unregisteredAnnunciators.Add(uid);

        if (payload.annunciators == null)
            return;

        foreach (IoAnnunciatorEntry entry in payload.annunciators)
        {
            if (entry != null && ServerAgreesOn(entry))
                _unregisteredAnnunciators.Remove(entry.uid);
        }
    }

    // Does the server's copy still describe the window this rack actually
    // holds? Only the groupings are checked: they are what decides which panel
    // flashes it and which cluster commands it, so a stale one is a window that
    // visibly misbehaves. The legend and the lens are cosmetic by comparison
    // and go through the same path when they are next reported.
    private bool ServerAgreesOn(IoAnnunciatorEntry entry)
    {
        if (!_annunciators.TryGetValue(entry.uid, out List<AnnunciatorTile> windows)
                || windows.Count == 0 || windows[0] == null)
            return true;   // not in this scene, so nothing here disagrees with it

        AnnunciatorTile tile = windows[0];

        return SameGroup(entry.group, tile.FlashGroup)
            && SameGroup(entry.sartGroup, tile.SartGroup);
    }

    private static bool SameGroup(string a, string b) =>
        string.Equals(a ?? "", b ?? "", System.StringComparison.Ordinal);

    // ------------------------------------------------------------------ apply

    private void Apply(IoSyncPayload payload)
    {
        if (payload.reportIntervalSeconds > 0f)
            _interval = payload.reportIntervalSeconds;

        if (payload.switches != null)
            foreach (IoSwitchEntry entry in payload.switches)
                ApplySwitch(entry);

        if (payload.indicators != null)
            foreach (IoIndicatorEntry entry in payload.indicators)
                ApplyIndicator(entry);

        if (payload.gauges != null)
            foreach (IoGaugeEntry entry in payload.gauges)
                ApplyGauge(entry);

        if (payload.annunciators != null)
            foreach (IoAnnunciatorEntry entry in payload.annunciators)
                ApplyAnnunciator(entry);
    }

    private void ApplySwitch(IoSwitchEntry entry)
    {
        if (entry == null || !_switches.TryGetValue(entry.uid, out ISwitchControl control))
            return;

        if (!(control is MonoBehaviour behaviour) || behaviour == null)
            return;   // destroyed since the last scan

        // Only move it if it isn't already there: SetPosition animates and logs.
        if (string.Equals(control.Position, entry.position, System.StringComparison.OrdinalIgnoreCase))
            return;

        control.SetPosition(entry.position);

        if (_verbose)
            Debug.Log($"[IoSync] switch {entry.uid} → {entry.position} (from server).");
    }

    private void ApplyIndicator(IoIndicatorEntry entry)
    {
        if (entry == null || !_indicators.TryGetValue(entry.uid, out SwitchLampIndicator indicator)
            || indicator == null)
            return;

        indicator.SetServerState(entry.state, entry.flashing);

        if (_verbose)
            Debug.Log($"[IoSync] indicator {entry.uid} → {entry.state}" +
                      (entry.flashing ? " (flashing)" : "") + ".");
    }

    private void ApplyGauge(IoGaugeEntry entry)
    {
        if (entry == null || !_gauges.TryGetValue(entry.uid, out List<GaugeNeedle> needles))
            return;

        foreach (GaugeNeedle needle in needles)
        {
            if (needle != null)
                needle.SetValue(entry.value);
        }

        if (_verbose)
            Debug.Log($"[IoSync] gauge {entry.uid} → {entry.value} {entry.units} " +
                      $"on {needles.Count} needle{(needles.Count == 1 ? "" : "s")}.");
    }

    private void ApplyAnnunciator(IoAnnunciatorEntry entry)
    {
        if (entry == null || !_annunciators.TryGetValue(entry.uid, out List<AnnunciatorTile> windows))
            return;

        // The lens colour is the rack's, not the server's: it's a physical
        // window, and the server only knows what it was told. State and
        // flashing are all that come down.
        foreach (AnnunciatorTile window in windows)
        {
            if (window != null)
                window.SetServerState(entry.state, entry.flashing, entry.flashRate, entry.silenced);
        }

        if (_verbose)
            Debug.Log($"[IoSync] annunciator {entry.id} -> {entry.state}" +
                      (entry.flashing ? $" (flashing {entry.flashRate})" : "") +
                      (entry.silenced ? " (silenced)" : "") +
                      $" on {windows.Count} window{(windows.Count == 1 ? "" : "s")}.");
    }

    // ------------------------------------------------------------ diagnostics

    private void ReportDiagnostics(IoSyncPayload payload)
    {
        // Rejected means the server had a newer value than we were reporting
        // against; that value is in the same payload, so we've already corrected.
        if (_verbose && Count(payload.rejected) > 0)
            Debug.Log($"[IoSync] {Count(payload.rejected)} stale report(s) rejected: " +
                      string.Join(", ", payload.rejected));

        if (Count(payload.registered) > 0)
        {
            Debug.Log($"[IoSync] server registered {Count(payload.registered)} new " +
                      "definition(s) from this client.");

            // Registered windows are on the server now, so they stop riding up
            // with every report.
            foreach (string uid in payload.registered)
                _unregisteredAnnunciators.Remove(uid);
        }

        // Unknown uid: the server has no definition and isn't auto-registering.
        // Worth saying once per uid, then never again.
        if (payload.unknown == null)
            return;

        foreach (string uid in payload.unknown)
        {
            // Reporting it again won't help - the server has already refused it.
            _unregisteredAnnunciators.Remove(uid);

            if (string.IsNullOrEmpty(uid) || !_reportedUnknown.Add(uid))
                continue;

            Debug.LogWarning(
                $"[IoSync] the server has no definition for {uid} and is not " +
                "auto-registering. Add it to data/io_definitions.json.");
        }
    }

    private bool Succeeded(UnityWebRequest request, string what)
    {
        if (request.result == UnityWebRequest.Result.Success)
        {
            _consecutiveFailures = 0;
            return true;
        }

        _consecutiveFailures++;

        // Keep trying, but don't fill the console at two requests a second.
        if (_consecutiveFailures == 1 || _consecutiveFailures % FailureLogEvery == 0)
            Debug.LogWarning($"[IoSync] {what} failed ({request.error}); " +
                             $"{_consecutiveFailures} in a row.");

        return false;
    }

    private static IoSyncPayload Parse(string json)
    {
        try
        {
            return JsonUtility.FromJson<IoSyncPayload>(json);
        }
        catch (System.Exception exception)
        {
            Debug.LogWarning($"[IoSync] unreadable response: {exception.Message}");
            return null;
        }
    }

    private static int Count(System.Array array) => array?.Length ?? 0;
}
