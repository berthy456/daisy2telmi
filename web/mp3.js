// MP3 concatenation without re-encoding.
//
// The Telmi player forces mpg123 to 44100 Hz stereo and resamples internally
// (Telmi-story-teller src/storyTeller/mp3_reader.h), so a stream left at the
// source rate still plays. Concatenating frame data is therefore enough, and it
// avoids shipping an MP3 encoder to the browser.
//
// A cut below chapter level points at a range inside one file, so the frames
// covering that range have to be found: an MP3 frame is a fixed number of
// samples, so the range can be cut at a frame boundary with no re-encoding.

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

const BITRATES = [
  [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256], // MPEG-1 layer III, kbit/s
  [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144], // MPEG-2 and 2.5
];
const RATES = { 3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000] };

/** One frame's byte length and duration in seconds, or null when the header is not decodable. */
function frameAt(bytes, at) {
  if (at + 4 > bytes.length) return null;
  if (bytes[at] !== 0xff || (bytes[at + 1] & 0xe0) !== 0xe0) return null;
  const version = (bytes[at + 1] >> 3) & 0x03; // 3 = MPEG-1, 2 = MPEG-2, 0 = MPEG-2.5
  if (version === 1 || (bytes[at + 1] & 0x06) !== 0x02) return null; // only layer III
  const rate = RATES[version][(bytes[at + 2] >> 2) & 0x03];
  const index = (bytes[at + 2] >> 4) & 0x0f;
  if (!rate || index === 0 || index === 15) return null; // free format and padding
  const samples = version === 3 ? 1152 : 576;
  const kbit = BITRATES[version === 3 ? 0 : 1][index];
  const length = Math.floor((samples * kbit * 1000) / 8 / rate) + ((bytes[at + 2] >> 1) & 1);
  return length > 0 ? { length, duration: samples / rate } : null;
}

/**
 * The frames of one MP3 stream that cover [begin, end) seconds.
 * Times land on a frame boundary, which is within 26 ms at 44100 Hz.
 */
export function trimFrames(bytes, begin = null, end = null) {
  const data = mp3Frames(bytes);
  if ((begin === null || begin <= 0) && end === null) return data;
  let at = 0;
  let seconds = 0;
  let from = -1;
  let to = data.length;
  while (at < data.length) {
    const frame = frameAt(data, at);
    if (!frame) break; // no further header: keep whatever was decoded
    if (from < 0 && (begin === null || seconds + frame.duration >= begin)) from = at;
    if (end !== null && seconds >= end) {
      to = at;
      break;
    }
    seconds += frame.duration;
    at += frame.length;
  }
  if (from < 0) return data.subarray(0, 0);
  return data.subarray(from, Math.max(from, to));
}

/**
 * MP3 segments joined into one stream, in playback order.
 * A segment is `{data, begin, end}`; the times cut inside its file, or null for all of it.
 */
export function concatSegments(segments) {
  const parts = segments
    .map((segment) => trimFrames(segment.data, segment.begin ?? null, segment.end ?? null))
    .filter((part) => part.length > 0);
  return join(parts);
}

/** Whole files joined into one MP3 stream, in playback order. */
export function concatMp3(files) {
  return join(files.map(mp3Frames).filter((part) => part.length > 0));
}

function join(parts) {
  const total = new Uint8Array(parts.reduce((sum, part) => sum + part.length, 0));
  let at = 0;
  for (const part of parts) {
    total.set(part, at);
    at += part.length;
  }
  return total;
}
