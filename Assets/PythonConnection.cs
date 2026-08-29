using System;
using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// Single entry point for HTTP communication between Unity and the
/// Python backend. Every other script talks to Python through this
/// component instead of building its own UnityWebRequest calls, so the
/// base URL, timeout, and connection state live in exactly one place.
/// </summary>
public class PythonConnection : MonoBehaviour
{
    public static PythonConnection Instance { get; private set; }

    [Header("Backend Address")]
    [Tooltip("Base URL of the Python Flask server, without a trailing slash.")]
    public string baseUrl = "http://127.0.0.1:5000";

    [Header("Connection Check")]
    [Tooltip("How often (in seconds) to verify the backend is reachable.")]
    public float healthCheckInterval = 5f;

    [Tooltip("Endpoint used to check if the backend is alive.")]
    public string healthCheckEndpoint = "/health";

    [Tooltip("Request timeout, in seconds, before a call is considered failed.")]
    public int requestTimeoutSeconds = 10;

    /// <summary>True once at least one request has succeeded since the last failure.</summary>
    public bool IsConnected { get; private set; } = false;

    /// <summary>Raised whenever the connection state changes (true = just connected, false = just lost).</summary>
    public event Action<bool> OnConnectionChanged;

    void Awake()
    {
        // Simple singleton: this component is meant to exist exactly
        // once per Unity process, since it represents ONE connection
        // to ONE backend.
        if (Instance != null && Instance != this)
        {
            Destroy(gameObject);
            return;
        }

        Instance = this;
        DontDestroyOnLoad(gameObject);
    }

    void Start()
    {
        StartCoroutine(HealthCheckLoop());
    }

    private IEnumerator HealthCheckLoop()
    {
        while (true)
        {
            yield return Get(healthCheckEndpoint, OnHealthCheckResult);
            yield return new WaitForSeconds(healthCheckInterval);
        }
    }

    private void OnHealthCheckResult(bool success, string _)
    {
        SetConnected(success);
    }

    private void SetConnected(bool connected)
    {
        if (connected == IsConnected) return;

        IsConnected = connected;
        Debug.Log(connected
            ? "[PythonConnection] Backend reachable."
            : "[PythonConnection] Backend unreachable.");

        OnConnectionChanged?.Invoke(connected);
    }

    /// <summary>
    /// Sends a GET request to the given endpoint (relative to baseUrl)
    /// and invokes onComplete with (success, rawResponseBody).
    /// success=true with an empty body means the server answered with
    /// "no content" (204) — used everywhere as "nothing pending".
    /// </summary>
    public IEnumerator Get(string endpoint, Action<bool, string> onComplete)
    {
        using (UnityWebRequest request = UnityWebRequest.Get(baseUrl + endpoint))
        {
            request.timeout = requestTimeoutSeconds;

            yield return request.SendWebRequest();

            bool success = request.result == UnityWebRequest.Result.Success;
            SetConnected(success);

            onComplete?.Invoke(success, success ? request.downloadHandler.text : null);
        }
    }

    /// <summary>
    /// Sends a POST request with a JSON body to the given endpoint and
    /// invokes onComplete with (success, rawResponseBody).
    /// </summary>
    public IEnumerator Post(string endpoint, string jsonBody, Action<bool, string> onComplete)
    {
        using (UnityWebRequest request = new UnityWebRequest(baseUrl + endpoint, "POST"))
        {
            byte[] bodyBytes = System.Text.Encoding.UTF8.GetBytes(jsonBody ?? "");

            request.uploadHandler = new UploadHandlerRaw(bodyBytes);
            request.downloadHandler = new DownloadHandlerBuffer();
            request.SetRequestHeader("Content-Type", "application/json");
            request.timeout = requestTimeoutSeconds;

            yield return request.SendWebRequest();

            bool success = request.result == UnityWebRequest.Result.Success;
            SetConnected(success);

            onComplete?.Invoke(success, success ? request.downloadHandler.text : null);
        }
    }
}
