using System.Collections;
using TMPro;
using UnityEngine;

/// <summary>
/// Displays floating text (e.g., "Energy++", "Anger--") above
/// Venus's head whenever the backend response includes a
/// valid MOOD_SHIFT — providing immediate visual feedback for mood changes.
/// </summary>
public class MoodChangeIndicator : MonoBehaviour
{
    [Header("References")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, attempts to find one in the scene.")]
    public ResponseListener responseListener;
    public Transform originPoint;
    public TMP_FontAsset font;

    [Header("Configuration")]
    public float riseDistance = 0.5f;
    public float duration = 1.5f;
    public float fontSize = 1f;

    [Header("Colors by Variant")]
    public Color angerColor = new Color(0.9f, 0.2f, 0.2f);
    public Color energyColor = new Color(1f, 0.85f, 0.2f);
    public Color boredomColor = new Color(0.5f, 0.5f, 0.9f);
    public Color affectionColor = new Color(1f, 0.4f, 0.7f);

    void Awake()
    {
        if (responseListener == null)
        {
            responseListener = FindObjectOfType<ResponseListener>();
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
            Debug.LogWarning("MoodChangeIndicator: No ResponseListener found — mood indicator disabled.");
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

        // mood_variant and mood_shift are always populated by
        // ResponseParser (Python), but may arrive as "NONE" when
        // there is no mood change in this response — Show() handles
        // this case and simply displays nothing.
        Show(response.mood_variant, response.mood_shift);
    }

    public void Show(string variant, string shift)
    {
        if (string.IsNullOrEmpty(variant) || string.IsNullOrEmpty(shift)) return;
        if (variant == "NONE" || shift == "NONE") return;
        if (originPoint == null) return;

        string symbol = shift == "INCREASE" ? "++" : shift == "DECREASE" ? "--" : null;
        if (symbol == null) return;

        StartCoroutine(AnimateText($"{FormatName(variant)}{symbol}", GetColorForVariant(variant)));
    }

    private string FormatName(string variant)
    {
        switch (variant)
        {
            case "ANGER": return "Anger";
            case "ENERGY": return "Energy";
            case "BOREDOM": return "Boredom";
            case "AFFECTION": return "Affection";
            default: return variant;
        }
    }

    private Color GetColorForVariant(string variant)
    {
        switch (variant)
        {
            case "ANGER": return angerColor;
            case "ENERGY": return energyColor;
            case "BOREDOM": return boredomColor;
            case "AFFECTION": return affectionColor;
            default: return Color.white;
        }
    }

    private IEnumerator AnimateText(string message, Color color)
    {
        GameObject obj = new GameObject("MoodChangeText");
        TextMeshPro tmp = obj.AddComponent<TextMeshPro>();

        tmp.text = message;
        tmp.color = color;
        tmp.fontSize = fontSize;
        tmp.alignment = TextAlignmentOptions.Center;

        if (font != null)
            tmp.font = font;

        obj.transform.position = originPoint.position;

        Vector3 initialPos = originPoint.position;
        Vector3 targetPos = initialPos + Vector3.up * riseDistance;

        float elapsedTime = 0f;

        while (elapsedTime < duration)
        {
            elapsedTime += Time.deltaTime;
            float progress = Mathf.Clamp01(elapsedTime / duration);

            obj.transform.position = Vector3.Lerp(initialPos, targetPos, progress);

            if (Camera.main != null)
                obj.transform.rotation = Camera.main.transform.rotation;

            if (progress > 0.5f)
            {
                Color currentColor = tmp.color;
                currentColor.a = Mathf.Lerp(1f, 0f, (progress - 0.5f) / 0.5f);
                tmp.color = currentColor;
            }

            yield return null;
        }

        Destroy(obj);
    }
}