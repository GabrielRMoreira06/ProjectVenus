using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Creates small black squares at random positions within an area
/// (RectTransform), simulating dead pixels on the screen. Used as a
/// silent reaction when her anger is high.
///
/// Triggers on its own upon receiving a VenusResponse with action ==
/// "DEADPIXEL", subscribing to ResponseListener.OnResponseReceived —
/// same pattern as MoodChangeIndicator. DEADPIXEL is a silent action
/// (no audio/text), so there is nothing beyond the pixel itself to show.
/// </summary>
public class DeadPixelSpawner : MonoBehaviour
{
    [Header("References")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    public ResponseListener responseListener;

    [Tooltip("RectTransform that defines the area where pixels can appear")]
    public RectTransform validArea;

    [Header("Configuration")]
    public Color pixelColor = Color.red;
    public float pixelSize = 2f;
    public int maxPixels = 15;

    private List<GameObject> activePixels = new List<GameObject>();

 

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
            Debug.LogWarning("DeadPixelSpawner: no ResponseListener found — will not react to DEADPIXEL.");
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
        if (response.action != "DEADPIXEL") return;

        DrawDeadPixel();
    }

    public void DrawDeadPixel()
    {
        if (validArea == null)
        {
            Debug.LogWarning("DeadPixelSpawner: validArea not set.");
            return;
        }

        GameObject pixel = new GameObject("DeadPixel");
        pixel.transform.SetParent(validArea, false);

        Image img = pixel.AddComponent<Image>();
        img.color = pixelColor;
        img.raycastTarget = false; // must not block clicks on the window

        RectTransform rect = pixel.GetComponent<RectTransform>();
        rect.sizeDelta = new Vector2(pixelSize, pixelSize);

        float x = Random.Range(0f, validArea.rect.width) - validArea.rect.width / 2f;
        float y = Random.Range(0f, validArea.rect.height) - validArea.rect.height / 2f;
        rect.anchoredPosition = new Vector2(x, y);

        activePixels.Add(pixel);

        // Avoids accumulating pixels indefinitely — removes the oldest
        // one when the limit is exceeded.
        if (activePixels.Count > maxPixels)
        {
            GameObject oldest = activePixels[0];
            activePixels.RemoveAt(0);
            Destroy(oldest);
        }
    }
}