// AnnunciatorRackDefinition.cs
using System;
using UnityEngine;

// Data-driven description of one annunciator rack: how big it is, how many
// windows it holds, what each window says and what colour it lights.
//
// The editor builder (Editor/AnnunciatorRackBuilder.cs) turns this into the
// model - frame mesh, lens meshes, materials, legends - and a prefab you drop
// in the scene. Nothing about the rack is modelled by hand, so changing
// cellsX/cellsY or re-importing a CSV and rebuilding is the whole workflow.
//
// Every window carries its own uid, which is what the server keys its live
// state by (see AnnunciatorTile / IoSync). Uids are generated on import and
// kept across rebuilds - a window that keeps its uid keeps its alarm.
//
// Space convention: the face lies in the XY plane looking down +Z, origin at
// the centre of the face, and the box extends back into -Z. Row 0 is the top
// row and column 0 the left one *as the face is read*, so the tile array reads
// like the CSV does - which is why the columns run the other way along local x
// (see CellCenter). The rack is read from +Z, and looking down -Z puts local +X
// on the reader's left.
[CreateAssetMenu(fileName = "AnnRack_New", menuName = "NPP/Annunciator Rack Definition")]
public class AnnunciatorRackDefinition : ScriptableObject
{
    // The nine lens colours. The X variants are the ones that keep their colour
    // when the window is dark ("xred" is a red-tinted window even unlit); the
    // plain ones sit grey and colourless until they light.
    public enum TileColor { White, Amber, Red, Green, Blue, XAmber, XRed, XGreen, XBlue }

    [Serializable]
    public class Tile
    {
        [Tooltip("Definition UID the server keys this window by. Generated on import - don't reuse one.")]
        public string uid;

        [Tooltip("Readable id a simulation names the window by (RCP_1_TRIP). Defaults to the legend, slugged.")]
        public string id;

        [Tooltip("Legend printed on the window. Line breaks split it over several lines.")]
        [TextArea(1, 3)]
        public string legend;

        public TileColor color = TileColor.White;

        [Tooltip("Blanked-off cell: frame, no window. A '-' in the labels CSV.")]
        public bool blank;

        public bool IsEmpty => blank || string.IsNullOrWhiteSpace(legend);
    }

    [Header("Identity")]
    [SerializeField] private string _id;
    public string Id => _id;
    public string displayName;

    [Tooltip("Racks sharing a group name flash in step - within one rack and across every other rack in the group. Empty means the default group.")]
    public string flashGroup = "";

    [Tooltip("Which SART cluster works this rack: the name its Silence/Acknowledge/Reset/Test " +
             "buttons carry. A DIFFERENT and usually smaller grouping than Flash Group - a whole " +
             "control room flashes in step, while one SART panel commands the one to three racks " +
             "in front of it. Empty means only a master cluster (one with no name of its own) " +
             "reaches this rack.")]
    public string sartGroup = "";

    [Header("Layout (metres)")]
    [Tooltip("Overall size of the rack face.")]
    public float width = 1.2f;
    public float height = 0.5f;
    [Tooltip("Windows across, and down.")]
    public int cellsX = 8;
    public int cellsY = 4;
    [Tooltip("How far the box extends behind the face.")]
    public float depth = 0.09f;
    [Tooltip("Frame left around the outside of the window grid.")]
    public float bezelMargin = 0.018f;
    [Tooltip("Frame between two windows.")]
    public float ribWidth = 0.008f;
    [Tooltip("How far the lens sits behind the face - the depth of the window's socket.")]
    public float lensRecess = 0.010f;

    [Header("Flashing")]
    [Tooltip("Half a flash cycle for an alarm nobody has acknowledged yet: lit for this long, dark for this long. The fast one. Shared by every rack in the group - the first rack to register the group sets it.")]
    public float announceFlashSeconds = 0.2f;

    [Tooltip("Half a flash cycle for ringback - the condition cleared before anyone acknowledged it. Slower than the announce flash on purpose, so the two read as different things across the room.")]
    public float clearFlashSeconds = 0.8f;

