using System;
using System.Collections;
using UnityEngine;

/// <summary>
/// Spins a die with a tumbling animation and settles so that the chosen
/// face number points toward the camera.
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

    private bool isRolling;
    private Coroutine rollRoutine;

    /// <summary>Fired with the resulting face number once the roll settles.</summary>
    public event Action<int> OnRollComplete;

    public bool IsRolling => isRolling;

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

        // Independent random speed AND sign per world axis. Combining three
        // simultaneous rotations (rather than one rotation around one random
        // axis) is what actually reads as a tumbling die instead of a spin.
        Vector3 angularSpeed = new Vector3(
            RandomSignedSpeed(),
            RandomSignedSpeed(),
            RandomSignedSpeed());

        // The "free" chaotic orientation, tracked separately from what's
        // actually shown. It keeps accumulating every frame; it's never
        // itself snapped to or paused, which is what removes the seam.
        Quaternion freeSpinRotation = transform.localRotation;

        float elapsed = 0f;
        while (elapsed < rollDuration)
        {
            elapsed += Time.deltaTime;
            float t = Mathf.Clamp01(elapsed / rollDuration);

            float decay = tumbleDecayCurve.Evaluate(t);
            Vector3 frameDelta = angularSpeed * decay * Time.deltaTime;
            freeSpinRotation = Quaternion.Euler(frameDelta) * freeSpinRotation;

            // Continuously blend from the chaotic spin toward the exact
            // result across the WHOLE duration (not a separate phase), so
            // there's no velocity discontinuity to be felt as a stop.
            float blend = lockOnCurve.Evaluate(t);
            transform.localRotation = Quaternion.Slerp(freeSpinRotation, targetFaceRotation, blend);

            yield return null;
        }

        // Snap exactly to the calibrated rotation so the face reads cleanly,
        // with no leftover interpolation error.
        transform.localRotation = targetFaceRotation;
        isRolling = false;
        OnRollComplete?.Invoke(result);
    }

    private float RandomSignedSpeed()
    {
        float magnitude = UnityEngine.Random.Range(tumbleSpeedRange.x, tumbleSpeedRange.y);
        return UnityEngine.Random.value < 0.5f ? -magnitude : magnitude;
    }

#if UNITY_EDITOR
    // --- Calibration helpers -------------------------------------------
    // Use these while setting up faceEulerAngles: rotate the die by hand
    // until a face reads correctly toward the camera, note the Transform's
    // Rotation X/Y/Z in the Inspector, type them into the matching array
    // slot, then use these menu items to verify the snap lands correctly.

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

    public void Update()
    {
        //test roll with space key
        if (Input.GetKeyDown(KeyCode.Space))
        {
            Roll();
        }
    }

}