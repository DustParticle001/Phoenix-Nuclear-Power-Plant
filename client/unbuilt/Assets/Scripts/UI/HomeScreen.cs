// HomeScreen.cs
using System.Collections;
using System.IO;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.InputSystem.UI;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

// The game's entry scene (build index 0). There is no offline mode: the control
// room only loads once a server has been joined, so the screen is a title, a
// server address and a Join button.
//
// The UI is built in code instead of being authored on a canvas — the whole
// screen is one file to read, and there is no prefab/scene wiring to keep in
// sync with the script. Tweak the numbers in BuildUi to restyle it.
public class HomeScreen : MonoBehaviour
{
    [Header("Flow")]
    [Tooltip("Scene loaded after a successful join. Must be in Build Settings. " +
             "A server that names its own scene in /api/info wins over this.")]
    [SerializeField] private string _controlRoomScene = "MainScene";

    [Tooltip("Address the field starts with: host, host:port, or a full http:// URL.")]
    [SerializeField] private string _defaultAddress = "localhost:8000";

    [Header("Style")]
    [SerializeField] private Color _backgroundColor = new Color(0.043f, 0.055f, 0.071f);
    [SerializeField] private Color _panelColor = new Color(0.102f, 0.118f, 0.141f);
    [SerializeField] private Color _accentColor = new Color(0.98f, 0.62f, 0.15f);

    // Last address that joined successfully, so restarting doesn't mean retyping.
    private const string AddressPrefKey = "pnpp.lastServerAddress";

    private static readonly Color TextColor  = new Color(0.87f, 0.89f, 0.91f);
    private static readonly Color MutedColor = new Color(0.55f, 0.59f, 0.64f);
    private static readonly Color ErrorColor = new Color(0.93f, 0.42f, 0.36f);
    private static readonly Color OkColor    = new Color(0.45f, 0.82f, 0.51f);

    private TMP_InputField _addressField;
    private Button _joinButton;
    private TextMeshProUGUI _joinLabel;
    private TextMeshProUGUI _statusText;
    private bool _joining;

    private void Awake()
    {
        // The control room locks the cursor (InteractionManager); the menu needs
        // it back, including when the player returns here from a session.
        Cursor.lockState = CursorLockMode.None;
        Cursor.visible = true;

        EnsureEventSystem();
        BuildUi();
    }

    private void Start()
    {
        _addressField.text = PlayerPrefs.GetString(AddressPrefKey, _defaultAddress);
        _addressField.Select();
        SetStatus("Enter a server address and join to play.", MutedColor);
    }

    // ---------------------------------------------------------------- flow

    private void OnJoinClicked()
    {
        if (_joining)
            return;

        string address = _addressField.text.Trim();
        if (address.Length == 0)
        {
            SetStatus("Enter a server address, e.g. localhost:8000.", ErrorColor);
            return;
        }

        StartCoroutine(JoinRoutine(address));
    }

    private IEnumerator JoinRoutine(string address)
    {
        SetJoining(true);
        SetStatus($"Connecting to {ServerConnection.NormalizeUrl(address)} ...", MutedColor);

        bool joined = false;
        string message = null;

        var connection = ServerConnection.GetOrCreate();
        yield return connection.Join(address, (success, text) =>
        {
            joined = success;
            message = text;
        });

        if (!joined)
        {
            SetJoining(false);
            SetStatus(message ?? "Could not join the server.", ErrorColor);
            yield break;
        }

        // The server says which control room this session belongs in; fall back
        // to the serialized scene when it doesn't name one we have.
        string scene = IsSceneInBuild(connection.Info.scene) ? connection.Info.scene : _controlRoomScene;
        if (!IsSceneInBuild(scene))
        {
            connection.Disconnect();
            SetJoining(false);
            SetStatus($"Joined, but the scene '{scene}' is not in Build Settings.", ErrorColor);
            yield break;
        }

        PlayerPrefs.SetString(AddressPrefKey, address);
        PlayerPrefs.Save();

        SetStatus($"{message} Loading control room ...", OkColor);
        yield return null;   // let that paint before the load stalls the frame

        SceneManager.LoadScene(scene);
    }

    private void OnQuitClicked()
    {
#if UNITY_EDITOR
        UnityEditor.EditorApplication.isPlaying = false;
#else
        Application.Quit();
#endif
    }

