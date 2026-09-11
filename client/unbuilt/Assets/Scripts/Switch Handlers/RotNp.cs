using UnityEngine;

// A multiposition rotary selector: N detents, one per click. Rot3p carried past
// three positions - the meter selector that reads six points off one gauge, a
// frequency selector, a synchroscope's incoming-line switch. It latches, like
// Rot3p: a detent is a state, not a command.
//
// Two ways to say where the detents are, because a switch is authored either
// way round. Even Step is the usual one - a rotary has evenly spaced detents,
// so one degrees-per-position covers all of them. Per Position takes an angle
// for each, for the switches that aren't even: a wide gap where a detent was
// left out, or an OFF that sits away from the rest.
//
// Both measure from the handle's MODELLED rotation, read once on scene load,
// the way Trans2p measures travel from the cap's modelled position: the
// modeller poses the handle where it belongs and this only ever turns it from
// there. So there is no per-position Vector3 to keep in step with the model.
//
// On the wire the positions are "p1".."pN" - geometry, not meaning, like every
// other controller here. What detent 3 selects belongs to the server's I/O map;
// on this side it is the third detent, and it is what `/turnswitch <switch> 3`
// moves the switch to.
public class RotNp : MonoBehaviour, ISwitchControl, IInteractable
{
    // One enum for both axis fields: the shaft the handle turns about, and the
    // plane a click is tested against. Same three choices, different jobs.
    public enum Axis { X, Y, Z }

    public enum AngleMode { EvenStep, PerPosition }

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    // The definition's UID if one is assigned, otherwise a panel above this
    // control may name it - see IControlIdSource.
    public string Id => ControlId.Resolve(this, _definition);

    [Header("Parts")]
    [SerializeField] private Transform _handle;

    [Header("Detents")]
    [Tooltip("The shaft: axis the handle turns about, in the handle's own space.")]
    [SerializeField] private Axis _turnAxis = Axis.X;

    [Tooltip("Even Step: evenly spaced detents, one angle between each. " +
             "Per Position: an angle for every detent, for a switch whose " +
             "detents aren't evenly spaced.")]
    [SerializeField] private AngleMode _angleMode = AngleMode.EvenStep;

    [Tooltip("Even Step only. How many detents the switch has.")]
    [SerializeField] private int _positionCount = 4;

    [Tooltip("Even Step only. Degrees from one detent to the next. Negate it " +
             "to turn the other way.")]
    [SerializeField] private float _degreesPerPosition = 30f;

    [Tooltip("Even Step only. The detent the handle was MODELLED in - where it " +
             "sits with no rotation applied. 1 sweeps the whole switch one way " +
             "from the modelled pose; the middle detent sweeps it both ways.")]
    [SerializeField] private int _restPosition = 1;

    [Tooltip("Per Position only. Degrees from the modelled pose for each " +
             "detent, in order. How many entries there are is how many " +
             "positions the switch has.")]
    [SerializeField] private float[] _positionAngles = { 0f, 30f, 60f, 90f };

    [Header("State")]
    [Tooltip("Detent the switch starts in on scene load, counting from 1.")]
    [SerializeField] private int _defaultPosition = 1;

    [Header("Interaction")]
    [Tooltip("Which side of the handle was clicked decides whether it steps up " +
             "or down a detent.")]
    [SerializeField] private Axis _splitAxis = Axis.X;
    [SerializeField] private bool _invertSides = false;

    [Tooltip("On: past the last detent it comes round to the first. Off: it " +
             "stops there, like a switch with end stops - which is most of them.")]
    [SerializeField] private bool _wrap = false;

    [Header("Rotation Config")]
    [SerializeField] private float _speed = 8f;

    // The handle as modelled. Every detent angle is measured from it, so it is
    // read before anything has turned it.
    private Quaternion _restRotation;

    private string[] _positionNames;

    // Which detent it is in, counting from 1 - the way a panel is engraved, the
    // way /turnswitch counts, and the number in the position name.
    public int CurrentPosition { get; private set; } = 1;

    // Where the count comes from depends on the mode: typed in for Even Step,
    // and in Per Position it is however many angles were given.
    public int PositionCount => _angleMode == AngleMode.EvenStep
        ? Mathf.Max(2, _positionCount)
        : Mathf.Max(1, _positionAngles != null ? _positionAngles.Length : 0);

    public event System.Action<int> OnPositionChanged;

    // --- ISwitchControl -----------------------------------------------------

    // Built rather than static, unlike the other controllers: the list is as
    // long as this switch was made. IoSync reads it every tick, so it is cached
    // and only rebuilt if the count changes under it - someone tuning the
    // switch in play mode.
    public string[] Positions
    {
        get
        {
            if (_positionNames == null || _positionNames.Length != PositionCount)
                RebuildPositionNames();

            return _positionNames;
        }
    }

    // Clamped on the way out: the count can shrink under a switch being tuned
    // in play mode, and Update hasn't necessarily caught it yet this frame.
    public string Position => Positions[Mathf.Clamp(CurrentPosition, 1, PositionCount) - 1];

