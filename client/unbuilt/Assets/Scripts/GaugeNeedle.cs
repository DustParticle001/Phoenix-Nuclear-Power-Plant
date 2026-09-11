// GaugeNeedle.cs
using UnityEngine;

// Rotates a gauge needle to track a value, mapped through the gauge's
// definition so the needle always agrees with the baked dial markings.
// Add this to the gauge model root and assign the needle transform.
// The needle's authored local rotation is taken as 12 o'clock (0 deg).
public class GaugeNeedle : MonoBehaviour
{
    [Header("Identity")]
    [SerializeField] private GaugeDefinition _definition;
    public GaugeDefinition Definition => _definition;
    public string Id => _definition != null ? _definition.Id : "unassigned";

    [Header("Parts")]
    [SerializeField] private Transform _needle;

    [Header("Rotation Config")]
    [Tooltip("Local axis the needle rotates around. Negate it if the needle sweeps the wrong way.")]
    [SerializeField] private Vector3 _rotationAxis = Vector3.forward;

    [Header("Testing")]
    [Tooltip("While enabled, the needle follows Test Value instead of SetValue calls.")]
    [SerializeField] private bool _useTestValue = false;
    [SerializeField] private float _testValue = 0f;

    public float Value { get; private set; }

    private Quaternion _zeroRotation;
    private float _currentAngle;
    private float _targetAngle;
    private float _angleVelocity;

    // A dial that sweeps the whole circle has no ends: its scale wraps, so the
    // shortest way between two readings is the way the pointer really travels.
    private float _sweep;
    private bool _wraps;

    // Fallback for a needle with no definition assigned: rigid, so it reads
    // exactly what it is given rather than inventing a lag nobody asked for.
    private const float DefaultResponse = 0.02f;

    // How long the pointer takes to catch a step change. This is the
    // INSTRUMENT, not the signal: the server can step a value as sharply as it
    // likes and a real pointer still has a pivot, a spring and damping to get
    // there through. It used to be a per-needle Inspector value that had to be
    // set high enough to blend stepped setpoints into one sweep - at the sync
    // rate this now runs at there are no steps left to blend, so it went back
    // to being what it physically is: a property of the instrument, and so of
    // the definition that describes it.
    private float Response =>
        _definition != null ? Mathf.Max(0f, _definition.needleResponse) : DefaultResponse;

    private void Awake()
    {
        _zeroRotation = _needle.localRotation;

        _sweep = _definition != null ? Mathf.Abs(_definition.endAngle - _definition.startAngle) : 0f;
        _wraps = _sweep >= 359.99f;

        SetValue(_definition != null ? _definition.minValue : 0f);
        _currentAngle = _targetAngle;
        Apply();
    }

    private void Update()
    {
        if (_useTestValue)
            SetValue(_testValue);

        // Interpolate the angle, not the rotation: quaternion lerp takes the
        // shortest arc, which on swings wider than 180 deg cuts through the
        // bottom of the dial — outside the scale. The scalar angle always
        // stays within the sweep.
        //
        // On a full-circle dial the scale wraps, and the scalar angle doesn't
        // know it: a synchroscope crossing 12 o'clock reads 359 then 1, which is
        // two degrees on and 358 back. Roll the current angle into the same turn
        // as the target first, so the needle takes the short way — on a pointer
        // that turns continuously, that is always the way it is really going.
        if (_wraps)
        {
            float half = _sweep * 0.5f;
            float delta = Mathf.Repeat(_targetAngle - _currentAngle + half, _sweep) - half;
            _currentAngle = _targetAngle - delta;
        }

        // SmoothDamp, not an exponential lerp: synced values arrive as discrete
        // setpoints a few times a second, and a lerp converges before the next
        // one lands — the needle steps. SmoothDamp keeps its velocity across
        // setpoint changes, so a stream of steps reads as one continuous sweep.
        _currentAngle = Mathf.SmoothDamp(_currentAngle, _targetAngle, ref _angleVelocity, Response);
        Apply();
    }

    public void SetValue(float value)
    {
        Value = _definition != null
            ? Mathf.Clamp(value, _definition.minValue, _definition.maxValue)
            : value;

        _targetAngle = _definition != null ? _definition.ValueToAngle(Value) : 0f;
    }

    private void Apply() =>
        _needle.localRotation = _zeroRotation * Quaternion.AngleAxis(_currentAngle, _rotationAxis);
}
