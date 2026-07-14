// GaugeFaceBaker.cs
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

// Bakes a GaugeDefinition into a dial-face texture (PNG saved next to the
// definition asset) plus an HDRP/Lit material that uses it, and links both
// back into the definition. No cameras or scene objects are involved: the
// ticks/bands/labels are built as meshes and rendered straight into a
// RenderTexture with a CommandBuffer, so the bake can't be polluted by
// scene lighting or geometry.
public static class GaugeFaceBaker
{
    public static void Bake(GaugeDefinition def)
    {
        if (def.maxValue <= def.minValue || def.majorTickInterval <= 0f)
        {
            Debug.LogError($"[GaugeFaceBaker] '{def.name}': maxValue must exceed minValue and majorTickInterval must be positive.");
            return;
        }

        int size = Mathf.Clamp(def.bakeResolution, 128, 4096);
        float radius = size * 0.5f;
        Vector2 center = new Vector2(radius, radius);

        Font font = def.labelFont != null
            ? def.labelFont
            : Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

        float labelPx = def.labelSize * radius;
        float textPx = def.textSize * radius;

        int majorCount = Mathf.FloorToInt((def.maxValue - def.minValue) / def.majorTickInterval + 1e-4f);

        // --- Geometry (bands + ticks), vertex-colored, no texture ---
        var geo = new MeshBuilder();

        foreach (var band in def.bands)
        {
            float a0 = def.ValueToAngle(band.fromValue);
            float a1 = def.ValueToAngle(band.toValue);
            int segments = Mathf.Max(1, Mathf.CeilToInt(Mathf.Abs(a1 - a0) / 1.5f));
            for (int s = 0; s < segments; s++)
            {
                float sa = Mathf.Lerp(a0, a1, s / (float)segments);
                float sb = Mathf.Lerp(a0, a1, (s + 1) / (float)segments);
                geo.Quad(
                    center + Dir(sa) * (def.bandInnerRadius * radius), Vector2.zero,
                    center + Dir(sa) * (def.bandOuterRadius * radius), Vector2.zero,
                    center + Dir(sb) * (def.bandOuterRadius * radius), Vector2.zero,
                    center + Dir(sb) * (def.bandInnerRadius * radius), Vector2.zero,
                    band.color.linear);
            }
        }

        float minorStep = def.majorTickInterval / (def.minorTicksPerMajor + 1);
        for (int i = 0; i <= majorCount; i++)
        {
            float v = def.minValue + i * def.majorTickInterval;
            AddTick(geo, def, center, radius, def.ValueToAngle(v),
                def.majorTickLength, def.majorTickWidth);

            if (i == majorCount) break;
            for (int j = 1; j <= def.minorTicksPerMajor; j++)
                AddTick(geo, def, center, radius, def.ValueToAngle(v + j * minorStep),
                    def.minorTickLength, def.minorTickWidth);
        }

        // --- Text (labels + name + units), textured with the font atlas ---
        // Request every glyph up front (twice: a mid-request atlas rebuild
        // could otherwise evict glyphs requested at the other size).
        var labelText = new StringBuilder();
        for (int i = 0; i <= majorCount; i++)
            labelText.Append(LabelFor(def, i));
        string headerText = (def.drawDisplayName ? def.displayName : "") + def.units;
        for (int pass = 0; pass < 2; pass++)
        {
            RequestGlyphs(font, labelText.ToString(), labelPx);
            RequestGlyphs(font, headerText, textPx);
        }

        var text = new MeshBuilder();
        Color textColor = def.markingColor.linear;
        for (int i = 0; i <= majorCount; i++)
        {
            float v = def.minValue + i * def.majorTickInterval;
            Vector2 pos = center + Dir(def.ValueToAngle(v)) * (def.labelRadius * radius);
            DrawString(text, font, LabelFor(def, i), labelPx, pos, textColor);
        }
        if (def.drawDisplayName)
            DrawString(text, font, def.displayName, textPx, center + new Vector2(0f, 0.30f * radius), textColor);
        DrawString(text, font, def.units, textPx, center + new Vector2(0f, -0.30f * radius), textColor);

        // --- Render both meshes into a RenderTexture and read back ---
        var colorMat = new Material(Shader.Find("Hidden/Internal-Colored")) { hideFlags = HideFlags.HideAndDontSave };
        colorMat.SetInt("_SrcBlend", (int)BlendMode.SrcAlpha);
        colorMat.SetInt("_DstBlend", (int)BlendMode.OneMinusSrcAlpha);
        colorMat.SetInt("_Cull", (int)CullMode.Off);
        colorMat.SetInt("_ZWrite", 0);
        colorMat.SetInt("_ZTest", (int)CompareFunction.Always);

        var rt = new RenderTexture(size, size, 0, RenderTextureFormat.ARGB32, RenderTextureReadWrite.sRGB)
        {
            antiAliasing = 8
        };
        rt.Create();

        Mesh geoMesh = geo.Build();
        Mesh textMesh = text.Build();

        var cb = new CommandBuffer { name = "Bake Gauge Face" };
        cb.SetRenderTarget(rt);
        cb.ClearRenderTarget(true, true, def.faceColor.linear);
        Matrix4x4 proj = Matrix4x4.Ortho(0f, size, 0f, size, -100f, 100f);
        cb.SetViewProjectionMatrices(Matrix4x4.identity, GL.GetGPUProjectionMatrix(proj, true));
        cb.DrawMesh(geoMesh, Matrix4x4.identity, colorMat);
        cb.DrawMesh(textMesh, Matrix4x4.identity, font.material); // GUI/Text shader, tinted by vertex color
        Graphics.ExecuteCommandBuffer(cb);
        cb.Release();

        var prevActive = RenderTexture.active;
        RenderTexture.active = rt;
        var baked = new Texture2D(size, size, TextureFormat.RGBA32, false);
        baked.ReadPixels(new Rect(0f, 0f, size, size), 0, 0);
        baked.Apply();
        RenderTexture.active = prevActive;

        byte[] png = baked.EncodeToPNG();

        Object.DestroyImmediate(geoMesh);
        Object.DestroyImmediate(textMesh);
        Object.DestroyImmediate(colorMat);
        Object.DestroyImmediate(baked);
        rt.Release();
        Object.DestroyImmediate(rt);

        // --- Save PNG + material next to the definition, link them back ---
        string dir = Path.GetDirectoryName(AssetDatabase.GetAssetPath(def)).Replace('\\', '/');
        string texPath = $"{dir}/{def.name}_Face.png";
        File.WriteAllBytes(texPath, png);
        AssetDatabase.ImportAsset(texPath);

        var importer = (TextureImporter)AssetImporter.GetAtPath(texPath);
        if (importer.maxTextureSize < size)
        {
            importer.maxTextureSize = Mathf.NextPowerOfTwo(size);
            importer.SaveAndReimport();
        }
        var faceTex = AssetDatabase.LoadAssetAtPath<Texture2D>(texPath);

        string matPath = $"{dir}/{def.name}_Face.mat";
        var mat = AssetDatabase.LoadAssetAtPath<Material>(matPath);
        if (mat == null)
        {
            mat = new Material(Shader.Find("HDRP/Lit"));
            AssetDatabase.CreateAsset(mat, matPath);
        }
        mat.SetTexture("_BaseColorMap", faceTex);
        mat.SetFloat("_Smoothness", 0.25f);
        HDMaterial.ValidateMaterial(mat);
        EditorUtility.SetDirty(mat);

        var so = new SerializedObject(def);
        so.FindProperty("bakedFace").objectReferenceValue = faceTex;
        so.FindProperty("bakedFaceMaterial").objectReferenceValue = mat;
        so.ApplyModifiedPropertiesWithoutUndo();
        AssetDatabase.SaveAssets();

        Debug.Log($"[GaugeFaceBaker] Baked '{def.name}' → {texPath}");
    }

