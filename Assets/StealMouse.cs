using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

/// <summary>
/// Makes the cursor drift toward the top-right corner with a jittery
/// "fighting for control" motion, then returns it to its original
/// position — as if she lost the fight. Triggers automatically when a
/// ResponseListener reports action == "STEALMOUSE".
/// </summary>
public class StealMouse : MonoBehaviour
{
    [Header("References")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    public ResponseListener responseListener;

    [Header("STEALMOUSE")]
    [Tooltip("How many seconds the fight over the cursor lasts.")]
    public float duration = 2.5f;

    [Tooltip("Distance the cursor drifts toward the top-right corner, in pixels.")]
    public float dragDistance = 300f;

    [Tooltip("Intensity of the shake/tugging during the fight for control.")]
    public float tremorIntensity = 15f;

    private bool isRunning = false;

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT lpPoint);

    private struct POINT
    {
        public int X;
        public int Y;
    }

    void Awake()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }
    }

    void OnEnable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("StealMouse: no ResponseListener found — won't react to STEALMOUSE.");
        }
    }

    void OnDisable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (response.action != "STEALMOUSE") return;

        Executar();
    }

    /// <summary>
    /// Starts the cursor-stealing coroutine, ignoring the request if one
    /// is already in progress.
    /// </summary>
    public void Executar()
    {
        if (isRunning)
        {
            Debug.LogWarning("StealMouse: action ignored, already in progress.");
            return;
        }

        StartCoroutine(StealMouseCoroutine());
    }

    private IEnumerator StealMouseCoroutine()
    {
        isRunning = true;

        GetCursorPos(out POINT originalPos);

        float screenWidth = Screen.currentResolution.width;
        float screenHeight = Screen.currentResolution.height;

        float x = originalPos.X;
        float y = originalPos.Y;

        // Diagonal direction toward the top-right corner (smaller y = higher up).
        Vector2 direction = new Vector2(1f, -1f).normalized;

        float targetX = Mathf.Clamp(x + direction.x * dragDistance, 0, screenWidth);
        float targetY = Mathf.Clamp(y + direction.y * dragDistance, 0, screenHeight);

        float elapsedTime = 0f;

        while (elapsedTime < duration)
        {
            elapsedTime += Time.deltaTime;
            float progress = Mathf.Clamp01(elapsedTime / duration);

            // Overall drift toward the target — doesn't need to arrive exactly.
            float baseX = Mathf.Lerp(x, targetX, progress);
            float baseY = Mathf.Lerp(y, targetY, progress);

            // "Fight for control": tugs that alternately push forward and pull back.
            float fightX = Mathf.Sin(Time.time * 14f) * tremorIntensity;
            float fightY = Mathf.Cos(Time.time * 11f) * tremorIntensity;

            // High-frequency shake added on top, to sell resistance/instability.
            float tremorX = (Mathf.PerlinNoise(Time.time * 20f, 0f) - 0.5f) * tremorIntensity;
            float tremorY = (Mathf.PerlinNoise(0f, Time.time * 20f) - 0.5f) * tremorIntensity;

            int newX = Mathf.Clamp((int)(baseX + fightX + tremorX), 0, (int)screenWidth);
            int newY = Mathf.Clamp((int)(baseY + fightY + tremorY), 0, (int)screenHeight);

            SetCursorPos(newX, newY);

            yield return null;
        }

        isRunning = false;
    }
}
