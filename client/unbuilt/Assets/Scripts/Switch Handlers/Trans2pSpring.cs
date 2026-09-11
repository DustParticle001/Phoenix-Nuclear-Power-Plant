using UnityEngine;

// A momentary pushbutton - the ordinary kind. Same philosophy as Rot2pSpring,
// except the moving part travels instead of turning: hold the mouse button and
// the cap is in, let go and it comes straight back out. Reactor trip, turbine
// trip, alarm acknowledge, lamp test - the button that is a command.
//
// Two positions only, because a pushbutton has two.
//
// The cap's authored local position is taken as "released", so the modeller
// places the button where it belongs and this only ever pushes it in from
// there. Travel is set as a direction plus a depth rather than a second
// position, so it can be tuned with one number in play mode.
public class Trans2pSpring : MonoBehaviour, ISwitchControl, IHoldInteractable
{
    // Position names the server knows this button by; order matches IsPressed.
    private static readonly string[] _positionNames = { "released", "pressed" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    // The definition's UID if one is assigned, otherwise a panel above this
    // control may name it - see IControlIdSource.
    public string Id => ControlId.Resolve(this, _definition);

    [Header("Parts")]
    [Tooltip("The cap - the part that travels. Same field as a switch's handle.")]
    [SerializeField] private Transform _handle;

    [Header("Travel Config")]
    [Tooltip("Local direction the cap travels when pressed, in the space it " +
             "sits in. Negate it if the button pops out instead of sinking in.")]
    [SerializeField] private Vector3 _pressAxis = Vector3.back;

    [Tooltip("How far the cap travels, in metres.")]
    [SerializeField] private float _pressDepth = 0.004f;

    [SerializeField] private float _speed = 25f;

    [Header("Spring")]
    [Tooltip("Shortest time the button stays in, however briefly it was " +
             "clicked. IoSync reports positions on a timer, so a tap shorter " +
             "than one tick would never reach the server at all - and on a " +
             "momentary button that press is the entire signal. Keep this at " +
             "or above the server's report interval (0.2 s by default).")]
    [SerializeField] private float _minimumHoldSeconds = 0.25f;

    private Vector3 _releasedPosition;
    private Vector3 _targetPosition;

    // This client pressed it and still owes it a release. Nothing else may pop
    // the button back out: "pressed" arriving from the server is another
    // player's finger on their own copy of it, and they are the one who lifts it.
    private bool _springing;
    private bool _pressed;
    private float _heldSeconds;

    public bool IsPressed { get; private set; }

    public event System.Action<bool> OnStateChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => IsPressed ? "pressed" : "released";

    public void SetPosition(string position)
    {
        // The operator's finger wins while it is on the button. The server can
        // hold a stale "released" for a tick after we report the press, and
        // popping out under a held button is worse than being a tick behind.
        if (_pressed)
            return;

        if (string.Equals(position, "pressed", System.StringComparison.OrdinalIgnoreCase))
            SetState(true);
        else if (string.Equals(position, "released", System.StringComparison.OrdinalIgnoreCase))
            SetState(false);
        else
            Debug.LogWarning($"[Button {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // Read the released pose before anything moves the cap: it is the
        // authored position, and pressing is measured from it. A momentary
        // button has no start state to choose - it starts out, like the spring
        // leaves it.
        _releasedPosition = _handle.localPosition;

        IsPressed = false;
        _targetPosition = _releasedPosition;
        _handle.localPosition = _targetPosition;
    }

    private void Update()
    {
        if (_springing)
        {
            _heldSeconds += Time.deltaTime;

            // Let go once the player has and the sync loop has had its chance
            // to see the press.
            if (!_pressed && _heldSeconds >= _minimumHoldSeconds)
            {
                _springing = false;
                SetState(false);
            }
        }

        _handle.localPosition = Vector3.Lerp(
            _handle.localPosition, _targetPosition, Time.deltaTime * _speed);
    }

    // --- IHoldInteractable --------------------------------------------------

    // A button has no sides: the whole cap does the one thing it does, so the
    // hit point is nothing to it.
    public void OnInteract(Vector3 worldHitPoint)
    {
        _pressed = true;
        _springing = true;
        _heldSeconds = 0f;
        SetState(true);
    }

    public void OnRelease()
    {
        // Not SetState(false): Update owes the button its minimum hold first.
        _pressed = false;
    }

    private void SetState(bool pressed)
    {
        if (IsPressed == pressed)
            return;

        IsPressed = pressed;
        _targetPosition = PositionFor(IsPressed);
        OnStateChanged?.Invoke(IsPressed);
        Debug.Log($"[Button {Id}] → {(IsPressed ? "PRESSED" : "RELEASED")}");
    }

    // Normalized, so a hand-typed axis that isn't unit length doesn't quietly
    // scale the depth along with it.
    private Vector3 PositionFor(bool pressed) =>
        pressed ? _releasedPosition + _pressAxis.normalized * _pressDepth
                : _releasedPosition;
}
