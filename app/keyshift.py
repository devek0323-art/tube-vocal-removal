# 곡의 키를 감지하고 음질 손실 없이 반음 단위로 올리거나 내리는 모듈
import numpy as np

# 음이름 (0=C 기준)
_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl-Schmuckler 조성 프로파일
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(audio_path, sample_rate=22050, duration=120):
    """크로마 특징과 K-S 프로파일 상관도로 조성을 추정한다. 예: 'C# minor'."""
    import librosa

    y, sr = librosa.load(str(audio_path), sr=sample_rate, mono=True, duration=duration)
    if y.size == 0:
        return None
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr).mean(axis=1)
    best = (None, None, -2.0)
    for shift in range(12):
        rolled = np.roll(chroma, -shift)
        for mode_name, profile in (("major", _MAJOR), ("minor", _MINOR)):
            score = float(np.corrcoef(rolled, profile)[0, 1])
            if score > best[2]:
                best = (_NOTES[shift], mode_name, score)
    if best[0] is None:
        return None
    return f"{best[0]} {best[1]}"


def shift_file(source, semitones, destination):
    """Signalsmith Stretch로 피치만 반음 단위 이동(템포 유지)해 WAV로 쓴다."""
    import soundfile as sf
    import python_stretch

    audio, sr = sf.read(str(source), dtype="float32")
    # (samples,) 또는 (samples, ch) → (ch, samples)
    if audio.ndim == 1:
        audio = audio[np.newaxis, :]
    else:
        audio = np.ascontiguousarray(audio.T)
    stretch = python_stretch.Signalsmith.Stretch()
    stretch.preset(audio.shape[0], sr)
    stretch.setTransposeSemitones(float(semitones))
    shifted = stretch.process(audio)
    sf.write(str(destination), shifted.T, sr)
    return destination
