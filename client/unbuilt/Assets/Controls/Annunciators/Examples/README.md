# Example annunciator racks

Two racks, two ways of writing the same thing.

| File | Shape | What it is |
| --- | --- | --- |
| `mcr-rack-a-labels.csv` + `mcr-rack-a-colours.csv` | grid | 8 x 4 process rack. Two files, laid out like the panel: legends in one, lens colours in the other, cell for cell. |
| `mcr-rack-b-list.csv` | list | 6 x 2 turbine-generator rack. One file with a `row,column,text,colour,id` header, so it carries both legends and colours - give it to **both** importers. Row 2 column 4 is missing from the list, so that window stays as it was. |

Both use `|` for a line break in a legend (`\n` works too), and rack A blanks its
last two cells off with `-`.

To use one: create an **NPP > Annunciator Rack Definition**, drop the CSV(s) into
its Labels/Colours slots, press **Import Both**, then **Build Model + Prefab**.
Put both racks in the same **Flash Group** (`MCR`, say) and every window on both
of them blinks together.

The ids in rack A are what `server/annunciator_sim.py` drives: run a pump up and
`RCP_n_LO_SPEED` lights until it gets to speed, crack the bypass valve and
`BYPASS_VLV_OPEN` comes in.
