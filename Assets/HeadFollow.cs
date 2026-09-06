using System.Collections;
using UnityEngine;
using UniVRM10;
using static UniVRM10.VRM10ObjectLookAt;

/// <summary>
/// Makes the head AND the eyes follow the mouse, combining two systems
/// that control DIFFERENT bones — with no conflict between them:
///
/// - EYES: VRM10's native LookAt system (Vrm10Instance.LookAtTarget).
///   By the VRM spec, LookAt only rotates the EYE bones, never the
///   head/neck — that's why migrating to only this made the head stop
///   following the mouse.
/// - HEAD/BODY: the Animator's built-in LookAt IK (SetLookAtWeight),
///   with the EYES' weight forced to 0 — the Animator IK runs during
///   the Animator's evaluation phase, BEFORE the Vrm10Instance's
///   LateUpdate, so when the VRM applies its own LookAt (only to the
///   eyes) on top, the head/body rotation the Animator IK already
///   applied remains intact. Each system touches different bones, so
///   there's no "who writes last" contention.
///
/// The "attention weight" (globalWeight) is used both by the Animator
/// IK (bodyWeight/headWeight) and to interpolate the POSITION of the
/// internal target passed to the VRM (since the VRM's LookAt doesn't
/// expose an adjustable weight when the type is SpecifiedTransform — it
/// always aims at the target with full force, so we simulate the weight
/// by moving the target itself between a neutral position and the real
/// position).
///
/// TWIST LIMITS: "twistLimit" is Unity's Animator clamp value and only
/// ever affected the head/body IK (it's passed as the clampWeight
/// argument of SetLookAtWeight, and eyesWeight is always 0 there — so
/// it never touched the eyes to begin with). The eyes are driven purely
/// by where "internalTarget" sits in world space. "maxEyeAngle" gives
/// the eyes their own, independent angular clamp by limiting how far
/// internalTarget is allowed to sit from the neutral forward direction,
/// completely decoupled from twistLimit.
///
/// EYE DISTANCE: "eyeTargetDistance" is fully independent from
/// "targetDistance" — including the DIRECTION, not just the magnitude.
/// It's not enough to rescale the body's target direction toward a
/// different distance: mainCamera.ScreenToWorldPoint(mousePos) projects
/// the mouse ray at a given depth FROM THE CAMERA, and since the camera
/// and this transform (the head) sit at different world positions, two
/// different depths along the SAME screen pixel's ray produce points
/// that lie in DIFFERENT directions as seen from the head (parallax) —
/// not just different distances. So the eyes get their own mouse
/// projection at eyeTargetDistance (CalculateMouseTargetPosition is now
/// parametrized by depth) and their own smoothed target
/// (currentEyeTargetPosition), computed independently of
/// currentTargetPosition/targetDistance end to end. The only place the
/// two systems still meet is targetOverride, which is an explicit
/// Transform position with no camera involved, so no parallax issue
/// exists there.
/// </summary>
[RequireComponent(typeof(Animator))]
public class HeadFollowMouseIK : MonoBehaviour
{
    [Tooltip("Reference to the model's Vrm10Instance (same GameObject or parent).")]
    public Vrm10Instance vrm10Instance;

    private Animator animator;
    private Camera mainCamera;

    [Header("IK Weights (0 to 1)")]
    [Tooltip("Overall weight: also controls how much the eyes' target moves away from the neutral position towards the real position.")]
    public float globalWeight = 1f;
    [Tooltip("How much the body (torso) participates in turning to look at the target — controlled via Animator IK.")]
    public float bodyWeight = 0.1f;
    [Tooltip("How much the head/neck turn to look at the target — controlled via Animator IK.")]
    public float headWeight = 1f;
    [Tooltip("0 = turns the whole body; 1 = limits the neck and prevents unrealistic rotations. Only affects the Animator's head/body IK (never the eyes).")]
    public float twistLimit = 0.5f;

    [Header("Eye-Specific Limit")]
    [Tooltip("Maximum angle (in degrees) the EYES are allowed to rotate away from the neutral forward direction. Independent from twistLimit — this only clamps the target passed to the VRM's eye LookAt, not the Animator head/body IK.")]
    public float maxEyeAngle = 35f;
    [Tooltip("Distance (world units) from the head at which the EYES' target sits. Independent from Target Distance below, which is only used for the head/body IK and for projecting the mouse into world space. Lower this to make the eyes converge more (cross-eyed look) for close targets, or raise it for a more distant, parallel gaze.")]
    public float eyeTargetDistance = 3f;

    [Header("Mouse Settings (default target)")]
    public float targetDistance = 3f;
    public float positionSmoothing = 5f;

    [Header("Natural Behavior (Attention)")]
    [Tooltip("If true, she will look and randomly look away.")]
    public bool useNaturalGaze = true;
    public float minLookTime = 3f;
    public float maxLookTime = 8f;
    public float minDistractedTime = 1f;
    public float maxDistractedTime = 3f;
    [Tooltip("Speed at which she turns her head when gaining/losing interest")]
    public float weightSmoothing = 3f;

