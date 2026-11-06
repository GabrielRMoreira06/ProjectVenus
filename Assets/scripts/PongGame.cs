using System.Runtime.InteropServices;
using Kirurobo;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

/// <summary>
/// Pong against Venus. Venus invites the user by sending action == "PONG"
/// (high energy mood, see MoodController.py): a Play button appears, and
/// clicking it opens and starts a match. Move the mouse vertically to
/// control the right paddle. Venus controls the left one.
///
/// Put this script on an object that is ALWAYS active (not on gameRoot,
/// not on playButton), since both are hidden most of the time. Paddles
/// and ball must be direct children of the playfield; their anchors are
/// forced to center at startup and the paddles are placed on the
/// left/right edges of the playfield automatically.
/// </summary>
public class PongGame : MonoBehaviour
{
    private enum State { Idle, Serving, Playing, GameOver }

    [Header("References")]
    [Tooltip("Parent of everything visual (playfield, avatars, scores). Hidden while no match is running. Must NOT be the object this script is on.")]
    public GameObject gameRoot;
    [Tooltip("Rect that defines the play area. Paddles and ball are its children.")]
    public RectTransform playfield;
    public RectTransform playerPaddle;
    public RectTransform venusPaddle;
    public RectTransform ball;
    public TextMeshProUGUI playerScoreText;
    public TextMeshProUGUI venusScoreText;
    [Tooltip("Optional. Shows 'You win' / 'Venus wins' at the end of a match.")]
    public TextMeshProUGUI statusText;
    [Tooltip("Optional. Window-drag canvas, disabled during a match so moving the mouse doesn't drag the window.")]
    public GameObject dragMoveCanvas;

    [Header("Invitation")]
    [Tooltip("Play button shown when Venus sends action PONG. Must NOT be a child of gameRoot. Keep it above the window-drag canvas in the hierarchy so it receives clicks. If empty, the match starts immediately on PONG.")]
    public Button playButton;
    [Tooltip("Seconds the Play button stays on screen before disappearing if ignored.")]
    public float inviteDuration = 60f;
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, attempts to find one in the scene.")]
    public ResponseListener responseListener;

    [Header("Input")]
    public KeyCode startKey = KeyCode.Space;
    public KeyCode closeKey = KeyCode.Escape;
    [Tooltip("Testing only: allows starting a match with the start key without Venus's invitation. After a match ends, the start key always closes the game.")]
    public bool allowStartKeyWithoutInvite = false;

    [Header("Layout")]
    [Tooltip("Gap between each paddle and the playfield's left/right edge.")]
    public float paddleEdgeMargin = 30f;

    [Header("Screen Border")]
    [Tooltip("The container that gets pushed back inside the monitor. It must contain everything visible (background, playfield, avatars, scores) and should NOT be stretched to fill the whole canvas. If empty, uses gameRoot.")]
    public RectTransform boardPanel;
    [Tooltip("If empty, attempts to find automatically in the scene.")]
    public UniWindowController window;
    public float screenMargin = 20f;
    public bool keepInsideScreen = true;
    [Tooltip("Check if the board moves in the opposite direction along the vertical axis. Same setting as the SpeechBubble.")]
    public bool invertedYAxis = true;

    [Header("Rules")]
    public int scoreToWin = 5;
    public float serveDelay = 1f;
    [Range(0f, 1f)] public float scoreReactionChance = 0.5f;

    [Header("Ball")]
    public float ballStartSpeed = 450f;
    public float ballSpeedIncrease = 1.06f;
    public float ballMaxSpeed = 1100f;
    [Tooltip("Max angle (degrees) the ball leaves a paddle at, reached when hitting its very edge.")]
    public float maxBounceAngle = 55f;

    [Header("Venus AI")]
    public float venusMaxSpeed = 380f;
    [Tooltip("Max distance (UI units) Venus's aim is randomly off from the ball.")]
    public float venusAimError = 40f;
    public float venusErrorRefreshSeconds = 0.6f;

    private State state = State.Idle;
    private Camera uiCamera;
    private Vector2 ballVelocity;
    private int playerScore;
    private int venusScore;
    private int serveDirection = 1;
    private float serveTimer;
    private float venusError;
    private float venusErrorTimer;
    private bool inviteOpen;
    private float inviteTimer;
    private Vector3 currentAppliedOffset = Vector3.zero;

