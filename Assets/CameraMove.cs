using UnityEngine;

public class PingPongMover : MonoBehaviour
{
    [SerializeField] private Transform pointA;
    [SerializeField] private Transform pointB;
    [SerializeField] private float moveDuration = 2f;
    [SerializeField] private float waitTime = 3f;
    [SerializeField] private AnimationCurve easing = AnimationCurve.EaseInOut(0, 0, 1, 1);

    private Coroutine moveRoutine;
    private void Update()
    {
        //test spacebar to trigger the round trip movement
        if (Input.GetKeyDown(KeyCode.Space))
        {
            TriggerRoundTrip();
        }
    }
    private void Start()
    {
        transform.position = pointA.position;
        transform.rotation = pointA.rotation;
    }

    public void TriggerRoundTrip()
    {
        if (moveRoutine != null) return; // ignore calls while already running

        moveRoutine = StartCoroutine(RoundTrip());
    }

    private System.Collections.IEnumerator RoundTrip()
    {
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