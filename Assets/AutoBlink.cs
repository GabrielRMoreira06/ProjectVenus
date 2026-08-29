using System.Collections;
using UniGLTF;
using UniVRM10;
using UnityEngine;

/// <summary>
/// Blinks periodically using the VRM10 Expression runtime, instead of
/// writing directly to a blend shape via SkinnedMeshRenderer.
///
/// Why: Vrm10Instance (Update Type = Late Update) reapplies the VRM's
/// pose and expressions in its own LateUpdate. If AutoBlink wrote
/// directly to the "Blink" blend shape, that write would be overwritten
/// by the VRM's runtime in the same frame (or the next), depending on
/// script execution order — giving the impression that blinking "isn't
/// working". By setting the weight through
/// vrm10Instance.Runtime.Expression.SetWeight(...), the VRM itself
/// applies that value as part of its normal processing, instead of
/// competing with it.
/// </summary>
public class AutoBlink : MonoBehaviour
{
    [Tooltip("Reference to the model's Vrm10Instance (same GameObject or parent).")]
    public Vrm10Instance vrm10Instance;

    public float blinkDuration = 0.1f; // Time it takes to close and to open

    void Start()
    {
        if (vrm10Instance == null)
        {
            vrm10Instance = GetComponent<Vrm10Instance>();

            if (vrm10Instance == null)
            {
                vrm10Instance = GetComponentInParent<Vrm10Instance>();
            }
        }

        if (vrm10Instance == null)
        {
            Debug.LogWarning("AutoBlink: Vrm10Instance not found — blinking disabled.");
            return;
        }

        StartCoroutine(BlinkLoop());
    }

    IEnumerator BlinkLoop()
    {
        while (true)
        {
            // Waits a random amount of time before blinking
            yield return new WaitForSeconds(Random.Range(2f, 6f));

            float elapsedTime = 0f;

            // Transition closing the eyes (0 to 1)
            while (elapsedTime < blinkDuration)
            {
                elapsedTime += Time.deltaTime;
                float weight = Mathf.Lerp(0f, 1f, elapsedTime / blinkDuration);
                vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, weight);
                yield return null; // Waits for the next frame
            }
            vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, 1f); // Ensures it ends exactly closed

            elapsedTime = 0f;

            // Transition opening the eyes (1 to 0)
            while (elapsedTime < blinkDuration)
            {
                elapsedTime += Time.deltaTime;
                float weight = Mathf.Lerp(1f, 0f, elapsedTime / blinkDuration);
                vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, weight);
                yield return null; // Waits for the next frame
            }
            vrm10Instance.Runtime.Expression.SetWeight(ExpressionKey.Blink, 0f); // Ensures it ends exactly open
        }
    }
}