    public void SetPosition(string position)
    {
        string[] names = Positions;

        for (int i = 0; i < names.Length; i++)
        {
            if (!string.Equals(position, names[i], System.StringComparison.OrdinalIgnoreCase))
                continue;

            SetPosition(i + 1);
            return;
        }

        Debug.LogWarning($"[Switch {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // Read the modelled pose before anything turns the handle: it is what
        // every detent angle is measured from.
        _restRotation = _handle.localRotation;

        if (_angleMode == AngleMode.PerPosition && (_positionAngles == null || _positionAngles.Length < 2))
            Debug.LogError(
                $"[Switch {Id}] is set to Per Position angles but has " +
                $"{(_positionAngles != null ? _positionAngles.Length : 0)} of them. " +
                "Give it one angle per detent, or set it to Even Step.");

        // Set directly (not via SetPosition) so scene load doesn't fire
        // OnPositionChanged before listeners have subscribed.
        CurrentPosition = Mathf.Clamp(_defaultPosition, 1, PositionCount);
        _handle.localRotation = RotationFor(CurrentPosition);
    }

    private void Update()
    {
        // Tuning the switch in play mode can leave it in a detent it no longer
        // has. Come back inside rather than reporting a position that isn't on
        // the switch any more.
        int inRange = Mathf.Clamp(CurrentPosition, 1, PositionCount);
        if (inRange != CurrentPosition)
            MoveTo(inRange);

        // Recomputed rather than cached on the way in, so an angle tuned in
        // play mode shows at once instead of at the next click.
        _handle.localRotation = Quaternion.Lerp(
            _handle.localRotation, RotationFor(CurrentPosition), Time.deltaTime * _speed);
    }

    // --- IInteractable ------------------------------------------------------

    public void OnInteract(Vector3 worldHitPoint)
    {
        // Test in the switch body's frame, not the handle's — the handle
        // rotates, which would tilt the split plane with it.
        Vector3 localHit = transform.InverseTransformPoint(worldHitPoint);

        float value = _splitAxis switch
        {
            Axis.X => localHit.x,
            Axis.Y => localHit.y,
            Axis.Z => localHit.z,
            _      => localHit.x
        };

        bool clickedPositiveSide = value >= 0f;
        if (_invertSides) clickedPositiveSide = !clickedPositiveSide;

        Step(clickedPositiveSide ? 1 : -1);
    }

    // Turn it on by detents, the way a hand does. Stops at the ends unless the
    // switch is set to wrap.
    public void Step(int detents)
    {
        int count = PositionCount;
        int next = CurrentPosition + detents;

        // Modulo twice: C# keeps the sign of the left operand, so stepping down
        // off the first detent would otherwise land negative.
        next = _wrap
            ? ((next - 1) % count + count) % count + 1
            : Mathf.Clamp(next, 1, count);

        MoveTo(next);
    }

    // Counting from 1. Out of range is clamped rather than thrown: a switch has
    // end stops, and the server asking for a detent this one doesn't have is a
    // mismatch to read in the log, not a reason to take the frame down.
    public void SetPosition(int position)
    {
        int clamped = Mathf.Clamp(position, 1, PositionCount);

        if (clamped != position)
            Debug.LogWarning(
                $"[Switch {Id}] position {position} is outside 1-{PositionCount}; " +
                $"using {clamped}.");

        MoveTo(clamped);
    }

    private void MoveTo(int position)
    {
        if (CurrentPosition == position)
            return;

        CurrentPosition = position;
        OnPositionChanged?.Invoke(CurrentPosition);
        Debug.Log($"[Switch {Id}] → {Position} of {PositionCount}");
    }

    // Post-multiplied, so the turn is about the handle's own axis: the shaft
    // stays the shaft however the handle was posed in the model.
    private Quaternion RotationFor(int position) =>
        _restRotation * Quaternion.AngleAxis(AngleFor(position), AxisVector(_turnAxis));

    // Degrees from the modelled pose.
    private float AngleFor(int position)
    {
        if (_angleMode == AngleMode.EvenStep)
            return _degreesPerPosition * (position - Mathf.Clamp(_restPosition, 1, PositionCount));

        int index = position - 1;

        // A short angle list is already an error from Awake; sitting at the
        // modelled pose is the harmless way to be wrong about it.
        return _positionAngles != null && index >= 0 && index < _positionAngles.Length
            ? _positionAngles[index]
            : 0f;
    }

    private static Vector3 AxisVector(Axis axis) => axis switch
    {
        Axis.X => Vector3.right,
        Axis.Y => Vector3.up,
        Axis.Z => Vector3.forward,
        _      => Vector3.right
    };

    private void RebuildPositionNames()
    {
        int count = PositionCount;
        _positionNames = new string[count];

        for (int i = 0; i < count; i++)
            _positionNames[i] = $"p{i + 1}";
    }

    // Clamped as they are typed: the inspector is where these are set, and a
    // rest or start detent off the end of the switch is worth catching there
    // rather than on the next scene load.
    private void OnValidate()
    {
        _positionCount = Mathf.Max(2, _positionCount);

        // Against the Even Step count, not PositionCount: it is an Even Step
        // field, and clamping it to a short angle list would quietly rewrite it
        // while the switch is in the other mode.
        _restPosition = Mathf.Clamp(_restPosition, 1, _positionCount);

        _defaultPosition = Mathf.Clamp(_defaultPosition, 1, PositionCount);
    }
}
