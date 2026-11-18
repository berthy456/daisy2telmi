// MP3 concatenation without re-encoding.
//
// The Telmi player forces mpg123 to 44100 Hz stereo and resamples internally
// (Telmi-story-teller src/storyTeller/mp3_reader.h), so a stream left at the
// source rate still plays. Concatenating frame data is therefore enough, and it
// avoids shipping an MP3 encoder to the browser.

function id3v2Size(bytes) {
  if (bytes.length < 10 || bytes[0] !== 0x49 || bytes[1] !== 0x44 || bytes[2] !== 0x33) return 0;
  const syncsafe = (bytes[6] << 21) | (bytes[7] << 14) | (bytes[8] << 7) | bytes[9];
  const footer = (bytes[5] & 0x10) !== 0 ? 10 : 0;
  return 10 + syncsafe + footer;
}

function id3v1Size(bytes) {
  if (bytes.length < 128) return 0;
  const at = bytes.length - 128;
  return bytes[at] === 0x54 && bytes[at + 1] === 0x41 && bytes[at + 2] === 0x47 ? 128 : 0;
}

/** The MP3 frame data of one file, with its ID3 tags removed. */
export function mp3Frames(bytes) {
  const start = id3v2Size(bytes);
  const end = bytes.length - id3v1Size(bytes);
  return bytes.subarray(start, Math.max(start, end));
}

/** Whole files joined into one MP3 stream, in playback order. */
export function concatMp3(files) {
  const parts = files.map(mp3Frames).filter((part) => part.length > 0);
  const total = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    total.set(part, at);
    at += part.length;
  }
  return total;
}
