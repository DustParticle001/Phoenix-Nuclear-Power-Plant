using UnityEngine;
using UnityEngine.InputSystem;

public class InteractionManager : MonoBehaviour
{
    [SerializeField] private Camera    _camera;
    [SerializeField] private LayerMask _interactableLayer;
    [SerializeField] private float     _maxDistance = 10f;

    private InputAction _clickAction;

    private void Awake()
    {
        _clickAction = new InputAction(
            type: InputActionType.Button,
            binding: "<Mouse>/leftButton");

        _clickAction.performed += HandleClick;
        _clickAction.Enable();

        Cursor.lockState = CursorLockMode.Locked;
        Cursor.visible = false;
    }

    private void OnDestroy()
    {
        _clickAction.performed -= HandleClick;
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

    private void HandleClick(InputAction.CallbackContext _)
    {
        var ray = _camera.ScreenPointToRay(Mouse.current.position.ReadValue());

        if (Physics.Raycast(ray, out RaycastHit hit, _maxDistance, _interactableLayer))
        {
            if (hit.collider.GetComponentInParent<Rot2p>() is { } sw2)
                sw2.OnInteract(hit.point);
            else if (hit.collider.GetComponentInParent<Rot3p>() is { } sw3)
                sw3.OnInteract(hit.point);
        }
    }
}