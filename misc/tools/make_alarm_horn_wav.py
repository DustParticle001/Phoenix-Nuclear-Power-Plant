"""Generate the two annunciator audibles:

    client/unbuilt/Assets/Audio/AnnunciatorHorn.wav       an alarm is in
    client/unbuilt/Assets/Audio/AnnunciatorRingback.wav   an alarm is over

Synthesised rather than downloaded, so there is no licence attached to them and
every part of the sound is a number you can change here and regenerate.

Two sounds because the panel says two things. The SART sequence puts a window on
one of two flash rates - `announce` while an alarm is in and unacknowledged,
`clear` once the condition has gone and nobody has reset it - and the ear has to
be able to tell them apart from across the room without reading a legend. So the
rates get separate clips as well as separate periods: an operator who hears the
ringback knows it is over before turning round.

    THE HORN is a panel horn of the kind that sits above a control-room
    annunciator - an electromechanical diaphragm buzzer. Harsh, harmonically
    rich, and at ONE PITCH. No sweep, no siren, no warble in frequency: real
    horns hold a constant note and the alarm reads as urgent because of its
    spectrum, not because it slides about.

    THE RINGBACK is deliberately unlike it on every axis that carries: a high,
    small chime - smooth, no rattle, no presence boost, and well quieter. It is
    an advisory, since the thing it announces has already stopped happening, so
    it must not read as a second alarm. Contrast in TIMBRE is what does the work
    here; the slower blip interval alone would not, because a horn heard through
    a door is a horn. Higher rather than lower on purpose: a low ringback shares
    too much spectrum with the horn to be told apart at a distance, and a quiet
    sound has to be high to survive the room at all.

    instant attack / long release is NOT baked into these clips, deliberately.
    Each clip is a seamless steady loop; AnnunciatorHorn.cs applies the envelope
    at runtime, which is what lets a horn hold indefinitely while windows are
    flashing and still ring off rather than being cut dead on acknowledge.

Seamless looping is the constraint that shapes everything below: every partial
in a clip must complete a whole number of cycles in one loop. With a 0.25 s
loop that means every frequency has to be a multiple of 4 Hz, including the
"rasp" partials that would otherwise be noise - noise cannot loop, so the rasp
is built as a bank of sines on the loop's own harmonic grid with scattered
phases. It sounds like rattle and repeats exactly.

Mono on purpose: Unity only spatialises mono clips, so a stereo horn could not
be placed on the panel.

Run:  python misc/tools/make_alarm_horn_wav.py
"""

import array
import math
import random
import wave
from collections import namedtuple
from pathlib import Path

AUDIO = (Path(__file__).resolve().parents[2]
         / "client" / "unbuilt" / "Assets" / "Audio")

SAMPLE_RATE = 48000
LOOP_SECONDS = 0.25          # 12000 samples -> the loop's own fundamental is 4 Hz
SEED = 20260906              # fixed: the same command always makes the same clip

# How far the harmonics are scattered in phase, 0 = all aligned. Alignment
# stacks every partial into one spike per cycle: the clip then has to be turned
# down to fit the peak, and it plays quiet and thin. Scattering spreads the same
# energy across the cycle, which is both denser and closer to a real diaphragm,
# where no two partials are in step anyway. Measured as crest factor: 12.2 dB
# aligned, 8.4 dB scattered - nearly 4 dB more horn for the same peak.
PHASE_SCATTER = 1.0

# Every frequency below has to stay on the loop's 4 Hz grid, or the wrap clicks.
GRID_HZ = 1.0 / LOOP_SECONDS

Voice = namedtuple("Voice", (
    "filename",
    "tone",          # fundamental, Hz - on the grid
    "beat",          # second diaphragm a few Hz away, also on the grid
    "beat_level",    # 0 for a single clean tone
    "harmonics",     # partials of each tone, at 1/n - more is harsher
    "presence",      # (low, high, boost) where the ear is most sensitive
    "rasp",          # (low, high, partials, level) rattle; partials 0 for none
    "peak",          # full-scale headroom, so Unity's mixer has somewhere to go
))

# 400 Hz sits above the room's own noise and cuts better than the 320 Hz this
# started at, without tipping over into a smoke-alarm shriek. The 4 Hz
# difference between the two tones is exactly one loop, so the beat lands back
# in phase at the wrap. This is an AMPLITUDE beat - neither tone changes pitch.
HORN = Voice(
    filename="AnnunciatorHorn.wav",
    tone=400.0,              # 100 x 4 Hz
    beat=404.0,              # 101 x 4 Hz
    beat_level=0.35,
    harmonics=16,            # sawtooth-ish and harsh
    presence=(1800.0, 4000.0, 1.8),
    rasp=(1600.0, 5200.0, 120, 0.10),
    peak=0.85,
)

