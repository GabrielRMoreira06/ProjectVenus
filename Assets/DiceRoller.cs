using System;
using System.Collections;
using UnityEngine;

/// <summary>
/// Spins a die with a tumbling animation and settles so that the chosen
/// face number points toward the camera.
///
/// Disabled by default — only becomes active when a VenusResponse with
/// action == "DICE" arrives (same activation pattern as
/// AllowPetController/FlipController). Once the roll settles,
/// VenusRequester.Ask() reports the result back to the Python backend as
/// a new user-category message; Venus's reaction to it arrives later,
/// normally, via ResponseListener — this script doesn't wait for it.
///
/// This does NOT guess the die's geometry. You must calibrate it once:
/// rotate the die by hand in the Scene view (or use the context menu
/// helpers below) until face 1 is pointing at the camera, then copy the
/// Transform's Rotation values from the Inspector into faceEulerAngles[0].
/// Repeat for faces 2 through 6.
/// </summary>
public class DiceRoller : MonoBehaviour
{
    [Header("Face Calibration")]
    [Tooltip("Local Euler rotation that makes face N point toward the camera. Index 0 = face 1 ... index 5 = face 6.")]
    [SerializeField] private Vector3[] faceEulerAngles = new Vector3[6];

    [Header("Roll Settings")]
    [Tooltip("Total time for the whole roll animation.")]
    [SerializeField] private float rollDuration = 1.2f;
    [Tooltip("Min/max angular speed (degrees/sec), randomized independently and with a random sign for each world axis (X, Y, Z), so the tumble reads as a chaotic dice roll rather than a spin around one axis.")]
    [SerializeField] private Vector2 tumbleSpeedRange = new Vector2(480f, 900f);
    [Tooltip("Shapes how the chaotic tumble's speed decays over rollDuration. Default goes from full speed (1) to stopped (0), so it isn't still spinning fast right as it locks onto the result.")]
    [SerializeField] private AnimationCurve tumbleDecayCurve = new AnimationCurve(new Keyframe(0, 1), new Keyframe(1, 0));
    [Tooltip("Shapes how quickly the roll locks onto the final face over rollDuration (0 = pure tumble, 1 = exact result). A single continuous curve across the whole duration avoids any visible seam or restart.")]
    [SerializeField] private AnimationCurve lockOnCurve = AnimationCurve.EaseInOut(0, 0, 1, 1);

    [Header("Venus Integration")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    public ResponseListener responseListener;

    [Tooltip("Seconds to keep the die visible after it settles, before hiding again (gameObject.SetActive(false)).")]
    public float visibleAfterRollDuration = 2.5f;

    private bool isRolling;
    private Coroutine rollRoutine;

    /// <summary>Fired with the resulting face number once the roll settles.</summary>
    public event Action<int> OnRollComplete;

    public bool IsRolling => isRolling;

    void Awake()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }
    }

    void Start()
    {
        // Subscribed here, not OnEnable/OnDisable — same reasoning as
        // AllowPetController/SpeechBubble: this script disables its own
        // GameObject as part of the normal cycle (see Encerrar() below).
        // Subscribing in OnEnable would unsubscribe on every hide, and
        // since HandleResponseReceived is what reactivates the die, it
        // would never receive the next DICE action.
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("DiceRoller: no ResponseListener found — won't react to DICE.");
        }

        // Starts hidden — only after subscribing above, same ordering
        // reason as AllowPetController.Start().
        gameObject.SetActive(false);
    }

    void OnDestroy()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (response.action != "DICE") return;

        gameObject.SetActive(true);
        Roll();
    }

    /// <summary>Rolls a random face (1-6).</summary>
    public void Roll()
    {
        Roll(UnityEngine.Random.Range(1, 7));
    }

    /// <summary>Rolls and settles on a specific face (1-6).</summary>
    public void Roll(int result)
    {
        if (result < 1 || result > 6)
        {
            Debug.LogError($"DiceRoller: result must be between 1 and 6, got {result}");
            return;
        }

        if (faceEulerAngles.Length != 6)
        {
            Debug.LogError("DiceRoller: faceEulerAngles must have exactly 6 entries (one per face). Calibrate in the Inspector first.");
            return;
        }

        if (rollRoutine != null)
            StopCoroutine(rollRoutine);

        rollRoutine = StartCoroutine(RollRoutine(result));
    }

    private IEnumerator RollRoutine(int result)
    {
        isRolling = true;

        Quaternion targetFaceRotation = Quaternion.Euler(faceEulerAngles[result - 1]);

        Vector3 angularSpeed = new Vector3(
            RandomSignedSpeed(),
            RandomSignedSpeed(),
            RandomSignedSpeed());

        Quaternion freeSpinRotation = transform.localRotation;

        float elapsed = 0f;
        while (elapsed < rollDuration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / rollDuration);

            float decay = tumbleDecayCurve.Evaluate(t);
            Vector3 frameDelta = angularSpeed * decay * Time.deltaTime;
            freeSpinRotation = Quaternion.Euler(frameDelta) * freeSpinRotation;

            float blend = lockOnCurve.Evaluate(t);
            transform.localRotation = Quaternion.Slerp(freeSpinRotation, targetFaceRotation, blend);

            yield return null;
        }

        transform.localRotation = targetFaceRotation;
        isRolling = false;
        OnRollComplete?.Invoke(result);

        NotifyResult(result);

        yield return new WaitForSeconds(visibleAfterRollDuration);

        gameObject.SetActive(false);
    }

    /// <summary>
    /// Reports the roll back to the Python backend via VenusRequester —
    /// same entry point PokeController/AllowPetController use. The
    /// message goes into the normal /ask -> Category.USER pipeline;
    /// Venus's reaction arrives later, normally, via ResponseListener.
    /// </summary>
    private void NotifyResult(int result)
    {
        VenusRequester.Ask($"[SYSTEM MESSAGE: The dice you rolled landed on {result}.]");
    }

    private float RandomSignedSpeed()
    {
        float magnitude = UnityEngine.Random.Range(tumbleSpeedRange.x, tumbleSpeedRange.y);
        return UnityEngine.Random.value < 0.5f ? -magnitude : magnitude;
    }

#if UNITY_EDITOR
    [ContextMenu("Calibration/Snap To Face 1")]
    private void SnapFace1() => SnapTo(0);
    [ContextMenu("Calibration/Snap To Face 2")]
    private void SnapFace2() => SnapTo(1);
    [ContextMenu("Calibration/Snap To Face 3")]
    private void SnapFace3() => SnapTo(2);
    [ContextMenu("Calibration/Snap To Face 4")]
    private void SnapFace4() => SnapTo(3);
    [ContextMenu("Calibration/Snap To Face 5")]
    private void SnapFace5() => SnapTo(4);
    [ContextMenu("Calibration/Snap To Face 6")]
    private void SnapFace6() => SnapTo(5);

    private void SnapTo(int index)
    {
        if (faceEulerAngles == null || faceEulerAngles.Length <= index) return;
        transform.localRotation = Quaternion.Euler(faceEulerAngles[index]);
    }

    [ContextMenu("Test Roll (Random)")]
    private void TestRollRandom() => Roll();
#endif
}