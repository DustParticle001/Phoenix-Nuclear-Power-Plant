// IInteractable.cs
using UnityEngine;

// What InteractionManager needs from anything the player can click, so the
// raycast doesn't have to know every controller class by name. Put it on the
// component that sits on the model root (the same one that carries
// ISwitchControl), not on the moving part.
public interface IInteractable
{
    // Clicked. The world point the ray hit, so a control with sides can work
    // out which one was pressed.
    void OnInteract(Vector3 worldHitPoint);
}

// A control that also cares about the click ending: a spring-return switch or
// a momentary button, which is only off its rest position while the mouse
// button is down.
//
// InteractionManager remembers what it pressed and releases that one, wherever
// the player happens to be looking by the time they let go - in the room your
// hand stays on the switch while you look somewhere else.
public interface IHoldInteractable : IInteractable
{
    // The mouse button came up. The control may still take its time going back:
    // see Minimum Hold Seconds on the spring-return handlers.
    void OnRelease();
}