    // Direction of a dial angle in y-up pixel space (0 = up, clockwise positive).
    private static Vector2 Dir(float angleDeg)
    {
        float rad = angleDeg * Mathf.Deg2Rad;
        return new Vector2(Mathf.Sin(rad), Mathf.Cos(rad));
    }

    private static string LabelFor(GaugeDefinition def, int majorIndex)
    {
        float v = (def.minValue + majorIndex * def.majorTickInterval) * def.labelMultiplier;
        return v.ToString(def.labelFormat);
    }

    private static void AddTick(MeshBuilder mb, GaugeDefinition def, Vector2 center,
        float radius, float angle, float lengthFrac, float widthFrac)
    {
        Vector2 dir = Dir(angle);
        Vector2 perp = new Vector2(dir.y, -dir.x) * (widthFrac * radius * 0.5f);
        Vector2 outer = center + dir * (def.tickOuterRadius * radius);
        Vector2 inner = center + dir * ((def.tickOuterRadius - lengthFrac) * radius);
        mb.Quad(inner - perp, Vector2.zero, inner + perp, Vector2.zero,
                outer + perp, Vector2.zero, outer - perp, Vector2.zero,
                def.markingColor.linear);
    }

    private static void RequestGlyphs(Font font, string s, float px)
    {
        if (font.dynamic && !string.IsNullOrEmpty(s))
            font.RequestCharactersInTexture(s, Mathf.RoundToInt(px));
    }

