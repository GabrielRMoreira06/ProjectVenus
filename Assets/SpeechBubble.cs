using System.Collections;
using System.Runtime.InteropServices;
using Kirurobo;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class SpeechBubble : MonoBehaviour
{
    [Header("References")]
    public TextMeshProUGUI text;
    public RectTransform panel;

    [Tooltip("If empty, attempts to find automatically in the scene")]
    public UniWindowController window;

    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, attempts to find one in the scene.")]
    public ResponseListener responseListener;

    [Header("Settings")]
    public float timeOnScreen = 6f;
    public float typingSpeed = 0.03f;

    [Header("Screen Margin")]
    public float screenMargin = 20f;
    public bool keepInsideScreen = true;

    [Tooltip("Check if the bubble is moving in the opposite direction along the vertical axis. Common when using UniWindowController with a transparent background.")]
    public bool invertedYAxis = true;

    private Coroutine hideCoroutine;
    private Coroutine typingCoroutine;
    private Vector3 originalScale;

    private Canvas parentCanvas;
    private RectTransform canvasRect;
    private Camera canvasCamera;

    private Vector3 currentAppliedOffset = Vector3.zero;

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    private const int SM_CXSCREEN = 0;
    private const int SM_CYSCREEN = 1;

    void Awake()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }
    }

    void Start()
    {
        if (panel == null)
            panel = GetComponent<RectTransform>();

        panel.pivot = new Vector2(0.5f, 0f);
        originalScale = transform.localScale;
        transform.localScale = Vector3.zero;

        parentCanvas = GetComponentInParent<Canvas>();
        if (parentCanvas != null)
        {
            canvasRect = parentCanvas.GetComponent<RectTransform>();
            if (parentCanvas.renderMode != RenderMode.ScreenSpaceOverlay)
            {
                canvasCamera = parentCanvas.worldCamera;
                if (canvasCamera == null) canvasCamera = Camera.main;
            }
        }

        if (window == null)
        {
            window = FindFirstObjectByType<UniWindowController>();
        }

        // Event subscription is handled HERE (not in OnEnable/OnDisable)
        // by design: this same script disables its own gameObject below
        // (and again at the end of Hide()) as part of the normal
        // show/hide cycle of the bubble. If subscribed in OnEnable/OnDisable,
        // each time the bubble hides it would unsubscribe from
        // OnResponseReceived — and since that event triggers Show() to
        // reactivate the bubble, it would never receive subsequent
        // responses (deadlock: needs to be subscribed to reactivate,
        // but only reactivates when subscribed).
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("SpeechBubble: No ResponseListener found — speech bubble will not respond to backend responses.");
        }

        gameObject.SetActive(false);
    }

    void OnDestroy()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }
    }

    /// <summary>
    /// Called whenever Python returns a response (via ResponseListener).
    /// Only displays the bubble when there is actual text — silent
    /// responses (e.g., DEADPIXEL action) arrive with empty text and
    /// should not display the bubble.
    /// </summary>
    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (string.IsNullOrEmpty(response.text)) return;

        Show(response.text);
    }

    void LateUpdate()
    {
        if (keepInsideScreen && gameObject.activeInHierarchy)
        {
            panel.localPosition -= currentAppliedOffset;
            currentAppliedOffset = Vector3.zero;

            ClampInsideMonitor();
        }
    }

    public void Show(string message)
    {

        gameObject.SetActive(true);

        if (hideCoroutine != null) StopCoroutine(hideCoroutine);
        if (typingCoroutine != null) StopCoroutine(typingCoroutine);

        StartCoroutine(Appear());
        typingCoroutine = StartCoroutine(TypeText(message));
        hideCoroutine = StartCoroutine(Hide());
    }

    IEnumerator TypeText(string message)
    {
        text.text = "";
        foreach (char letter in message)
        {
            text.text += letter;
            LayoutRebuilder.ForceRebuildLayoutImmediate(panel);
            yield return new WaitForSeconds(typingSpeed);
        }
    }

    IEnumerator Appear()
    {
        Vector3 target = originalScale;
        while (Vector3.Distance(transform.localScale, target) > 0.01f)
        {
            transform.localScale = Vector3.Lerp(transform.localScale, target, Time.deltaTime * 12f);
            yield return null;
        }
        transform.localScale = originalScale;
    }

    IEnumerator Hide()
    {
        yield return new WaitForSeconds(timeOnScreen);
        while (transform.localScale.magnitude > 0.01f)
        {
            transform.localScale = Vector3.Lerp(transform.localScale, Vector3.zero, Time.deltaTime * 10f);
            yield return null;
        }
        gameObject.SetActive(false);
    }

    private void ClampInsideMonitor()
    {
        if (canvasRect == null) return;

        Vector3[] corners = new Vector3[4];
        panel.GetWorldCorners(corners);

#if !UNITY_EDITOR
        if (window != null)
        {
            Vector2 windowPos = window.windowPosition;
            Vector2 windowSize = window.windowSize;

            float desktopTopY = float.MaxValue;
            float desktopBottomY = float.MinValue;
            float desktopMinX = float.MaxValue;
            float desktopMaxX = float.MinValue;

            // Extract absolute bounds by checking the 4 corners
            for (int i = 0; i < 4; i++)
            {
                Vector2 screenPt = RectTransformUtility.WorldToScreenPoint(canvasCamera, corners[i]);
                float deskX = windowPos.x + screenPt.x;
                
                // Y conversion based on screen orientation
                float deskY = invertedYAxis 
                    ? windowPos.y + screenPt.y 
                    : windowPos.y + (windowSize.y - screenPt.y);

                if (deskX < desktopMinX) desktopMinX = deskX;
                if (deskX > desktopMaxX) desktopMaxX = deskX;
                if (deskY < desktopTopY) desktopTopY = deskY;
                if (deskY > desktopBottomY) desktopBottomY = deskY;
            }

            float monitorWidth = GetSystemMetrics(SM_CXSCREEN);
            float monitorHeight = GetSystemMetrics(SM_CYSCREEN);

            float desktopOffsetX = 0f;
            float desktopOffsetY = 0f; // Positive = needs to move DOWN on the monitor

            if (desktopMinX < screenMargin) desktopOffsetX = screenMargin - desktopMinX;
            else if (desktopMaxX > monitorWidth - screenMargin) desktopOffsetX = (monitorWidth - screenMargin) - desktopMaxX;

            if (desktopTopY < screenMargin) desktopOffsetY = screenMargin - desktopTopY;
            else if (desktopBottomY > monitorHeight - screenMargin) desktopOffsetY = (monitorHeight - screenMargin) - desktopBottomY;

            if (desktopOffsetX == 0f && desktopOffsetY == 0f) return;

            // Convert desktop offset back to Unity screen coordinates
            float screenOffsetY = invertedYAxis ? desktopOffsetY : -desktopOffsetY;
            
            ApplyOffset(new Vector2(desktopOffsetX, screenOffsetY));
            return;
        }
#endif
        // Fallback for Unity Editor
        ClampAgainstWindow(corners);
    }

    private void ClampAgainstWindow(Vector3[] corners)
    {
        float screenMinX = float.MaxValue;
        float screenMaxX = float.MinValue;
        float screenTopY = float.MaxValue;
        float screenBottomY = float.MinValue;

        for (int i = 0; i < 4; i++)
        {
            Vector2 pt = RectTransformUtility.WorldToScreenPoint(canvasCamera, corners[i]);
            if (pt.x < screenMinX) screenMinX = pt.x;
            if (pt.x > screenMaxX) screenMaxX = pt.x;

            float visualY = invertedYAxis ? pt.y : (Screen.height - pt.y);

            if (visualY < screenTopY) screenTopY = visualY; // Closer to visual top
            if (visualY > screenBottomY) screenBottomY = visualY; // Closer to visual bottom
        }

        float offsetX = 0f;
        float visualOffsetY = 0f;

        if (screenMinX < screenMargin) offsetX = screenMargin - screenMinX;
        else if (screenMaxX > Screen.width - screenMargin) offsetX = (Screen.width - screenMargin) - screenMaxX;

        if (screenTopY < screenMargin) visualOffsetY = screenMargin - screenTopY;
        else if (screenBottomY > Screen.height - screenMargin) visualOffsetY = (Screen.height - screenMargin) - screenBottomY;

        if (offsetX == 0f && visualOffsetY == 0f) return;

        float screenOffsetY = invertedYAxis ? visualOffsetY : -visualOffsetY;
        ApplyOffset(new Vector2(offsetX, screenOffsetY));
    }

    private void ApplyOffset(Vector2 screenPixelOffset)
    {
        Vector2 currentScreenPos = RectTransformUtility.WorldToScreenPoint(canvasCamera, panel.position);
        Vector2 newScreenPos = currentScreenPos + screenPixelOffset;

        if (RectTransformUtility.ScreenPointToLocalPointInRectangle(
            panel.parent as RectTransform,
            newScreenPos,
            canvasCamera,
            out Vector2 newLocalPos))
        {
            Vector3 localPosBefore = panel.localPosition;
            panel.localPosition = new Vector3(newLocalPos.x, newLocalPos.y, panel.localPosition.z);
            currentAppliedOffset = panel.localPosition - localPosBefore;
        }
    }
}