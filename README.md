# daisy2telmi

Converts a **DAISY 2.02 audio book pack** into a **Telmi story folder** (Telmi Sync / Telmi OS).

One Telmi scene per top-level chapter. Audio only — no text, no scene images, no TTS.

```
daisy2telmi <path-to-daisy-pack> <output-folder>
```

Works with a `.zip` pack or an already-extracted folder.

---

## Install

Requires Python 3.11+ and **ffmpeg on PATH**.

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -e .
```

ffmpeg is **mandatory**, not optional: every source MP3 in the test pack is 22050 Hz / mono / 56 kbps and Telmi requires 44100 Hz / CBR 64–192 kbps, so every scene is re-encoded. It is not a Python dependency, so install it:

- Windows: `winget install Gyan.FFmpeg`
- macOS: `brew install ffmpeg`
- Linux: `apt install ffmpeg`

The built `daisy2telmi.exe` **bundles ffmpeg** (see Build below), so an end user running the exe does not need it installed. Only a source install needs it on PATH. The converter checks for ffmpeg before doing any work and exits with a clear message if it can find neither a bundled copy nor one on PATH.

## Usage

```bash
daisy2telmi gon-ruby-mp3.zip output
daisy2telmi --verbose gon-ruby-mp3.zip output   # logs every ffmpeg call
daisy2telmi --force gon-ruby-mp3.zip output     # write into a non-empty folder
```

Exit codes: `0` success, `1` pack unreadable or ffmpeg failed, `2` bad arguments / not a DAISY pack / output folder not empty.

## Output

```
output/
  metadata.json
  nodes.json
  title.mp3
  title.png        640x480 placeholder, generated
  audios/
    s1.mp3 ... sN.mp3
```

`nodes.json` is a linear chain: `startAction` → `a0` → `s1`, and each `sN.ok` → `aN` → `sN+1`. Every scene has `control: {ok: true, home: true, autoplay: true}`, `home: backAction`, and a unique `ok` action key. Scene `image` is `null`, so no `images/` folder is written.

---

## What the test pack actually contains

`gon-ruby-mp3.zip` — ATDO, *ごんぎつね* (Gon, the Fox), 2009, 86 files. It is **not** a textbook DAISY 2.02 pack, and the parser follows the pack rather than the spec.

| Observation | Consequence for the converter |
| :--- | :--- |
| There is **no `package.opf`**. Metadata lives in `ncc.html` as `<meta name="dc:*">`. | `ncc.html` alone is enough to accept a pack. `package.opf` is read only if present. |
| `ncc.html` has 26 outline items: 1 `h1 class="title"`, 6 `h1`, 19 `h2`, plus 6 `span class="page-normal"`. `ncc:depth` is 2. | `h1` opens a chapter, `h2`+ fold into it, `h1 class="title"` is front matter, `page-normal` spans are skipped. |
| 26 SMIL files and 26 MP3s, strictly one MP3 per SMIL. | A chapter's audio is a *set* of whole MP3 files, not one. |
| SMIL and MP3 names do **not** match: `hotl000c.smil` → `hotl0012.mp3`. | Never infer audio from filenames; always follow the `<audio src>` references. |
| Each SMIL tiles its MP3 with `<audio clip-begin clip-end>` ranges running 0 → declared duration. | Clip ranges are honoured, and adjacent clips of the same file are merged into one range. |
| A chapter's own SMIL covers only its heading audio (chapter 一 = 29.8 s). The body is in its `h2` children, each with its own MP3. | A chapter is its own SMIL **plus every descendant SMIL**, concatenated. Ignoring this would drop 95% of the book. |
| All 26 MP3s are 22050 Hz, mono, 56 kbps. | Re-encode is mandatory to reach Telmi's 44100 Hz / 64–192 kbps CBR. |
| `er_book_info.xml` lists a duration per SMIL; total 1376.645 s, matching `ncc:totalTime 00:22:56`. | Used as the independent check that no audio was dropped. |

Chapter → audio, as produced:

| Scene | Chapter | SMILs merged | Source MP3s |
| :--- | :--- | ---: | ---: |
| s1 | 一 | 9 | hotl0035, hotl000B, hotl0007, hotl0008, hotl0009, hotl000a, hotl0037, hotl0038, hotl0010 |
| s2 | 二 | 5 | hotl0012, hotl0013, hotl0039, hotl0017, hotl0018 |
| s3 | 三 | 4 | hotl001a, hotl006B, hotl001e, hotl006C |
| s4 | 四 | 3 | hotl006D, hotl006E, hotl006F |
| s5 | 五 | 2 | hotl002a, hotl0070 |
| s6 | 六 | 2 | hotl0071, hotl0072 |
| title.mp3 | front matter | 1 | hotl0002 |

All 26 source MP3s are consumed; none are dropped.

## Assumptions

1. The shallowest heading level in the outline is the chapter level. In this pack that is `h1`; a pack that starts at `h2` splits on `h2`.
2. `class="title"` on a heading means front matter, not a chapter. Its audio becomes `title.mp3`.
3. `span class="page-normal"` / `page-front` / `page-special` are page anchors, not outline items.
4. SMIL document order is playback order.
5. `clip-begin` / `clip-end` are authoritative over the file's real length.
6. The final chapter's `ok` points at `backAction`. The Telmi format has no "story finished" node, and looping or self-referencing the last scene is worse than returning to the menu. **This is the main format interpretation in the project.**
7. Stage keys are `s1..sN` and audio files are `sN.mp3`, matching the wiki's `stages` example.
8. `uuid` is `uuid5` seeded from `dc:identifier`, so re-converting the same pack gives the same story id.
9. Every scene is re-encoded to 44100 Hz, mono, CBR 128 kbps, even when the source is already compliant.
10. `title.png` is always generated. The wiki lists it in the folder layout and `metadata.json` `image` only accepts `title.png` or `cover.png`, so it is treated as required.

## Build the Windows executable

PyInstaller cannot cross-compile. Run this **on Windows**:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python build_windows.py
```

