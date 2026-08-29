using UnityEngine;

public class PokeSpring : MonoBehaviour
{
    [Header("Spring Physics (Fake)")]
    public float stiffness = 120f;
    public float damping = 22f;
    public float maxAngle = 25f;

    [Header("Poke Direction")]
    [Tooltip("If checked, ignores the axis calculated by PokeController and always uses this direction (bone's local space).")]
    public bool useFixedDirection = false;

    [Tooltip("Poke direction in bone local space, manually set in the Inspector. Only used if 'Use Fixed Direction' is enabled.")]
    public Vector3 pokeDirection = Vector3.right;

    private Vector3 angularDisplacement = Vector3.zero;
    private Vector3 angularVelocity = Vector3.zero;

    [Tooltip("If checked, uses the local rotation captured in Awake as a fixed base (required when the bone is NOT overwritten by an Animator each frame, like detached ears).")]
    public bool useFixedBaseRotation = false;

    private Quaternion fixedBaseRotation;

    void Awake()
    {
        fixedBaseRotation = transform.localRotation;
    }

    void LateUpdate()
    {
        // If an Animator overwrites the pose before this LateUpdate,
        // transform.localRotation is already the "raw" base for the frame.
        // If there is NO Animator affecting this bone (e.g., ears not part of the animation),
        // the current rotation already contains the offset written in the
        // previous frame — using it as the base would cause displacement to
        // accumulate indefinitely, preventing the bone from returning to rest.
        Quaternion baseRotation = useFixedBaseRotation ? fixedBaseRotation : transform.localRotation;

        Vector3 springForce = -stiffness * angularDisplacement;
        Vector3 dampingForce = -damping * angularVelocity;

        angularVelocity += (springForce + dampingForce) * Time.deltaTime;
        angularDisplacement += angularVelocity * Time.deltaTime;

        float angleDegrees = angularDisplacement.magnitude * Mathf.Rad2Deg;
        if (angleDegrees > maxAngle)
        {
            angularDisplacement = angularDisplacement.normalized * (maxAngle * Mathf.Deg2Rad);
        }

        Quaternion offsetQuat = AngleAxisFromVector(angularDisplacement);
        transform.localRotation = baseRotation * offsetQuat;
    }

    private Quaternion AngleAxisFromVector(Vector3 vector)
    {
        float angle = vector.magnitude * Mathf.Rad2Deg;
        Vector3 axis = vector.sqrMagnitude > 0.0001f ? vector.normalized : Vector3.up;
        return Quaternion.AngleAxis(angle, axis);
    }

    public void ApplyImpulse(Vector3 localAxis, float force)
    {
        Vector3 finalAxis = useFixedDirection ? pokeDirection.normalized : localAxis.normalized;
        angularVelocity += finalAxis * force;
    }
}