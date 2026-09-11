// AnnunciatorHorn.cs
using UnityEngine;

// The panel audible: the horn that blips while any window is flashing, and
// stops when the panel is acknowledged.
//
// PUT ONE ON EACH RACK. A horn takes its flash group from the rack it sits on,
// and plays through its own AudioSource, so the sound comes from that rack's
// place on the wall - but the blips themselves are timed by the group's shared
// blip clock (AnnunciatorFlashGroups), so every rack in a group sounds on the
// same frame. Two racks blipping out of step would read as two separate panels
// in trouble; one panel, however wide, should sound like one panel.
//
// It needs nothing from the server beyond what the windows already carry. A
// window coming in joins its group, the audible count goes above zero and the
// horn starts; acknowledging stops the flash, the count drops and the horn
// stops. That is the same contact driving the lamp and the horn on a real panel.
//
// SILENCE is the one place the two part company. A silenced window keeps
// flashing and leaves the AUDIBLE count, so the panel goes quiet with its lamps
// untouched - and because silence is per window, the next alarm to come in
// takes that count off zero again and this sounds. Nothing here has to know
// that: it reads the audible count and the count says it.
//
// Each blip is instant attack and long release - a struck horn ringing off,
// not a tone being faded in and out. The clip is a seamless loop and the
// envelope is applied here, so the release can outlast a blip interval (which
// turns distinct blips into a pulsing hold) without the clip having to change.
// Level is applied squared, so a linear ramp is heard as a natural decay.
//
// THE TWO RATES HAVE SEPARATE SOUNDS, so a rack wants TWO horns: one on
// `announce` (an alarm is in) and one on `clear` (ringback - it is over). The
// ear has to tell them apart from across the room without reading a legend, so
// the ringback is lower, smooth and quieter rather than just slower. Adding the
// component picks the clip that matches its rate, so set the rate first and
// then Reset it if you change your mind.
//
// ONE HORN PER OBJECT: a horn owns its AudioSource, and two of them sharing
// one source would fight over its volume every frame, so DisallowMultipleComponent
// stops the second one going on here. The second horn goes on a CHILD object of
// the rack, with its own source - which is also what two horns physically are.
// Right-click this component > "Add The Other Horn" builds it, set up and
// carrying the right clip; the child still finds the rack through its parents,
// so it joins the same group.
//
// The clips (Assets/Audio/AnnunciatorHorn.wav, AnnunciatorRingback.wav) are
// generated, not recorded - see misc/tools/make_alarm_horn_wav.py to change
// either sound and rebuild both. They are mono because Unity only spatialises
// mono clips.
[RequireComponent(typeof(AudioSource))]
[DisallowMultipleComponent]
public class AnnunciatorHorn : MonoBehaviour
{
    private const string AnnounceClipPath = "Assets/Audio/AnnunciatorHorn.wav";
    private const string ClearClipPath = "Assets/Audio/AnnunciatorRingback.wav";

    // Starting levels for the two rates. A ringback says "this is over" - it has
    // to be heard without being answered, so it comes in well under the alarm.
    private const float AlarmVolume = 0.8f;
    private const float RingbackVolume = 0.55f;

    [Header("What it answers to")]
    [Tooltip("Flash group to listen to. Empty = the group of the rack this horn is on; if it is not on a rack, any flashing window on any rack.")]
    [SerializeField] private string _flashGroup = "";

    [Tooltip("Which flash rate this horn answers: \"announce\" for unacknowledged alarms, \"clear\" for ringback. The two have separate sounds, so a rack wants one horn on each - set this, then Reset the component to pull the matching clip.")]
    [SerializeField] private string _flashRate = AnnunciatorFlashGroups.AnnounceRate;

    [Header("Blips")]
    [Tooltip("Blips a second: 2 while an alarm is unacknowledged, 1 for ringback. Shared by every horn in the group - the first to register sets it. 0 holds the horn on continuously instead of blipping.")]
    [Range(0f, 8f)] [SerializeField] private float _blipsPerSecond = 2f;

    [Header("Envelope")]
    [Tooltip("Volume at the top of a blip. The alarm horn sits at 0.8 so there is " +
             "somewhere above it to go; the ringback is quieter still - it is an " +
             "advisory, and the room should not react to it the same way.")]
    [Range(0f, 1f)] [SerializeField] private float _volume = AlarmVolume;