    [Header("Style")]
    public Color frameColor = new Color(0.18f, 0.18f, 0.19f);
    [Tooltip("Colourless lens: what a plain (non-x) window looks like unlit.")]
    public Color unlitLensColor = new Color(0.62f, 0.62f, 0.59f);
    [Tooltip("How much colour an x-window keeps while it's dark. 0 is black, 1 is fully lit-coloured.")]
    [Range(0.02f, 0.6f)] public float unlitTint = 0.22f;
    [Tooltip("Emissive intensity of a lit lens, in nits - same units as the switch lamp materials.")]
    public float litIntensity = 4f;
    [Tooltip("Legend colour. Annunciator legends are printed dark on the lens, so they read lit or unlit.")]
    public Color legendColor = new Color(0.06f, 0.06f, 0.06f);
    [Tooltip("Largest the legend text may be, in metres - it shrinks from here to fit its window.")]
    public float legendSize = 0.15f;
    [Tooltip("Clear space left around the legend inside its window, in metres.")]
    public float legendPadding = 0.004f;
    [Tooltip("Legend font. The TMP default is used if this is empty.")]
    public TMPro.TMP_FontAsset legendFont;

    [Header("Windows")]
    [Tooltip("One entry per cell, row-major from the top-left. Rebuilt to fit cellsX * cellsY.")]
    public Tile[] tiles = new Tile[0];

    // The grid width the tiles array was last laid out for. Changing cellsX
    // moves every window's index, so remapping a resized rack needs to know
    // what the old rows were - without this a wider rack would shuffle its own
    // legends. Set by the importer, not by hand.
    [HideInInspector] public int tilesCellsX;

    [Header("CSV Import")]
    [Tooltip("Legends, one cell per window - a grid shaped like the rack, or a list with a row/column/text header.")]
    public TextAsset labelsCsv;
    [Tooltip("Lens colours, same shape as the labels: white, amber, red, green, blue, xamber, xred, xgreen, xblue.")]
    public TextAsset colorsCsv;
    [Tooltip("Take cellsX/cellsY from the CSV instead of making the CSV fit the rack.")]
    public bool resizeToCsv = true;

    [Header("Generated (set by the builder)")]
    public GameObject generatedPrefab;
    public Mesh bodyMesh;
    public Mesh lensMesh;

    // ------------------------------------------------------------- geometry

    // Size of one window. Both come out of the face size, so a rack is
    // described the way it is ordered: this big, this many windows.
    public float CellWidth => (width - 2f * bezelMargin - Mathf.Max(0, cellsX - 1) * ribWidth)
                              / Mathf.Max(1, cellsX);
    public float CellHeight => (height - 2f * bezelMargin - Mathf.Max(0, cellsY - 1) * ribWidth)
                               / Mathf.Max(1, cellsY);

    public int CellCount => Mathf.Max(0, cellsX) * Mathf.Max(0, cellsY);

    public int IndexOf(int row, int column) => row * cellsX + column;

    public Tile TileAt(int row, int column)
    {
        int index = IndexOf(row, column);
        return tiles != null && index >= 0 && index < tiles.Length ? tiles[index] : null;
    }

    // Centre of a window on the lens plane, in the rack's local space.
    //
    // Columns run from +x to -x, not the other way about: the face is read from
    // +Z, and a viewer looking down -Z has local +X on their left. Laying column
    // 0 out at -X would put the first column of the CSV on the right-hand end of
    // the rack, mirroring the whole panel.
    public Vector3 CellCenter(int row, int column)
    {
        float x = width * 0.5f - bezelMargin - column * (CellWidth + ribWidth) - CellWidth * 0.5f;
        float y = height * 0.5f - bezelMargin - row * (CellHeight + ribWidth) - CellHeight * 0.5f;
        return new Vector3(x, y, -lensRecess);
    }

    public bool Validate(out string error)
    {
        if (cellsX < 1 || cellsY < 1)
            error = "cellsX and cellsY must both be at least 1.";
        else if (width <= 0f || height <= 0f)
            error = "width and height must be positive.";
        else if (CellWidth <= 0f || CellHeight <= 0f)
            error = "no room left for windows - reduce bezelMargin/ribWidth, or make the rack bigger.";
        else if (depth <= lensRecess)
            error = "depth must be greater than lensRecess, or the lens would sit behind the box.";
        else
            error = null;

        return error == null;
    }

