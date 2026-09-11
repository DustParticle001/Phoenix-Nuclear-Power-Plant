// AnnunciatorRackEditors.cs
using System.IO;
using UnityEditor;
using UnityEngine;

// The Inspector for an annunciator rack definition: import the two CSVs, look
// at what came in, build the model.
//
// The tile array is drawn as the panel rather than as a list - a hundred-window
// rack is unreadable as a list, and what you actually want to check after an
// import is that the legends landed on the right windows in the right colours.
[CustomEditor(typeof(AnnunciatorRackDefinition))]
public class AnnunciatorRackDefinitionEditor : Editor
{
    private const float MinPreviewCell = 26f;
    private const float MaxPreviewCell = 64f;

    private static readonly Color BlankCell = new Color(0.16f, 0.16f, 0.17f);

    private bool _showTiles;
    private string _message;
    private MessageType _messageType = MessageType.Info;

    public override void OnInspectorGUI()
    {
        var definition = (AnnunciatorRackDefinition)target;

        DrawPropertiesExcept("tiles");
        DrawIdentity(definition);
        serializedObject.ApplyModifiedProperties();

        if (!definition.Validate(out string error))
            EditorGUILayout.HelpBox(error, MessageType.Error);

        EditorGUILayout.Space();
        DrawImport(definition);

        EditorGUILayout.Space();
        DrawPreview(definition);

        EditorGUILayout.Space();
        DrawBuild(definition);

        if (!string.IsNullOrEmpty(_message))
        {
            EditorGUILayout.Space();
            EditorGUILayout.HelpBox(_message, _messageType);
        }
    }

    // ----------------------------------------------------------------- import

    private void DrawImport(AnnunciatorRackDefinition definition)
    {
        EditorGUILayout.LabelField("CSV Import", EditorStyles.boldLabel);
        EditorGUILayout.HelpBox(
            "Two files, either shape: a grid laid out like the rack, or a list with a "
            + "row/column/text header (rows and columns count from 1). In a legend, \\n or | "
            + "starts a new line and a lone - blanks the cell off. Colours: white, amber, red, "
            + "green, blue, and xamber/xred/xgreen/xblue, which stay coloured while dark.",
            MessageType.None);

        using (new EditorGUILayout.HorizontalScope())
        {
            using (new EditorGUI.DisabledScope(definition.labelsCsv == null))
            {
                if (GUILayout.Button("Import Labels"))
                    Import(definition, definition.labelsCsv.text, labels: true);
            }

            if (GUILayout.Button("Browse...", GUILayout.Width(80f)))
                Browse(definition, labels: true);
        }

        using (new EditorGUILayout.HorizontalScope())
        {
            using (new EditorGUI.DisabledScope(definition.colorsCsv == null))
            {
                if (GUILayout.Button("Import Colours"))
                    Import(definition, definition.colorsCsv.text, labels: false);
            }

            if (GUILayout.Button("Browse...", GUILayout.Width(80f)))
                Browse(definition, labels: false);
        }

        using (new EditorGUI.DisabledScope(definition.labelsCsv == null && definition.colorsCsv == null))
        {
            if (GUILayout.Button("Import Both"))
            {
                // Labels first: they're what may resize the rack, and colours
                // land on whatever grid comes out of that.
                if (definition.labelsCsv != null)
                    Import(definition, definition.labelsCsv.text, labels: true);
                if (definition.colorsCsv != null)
                    Import(definition, definition.colorsCsv.text, labels: false, append: true);
            }
        }
    }

    private void Browse(AnnunciatorRackDefinition definition, bool labels)
    {
        string path = EditorUtility.OpenFilePanel(
            labels ? "Annunciator legends CSV" : "Annunciator colours CSV", "", "csv");

        if (string.IsNullOrEmpty(path))
            return;

        try
        {
            Import(definition, File.ReadAllText(path), labels);
        }
        catch (IOException exception)
        {
            _message = $"Couldn't read {Path.GetFileName(path)}: {exception.Message}";
            _messageType = MessageType.Error;
        }
    }