    [Tooltip("Attack, seconds. Instant to the ear - long enough only to keep the blip from clicking.")]
    [Range(0f, 0.2f)] [SerializeField] private float _attackSeconds = 0.004f;

    [Tooltip("Release, seconds. How long a blip takes to die away. Longer than the blip interval and the horn pulses rather than blips.")]
    [Range(0f, 3f)] [SerializeField] private float _releaseSeconds = 1.6f;

    [Header("Testing")]
    [Tooltip("Sound the horn regardless of what the panel is doing - SILENCE included.")]
    [SerializeField] private bool _forceOn = false;

    private AudioSource _source;
    private AnnunciatorRack _rack;
    private string _declaredGroup;
    private float _declaredBlipSeconds = -1f;

    private float _level;
    private bool _attacking;
    private int _lastBlip = int.MinValue;
    private bool _warned;

    // 0 between blips, 1 at the top of one: the envelope before the curve is
    // applied. Useful to anything that should follow the horn.
    public float Level => _level;
    public bool Sounding => _level > 0f;

    // Explicit group, else the rack we are mounted on, else the default group.
    // Only the blip clock needs a concrete name; a horn with no group of its
    // own still LISTENS to every rack - see PanelFlashing.
    public string Group
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(_flashGroup))
                return _flashGroup.Trim();

            if (_rack != null)
                return _rack.FlashGroup;

            return AnnunciatorFlashGroups.DefaultGroup;
        }
    }

    private float BlipSeconds => _blipsPerSecond > 0f ? 1f / _blipsPerSecond : 0f;

    // The generated clip that goes with this horn's rate.
    private string ClipPath =>
        AnnunciatorFlashGroups.NormalizeRate(_flashRate) == AnnunciatorFlashGroups.ClearRate
            ? ClearClipPath
            : AnnounceClipPath;

    private void Awake()
    {
        _source = GetComponent<AudioSource>();
        _source.loop = true;
        _source.playOnAwake = false;
        _source.volume = 0f;

        _rack = GetComponentInParent<AnnunciatorRack>();
    }

    private void OnEnable()
    {
        DeclareBlipRate();
    }

    private void OnDisable()
    {
        _level = 0f;
        _attacking = false;
        _lastBlip = int.MinValue;

        if (_source != null)
        {
            _source.volume = 0f;
            _source.Stop();
        }
    }

    private void Update()
    {
        if (_source.clip == null)
        {
            if (!_warned)
            {
                _warned = true;
                Debug.LogWarning("[AnnunciatorHorn] no clip on the AudioSource - " +
                                 "assign " + ClipPath + ".", this);
            }

            return;
        }

        // The group or the rate can be re-pointed from the Inspector mid-run.
        if (_declaredGroup != Group || !Mathf.Approximately(_declaredBlipSeconds, BlipSeconds))
            DeclareBlipRate();

        bool energised = _forceOn || PanelSounding();

        if (energised)
            Trigger();
        else
            Release();

        Envelope();
    }

    // Start a blip when the group's blip counter steps under us. Every horn in
    // the group sees the same step on the same frame, which is the sync.
    private void Trigger()
    {
        if (_blipsPerSecond <= 0f)
        {
            _attacking = true;   // continuous: hold the level up
            return;
        }

        int blip = AnnunciatorFlashGroups.BlipIndex(Group, _flashRate);
        if (blip == _lastBlip)
            return;

        _lastBlip = blip;
        _attacking = true;
    }

    private void Release()
    {
        _attacking = false;

        // Forget where the group's counter was, so the next alarm blips at once
        // rather than waiting out the interval it happened to arrive in.
        _lastBlip = int.MinValue;
    }

    private void Envelope()
    {
        // Unscaled: pausing the simulation shouldn't leave the horn hanging on
        // half a blip, and it shouldn't stretch the release either.
        float dt = Time.unscaledDeltaTime;

        if (_attacking)
        {
            _level = _attackSeconds <= 0f
                ? 1f
                : Mathf.MoveTowards(_level, 1f, dt / _attackSeconds);

            // A blip is struck, not held: the moment it is up, it starts dying.
            // Continuous mode keeps re-arming _attacking, so it stays up.
            if (_level >= 1f)
                _attacking = false;
        }
        else
        {
            _level = _releaseSeconds <= 0f
                ? 0f
                : Mathf.MoveTowards(_level, 0f, dt / _releaseSeconds);
        }

        // Squared: equal steps in level are not equal steps in loudness, so a
        // linear ramp through this curve is what a horn ringing off sounds
        // like, and the tail of the release is genuinely quiet.
        _source.volume = _volume * _level * _level;

        if (_level > 0f && !_source.isPlaying)
            _source.Play();
        else if (_level <= 0f && _source.isPlaying)
            _source.Stop();
    }

    private bool PanelSounding()
    {
        // No group of its own and not on a rack: listen to the whole room.
        if (string.IsNullOrWhiteSpace(_flashGroup) && _rack == null)
            return AnnunciatorFlashGroups.AnyAudibleRate(_flashRate);

        return AnnunciatorFlashGroups.AnyAudible(Group, _flashRate);
    }

    private void DeclareBlipRate()
    {
        _declaredGroup = Group;
        _declaredBlipSeconds = BlipSeconds;

        if (BlipSeconds > 0f)
            AnnunciatorFlashGroups.DeclareBlip(_declaredGroup, _flashRate, BlipSeconds);
    }

    // Set up the AudioSource the way a panel horn wants it, when the component
    // is first added. 3D so it comes from the rack, wide spread so it fills the
    // room rather than arriving from a point, linear rolloff so it fades over a
    // distance you can reason about, and no doppler - the panel isn't moving.
    private void Reset()
    {
        ConfigureSource(GetComponent<AudioSource>(), ClipPath);
    }

    private static void ConfigureSource(AudioSource source, string clipPath)
    {
        source.playOnAwake = false;
        source.loop = true;
        source.volume = 1f;
        source.pitch = 1f;
        source.spatialBlend = 1f;
        source.spread = 58f;
        source.rolloffMode = AudioRolloffMode.Linear;
        source.dopplerLevel = 0f;
        source.minDistance = 1f;
        source.maxDistance = 50f;

#if UNITY_EDITOR
        if (source.clip == null)
            source.clip = UnityEditor.AssetDatabase.LoadAssetAtPath<AudioClip>(clipPath);
#endif
    }