    [DllImport("user32.dll")]
    private static extern int GetSystemMetrics(int nIndex);

    private const int SM_CXSCREEN = 0;
    private const int SM_CYSCREEN = 1;

    void Awake()
    {
        if (gameRoot == null || playfield == null || playerPaddle == null || venusPaddle == null || ball == null)
        {
            Debug.LogWarning("PongGame: gameRoot, playfield, paddles and ball must all be assigned in the Inspector.");
            enabled = false;
            return;
        }

        if (gameRoot == gameObject)
        {
            Debug.LogWarning("PongGame: this script is on gameRoot itself — it would never see responses while hidden. Move it to an always-active object.");
        }

        CenterAnchors(playerPaddle);
        CenterAnchors(venusPaddle);
        CenterAnchors(ball);

        if (boardPanel == null)
        {
            boardPanel = gameRoot.GetComponent<RectTransform>();
        }

        Canvas canvas = playfield.GetComponentInParent<Canvas>();
        if (canvas != null)
        {
            canvas = canvas.rootCanvas;
            if (canvas.renderMode != RenderMode.ScreenSpaceOverlay)
            {
                uiCamera = canvas.worldCamera != null ? canvas.worldCamera : Camera.main;
            }
        }

        if (playButton != null)
        {
            playButton.onClick.AddListener(OnPlayClicked);
            playButton.gameObject.SetActive(false);
        }

        gameRoot.SetActive(false);
    }

