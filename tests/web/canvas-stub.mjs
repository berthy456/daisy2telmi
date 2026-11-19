// Node has no canvas, so the page's drawing gets a stand-in: these tests care about
// which lines a card asks for and that every file has bytes, not about the pixels.
// The real drawing is checked in a browser.

// Every drawImage the page asks for, so a test can check where a crop lands.
export const DRAWS = [];

// Every picture the page flattens: its size and the colour values it ended up with.
export const FLATTENS = [];

// Every line the page writes: the line, where, and the card it was written on.
export const TEXTS = [];

// Every rectangle the page fills: where, and the card it was filled on.
export const FILLS = [];

export class StubCanvas {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.text = [];
  }

  getContext() {
    const card = this;
    return {
      fillRect: (left, top, width, height) =>
        FILLS.push([left, top, width, height, card.width, card.height]),
      drawImage: (...args) => DRAWS.push({ width: card.width, height: card.height, args }),
      fillText: (line, x, y) => {
        card.text.push([line, x, y]);
        TEXTS.push([line, x, y, card.width, card.height]);
      },
      strokeText: () => {},
      measureText: (line) => ({ width: [...line].length * 10 }),
      // A brightness ramp across each row, so a test can see which level every
      // shade lands on once the page has flattened the picture.
      getImageData: (left, top, width, height) => ({
        width,
        height,
        data: new Uint8ClampedArray(
          Array.from({ length: width * height * 4 }, (_, at) =>
            at % 4 === 3 ? 255 : ((at / 4) % width) * (256 / width),
          ),
        ),
      }),
      putImageData: (image) =>
        FLATTENS.push([card.width, card.height, [...new Set(image.data.filter((_v, at) => at % 4 !== 3))]]),
    };
  }

  convertToBlob() {
    return Promise.resolve(new Blob([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], { type: "image/png" }));
  }
}

export function installCanvasStub() {
  globalThis.OffscreenCanvas = StubCanvas;
  globalThis.document = globalThis.document ?? { createElement: (tag) => (tag === "canvas" ? new StubCanvas(0, 0) : null) };
}
