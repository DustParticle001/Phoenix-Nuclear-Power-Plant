# Joining a server (home screen)

The game opens on `Assets/Scenes/HomeScene.unity` (build index 0). There is no
offline mode: `MainScene` only loads after a server has been joined, so the
control room always has a template to bind to.

## Flow

1. **HomeScene** — `HomeScreen` (on the `HomeScreen` object) builds the menu and
   waits. The cursor is unlocked here, and the player types a server address
   (`localhost:8000`, `10.0.0.4:8000`, or a full `http://host:port`). The last
   address that joined successfully is remembered in `PlayerPrefs`.
2. **Join** — `ServerConnection.Join` fetches `GET /api/info`, then
   `GET /api/template`. Both must succeed; a server that answers but sends no
   `apiVersion` is reported as "not a PNPP server", and a missing template fails
   the join rather than half-connecting.
3. **Load** — the scene named by the server (`info.scene`, normally `MainScene`)
   is loaded, falling back to `HomeScreen._controlRoomScene` if the server names
   a scene that isn't in Build Settings.
4. **In the control room** — `ServerConnection.Instance` survives the scene
   change. Read `Instance.Template` / `Instance.Info` from any script; the
   connection object is created at runtime and marked `DontDestroyOnLoad`.
   `Instance.Io` (`IoSync`) then keeps switches, lamps and gauges in step with the
   server on a timer — see `server-io-sync.md`.

Both scenes must stay in **Build Settings** (`HomeScene` first) — `HomeScreen`
checks and reports a missing scene instead of failing silently.

## Files

| File | Role |
| --- | --- |
| `Assets/Scripts/UI/HomeScreen.cs` | The menu. Builds its own canvas in code. |
| `Assets/Scripts/Networking/ServerConnection.cs` | Join handshake, session-long connection, `Instance` accessor. |
| `Assets/Scripts/Networking/ControlRoomTemplate.cs` | C# mirror of `GET /api/template`. |
| `Assets/Scripts/Networking/IoSync.cs` | Live switch/indicator/gauge sync (`server-io-sync.md`). |
| `Assets/Scenes/HomeScene.unity` | Camera, EventSystem, and the `HomeScreen` object. Nothing else. |

## Restyling the menu

The UI is built at runtime in `HomeScreen.BuildUi()` rather than authored on a
canvas — one file to read, and no scene wiring that can drift from the script.

- **Colours** are `[SerializeField]`s on the `HomeScreen` component (background,
  panel, accent), editable in the Inspector without touching code.
- **Layout** is a stack of `CreateRow(parent, name, top, width, height)` calls at
  a 1920x1080 reference resolution — change the `top` values to move things.
- **Adding a control** (server list, options, credits) means adding a row in
  `BuildUi` plus a handler, in the same style as the Join button.

## Reading server data in the control room

`Template` entries carry the `definitionId` of the `SwitchDefinition` /
`GaugeDefinition` they belong to, which is the same UID `Rot2p.Id` and
`GaugeNeedle` use — so a control can look itself up:

```csharp
var connection = ServerConnection.Instance;
if (connection != null && connection.IsConnected)
{
    var entry = connection.Template.FindSwitch(_definition.Id);
    if (entry != null)
        SetState(entry.position == "on");
}
```

Live state doesn't need this: `IoSync` already drives switches, lamps and gauges
by UID from `/api/io` (see `server-io-sync.md`). The template is the blueprint
around them — panels, annunciator legends, names — and nothing binds it to the
scene yet.
