# daisy2telmi

Converts a **DAISY 2.02 audio book pack** into a **Telmi story folder** (Telmi Sync / Telmi OS).

One Telmi chapter per top-level DAISY chapter. Audio only — no synchronised text, no TTS. Scene images are generated placeholders.

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
daisy2telmi gon-ruby-mp3.zip stories
daisy2telmi --verbose gon-ruby-mp3.zip stories   # logs every ffmpeg call
daisy2telmi --force gon-ruby-mp3.zip stories     # overwrite an existing story folder
```

Exit codes: `0` success, `1` pack unreadable or ffmpeg failed, `2` bad arguments / not a DAISY pack / story folder already exists.

## Output

The second argument is a parent folder. Inside it the story gets Telmi's own folder name, `<category>_<age>_<title>_<uuid>`:

```
stories/_00_Wesh la fee_292b74ca-d8be-53f9-a5d5-5224a36bbd02/
  metadata.json
  nodes.json
  notes.json
  title.mp3      the pack's spoken title, played on the story's title screen
  title.png      640x480 placeholder
  cover.png      512x512 placeholder, referenced by metadata.json
  audios/
    s0.mp3 ... sN.mp3      one per chapter
  images/
    m0.png ... mN.png      640x480, the chapter number drawn on a placeholder