    private void SetJoining(bool joining)
    {
        _joining = joining;
        _joinButton.interactable = !joining;
        _addressField.interactable = !joining;
        _joinLabel.text = joining ? "JOINING ..." : "JOIN SERVER";
    }

    private void SetStatus(string message, Color color)
    {
        _statusText.text = message;
        _statusText.color = color;
    }

    private static bool IsSceneInBuild(string sceneName)
    {
        if (string.IsNullOrEmpty(sceneName))
            return false;

        for (int i = 0; i < SceneManager.sceneCountInBuildSettings; i++)
            if (Path.GetFileNameWithoutExtension(SceneUtility.GetScenePathByBuildIndex(i)) == sceneName)
                return true;

        return false;
    }

    // The scene ships an EventSystem; this covers dropping HomeScreen into a
    // scene that has none (no EventSystem = dead buttons, with no error).
    private static void EnsureEventSystem()
    {
        if (EventSystem.current != null)
            return;

        var eventSystem = new GameObject("EventSystem", typeof(EventSystem));
        eventSystem.AddComponent<InputSystemUIInputModule>().AssignDefaultActions();
    }

    // ------------------------------------------------------------------ ui

    private void BuildUi()
    {
        var canvasObject = new GameObject("HomeScreenCanvas",
            typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        canvasObject.transform.SetParent(transform, false);

        var canvas = canvasObject.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;

        var scaler = canvasObject.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920f, 1080f);
        scaler.matchWidthOrHeight = 0.5f;

        Transform root = canvasObject.transform;

        AddImage(Stretch(CreateRect("Background", root)), _backgroundColor);

        AddText(CreateRow(root, "Title", 150f, 1600f, 104f),
            "PHOENIX NUCLEAR POWER PLANT", 76f, TextColor, TextAlignmentOptions.Center);
        AddText(CreateRow(root, "Subtitle", 258f, 1600f, 44f),
            "MAIN CONTROL ROOM SIMULATOR", 28f, _accentColor, TextAlignmentOptions.Center);

        // Join card, centred.
        RectTransform panel = CreateRect("JoinPanel", root);
        panel.anchorMin = panel.anchorMax = panel.pivot = new Vector2(0.5f, 0.5f);
        panel.sizeDelta = new Vector2(680f, 420f);
        panel.anchoredPosition = new Vector2(0f, -40f);
        AddImage(panel, _panelColor);

        AddText(CreateRow(panel, "PanelTitle", 26f, 600f, 44f),
            "JOIN A SERVER", 34f, TextColor, TextAlignmentOptions.Center);
        AddText(CreateRow(panel, "Hint", 74f, 600f, 30f),
            "A server is required to play.", 22f, MutedColor, TextAlignmentOptions.Center);

        AddText(CreateRow(panel, "AddressLabel", 128f, 600f, 30f),
            "SERVER ADDRESS", 20f, MutedColor, TextAlignmentOptions.Left);
        _addressField = AddInputField(CreateRow(panel, "AddressField", 160f, 600f, 60f),
            _defaultAddress, 28f);
        _addressField.onSubmit.AddListener(_ => OnJoinClicked());

        _joinButton = AddButton(CreateRow(panel, "JoinButton", 244f, 600f, 66f),
            "JOIN SERVER", 30f, _accentColor, new Color(0.08f, 0.08f, 0.09f), out _joinLabel);
        _joinButton.onClick.AddListener(OnJoinClicked);

        _statusText = AddText(CreateRow(panel, "Status", 324f, 600f, 80f),
            "", 20f, MutedColor, TextAlignmentOptions.Top);
        _statusText.textWrappingMode = TextWrappingModes.Normal;

        // Quit, bottom centre.
        RectTransform quit = CreateRect("QuitButton", root);
        quit.anchorMin = quit.anchorMax = quit.pivot = new Vector2(0.5f, 0f);
        quit.sizeDelta = new Vector2(220f, 54f);
        quit.anchoredPosition = new Vector2(0f, 110f);
        AddButton(quit, "QUIT", 24f, new Color(0.16f, 0.18f, 0.21f), TextColor, out _)
            .onClick.AddListener(OnQuitClicked);

        RectTransform footer = CreateRect("Footer", root);
        footer.anchorMin = footer.anchorMax = footer.pivot = new Vector2(0.5f, 0f);
        footer.sizeDelta = new Vector2(1400f, 30f);
        footer.anchoredPosition = new Vector2(0f, 46f);
        AddText(footer, $"v{Application.version}  ·  © 2026 DHE Simulations Team",
            18f, MutedColor, TextAlignmentOptions.Center);
    }

