// Minimal ZIP reader and writer, using the platform's raw-deflate streams.
// Enough for DAISY packs in and Telmi story zips out; no dependencies.

const CRC_TABLE = (() => {
  const table = new Uint32Array(256);
  for (let i = 0; i < 256; i++) {
    let c = i;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[i] = c >>> 0;
  }
  return table;
})();

export function crc32(bytes) {
  let crc = 0xffffffff;
  for (let i = 0; i < bytes.length; i++) crc = CRC_TABLE[(crc ^ bytes[i]) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

async function inflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

async function deflate(bytes) {
  const stream = new Blob([bytes]).stream().pipeThrough(new CompressionStream("deflate-raw"));
  return new Uint8Array(await new Response(stream).arrayBuffer());
}

function readView(buffer) {
  return new DataView(buffer.buffer, buffer.byteOffset, buffer.byteLength);
}

/** Entries of a zip archive as {name, data:Uint8Array}, in central-directory order. */
export async function readZip(bytes) {
  const view = readView(bytes);
  let eocd = -1;
  const stop = Math.max(0, bytes.length - 65557);
  for (let i = bytes.length - 22; i >= stop; i--) {
    if (view.getUint32(i, true) === 0x06054b50) {
      eocd = i;
      break;
    }
  }
  if (eocd < 0) throw new Error("not a zip archive");

  const count = view.getUint16(eocd + 10, true);
  let offset = view.getUint32(eocd + 16, true);
  const entries = [];

  for (let n = 0; n < count; n++) {
    if (view.getUint32(offset, true) !== 0x02014b50) throw new Error("corrupt zip: bad central header");
    const method = view.getUint16(offset + 10, true);
    const compressedSize = view.getUint32(offset + 20, true);
    const nameLength = view.getUint16(offset + 28, true);
    const extraLength = view.getUint16(offset + 30, true);
    const commentLength = view.getUint16(offset + 32, true);
    const localOffset = view.getUint32(offset + 42, true);
    const name = new TextDecoder("utf-8").decode(bytes.subarray(offset + 46, offset + 46 + nameLength));

    // The local header carries its own name/extra lengths, which may differ.
    const localNameLength = view.getUint16(localOffset + 26, true);
    const localExtraLength = view.getUint16(localOffset + 28, true);
    const dataStart = localOffset + 30 + localNameLength + localExtraLength;
    const raw = bytes.subarray(dataStart, dataStart + compressedSize);

    if (!name.endsWith("/")) {
      entries.push({ name, data: method === 0 ? raw : method === 8 ? await inflate(raw) : null });
      const last = entries[entries.length - 1];
      if (last.data === null) throw new Error(`unsupported zip compression method ${method} for ${name}`);
    }
    offset += 46 + nameLength + extraLength + commentLength;
  }
  return entries;
}

/** Entries as [{name, data:Uint8Array}] written to a zip archive. */
export async function writeZip(entries) {
  const encoder = new TextEncoder();
  const locals = [];
  const centrals = [];
  let cursor = 0;

  for (const entry of entries) {
    const nameBytes = encoder.encode(entry.name);
    const stored = await deflate(entry.data);
    const useDeflate = stored.length < entry.data.length;
    const payload = useDeflate ? stored : entry.data;
    const method = useDeflate ? 8 : 0;

    const local = new Uint8Array(30 + nameBytes.length + payload.length);
    const lv = readView(local);
    lv.setUint32(0, 0x04034b50, true);
    lv.setUint16(4, 20, true);
    lv.setUint16(8, method, true);
    lv.setUint32(14, crc32(entry.data), true);
    lv.setUint32(18, payload.length, true);
    lv.setUint32(22, entry.data.length, true);
    lv.setUint16(26, nameBytes.length, true);
    local.set(nameBytes, 30);
    local.set(payload, 30 + nameBytes.length);
    locals.push(local);

    const central = new Uint8Array(46 + nameBytes.length);
    const cv = readView(central);
    cv.setUint32(0, 0x02014b50, true);
    cv.setUint16(4, 20, true);
    cv.setUint16(6, 20, true);
    cv.setUint16(10, method, true);
    cv.setUint32(16, crc32(entry.data), true);
    cv.setUint32(20, payload.length, true);
    cv.setUint32(24, entry.data.length, true);
    cv.setUint16(28, nameBytes.length, true);
    cv.setUint32(42, cursor, true);
    central.set(nameBytes, 46);
    centrals.push(central);

    cursor += local.length;
  }

  const centralSize = centrals.reduce((sum, c) => sum + c.length, 0);
  const end = new Uint8Array(22);
  const ev = readView(end);
  ev.setUint32(0, 0x06054b50, true);
  ev.setUint16(8, entries.length, true);
  ev.setUint16(10, entries.length, true);
  ev.setUint32(12, centralSize, true);
  ev.setUint32(16, cursor, true);

  const total = new Uint8Array(cursor + centralSize + 22);
  let at = 0;
  for (const chunk of [...locals, ...centrals, end]) {
    total.set(chunk, at);
    at += chunk.length;
  }
  return total;
}
