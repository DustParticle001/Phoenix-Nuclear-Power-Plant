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
    private Quaternion _targetRotation;

    private void Awake()
    {
        _zeroRotation = _needle.localRotation;
        SetValue(_definition != null ? _definition.minValue : 0f);
        _needle.localRotation = _targetRotation;
    }

    private void Update()
    {
        if (_useTestValue)
            SetValue(_testValue);

        _needle.localRotation = Quaternion.Lerp(
            _needle.localRotation, _targetRotation, Time.deltaTime * _speed);
    }

    public void SetValue(float value)
    {
        Value = _definition != null
            ? Mathf.Clamp(value, _definition.minValue, _definition.maxValue)
            : value;

        float angle = _definition != null ? _definition.ValueToAngle(Value) : 0f;
        _targetRotation = _zeroRotation * Quaternion.AngleAxis(angle, _rotationAxis);
    }
}
