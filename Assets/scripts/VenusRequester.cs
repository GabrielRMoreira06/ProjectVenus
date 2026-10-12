using System;
using UnityEngine;

[Serializable]
public class AskRequest
{
    public string text;
}

/// <summary>
/// Single entry point for anything in Unity that wants Venus to react
/// to an event — pokes, and any future trigger. Callers only decide
/// WHEN to ask and WHAT text describes the event (e.g. "user is
/// poking you on your head"); this script just gets that text to
/// Python's /ask endpoint.
///
/// The answer never comes back through this call. It arrives later
/// through ResponseListener's normal polling of /response, same as a
/// monitor-triggered response or anything else — callers of Ask()
/// don't need to do anything else once they've called it.
/// </summary>
public static class VenusRequester
{
    private const string AskEndpoint = "/ask";

    public static void Ask(string text)
    {
        if (PythonConnection.Instance == null)
        {
            Debug.LogWarning("[VenusRequester] No PythonConnection instance found in the scene.");
            return;
        }

        if (string.IsNullOrWhiteSpace(text))
        {
            return;
        }

        string json = JsonUtility.ToJson(new AskRequest { text = text });

        PythonConnection.Instance.StartCoroutine(
            PythonConnection.Instance.Post(AskEndpoint, json, OnAskComplete)
        );
    }

    private static void OnAskComplete(bool success, string responseBody)
    {
        if (!success)
        {
            Debug.LogWarning("[VenusRequester] Failed to reach /ask.");
        }
    }
}