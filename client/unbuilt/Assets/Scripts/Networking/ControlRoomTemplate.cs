// ControlRoomTemplate.cs
using System;
using UnityEngine;

// Mirror of the JSON the server returns from GET /api/template: the blueprint
// of one control room — which switches, annunciators and gauges exist, which
// panel each belongs to, and the state the server currently holds for them.
//
// Field names must match the JSON keys exactly, because JsonUtility maps keys
// straight onto field names (which is why the server sends camelCase and no
// hyphens). Missing keys keep their default value and unknown keys are
// ignored, so either side can add fields without breaking the other.
[Serializable]
public class ControlRoomTemplate
{
    [Serializable]
    public class Plant
    {
        public string id;
        public string name;
        public int unit;
        public string reactorType;
        public string scene;   // Unity scene the server expects the client to load
    }

    [Serializable]
    public class Panel
    {
        public string id;
        public string name;
        public string description;
    }

    // definitionId is the UID on the SwitchDefinition / GaugeDefinition asset
    // the control is bound to in the scene. Empty means the server knows about
    // the control but nothing has been modelled for it yet.
    [Serializable]
    public class Switch
    {
        public string id;
        public string definitionId;
        public string name;
        public string panelId;
        public string controller;   // handler class in the scene, e.g. Rot2p / Rot3p
        public string[] positions;
        public string position;
        public bool powered;
        public bool available;
        public string indicatorState;
    }

    [Serializable]
    public class Annunciator
    {
        public string id;
        public string name;
        public string panelId;
        public string text;        // legend printed on the tile
        public int row;
        public int column;
        public int priority;       // 1 = highest
        public string state;       // clear / alarm / cleared-unacked
        public bool flashing;
        public bool acknowledged;
        public string color;
    }

    [Serializable]
    public class Gauge
    {
        public string id;
        public string definitionId;
        public string name;
        public string panelId;
        public string units;
        public float minValue;
        public float maxValue;
        public float value;
        public bool valid;         // false when the instrument itself has failed
    }

    [Serializable]
    public class Breaker
    {
        public string id;
        public string name;
        public string panelId;
        public string switchState;   // open / closed
        public string indicatorState;
        public bool powered;
        public bool available;
    }

    public int templateVersion;
    public string generatedBy;
    public Plant plant;
    public Panel[] panels;
    public Switch[] switches;
    public Annunciator[] annunciators;
    public Gauge[] gauges;
    public Breaker[] breakers;

    // Parse an /api/template response. Returns null and fills error on bad JSON,
    // so callers never have to null-check the arrays.
    public static ControlRoomTemplate Parse(string json, out string error)
    {
        ControlRoomTemplate template;

        try
        {
            template = JsonUtility.FromJson<ControlRoomTemplate>(json);
        }
        catch (Exception exception)
        {
            error = $"Server sent a template we couldn't read ({exception.Message}).";
            return null;
        }

        if (template == null)
        {
            error = "Server sent an empty template.";
            return null;
        }

        template.plant ??= new Plant();
        template.panels ??= new Panel[0];
        template.switches ??= new Switch[0];
        template.annunciators ??= new Annunciator[0];
        template.gauges ??= new Gauge[0];
        template.breakers ??= new Breaker[0];

        error = null;
        return template;
    }

    public string Summary() =>
        $"{switches.Length} switches, {annunciators.Length} annunciators, {gauges.Length} gauges";

    // Lookups by definition UID — the same UID SwitchDefinition/GaugeDefinition
    // expose as Id, so scene controls can find their own entry.
    public Switch FindSwitch(string definitionId)
    {
        if (string.IsNullOrEmpty(definitionId))
            return null;

        foreach (var entry in switches)
            if (entry.definitionId == definitionId)
                return entry;

        return null;
    }

    public Gauge FindGauge(string definitionId)
    {
        if (string.IsNullOrEmpty(definitionId))
            return null;

        foreach (var entry in gauges)
            if (entry.definitionId == definitionId)
                return entry;

        return null;
    }
}
