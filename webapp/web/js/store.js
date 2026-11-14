// The user's additions (custom.json): one document, undo/redo, autosave, and what is already baked into the art.

import { api } from './api.js';
import { session } from './session.js';
import { S, bus } from './state.js';
import { canon, debounce } from './util.js';

const TYPES = { place: 'places', path: 'paths', note: 'notes' };
const PREFIX = { place: 'p', path: 'r', note: 'n' };

class Store {
  constructor() {
    this.slug = null;
    this.doc = { places: [], paths: [], notes: [] };
    this.undoStack = [];
    this.redoStack = [];
    this.lastKey = null;
    this.lastT = 0;
    this.version = 0;       // bumps on every change
    this.savedVersion = 0;  // version that is on disk
    this.saveState = 'saved';
    this.saving = null;
    this.baked = null;      // snapshot of {places, paths, notes} drawn into the render on screen
    this.bakedIndex = new Map();
    this.scheduleSave = debounce(() => this.save(), 600);
  }

  load(slug, doc) {
    this.slug = slug;
    this.doc = doc;
    for (const k of Object.values(TYPES)) if (!Array.isArray(doc[k])) doc[k] = [];
    this.undoStack = [];
    this.redoStack = [];
    this.version = this.savedVersion = 0;
    this.setSaveState('saved');
    bus.emit('doc');
  }

  list(type) { return this.doc[TYPES[type]]; }
  get(type, id) { return this.list(type).find((it) => it.id === id) || null; }
  get count() { return this.doc.places.length + this.doc.paths.length + this.doc.notes.length; }
  get canUndo() { return this.undoStack.length > 0; }
  get canRedo() { return this.redoStack.length > 0; }

  nextId(type) {
    const pre = PREFIX[type];
    let max = 0;
    for (const it of this.list(type)) {
      const m = /-(\d+)$/.exec(it.id);
      if (m) max = Math.max(max, +m[1]);
    }
    let id = `${pre}-${max + 1}`;
    while (this.get(type, id)) id += 'x';
    return id;
  }

  /**
   * Change the document. `key` coalesces a burst of related edits (typing in one field, one drag)
   * into a single undo step.
   */
  mutate(fn, key = null) {
    const now = performance.now();
    const sameBurst = key && key === this.lastKey && (key.startsWith('drag:') || now - this.lastT < 1500);
    if (!sameBurst) {
      this.undoStack.push(JSON.stringify(this.doc));
      if (this.undoStack.length > 200) this.undoStack.shift();
      this.redoStack.length = 0;
    }
    this.lastKey = key;
    this.lastT = now;
    fn(this.doc);
    this.touch();
  }

  /** Close the current burst so the next edit starts a new undo step. */
  seal() { this.lastKey = null; }

  touch() {
    this.version += 1;
    this.setSaveState('dirty');
    this.scheduleSave();
    bus.emit('doc');
  }

  undo() { this.step(this.undoStack, this.redoStack); }
  redo() { this.step(this.redoStack, this.undoStack); }

  step(from, to) {
    if (!from.length) return;
    to.push(JSON.stringify(this.doc));
    this.doc = JSON.parse(from.pop());
    this.lastKey = null;
    if (S.sel && !this.get(S.sel.type, S.sel.id)) { S.sel = null; S.vertex = null; bus.emit('sel'); }
    if (S.vertex != null && S.sel?.type === 'path' && S.vertex >= this.get('path', S.sel.id).coords.length) S.vertex = null;
    this.touch();
  }

  setSaveState(s) {
    if (this.saveState === s) return;
    this.saveState = s;
    bus.emit('save');
  }

  async save(opts = {}) {
    this.scheduleSave.cancel();
    if (!session.me) { this.savedVersion = this.version; this.setSaveState('saved'); return true; }
    if (this.saving) { await this.saving.catch(() => {}); }
    if (this.version === this.savedVersion) { this.setSaveState('saved'); return true; }
    const version = this.version;
    this.setSaveState('saving');
    this.saving = api.saveCustom(this.slug, this.doc, opts);
    try {
      await this.saving;
      this.savedVersion = version;
      this.saving = null;
      if (this.version === version) this.setSaveState('saved');
      else { this.setSaveState('dirty'); this.scheduleSave(); }
      return true;
    } catch (e) {
      this.saving = null;
      this.setSaveState('error');
      bus.emit('saveError', e);
      return false;
    }
  }

  /** Best effort when the page is going away. */
  flushOnExit() {
    if (session.me && this.version !== this.savedVersion && this.slug) {
      api.saveCustom(this.slug, this.doc, { keepalive: true }).catch(() => {});
    }
  }

  // ---- what is baked into the art on screen

  setBaked(snapshot) {
    this.baked = snapshot && typeof snapshot === 'object' ? snapshot : null;
    this.bakedIndex = new Map();
    if (this.baked) {
      for (const [type, key] of Object.entries(TYPES)) {
        for (const it of this.baked[key] || []) this.bakedIndex.set(`${type}:${it.id}`, canon(it));
      }
    }
    bus.emit('baked');
  }

  /** True when this exact item (same content) is drawn into the art on screen. */
  isBaked(type, item) {
    const c = this.bakedIndex.get(`${type}:${item.id}`);
    return c !== undefined && c === canon(item);
  }

  /** True when the art on screen does not show the additions as they are now. */
  get needsRedraw() {
    const now = canon({ places: this.doc.places, paths: this.doc.paths, notes: this.doc.notes });
    const then = this.baked
      ? canon({ places: this.baked.places || [], paths: this.baked.paths || [], notes: this.baked.notes || [] })
      : canon({ places: [], paths: [], notes: [] });
    return now !== then;
  }
}

export const store = new Store();
