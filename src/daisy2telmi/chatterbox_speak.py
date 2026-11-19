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


def speak(manifest: dict) -> None:
    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    from torchaudio import save

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
        save(out, wav, model.sr)


def main(argv: list[str]) -> int:
    manifest = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    speak(manifest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