    private static RectTransform CreateRect(string name, Transform parent)
    {
        var rect = new GameObject(name, typeof(RectTransform)).GetComponent<RectTransform>();
        rect.SetParent(parent, false);
        return rect;
    }

    // Child pinned to the top centre of its parent, positioned by its top edge —
    // the whole screen is laid out as a stack of these.
    private static RectTransform CreateRow(Transform parent, string name, float top, float width, float height)
    {
        RectTransform rect = CreateRect(name, parent);
        rect.anchorMin = rect.anchorMax = rect.pivot = new Vector2(0.5f, 1f);
        rect.sizeDelta = new Vector2(width, height);
        rect.anchoredPosition = new Vector2(0f, -top);
        return rect;
    }

    private static RectTransform Stretch(RectTransform rect, float padX = 0f, float padY = 0f)
    {
        rect.anchorMin = Vector2.zero;
        rect.anchorMax = Vector2.one;
        rect.pivot = new Vector2(0.5f, 0.5f);
        rect.offsetMin = new Vector2(padX, padY);
        rect.offsetMax = new Vector2(-padX, -padY);
        return rect;
    }

    private static Image AddImage(RectTransform rect, Color color)
    {
        var image = rect.gameObject.AddComponent<Image>();
        image.color = color;
        return image;
    }

    private static TextMeshProUGUI AddText(RectTransform rect, string content, float size,
        Color color, TextAlignmentOptions alignment)
    {
        var text = rect.gameObject.AddComponent<TextMeshProUGUI>();
        text.text = content;
        text.fontSize = size;
        text.color = color;
        text.alignment = alignment;
        text.textWrappingMode = TextWrappingModes.NoWrap;
        text.raycastTarget = false;   // never swallow clicks meant for a button
        return text;
    }

    private Button AddButton(RectTransform rect, string label, float fontSize,
        Color faceColor, Color labelColor, out TextMeshProUGUI labelText)
    {
        Image face = AddImage(rect, faceColor);

        var button = rect.gameObject.AddComponent<Button>();
        button.targetGraphic = face;

        // Tints multiply the face colour, so white == "as authored".
        ColorBlock colors = button.colors;
        colors.normalColor = Color.white;
        colors.highlightedColor = new Color(1.12f, 1.12f, 1.12f, 1f);
        colors.pressedColor = new Color(0.82f, 0.82f, 0.82f, 1f);
        colors.selectedColor = Color.white;
        colors.disabledColor = new Color(0.45f, 0.45f, 0.45f, 1f);
        colors.fadeDuration = 0.08f;
        button.colors = colors;

        labelText = AddText(Stretch(CreateRect("Label", rect)), label, fontSize,
            labelColor, TextAlignmentOptions.Center);
        return button;
    }

    private TMP_InputField AddInputField(RectTransform rect, string placeholderText, float fontSize)
    {
        AddImage(rect, new Color(0.043f, 0.051f, 0.063f));

        // Assembled inactive: TMP_InputField inspects its parts on enable, so it
        // must not come up before textViewport/textComponent are set.
        rect.gameObject.SetActive(false);

        RectTransform viewport = Stretch(CreateRect("Text Area", rect), 14f, 8f);
        viewport.gameObject.AddComponent<RectMask2D>();

        TextMeshProUGUI placeholder = AddText(Stretch(CreateRect("Placeholder", viewport)),
            placeholderText, fontSize, MutedColor, TextAlignmentOptions.Left);
        TextMeshProUGUI text = AddText(Stretch(CreateRect("Text", viewport)),
            "", fontSize, TextColor, TextAlignmentOptions.Left);

        var field = rect.gameObject.AddComponent<TMP_InputField>();
        field.textViewport = viewport;
        field.textComponent = text;
        field.placeholder = placeholder;
        field.lineType = TMP_InputField.LineType.SingleLine;
        field.pointSize = fontSize;
        field.customCaretColor = true;
        field.caretColor = _accentColor;
        field.caretWidth = 2;
        field.selectionColor = new Color(_accentColor.r, _accentColor.g, _accentColor.b, 0.35f);

        rect.gameObject.SetActive(true);
        return field;
    }
}
