// AnnunciatorRackBuilder.cs
using System.Collections.Generic;
using TMPro;
using UnityEditor;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.HighDefinition;

// Builds the model for an annunciator rack out of its definition: the frame
// mesh with a socket cut for every window, one lens mesh shared by all of them,
// the HDRP materials each lens colour needs lit and dark, a legend per window,
// and a prefab holding it all together.
//
// Nothing is modelled by hand, so the rack is only ever as described: change
// the size or the grid, re-import a CSV, press Build, and the model, the
// materials and every instance of the prefab follow. Uids survive a rebuild
// (they live in the definition), so a rack keeps its identity on the server
// however often it is rebuilt.
//
// Assets are written beside the definition, the way the gauge face baker does
// it: meshes/ and materials/ subfolders, and the prefab next to the asset.
// Existing assets are rewritten in place rather than replaced, so their GUIDs
// hold and scenes already using them keep working.
//
// Geometry: the face lies in the XY plane looking down +Z, origin in the middle
// of the face, and the box runs back into -Z. Row 0 is the top row, and column 0
// is the leftmost as the face is read - which is the +x end, because a viewer
// looking down -Z has local +X on their left.
public static class AnnunciatorRackBuilder
{
    // Faces thinner than this are dropped rather than drawn as slivers.
    private const float Epsilon = 1e-5f;

    // TextMeshPro in world space behaves better at sane font sizes than at
    // fractions of one, so the legend object is scaled down instead - same
    // trick the project's label prefabs use.
    private const float LegendScale = 0.001f;

    // How far in front of the lens the legend sits.
    private const float LegendOffset = 0.0015f;

    // ------------------------------------------------------------------ build

    // Writes meshes, materials and the prefab. Returns the prefab, or null if
    // the definition can't be built.
    public static GameObject BuildPrefab(AnnunciatorRackDefinition definition)
    {
        if (!Prepare(definition, out Parts parts))
            return null;

        GameObject root = new GameObject(definition.name);
        Populate(root, definition, parts);

        string prefabPath = $"{AssetFolder(definition)}/{definition.name}.prefab";
        GameObject prefab = PrefabUtility.SaveAsPrefabAsset(root, prefabPath, out bool saved);
        Object.DestroyImmediate(root);

        if (!saved || prefab == null)
        {
            Debug.LogError($"[AnnunciatorRackBuilder] couldn't save the prefab at {prefabPath}.");
            return null;
        }

        definition.generatedPrefab = prefab;
        definition.bodyMesh = parts.Body;
        definition.lensMesh = parts.Lens;
        EditorUtility.SetDirty(definition);
        AssetDatabase.SaveAssets();

        Debug.Log($"[AnnunciatorRackBuilder] built '{definition.name}': " +
                  $"{definition.cellsX} x {definition.cellsY} = {parts.WindowCount} window(s), " +
                  $"{parts.MaterialCount} material(s) -> {prefabPath}");
        return prefab;
    }

    // Rebuilds a rack that is already in a scene, in place. For a rack that is
    // a prefab instance, rebuild the prefab instead - every instance follows.
    public static bool RebuildInScene(AnnunciatorRack rack)
    {
        if (rack == null || rack.Definition == null)
        {
            Debug.LogError("[AnnunciatorRackBuilder] this rack has no definition to build from.");
            return false;
        }

        if (!Prepare(rack.Definition, out Parts parts))
            return false;

        Undo.RegisterFullObjectHierarchyUndo(rack.gameObject, "Rebuild Annunciator Rack");

        for (int i = rack.transform.childCount - 1; i >= 0; i--)
            Undo.DestroyObjectImmediate(rack.transform.GetChild(i).gameObject);

        Populate(rack.gameObject, rack.Definition, parts);
        EditorUtility.SetDirty(rack);
        return true;
    }

    // Meshes and materials, ready to hang a hierarchy off.
    private class Parts
    {
        public Mesh Body;
        public Mesh Lens;
        public Material Frame;
        public Dictionary<AnnunciatorRackDefinition.TileColor, Material> Lit;
        public Dictionary<AnnunciatorRackDefinition.TileColor, Material> Unlit;
        public int WindowCount;
        public int MaterialCount;
    }

