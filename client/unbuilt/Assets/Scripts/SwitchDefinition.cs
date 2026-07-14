// SwitchDefinition.cs
using UnityEngine;

[CreateAssetMenu(fileName = "SwitchDef_New", menuName = "NPP/Switch Definition")]
public class SwitchDefinition : ScriptableObject
{
    [SerializeField] private string _id;
    public string Id => _id;
    public string displayName;

    // Right-click the asset in Project → Generate New ID
    [ContextMenu("Generate New ID")]
    private void GenerateId() => _id = System.Guid.NewGuid().ToString();
}