# 880 Hz and only three partials: a small chime, well clear of the horn's 400 Hz
# and of the harmonics stacked on top of it, so the two never sound like one
# instrument. It went UP rather than down because a low ringback shares too much
# spectrum with the horn to be told apart through a door, and because a quiet
# sound has to be high to stay audible - drop the level on a low tone and the
# room simply swallows it.
#
# No rasp and no presence boost, so it has none of the 2-4 kHz bite the horn is
# built around: high, but not piercing. Three partials rather than the horn's
# sixteen keeps it a tone instead of a whistle. The gentle beat is the only
# thing it keeps from the horn - without it a pure tone reads as a test signal
# rather than as a panel. Peak well under the horn's on purpose, and the horn
# component turns it down again (RingbackVolume): a ringback has to be heard
# without being answered.
RINGBACK = Voice(
    filename="AnnunciatorRingback.wav",
    tone=880.0,              # 220 x 4 Hz
    beat=884.0,              # 221 x 4 Hz
    beat_level=0.25,
    harmonics=3,
    presence=(0.0, 0.0, 1.0),
    rasp=(0.0, 0.0, 0, 0.0),
    peak=0.45,
)

VOICES = (HORN, RINGBACK)


def partial_weight(freq, base, voice):
    low, high, boost = voice.presence
    if low <= freq <= high and boost != 1.0:
        return base * boost
    return base


def build_partials(voice):
    """(frequency, amplitude, phase) for everything in one clip.

    Every frequency is a multiple of the loop fundamental, which is what makes
    the wrap seamless - the waveform is genuinely periodic at the loop length,
    so the last sample runs into the first with no step and no click.
    """
    rng = random.Random(SEED)
    partials = []

    for tone, level in ((voice.tone, 1.0), (voice.beat, voice.beat_level)):
        if level <= 0.0:
            continue

        for n in range(1, voice.harmonics + 1):
            freq = tone * n
            if freq >= SAMPLE_RATE / 2:
                break        # nothing above Nyquist, or it aliases back down as a whistle
            amplitude = partial_weight(freq, level / n, voice)
            partials.append((freq, amplitude,
                             rng.uniform(0, math.tau) * PHASE_SCATTER))

    # The rattle. Sines on the loop grid rather than real noise, so it repeats.
    rasp_low, rasp_high, rasp_count, rasp_level = voice.rasp
    if rasp_count > 0:
        low = int(rasp_low / GRID_HZ)
        high = int(rasp_high / GRID_HZ)
        for bin_index in rng.sample(range(low, high), rasp_count):
            freq = bin_index * GRID_HZ
            partials.append((freq, rasp_level / math.sqrt(rasp_count),
                             rng.uniform(0, math.tau)))

    return partials


def render(partials, peak):
    count = int(round(SAMPLE_RATE * LOOP_SECONDS))
    samples = [0.0] * count

    for freq, amplitude, phase in partials:
        step = math.tau * freq / SAMPLE_RATE
        for i in range(count):
            samples[i] += amplitude * math.sin(step * i + phase)

    loudest = max(abs(s) for s in samples)
    scale = (peak / loudest) if loudest else 0.0
    return array.array("h", (int(max(-32768, min(32767, round(s * scale * 32767))))
                             for s in samples))


def write(voice):
    partials = build_partials(voice)
    samples = render(partials, voice.peak)
    out = AUDIO / voice.filename

    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(samples.tobytes())

    # The wrap is the only thing that can go audibly wrong in a loop, so check
    # it: sample 0 continues the waveform after the last sample.
    step = abs(samples[0] - samples[-1]) / 32768.0
    biggest = max(abs(samples[i + 1] - samples[i])
                  for i in range(len(samples) - 1)) / 32768.0

    print(f"wrote {out}")
    print(f"  {len(samples)} samples, {LOOP_SECONDS}s, {SAMPLE_RATE} Hz, mono 16-bit, "
          f"{len(partials)} partials")
    print(f"  peak {max(abs(s) for s in samples) / 32768.0:.3f} full scale")
    print(f"  loop wrap step {step:.5f} vs largest step inside the clip {biggest:.5f}"
          f"  ->  {'seamless' if step <= biggest else 'CLICKS - check the partial grid'}")


def main():
    for voice in VOICES:
        write(voice)


if __name__ == "__main__":
    main()
