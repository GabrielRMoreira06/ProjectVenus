using UnityEngine;

public class PokeController : MonoBehaviour
{
    [Header("Impulse Settings")]
    public float baseImpulseForce = 15f;

    [Tooltip("How much the force increases with each consecutive poke (multiplier)")]
    public float multiplierPerPoke = 1.3f;

    [Tooltip("Maximum allowed force to prevent excessive values in long streaks")]
    public float maxImpulseForce = 60f;

    [Header("Multi-Poke -> Gemini")]
    public int pokesToTrigger = 3;
    public float pokeTimeWindow = 2f;

    [Header("UI")]
    public SpeechBubble speechBubble;
    
    private int pokeCount = 0;
    private float lastPokeTime = 0f;
    private bool isWaitingResponse = false;

    // Add this so you can assign the bubble in the Inspector (or let Awake auto-find it)



    void Update()
    {
        if (Input.GetMouseButtonDown(0))
        {
            CheckClick();
        }
    }

    private void CheckClick()
    {
        if (Camera.main == null) return;

        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);

        if (!Physics.Raycast(ray, out RaycastHit hit)) return;

        PokeRegion region = hit.collider.GetComponent<PokeRegion>();
        if (region == null) return;

        ProcessPoke(region, hit.point);
    }

    private void ProcessPoke(PokeRegion region, Vector3 hitPoint)
    {
        float now = Time.time;

        if (now - lastPokeTime > pokeTimeWindow)
        {
            pokeCount = 0;
        }

        pokeCount++;
        lastPokeTime = now;

        float scaledForce =
            baseImpulseForce *
            Mathf.Pow(multiplierPerPoke, pokeCount - 1);

        scaledForce = Mathf.Min(
            scaledForce,
            maxImpulseForce
        );

        PokeSpring spring =
            region.targetBone.GetComponent<PokeSpring>();

        if (spring != null)
        {
            Vector3 pokeDirection =
                (region.targetBone.position -
                 Camera.main.transform.position).normalized;

            Vector3 worldAxis =
                Vector3.Cross(pokeDirection, Vector3.up);

            Vector3 localAxis =
                region.targetBone.InverseTransformDirection(worldAxis);

            if (region.invertDirection)
                localAxis = -localAxis;

            spring.ApplyImpulse(
                localAxis,
                scaledForce
            );
        }

        Debug.Log(
            $"[PokeController] Poke on '{region.regionName}' " +
            $"({pokeCount}/{pokesToTrigger}), " +
            $"force: {scaledForce:F1}"
        );

        if (pokeCount >= pokesToTrigger)
        {
            pokeCount = 0;
            TriggerGeminiRequest(region.regionName);

            if (speechBubble != null)
                speechBubble.Show("Thinking...");
        }
    }

    private void TriggerGeminiRequest(string region)
    {
        if (isWaitingResponse) return;

        isWaitingResponse = true;

        string message =
            $"user is poking you on your {region}.";

        VenusRequester.Ask(message);

        // Use the instance instead of a static call
        if (speechBubble != null)
            speechBubble.Show("/n Thinking...");

        else
            Debug.LogWarning("[PokeController] No SpeechBubble assigned to show message.");

        Invoke(nameof(ReleaseWaiting), 1f);
    }

    private void ReleaseWaiting()
    {
        isWaitingResponse = false;
    }
}