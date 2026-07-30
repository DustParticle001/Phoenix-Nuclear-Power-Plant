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
    [SerializeField] private float _speed = 8f;

    [Header("Testing")]
    [Tooltip("While enabled, the needle follows Test Value instead of SetValue calls.")]
    [SerializeField] private bool _useTestValue = false;
    [SerializeField] private float _testValue = 0f;

    public float Value { get; private set; }

    private Quaternion _zeroRotation;
    private float _currentAngle;
    private float _targetAngle;

    private void Awake()
    {
        _zeroRotation = _needle.localRotation;
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
        _currentAngle = Mathf.Lerp(_currentAngle, _targetAngle, Time.deltaTime * _speed);
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
