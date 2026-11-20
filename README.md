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

### Output format

```bash
daisy2telmi --format lunii gon-ruby-mp3.zip stories
```

`--format telmi|lunii|flam` picks the player the story is written for; Telmi is the default. The story folder is always written, and one archive comes out of it: `story.zip` for the Telmi Sync and the Flam launcher, which both import TELMI folders, or `<story>-lunii.zip` in the STUdio form for a Lunii. A plain Lunii has no colour panel and four grey levels, so choosing it draws a second set of cards — white ground, black ink, flattened to `0/96/192/255` — and builds the archive from those. The GUI has the same three choices under the cover field.

`--night-mode` / `--no-night-mode` marks the Lunii archive `nightModeAvailable`, which is how a Lunii offers the story in its bedtime playlist — screen off, volume capped. It is on by default and only reaches `--format lunii`: the Telmi player keeps night mode as a device setting, and a story folder cannot ask for it.

### Spoken chapter cards

A chapter card can speak when it appears, so a listener who cannot see the screen knows where the book is:

```bash
daisy2telmi --announce prompt --language fr gon-ruby-mp3.zip stories
daisy2telmi --announce chapter --autoplay gon-ruby-mp3.zip stories
```

`--announce` chooses what the card says: `off`; `number` (the number alone); `number_of` (the number and how many parts the story has); `title` (the part's own name, as the DAISY outline labels it); `number_title` and `title_number` (that name with the number, either order); `chapter` ("Chapter 4"); or `prompt` (the number plus a question inviting OK, the default). A pattern that needs a name falls back to `chapter` in a pack whose parts carry no synced text. If no speech engine is found the run logs a warning and the cards stay silent — the story is still valid. The player plays a card's audio as soon as it draws the card, whether or not autoplay is on; `--autoplay` only decides whether it then advances by itself or waits for OK.

`--language` sets the phrase and the voice — `ar, de, en, es, fr, it, nl, pt, tr, zh` (`src/daisy2telmi/i18n.py` holds the wording). `--tts` picks the engine: `chatterbox` (the default), `auto` (espeak-ng, then macOS `say`, then Windows speech), `espeak`, `say`, `sapi` or `command`. A run that asks for Chatterbox on a machine that does not have it logs a warning and reads the cards with `auto` instead. `--tts-voice` names a voice, and `--tts-command` is a template with `{text}`, `{out}`, `{lang}`, `{locale}` and `{voice}`, which is how any other engine gets used. Cards only get a spoken number when the cut is by chapter; at paragraph or sentence level a card plays the opening seconds of its own part instead, which is the only way to tell hundreds of cards apart.

`--tts chatterbox` speaks with [Chatterbox](https://github.com/resemble-ai/chatterbox). It is not bundled — the binaries carry no torch — so daisy2telmi runs `src/daisy2telmi/chatterbox_speak.py` in an interpreter of your own: `pip install chatterbox-tts` first, and `--tts-python` picks the interpreter if the `python3` on `PATH` is not the one that has it. The app offers to do that install instead of asking you to type it: on Save, a machine without the package gets one dialog, OK runs `pip install --upgrade chatterbox-tts` in the interpreter named in the options and streams pip's output into the log, Cancel uses the machine's own voice for that story. The options page says whether the package is in the interpreter it is pointed at, and has an **Install Chatterbox** button for the same pip run. `--tts-clip` points at a few seconds of someone speaking, which the model copies as a voice; without it the model speaks in its own voice. One process speaks the whole batch, because loading the model costs more than saying a chapter number. `--tts-device auto|cpu|mps|cuda` says what it runs on: Chatterbox leaves the GPU alone unless asked, so `mps` takes the Apple GPU and `cuda` an Nvidia one. `auto` picks the fastest device it finds and logs which one it chose; a forced device the machine does not have stops the run rather than falling back. Chatterbox is retired upstream: as of August 2026 the repository is an unmaintained MIT archive.

The built binaries carry espeak-ng, its shared libraries and its language data, so speech works with nothing installed. Windows builds rely on the speech engine that ships with Windows.

### Cover art

DAISY 2.02 audio packs carry no cover, so the user supplies one:

```bash
daisy2telmi --cover cover.jpg gon-ruby-mp3.zip stories
```

The pack does name the print book it was read from: `dc:source` holds that book's ISBN (`dc:identifier` is the DAISY edition's own number, which no cover service knows). `--find-cover` asks Open Library for that ISBN, or searches by title and author when the pack has no ISBN, and uses the picture it returns:

```bash
daisy2telmi --find-cover gon-ruby-mp3.zip stories
```

ffmpeg crops the picture to `640x480` for `title.png` and for every chapter card, and to `512x512` for `cover.png`. Each card gets its number drawn across the middle in white with a black border — `CHAPTER 2/23`, in the `--language` of the story — so the listener sees which chapter of how many is playing. Without `--cover` the images are the placeholders described under [Output](#output).

`--cover-crop top|center|bottom` says how the picture is cropped to fit those three different ratios; the middle is the default, and a tall cover loses its title there. `--cover-zoom FACTOR` (1 to 4) enlarges the picture before cropping it, so the frame shows less of it and can be moved sideways as well.

The number is drawn by the converter rather than by ffmpeg: Homebrew's ffmpeg has no `drawtext`, so `src/daisy2telmi/images.py` carries a 5x7 bitmap font and ffmpeg only composites the result. The font is Latin, so Chinese and Arabic cards show `2/23` alone; the spoken card still says the word.

The GUI has the same field below the output folder, and looks a cover up by itself as soon as a pack is picked or dropped: the answer lands in the field, and a cover already typed there is never replaced. The web page does the same once it has read the pack. Both keep their own link, which opens a Google image search for the pack's title, and both take a cover from a file or from a link. The GUI then shows the three crops side by side, drawn from the cover in use. The web page draws one frame at the chosen player's ratio instead, and you move it by dragging it, or with the slider, the wheel or the arrow keys, which enlarge the picture under it. Open Library is asked rather than isbndb.com because it needs no key and answers browser requests; isbndb.com's key costs money.

### Listening before converting

```bash
daisy2telmi --list gon-ruby-mp3.zip
daisy2telmi --preview /tmp/listen gon-ruby-mp3.zip
daisy2telmi --drop 2,5-6 gon-ruby-mp3.zip stories
```

`--list` prints one line per chapter — number, length, title, clip count — and stops. It needs no output folder. `--preview FOLDER` writes one playable MP3 per chapter (`01 一.mp3`, `02 二.mp3`, ...) into FOLDER and stops, so a chapter can be heard before anything is built. The lengths come from ffmpeg's container header, not from decoding the file.

`--drop` leaves chapters out of the story, by the numbers `--list` prints: `2`, or `2,4-6`. What is left is renumbered, so dropping chapter 1 makes the old chapter 2 the first one: its card reads `CHAPTER 1/5` and its announcement says `Chapter 1`. A number outside the book, or a selection that drops every chapter, stops the run with exit code 2.

The GUI's **Chapters** button opens the same list. Each row shows the chapter's length, plays it through the system's audio player, and has a box to leave it out; closing the window keeps the unticked numbers for the next conversion.

### GUI

Running `daisy2telmi` with no arguments opens a Tkinter window: pick or drop a pack, pick an output folder and an optional cover, watch the same log the CLI writes. The conversion runs on a worker thread.

**Options** opens a second window with the interface language (the same ten), what the cards say, autoplay, the speech engine and the voice, and under them the Chatterbox rows: which Python runs it, which device it runs on, the voice clip, and whether the package is in that Python — with an **Install Chatterbox** button when it is not. Closing the window writes `~/.config/daisy2telmi/config.json` (`%APPDATA%\daisy2telmi\config.json` on Windows), which the CLI reads too, so a flag like `--language` only overrides what is already saved.

Drag-and-drop needs the optional `tkinterdnd2` (`pip install -e .[gui]`); without it the browse buttons work and the window says so. `build_binary.py` passes `--collect-all tkinterdnd2` when it is installed, so the built binaries get drop support.

On macOS, Homebrew's Python needs the Tk package separately: `brew install python-tk@3.15`.

### Web page

`web/` is a static converter that runs entirely in the browser, deployed to GitHub Pages from the `web` job. It shares no code with the Python package, so `tests/web/converter.test.mjs` pins it to the same naming, uuid and outline behaviour, and `tests/test_web_converter.py` runs the browser modules under Node and validates their output with the same validator as the CLI.

Once a pack has been read, the page lists the parts it was cut into with their lengths, each with a box: untick one to leave it out of the story. The numbers belong to the chosen cut level, so changing level redraws the list; past 400 parts the page only says how many there are.

Its chapter cards speak as well. `web/voices/<language>/01.mp3` … `50.mp3` are pre-recorded announcements ("Chapter 4") generated by `tools/make_web_voices.py`, which records them from espeak-ng (GPLv3 like this project) or, with `--engine chatterbox`, from Chatterbox, and levels every clip to the same loudness the app levels its cards to. A browser tab can play speech but cannot capture it into a file, so the clips are committed rather than synthesised during conversion; past chapter 50 the cards stay silent.

It differs from the CLI in one way that matters: it concatenates MP3 frame data instead of re-encoding. That is safe because the player resamples, but it means no clip trimming and no bitrate normalisation. See [Known limitations](#known-limitations).

## Output

The second argument is a parent folder. Inside it the story gets Telmi's own folder name, `<category>_<age>_<title>_<uuid>`:

```
stories/_00_Wesh la fee_292b74ca-d8be-53f9-a5d5-5224a36bbd02/
  metadata.json
  nodes.json
  notes.json
  title.mp3      the pack's spoken title, played on the story's title screen
  title.png      640x480: the --cover picture, or a placeholder
  cover.png      512x512 copy of the same, referenced by metadata.json
  audios/
    s0.mp3 ... sN.mp3      one per chapter
  images/
    m0.png ... mN.png      640x480: the cover with `CHAPTER k/N` over it, or the number on a placeholder
```

If the second argument already has the conventional name it is used directly instead of nesting.

Alongside the folder the converter writes `<story folder name>.zip`, which is what you hand to Telmi Sync's *Import → zip*. The folder goes in nested one level, because `findDirectory` in `ConvertZip.js` identifies the format by counting `metadata.json`, `nodes.json`, `title.mp3` and `title.png` in a single zip directory and requires exactly four.

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
- Audio is accepted unconverted only as MP3, 44100 Hz, mono or stereo, 64–192 kbps. Otherwise Telmi-Sync re-encodes it to 44100 Hz stereo — but **only on the conversion import paths**. `ConvertFolderTelmi.js`, which handles a pack already in Telmi format, is a plain `copyFileSync` of every file: no re-encode. A Telmi-format pack must arrive with audio already inside the range.
- The player itself is not that strict: `mp3_reader.h` calls `mpg123_format(handle, 44100, 2, …)`, so mpg123 resamples any source rate to 44100 Hz stereo. A 22050 Hz mono MP3 plays; it just stays at source quality.
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

## Build a binary

`build_binary.py` produces a `--onefile` executable for the machine it runs on. PyInstaller cannot cross-compile, so build on the target OS. On Windows:

```bat
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -e .[dev]
python build_binary.py
```

Produces `dist\daisy2telmi.exe` (`dist/daisy2telmi` on macOS and Linux). `lxml.etree` and `lxml._elementpath` are passed as hidden imports; PyInstaller's own lxml hook does the rest.

`build_binary.py` locates ffmpeg on the build machine and embeds it with `--add-binary`, so the binary is self-contained. If ffmpeg is missing the script stops rather than shipping something that needs a separate install. Set `DAISY2TELMI_FFMPEG` to override the search. At runtime the converter looks for the bundled copy (`sys._MEIPASS`, then the executable's own folder) before falling back to PATH.

### CI artifacts

`.github/workflows/build.yml` builds all three on push to `main`, each on its own runner, and attaches them to a GitHub Release on a `v*` tag:

| Artifact | Built on | Notes |
| :--- | :--- | :--- |
| `daisy2telmi.exe` | `windows-latest` | ffmpeg bundled; speech uses the Windows engine |
| `daisy2telmi_<version>_<arch>.deb` | `ubuntu-latest` | installs to `/usr/local/bin/daisy2telmi`, declares `ffmpeg` as a dependency rather than duplicating it |
| `daisy2telmi-<version>-x86_64.AppImage` | `ubuntu-latest` | the same binary, packaged by `tools/make_appimage.py`; `appimagetool` is unpacked with `--appimage-extract` because runners have no FUSE |
| `daisy2telmi-<version>-macos-<arch>.dmg` | `macos-latest` (arm64) and `macos-15-intel` (x86_64) | **unsigned and un-notarised**: Gatekeeper blocks the first run, so open it with right-click → Open or `xattr -d com.apple.quarantine daisy2telmi` |

The Linux and macOS builds also bundle espeak-ng, the libraries it links and its language data. `build_binary.py` copies them to `dist/speech/` and rewrites the macOS load commands to `@loader_path`; at runtime `tts.py` points `ESPEAK_DATA_PATH` at the copied data and, on Linux, `LD_LIBRARY_PATH` at the copied libraries. Without a data folder the script says so and ships without speech — on Debian and Ubuntu that data is a separate package, `espeak-ng-data`, which `espeak-ng` only recommends. The `linux-deb` job removes the `espeak-ng` package before its smoke test so the run has to use the bundled copy.

The `.deb` is written by `tools/make_deb.py` using only the standard library, so it can be produced and checked on any OS without `dpkg` or `fakeroot`.

## Tests

```bash
pip install -e .[dev]
pytest
```

301 Python tests and 63 for the browser modules. The integration tests skip themselves if `gon-ruby-mp3.zip` or `ffprobe` is absent. `tests/test_published_pack.py` additionally checks a real published Telmi story against the same validator; it skips unless `TELMI_SAMPLE` points at one. `tests/test_gui.py` skips where there is no Tk or no display.

The browser modules have their own suite, run with Node's test runner:

```bash
node --test tests/web/*.test.mjs
```

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

The browser converter (`web/`), run under Node against both packs:

- Same folder names as the CLI: `_00_ _fe3ea2d2-…` and `_00_Wesh la fee_292b74ca-…`.
- `storyUuid` reproduces the CLI's uuid5 exactly, so both produce the same story id for the same pack.
- Its output passes `validate_story_dir` and `validate_story_zip`, the same checks the CLI output is held to.
- Concatenated audio decodes as MP3 at the source rate; the 6 chapters total 1372.4 s against the CLI's 1369.4 s. The 3 s difference is encoder padding left at the end of each source file, which the CLI trims.
- Conversion time: 0.5 s for the 22-minute Japanese pack, 2.7 s for the 2 h 18 French one.
- Driven in headless Chrome against `gon-ruby-mp3.zip`: the zip picker and the folder picker each produce a downloadable zip that passes `validate_story_zip` and `validate_story_dir`, with no page errors. The download link is hidden until a story exists, and feeding a converted story back to the page reports that it is already a Telmi story.

Builds:

- A `--onefile` PyInstaller build runs the whole conversion end to end with lxml bundled, and again with `PATH=/usr/bin:/bin` using the ffmpeg embedded in the bundle. That stripped-`PATH` run also spoke 6 French chapter cards through the bundled espeak-ng, whose load commands point at `@loader_path` and whose data comes from the copied `espeak-ng-data`.
- GitHub Actions builds and smoke-tests `daisy2telmi.exe` on a Windows runner, the `.deb` on Ubuntu and the `.dmg` on macOS.

## Known limitations

- **DAISY 3 is not supported.** Only DAISY 2.02 `ncc.html` is parsed in practice. There is a DAISY 2 XML `.ncx` fallback, but it has never been run against a real pack — treat it as unproven.
- **Synchronised text is ignored completely.** Only `<audio>` elements are read; `<text>` and the XHTML files are never opened. Safe for audio+text packs, but a text-only pack produces "no chapter with audio" and exits 2.
- **TTS speaks the cards, not the book.** A book with no recorded audio still produces no chapters. The synthesised phrases are short. The default voice is Chatterbox, which is not in the binaries; the engine the binaries do carry, espeak-ng, is robotic, and `--tts command` is the way to put any other model behind it.
- **The bundled ffmpeg is the build machine's binary**, unmodified and unsigned.
- **No cover art comes from the pack.** DAISY 2.02 audio packs carry no usable cover, so `--cover` supplies one and `--find-cover` asks Open Library for the print book named in `dc:source`; with neither, `cover.png`, `title.png` and the chapter images are generated placeholders. A lookup needs the network, and a pack with no ISBN and no searchable title has nothing to ask with.
- **The drawn card label is uppercase Latin.** The bitmap font in `src/daisy2telmi/images.py` covers the eight Latin-script languages plus accented letters; Chinese and Arabic cards fall back to the bare number.
- **A non-Latin title collapses in the folder name.** `stringNormalizeFileName` keeps only `a-zA-Z0-9-.`, so *ごんぎつね* becomes a single space and the folder is `_00_ _<uuid>`. This is Telmi-Sync's own behaviour, not a converter bug; `metadata.json` keeps the real title.
- **Chapter granularity is fixed.** A pack with a single flat heading level becomes one chapter; there is no option to split on `h2`.
- **No resume or bookmarking.** Telmi has no position concept in this format, so a listener restarts at chapter 1.
- **The web page does not re-encode.** It joins MP3 frame data, so audio keeps the source sample rate and bitrate, and each source file's encoder padding survives (about 0.1 s per file). The player resamples, so it plays. Use the CLI when the audio has to meet the 44100 Hz / 64–192 kbps range exactly.
- **The web page cannot trim clips.** A SMIL that plays part of a file yields the whole file. Both test packs use whole files, so this has not been hit in practice.
- **The web page needs a recent browser.** It relies on `DecompressionStream`/`CompressionStream` (Chrome 80+, Firefox 113+, Safari 16.4+) and `crypto.subtle`, which requires a secure context — `https://` or `localhost`.

## v3 candidates

DAISY 3 (`.opf` + `.ncx` + SMIL 2.0), configurable granularity.

## Licence

GPL-3.0-or-later, see `LICENSE`. Copyright 2026 berthy456 and qwen-flash-next.
