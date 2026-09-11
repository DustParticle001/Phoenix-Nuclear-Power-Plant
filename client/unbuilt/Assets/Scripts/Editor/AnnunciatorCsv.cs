// AnnunciatorCsv.cs
using System.Collections.Generic;
using System.Text;
using UnityEngine;

// Reads the two CSVs a rack is described by - one of legends, one of lens
// colours - into an AnnunciatorRackDefinition.
//
// Both files take either shape, and which one you have is worked out from the
// first line rather than declared:
//
//   grid   one line per row of windows, one field per column, laid out like the
//          rack is. This is the one to write by hand - you can see the panel in
//          the file. An 8x4 rack is 4 lines of 8 fields.
//
//   list   a header naming row/column/text (and optionally colour and id), then
//          one line per window. Rows and columns are 1-based, counting from the
//          top-left. Worth it for a sparse rack, or when the legends are coming
//          out of a spreadsheet that already looks like this.
//
// A list with both a text and a colour column describes the whole rack, so the
// same file can be given to both importers.
//
// In a legend, a line break is written "\n" or "|" - or as a real one inside a
// quoted field. A field of "-" on its own blanks the cell off: frame, no
// window, which is how a rack with a spare row is described.
//
// Colours are the nine the lenses come in: white, amber, red, green, blue, and
// the x variants xamber/xred/xgreen/xblue that stay coloured while dark.
// "dark red" and "x-red" read the same as "xred".
//
// Commas, semicolons and tabs all work as the separator; the first line decides
// which. Quoting is the usual CSV kind: wrap a field in double quotes to put a
// separator, a line break or a quote ("" for one quote) inside it.
public static class AnnunciatorCsv
{
    // Column names a list-form header can use for each field.
    private static readonly string[] RowKeys = { "row", "r", "line" };
    private static readonly string[] ColumnKeys = { "column", "col", "c" };
    private static readonly string[] TextKeys = { "text", "label", "legend", "value", "window" };
    private static readonly string[] ColorKeys = { "color", "colour", "lens" };
    private static readonly string[] IdKeys = { "id", "tag", "point" };

    // A parsed file, addressed the way the rack is: row 0 at the top, column 0
    // on the left. Colors/Ids are only filled in by the list form.
    public class Sheet
    {
        public int Rows;
        public int Columns;
        public bool ListForm;
        public string[][] Values;
        public string[][] Colors;
        public string[][] Ids;

        public string Value(int row, int column) => At(Values, row, column);
        public string ColorAt(int row, int column) => At(Colors, row, column);
        public string IdAt(int row, int column) => At(Ids, row, column);

        // Colours come from the colour column when there is one, and from the
        // grid itself when the file is a plain colour grid.
        public string LensAt(int row, int column) =>
            Colors != null ? At(Colors, row, column) : At(Values, row, column);

        private static string At(string[][] cells, int row, int column)
        {
            if (cells == null || row < 0 || row >= cells.Length)
                return null;

            string[] line = cells[row];
            return line != null && column >= 0 && column < line.Length ? line[column] : null;
        }
    }

    // ------------------------------------------------------------------ parse

    public static Sheet Parse(string text, out string error)
    {
        error = null;

        if (string.IsNullOrWhiteSpace(text))
        {
            error = "the file is empty.";
            return null;
        }

        // Normalising line endings up front costs nothing inside quoted fields
        // - a legend written over two lines still ends up with one \n - and
        // saves the tokenizer a case.
        string body = text.Replace("\r\n", "\n").Replace('\r', '\n');

        List<List<string>> records = Tokenize(body, DetectDelimiter(body));
        TrimTrailingBlanks(records);

        if (records.Count == 0)
        {
            error = "the file has no rows.";
            return null;
        }

        return IsHeader(records[0])
            ? ParseList(records, out error)
            : ParseGrid(records);
    }

    private static Sheet ParseGrid(List<List<string>> records)
    {
        int columns = 0;
        foreach (List<string> record in records)
            columns = Mathf.Max(columns, record.Count);

        var values = new string[records.Count][];
        for (int row = 0; row < records.Count; row++)
        {
            values[row] = new string[columns];
            for (int column = 0; column < records[row].Count; column++)
                values[row][column] = records[row][column];
        }

        return new Sheet
        {
            Rows = records.Count,
            Columns = columns,
            ListForm = false,
            Values = values,
        };
    }

