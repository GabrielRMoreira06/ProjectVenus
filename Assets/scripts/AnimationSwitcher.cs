using UnityEngine;

public class AnimationSwitcher : MonoBehaviour
{
    [Header("References")]
    [SerializeField] private Animator animator;

    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    [SerializeField] private ResponseListener responseListener;

    [Header("Animator state names (must match the Animator window exactly)")]
    [SerializeField] private string standingState = "Standing Using Touchscreen Tablet";
    [SerializeField] private string relaxingState = "Sitting";
    [SerializeField] private string lookingDownState = "Looking Down";

    [Header("Animation settings")]
    [SerializeField] private float crossFadeDuration = 0.25f;

    [Header("Tablet")]
    [SerializeField] private Transform tablet;
    [SerializeField] private Transform floatAnchor;
    [SerializeField] private float tabletTransitionTime = 0.6f;
    [SerializeField] private float bobAmplitude = 0.02f;
    [SerializeField] private float bobSpeed = 2f;

    [Header("Floating platform")]
    [SerializeField] private GameObject floatingPlatform;

    private Transform handParent;
    private Vector3 handLocalPosition;
    private Quaternion handLocalRotation;

    private bool tabletFloating;
    private float tabletBlend; // 0 = in hand, 1 = floating

    private void Awake()
    {
        if (animator == null)
            animator = GetComponentInChildren<Animator>();

        if (responseListener == null)
            responseListener = FindFirstObjectByType<ResponseListener>();

        if (tablet != null)
        {
            // Remember the original pose in the hand
            handParent = tablet.parent;
            handLocalPosition = tablet.localPosition;
            handLocalRotation = tablet.localRotation;
        }
    }

    private void OnEnable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("AnimationSwitcher: no ResponseListener found — won't react to ANIMATION.");
        }
    }

    private void OnDisable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }
    }

    private void Start()
    {
        // Default animation
        animator.Play(standingState);
        SetPlatformActive(false);
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (string.IsNullOrEmpty(response.animation) || response.animation == "NONE") return;

        ChangeAnimation(response.animation);
    }

    public void ChangeAnimation(string animation)
    {
        if (string.IsNullOrEmpty(animation)) return;

        switch (animation.ToUpperInvariant())
        {
            case "RELAXING":
            case "SITTING":
                Play(relaxingState);
                tabletFloating = true;
                SetPlatformActive(true);
                break;
            case "IDLE":
                Play(lookingDownState);
                tabletFloating = true;
                SetPlatformActive(false);
                break;
            case "WORKING":
                Play(standingState);
                tabletFloating = false;
                SetPlatformActive(false);
                break;
            default:
                Debug.LogWarning($"[AnimationSwitcher] Unknown animation: {animation}");
                break;
        }
    }

    private void Play(string stateName)
    {
        animator.CrossFadeInFixedTime(stateName, crossFadeDuration);
    }

    private void SetPlatformActive(bool active)
    {
        if (floatingPlatform != null)
            floatingPlatform.SetActive(active);
    }

    public void Update()
    {
        //test animation switching with keyboard input
        if (Input.GetKeyDown(KeyCode.Alpha1))
        {
            ChangeAnimation("RELAXING");
        }
        else if (Input.GetKeyDown(KeyCode.Alpha2))
        {
            ChangeAnimation("IDLE");
        }
        else if (Input.GetKeyDown(KeyCode.Alpha3))
        {
            ChangeAnimation("WORKING");
        }
    }

    // LateUpdate so we run after the Animator has posed the hand
    private void LateUpdate()
    {
        if (tablet == null || floatAnchor == null || handParent == null) return;

        float target = tabletFloating ? 1f : 0f;
        float step = Time.deltaTime / Mathf.Max(0.01f, tabletTransitionTime);
        tabletBlend = Mathf.MoveTowards(tabletBlend, target, step);

        // Fully in hand: let the normal parenting do its job
        if (tabletBlend <= 0f)
        {
            tablet.localPosition = handLocalPosition;
            tablet.localRotation = handLocalRotation;
            return;
        }

        float t = Mathf.SmoothStep(0f, 1f, tabletBlend);

        Vector3 handPos = handParent.TransformPoint(handLocalPosition);
        Quaternion handRot = handParent.rotation * handLocalRotation;

        Vector3 bob = Vector3.up * (Mathf.Sin(Time.time * bobSpeed) * bobAmplitude * t);
        Vector3 floatPos = floatAnchor.position + bob;

        tablet.SetPositionAndRotation(
            Vector3.Lerp(handPos, floatPos, t),
            Quaternion.Slerp(handRot, floatAnchor.rotation, t));
    }
}