    // Lays a string out as font-atlas quads, centred on `center` (both axes).
    private static void DrawString(MeshBuilder mb, Font font, string s, float px,
        Vector2 center, Color color)
    {
        if (string.IsNullOrEmpty(s)) return;

        // Non-dynamic fonts only expose glyphs at their import size — scale those.
        int reqSize = font.dynamic ? Mathf.RoundToInt(px) : 0;
        float scale = font.dynamic ? 1f : px / Mathf.Max(1, font.fontSize);

        float width = 0f, minY = float.MaxValue, maxY = float.MinValue;
        foreach (char ch in s)
        {
            if (!font.GetCharacterInfo(ch, out CharacterInfo ci, reqSize)) continue;
            width += ci.advance * scale;
            if (ch != ' ')
            {
                minY = Mathf.Min(minY, ci.minY * scale);
                maxY = Mathf.Max(maxY, ci.maxY * scale);
            }
        }
        if (minY > maxY) return; // nothing printable

        float x = center.x - width * 0.5f;
        float baseline = center.y - (minY + maxY) * 0.5f;

        foreach (char ch in s)
        {
            if (!font.GetCharacterInfo(ch, out CharacterInfo ci, reqSize)) continue;
            if (ch != ' ')
            {
                mb.Quad(
                    new Vector2(x + ci.minX * scale, baseline + ci.minY * scale), ci.uvBottomLeft,
                    new Vector2(x + ci.maxX * scale, baseline + ci.minY * scale), ci.uvBottomRight,
                    new Vector2(x + ci.maxX * scale, baseline + ci.maxY * scale), ci.uvTopRight,
                    new Vector2(x + ci.minX * scale, baseline + ci.maxY * scale), ci.uvTopLeft,
                    color);
            }
            x += ci.advance * scale;
        }
    }

    private class MeshBuilder
    {
        private readonly List<Vector3> _vertices = new List<Vector3>();
        private readonly List<Vector2> _uvs = new List<Vector2>();
        private readonly List<Color> _colors = new List<Color>();
        private readonly List<int> _triangles = new List<int>();

        public void Quad(Vector2 a, Vector2 uvA, Vector2 b, Vector2 uvB,
                         Vector2 c, Vector2 uvC, Vector2 d, Vector2 uvD, Color color)
        {
            int i = _vertices.Count;
            _vertices.Add(a); _vertices.Add(b); _vertices.Add(c); _vertices.Add(d);
            _uvs.Add(uvA); _uvs.Add(uvB); _uvs.Add(uvC); _uvs.Add(uvD);
            for (int n = 0; n < 4; n++) _colors.Add(color);
            _triangles.Add(i); _triangles.Add(i + 1); _triangles.Add(i + 2);
            _triangles.Add(i); _triangles.Add(i + 2); _triangles.Add(i + 3);
        }

        public Mesh Build()
        {
            var mesh = new Mesh { indexFormat = UnityEngine.Rendering.IndexFormat.UInt32 };
            mesh.SetVertices(_vertices);
            mesh.SetUVs(0, _uvs);
            mesh.SetColors(_colors);
            mesh.SetTriangles(_triangles, 0);
            return mesh;
        }
    }
}

[CustomEditor(typeof(GaugeDefinition))]
[CanEditMultipleObjects]
public class GaugeDefinitionEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();
        EditorGUILayout.Space();

        if (GUILayout.Button("Bake Dial Face", GUILayout.Height(28)))
            foreach (var t in targets)
                GaugeFaceBaker.Bake((GaugeDefinition)t);

        var def = (GaugeDefinition)target;
        if (targets.Length == 1 && def.bakedFace != null)
        {
            EditorGUILayout.Space();
            Rect rect = GUILayoutUtility.GetAspectRect(1f);
            EditorGUI.DrawPreviewTexture(rect, def.bakedFace);
        }
    }
}