    // ---------------------------------------------------------------- colour

    // The wire name, and what the CSV writes. Lower case, x-prefixed.
    public static string WireName(TileColor color)
    {
        switch (color)
        {
            case TileColor.White:  return "white";
            case TileColor.Amber:  return "amber";
            case TileColor.Red:    return "red";
            case TileColor.Green:  return "green";
            case TileColor.Blue:   return "blue";
            case TileColor.XAmber: return "xamber";
            case TileColor.XRed:   return "xred";
            case TileColor.XGreen: return "xgreen";
            case TileColor.XBlue:  return "xblue";
            default:               return "white";
        }
    }

    // Reads what a CSV is likely to contain: "xred", "x-red", "dark red",
    // "darkred" and "DARK RED" are all the same window.
    public static bool TryParseColor(string text, out TileColor color)
    {
        color = TileColor.White;
        if (string.IsNullOrWhiteSpace(text))
            return false;

        string name = text.Trim().ToLowerInvariant()
            .Replace(" ", "").Replace("-", "").Replace("_", "");

        if (name.StartsWith("dark"))
            name = "x" + name.Substring(4);

        switch (name)
        {
            case "white":  color = TileColor.White;  return true;
            case "amber":
            case "yellow": color = TileColor.Amber;  return true;
            case "red":    color = TileColor.Red;    return true;
            case "green":  color = TileColor.Green;  return true;
            case "blue":   color = TileColor.Blue;   return true;
            case "xamber":
            case "xyellow": color = TileColor.XAmber; return true;
            case "xred":   color = TileColor.XRed;   return true;
            case "xgreen": color = TileColor.XGreen; return true;
            case "xblue":  color = TileColor.XBlue;  return true;
            // A window with no colour of its own is a plain white one.
            case "xwhite": color = TileColor.White;  return true;
            default:       return false;
        }
    }

    // True for the x-variants: coloured even when dark.
    public static bool KeepsColorUnlit(TileColor color) => color >= TileColor.XAmber;

    // The hue a window lights in. X variants light the same as their plain twin.
    public static Color LitColor(TileColor color)
    {
        switch (color)
        {
            case TileColor.Amber:
            case TileColor.XAmber: return new Color(1f, 0.58f, 0.06f);
            case TileColor.Red:
            case TileColor.XRed:   return new Color(1f, 0.06f, 0.03f);
            case TileColor.Green:
            case TileColor.XGreen: return new Color(0.16f, 1f, 0.29f);
            case TileColor.Blue:
            case TileColor.XBlue:  return new Color(0.20f, 0.45f, 1f);
            default:               return new Color(1f, 0.97f, 0.90f);
        }
    }

    // What the lens looks like with the lamp out: grey for a plain window, a
    // dark version of its own colour for an x one.
    public Color UnlitColor(TileColor color)
    {
        if (!KeepsColorUnlit(color))
            return unlitLensColor;

        return Color.Lerp(new Color(0.05f, 0.05f, 0.05f), LitColor(color), unlitTint);
    }

    // The readable id a window gets when the CSV doesn't name one: the legend,
    // upper-cased, with everything that isn't a letter or digit collapsed into
    // single underscores. "RCP 1 / LO SPEED" -> "RCP_1_LO_SPEED", which is what
    // a simulation writes when it addresses the window by id.
    public static string SlugFor(string legend)
    {
        if (string.IsNullOrWhiteSpace(legend))
            return "";

        var slug = new System.Text.StringBuilder(legend.Length);
        bool separator = false;

        foreach (char character in legend.ToUpperInvariant())
        {
            if (char.IsLetterOrDigit(character))
            {
                if (separator && slug.Length > 0)
                    slug.Append('_');

                separator = false;
                slug.Append(character);
            }
            else
            {
                separator = true;
            }
        }

        return slug.ToString();
    }

    // Right-click the asset in Project -> Generate New ID
    [ContextMenu("Generate New ID")]
    private void GenerateId() => _id = System.Guid.NewGuid().ToString();
}
