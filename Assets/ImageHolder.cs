using System;
using System.Collections;
using System.Diagnostics;
using System.IO;
using UnityEngine;
using UnityEngine.Networking;
using Debug = UnityEngine.Debug;

/// <summary>
/// Downloads an image from a URL and displays it as an object attached
/// to a hand point (or any other Transform), as if the pet were
/// holding a drawing or photo for a while. The image is displayed over
/// a frame (a separate asset). On entry, the image and frame start as
/// a thin line (~0 height) and stretch vertically to their final size.
/// While the image is being shown, an optional ArmReachIK raises the
/// hand toward the image so it visually looks held rather than just
/// floating next to the hand bone.
/// </summary>
public class ImageHolder : MonoBehaviour
{
    [Header("References")]
    [Tooltip("Hand Transform (or equivalent bone) the image will be attached to")]
    public Transform grabPoint;

    [Tooltip("Raises the hand toward the image while it's being held, and lowers it again once the image is cleared. Optional — leave empty to skip the pose entirely.")]
    public ArmReachIK armReachIK;

    [Header("Testing")]
    [Tooltip("While AcaoExecutor hasn't been rebuilt to consume ResponseListener yet, this component listens directly and shows any SHOWIMAGE response on its own — a stand-in so the pipeline is testable end-to-end. Turn this off once AcaoExecutor owns action dispatch instead, to avoid both handling the same response.")]
    public bool listenDirectlyForTesting = true;

    [Tooltip("Found automatically in the scene if left empty.")]
    public ResponseListener responseListener;

    [Header("Configuration")]
    [Tooltip("Size of the displayed image, in world units")]
    public Vector2 imageSize = new Vector2(0.3f, 0.3f);

    [Tooltip("Local offset relative to the grab point (e.g. above the hand)")]
    public Vector3 localPositionOffset = new Vector3(-0.055f, -0.15f, 0f);

    [Tooltip("If checked, the image always faces the camera, ignoring the hand's rotation")]
    public bool faceCamera = true;

    [Tooltip("Extra rotation applied on top of 'face camera' (usually 0,180,0)")]
    public Vector3 extraRotationOffsetEuler = new Vector3(0f, 180f, 0f);

    [Header("Frame")]
    [Tooltip("If checked, displays the frame image behind the downloaded image")]
    public bool showFrame = true;

    [Tooltip("Frame texture (own asset), displayed behind the downloaded image")]
    public Texture2D frameTexture;

    [Tooltip("Maximum box (width, height) the frame can occupy. The texture's original aspect ratio is preserved (the frame shrinks to fit inside this box)")]
    public Vector2 frameSize = new Vector2(0.36f, 0.36f);

    [Tooltip("How much farther from the camera the frame sits relative to the image, to guarantee the image always renders in front")]
    public float frameDistanceBehind = 0.01f;

    [Tooltip("How many seconds she holds the image, by default")]
    public float defaultDuration = 5f;

    [Header("Animation")]
    [Tooltip("Duration of the entrance animation: the image (and frame) start as a thin line at final width and stretch to final height")]
    public float entranceAnimationDuration = 0.25f;

    [Header("Gaze")]
    [Tooltip("If assigned, she looks at the image while it's being shown")]
    public HeadFollowMouseIK headFollow;

    [Header("Click to open")]
    [Tooltip("If checked, clicking the image opens it full-size in the system's default viewer")]
    public bool openOnClick = true;

    private GameObject currentQuad;
    private GameObject currentFrame;
    private Vector2 finalFrameScale;
    private Coroutine currentCoroutine;
    private Texture2D currentTexture;

    void Start()
    {
        if (!listenDirectlyForTesting) return;

        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }

        if (responseListener == null)
        {
            Debug.LogWarning("ImageHolder: listenDirectlyForTesting is on, but no ResponseListener was found in the scene.");
            return;
        }