    private static Sheet ParseList(List<List<string>> records, out string error)
    {
        error = null;

        List<string> header = records[0];
        int rowIndex = IndexOfKey(header, RowKeys);
        int columnIndex = IndexOfKey(header, ColumnKeys);
        int textIndex = IndexOfKey(header, TextKeys);
        int colorIndex = IndexOfKey(header, ColorKeys);
        int idIndex = IndexOfKey(header, IdKeys);

        if (rowIndex < 0 || columnIndex < 0)
        {
            error = "a list needs both a 'row' and a 'column' column in its header.";
            return null;
        }

        if (textIndex < 0 && colorIndex < 0)
        {
            error = "a list needs a 'text' column (legends) or a 'colour' one.";
            return null;
        }

        // Two passes: the first finds how big the rack has to be, the second
        // fills it in, so the entries can arrive in any order.
        int rows = 0, columns = 0;
        var entries = new List<(int row, int column, List<string> fields)>();

        for (int i = 1; i < records.Count; i++)
        {
            List<string> fields = records[i];
            if (IsBlank(fields))
                continue;

            if (!int.TryParse(Field(fields, rowIndex), out int row) ||
                !int.TryParse(Field(fields, columnIndex), out int column))
            {
                error = $"line {i + 1}: row and column have to be whole numbers, counting from 1.";
                return null;
            }

            if (row < 1 || column < 1)
            {
                error = $"line {i + 1}: row and column count from 1, not 0.";
                return null;
            }

            rows = Mathf.Max(rows, row);
            columns = Mathf.Max(columns, column);
            entries.Add((row - 1, column - 1, fields));
        }

        var sheet = new Sheet
        {
            Rows = rows,
            Columns = columns,
            ListForm = true,
            Values = textIndex >= 0 ? NewGrid(rows, columns) : null,
            Colors = colorIndex >= 0 ? NewGrid(rows, columns) : null,
            Ids = idIndex >= 0 ? NewGrid(rows, columns) : null,
        };

        foreach (var entry in entries)
        {
            if (sheet.Values != null)
                sheet.Values[entry.row][entry.column] = Field(entry.fields, textIndex);
            if (sheet.Colors != null)
                sheet.Colors[entry.row][entry.column] = Field(entry.fields, colorIndex);
            if (sheet.Ids != null)
                sheet.Ids[entry.row][entry.column] = Field(entry.fields, idIndex);
        }

        return sheet;
    }

    // A first line is a header if it names the things a list is made of. A grid
    // of legends never does, because "row" isn't an annunciator legend.
    private static bool IsHeader(List<string> record)
    {
        int hits = 0;
        bool hasRow = false, hasColumn = false;

        foreach (string field in record)
        {
            string name = (field ?? "").Trim().ToLowerInvariant();
            if (Matches(name, RowKeys)) { hasRow = true; hits++; }
            else if (Matches(name, ColumnKeys)) { hasColumn = true; hits++; }
            else if (Matches(name, TextKeys) || Matches(name, ColorKeys) || Matches(name, IdKeys))
                hits++;
        }

        return hasRow && hasColumn && hits >= 3;
    }

    private static List<List<string>> Tokenize(string text, char delimiter)
    {
        var records = new List<List<string>>();
        var record = new List<string>();
        var field = new StringBuilder();
        bool quoted = false;

        for (int i = 0; i < text.Length; i++)
        {
            char character = text[i];

            if (quoted)
            {
                if (character != '"')
                {
                    field.Append(character);
                }
                else if (i + 1 < text.Length && text[i + 1] == '"')
                {
                    field.Append('"');   // "" inside a quoted field is one quote
                    i++;
                }
                else
                {
                    quoted = false;
                }

                continue;
            }

            if (character == '"' && field.Length == 0)
                quoted = true;
            else if (character == delimiter)
                Push(record, field);
            else if (character == '\n')
            {
                Push(record, field);
                records.Add(record);
                record = new List<string>();
            }
            else
                field.Append(character);
        }

        Push(record, field);
        records.Add(record);
        return records;
    }