    private void Import(AnnunciatorRackDefinition definition, string csv, bool labels,
                        bool append = false)
    {
        Undo.RecordObject(definition, labels ? "Import Annunciator Labels" : "Import Annunciator Colours");

        string message;
        bool ok = labels
            ? AnnunciatorCsv.ImportLabels(definition, csv, out message)
            : AnnunciatorCsv.ImportColors(definition, csv, out message);

        EditorUtility.SetDirty(definition);
        serializedObject.Update();

        _message = append && !string.IsNullOrEmpty(_message) ? $"{_message}\n{message}" : message;
        _messageType = ok ? MessageType.Info : MessageType.Warning;
    }

    // ---------------------------------------------------------------- preview

    // The rack as it would light: every window in its own colour, so a CSV that
    // landed a column out is obvious at a glance.
    private void DrawPreview(AnnunciatorRackDefinition definition)
    {
        int windows = 0;
        if (definition.tiles != null)
        {
            foreach (AnnunciatorRackDefinition.Tile tile in definition.tiles)
                if (tile != null && !tile.blank)
                    windows++;
        }

        EditorGUILayout.LabelField(
            $"Windows ({definition.cellsX} x {definition.cellsY}, {windows} fitted, shown lit)",
            EditorStyles.boldLabel);

        if (definition.tiles == null || definition.tiles.Length < definition.CellCount)
        {
            EditorGUILayout.HelpBox("Import a CSV, or press Build, to lay the windows out.",
                                    MessageType.Info);
        }
        else
        {
            DrawGrid(definition);
        }

        _showTiles = EditorGUILayout.Foldout(_showTiles, "Window list", true);
        if (_showTiles)
            EditorGUILayout.PropertyField(serializedObject.FindProperty("tiles"), true);

        serializedObject.ApplyModifiedProperties();
    }

    private void DrawGrid(AnnunciatorRackDefinition definition)
    {
        if (definition.cellsX < 1 || definition.cellsY < 1)
            return;   // nothing to draw, and nothing to divide by

        float available = EditorGUIUtility.currentViewWidth - 40f;
        float cellWidth = Mathf.Max(MinPreviewCell, available / definition.cellsX);
        float aspect = definition.CellHeight / Mathf.Max(0.0001f, definition.CellWidth);
        float cellHeight = Mathf.Clamp(cellWidth * aspect, MinPreviewCell, MaxPreviewCell);

        Rect area = GUILayoutUtility.GetRect(
            definition.cellsX * cellWidth, definition.cellsY * cellHeight, GUILayout.ExpandWidth(false));

        var style = new GUIStyle(EditorStyles.miniLabel)
        {
            alignment = TextAnchor.MiddleCenter,
            wordWrap = true,
            fontSize = 8,
        };

        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                var cell = new Rect(area.x + column * cellWidth, area.y + row * cellHeight,
                                    cellWidth - 2f, cellHeight - 2f);

                AnnunciatorRackDefinition.Tile tile = definition.TileAt(row, column);
                if (tile == null || tile.blank)
                {
                    EditorGUI.DrawRect(cell, BlankCell);
                    continue;
                }

                Color color = AnnunciatorRackDefinition.LitColor(tile.color);
                EditorGUI.DrawRect(cell, color);

                style.normal.textColor = color.grayscale > 0.45f ? Color.black : Color.white;
                GUI.Label(cell, tile.legend, style);
            }
        }
    }

    // ------------------------------------------------------------------ build

    private void DrawBuild(AnnunciatorRackDefinition definition)
    {
        EditorGUILayout.LabelField("Model", EditorStyles.boldLabel);

        if (GUILayout.Button("Build Model + Prefab", GUILayout.Height(28f)))
        {
            GameObject prefab = AnnunciatorRackBuilder.BuildPrefab(definition);
            serializedObject.Update();

            if (prefab != null)
            {
                _message = $"Built {AssetDatabase.GetAssetPath(prefab)}. Every instance of the "
                           + "prefab in a scene has followed.";
                _messageType = MessageType.Info;
            }
        }

        using (new EditorGUI.DisabledScope(definition.generatedPrefab == null))
        {
            if (GUILayout.Button("Add To Scene"))
            {
                var instance = (GameObject)PrefabUtility.InstantiatePrefab(definition.generatedPrefab);
                Undo.RegisterCreatedObjectUndo(instance, "Add Annunciator Rack");
                Selection.activeGameObject = instance;
                SceneView.lastActiveSceneView?.FrameSelected();
            }
        }
    }

    // The rack's own id. "Generate New ID" on the asset's context menu writes
    // straight onto the object, which an open Inspector has no way of noticing;
    // going through the SerializedObject does, and marks the asset dirty so the
    // id is still there after a restart.
    private void DrawIdentity(AnnunciatorRackDefinition definition)
    {
        SerializedProperty id = serializedObject.FindProperty("_id");
        bool blank = string.IsNullOrEmpty(id.stringValue);

        using (new EditorGUILayout.HorizontalScope())
        {
            GUILayout.FlexibleSpace();
            if (GUILayout.Button(blank ? "Generate ID" : "New ID", GUILayout.Width(110f)))
            {
                id.stringValue = System.Guid.NewGuid().ToString();
                serializedObject.ApplyModifiedProperties();
                EditorUtility.SetDirty(definition);
            }
        }

        if (blank)
            EditorGUILayout.HelpBox("This rack has no ID yet - press Generate ID. (Its windows "
                                    + "carry their own uids, which the CSV import generates.)",
                                    MessageType.Info);
    }

    // Everything but the one property this Inspector draws itself.
    private void DrawPropertiesExcept(params string[] skip)
    {
        // Without this the Inspector keeps working from the copy it took the
        // first time it drew, so a change made anywhere else is invisible here
        // and gets overwritten on the next ApplyModifiedProperties.
        serializedObject.Update();

        SerializedProperty property = serializedObject.GetIterator();
        bool enterChildren = true;

        while (property.NextVisible(enterChildren))
        {
            enterChildren = false;

            if (property.propertyPath == "m_Script")
            {
                using (new EditorGUI.DisabledScope(true))
                    EditorGUILayout.PropertyField(property);
                continue;
            }

            if (System.Array.IndexOf(skip, property.propertyPath) >= 0)
                continue;

            EditorGUILayout.PropertyField(property, true);
        }
    }
}

