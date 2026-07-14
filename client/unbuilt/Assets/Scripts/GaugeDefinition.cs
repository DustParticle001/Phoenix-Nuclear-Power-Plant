// GaugeDefinition.cs
using UnityEngine;

// Data-driven description of an analog gauge face: scale, sweep, ticks,
// color bands and styling. The editor baker (Editor/GaugeFaceBaker.cs)
// turns this into a dial-face texture + material; GaugeNeedle maps values
// through ValueToAngle at runtime, so the needle and the printed markings
// can never disagree about the scale.
//
// Angle convention: degrees, 0 = 12 o'clock, positive = clockwise when
// looking at the dial. A typical 270-degree gauge runs -135 .. +135.
[CreateAssetMenu(fileName = "GaugeDef_New", menuName = "NPP/Gauge Definition")]
public class GaugeDefinition : ScriptableObject
{
    [System.Serializable]
    public struct ColorBand
    {
        public float fromValue;
        public float toValue;
        public Color color;
    }

    [Header("Identity")]
    [SerializeField] private string _id;
    public string Id => _id;
    public string displayName;

    [Header("Scale")]
    public float minValue = 0f;
    public float maxValue = 100f;
    [Tooltip("Printed below the centre of the dial, e.g. \"bar\" or \"x100 RPM\".")]
    public string units = "";
    [Tooltip("Value step between numbered (major) ticks. Pick something that divides the range evenly.")]
    public float majorTickInterval = 10f;
    [Tooltip("Number of minor ticks between two major ticks.")]
    public int minorTicksPerMajor = 4;
    [Tooltip("Numeric format for tick labels, e.g. \"0\" or \"0.0\".")]
    public string labelFormat = "0";
    [Tooltip("Labels show value * multiplier — for \"x1000\" style dials.")]
    public float labelMultiplier = 1f;

    [Header("Sweep")]
    [Tooltip("Needle angle at minValue. 0 = 12 o'clock, clockwise positive.")]
    public float startAngle = -135f;
    [Tooltip("Needle angle at maxValue.")]
    public float endAngle = 135f;

    [Header("Color Bands")]
    [Tooltip("Colored arcs along the scale (normal / caution / danger zones), in scale values.")]
    public ColorBand[] bands = new ColorBand[0];

    [Header("Face Style")]
    public Color faceColor = new Color(0.93f, 0.93f, 0.90f);
    [Tooltip("Color of ticks and text.")]
    public Color markingColor = Color.black;
    [Tooltip("Optional label font. Uses the built-in font if empty.")]
    public Font labelFont;
    [Tooltip("All radii/lengths/sizes below are fractions of the face radius.")]
    public float tickOuterRadius = 0.90f;
    public float majorTickLength = 0.14f;
    public float minorTickLength = 0.08f;
    public float majorTickWidth = 0.022f;
    public float minorTickWidth = 0.010f;
    [Tooltip("Radius the number labels are centred on.")]
    public float labelRadius = 0.62f;
    public float labelSize = 0.12f;
    [Tooltip("Size of the display name / units text.")]
    public float textSize = 0.10f;
    [Tooltip("Color bands run between these two radii (default: just outside the ticks).")]
    public float bandOuterRadius = 0.965f;
    public float bandInnerRadius = 0.905f;
    [Tooltip("Print the display name on the upper half of the face.")]
    public bool drawDisplayName = true;

    [Header("Baked Output (set by the baker)")]
    public int bakeResolution = 1024;
    public Texture2D bakedFace;
    public Material bakedFaceMaterial;

    // Value -> needle angle (degrees, 0 = 12 o'clock, clockwise). Clamped.
    public float ValueToAngle(float value)
    {
        float t = Mathf.InverseLerp(minValue, maxValue, value);
        return Mathf.Lerp(startAngle, endAngle, t);
    }

    // Right-click the asset in Project → Generate New ID
    [ContextMenu("Generate New ID")]
    private void GenerateId() => _id = System.Guid.NewGuid().ToString();
}
