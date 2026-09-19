using System.Collections;
using UnityEngine;

/// <summary>
/// Spins the model 360° clockwise (around the Y axis, as seen from
/// above) when a VenusResponse arrives with action == "FLIP".
/// </summary>
public class FlipController : MonoBehaviour
{
    [Header("References")]
    public ResponseListener responseListener;

    [Tooltip("What actually rotates. If empty, uses this GameObject's transform.")]
    public Transform modelRoot;

    [Header("FLIP")]
    public float duration = 0.8f;

    private bool isRunning = false;

    void Awake()
    {
        if (modelRoot == null)
            modelRoot = transform;

        if (responseListener == null)
            responseListener = FindFirstObjectByType<ResponseListener>();
    }

    void OnEnable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("FlipController: no ResponseListener found — won't react to FLIP.");
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
        if (response.action != "FLIP") return;

        Flip();
    }

    public void Flip()
    {
        if (isRunning)
        {
            Debug.LogWarning("FlipController: flip ignored, already in progress.");
            return;
        }

        StartCoroutine(FlipCoroutine());
    }

    private IEnumerator FlipCoroutine()
    {
        isRunning = true;

        Quaternion startRotation = modelRoot.rotation;
        float elapsed = 0f;

        while (elapsed < duration)
        {
            elapsed += Time.deltaTime;
            float progress = Mathf.Clamp01(elapsed / duration);

            // Clockwise from above = negative Y rotation.
            float angle = Mathf.Lerp(0f, -360f, progress);
            modelRoot.rotation = startRotation * Quaternion.Euler(0f, angle, 0f);

            yield return null;
        }

        modelRoot.rotation = startRotation;
        isRunning = false;
    }
}