// The Inspector for a rack in a scene: which group it flashes with, and the two
// things worth doing to one by hand - rebuilding it and testing its lamps.
[CustomEditor(typeof(AnnunciatorRack))]
public class AnnunciatorRackEditor : Editor
{
    public override void OnInspectorGUI()
    {
        DrawDefaultInspector();

        var rack = (AnnunciatorRack)target;

        EditorGUILayout.Space();
        EditorGUILayout.LabelField(
            $"{rack.TileCount} window(s), flashing with group '{rack.FlashGroup}' "
            + $"at {rack.AnnounceFlashSeconds:0.##}s announce / "
            + $"{rack.ClearFlashSeconds:0.##}s ringback.", EditorStyles.miniLabel);

        using (new EditorGUI.DisabledScope(rack.Definition == null))
        {
            if (GUILayout.Button("Rebuild From Definition"))
            {
                if (PrefabUtility.IsPartOfPrefabInstance(rack))
                    Debug.LogWarning(
                        $"[AnnunciatorRack] '{rack.name}' is a prefab instance - build the " +
                        "definition instead (Build Model + Prefab) and every instance follows.");
                else if (AnnunciatorRackBuilder.RebuildInScene(rack))
                    Debug.Log($"[AnnunciatorRack] rebuilt '{rack.name}'.");
            }
        }

        using (new EditorGUI.DisabledScope(!Application.isPlaying))
        {
            using (new EditorGUILayout.HorizontalScope())
            {
                if (GUILayout.Button("Lamp Test"))
                    rack.SetLampTest(true);

                // Everything dark, lamp test included.
                if (GUILayout.Button("Lamps Off"))
                    rack.LampsOff();

                // In and unacknowledged: fast flash, horn sounding.
                if (GUILayout.Button("Flash All"))
                    rack.FlashAll();

                // Cleared but unacknowledged: the slow ringback flash.
                if (GUILayout.Button("Clear All"))
                    rack.RingbackAll();
            }
        }

        if (!Application.isPlaying)
            EditorGUILayout.LabelField("Lamp test and the local drives need play mode.",
                                       EditorStyles.miniLabel);
    }
}