Produces `dist\daisy2telmi.exe` (`--onefile`). `lxml.etree` and `lxml._elementpath` are passed as hidden imports; PyInstaller's own lxml hook does the rest.

`build_windows.py` locates ffmpeg on the build machine and embeds it with `--add-binary`, so the exe is self-contained. If ffmpeg is missing on the build machine the script stops rather than shipping an exe that needs a separate install. At runtime the converter looks for the bundled copy (`sys._MEIPASS`, then the exe's own folder) before falling back to PATH.

## Tests

```bash
pip install -e .[dev]
pytest
```

57 tests. The integration tests skip themselves if `~/daisy/gon-ruby-mp3.zip` or `ffprobe` is absent.

## What was verified on `gon-ruby-mp3.zip`

- 6 scenes, one per `h1` chapter.
- Each scene's rendered duration matches the sum of its SMIL durations from `er_book_info.xml` to under 1 ms. Scenes + `title.mp3` = 1376.645 s, exactly `ncc:totalTime`.
- All 7 output MP3s are 44100 Hz, mono, 128 kbps — inside Telmi's stated range.
- `nodes.json` passes structural checks: unique `ok` keys, `home` → `backAction` everywhere, every referenced action and stage exists, all 6 stages reachable from `startAction`.
- `title.png` is a valid 640×480 8-bit RGB PNG (confirmed with `sips`).
- A `--onefile` PyInstaller build runs the whole conversion end to end with lxml bundled, and again with `PATH=/usr/bin:/bin` (no ffmpeg on PATH) using the ffmpeg embedded in the bundle. Built on macOS, because that is the available machine — **the Windows `.exe` itself has not been built or run.**

## Known limitations

- **DAISY 3 is not supported.** Only DAISY 2.02 `ncc.html` is parsed in practice. There is a DAISY 2 XML `.ncx` fallback, but it has never been run against a real pack — treat it as unproven.
- **Synchronised text is ignored completely.** Only `<audio>` elements are read; `<text>` and the XHTML files are never opened. Safe for audio+text packs, but a text-only pack produces "no chapter with audio" and exits 2.
- **No TTS.** Books without recorded audio are out of scope.
- **The bundled ffmpeg is the build machine's binary**, unmodified and unsigned. It has only been exercised through the macOS equivalent of the build, not through a real `daisy2telmi.exe`.
- **The end-of-story behaviour is unverified on real hardware.** The `ok` → `backAction` choice for the last scene is an interpretation of an undocumented case.
- **No cover art.** `title.png` is a flat 640×480 placeholder; nothing is extracted from the pack.
- **Chapter granularity is fixed.** A pack with a single flat heading level becomes one scene; there is no option to split on `h2`.
- **No resume or bookmarking.** Telmi has no position concept in this format, so a listener restarts at chapter 1.

## v2 candidates

GUI, DAISY 3 (`.opf` + `.ncx` + SMIL 2.0), scene images extracted from the pack, configurable granularity, real-device validation on a Telmi.
