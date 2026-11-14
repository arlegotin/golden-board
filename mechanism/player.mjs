// Inert numeric document mechanism. All glyphs, updates and feedback are data.
const NONE = 65535;
const copy = value => structuredClone(value);
const increasing = values => values.every((value, index) => index === 0 || values[index - 1] < value);
const integer = (value, maximum) => Number.isInteger(value) && value >= 0 && value <= maximum;

class Reader {
  constructor(data) { this.data = data; this.offset = 0; }
  take(count) {
    if (!Number.isSafeInteger(count) || count < 0 || count > this.data.length - this.offset)
      throw Error(`Truncated length at ${this.offset}: ${count}`);
    const value = this.data.subarray(this.offset, this.offset + count);
    this.offset += count; return value;
  }
  uint(width) { let value = 0; for (const byte of this.take(width)) value = value * 256 + byte; return value; }
  integers(count, width = 2) {
    const raw = new Reader(this.take(count * width)); const result = [];
    for (let index = 0; index < count; index++) result.push(raw.uint(width));
    return result;
  }
  end() { if (this.offset !== this.data.length) throw Error(`Trailing bytes at ${this.offset}`); }
}

function record(kind, id, bytes) {
  const input = new Reader(bytes); const result = { kind, id };
  if (kind === 1 || kind === 2) {
    result.rows = input.uint(1); result.cols = input.uint(1);
    if (!result.rows || !result.cols) throw Error('Zero matrix dimension');
    const count = result.rows * result.cols;
    if (kind === 1) {
      result.mask = [...input.take(Math.ceil(count / 8))];
      const padding = (8 - count % 8) % 8;
      if (padding && (result.mask.at(-1) & ((1 << padding) - 1))) throw Error('Nonzero glyph padding');
    } else {
      result.cells = [...input.take(count)];
      const regions = input.uint(2); const raw = new Reader(input.take(regions * 4));
      result.regions = Array.from({ length: regions }, () => [raw.uint(2), raw.uint(2)]);
    }
  } else if (kind === 3) {
    result.initial = input.uint(2); result.data = input.integers(input.uint(1));
    const count = input.uint(4);
    if (count > (bytes.length - input.offset) / 2) throw Error('Truncated trace count');
    result.steps = [];
    for (let index = 0; index < count; index++) {
      const changes = input.uint(2); const raw = new Reader(input.take(changes * 3));
      result.steps.push(Array.from({ length: changes }, () => [raw.uint(2), raw.uint(1)]));
    }
  } else if (kind === 4) {
    result.display_kind = input.uint(1); result.display = input.uint(2); result.shape = input.uint(1);
    result.choices = input.integers(input.uint(2));
    const count = input.uint(2);
    if (count > (bytes.length - input.offset) / 2) throw Error('Truncated response count');
    result.accepted = Array.from({ length: count }, () => input.integers(input.uint(2)));
    result.success = input.uint(2); result.failure = input.uint(2); result.passive = input.uint(2);
    result.links = input.integers(input.uint(2));
  } else if (kind === 5) {
    result.rows = input.uint(4); result.cols = input.uint(1);
    if (!result.rows || !result.cols) throw Error('Zero table dimension');
    result.values = input.integers(result.rows * result.cols);
  } else throw Error(`Unknown required record kind ${kind}`);
  input.end(); return result;
}