    private Vector3 currentTargetPosition;
    private Vector3 desiredTargetPosition;

    // Eyes get their own independently-smoothed target so that
    // eyeTargetDistance never has to derive from currentTargetPosition
    // (which is projected using targetDistance and would carry that
    // depth's parallax into the eyes' direction — see class doc comment).
    private Vector3 currentEyeTargetPosition;
    private Vector3 desiredEyeTargetPosition;

    private Transform targetOverride;

    // Lightweight internal transform that is what actually gets passed
    // to the Vrm10Instance as LookAtTarget. Never destroyed/recreated —
    // only repositioned every frame. Its position is what the eyes
    // actually track, so this is what we clamp with maxEyeAngle and
    // place at eyeTargetDistance.
    private Transform internalTarget;

    private Vector3 baseNeutralDirection; // "looking forward", captured once in Start

    // Weight control variables
    private float currentGlobalWeight = 0f;
    private float desiredGlobalWeight = 1f;
    private bool externalControlForced = false;

    void Start()
    {
        animator = GetComponent<Animator>();

        if (vrm10Instance == null)
        {
            vrm10Instance = GetComponent<Vrm10Instance>();

            if (vrm10Instance == null)
            {
                vrm10Instance = GetComponentInParent<Vrm10Instance>();
            }
        }

        mainCamera = Camera.main;

        baseNeutralDirection = transform.forward;
        currentTargetPosition = transform.position + baseNeutralDirection * targetDistance;
        currentEyeTargetPosition = transform.position + baseNeutralDirection * eyeTargetDistance;

        internalTarget = new GameObject("HeadFollow_InternalLookAtTarget").transform;
        internalTarget.position = currentEyeTargetPosition;

        if (vrm10Instance != null)
        {
            // Ensures the Vrm10Instance is aiming at our internal target,
            // not at some other Transform manually configured in the
            // Inspector.
            vrm10Instance.LookAtTargetType = LookAtTargetTypes.SpecifiedTransform;
            vrm10Instance.LookAtTarget = internalTarget;
        }
        else
        {
            Debug.LogWarning("HeadFollowMouseIK: Vrm10Instance not found — gaze will not work.");
        }

        StartCoroutine(NaturalGazeRoutine());
    }

    void Update()
    {
        bool hasOverride = targetOverride != null;

        // 1. Sets the desired position — BODY at targetDistance depth,
        // EYES at eyeTargetDistance depth. These are two separate calls
        // to CalculateMouseTargetPosition (one per depth), not one call
        // reused/rescaled, precisely because the camera's parallax means
        // depth changes direction too (see class doc comment). When a
        // Transform override is set there's no camera/depth involved, so
        // both simply target its actual position.
        desiredTargetPosition = hasOverride
            ? targetOverride.position
            : CalculateMouseTargetPosition(targetDistance);

        desiredEyeTargetPosition = hasOverride
            ? targetOverride.position
            : CalculateMouseTargetPosition(eyeTargetDistance);

        // 2. Smooths the POSITION transition of each target independently
        currentTargetPosition = Vector3.Lerp(
            currentTargetPosition,
            desiredTargetPosition,
            Time.deltaTime * positionSmoothing
        );

        currentEyeTargetPosition = Vector3.Lerp(
            currentEyeTargetPosition,
            desiredEyeTargetPosition,
            Time.deltaTime * positionSmoothing
        );

        // 3. Smooths the WEIGHT transition (interpolates between 0 and globalWeight)
        float finalTargetWeight = desiredGlobalWeight * globalWeight;
        currentGlobalWeight = Mathf.Lerp(
            currentGlobalWeight,
            finalTargetWeight,
            Time.deltaTime * weightSmoothing
        );

        // 4. The "weight" becomes a POSITION interpolation: at weight 0,
        // the internal target sits at a neutral position (in front of the
        // head, in the direction captured in Start) — at weight 1, it
        // sits on the real target position. currentTargetPosition (body,
        // at targetDistance) drives the Animator IK below; currentEyeTargetPosition
        // (eyes, at eyeTargetDistance) drives the eyes — computed fully
        // independently, so no depth/parallax leaks from one into the other.
        Vector3 eyeNeutralPosition = transform.position + baseNeutralDirection * eyeTargetDistance;
        Vector3 eyeTargetPosition = Vector3.Lerp(eyeNeutralPosition, currentEyeTargetPosition, currentGlobalWeight);

        // 5. Clamp ONLY the eye target's angle from the neutral forward
        // direction — this is what makes maxEyeAngle fully independent
        // of twistLimit, since it never touches currentTargetPosition
        // (used by the Animator's head/body IK) or twistLimit itself.
        internalTarget.position = ClampToMaxEyeAngle(eyeTargetPosition);
    }

