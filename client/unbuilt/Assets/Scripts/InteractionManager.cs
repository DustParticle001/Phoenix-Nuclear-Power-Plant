using UnityEngine;
using UnityEngine.InputSystem;

// Turns clicks into interactions: raycast from the camera, hand the hit to
// whatever IInteractable sits on (or above) the collider.
//
// Both edges of the click are dispatched, because spring-return switches and
// momentary buttons need the release as much as the press. The control pressed
// is remembered and released, wherever the player is looking by then - in the
// room your hand stays on the switch while you look somewhere else.
public class InteractionManager : MonoBehaviour
{
    [SerializeField] private Camera    _camera;
    [SerializeField] private LayerMask _interactableLayer;
    [SerializeField] private float     _maxDistance = 10f;

    private InputAction _clickAction;

    // The spring-return control the mouse button is currently down on, if any.
    private IHoldInteractable _held;

    private void Awake()
    {
        _clickAction = new InputAction(
            type: InputActionType.Button,
            binding: "<Mouse>/leftButton");

        // A Button action performs on press and cancels on release.
        _clickAction.performed += HandlePress;
        _clickAction.canceled  += HandleRelease;
        _clickAction.Enable();

        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
    }

    private void OnDestroy()
    {
        _clickAction.performed -= HandlePress;
        _clickAction.canceled  -= HandleRelease;
        _clickAction.Disable();
    }

    private void Update()
    {
        // Press Escape to unlock cursor during development
        if (Keyboard.current.escapeKey.wasPressedThisFrame)
        {
            Cursor.lockState = CursorLockMode.None;
            Cursor.visible = true;
        }
    }

    private void HandlePress(InputAction.CallbackContext _)
    {
        // A press with something still held means the release went missing
        // (focus lost mid-click, say). Let go of it rather than leaving a
        // switch held down by nobody.
        ReleaseHeld();

        var ray = _camera.ScreenPointToRay(Mouse.current.position.ReadValue());

        if (!Physics.Raycast(ray, out RaycastHit hit, _maxDistance, _interactableLayer))
            return;

        var control = hit.collider.GetComponentInParent<IInteractable>();
        if (control == null)
            return;

        control.OnInteract(hit.point);

        // Latching controls are done at this point; the rest are held until the
        // button comes up.
        _held = control as IHoldInteractable;
    }

    private void HandleRelease(InputAction.CallbackContext _) => ReleaseHeld();

    private void ReleaseHeld()
    {
        if (_held == null)
            return;

        // Interface references don't get Unity's destroyed-object ==, so check
        // through the component.
        if (_held is MonoBehaviour behaviour && behaviour != null)
            _held.OnRelease();

        _held = null;
    }
}
