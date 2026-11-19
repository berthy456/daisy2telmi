// Small XML tokenizer for DAISY ncc.html and SMIL files.
// Enough for well-formed XHTML/XML; avoids DOMParser so the same code runs under Node tests.

const ENTITIES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'" };

function decodeEntities(value) {
  return value.replace(/&(#x?[0-9a-fA-F]+|\w+);/g, (whole, body) => {
    if (body.startsWith("#x") || body.startsWith("#X")) return String.fromCodePoint(parseInt(body.slice(2), 16));
    if (body.startsWith("#")) return String.fromCodePoint(parseInt(body.slice(1), 10));
    return ENTITIES[body] ?? whole;
  });
}

export class Element {
  constructor(tagName) {
    this.tagName = tagName;
    this.attrs = new Map();
    this.children = [];
  }

  get(name) {
    return this.attrs.has(name) ? this.attrs.get(name) : null;
  }

  /** Direct children with this tag name. */
  all(name) {
    return this.children.filter((child) => child.tagName === name);
  }

  /** Every descendant with this tag name, in document order. */
  find(name) {
    const found = [];
    const walk = (node) => {
      for (const child of node.children) {
        if (child.tagName === name) found.push(child);
        walk(child);
      }
    };
    walk(this);
    return found;
  }
}

/** A run of text between tags, kept among the children so it stays in document order. */
export class TextNode extends Element {
  constructor(value) {
    super("#text");
    this.value = value;
  }
}

export function parseXml(text) {
  const root = new Element("#root");
  const stack = [root];
  let i = 0;

  const appendText = (slice) => {
    stack[stack.length - 1].children.push(new TextNode(decodeEntities(slice)));
  };

  while (i < text.length) {
    const lt = text.indexOf("<", i);
    if (lt < 0) {
      appendText(text.slice(i));
      break;
    }
    if (lt > i) appendText(text.slice(i, lt));

    if (text.startsWith("<!--", lt)) {
      i = text.indexOf("-->", lt + 4);
      i = i < 0 ? text.length : i + 3;
      continue;
    }
    if (text.startsWith("<![CDATA[", lt)) {
      i = text.indexOf("]]>", lt + 9);
      i = i < 0 ? text.length : i + 3;
      continue;
    }
    if (text.startsWith("<!", lt) || text.startsWith("<?", lt)) {
      i = text.indexOf(">", lt + 2);
      i = i < 0 ? text.length : i + 1;
      continue;
    }

    const gt = text.indexOf(">", lt + 1);
    if (gt < 0) throw new Error("unclosed tag in markup");
    const raw = text.slice(lt + 1, gt).trim();
    i = gt + 1;

    if (raw.startsWith("/")) {
      const name = raw.slice(1).trim();
      if (stack.length > 1 && stack[stack.length - 1].tagName === name) stack.pop();
      continue;
    }

    const selfClosing = raw.endsWith("/");
    const body = selfClosing ? raw.slice(0, -1).trim() : raw;
    const nameMatch = /^[\w:.-]+/.exec(body);
    if (!nameMatch) continue;

    const element = new Element(nameMatch[0]);
    const attribute = /([\w:.-]+)\s*=\s*("([^"]*)"|'([^']*)')/g;
    let match;
    while ((match = attribute.exec(body.slice(nameMatch[0].length))) !== null) {
      element.attrs.set(match[1], decodeEntities(match[3] ?? match[4] ?? ""));
    }

    stack[stack.length - 1].children.push(element);
    if (!selfClosing) stack.push(element);
  }

  return root.children.find((child) => child.tagName !== "#text") ?? root;
}

/** "00:22:56.5" and "1376.5" both appear in DAISY packs; both mean seconds. */
export function parseClock(value) {
  if (value == null) return null;
  const text = value.trim();
  if (!text) return null;
  if (!text.includes(":")) {
    const seconds = Number.parseFloat(text);
    return Number.isFinite(seconds) ? seconds : null;
  }
  let total = 0;
  for (const part of text.split(":")) {
    const unit = Number.parseFloat(part);
    if (!Number.isFinite(unit)) return null;
    total = total * 60 + unit;
  }
  return total;
}