    void Start()
    {
        if (window == null)
        {
            window = FindFirstObjectByType<UniWindowController>();
        }

        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }

        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("PongGame: no ResponseListener found — won't react to PONG.");
        }
    }

    void OnDestroy()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }

        if (playButton != null)
        {
            playButton.onClick.RemoveListener(OnPlayClicked);
        }
    }

    void OnDisable()
    {
        if (dragMoveCanvas != null) dragMoveCanvas.SetActive(true);
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (response.action != "PONG") return;
        if (state != State.Idle) return;

        if (playButton == null)
        {
            StartMatch();
            return;
        }

        inviteOpen = true;
        inviteTimer = inviteDuration;
        playButton.gameObject.SetActive(true);
    }

    private void OnPlayClicked()
    {
        if (state != State.Idle) return;

        StartMatch();
    }

    private void HideInvite()
    {
        inviteOpen = false;

        if (playButton != null)
        {
            playButton.gameObject.SetActive(false);
        }
    }

    void Update()
    {
        if (inviteOpen)
        {
            inviteTimer -= Time.deltaTime;
            if (inviteTimer <= 0f) HideInvite();
        }

        if (state != State.Idle && Input.GetKeyDown(closeKey))
        {
            CloseMatch();
            return;
        }

        if (state == State.GameOver && Input.GetKeyDown(startKey))
        {
            CloseMatch();
            return;
        }

        if (state == State.Idle && allowStartKeyWithoutInvite && Input.GetKeyDown(startKey))
        {
            StartMatch();
        }

        if (state == State.Idle || state == State.GameOver) return;

        float dt = Mathf.Min(Time.deltaTime, 0.033f);

        MovePlayer();
        MoveVenus(dt);

        if (state == State.Serving)
        {
            serveTimer -= dt;
            if (serveTimer <= 0f) LaunchBall();
            return;
        }

        MoveBall(dt);
    }

    void LateUpdate()
    {
        if (!keepInsideScreen || boardPanel == null || !gameRoot.activeInHierarchy) return;

        ResetClampOffset();
        ClampInsideMonitor();
    }

    private void ResetClampOffset()
    {
        if (boardPanel == null) return;

        boardPanel.localPosition -= currentAppliedOffset;
        currentAppliedOffset = Vector3.zero;
    }

    private void ClampInsideMonitor()
    {
        Vector3[] corners = new Vector3[4];
        boardPanel.GetWorldCorners(corners);

#if !UNITY_EDITOR
        if (window != null)
        {
            Vector2 windowPos = window.windowPosition;
            Vector2 windowSize = window.windowSize;

            float desktopTopY = float.MaxValue;
            float desktopBottomY = float.MinValue;
            float desktopMinX = float.MaxValue;
            float desktopMaxX = float.MinValue;

            for (int i = 0; i < 4; i++)
            {
                Vector2 screenPt = RectTransformUtility.WorldToScreenPoint(uiCamera, corners[i]);
                float deskX = windowPos.x + screenPt.x;

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
            float desktopOffsetY = 0f;

            if (desktopMinX < screenMargin) desktopOffsetX = screenMargin - desktopMinX;
            else if (desktopMaxX > monitorWidth - screenMargin) desktopOffsetX = (monitorWidth - screenMargin) - desktopMaxX;

            if (desktopTopY < screenMargin) desktopOffsetY = screenMargin - desktopTopY;
            else if (desktopBottomY > monitorHeight - screenMargin) desktopOffsetY = (monitorHeight - screenMargin) - desktopBottomY;

            if (desktopOffsetX == 0f && desktopOffsetY == 0f) return;

            float screenOffsetY = invertedYAxis ? desktopOffsetY : -desktopOffsetY;

            ApplyOffset(new Vector2(desktopOffsetX, screenOffsetY));
            return;
        }
#endif
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
            Vector2 pt = RectTransformUtility.WorldToScreenPoint(uiCamera, corners[i]);
            if (pt.x < screenMinX) screenMinX = pt.x;
            if (pt.x > screenMaxX) screenMaxX = pt.x;

            float visualY = invertedYAxis ? pt.y : (Screen.height - pt.y);

            if (visualY < screenTopY) screenTopY = visualY;
            if (visualY > screenBottomY) screenBottomY = visualY;
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
        RectTransform parent = boardPanel.parent as RectTransform;
        if (parent == null) return;

        Vector2 currentScreenPos = RectTransformUtility.WorldToScreenPoint(uiCamera, boardPanel.position);
        Vector2 newScreenPos = currentScreenPos + screenPixelOffset;

        if (RectTransformUtility.ScreenPointToLocalPointInRectangle(
            parent, newScreenPos, uiCamera, out Vector2 newLocalPos))
        {
            Vector3 localPosBefore = boardPanel.localPosition;
            boardPanel.localPosition = new Vector3(newLocalPos.x, newLocalPos.y, boardPanel.localPosition.z);
            currentAppliedOffset = boardPanel.localPosition - localPosBefore;
        }
    }

    private static void CenterAnchors(RectTransform rect)
    {
        rect.anchorMin = new Vector2(0.5f, 0.5f);
        rect.anchorMax = new Vector2(0.5f, 0.5f);
        rect.pivot = new Vector2(0.5f, 0.5f);
    }

    private void PlacePaddles()
    {
        float halfWidth = playfield.rect.width * 0.5f;

        venusPaddle.anchoredPosition = new Vector2(
            -halfWidth + paddleEdgeMargin + Half(venusPaddle).x, 0f);
        playerPaddle.anchoredPosition = new Vector2(
            halfWidth - paddleEdgeMargin - Half(playerPaddle).x, 0f);
    }

    private void StartMatch()
    {
        HideInvite();

        playerScore = 0;
        venusScore = 0;
        UpdateScoreTexts();

        serveDirection = Random.value < 0.5f ? -1 : 1;

        gameRoot.SetActive(true);
        if (dragMoveCanvas != null) dragMoveCanvas.SetActive(false);

        PlacePaddles();
        BeginServe();
    }

    private void CloseMatch()
    {
        ResetClampOffset();
        state = State.Idle;
        gameRoot.SetActive(false);
        if (dragMoveCanvas != null) dragMoveCanvas.SetActive(true);
    }

    private void BeginServe()
    {
        state = State.Serving;
        serveTimer = serveDelay;
        ballVelocity = Vector2.zero;
        ball.anchoredPosition = Vector2.zero;
        SetStatus("");
    }

    private void LaunchBall()
    {
        float angle = Random.Range(-25f, 25f) * Mathf.Deg2Rad;
        ballVelocity = new Vector2(Mathf.Cos(angle) * serveDirection, Mathf.Sin(angle)) * ballStartSpeed;
        state = State.Playing;
    }

    private void MovePlayer()
    {
        if (RectTransformUtility.ScreenPointToLocalPointInRectangle(
            playfield, Input.mousePosition, uiCamera, out Vector2 local))
        {
            SetPaddleY(playerPaddle, local.y - playfield.rect.center.y);
        }
    }

    private void MoveVenus(float dt)
    {
        venusErrorTimer -= dt;
        if (venusErrorTimer <= 0f)
        {
            venusErrorTimer = venusErrorRefreshSeconds;
            venusError = Random.Range(-venusAimError, venusAimError);
        }

        bool ballComing = state == State.Playing && ballVelocity.x < 0f;
        float targetY = ballComing ? ball.anchoredPosition.y + venusError : 0f;

        float newY = Mathf.MoveTowards(venusPaddle.anchoredPosition.y, targetY, venusMaxSpeed * dt);
        SetPaddleY(venusPaddle, newY);
    }

    private void SetPaddleY(RectTransform paddle, float y)
    {
        float limit = Mathf.Max(0f, playfield.rect.height * 0.5f - Half(paddle).y);
        Vector2 position = paddle.anchoredPosition;
        position.y = Mathf.Clamp(y, -limit, limit);
        paddle.anchoredPosition = position;
    }

    private void MoveBall(float dt)
    {
        Vector2 position = ball.anchoredPosition + ballVelocity * dt;
        Vector2 ballHalf = Half(ball);
        float halfWidth = playfield.rect.width * 0.5f;
        float halfHeight = playfield.rect.height * 0.5f;

        if (position.y + ballHalf.y > halfHeight)
        {
            position.y = halfHeight - ballHalf.y;
            ballVelocity.y = -Mathf.Abs(ballVelocity.y);
        }
        else if (position.y - ballHalf.y < -halfHeight)
        {
            position.y = -halfHeight + ballHalf.y;
            ballVelocity.y = Mathf.Abs(ballVelocity.y);
        }

        if (ballVelocity.x > 0f) TryBounce(playerPaddle, ref position, -1);
        else if (ballVelocity.x < 0f) TryBounce(venusPaddle, ref position, 1);

        ball.anchoredPosition = position;

        if (position.x - ballHalf.x > halfWidth) Score(false);
        else if (position.x + ballHalf.x < -halfWidth) Score(true);
    }

    private void TryBounce(RectTransform paddle, ref Vector2 position, int directionAfter)
    {
        Vector2 paddleHalf = Half(paddle);
        Vector2 ballHalf = Half(ball);
        Vector2 paddlePosition = paddle.anchoredPosition;

        if ((position.x - paddlePosition.x) * -directionAfter > 0f) return;
        if (Mathf.Abs(position.x - paddlePosition.x) > paddleHalf.x + ballHalf.x) return;
        if (Mathf.Abs(position.y - paddlePosition.y) > paddleHalf.y + ballHalf.y) return;

        float offset = Mathf.Clamp((position.y - paddlePosition.y) / (paddleHalf.y + ballHalf.y), -1f, 1f);
        float angle = offset * maxBounceAngle * Mathf.Deg2Rad;
        float speed = Mathf.Min(ballVelocity.magnitude * ballSpeedIncrease, ballMaxSpeed);

        ballVelocity = new Vector2(Mathf.Cos(angle) * directionAfter, Mathf.Sin(angle)) * speed;
        position.x = paddlePosition.x + directionAfter * (paddleHalf.x + ballHalf.x);
    }

    private void Score(bool playerScored)
    {
        if (playerScored) playerScore++;
        else venusScore++;

        UpdateScoreTexts();

        if (playerScore >= scoreToWin || venusScore >= scoreToWin)
        {
            state = State.GameOver;
            ballVelocity = Vector2.zero;
            SetStatus(playerScored ? $"You win! [{startKey}] to close" : $"Venus wins! [{startKey}] to close");
            VenusRequester.Ask(
                $"[SYSTEM MESSAGE: GAME END, {(playerScored ? "User" : "Venus")} won, score: User {playerScore} - Venus {venusScore}]");
            return;
        }

        if (Random.value < scoreReactionChance)
        {
            VenusRequester.Ask(
                $"[SYSTEM MESSAGE: {(playerScored ? "User" : "Venus")} scored, current score user: {playerScore}. Venus: {venusScore}]");
        }

        serveDirection = playerScored ? -1 : 1;
        BeginServe();
    }

    private void UpdateScoreTexts()
    {
        if (playerScoreText != null) playerScoreText.text = playerScore.ToString();
        if (venusScoreText != null) venusScoreText.text = venusScore.ToString();
    }

    private void SetStatus(string message)
    {
        if (statusText != null) statusText.text = message;
    }

    private static Vector2 Half(RectTransform rect)
    {
        return new Vector2(
            rect.rect.width * Mathf.Abs(rect.localScale.x),
            rect.rect.height * Mathf.Abs(rect.localScale.y)) * 0.5f;
    }
}