    // Whichever of comma, semicolon and tab shows up most on the first line.
    private static char DetectDelimiter(string text)
    {
        char[] candidates = { ',', ';', '\t' };
        var counts = new int[candidates.Length];
        bool quoted = false;

        foreach (char character in text)
        {
            if (character == '"')
                quoted = !quoted;
            else if (quoted)
                continue;
            else if (character == '\n')
                break;
            else
                for (int i = 0; i < candidates.Length; i++)
                    if (character == candidates[i])
                        counts[i]++;
        }

        int best = 0;
        for (int i = 1; i < candidates.Length; i++)
            if (counts[i] > counts[best])
                best = i;

        return counts[best] > 0 ? candidates[best] : ',';
    }

    private static void Push(List<string> record, StringBuilder field)
    {
        record.Add(field.ToString().Trim());
        field.Length = 0;
    }

    private static void TrimTrailingBlanks(List<List<string>> records)
    {
        while (records.Count > 0 && IsBlank(records[records.Count - 1]))
            records.RemoveAt(records.Count - 1);
    }

    private static bool IsBlank(List<string> record)
    {
        foreach (string field in record)
            if (!string.IsNullOrWhiteSpace(field))
                return false;

        return true;
    }

    private static string Field(List<string> fields, int index) =>
        index >= 0 && index < fields.Count ? fields[index] : null;

    private static int IndexOfKey(List<string> header, string[] keys)
    {
        for (int i = 0; i < header.Count; i++)
            if (Matches((header[i] ?? "").Trim().ToLowerInvariant(), keys))
                return i;

        return -1;
    }

    private static bool Matches(string name, string[] keys)
    {
        foreach (string key in keys)
            if (name == key)
                return true;

        return false;
    }

    private static string[][] NewGrid(int rows, int columns)
    {
        var grid = new string[rows][];
        for (int row = 0; row < rows; row++)
            grid[row] = new string[columns];

        return grid;
    }

    // ----------------------------------------------------------------- import

