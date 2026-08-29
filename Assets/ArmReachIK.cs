using UnityEngine;

/// <summary>
/// Uses the Animator's IK (Humanoid) to raise the left hand towards a
/// target, without replacing the base animation (e.g. idle). Used to
/// raise the hand holding the image during the OPENIMAGE action.
/// </summary>
[RequireComponent(typeof(Animator))]
public class ArmReachIK : MonoBehaviour
{
    [Header("References")]
    [Tooltip("Position/rotation target where the left hand should go")]
    public Transform handTarget;

    [Header("Configuration")]
    [Tooltip("Transition speed when enabling/disabling the pose")]
    public float transitionSpeed = 3f;

    private Animator animator;
    private float currentWeight = 0f;
    private float targetWeight = 0f;

    void Awake()
    {
        animator = GetComponent<Animator>();
    }


    public void ActivatePose()
    {
        targetWeight = 1f;
    }

    public void DeactivatePose()
    {
        targetWeight = 0f;
    }

    void OnAnimatorIK(int layerIndex)
    {
        if (handTarget == null) return;

        currentWeight = Mathf.Lerp(currentWeight, targetWeight, Time.deltaTime * transitionSpeed);

        animator.SetIKPositionWeight(AvatarIKGoal.LeftHand, currentWeight);
        animator.SetIKRotationWeight(AvatarIKGoal.LeftHand, currentWeight);

        animator.SetIKPosition(AvatarIKGoal.LeftHand, handTarget.position);
        animator.SetIKRotation(AvatarIKGoal.LeftHand, handTarget.rotation);
    }
}