function validate(document) {
  const records = document.records;
  const ref = (id, kind) => {
    if (!records[id] || records[id].kind !== kind) throw Error(`Invalid reference ${id}, kind ${kind}`);
    return records[id];
  };
  for (const item of Object.values(records)) {
    if (!integer(item.id, NONE - 1)) throw Error('Invalid record identity');
    if (item.kind === 1) {
      if (item.id > 255 || !integer(item.rows, 255) || !integer(item.cols, 255) || !item.rows || !item.cols
          || item.mask.length !== Math.ceil(item.rows * item.cols / 8)
          || item.mask.some(value => !integer(value, 255))) throw Error('Invalid glyph');
    } else if (item.kind === 2) {
      if (!integer(item.rows, 255) || !integer(item.cols, 255) || !item.rows || !item.cols
          || item.cells.length !== item.rows * item.cols) throw Error('Invalid frame dimensions');
      for (const token of item.cells) ref(token, 1);
      const ids = item.regions.map(region => region[0]); const indices = item.regions.map(region => region[1]);
      if (!increasing(ids) || ids.includes(NONE) || new Set(indices).size !== indices.length
          || indices.some(index => !integer(index, item.cells.length - 1))) throw Error('Invalid regions');
    } else if (item.kind === 3) {
      const initial = ref(item.initial, 2);
      for (const id of item.data) ref(id, 5);
      for (const step of item.steps) {
        if (!increasing(step.map(change => change[0]))) throw Error('Noncanonical trace indices');
        for (const [index, token] of step) {
          if (!integer(index, initial.cells.length - 1)) throw Error('Invalid trace index');
          ref(token, 1);
        }
      }
    } else if (item.kind === 4) {
      if (!integer(item.display_kind, 1) || !integer(item.shape, 3)) throw Error('Unknown response/display shape');
      const display = ref(item.display, 2 + item.display_kind);
      const frame = display.kind === 2 ? display : ref(display.initial, 2);
      const regions = new Set(frame.regions.map(region => region[0]));
      if (!increasing(item.choices) || item.choices.some(value => !regions.has(value))) throw Error('Invalid choices');
      for (const id of item.links) ref(id, 4);
      if (item.shape === 0) {
        if (item.choices.length || item.accepted.length || [item.success, item.failure, item.passive].some(id => id !== NONE))
          throw Error('Passive page has practice fields');
      } else {
        if (!item.choices.length || !item.accepted.length) throw Error('Missing practice response data');
        for (const id of [item.success, item.failure, item.passive]) ref(id, 4);
        if (new Set(item.accepted.map(value => JSON.stringify(value))).size !== item.accepted.length)
          throw Error('Duplicate accepted alternatives');
        for (const response of item.accepted) {
          if (response.length > item.choices.length || response.some(value => !item.choices.includes(value))
              || (item.shape === 1 && response.length > 1) || (item.shape === 2 && !increasing(response)))
            throw Error('Invalid accepted response shape');
        }
      }
    } else if (item.kind === 5) {
      if (!integer(item.rows, 0xffffffff) || !integer(item.cols, 255) || !item.rows || !item.cols
          || item.values.length !== item.rows * item.cols) throw Error('Invalid table dimensions');
    } else throw Error('Unknown record kind');
  }
  if (!document.entries.length || new Set(document.entries).size !== document.entries.length)
    throw Error('Missing/duplicate entries');
  for (const id of document.entries) if (!records[id] || ![3, 4].includes(records[id].kind)) throw Error('Invalid entry');
}

export function decodeDocument(bytes) {
  const input = new Reader(bytes);
  if (input.uint(2) !== 0xd639) throw Error('Unknown document marker');
  const entries = input.uint(2); const count = input.uint(2);
  const document = { version: 1, entries: input.integers(entries), records: {} };
  if (count > (bytes.length - input.offset) / 7) throw Error('Truncated record count');
  let previous = -1;
  for (let index = 0; index < count; index++) {
    const kind = input.uint(1); const id = input.uint(2); const length = input.uint(4);
    if (id <= previous) throw Error('Record IDs not unique/increasing');
    previous = id; document.records[id] = record(kind, id, input.take(length));
  }
  input.end(); validate(document); return document;
}