    // Legends, and the readable ids that come from them. Returns false with a
    // message when the file can't be read; the definition isn't touched then.
    public static bool ImportLabels(AnnunciatorRackDefinition definition, string csvText,
                                    out string message)
    {
        Sheet sheet = Parse(csvText, out string error);
        if (sheet == null)
        {
            message = $"Labels CSV: {error}";
            return false;
        }

        if (sheet.Values == null)
        {
            message = "Labels CSV: no legends in it - a list needs a 'text' column.";
            return false;
        }

        bool resized = Resize(definition, sheet);
        EnsureTiles(definition);

        int written = 0, blanked = 0;

        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                string value = sheet.Value(row, column);
                if (value == null)
                    continue;   // the CSV doesn't reach this cell: leave it alone

                AnnunciatorRackDefinition.Tile tile = definition.tiles[definition.IndexOf(row, column)];

                if (value.Trim() == "-")
                {
                    tile.blank = true;
                    tile.legend = "";
                    tile.id = "";
                    blanked++;
                    continue;
                }

                tile.blank = false;
                tile.legend = NormaliseLegend(value);

                string id = sheet.IdAt(row, column);
                tile.id = !string.IsNullOrWhiteSpace(id)
                    ? id.Trim()
                    : AnnunciatorRackDefinition.SlugFor(tile.legend);

                if (!string.IsNullOrEmpty(tile.legend))
                    written++;
            }
        }

        int renamed = MakeIdsUnique(definition);

        message = $"Imported {written} legend{Plural(written)}"
                  + (blanked > 0 ? $", {blanked} cell{Plural(blanked)} blanked off" : "")
                  + (resized ? $", rack resized to {definition.cellsX} x {definition.cellsY}" : "")
                  + (renamed > 0 ? $", {renamed} duplicate id{Plural(renamed)} numbered off" : "")
                  + Coverage(definition, sheet) + ".";
        return true;
    }

    // Lens colours. Cells the file doesn't name keep the colour they had.
    public static bool ImportColors(AnnunciatorRackDefinition definition, string csvText,
                                    out string message)
    {
        Sheet sheet = Parse(csvText, out string error);
        if (sheet == null)
        {
            message = $"Colours CSV: {error}";
            return false;
        }

        // Colours never resize a rack - that's the labels' job, and a colour
        // grid that has drifted out of shape is worth being told about.
        EnsureTiles(definition);

        int written = 0;
        var unknown = new List<string>();

        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                string value = sheet.LensAt(row, column);
                if (string.IsNullOrWhiteSpace(value))
                    continue;

                if (!AnnunciatorRackDefinition.TryParseColor(
                        value, out AnnunciatorRackDefinition.TileColor color))
                {
                    if (!unknown.Contains(value))
                        unknown.Add(value);
                    continue;
                }

                definition.tiles[definition.IndexOf(row, column)].color = color;
                written++;
            }
        }

        message = $"Imported {written} colour{Plural(written)}"
                  + Coverage(definition, sheet)
                  + (unknown.Count > 0
                      ? $". Not a lens colour: {string.Join(", ", unknown)} - use white/amber/red/"
                        + "green/blue or xamber/xred/xgreen/xblue"
                      : "")
                  + ".";
        return unknown.Count == 0;
    }

    // Makes the tiles array match cellsX * cellsY, keeping each window where it
    // is on the panel rather than where it is in the array - a rack that gets a
    // column wider would otherwise shuffle every legend along one.
    public static void EnsureTiles(AnnunciatorRackDefinition definition)
    {
        definition.cellsX = Mathf.Max(1, definition.cellsX);
        definition.cellsY = Mathf.Max(1, definition.cellsY);

        AnnunciatorRackDefinition.Tile[] existing =
            definition.tiles ?? new AnnunciatorRackDefinition.Tile[0];
        int oldWidth = definition.tilesCellsX > 0 ? definition.tilesCellsX : definition.cellsX;

        var tiles = new AnnunciatorRackDefinition.Tile[definition.CellCount];

        for (int row = 0; row < definition.cellsY; row++)
        {
            for (int column = 0; column < definition.cellsX; column++)
            {
                AnnunciatorRackDefinition.Tile tile = null;

                if (column < oldWidth)
                {
                    int index = row * oldWidth + column;
                    if (index >= 0 && index < existing.Length)
                        tile = existing[index];
                }

                tile ??= new AnnunciatorRackDefinition.Tile();

                // Its uid is its identity on the server: generated once, kept
                // for as long as the window exists.
                if (string.IsNullOrEmpty(tile.uid))
                    tile.uid = System.Guid.NewGuid().ToString();

                tiles[definition.IndexOf(row, column)] = tile;
            }
        }

        definition.tiles = tiles;
        definition.tilesCellsX = definition.cellsX;
    }

    // Two windows answering to one id would leave a simulation writing to
    // whichever came first, so the later ones are numbered off.
    public static int MakeIdsUnique(AnnunciatorRackDefinition definition)
    {
        var seen = new HashSet<string>();
        int renamed = 0;

        foreach (AnnunciatorRackDefinition.Tile tile in definition.tiles)
        {
            if (tile == null || tile.blank || string.IsNullOrEmpty(tile.id))
                continue;

            if (seen.Add(tile.id))
                continue;

            int suffix = 2;
            string candidate;
            do
            {
                candidate = $"{tile.id}_{suffix++}";
            }
            while (!seen.Add(candidate));

            tile.id = candidate;
            renamed++;
        }

        return renamed;
    }

    // "\n" and "|" are how a line break is written in a field that isn't quoted.
    public static string NormaliseLegend(string value)
    {
        if (string.IsNullOrEmpty(value))
            return "";

        return value
            .Replace("\\n", "\n")
            .Replace("|", "\n")
            .Replace("\r\n", "\n")
            .Trim();
    }

    private static bool Resize(AnnunciatorRackDefinition definition, Sheet sheet)
    {
        if (!definition.resizeToCsv || sheet.Rows < 1 || sheet.Columns < 1)
            return false;

        if (definition.cellsX == sheet.Columns && definition.cellsY == sheet.Rows)
            return false;

        definition.cellsX = sheet.Columns;
        definition.cellsY = sheet.Rows;
        return true;
    }

    private static string Coverage(AnnunciatorRackDefinition definition, Sheet sheet)
    {
        if (sheet.Rows == definition.cellsY && sheet.Columns == definition.cellsX)
            return "";

        return $" (the file is {sheet.Columns} x {sheet.Rows}, the rack is "
               + $"{definition.cellsX} x {definition.cellsY} - the rest was left as it was)";
    }

    private static string Plural(int count) => count == 1 ? "" : "s";
}
