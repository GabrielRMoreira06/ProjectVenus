using UnityEngine;

public class PingPongMover : MonoBehaviour
{
    [SerializeField] private Transform pointA;
    [SerializeField] private Transform pointB;
    [SerializeField] private float moveDuration = 2f;
    [SerializeField] private float waitTime = 3f;
    [SerializeField] private float startDelay = 15f;
    [SerializeField] private AnimationCurve easing = AnimationCurve.EaseInOut(0, 0, 1, 1);

    [Header("References")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    [SerializeField] private ResponseListener responseListener;

    private Coroutine moveRoutine;

    private void Awake()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
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
            Debug.LogWarning("PingPongMover: no ResponseListener found — won't react to JUDGE.");
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
        transform.position = pointA.position;
        transform.rotation = pointA.rotation;
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;
        if (response.action != "JUDGE") return;

        TriggerRoundTrip();
    }

    public void TriggerRoundTrip()
    {
        if (moveRoutine != null) return; // ignore calls while already running (including during the start delay)

        moveRoutine = StartCoroutine(RoundTrip());
    }

    private System.Collections.IEnumerator RoundTrip()
    {
        if (startDelay > 0f)
        {
            yield return new WaitForSeconds(startDelay);
        }

        yield return MoveTo(pointB);
        yield return new WaitForSeconds(waitTime);
        yield return MoveTo(pointA);

        moveRoutine = null;
    }

    private System.Collections.IEnumerator MoveTo(Transform targetPoint)
    {
        Vector3 startPos = transform.position;
        Quaternion startRot = transform.rotation;
        float elapsed = 0f;

        while (elapsed < moveDuration)
        {
            elapsed += Time.deltaTime;
            float t = easing.Evaluate(Mathf.Clamp01(elapsed / moveDuration));
            transform.position = Vector3.Lerp(startPos, targetPoint.position, t);
            transform.rotation = Quaternion.Slerp(startRot, targetPoint.rotation, t);
            yield return null;
        }

        transform.position = targetPoint.position;
        transform.rotation = targetPoint.rotation;
    }
}