export class Player {
  constructor(document, entry = document.entries[0]) {
    this.document = copy(document); validate(this.document);
    if (!document.entries.includes(entry)) throw Error('Unknown entry');
    this.state = { node: entry, step: 0, selection: [], committed: null,
      attempt: this.document.records[entry].kind === 4 && this.document.records[entry].shape ? 1 : 0 };
  }
  action(action) {
    const before = copy(this.state); const next = copy(this.state);
    try {
      if (!action || Array.isArray(action) || Object.keys(action).length !== 1) throw Error('One operation per action required');
      const [operation, value] = Object.entries(action)[0];
      const item = this.document.records[next.node]; const page = item.kind === 4 ? item : null;
      const display = page ? this.document.records[page.display] : item;
      if (operation === 'select') {
        if (!page?.shape || !page.choices.includes(value)) throw Error('Selection outside active choices');
        if (page.shape === 1) next.selection = [value];
        if (page.shape === 2) next.selection = next.selection.includes(value)
          ? next.selection.filter(item => item !== value) : [...next.selection, value].sort((a, b) => a - b);
        if (page.shape === 3) {
          if (next.selection.length >= page.choices.length) throw Error('Sequence buffer full');
          next.selection.push(value);
        }
      } else if (operation === 'reset') {
        if (value !== true || !page?.shape) throw Error('No uncommitted practice to reset');
        next.selection = [];
      } else if (operation === 'commit') {
        if (value !== true || !page?.shape) throw Error('No active response to commit');
        const accepted = page.accepted.some(response => JSON.stringify(response) === JSON.stringify(next.selection));
        next.committed = { node: page.id, response: [...next.selection], accepted };
        next.node = accepted ? page.success : page.failure; next.step = 0; next.selection = [];
      } else if (operation === 'link') {
        if (!page || !page.links.includes(value)) throw Error('Link not exposed by current page');
        next.node = value; next.step = 0; next.selection = [];
        if (this.document.records[value].shape) { next.attempt++; next.committed = null; }
      } else if (operation === 'seek') {
        if (display.kind !== 3 || !integer(value, display.steps.length)) throw Error('Seek outside trace');
        next.step = value;
      } else throw Error('Unknown operation');
      this.state = next;
      return { ok: true, action: copy(action), before, after: copy(next), packet: this.packet() };
    } catch (error) { return { ok: false, error: error.message, packet: this.packet() }; }
  }
  packet() {
    const item = this.document.records[this.state.node]; const page = item.kind === 4 ? item : null;
    const display = page ? this.document.records[page.display] : item;
    const trace = display.kind === 3 ? display : null;
    const frame = copy(trace ? this.document.records[trace.initial] : display);
    if (trace) for (const step of trace.steps.slice(0, this.state.step))
      for (const [index, token] of step) frame.cells[index] = token;
    return copy({ ...this.state, entries: this.document.entries, display: display.id,
      step_count: trace?.steps.length ?? 0, frame,
      shape: page?.shape ?? 0, choices: page?.choices ?? [], links: page?.links ?? [],
      passive: page?.passive ?? NONE,
      glyphs: Object.fromEntries(Object.values(this.document.records).filter(item => item.kind === 1).map(item => [item.id, item])),
      data: (trace?.data ?? []).map(id => this.document.records[id]) });
  }
}

export function renderSvg(packet, scale = 24) {
  if (!integer(scale, 128) || scale < 12) throw Error('Invalid rendering scale');
  const frame = packet.frame; const selected = new Set(packet.selection);
  const selectedCells = new Set(frame.regions.filter(([id]) => selected.has(id)).map(([, index]) => index));
  const definitions = Object.values(packet.glyphs).map(glyph => {
    const bits = [];
    for (let index = 0; index < glyph.rows * glyph.cols; index++)
      if (glyph.mask[Math.floor(index / 8)] & (128 >> (index % 8)))
        bits.push(`<rect x="${index % glyph.cols}" y="${Math.floor(index / glyph.cols)}" width="1" height="1"/>`);
    return `<symbol id="g${glyph.id}" viewBox="0 0 ${glyph.cols} ${glyph.rows}">${bits.join('')}</symbol>`;
  });
  const cells = frame.cells.map((token, index) => {
    const x = index % frame.cols * scale; const y = Math.floor(index / frame.cols) * scale;
    return `<rect x="${x}" y="${y}" width="${scale}" height="${scale}" fill="white" stroke="black" stroke-width="${selectedCells.has(index) ? 3 : 0.5}"/><use href="#g${token}" x="${x + 4}" y="${y + 4}" width="${scale - 8}" height="${scale - 8}"/>`;
  });
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${frame.cols * scale}" height="${frame.rows * scale}" viewBox="0 0 ${frame.cols * scale} ${frame.rows * scale}"><defs>${definitions.join('')}</defs>${cells.join('')}</svg>`;
}
