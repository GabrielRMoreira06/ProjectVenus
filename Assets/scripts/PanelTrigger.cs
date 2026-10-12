using UnityEngine;

/// <summary>
/// Attach to a GameObject with a Collider. Clicking it toggles the
/// Python PanelWindow, same as the Ctrl+Alt+H global hotkey.
/// </summary>
public class PanelToggleTrigger : MonoBehaviour
{
    private const string ToggleEndpoint = "/toggle_panel";

    void Update()
    {
        if (Input.GetMouseButtonDown(0))
        {
            print("Mouse click detected on PanelToggleTrigger.");
            CheckClick();
        }
    }

    private void CheckClick()
    {
        if (Camera.main == null) return;

        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);

        if (!Physics.Raycast(ray, out RaycastHit hit)) return;
        if (hit.collider.gameObject != gameObject) return;

        TogglePanel();
    }

    private void TogglePanel()
    {
        if (PythonConnection.Instance == null)
        {
            Debug.LogWarning("[PanelToggleTrigger] No PythonConnection instance found in the scene.");
            return;
        }

        PythonConnection.Instance.StartCoroutine(
            PythonConnection.Instance.Post(ToggleEndpoint, "{}", OnToggleComplete)
        );
    }

    private void OnToggleComplete(bool success, string responseBody)
    {
        if (!success)
        {
            Debug.LogWarning("[PanelToggleTrigger] Failed to reach /toggle_panel.");
        }
    }
}