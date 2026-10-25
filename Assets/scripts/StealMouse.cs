using System;
using System.Collections;
using System.Runtime.InteropServices;
using UnityEngine;

/// <summary>
/// Makes the cursor drift toward the top-right corner with a jittery
/// "fighting for control" motion. The real cursor is hidden and a fake
/// cursor image is drawn on top of it to sell the "being dragged" look.
/// Triggers automatically when a ResponseListener reports action == "STEALMOUSE".
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

    [Header("Fake cursor")]
    [Tooltip("RectTransform of the cursor Image (the CHILD of the canvas, not the canvas itself). Disabled by default.")]
    public RectTransform fakeCursor;

    [Tooltip("Offset of the fake cursor relative to the real one, in pixels (X = right, Y = down). (0,0) = on top of it.")]
    public Vector2 fakeCursorOffset = Vector2.zero;

    [Tooltip("Pivot of the fake cursor image (0-1). (0,1) = top-left. Put this on the image's 'tip'.")]
    public Vector2 fakeCursorPivot = new Vector2(0f, 1f);
    [Header("Cursor copy")]
    [Tooltip("Image with a normal arrow PNG that replaces the hidden real cursor.")]
    public RectTransform cursorCopy;

    [Header("Pulling hand")]
    [Tooltip("How fast the hand catches up to the arrow. Lower = more lag.")]
    public float handLagSpeed = 6f;

    private Vector2 handPos;
    private bool isRunning = false;
    private IntPtr windowHandle;
    private POINT realStart;
    private Vector2 fakeStartUI;

    private const uint OCR_NORMAL = 32512;
    private const uint SPI_SETCURSORS = 0x0057;

    [DllImport("user32.dll")]
    private static extern bool SetCursorPos(int x, int y);

    [DllImport("user32.dll")]
    private static extern bool GetCursorPos(out POINT lpPoint);

    [DllImport("user32.dll")]
    private static extern bool ScreenToClient(IntPtr hWnd, ref POINT lpPoint);

    [DllImport("user32.dll")]
    private static extern IntPtr CreateCursor(IntPtr hInst, int xHotSpot, int yHotSpot,
        int nWidth, int nHeight, byte[] pvANDPlane, byte[] pvXORPlane);

    [DllImport("user32.dll")]
    private static extern bool SetSystemCursor(IntPtr hcur, uint id);

    [DllImport("user32.dll")]
    private static extern bool SystemParametersInfo(uint uiAction, uint uiParam, IntPtr pvParam, uint fWinIni);

    private struct POINT
    {
        public int X;
        public int Y;
    }

    void Awake()
    {
        if (cursorCopy != null)
        {
            cursorCopy.pivot = new Vector2(0f, 1f);
            cursorCopy.gameObject.SetActive(false);
        }

        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }

        windowHandle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;

        if (fakeCursor != null)
        {
            fakeCursor.pivot = fakeCursorPivot;
            fakeCursor.gameObject.SetActive(false);
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

        RestoreRealCursor();
    }

    void OnApplicationQuit()
    {
        RestoreRealCursor();
    }

    //public void Update()
    //{
      //  // test STEALMOUSE: press spacebar
        //if (Input.GetKeyDown(KeyCode.Space))
        //{
          //  Executar();
        //}
    //}

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

    /// <summary>
    /// Replaces the system arrow with a fully transparent cursor.
    /// </summary>
    private void HideRealCursor()
    {
        byte[] andMask = new byte[128];   // 32x32, 1 bit per pixel
        for (int i = 0; i < andMask.Length; i++) andMask[i] = 0xFF; // keep background
        byte[] xorMask = new byte[128];                              // draw nothing

        IntPtr blank = CreateCursor(IntPtr.Zero, 0, 0, 32, 32, andMask, xorMask);
        SetSystemCursor(blank, OCR_NORMAL);
    }

    /// <summary>
    /// Reloads the user's system cursors from the registry.
    /// </summary>
    private void RestoreRealCursor()
    {
        SystemParametersInfo(SPI_SETCURSORS, 0, IntPtr.Zero, 0);
    }

    /// <summary>
    /// Remembers where the real cursor and the fake cursor start, so the fake
    /// one can follow the real one's movement (works in Editor and builds).
    /// </summary>
    private void BeginFakeCursor(POINT startPos)
    {
        realStart = startPos;

#if UNITY_EDITOR
        // Input.mousePosition is already in Game view pixels.
        fakeStartUI = Input.mousePosition;
#else
        POINT p = startPos;
        ScreenToClient(windowHandle, ref p);
        fakeStartUI = new Vector2(p.X, Screen.height - p.Y);
#endif
    }

    /// <summary>
    /// Places the fake cursor relative to a Windows screen position.
    /// </summary>
    private void UpdateFakeCursor(int screenX, int screenY, bool snap = false)
    {
        float dx = screenX - realStart.X;
        float dy = screenY - realStart.Y;

        // Windows Y goes down, UI Y goes up.
        Vector2 realUI = new Vector2(fakeStartUI.x + dx, fakeStartUI.y - dy);

        // The copy sits exactly where the real cursor is.
        if (cursorCopy != null)
            cursorCopy.position = new Vector3(realUI.x, realUI.y, 0f);

        // The hand follows the copy with a delay.
        if (fakeCursor != null)
        {
            Vector2 target = realUI + new Vector2(fakeCursorOffset.x, -fakeCursorOffset.y);

            if (snap) handPos = target;
            else handPos = Vector2.Lerp(handPos, target, 1f - Mathf.Exp(-handLagSpeed * Time.deltaTime));

            fakeCursor.position = new Vector3(handPos.x, handPos.y, 0f);
        }
    }

    private IEnumerator StealMouseCoroutine()
    {
        isRunning = true;

        HideRealCursor();

        windowHandle = System.Diagnostics.Process.GetCurrentProcess().MainWindowHandle;

        GetCursorPos(out POINT originalPos);

        BeginFakeCursor(originalPos);
        UpdateFakeCursor(originalPos.X, originalPos.Y, true);   // snap on the first frame
        if (cursorCopy != null) cursorCopy.gameObject.SetActive(true);
        if (fakeCursor != null) fakeCursor.gameObject.SetActive(true);

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
            UpdateFakeCursor(newX, newY);

            yield return null;
        }

        // after the while loop, before RestoreRealCursor():
        if (cursorCopy != null) cursorCopy.gameObject.SetActive(false);
        if (fakeCursor != null) fakeCursor.gameObject.SetActive(false);

        RestoreRealCursor();

        isRunning = false;
    }
}