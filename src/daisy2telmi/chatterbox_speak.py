"""Speak a batch of phrases with Chatterbox, run by the machine's own Python.

daisy2telmi ships as a single binary with no torch in it, so it cannot import
Chatterbox itself. It writes a manifest and runs this file with a Python the
user installed `chatterbox-tts` into; the model loads once for the whole batch,
which matters because loading it takes longer than speaking a chapter number.

Manifest: {"phrases": [...], "outs": [...], "lang": "fr", "clip": "ref.wav"}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def _write_wav(path: str, wav, sample_rate: int) -> None:
    """Write the model's float tensor as a WAV by hand: recent torchaudio routes
    save() through TorchCodec, a package chatterbox-tts does not install."""
    from wave import open as open_wav

    import numpy as np

    samples = np.asarray(getattr(wav, "detach", lambda: wav)().cpu().numpy(), dtype=np.float32).reshape(-1)
    with open_wav(path, "wb") as handle:
        handle.setframerate(sample_rate)
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())


def speak(manifest: dict) -> None:
    import perth
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    if perth.PerthImplicitWatermarker is None:
        # perth loads its network through pkg_resources, which venvs on recent
        # Pythons no longer ship, and Chatterbox cannot build a model at all
        # while that class is None. The dummy leaves the audio alone.
        print(
            "no Perth watermark model (pip install setuptools in this Python for one); speaking without it",
            file=sys.stderr,
        )
        perth.PerthImplicitWatermarker = perth.DummyWatermarker

    device = manifest.get("device")
    if not device:
        if torch.cuda.is_available():
            device = "cuda"
        elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            device = "mps"
        else:
            device = "cpu"

    model = ChatterboxMultilingualTTS.from_pretrained(device=device)
    extra = {"audio_prompt_path": manifest["clip"]} if manifest.get("clip") else {}
    for phrase, out in zip(manifest["phrases"], manifest["outs"]):
        wav = model.generate(phrase, language_id=manifest["lang"], **extra)
        _write_wav(out, wav, model.sr)


def main(argv: list[str]) -> int:
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    speak(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
