using UnityEngine;

public class Rot3p : MonoBehaviour, ISwitchControl
{
    public enum SwitchPosition { Left, Center, Right }
    public enum SplitAxis { X, Y, Z }

    // Position names the server knows this switch by; order matches SwitchPosition.
    private static readonly string[] _positionNames = { "left", "center", "right" };

    [Header("Identity")]
    [SerializeField] private SwitchDefinition _definition;
    public SwitchDefinition Definition => _definition;
    public string Id => _definition != null ? _definition.Id : "unassigned";

    [Header("Parts")]
    [SerializeField] private Transform _handle;

    [Header("State")]
    [Tooltip("Position the switch starts in on scene load.")]
    [SerializeField] private SwitchPosition _defaultPosition = SwitchPosition.Center;

    [Header("Interaction")]
    [SerializeField] private SplitAxis _splitAxis = SplitAxis.X;
    [SerializeField] private bool _invertSides = false;

    [Header("Rotation Config")]
    [SerializeField] private Vector3 _leftRotation   = new Vector3( 35f, 0f, 0f);
    [SerializeField] private Vector3 _centerRotation = new Vector3(  0f, 0f, 0f);
    [SerializeField] private Vector3 _rightRotation  = new Vector3(-35f, 0f, 0f);
    [SerializeField] private float   _speed = 8f;

    private Quaternion _targetRotation;
    public SwitchPosition CurrentPosition { get; private set; } = SwitchPosition.Center;

    public event System.Action<SwitchPosition> OnPositionChanged;

    // --- ISwitchControl -----------------------------------------------------

    public string[] Positions => _positionNames;
    public string Position => _positionNames[(int)CurrentPosition];

    public void SetPosition(string position)
    {
        for (int i = 0; i < _positionNames.Length; i++)
        {
            if (!string.Equals(position, _positionNames[i], System.StringComparison.OrdinalIgnoreCase))
                continue;

            SetPosition((SwitchPosition)i);
            return;
        }

        Debug.LogWarning($"[Switch {Id}] ignoring unknown position '{position}'.");
    }

    private void Awake()
    {
        // Set directly (not via SetPosition) so scene load doesn't fire
        // OnPositionChanged before listeners have subscribed.
        CurrentPosition = _defaultPosition;
        _targetRotation = RotationFor(CurrentPosition);
        _handle.localRotation = _targetRotation;
    }

    private void Update()
    {
        _handle.localRotation = Quaternion.Lerp(
            _handle.localRotation, _targetRotation, Time.deltaTime * _speed);
    }

    public void OnInteract(Vector3 worldHitPoint)
    {
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

        SwitchPosition next = CurrentPosition switch
        {
            SwitchPosition.Left   => SwitchPosition.Center,
            SwitchPosition.Center => clickedPositiveSide ? SwitchPosition.Right : SwitchPosition.Left,
            SwitchPosition.Right  => SwitchPosition.Center,
            _                     => SwitchPosition.Center
        };

        SetPosition(next);
    }

    public void SetPosition(SwitchPosition pos)
    {
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