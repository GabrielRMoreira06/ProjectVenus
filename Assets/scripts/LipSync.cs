using UniVRM10;
using UnityEngine;

/// <summary>
/// Volume-based fake lip sync using the VRM10 Expression runtime
/// (Aa/Ih/Ou) instead of writing directly to blend shapes via
/// SkinnedMeshRenderer — same reason as AutoBlink: Vrm10Instance
/// reapplies expressions in its own LateUpdate, so writing directly
/// to the mesh causes conflicts/overwrites with the VRM runtime.
/// </summary>
public class FakeLipSync : MonoBehaviour
{
    [Tooltip("Reference to the model's Vrm10Instance (same GameObject or parent).")]
    public Vrm10Instance vrm10Instance;

    [Header("Lip Sync Settings")]
    [Tooltip("Controls how much the mouth opens based on volume")]
    public float sensitivity = 300f;

    [Tooltip("Interpolation speed to prevent jerky movements")]
    public float smoothing = 15f;

    [Tooltip("How often (in seconds) to re-randomize the viseme distribution")]
    public float visemeRandomizeInterval = 0.12f;

    [Header("Reset on speech start")]
    [Tooltip("Other expressions that affect the mouth and should be reset to default when speech starts (e.g. Happy, Angry, Sad).")]
    public ExpressionKey[] expressionsToResetOnSpeechStart = new ExpressionKey[0];

    private float currentWeight = 0f;
    private readonly float[] samples = new float[256];

    private float rAa = 1f, rIh = 1f, rOu = 1f;
    private float timeSinceLastRandomize = 0f;
    private bool wasPlaying = false;

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
            Debug.LogWarning("FakeLipSync: Vrm10Instance not found — lip sync disabled.");
        }
    }

    private void RandomizeVisemes()
    {
        timeSinceLastRandomize = 0f;
        rAa = Random.value;
        rIh = Random.value;
        rOu = Random.value;
    }

    /// <summary>
    /// Puts the mouth back to its default (neutral) state.
    /// </summary>
    private void ResetMouth()
    {
        currentWeight = 0f;
        RandomizeVisemes();

        var expression = vrm10Instance.Runtime.Expression;

        expression.SetWeight(ExpressionKey.Aa, 0f);
        expression.SetWeight(ExpressionKey.Ih, 0f);
        expression.SetWeight(ExpressionKey.Ou, 0f);

        foreach (var key in expressionsToResetOnSpeechStart)
        {
            expression.SetWeight(key, 0f);
        }
    }

    public void UpdateAnimation(AudioSource audioSource)
    {
        if (vrm10Instance == null) return;

        bool isPlaying = audioSource.isPlaying;

        // Speech just started: reset the mouth to default
        if (isPlaying && !wasPlaying)
        {
            ResetMouth();
        }
        wasPlaying = isPlaying;

        timeSinceLastRandomize += Time.deltaTime;
        if (timeSinceLastRandomize >= visemeRandomizeInterval)
        {
            RandomizeVisemes();
        }

        if (isPlaying)
        {
            audioSource.GetOutputData(samples, 0);

            float sum = 0f;
            for (int i = 0; i < samples.Length; i++)
                sum += samples[i] * samples[i];
            float volume = Mathf.Sqrt(sum / samples.Length);

            // targetWeight normalized to 0-1 (VRM10 expressions use this
            // scale, unlike raw blend shapes which ranged from 0-100)
            float targetWeight = Mathf.Clamp(volume * sensitivity / 100f, 0f, 1f);
            currentWeight = Mathf.Lerp(currentWeight, targetWeight, Time.deltaTime * smoothing);
        }
        else
        {
            currentWeight = Mathf.Lerp(currentWeight, 0f, Time.deltaTime * smoothing);
        }

        float totalWeight = rAa + rIh + rOu;
        if (totalWeight < 0.0001f) totalWeight = 1f;

        var expr = vrm10Instance.Runtime.Expression;
        expr.SetWeight(ExpressionKey.Aa, currentWeight * (rAa / totalWeight));
        expr.SetWeight(ExpressionKey.Ih, currentWeight * (rIh / totalWeight));
        expr.SetWeight(ExpressionKey.Ou, currentWeight * (rOu / totalWeight));
    }
}