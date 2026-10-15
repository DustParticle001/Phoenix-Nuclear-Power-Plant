// BarGaugeFaceBaker.cs
using System.Text;
using UnityEditor;
using UnityEngine;
using MeshBuilder = GaugeFaceBaker.MeshBuilder;

// Bakes a BarGaugeDefinition into a tall face texture: horizontal ticks down a
// vertical scale, labels to the right of them, the display name above and the
// units below. Rendering, saving and material setup are shared with the round
// dial baker (GaugeFaceBaker); only the layout differs.
//
// Pixel space is y-up with the image covering the whole face, top row = top of
// the face; the definition's tiling/offset map it onto the face UVs.
public static class BarGaugeFaceBaker
{
    public static void Bake(BarGaugeDefinition def)
    {
        if (def.maxValue <= def.minValue || def.majorTickInterval <= 0f)
        {
            Debug.LogError($"[BarGaugeFaceBaker] '{def.name}': maxValue must exceed minValue and majorTickInterval must be positive.");
            return;
        }
        if (def.faceAspect <= 0f)
        {
            Debug.LogError($"[BarGaugeFaceBaker] '{def.name}': faceAspect must be positive.");
            return;
        }

        // bakeResolution is the long (vertical) side.
        int height = Mathf.Clamp(def.bakeResolution, 128, 8192);
        int width = Mathf.Max(16, Mathf.RoundToInt(height / def.faceAspect));

        Font font = def.labelFont != null
            ? def.labelFont
            : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        float labelPx = def.barLabelSize * width;
        float textPx = def.barTextSize * width;

        int majorCount = Mathf.FloorToInt((def.maxValue - def.minValue) / def.majorTickInterval + 1e-4f);

        float X(float frac) => frac * width;
        float Y(float value) => (1f - def.ValueToFraction(value)) * height;

        // --- Geometry (bands, spine, ticks), vertex-colored ---
        var geo = new MeshBuilder();
        Color mark = def.markingColor.linear;

        foreach (var band in def.bands)
            Rect(geo, X(def.bandLeft), Y(band.fromValue),
                      X(def.bandLeft + def.bandWidth), Y(band.toValue), band.color.linear);

        if (def.spineWidth > 0f)
        {
            float half = def.barMajorTickWidth * width * 0.5f; // square the spine off with the end ticks
            Rect(geo, X(def.tickEdge), Y(def.minValue) - half,
                      X(def.tickEdge + def.spineWidth), Y(def.maxValue) + half, mark);
        }

        float minorStep = def.majorTickInterval / (def.minorTicksPerMajor + 1);
        for (int i = 0; i <= majorCount; i++)
        {
            float v = def.minValue + i * def.majorTickInterval;
            Tick(geo, X(def.tickEdge), Y(v), def.barMajorTickLength * width, def.barMajorTickWidth * width, mark);

            if (i == majorCount) break;
            for (int j = 1; j <= def.minorTicksPerMajor; j++)
                Tick(geo, X(def.tickEdge), Y(v + j * minorStep),
                    def.barMinorTickLength * width, def.barMinorTickWidth * width, mark);
        }

        // --- Text: labels beside the major ticks, name above, units below ---
        string name = def.drawDisplayName ? def.displayName : "";
        var labels = new string[majorCount + 1];
        var labelText = new StringBuilder();
        for (int i = 0; i <= majorCount; i++)
        {
            labels[i] = ((def.minValue + i * def.majorTickInterval) * def.labelMultiplier).ToString(def.labelFormat);
            labelText.Append(labels[i]);
        }

        // Name/units shrink to fit the face width; measure at the requested
        // size, then request the (smaller) fitted sizes too.
        float maxTextWidth = width * 0.92f;
        for (int pass = 0; pass < 2; pass++)
        {
            GaugeFaceBaker.RequestGlyphs(font, labelText.ToString(), labelPx);
            GaugeFaceBaker.RequestGlyphs(font, name + def.units, textPx);
        }
        float namePx = Fit(font, name, textPx, maxTextWidth);
        float unitsPx = Fit(font, def.units, textPx, maxTextWidth);
        for (int pass = 0; pass < 2; pass++)
        {
            GaugeFaceBaker.RequestGlyphs(font, labelText.ToString(), labelPx);
            GaugeFaceBaker.RequestGlyphs(font, name, namePx);
            GaugeFaceBaker.RequestGlyphs(font, def.units, unitsPx);
        }

        var text = new MeshBuilder();
        for (int i = 0; i <= majorCount; i++)
        {
            float v = def.minValue + i * def.majorTickInterval;
            GaugeFaceBaker.DrawString(text, font, labels[i], labelPx, new Vector2(X(def.labelCenter), Y(v)), mark);
        }
        float centerX = width * 0.5f;
        GaugeFaceBaker.DrawString(text, font, name, namePx,
            new Vector2(centerX, (1f - def.scaleTop * 0.5f) * height), mark);
        GaugeFaceBaker.DrawString(text, font, def.units, unitsPx,
            new Vector2(centerX, (1f - (1f + def.scaleBottom) * 0.5f) * height), mark);

        Color32[] pixels = GaugeFaceBaker.Render(width, height, def.faceColor, geo, text, font);
        GaugeFaceBaker.Save(def, GaugeFaceBaker.EncodePng(width, height, pixels), height);
    }

