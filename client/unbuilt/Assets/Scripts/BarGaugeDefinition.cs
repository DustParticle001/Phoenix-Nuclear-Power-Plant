// BarGaugeDefinition.cs
using UnityEngine;

// A vertical bar (edgewise) gauge: a pointer swings a short arc behind a tall,
// narrow face curved around the pointer's pivot, so the face reads as a straight
// vertical scale. The editor baker (Editor/BarGaugeFaceBaker.cs) prints the scale
// as horizontal ticks down the face.
//
// It is still a GaugeDefinition, so GaugeNeedle, IoSync and the template
// lookups work unchanged: startAngle/endAngle and the material tiling are
// derived here from the face geometry below (see OnValidate) instead of being
// typed in, which keeps the pointer and the printed ticks in agreement.
//
// Face coordinates: fractions of the face, 0 = top / pointer-side edge,
// 1 = bottom / far edge. The pointer comes in from the left.
[CreateAssetMenu(fileName = "BarGaugeDef_New", menuName = "NPP/Bar Gauge Definition")]
public class BarGaugeDefinition : GaugeDefinition
{
    [Header("Face Geometry (from the model)")]
    [Tooltip("UV bounds of the face submesh, in the model's raw UV units. Use \"Fit From Mesh\" " +
             "in the inspector rather than typing these. Defaults match bar-gauge.fbx.")]
    public Vector2 faceUvMin = new Vector2(-4.6f, 0.2922f);
    public Vector2 faceUvMax = new Vector2(-0.4f, 21.4667f);
    [Tooltip("Mirror the image left/right on the face - set when U runs away from the pointer side.")]
    public bool flipU = true;
    [Tooltip("Mirror the image top/bottom on the face - set when V runs downwards.")]
    public bool flipV = true;
    [Tooltip("Physical face height / width, so text isn't stretched. \"Fit From Mesh\" measures it.")]
    public float faceAspect = 4.887f;
    [Tooltip("Angle the face spans around the pointer pivot, top edge to bottom edge. " +
             "bar-gauge.fbx: a 17 mm radius arc over +/-34.58 deg.")]
    public float faceArcDegrees = 69.16f;

    [Header("Scale Layout (fractions of the face)")]
    [Tooltip("Where maxValue sits, from the top of the face.")]
    [Range(0f, 1f)] public float scaleTop = 0.07f;
    [Tooltip("Where minValue sits, from the top of the face.")]
    [Range(0f, 1f)] public float scaleBottom = 0.93f;
    [Tooltip("Pointer-side edge of the ticks, from the left. The fbx pointer tip reaches 0.24.")]
    [Range(0f, 1f)] public float tickEdge = 0.25f;
    [Tooltip("Tick lengths and thicknesses, as fractions of the face WIDTH.")]
    public float barMajorTickLength = 0.22f;
    public float barMinorTickLength = 0.12f;
    public float barMajorTickWidth = 0.022f;
    public float barMinorTickWidth = 0.011f;
    [Tooltip("Vertical line joining the ticks along their pointer-side edge. 0 = none.")]
    public float spineWidth = 0.015f;
    [Tooltip("Horizontal centre of the number labels, from the left.")]
    [Range(0f, 1f)] public float labelCenter = 0.72f;
    [Tooltip("Label height, as a fraction of the face width.")]
    public float barLabelSize = 0.2f;
    [Tooltip("Display name (above the scale) / units (below) height, as a fraction of the " +
             "face width. Shrinks to fit when the text is too wide.")]
    public float barTextSize = 0.17f;
    [Tooltip("Color bands run as a vertical strip starting at this edge...")]
    [Range(0f, 1f)] public float bandLeft = 0.25f;
    [Tooltip("...this wide (fraction of face width).")]
    public float bandWidth = 0.1f;

    // Fraction down the face -> pointer angle. Top of the face is negative:
    // with the template's +X rotation axis a positive angle swings downward.
    public float FractionToAngle(float fromTop) => (fromTop - 0.5f) * faceArcDegrees;

    // Value -> fraction down the face (linear, clamped).
    public float ValueToFraction(float value) =>
        Mathf.Lerp(scaleBottom, scaleTop, Mathf.InverseLerp(minValue, maxValue, value));

    private void Reset()
    {
        bakeResolution = 2048;
        bakeRotation = FaceRotation.None;
        drawDisplayName = true;
        OnValidate();
    }

    private void OnValidate()
    {
        // The face UVs are (to within ~0.2 deg on the fbx) linear in pivot
        // angle, so a linear scale on the texture is a linear sweep.
        startAngle = FractionToAngle(scaleBottom);
        endAngle = FractionToAngle(scaleTop);

        // Map the face's raw UV rect onto the whole 0..1 image.
        float w = faceUvMax.x - faceUvMin.x;
        float h = faceUvMax.y - faceUvMin.y;
        if (Mathf.Abs(w) < 1e-6f || Mathf.Abs(h) < 1e-6f) return;
        materialTiling = new Vector2(flipU ? -1f / w : 1f / w, flipV ? -1f / h : 1f / h);
        materialOffset = new Vector2(
            flipU ? faceUvMax.x / w : -faceUvMin.x / w,
            flipV ? faceUvMax.y / h : -faceUvMin.y / h);
    }
}
