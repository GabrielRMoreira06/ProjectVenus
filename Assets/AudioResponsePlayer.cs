using System.Collections;
using UnityEngine;
using UnityEngine.Networking;

/// <summary>
/// Downloads and plays the audio for each VenusResponse coming from the
/// Python backend. Follows the same pattern as ImageHolder for
/// OPENIMAGE: subscribes to ResponseListener.OnResponseReceived,
/// downloads the content via UnityWebRequest and plays it on the local
/// AudioSource.
///
/// "Silent" responses (e.g. DEADPIXEL) arrive with a null/empty audio
/// field — in that case nothing is played, with no error.
///
/// If a new response arrives while a previous audio is still
/// playing/downloading, the previous one is canceled: the in-progress
/// download is aborted and the AudioSource is stopped, so two lines are
/// never overlapped.
/// </summary>
[RequireComponent(typeof(AudioSource))]
public class AudioResponsePlayer : MonoBehaviour
{
    [Header("References")]
    [Tooltip("ResponseListener that receives responses from the Python backend. If empty, tries to find one in the scene.")]
    public ResponseListener responseListener;

    [Tooltip("AudioSource used to play the speech. If empty, uses the component on the same GameObject.")]
    public AudioSource audioSource;

    [Tooltip("Optional: LipSyncFake to be fed with this AudioSource while the audio plays. If empty, no lip sync is triggered by this script.")]
    public FakeLipSync lipSync;

    [Header("Configuration")]
    [Tooltip("Assumed format of the audio files returned by the backend.")]
    public AudioType audioType = AudioType.MPEG;

    /// <summary>Fired on the exact frame a new speech's playback begins.</summary>
    public event System.Action OnAudioStarted;

    /// <summary>Fired when playback ends (naturally or because it was canceled by a new response).</summary>
    public event System.Action OnAudioFinished;

    private Coroutine currentDownloadAndPlayback;
    private UnityWebRequest currentRequest;

    void Awake()
    {
        if (audioSource == null)
        {
            audioSource = GetComponent<AudioSource>();
        }
    }

    void OnEnable()
    {
        if (responseListener == null)
        {
            responseListener = FindFirstObjectByType<ResponseListener>();
        }

        if (responseListener != null)
        {
            responseListener.OnResponseReceived += HandleResponseReceived;
        }
        else
        {
            Debug.LogWarning("AudioResponsePlayer: no ResponseListener found — audio playback disabled.");
        }
    }

    void OnDisable()
    {
        if (responseListener != null)
        {
            responseListener.OnResponseReceived -= HandleResponseReceived;
        }

        CancelCurrentPlayback();
    }

    void Update()
    {
        if (lipSync != null && audioSource != null && audioSource.isPlaying)
        {
            lipSync.UpdateAnimation(audioSource);
        }
    }

    private void HandleResponseReceived(VenusResponse response)
    {
        if (response == null) return;

        // Silent response (e.g. DEADPIXEL) — no audio to play.
        if (string.IsNullOrEmpty(response.audio))
        {
            return;
        }

        PlayAudio(response.audio);
    }

    /// <summary>
    /// Downloads and plays the audio at the given URL, canceling any
    /// previous download/playback still in progress.
    /// </summary>
    public void PlayAudio(string url)
    {
        if (string.IsNullOrEmpty(url)) return;
        if (audioSource == null)
        {
            Debug.LogWarning("AudioResponsePlayer: no AudioSource available.");
            return;
        }

        CancelCurrentPlayback();

        currentDownloadAndPlayback = StartCoroutine(DownloadAndPlay(url));
    }

    private IEnumerator DownloadAndPlay(string url)
    {
        using (UnityWebRequest request = UnityWebRequestMultimedia.GetAudioClip(url, audioType))
        {
            currentRequest = request;

            yield return request.SendWebRequest();

            currentRequest = null;

            if (request.result != UnityWebRequest.Result.Success)
            {
                // A deliberate abort (a new response arrived) also lands
                // here — silent, not a real error.
                if (request.result != UnityWebRequest.Result.ConnectionError || !request.error.Contains("Aborted"))
                {
                    Debug.LogWarning($"AudioResponsePlayer: failed to download audio '{url}': {request.error}");
                }

                yield break;
            }

            AudioClip clip = DownloadHandlerAudioClip.GetContent(request);
            if (clip == null)
            {
                Debug.LogWarning($"AudioResponsePlayer: audio downloaded from '{url}' could not be decoded.");
                yield break;
            }

            audioSource.clip = clip;
            audioSource.Play();

            OnAudioStarted?.Invoke();

            // Waits for the whole clip to finish (doesn't use a fixed
            // WaitForSeconds: the real clip can vary in duration from the
            // request, and a manual Stop() in CancelCurrentPlayback()
            // needs to be able to interrupt this wait too).
            while (audioSource.isPlaying)
            {
                yield return null;
            }

            currentDownloadAndPlayback = null;
            OnAudioFinished?.Invoke();
        }
    }

    /// <summary>
    /// Cancels any in-progress download and stops the AudioSource, if a
    /// playback is active. Called automatically before playing new audio
    /// and in OnDisable.
    /// </summary>
    public void CancelCurrentPlayback()
    {
        if (currentRequest != null)
        {
            currentRequest.Abort();
            currentRequest = null;
        }

        if (currentDownloadAndPlayback != null)
        {
            StopCoroutine(currentDownloadAndPlayback);
            currentDownloadAndPlayback = null;
        }

        if (audioSource != null && audioSource.isPlaying)
        {
            audioSource.Stop();
            OnAudioFinished?.Invoke();
        }
    }
}