    private static float Fit(Font font, string s, float px, float maxWidth)
    {
        float w = GaugeFaceBaker.MeasureString(font, s, px);
        return w > maxWidth ? px * maxWidth / w : px;
    }

    // Horizontal tick running right from (x, y), centred on y.
    private static void Tick(MeshBuilder mb, float x, float y, float length, float thickness, Color color) =>
        Rect(mb, x, y - thickness * 0.5f, x + length, y + thickness * 0.5f, color);

    private static void Rect(MeshBuilder mb, float x0, float y0, float x1, float y1, Color color) =>
        mb.Quad(new Vector2(x0, y0), Vector2.zero, new Vector2(x1, y0), Vector2.zero,
                new Vector2(x1, y1), Vector2.zero, new Vector2(x0, y1), Vector2.zero, color);

    // Measures a face submesh: its UV bounds, and its physical height/width
    // ratio (world length per UV unit along V vs U, averaged over triangles
    // weighted by UV area) so the baked texels come out square on the model.
    public static bool FitFromMesh(Mesh mesh, int submesh, out Vector2 uvMin, out Vector2 uvMax, out float aspect)
    {
        uvMin = uvMax = Vector2.zero;
        aspect = 0f;
        if (mesh == null || submesh < 0 || submesh >= mesh.subMeshCount) return false;

        Vector3[] verts = mesh.vertices;
        Vector2[] uvs = mesh.uv;
        int[] tris = mesh.GetTriangles(submesh);
        if (uvs.Length != verts.Length || tris.Length == 0) return false;

        uvMin = new Vector2(float.MaxValue, float.MaxValue);
        uvMax = new Vector2(float.MinValue, float.MinValue);
        double duSum = 0, dvSum = 0, weight = 0;
        for (int t = 0; t < tris.Length; t += 3)
        {
            int a = tris[t], b = tris[t + 1], c = tris[t + 2];
            foreach (int i in new[] { a, b, c })
            {
                uvMin = Vector2.Min(uvMin, uvs[i]);
                uvMax = Vector2.Max(uvMax, uvs[i]);
            }

            Vector3 e1 = verts[b] - verts[a], e2 = verts[c] - verts[a];
            Vector2 d1 = uvs[b] - uvs[a], d2 = uvs[c] - uvs[a];
            float det = d1.x * d2.y - d2.x * d1.y;
            if (Mathf.Abs(det) < 1e-9f) continue;
            Vector3 dPdu = (e1 * d2.y - e2 * d1.y) / det;
            Vector3 dPdv = (e2 * d1.x - e1 * d2.x) / det;
            float w = Mathf.Abs(det);
            duSum += dPdu.magnitude * w;
            dvSum += dPdv.magnitude * w;
            weight += w;
        }
        if (weight <= 0 || duSum <= 0) return false;

        float physW = (uvMax.x - uvMin.x) * (float)(duSum / weight);
        float physH = (uvMax.y - uvMin.y) * (float)(dvSum / weight);
        aspect = physH / physW;
        return true;
    }
}

