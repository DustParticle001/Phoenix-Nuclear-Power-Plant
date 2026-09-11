using UnityEngine;

// A three-position rotary switch with a spring return to centre: hold left and
// it sits left, hold right and it sits right, let go and it comes back. The
// breaker control switch of every control room - TRIP / normal / CLOSE, where
// both ends are momentary commands and centre is where the switch lives.
//
// Either end can be made maintained instead, for the switches that spring one
// way and latch the other (a pump control switch whose START springs back but
// whose PULL-TO-LOCK stays put). A latched end behaves like Rot3p: a click
// brings it back to centre.
//
// Wire format is Rot3p's ("left"/"center"/"right" - geometry, not meaning), so
// a definition can move between a latching switch and a spring-return one
// without the server noticing.
public class Rot3pSpring : MonoBehaviour, ISwitchControl, IHoldInteractable
{
    public enum SwitchPosition { Left, Center, Right }
    public enum SplitAxis { X, Y, Z }

    // Position names the server knows this switch by; order matches SwitchPosition.
    private static readonly string[] _positionNames = { "left", "center", "right" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    // The definition's UID if one is assigned, otherwise a panel above this
    // control may name it - see IControlIdSource.
    public string Id => ControlId.Resolve(this, _definition);

    [Header("Parts")]
    [SerializeField] private Transform _handle;

    [Header("Interaction")]
    [SerializeField] private SplitAxis _splitAxis = SplitAxis.X;
    [SerializeField] private bool _invertSides = false;

    [Header("Spring")]
    [Tooltip("Off: that end is maintained instead - it latches there and a " +
             "click brings it back to centre, like Rot3p.")]
    [SerializeField] private bool _leftSpringReturn = true;

    [Tooltip("Off: that end is maintained instead - it latches there and a " +
             "click brings it back to centre, like Rot3p.")]
    [SerializeField] private bool _rightSpringReturn = true;

    [Tooltip("Shortest time the switch stays off centre, however briefly it " +
             "was clicked. IoSync reports positions on a timer, so a press " +
             "shorter than one tick would never reach the server at all. Keep " +
             "this at or above the server's report interval (0.2 s by default).")]
    [SerializeField] private float _minimumHoldSeconds = 0.25f;

    [Header("Rotation Config")]
    [SerializeField] private Vector3 _leftRotation   = new Vector3( 35f, 0f, 0f);
    [SerializeField] private Vector3 _centerRotation = new Vector3(  0f, 0f, 0f);
    [SerializeField] private Vector3 _rightRotation  = new Vector3(-35f, 0f, 0f);
    [SerializeField] private float   _speed = 12f;

    private Quaternion _targetRotation;

    // This client pressed it and still owes it a return. Nothing else may spring
    // the switch back: a position arriving from the server is another player's
    // hand on their own copy of it, and they are the ones who will let go.
    private bool _springing;
    private bool _pressed;
    private float _heldSeconds;

    public SwitchPosition CurrentPosition { get; private set; } = SwitchPosition.Center;

    public event System.Action<SwitchPosition> OnPositionChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => _positionNames[(int)CurrentPosition];

    public void SetPosition(string position)
    {
        // The operator's hand wins while it is on the switch. The server can
        // hold a stale centre for a tick after we report the press, and snapping
        // back under a held button is worse than being a tick behind.
        if (_pressed)
            return;

        for (int i = 0; i < _positionNames.Length; i++)
        {
            if (!string.Equals(position, _positionNames[i], System.StringComparison.OrdinalIgnoreCase))
                continue;

            MoveTo((SwitchPosition)i);
            return;
        }

        Debug.LogWarning($"[Switch {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // A spring switch has no start position to choose - it is wherever the
        // spring leaves it. Set directly (not via MoveTo) so scene load doesn't
        // fire OnPositionChanged before listeners have subscribed.
        CurrentPosition = SwitchPosition.Center;
        _targetRotation = RotationFor(CurrentPosition);
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
                MoveTo(SwitchPosition.Center);
            }
        }

        _handle.localRotation = Quaternion.Lerp(
            _handle.localRotation, _targetRotation, Time.deltaTime * _speed);
    }

    // --- IHoldInteractable --------------------------------------------------

    public void OnInteract(Vector3 worldHitPoint)
    {
        // Anywhere but centre, a click brings it back and that is the whole
        // gesture - same as Rot3p. Covers both ways of being off centre: an end
        // that latched because it has no spring return, and the last press
        // still springing back, which this ends wherever it had got to.
        if (CurrentPosition != SwitchPosition.Center)
        {
            _springing = false;
            MoveTo(SwitchPosition.Center);
            return;
        }

        // Test in the switch body's frame, not the handle's — the handle
        // rotates, which would tilt the left/right split plane with it.
        Vector3 localHit = transform.InverseTransformPoint(worldHitPoint);

        float value = _splitAxis switch
        {
            SplitAxis.X => localHit.x,
            SplitAxis.Y => localHit.y,
            SplitAxis.Z => localHit.z,
            _           => localHit.x
        };

        bool clickedPositiveSide = value >= 0f;
        if (_invertSides) clickedPositiveSide = !clickedPositiveSide;

        SwitchPosition target = clickedPositiveSide ? SwitchPosition.Right : SwitchPosition.Left;

        _pressed = true;
        _springing = SpringReturns(target);
        _heldSeconds = 0f;
        MoveTo(target);
    }

    public void OnRelease()
    {
        // Not a move: Update owes a springing switch its minimum hold first,
        // and a maintained end isn't going anywhere.
        _pressed = false;
    }

    private bool SpringReturns(SwitchPosition position) => position switch
    {
        SwitchPosition.Left  => _leftSpringReturn,
        SwitchPosition.Right => _rightSpringReturn,
        _                    => false
    };

    // Private on purpose: "put it here and leave it" is not something a spring
    // switch can do, so the only ways in are the player's hand and the server.
    private void MoveTo(SwitchPosition pos)
    {
        if (CurrentPosition == pos)
            return;

        CurrentPosition = pos;
        _targetRotation = RotationFor(pos);
        OnPositionChanged?.Invoke(CurrentPosition);
        Debug.Log($"[Switch {Id}] → {CurrentPosition}");
    }

    private Quaternion RotationFor(SwitchPosition pos) => pos switch
    {
        SwitchPosition.Left   => Quaternion.Euler(_leftRotation),
        SwitchPosition.Center => Quaternion.Euler(_centerRotation),
        SwitchPosition.Right  => Quaternion.Euler(_rightRotation),
        _                     => Quaternion.Euler(_centerRotation)
    };
}
