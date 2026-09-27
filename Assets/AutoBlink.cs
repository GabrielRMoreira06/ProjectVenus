using System.Collections;
using UniGLTF;
using UniVRM10;
using UnityEngine;

/// <summary>
/// Blinks periodically and occasionally switches to a random emotion
/// expression, both using the VRM10 Expression runtime instead of writing
/// directly to a blend shape via SkinnedMeshRenderer.
///
/// Why: Vrm10Instance (Update Type = Late Update) reapplies the VRM's
/// pose and expressions in its own LateUpdate. If this script wrote
/// directly to a blend shape, that write would be overwritten by the
/// VRM's runtime in the same frame (or the next), depending on script
/// execution order — giving the impression that blinking/expressions
/// "aren't working". By setting the weight through
/// vrm10Instance.Runtime.Expression.SetWeight(...), the VRM itself
/// applies that value as part of its normal processing, instead of
/// competing with it.
///
/// Blink and Emotion run as two independent coroutines targeting
/// different ExpressionKeys (Blink vs. Happy/Angry/Sad/Relaxed/Surprised),
/// so they never fight over the same weight.
/// </summary>
public class AutoBlink : MonoBehaviour
{
    [Tooltip("Reference to the model's Vrm10Instance (same GameObject or parent).")]
    public Vrm10Instance vrm10Instance;

    [Header("Blink")]
    public float blinkDuration = 0.1f; // Time it takes to close and to open
    public float blinkIntervalMin = 2f;
    public float blinkIntervalMax = 6f;

    [Header("Emotion")]
    [Tooltip("Time between the end of one expression and the start of the next.")]
    public float expressionIntervalMin = 4f;
    public float expressionIntervalMax = 10f;

    [Tooltip("How long a random expression is held before returning to normal.")]
    public float expressionHoldMin = 5f;
    public float expressionHoldMax = 15f;

    [Tooltip("Time it takes to ramp the expression weight in and out.")]
    public float expressionTransitionDuration = 0.3f;

    /// <summary>
    /// One entry = one emotion paired with a mouth shape (from the LipSync
    /// preset group: Aa/Ih/Ou/Ee/Oh) so the face doesn't just move eyebrows.
    /// Both keys in a pair are ramped up/down together in ExpressionLoop.
    /// </summary>
    private struct EmotionDefinition
    {
        public ExpressionKey Emotion;
        public ExpressionKey Mouth;

        public EmotionDefinition(ExpressionKey emotion, ExpressionKey mouth)
        {
            Emotion = emotion;
            Mouth = mouth;
        }
    }

    // Random emotion pool. Surprised was replaced with "Sorrow", and "Fun"
    // was added — both are custom expression clips on this model (they sit
    // next to Angry in the Expression list rather than in the standard
    // preset dropdown), not VRM10 standard presets. Rename the strings
    // below if your model's Expression list spells them differently.
    private static readonly EmotionDefinition[] RandomExpressions =
    {
        new EmotionDefinition(ExpressionKey.Happy,   ExpressionKey.Aa),
        new EmotionDefinition(ExpressionKey.Angry,   ExpressionKey.Ih),
        new EmotionDefinition(ExpressionKey.Sad,     ExpressionKey.Ee),
        new EmotionDefinition(ExpressionKey.Relaxed, ExpressionKey.Ou),
    };


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
            Debug.LogWarning("AutoBlink: Vrm10Instance not found — blinking/expressions disabled.");
            return;
        }

        StartCoroutine(BlinkLoop());
        StartCoroutine(ExpressionLoop());
    }

    IEnumerator BlinkLoop()
    {
        while (true)
        {
            // Waits a random amount of time before blinking
            yield return new WaitForSeconds(Random.Range(blinkIntervalMin, blinkIntervalMax));

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

    IEnumerator ExpressionLoop()
    {
        while (true)
        {
            // Waits a random amount of time before changing expression
            yield return new WaitForSeconds(Random.Range(expressionIntervalMin, expressionIntervalMax));

            EmotionDefinition definition = RandomExpressions[Random.Range(0, RandomExpressions.Length)];
            ExpressionKey[] keys = { definition.Emotion, definition.Mouth };
            float holdDuration = Random.Range(expressionHoldMin, expressionHoldMax);

            yield return TransitionExpressions(keys, 0f, 1f, expressionTransitionDuration);
            SetWeights(keys, 1f); // Ensures it ends exactly at full weight

            yield return new WaitForSeconds(holdDuration);

            yield return TransitionExpressions(keys, 1f, 0f, expressionTransitionDuration);
            SetWeights(keys, 0f); // Ensures it ends exactly back to normal
        }
    }

    IEnumerator TransitionExpressions(ExpressionKey[] expressions, float from, float to, float duration)
    {
        float elapsedTime = 0f;

        while (elapsedTime < duration)
        {
            elapsedTime += Time.deltaTime;
            float weight = Mathf.Lerp(from, to, elapsedTime / duration);
            SetWeights(expressions, weight);
            yield return null; // Waits for the next frame
        }
    }

    void SetWeights(ExpressionKey[] expressions, float weight)
    {
        foreach (ExpressionKey expression in expressions)
        {
            vrm10Instance.Runtime.Expression.SetWeight(expression, weight);
        }
    }
}