        responseListener.OnResponseReceived += HandleVenusResponse;
    }

    void OnDestroy()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleVenusResponse;
        }
    }

    /// <summary>
    /// Temporary test wiring — see listenDirectlyForTesting above.
    /// Once AcaoExecutor is rebuilt to read VenusResponse.action itself,
    /// it should call ShowImage() directly instead of this subscribing
    /// on its own.
    /// </summary>
    private void HandleVenusResponse(VenusResponse response)
    {
        print("ImageHolder: HandleVenusResponse called with action: " + response.action + ", image URL: " + response.image);
        if (response.action != "SHOWIMAGE") return;
        if (string.IsNullOrEmpty(response.image)) return;

        ShowImage(response.image);
    }

    public void ShowImage(string url, float duration = -1f)
    {
         
        if (string.IsNullOrEmpty(url)) return;
        if (grabPoint == null)
        {
            Debug.LogWarning("ImageHolder: grabPoint was not set in the Inspector.");
            return;
        }

        if (duration < 0f) duration = defaultDuration;

        if (currentCoroutine != null)
        {
            StopCoroutine(currentCoroutine);
        }

        currentCoroutine = StartCoroutine(ShowImageCoroutine(url, duration));
    }

    private IEnumerator ShowImageCoroutine(string url, float duration)
    {
        UnityWebRequest request = UnityWebRequestTexture.GetTexture(url);
        yield return request.SendWebRequest();

        if (request.result != UnityWebRequest.Result.Success)
        {
            Debug.LogError("ImageHolder: failed to download image: " + request.error);
            yield break;
        }

        Texture2D texture = DownloadHandlerTexture.GetContent(request);

        ClearCurrentImage();

        if (showFrame)
        {
            CreateFrame();
        }

        currentQuad = GameObject.CreatePrimitive(PrimitiveType.Quad);
        currentQuad.name = "HeldImage";

        // Keeps the collider (the Quad already has one) to detect clicks via raycast

        currentQuad.transform.SetParent(grabPoint, false);
        currentQuad.transform.localPosition = localPositionOffset;
        // Starts as a thin line (final width, ~0 height) for the entrance animation
        currentQuad.transform.localScale = new Vector3(imageSize.x, 0f, 1f);
        UpdateRotation();

        currentTexture = texture;
        Material material = CreateDoubleSidedMaterial(texture, null);
        currentQuad.GetComponent<MeshRenderer>().material = material;

        headFollow?.SetTarget(currentQuad.transform);
        armReachIK?.ActivatePose();

        yield return AnimateEntranceHeight(imageSize, finalFrameScale, entranceAnimationDuration);

        float remainingTime = duration - entranceAnimationDuration;
        if (remainingTime > 0f)
        {
            yield return new WaitForSeconds(remainingTime);
        }

        ClearCurrentImage();
    }

    /// <summary>
    /// Animates the image (and frame, if any) from a thin line to its
    /// final height, stretching only the Y axis (width is already at
    /// final size from the start).
    /// </summary>
    private IEnumerator AnimateEntranceHeight(Vector2 finalImageScale, Vector2 targetFinalFrameScale, float duration)
    {
        if (duration <= 0f)
        {
            if (currentQuad != null) currentQuad.transform.localScale = new Vector3(finalImageScale.x, finalImageScale.y, 1f);
            if (currentFrame != null) currentFrame.transform.localScale = new Vector3(targetFinalFrameScale.x, targetFinalFrameScale.y, 1f);
            yield break;
        }

        float elapsedTime = 0f;

        while (elapsedTime < duration)
        {
            if (currentQuad == null) yield break;

            elapsedTime += Time.deltaTime;
            float progress = Mathf.Clamp01(elapsedTime / duration);

            // Simple smoothstep: stretches smoothly, without overshooting final height
            float smoothProgress = progress * progress * (3f - 2f * progress);

            float imageHeight = Mathf.Lerp(0f, finalImageScale.y, smoothProgress);
            currentQuad.transform.localScale = new Vector3(finalImageScale.x, imageHeight, 1f);

            if (currentFrame != null)
            {
                float frameHeight = Mathf.Lerp(0f, targetFinalFrameScale.y, smoothProgress);
                currentFrame.transform.localScale = new Vector3(targetFinalFrameScale.x, frameHeight, 1f);
            }

            yield return null;
        }

        if (currentQuad != null) currentQuad.transform.localScale = new Vector3(finalImageScale.x, finalImageScale.y, 1f);
        if (currentFrame != null) currentFrame.transform.localScale = new Vector3(targetFinalFrameScale.x, targetFinalFrameScale.y, 1f);
    }

    void Update()
    {
        if (openOnClick && currentQuad != null && Input.GetMouseButtonDown(0))
        {
            CheckImageClick();
        }
    }

    private void CheckImageClick()
    {
        if (Camera.main == null) return;

        Ray ray = Camera.main.ScreenPointToRay(Input.mousePosition);

        if (Physics.Raycast(ray, out RaycastHit hit) && hit.collider != null && hit.collider.gameObject == currentQuad)
        {
            OpenFullImage();
        }
    }

    private void OpenFullImage()
    {
        if (currentTexture == null) return;

        byte[] pngBytes = currentTexture.EncodeToPNG();
        string path = Path.Combine(Application.temporaryCachePath, "enlarged_image.png");
        File.WriteAllBytes(path, pngBytes);

        try
        {
            Process.Start(new ProcessStartInfo
            {
                FileName = path,
                UseShellExecute = true
            });
        }
        catch (System.Exception error)
        {
            Debug.LogError("ImageHolder: failed to open the image in the viewer: " + error.Message);
        }
    }

    void LateUpdate()
    {
        if (currentQuad != null)
        {
            UpdateRotation();
        }
    }

    private void UpdateRotation()
    {
        Quaternion rotation;

        if (faceCamera && Camera.main != null)
        {
            rotation = Camera.main.transform.rotation * Quaternion.Euler(extraRotationOffsetEuler);
            currentQuad.transform.rotation = rotation;
        }
        else
        {
            rotation = Quaternion.Euler(extraRotationOffsetEuler);
            currentQuad.transform.localRotation = rotation;
        }

        if (currentFrame != null)
        {
            currentFrame.transform.rotation = currentQuad.transform.rotation;
            PositionFrameBehindImage();
        }
    }

    /// <summary>
    /// Pushes the frame away from the camera (in world space, along the
    /// actual view direction), guaranteeing the image always renders in
    /// front, regardless of the hand's rotation.
    /// </summary>
    private void PositionFrameBehindImage()
    {
        Vector3 backwardDirection = (Camera.main != null)
            ? (currentQuad.transform.position - Camera.main.transform.position).normalized
            : currentQuad.transform.forward;

        currentFrame.transform.position = currentQuad.transform.position + backwardDirection * frameDistanceBehind;
    }

    private void CreateFrame()
    {
        if (frameTexture == null)
        {
            Debug.LogWarning("ImageHolder: frameTexture was not set in the Inspector.");
            return;
        }

        currentFrame = GameObject.CreatePrimitive(PrimitiveType.Quad);
        currentFrame.name = "Frame";

        Destroy(currentFrame.GetComponent<Collider>());

        currentFrame.transform.SetParent(grabPoint, false);
        // Initial position/rotation; PositionFrameBehindImage() and the
        // correct rotation are applied right after, in UpdateRotation()
        currentFrame.transform.localPosition = localPositionOffset;
        currentFrame.transform.localRotation = Quaternion.Euler(extraRotationOffsetEuler);

        finalFrameScale = CalculateScaleWithAspect(frameSize, frameTexture);
        // Starts as a thin line (final width, ~0 height), same as the
        // image, so the entrance animation stretches both together
        currentFrame.transform.localScale = new Vector3(finalFrameScale.x, 0f, 1f);

        // transparent = true: respects the PNG's alpha channel, so the
        // areas outside the frame's artwork are actually transparent
        // (instead of showing up as a solid white rectangle behind the image)
        Material frameMaterial = CreateDoubleSidedMaterial(frameTexture, null, transparent: true);
        currentFrame.GetComponent<MeshRenderer>().material = frameMaterial;
    }

    /// <summary>
    /// Calculates the final scale (width, height) so the texture fits
    /// inside a maximum box without distorting, preserving its original
    /// aspect ratio.
    /// </summary>
    private Vector2 CalculateScaleWithAspect(Vector2 maxSize, Texture2D texture)
    {
        if (texture == null || texture.height == 0) return maxSize;

        float textureAspect = texture.width / (float)texture.height;
        float maxAspect = maxSize.x / maxSize.y;

        if (textureAspect > maxAspect)
        {
            // Texture proportionally wider than the box: clamp on width
            return new Vector2(maxSize.x, maxSize.x / textureAspect);
        }

        // Texture proportionally taller (or equal): clamp on height
        return new Vector2(maxSize.y * textureAspect, maxSize.y);
    }

    private Material CreateDoubleSidedMaterial(Texture texture, Color? color, bool transparent = false)
    {
        Shader urpShader = Shader.Find("Universal Render Pipeline/Unlit");
        Material material;

        if (urpShader != null)
        {
            material = new Material(urpShader);
            // "_Cull" = 0 means "Off" (renders both sides, no back-face culling)
            material.SetFloat("_Cull", 0f);

            if (texture != null) material.mainTexture = texture;
            if (color.HasValue) material.SetColor("_BaseColor", color.Value);

            if (transparent)
            {
                material.SetFloat("_Surface", 1f); // 0 = Opaque, 1 = Transparent
                material.SetFloat("_Blend", 0f);    // 0 = Alpha blend
                material.SetOverrideTag("RenderType", "Transparent");
                material.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
                material.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
                material.SetInt("_ZWrite", 0);
                material.DisableKeyword("_ALPHATEST_ON");
                material.EnableKeyword("_ALPHABLEND_ON");
                material.DisableKeyword("_ALPHAPREMULTIPLY_ON");
                material.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            }
        }
        else
        {
            // Fallback for projects using the Built-in Render Pipeline
            string shaderName = texture != null
                ? (transparent ? "Unlit/Transparent" : "Unlit/Texture")
                : "Unlit/Color";
            material = new Material(Shader.Find(shaderName));

            if (texture != null) material.mainTexture = texture;
            if (color.HasValue) material.color = color.Value;

            if (transparent)
            {
                material.renderQueue = (int)UnityEngine.Rendering.RenderQueue.Transparent;
            }
        }

        return material;
    }

    private void ClearCurrentImage()
    {
        if (currentQuad != null)
        {
            Destroy(currentQuad);
            currentQuad = null;
            headFollow?.ClearTarget();
            armReachIK?.DeactivatePose();
        }

        if (currentFrame != null)
        {
            Destroy(currentFrame);
            currentFrame = null;
        }

        currentTexture = null;

        if (currentCoroutine != null)
        {
            currentCoroutine = null;
        }
    }
}