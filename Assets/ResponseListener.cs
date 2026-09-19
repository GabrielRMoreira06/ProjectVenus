using System;
using UnityEngine;

/// <summary>
/// Shape of the JSON returned by the Python /response endpoint. Field
/// names match ResponseParser's output (response_parser.py) exactly —
/// JsonUtility matches by name, not by convention.
/// </summary>
[Serializable]
public class VenusResponse
{
    public string text;
    public string action;
    public string mood_variant;
    public string mood_shift;
    public string memory_type;
    public string memory_text;
    public string memory_expire;
    public string image_query;

    [Tooltip("Full, absolute URL to fetch when action is SHOWIMAGE — pass this straight to ImageHolder.MostrarImagem(). Null/empty when there's no image to show.")]
    public string image;

    [Tooltip("Full, absolute URL to fetch and play as the spoken response. Null/empty when the response is silent (e.g. DEADPIXEL).")]
    public string audio;
}

/// <summary>
/// Polls the Python backend for a pending Venus response — the final
/// step of the pipeline described in generic_interaction.py (internal
/// cooldown -> Orchestrator -> GeminiWorker -> ResponseParser ->
/// queue_response() -> here). Reports each response via
/// OnResponseReceived; nothing here decides what to DO with a
/// response (show a speech bubble, run an action, ...) — that belongs
/// to whatever subscribes to the event.
/// </summary>
public class ResponseListener : MonoBehaviour
{
    [Header("Polling")]
    [Tooltip("Endpoint that returns a pending Venus response, or 204 if none is waiting.")]
    public string responseEndpoint = "/response";

    [Tooltip("How often (in seconds) to ask the backend for a new response.")]
    public float pollInterval = 1f;

    /// <summary>Raised whenever a Venus response is received from Python.</summary>
    public event Action<VenusResponse> OnResponseReceived;

    private float timeSinceLastPoll = 0f;

    void Update()
    {
        if (PythonConnection.Instance == null) return;

        timeSinceLastPoll += Time.deltaTime;

        if (timeSinceLastPoll >= pollInterval)
        {
            timeSinceLastPoll = 0f;
            StartCoroutine(PythonConnection.Instance.Get(responseEndpoint, HandleResponse));
        }
    }

    private void HandleResponse(bool success, string responseBody)
    {
        if (!success || string.IsNullOrEmpty(responseBody)) return;

        VenusResponse venusResponse = JsonUtility.FromJson<VenusResponse>(responseBody);
        if (venusResponse == null) return;

        Debug.Log($"[ResponseListener] Response received from Python: '{venusResponse.text}' | action: {venusResponse.action}");
        OnResponseReceived?.Invoke(venusResponse);
    }
}