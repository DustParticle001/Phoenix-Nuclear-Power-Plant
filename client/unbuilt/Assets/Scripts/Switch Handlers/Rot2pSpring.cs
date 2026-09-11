using UnityEngine;

// A two-position rotary switch with a spring return: it rests in "off" and is
// only in "on" while the player holds the mouse button down. Lamp test, alarm
// reset, master reset - a switch that is a command rather than a state.
//
// Clicking anywhere on the handle takes it to "on", because there is only one
// way for it to go; the click side matters on Rot2p, which latches, and here
// it doesn't. Wire format is Rot2p's ("off"/"on"), so a definition can move
// between a latching switch and a spring-return one without the server
// noticing.
public class Rot2pSpring : MonoBehaviour, ISwitchControl, IHoldInteractable
{
    // Position names the server knows this switch by; order matches IsOn.
    private static readonly string[] _positionNames = { "off", "on" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    // The definition's UID if one is assigned, otherwise a panel above this
    // control may name it - see IControlIdSource.
    public string Id => ControlId.Resolve(this, _definition);

    [Header("Parts")]
    [SerializeField] private Transform _handle;

    [Header("Rotation Config")]
    [SerializeField] private Vector3 _onRotation  = new Vector3(0f, -35f, 0f);
    [SerializeField] private Vector3 _offRotation = new Vector3(0f,   0f, 0f);
    [SerializeField] private float   _speed = 12f;

    [Header("Spring")]
    [Tooltip("Shortest time the switch stays in 'on', however briefly it was " +
             "clicked. IoSync reports positions on a timer, so a press shorter " +
             "than one tick would never reach the server at all. Keep this at " +
             "or above the server's report interval (0.2 s by default).")]
    [SerializeField] private float _minimumHoldSeconds = 0.25f;

    private Quaternion _targetRotation;

    // This client pressed it and still owes it a return. Nothing else may spring
    // the switch back: "on" arriving from the server is another player's hand on
    // their own copy of it, and they are the ones who will let go.
    private bool _springing;
    private bool _pressed;
    private float _heldSeconds;

    public bool IsOn { get; private set; }

    public event System.Action<bool> OnStateChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => IsOn ? "on" : "off";

    public void SetPosition(string position)
    {
        // The operator's hand wins while it is on the switch. The server can
        // hold a stale "off" for a tick after we report the press, and snapping
        // back under a held button is worse than being a tick behind.
        if (_pressed)
            return;

        if (string.Equals(position, "on", System.StringComparison.OrdinalIgnoreCase))
            SetState(true);
        else if (string.Equals(position, "off", System.StringComparison.OrdinalIgnoreCase))
            SetState(false);
        else
            Debug.LogWarning($"[Switch {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // A spring switch has no start position to choose - it is wherever the
        // spring leaves it. Set directly (not via SetState) so scene load
        // doesn't fire OnStateChanged before listeners have subscribed.
        IsOn = false;
        _targetRotation = Quaternion.Euler(_offRotation);
        _handle.localRotation = _targetRotation;
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

        _handle.localRotation = Quaternion.Lerp(
            _handle.localRotation, _targetRotation, Time.deltaTime * _speed);
    }

    // --- IHoldInteractable --------------------------------------------------

    public void OnInteract(Vector3 worldHitPoint)
    {
        _pressed = true;
        _springing = true;
        _heldSeconds = 0f;
        SetState(true);
    }

    public void OnRelease()
    {
        // Not SetState(false): Update owes the switch its minimum hold first.
        _pressed = false;
    }

    private void SetState(bool on)
    {
        if (IsOn == on)
            return;

        IsOn = on;
        _targetRotation = Quaternion.Euler(IsOn ? _onRotation : _offRotation);
        OnStateChanged?.Invoke(IsOn);
        Debug.Log($"[Switch {Id}] → {(IsOn ? "ON" : "OFF")}");
    }
}