    /// <summary>
    /// Restricts how far a target position can sit, angularly, from
    /// baseNeutralDirection (as seen from this transform), preserving
    /// distance. Used only for the eye target — the head/body IK never
    /// goes through this.
    /// </summary>
    private Vector3 ClampToMaxEyeAngle(Vector3 worldPosition)
    {
        if (maxEyeAngle >= 180f) return worldPosition;

        Vector3 toTarget = worldPosition - transform.position;
        float distance = toTarget.magnitude;
        if (distance < 0.0001f) return worldPosition;

        float angle = Vector3.Angle(baseNeutralDirection, toTarget);
        if (angle <= maxEyeAngle) return worldPosition;

        Vector3 clampedDirection = Vector3.RotateTowards(
            baseNeutralDirection.normalized,
            toTarget.normalized,
            maxEyeAngle * Mathf.Deg2Rad,
            0f
        );

        return transform.position + clampedDirection * distance;
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (animator == null) return;

        if (currentGlobalWeight > 0.01f)
        {
            // eyesWeight fixed at 0: the eyes are already handled by the
            // VRM's LookAt (internalTarget, above) — if we also gave
            // weight here, the two systems would fight over rotating the
            // same bones. twistLimit here only clamps the head/body IK.
            animator.SetLookAtWeight(currentGlobalWeight, bodyWeight, headWeight, 0f, twistLimit);
            animator.SetLookAtPosition(currentTargetPosition);
        }
        else
        {
            animator.SetLookAtWeight(0f);
        }
    }

    /// <summary>
    /// Projects the mouse into world space at the given depth from the
    /// camera. Takes "depth" as a parameter (rather than always reading
    /// targetDistance) so the body and the eyes can each project the
    /// SAME screen-space mouse position at their OWN depth — which also
    /// means each gets its own, correctly-parallaxed direction as seen
    /// from this transform, not just a different distance.
    /// </summary>
    private Vector3 CalculateMouseTargetPosition(float depth)
    {
        Vector3 mousePos = Input.mousePosition;
        mousePos.z = depth;

        // Returns the converted position only if the camera exists
        if (mainCamera != null)
            return mainCamera.ScreenToWorldPoint(mousePos);

        return transform.position + transform.forward * depth;
    }

    private IEnumerator NaturalGazeRoutine()
    {
        while (true)
        {
            if (useNaturalGaze && !externalControlForced)
            {
                // Focuses attention (weight 1)
                desiredGlobalWeight = 1f;
                yield return WaitOrUntilForced(Random.Range(minLookTime, maxLookTime));

                // If it was forced mid-wait, go back to the top of the loop
                // NOW instead of finishing the cycle — this is what makes
                // ResumeNaturalBehavior() take effect immediately, instead
                // of only being noticed up to 11s later (the rest of this
                // wait plus the entire next cycle).
                if (externalControlForced) continue;

                // Loses interest (weight 0) - the head returns to the neutral position
                desiredGlobalWeight = 0f;
                yield return WaitOrUntilForced(Random.Range(minDistractedTime, maxDistractedTime));
            }
            else
            {
                // Pauses the routine while under external control or disabled
                yield return null;
            }
        }
    }

    /// <summary>
    /// Waits 'duration' seconds, BUT checks externalControlForced every
    /// frame and exits early if it becomes true — unlike a raw
    /// WaitForSeconds, which ignores any state change until the full time
    /// has elapsed.
    /// </summary>
    private IEnumerator WaitOrUntilForced(float duration)
    {
        float elapsed = 0f;

        while (elapsed < duration)
        {
            if (externalControlForced) yield break;

            elapsed += Time.deltaTime;
            yield return null;
        }
    }

    // =========================================================
    // PUBLIC API (For other scripts)
    // =========================================================

    /// <summary>
    /// Sets a specific target. If forceAttention is true, she will not
    /// randomly look away.
    /// </summary>
    public void SetTarget(Transform newTarget, bool forceAttention = true)
    {
        targetOverride = newTarget;
        if (forceAttention)
        {
            externalControlForced = true;
            desiredGlobalWeight = 1f;
        }
    }

    /// <summary>
    /// Removes the specific target and returns control to the natural
    /// routine of following the mouse.
    /// </summary>
    public void ClearTarget()
    {
        targetOverride = null;
        externalControlForced = false;
    }

    /// <summary>
    /// Manually turns tracking on or off. Useful if you want to force her
    /// to stop looking for some event.
    /// </summary>
    public void ForceTracking(bool activate)
    {
        externalControlForced = true;
        desiredGlobalWeight = activate ? 1f : 0f;
    }

    /// <summary>
    /// Returns control to the random routine that toggles attention
    /// on/off.
    /// </summary>
    public void ResumeNaturalBehavior()
    {
        externalControlForced = false;
    }
}