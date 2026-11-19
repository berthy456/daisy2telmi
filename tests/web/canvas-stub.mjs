// Node has no canvas, so the page's drawing gets a stand-in: these tests care about
// which lines a card asks for and that every file has bytes, not about the pixels.
// The real drawing is checked in a browser.

export class StubCanvas {
  constructor(width, height) {
    this.width = width;
    this.height = height;
    this.text = [];
  }

  getContext() {
    const card = this;
    return {
      fillRect: () => {},
      drawImage: () => {},
      fillText: (line, x, y) => card.text.push([line, x, y]),
      strokeText: () => {},
      measureText: (line) => ({ width: [...line].length * 10 }),
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