    private static bool Prepare(AnnunciatorRackDefinition definition, out Parts parts)
    {
        parts = null;

        if (definition == null)
            return false;

        if (!definition.Validate(out string error))
        {
            Debug.LogError($"[AnnunciatorRackBuilder] '{definition.name}': {error}");
            return false;
        }

        // Fills the tile array out to the grid and gives every new window a uid.
        AnnunciatorCsv.EnsureTiles(definition);

        string meshFolder = EnsureFolder(AssetFolder(definition), "meshes");

        parts = new Parts
        {
            Body = EnsureMesh($"{meshFolder}/{definition.name} Body.asset",
                              BuildBodyMesh(definition), $"{definition.name} Body"),
            Lens = EnsureMesh($"{meshFolder}/{definition.name} Lens.asset",
                              BuildLensMesh(definition), $"{definition.name} Lens"),
        };

        BuildMaterials(definition, parts);
        return true;
    }

    // ----------------------------------------------------------------- meshes

    // The frame: the face with a hole where each window goes, a socket behind
    // every hole, and the sides and back that close the box.
    private static Mesh BuildBodyMesh(AnnunciatorRackDefinition definition)
    {
        var mesh = new MeshBuilder();

        float halfWidth = definition.width * 0.5f;
        float halfHeight = definition.height * 0.5f;
        float cellWidth = definition.CellWidth;
        float cellHeight = definition.CellHeight;

        // Boundaries down each axis, alternating frame span / window span, so
        // the face is a grid of rectangles and a window is simply the one that
        // doesn't get drawn.
        //
        // Spans are counted from -x; columns are counted from the reader's left,
        // which is +x (see CellCenter). Taking the boundaries from CellCenter
        // rather than laying them out again is what keeps the frame from ever
        // disagreeing with where the windows were put.
        var xs = new float[2 * definition.cellsX + 2];
        xs[0] = -halfWidth;
        for (int column = 0; column < definition.cellsX; column++)
        {
            int slot = SlotOfColumn(definition, column);
            float center = definition.CellCenter(0, column).x;
            xs[2 * slot + 1] = center - cellWidth * 0.5f;
            xs[2 * slot + 2] = center + cellWidth * 0.5f;
        }
        xs[xs.Length - 1] = halfWidth;

        var ys = new float[2 * definition.cellsY + 2];
        ys[0] = halfHeight;
        for (int row = 0; row < definition.cellsY; row++)
        {
            float top = halfHeight - definition.bezelMargin
                        - row * (cellHeight + definition.ribWidth);
            ys[2 * row + 1] = top;
            ys[2 * row + 2] = top - cellHeight;
        }
        ys[ys.Length - 1] = -halfHeight;

        // Face.
        for (int i = 0; i < xs.Length - 1; i++)
        {
            for (int j = 0; j < ys.Length - 1; j++)
            {
                if (i % 2 == 1 && j % 2 == 1
                    && IsOpen(definition, (j - 1) / 2, ColumnOfSpan(definition, i)))
                    continue;   // a window opening - the lens shows through here

                Face(mesh, xs[i], xs[i + 1], ys[j + 1], ys[j], 0f, Vector3.forward);
            }
        }

        // Sockets: the four walls between the face and the lens behind it.
        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                if (!IsOpen(definition, row, column))
                    continue;

                int slot = SlotOfColumn(definition, column);
                float x0 = xs[2 * slot + 1];
                float x1 = xs[2 * slot + 2];
                float y1 = ys[2 * row + 1];
                float y0 = ys[2 * row + 2];
                float back = -definition.lensRecess;

                // Normals point into the socket - that's the only side of these
                // walls anybody ever sees.
                WallX(mesh, x0, y0, y1, 0f, back, Vector3.right);
                WallX(mesh, x1, y0, y1, 0f, back, Vector3.left);
                WallY(mesh, y1, x0, x1, 0f, back, Vector3.down);
                WallY(mesh, y0, x0, x1, 0f, back, Vector3.up);
            }
        }

        // The box itself.
        WallX(mesh, -halfWidth, -halfHeight, halfHeight, 0f, -definition.depth, Vector3.left);
        WallX(mesh, halfWidth, -halfHeight, halfHeight, 0f, -definition.depth, Vector3.right);
        WallY(mesh, halfHeight, -halfWidth, halfWidth, 0f, -definition.depth, Vector3.up);
        WallY(mesh, -halfHeight, -halfWidth, halfWidth, 0f, -definition.depth, Vector3.down);
        Face(mesh, -halfWidth, halfWidth, -halfHeight, halfHeight, -definition.depth, Vector3.back);

        return mesh.Build();
    }

    // One window's lens: a plate the size of a cell, facing out of its socket.
    // Every window shares it - they're all the same size - and only the
    // material differs.
    private static Mesh BuildLensMesh(AnnunciatorRackDefinition definition)
    {
        var mesh = new MeshBuilder();
        float halfWidth = definition.CellWidth * 0.5f;
        float halfHeight = definition.CellHeight * 0.5f;

        Face(mesh, -halfWidth, halfWidth, -halfHeight, halfHeight, 0f, Vector3.forward);
        return mesh.Build();
    }

    // Where a column sits counting from -x, and the way back from a span index
    // to the column it holds.
    private static int SlotOfColumn(AnnunciatorRackDefinition definition, int column) =>
        definition.cellsX - 1 - column;

    private static int ColumnOfSpan(AnnunciatorRackDefinition definition, int spanIndex) =>
        definition.cellsX - 1 - (spanIndex - 1) / 2;

    private static bool IsOpen(AnnunciatorRackDefinition definition, int row, int column)
    {
        AnnunciatorRackDefinition.Tile tile = definition.TileAt(row, column);
        return tile != null && !tile.blank;
    }

    private static void Face(MeshBuilder mesh, float x0, float x1, float y0, float y1,
                             float z, Vector3 facing)
    {
        if (x1 - x0 <= Epsilon || y1 - y0 <= Epsilon)
            return;   // no bezel or no rib: nothing to draw between the windows

        mesh.Quad(new Vector3(x0, y1, z), new Vector3(x1, y1, z),
                  new Vector3(x1, y0, z), new Vector3(x0, y0, z), facing);
    }

    private static void WallX(MeshBuilder mesh, float x, float y0, float y1,
                              float z0, float z1, Vector3 facing)
    {
        if (y1 - y0 <= Epsilon || Mathf.Abs(z1 - z0) <= Epsilon)
            return;

        mesh.Quad(new Vector3(x, y0, z0), new Vector3(x, y1, z0),
                  new Vector3(x, y1, z1), new Vector3(x, y0, z1), facing);
    }

    private static void WallY(MeshBuilder mesh, float y, float x0, float x1,
                              float z0, float z1, Vector3 facing)
    {
        if (x1 - x0 <= Epsilon || Mathf.Abs(z1 - z0) <= Epsilon)
            return;

        mesh.Quad(new Vector3(x0, y, z0), new Vector3(x1, y, z0),
                  new Vector3(x1, y, z1), new Vector3(x0, y, z1), facing);
    }

    // -------------------------------------------------------------- materials

    // One lit and one unlit material per colour the rack actually uses. The
    // plain colours share a single grey unlit lens - that's what "colourless
    // until it lights" means - while an x colour gets a dark one of its own.
    private static void BuildMaterials(AnnunciatorRackDefinition definition, Parts parts)
    {
        string folder = EnsureFolder(AssetFolder(definition), "materials");
        string prefix = $"{folder}/{definition.name}";

        parts.Frame = EnsureMaterial($"{prefix} Frame.mat", definition.frameColor,
                                     null, 0f, smoothness: 0.32f, metallic: 0.15f);
        parts.Lit = new Dictionary<AnnunciatorRackDefinition.TileColor, Material>();
        parts.Unlit = new Dictionary<AnnunciatorRackDefinition.TileColor, Material>();
        parts.MaterialCount = 1;

        Material grey = null;

        foreach (AnnunciatorRackDefinition.Tile tile in definition.tiles)
        {
            if (tile == null || tile.blank || parts.Lit.ContainsKey(tile.color))
                continue;

            AnnunciatorRackDefinition.TileColor color = tile.color;
            Color hue = AnnunciatorRackDefinition.LitColor(color);
            string hueName = HueName(color);

            parts.Lit[color] = EnsureMaterial(
                $"{prefix} Lens {hueName} Lit.mat", hue, hue, definition.litIntensity,
                smoothness: 0.62f, metallic: 0f);
            parts.MaterialCount++;

            if (AnnunciatorRackDefinition.KeepsColorUnlit(color))
            {
                parts.Unlit[color] = EnsureMaterial(
                    $"{prefix} Lens {hueName} Dark.mat", definition.UnlitColor(color),
                    null, 0f, smoothness: 0.62f, metallic: 0f);
                parts.MaterialCount++;
            }
            else
            {
                grey ??= EnsureMaterial($"{prefix} Lens Unlit.mat", definition.unlitLensColor,
                                        null, 0f, smoothness: 0.62f, metallic: 0f);
                parts.Unlit[color] = grey;
            }
        }

        if (grey != null)
            parts.MaterialCount++;
    }

    // X colours light the same as the plain ones, so they share a lit material.
    private static string HueName(AnnunciatorRackDefinition.TileColor color)
    {
        string name = AnnunciatorRackDefinition.WireName(color);
        if (name.StartsWith("x"))
            name = name.Substring(1);

        return char.ToUpperInvariant(name[0]) + name.Substring(1);
    }

    private static Material EnsureMaterial(string path, Color baseColor, Color? emissive,
                                           float intensity, float smoothness, float metallic)
    {
        Material material = AssetDatabase.LoadAssetAtPath<Material>(path);
        if (material == null)
        {
            material = new Material(Shader.Find("HDRP/Lit"));
            AssetDatabase.CreateAsset(material, path);
        }

        material.SetColor("_BaseColor", baseColor);
        material.SetColor("_Color", baseColor);
        material.SetFloat("_Metallic", metallic);
        material.SetFloat("_Smoothness", smoothness);

        if (emissive.HasValue)
        {
            // Same set-up as the switch lamp materials: an LDR colour with an
            // intensity in nits, so a lit lens sits in the same exposure range
            // as everything else lit in the room.
            material.SetFloat("_UseEmissiveIntensity", 1f);
            material.SetFloat("_EmissiveIntensityUnit", 0f);
            material.SetFloat("_EmissiveIntensity", Mathf.Max(0f, intensity));
            material.SetFloat("_EmissiveExposureWeight", 1f);
            material.SetColor("_EmissiveColorLDR", emissive.Value);
            material.SetColor("_EmissiveColor", emissive.Value.linear * Mathf.Max(0f, intensity));
        }
        else
        {
            material.SetFloat("_UseEmissiveIntensity", 0f);
            material.SetColor("_EmissiveColorLDR", Color.black);
            material.SetColor("_EmissiveColor", Color.black);
        }

        HDMaterial.ValidateMaterial(material);
        EditorUtility.SetDirty(material);
        return material;
    }

    // ------------------------------------------------------------- hierarchy

    private static void Populate(GameObject root, AnnunciatorRackDefinition definition, Parts parts)
    {
        AnnunciatorRack rack = root.GetComponent<AnnunciatorRack>();
        if (rack == null)
            rack = root.AddComponent<AnnunciatorRack>();

        var body = new GameObject("Body");
        body.transform.SetParent(root.transform, false);
        body.AddComponent<MeshFilter>().sharedMesh = parts.Body;
        body.AddComponent<MeshRenderer>().sharedMaterial = parts.Frame;

        // The box, so the rack is something you can't walk through.
        BoxCollider collider = body.AddComponent<BoxCollider>();
        collider.center = new Vector3(0f, 0f, -definition.depth * 0.5f);
        collider.size = new Vector3(definition.width, definition.height, definition.depth);

        var windows = new GameObject("Windows");
        windows.transform.SetParent(root.transform, false);

        var tiles = new List<AnnunciatorTile>(definition.CellCount);
        string group = string.IsNullOrWhiteSpace(definition.flashGroup)
            ? AnnunciatorFlashGroups.DefaultGroup
            : definition.flashGroup.Trim();

        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                AnnunciatorRackDefinition.Tile tile = definition.TileAt(row, column);
                if (tile == null || tile.blank)
                    continue;   // blanked off: the face is solid there

                tiles.Add(BuildWindow(definition, parts, tile, row, column,
                                      windows.transform, group));
            }
        }

        parts.WindowCount = tiles.Count;
        rack.Configure(definition, tiles.ToArray());
    }

    private static AnnunciatorTile BuildWindow(AnnunciatorRackDefinition definition, Parts parts,
                                               AnnunciatorRackDefinition.Tile tile,
                                               int row, int column, Transform parent, string group)
    {
        var window = new GameObject(WindowName(tile, row, column));
        window.transform.SetParent(parent, false);
        window.transform.localPosition = definition.CellCenter(row, column);

        window.AddComponent<MeshFilter>().sharedMesh = parts.Lens;
        MeshRenderer lens = window.AddComponent<MeshRenderer>();
        lens.sharedMaterial = parts.Unlit[tile.color];

        BuildLegend(definition, tile, window.transform);

        var component = window.AddComponent<AnnunciatorTile>();
        component.Configure(
            tile.uid,
            !string.IsNullOrEmpty(tile.id) ? tile.id : AnnunciatorRackDefinition.SlugFor(tile.legend),
            tile.legend,
            tile.color,
            group,
            lens,
            parts.Lit[tile.color],
            parts.Unlit[tile.color]);

        return component;
    }

    private static void BuildLegend(AnnunciatorRackDefinition definition,
                                    AnnunciatorRackDefinition.Tile tile, Transform parent)
    {
        if (string.IsNullOrWhiteSpace(tile.legend))
            return;   // an unlabelled window is a legitimate spare

        var legend = new GameObject("Legend", typeof(RectTransform));
        var rect = (RectTransform)legend.transform;
        rect.SetParent(parent, false);
        rect.localPosition = new Vector3(0f, 0f, LegendOffset);
        // TextMeshPro reads from its own -Z (the same reason the project's label
        // prefabs are turned to face up), and the rack looks down +Z - so left
        // at identity the legend comes out mirrored. Turn it to face out.
        rect.localRotation = Quaternion.Euler(0f, 180f, 0f);
        rect.localScale = Vector3.one * LegendScale;

        float padding = Mathf.Max(0f, definition.legendPadding);
        rect.sizeDelta = new Vector2(
            Mathf.Max(1f, (definition.CellWidth - 2f * padding) / LegendScale),
            Mathf.Max(1f, (definition.CellHeight - 2f * padding) / LegendScale));

        var text = legend.AddComponent<TextMeshPro>();
        text.text = tile.legend;
        text.color = definition.legendColor;
        text.alignment = TextAlignmentOptions.Center;
        text.raycastTarget = false;

        if (definition.legendFont != null)
            text.font = definition.legendFont;
        else if (TMP_Settings.defaultFontAsset == null)
            Debug.LogWarning("[AnnunciatorRackBuilder] no TMP font: import the TextMesh Pro " +
                             "essentials, or set a Legend Font on the definition.");

        // Legends are set in the space the window has, so a long one shrinks
        // rather than spilling over the frame.
        text.fontSize = definition.legendSize / LegendScale;
        text.fontSizeMax = text.fontSize;
        text.fontSizeMin = 1f;
        text.enableAutoSizing = true;

        MeshRenderer renderer = legend.GetComponent<MeshRenderer>();
        if (renderer != null)
        {
            // Printed on the lens: it shouldn't cast a shadow onto it.
            renderer.shadowCastingMode = ShadowCastingMode.Off;
            renderer.receiveShadows = false;
        }
    }

    private static string WindowName(AnnunciatorRackDefinition.Tile tile, int row, int column)
    {
        string legend = (tile.legend ?? "").Replace("\r", " ").Replace("\n", " ").Trim();
        if (legend.Length > 28)
            legend = legend.Substring(0, 28).TrimEnd();

        return string.IsNullOrEmpty(legend)
            ? $"R{row + 1}C{column + 1}"
            : $"R{row + 1}C{column + 1} {legend}";
    }

    // ------------------------------------------------------------------ assets

    private static string AssetFolder(AnnunciatorRackDefinition definition)
    {
        string path = AssetDatabase.GetAssetPath(definition);
        return System.IO.Path.GetDirectoryName(path).Replace('\\', '/');
    }

    private static string EnsureFolder(string parent, string name)
    {
        string path = $"{parent}/{name}";
        if (!AssetDatabase.IsValidFolder(path))
            AssetDatabase.CreateFolder(parent, name);

        return path;
    }

    // Rewrites the mesh asset in place if there is one, so prefabs and scenes
    // already pointing at it follow the rebuild instead of losing their model.
    private static Mesh EnsureMesh(string path, Mesh built, string name)
    {
        Mesh existing = AssetDatabase.LoadAssetAtPath<Mesh>(path);
        if (existing == null)
        {
            built.name = name;
            AssetDatabase.CreateAsset(built, path);
            return built;
        }

        EditorUtility.CopySerialized(built, existing);
        existing.name = name;
        EditorUtility.SetDirty(existing);
        Object.DestroyImmediate(built);
        return existing;
    }

    // ------------------------------------------------------------------ mesh

    private class MeshBuilder
    {
        private readonly List<Vector3> _vertices = new List<Vector3>();
        private readonly List<Vector3> _normals = new List<Vector3>();
        private readonly List<Vector2> _uvs = new List<Vector2>();
        private readonly List<int> _triangles = new List<int>();

        // Four corners in ring order and the direction the face should look.
        // The winding is corrected to match, so callers only have to get the
        // ring right - which side is out is stated, not derived.
        public void Quad(Vector3 a, Vector3 b, Vector3 c, Vector3 d, Vector3 facing)
        {
            Vector3 normal = Vector3.Cross(b - a, c - a);
            if (normal.sqrMagnitude <= 1e-14f)
                return;   // degenerate

            if (Vector3.Dot(normal, facing) < 0f)
            {
                (a, d) = (d, a);
                (b, c) = (c, b);
                normal = -normal;
            }

            normal.Normalize();

            // UVs in metres, so any texture put on a rack tiles at a real size
            // whatever size the rack is.
            float width = Vector3.Distance(a, b);
            float height = Vector3.Distance(b, c);

            int index = _vertices.Count;
            _vertices.Add(a); _vertices.Add(b); _vertices.Add(c); _vertices.Add(d);
            _uvs.Add(new Vector2(0f, height));
            _uvs.Add(new Vector2(width, height));
            _uvs.Add(new Vector2(width, 0f));
            _uvs.Add(new Vector2(0f, 0f));

            for (int i = 0; i < 4; i++)
                _normals.Add(normal);

            _triangles.Add(index); _triangles.Add(index + 1); _triangles.Add(index + 2);
            _triangles.Add(index); _triangles.Add(index + 2); _triangles.Add(index + 3);
        }

        public Mesh Build()
        {
            var mesh = new Mesh { indexFormat = IndexFormat.UInt32 };
            mesh.SetVertices(_vertices);
            mesh.SetNormals(_normals);
            mesh.SetUVs(0, _uvs);
            mesh.SetTriangles(_triangles, 0);
            mesh.RecalculateTangents();
            mesh.RecalculateBounds();
            return mesh;
        }
    }
}