```

If the second argument already has the conventional name it is used directly instead of nesting.

Telmi-Sync renames the folder to the same convention on import, so the name is for readability before import. `generateDirNameStory` is reproduced exactly — see the contract below.

### The story graph

`nodes.json` uses the same shape as Telmi-Sync's own audio-list importer:

```
startAction → m[0]
m<k>   menu card: image m<k>.png, no audio, autoplay off, ok → s<k>
s<k>   chapter:   audio s<k>.mp3, autoplay on, ok → m[k+1], home → m[k]
```

The last chapter's `ok` is `null`, which is how the published sample packs end a story.

### Contract, taken from the reference implementations

`DantSu/Telmi-Sync` (`ConvertFolder.js`, `Stories.js`, `Strings.js`, `FFmpegCommand.js`) and `DantSu/Telmi-story-teller` (`stories_reader.h`):

- A story folder must contain **all six** of `audios/`, `images/`, `metadata.json`, `nodes.json`, `title.mp3`, `title.png`. `readStoryMetadata` deletes a folder missing any of them, and `storyFormatDetector` reports "Invalid story format".
- `metadata.json` needs `title`, `uuid`, `image`, `version`; `age`, `category` and `description` are optional.
- Audio is accepted unconverted only as MP3, 44100 Hz, mono or stereo, 64–192 kbps. Otherwise Telmi-Sync re-encodes it to 44100 Hz stereo.
- A stage's `image` and `audio` may be `null`. `image` is loaded from `images/`, `audio` from `audios/`.
- An action is a **list** of `{stage}` options; a transition's `index` selects one. With no `index`, the player picks at random.
- A `null`-audio stage with `autoplay: true` advances immediately — Telmi-Sync's own idiom for a skipped stage.

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
| s0 | 一 | 9 | hotl0035, hotl000B, hotl0007, hotl0008, hotl0009, hotl000a, hotl0037, hotl0038, hotl0010 |
| s1 | 二 | 5 | hotl0012, hotl0013, hotl0039, hotl0017, hotl0018 |
| s2 | 三 | 4 | hotl001a, hotl006B, hotl001e, hotl006C |
| s3 | 四 | 3 | hotl006D, hotl006E, hotl006F |
| s4 | 五 | 2 | hotl002a, hotl0070 |
| s5 | 六 | 2 | hotl0071, hotl0072 |
| title.mp3 | front matter | 1 | hotl0002 |

All 26 source MP3s are consumed; none are dropped.

## Assumptions

1. The shallowest heading level in the outline is the chapter level. In this pack that is `h1`; a pack that starts at `h2` splits on `h2`.
2. `class="title"` on a heading means front matter, not a chapter. Its audio becomes `title.mp3`.
3. `span class="page-normal"` / `page-front` / `page-special` are page anchors, not outline items.
4. SMIL document order is playback order.
5. `clip-begin` / `clip-end` are authoritative over the file's real length.
6. The final chapter's `ok` is `null`. The published sample pack does this; Telmi-Sync's own audio-list importer instead wraps around to the first chapter. Null is chosen so the story ends.
7. Stage keys are `m0..mN` (cards) and `s0..sN` (chapters), matching Telmi-Sync's audio-list importer.
8. `uuid` is `uuid5` seeded from `dc:identifier`, so re-converting the same pack gives the same story id. Telmi-Sync generates its own ids as `<prefix>-<hex timestamp>`; any slug-safe value under 36 characters is accepted.
9. Every chapter is re-encoded to 44100 Hz, mono, CBR 128 kbps, even when the source is already compliant.
10. `age` is 0 and `category` is empty: DAISY 2.02 carries no audience-age field, and both feed the folder name.
11. Every top-level outline entry with audio becomes a chapter, including entries such as *Table des matières* or *Fin du livre*. Nothing is dropped on a title guess.

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

71 tests. The integration tests skip themselves if `gon-ruby-mp3.zip` or `ffprobe` is absent. `tests/test_published_pack.py` additionally checks a real published Telmi story against the same validator; it skips unless `TELMI_SAMPLE` points at one.

## What was verified

Against `gon-ruby-mp3.zip`:

- 6 chapters, one per `h1` outline entry.
- Each chapter's rendered duration matches the sum of its SMIL durations from `er_book_info.xml` to under 1 ms. Chapters + `title.mp3` = 1376.645 s, exactly `ncc:totalTime`.
- All 7 output MP3s are 44100 Hz, mono, 128 kbps — inside Telmi's accepted range.
- The generated folder passes `validate_story_dir`, which encodes Telmi-Sync's import checks.

Against a second, structurally different pack (`Rachel-Corenblit-Wesh-la-fee.zip`, a French audiobook with 23 top-level entries): 23 chapters, folder `_00_Wesh la fee_292b74ca-…`, also passing `validate_story_dir`.

Against a real published Telmi story (`_00_La reine des pirates_fffffd-19d14f92f57`):

- `validate_story_dir` reports no problems for it, so the validator matches a pack the player accepts.
- `story_dir_name` reproduces its folder name exactly.
- `story_dir_name` was diffed against Telmi-Sync's real `generateDirNameStory` running in Node over six inputs, including accented, non-Latin, over-long and punctuation-heavy titles: byte-identical.

Builds:

- A `--onefile` PyInstaller build runs the whole conversion end to end with lxml bundled, and again with `PATH=/usr/bin:/bin` using the ffmpeg embedded in the bundle.
- GitHub Actions builds and smoke-tests `daisy2telmi.exe` on a Windows runner.

## Known limitations

- **DAISY 3 is not supported.** Only DAISY 2.02 `ncc.html` is parsed in practice. There is a DAISY 2 XML `.ncx` fallback, but it has never been run against a real pack — treat it as unproven.
- **Synchronised text is ignored completely.** Only `<audio>` elements are read; `<text>` and the XHTML files are never opened. Safe for audio+text packs, but a text-only pack produces "no chapter with audio" and exits 2.
- **No TTS.** Books without recorded audio are out of scope.
- **The bundled ffmpeg is the build machine's binary**, unmodified and unsigned.
- **No cover art from the pack.** `cover.png`, `title.png` and the chapter images are generated placeholders; DAISY 2.02 audio packs carry no usable cover.
- **A non-Latin title collapses in the folder name.** `stringNormalizeFileName` keeps only `a-zA-Z0-9-.`, so *ごんぎつね* becomes a single space and the folder is `_00_ _<uuid>`. This is Telmi-Sync's own behaviour, not a converter bug; `metadata.json` keeps the real title.
- **Chapter granularity is fixed.** A pack with a single flat heading level becomes one chapter; there is no option to split on `h2`.
- **No resume or bookmarking.** Telmi has no position concept in this format, so a listener restarts at chapter 1.

## v2 candidates

GUI for picking a pack, DAISY 3 (`.opf` + `.ncx` + SMIL 2.0), spoken chapter cards (TTS), configurable granularity, cover art supplied by the user.