#if UNITY_EDITOR
    // A rack needs both horns - one for each flash rate - and they cannot share
    // an object. This makes the one this horn isn't: a sibling child of whatever
    // this horn hangs on, on the other rate, at the other rate's blip interval
    // and with the other clip. Nothing to wire afterwards.
    [ContextMenu("Add The Other Horn")]
    private void AddTheOtherHorn()
    {
        bool isRingback = AnnunciatorFlashGroups.NormalizeRate(_flashRate)
                          == AnnunciatorFlashGroups.ClearRate;

        string otherRate = isRingback
            ? AnnunciatorFlashGroups.AnnounceRate
            : AnnunciatorFlashGroups.ClearRate;

        foreach (AnnunciatorHorn horn in transform.parent != null
                     ? transform.parent.GetComponentsInChildren<AnnunciatorHorn>(true)
                     : GetComponentsInChildren<AnnunciatorHorn>(true))
        {
            if (horn != this
                    && AnnunciatorFlashGroups.NormalizeRate(horn._flashRate) == otherRate)
            {
                Debug.LogWarning($"[AnnunciatorHorn] there is already a {otherRate} horn " +
                                 $"here ('{horn.name}').", horn);
                UnityEditor.Selection.activeGameObject = horn.gameObject;
                return;
            }
        }

        var added = new GameObject(isRingback ? "Alarm Horn" : "Ringback Horn");
        UnityEditor.Undo.RegisterCreatedObjectUndo(added, "Add The Other Horn");

        added.transform.SetParent(transform, false);
        added.transform.localPosition = Vector3.zero;

        AnnunciatorHorn other = UnityEditor.Undo.AddComponent<AnnunciatorHorn>(added);
        other._flashGroup = _flashGroup;
        other._flashRate = otherRate;

        // Ringback is one blip a second and rings off for longer: it is a bell,
        // not a buzzer, and it has a whole second of room to do it in.
        other._blipsPerSecond = isRingback ? 2f : 1f;
        other._releaseSeconds = isRingback ? 1.6f : 2.5f;
        other._volume = isRingback ? AlarmVolume : RingbackVolume;

        ConfigureSource(added.GetComponent<AudioSource>(), other.ClipPath);

        UnityEditor.Selection.activeGameObject = added;
        Debug.Log($"[AnnunciatorHorn] added a {otherRate} horn ('{added.name}').", added);
    }
#endif
}
