// ServerConnection.cs
using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

// The session's link to a PNPP server. HomeScreen creates it and runs Join();
// it survives the scene change, so control-room scripts read Info/Template off
// ServerConnection.Instance instead of fetching anything themselves.
//
// A join is only successful once both the handshake (/api/info) and the
// control-room template (/api/template) have arrived — the control room has
// nothing to bind to without the template, so a half-connected state is
// treated as no connection at all.
public class ServerConnection : MonoBehaviour
{
    // Must match API_VERSION in server-python/api.py.
    public const int SupportedApiVersion = 1;

    private const int DefaultPort = 8000;
    private const int TimeoutSeconds = 5;

    // Mirror of GET /api/info. Same JsonUtility key-to-field rules as
    // ControlRoomTemplate.
    [Serializable]
    public class ServerInfo
    {
        public string server;
        public int apiVersion;
        public int templateVersion;
        public string plantName;
        public int unit;
        public string reactorType;
        public string scene;
        public int players;
        public int maxPlayers;
        public string host;
        public int port;
        public string[] endpoints;
    }

    public static ServerConnection Instance { get; private set; }

    public string BaseUrl { get; private set; }
    public ServerInfo Info { get; private set; }
    public ControlRoomTemplate Template { get; private set; }
    public bool IsConnected => Template != null;

    // Live switch/indicator/gauge sync; rides along on this object so it also
    // survives scene loads.
    public IoSync Io { get; private set; }

    public static ServerConnection GetOrCreate()
    {
        if (Instance == null)
            new GameObject(nameof(ServerConnection)).AddComponent<ServerConnection>();

        return Instance;
    }

    private void Awake()
    {
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);

        Io = GetComponent<IoSync>();
        if (Io == null)
            Io = gameObject.AddComponent<IoSync>();
    }

    // "localhost" / "localhost:8000" / "http://10.0.0.4:8000" -> "http://host:port"
    public static string NormalizeUrl(string address)
    {
        string url = (address ?? "").Trim().TrimEnd('/');
        if (url.Length == 0)
            return "";

        if (!url.Contains("://"))
            url = "http://" + url;

        // Fill in the default port when the host carries none of its own.
        string host = url.Substring(url.IndexOf("://", StringComparison.Ordinal) + 3);
        if (host.Length > 0 && !host.Contains(":") && !host.Contains("/"))
            url += ":" + DefaultPort;

        return url;
    }

    // Coroutine. onDone(success, message) — message is display-ready either way.
    public IEnumerator Join(string address, Action<bool, string> onDone)
    {
        Info = null;
        Template = null;
        BaseUrl = NormalizeUrl(address);

        if (BaseUrl.Length == 0)
        {
            onDone?.Invoke(false, "Enter a server address, e.g. localhost:8000.");
            yield break;
        }

        using (var request = UnityWebRequest.Get(BaseUrl + "/api/info"))
        {
            request.timeout = TimeoutSeconds;
            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                onDone?.Invoke(false, $"Could not reach {BaseUrl} — {request.error}.");
                yield break;
            }

            Info = ParseInfo(request.downloadHandler.text);
        }

        // Anything that answers on that port can return 200; a missing
        // apiVersion means it wasn't a PNPP server.
        if (Info == null || Info.apiVersion == 0)
        {
            onDone?.Invoke(false, $"{BaseUrl} answered, but it isn't a PNPP server.");
            yield break;
        }

        if (Info.apiVersion != SupportedApiVersion)
            Debug.LogWarning(
                $"[ServerConnection] Server speaks API v{Info.apiVersion}, this client expects " +
                $"v{SupportedApiVersion} — some data may not load.");

        using (var request = UnityWebRequest.Get(BaseUrl + "/api/template"))
        {
            request.timeout = TimeoutSeconds;
            yield return request.SendWebRequest();

            if (request.result != UnityWebRequest.Result.Success)
            {
                Info = null;
                onDone?.Invoke(false, $"Server reached, but the control-room template failed to load — {request.error}.");
                yield break;
            }

            Template = ControlRoomTemplate.Parse(request.downloadHandler.text, out string parseError);
            if (Template == null)
            {
                Info = null;
                onDone?.Invoke(false, parseError);
                yield break;
            }
        }

        // A fresh session starts from a full I/O sync, not from whatever
        // revision a previous connection left behind.
        Io?.RequestFullSync();

        Debug.Log($"[ServerConnection] Joined {Info.server} at {BaseUrl} — {Template.Summary()}.");
        onDone?.Invoke(true, $"Connected to {Info.plantName} — {Template.Summary()}.");
    }

    public void Disconnect()
    {
        BaseUrl = null;
        Info = null;
        Template = null;
        Io?.RequestFullSync();
    }

    // A non-PNPP server may well answer with HTML, which throws in FromJson.
    private static ServerInfo ParseInfo(string json)
    {
        try
        {
            return JsonUtility.FromJson<ServerInfo>(json);
        }
        catch (Exception)
        {
            return null;
        }
    }
}
