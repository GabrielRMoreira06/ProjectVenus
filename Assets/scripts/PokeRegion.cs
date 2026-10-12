using UnityEngine;

public class PokeRegion : MonoBehaviour
{
    [Tooltip("Region name used in the Gemini prompt (e.g., 'head', 'arm_left', 'torso')")]
    public string regionName = "body";

    [Tooltip("Bone that should react to the poke. If empty, uses this object's Transform.")]
    public Transform targetBone;

    [Tooltip("Check if the impulse is inverted on this bone (common on left/right bones with mirrored axes)")]
    public bool invertDirection = false;

    void Awake()
    {
        if (targetBone == null)
            targetBone = transform;
    }
}