[CustomEditor(typeof(BarGaugeDefinition))]
[CanEditMultipleObjects]
public class BarGaugeDefinitionEditor : Editor
{
    // Round-dial fields that don't apply, or that OnValidate derives.
    private static readonly string[] Hidden =
    {
        "m_Script", "startAngle", "endAngle",
        "tickOuterRadius", "majorTickLength", "minorTickLength", "majorTickWidth", "minorTickWidth",
        "labelRadius", "labelSize", "textSize", "bandOuterRadius", "bandInnerRadius",
        "bakeRotation", "materialTiling", "materialOffset",
    };

    private Mesh _fitMesh;
    private int _fitSubmesh = 1;

    public override void OnInspectorGUI()
    {
        serializedObject.Update();
        DrawPropertiesExcluding(serializedObject, Hidden);
        serializedObject.ApplyModifiedProperties();

        var def = (BarGaugeDefinition)target;

        EditorGUILayout.Space();
        using (new EditorGUI.DisabledScope(true))
        {
            EditorGUILayout.FloatField("Derived Start Angle", def.startAngle);
            EditorGUILayout.FloatField("Derived End Angle", def.endAngle);
            EditorGUILayout.Vector2Field("Derived Tiling", def.materialTiling);
            EditorGUILayout.Vector2Field("Derived Offset", def.materialOffset);
        }

        EditorGUILayout.Space();
        EditorGUILayout.LabelField("Fit From Mesh", EditorStyles.boldLabel);
        _fitMesh = (Mesh)EditorGUILayout.ObjectField("Body Mesh", _fitMesh, typeof(Mesh), false);
        _fitSubmesh = EditorGUILayout.IntField("Face Submesh", _fitSubmesh);
        using (new EditorGUI.DisabledScope(_fitMesh == null))
        {
            if (GUILayout.Button("Fit UV Rect + Aspect"))
            {
                if (BarGaugeFaceBaker.FitFromMesh(_fitMesh, _fitSubmesh, out var uvMin, out var uvMax, out float aspect))
                {
                    foreach (var t in targets)
                    {
                        var so = new SerializedObject(t);
                        so.FindProperty("faceUvMin").vector2Value = uvMin;
                        so.FindProperty("faceUvMax").vector2Value = uvMax;
                        so.FindProperty("faceAspect").floatValue = aspect;
                        so.ApplyModifiedProperties(); // triggers OnValidate -> tiling
                    }
                    Debug.Log($"[BarGaugeFaceBaker] Fitted UV {uvMin} .. {uvMax}, aspect {aspect:0.###}");
                }
                else
                {
                    Debug.LogError("[BarGaugeFaceBaker] Couldn't fit: check the mesh has UVs and the submesh index exists.");
                }
            }
        }

        EditorGUILayout.Space();
        if (GUILayout.Button("Bake Bar Face", GUILayout.Height(28)))
            foreach (var t in targets)
                BarGaugeFaceBaker.Bake((BarGaugeDefinition)t);

        if (targets.Length == 1 && def.bakedFace != null)
        {
            EditorGUILayout.Space();
            float aspect = def.bakedFace.height / (float)Mathf.Max(1, def.bakedFace.width);
            float h = Mathf.Min(512f, EditorGUIUtility.currentViewWidth * aspect);
            Rect rect = GUILayoutUtility.GetRect(h / aspect, h, GUILayout.ExpandWidth(false));
            rect.x = (EditorGUIUtility.currentViewWidth - rect.width) * 0.5f;
            EditorGUI.DrawPreviewTexture(rect, def.bakedFace);
        }
    }
}
