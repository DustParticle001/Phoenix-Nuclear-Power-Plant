using UnityEngine;

public class CameraZoom : MonoBehaviour
{
    [SerializeField] private Camera cam;                 // leave empty to auto-grab Camera.main
    [SerializeField] private float zoomedFOV = 9f;       // FOV while zoomed in
    [SerializeField] private float zoomSpeed = 10f;      // transition smoothness
    [SerializeField] private KeyCode zoomKey = KeyCode.E; // E key to zoom in

    private float defaultFOV;
    private float targetFOV;
    private bool zoomedIn = false;   // <-- moved up here as a field

    void Awake()
    {
        if (cam == null) cam = Camera.main;
        defaultFOV = cam.fieldOfView;
        targetFOV = defaultFOV;
    }

    void Update()
    {
        if (Input.GetKeyDown(zoomKey)) zoomedIn = !zoomedIn;
        targetFOV = zoomedIn ? zoomedFOV : defaultFOV;
        cam.fieldOfView = Mathf.Lerp(cam.fieldOfView, targetFOV, zoomSpeed * Time.deltaTime);
    }
}