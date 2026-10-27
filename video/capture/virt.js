// Init script injected before mock4.html runs. Gives the capture a virtual clock so every frame is exact:
// performance.now, requestAnimationFrame and setTimeout run on window.__cap.vnow once __cap.enable() is called;
// CSS animations and transitions are paused and advanced by hand each step; HTMLAudioElement is replaced by a
// silent stand-in that keeps time on the virtual clock and logs create/play/pause/seek/ended; the crowd bed's
// gain changes and buffer start are logged. Nothing in the page file is changed.
(() => {
  const DURS = window.__CAP_DURS || {};
  const realNow = performance.now.bind(performance);
  const C = window.__cap = { virt: false, vnow: 0, v0: 0, rafQ: [], timers: [], tid: 1e7, log: [], seen: new WeakSet(), audios: [] };
  const rec = (o) => C.log.push(Object.assign({ v: C.virt ? C.vnow : realNow(), virt: C.virt, epoch: Date.now() }, o));
  performance.now = () => (C.virt ? C.vnow : realNow());
  const realRaf = window.requestAnimationFrame.bind(window);
  window.requestAnimationFrame = (cb) => { if (C.virt) { C.rafQ.push(cb); return ++C.tid; } return realRaf(cb); };
  const rST = window.setTimeout.bind(window), rCT = window.clearTimeout.bind(window);
  window.setTimeout = (fn, ms = 0, ...a) => { if (!C.virt) return rST(fn, ms, ...a); const id = ++C.tid; C.timers.push({ id, at: C.vnow + (+ms || 0), fn, a }); return id; };
  window.clearTimeout = (id) => { const i = C.timers.findIndex((t) => t.id === id); if (i >= 0) C.timers.splice(i, 1); else rCT(id); };

  const keyOf = (src) => { try { const u = new URL(src, location.href); return decodeURIComponent(u.pathname.replace(/^\//, '')); } catch (e) { return String(src); } };
  class FakeAudio extends EventTarget {
    constructor(src) {
      super(); this._src = src || ''; this._ct = 0; this.volume = 1; this.paused = true; this.playbackRate = 1;
      this.readyState = 0; this._meta = false; this._startV = 0; this._startCT = 0; this.preload = 'auto';
      C.audios.push(this); rec({ ev: 'create', src: this.key, volume: this.volume });
    }
    get key() { return keyOf(this._src); }
    get src() { return new URL(this._src, location.href).href; } set src(v) { this._src = v; }
    get duration() { const d = DURS[this.key]; return d == null ? NaN : d; }
    get ended() { return this.paused && this._ct >= this.duration - 1e-6; }
    get currentTime() { return this.paused ? this._ct : this._startCT + (C.vnow - this._startV) / 1000 * this.playbackRate; }
    set currentTime(v) { if (this.paused) this._ct = v; else { this._startCT = v; this._startV = C.vnow; } rec({ ev: 'seek', src: this.key, offsetS: v, volume: this.volume }); }
    _fire(t) { const e = new Event(t); this.dispatchEvent(e); const h = this['on' + t]; if (typeof h === 'function') h.call(this, e); }
    play() {
      if (!this.paused) return Promise.resolve();
      this.paused = false; this._startV = C.vnow; this._startCT = this._ct;
      return new Promise((res) => { queueMicrotask(() => {
        if (!this._meta) { this._meta = true; this.readyState = 4; this._fire('loadedmetadata'); this._fire('canplay'); }
        if (this.paused) { res(); return; }
        rec({ ev: 'play', src: this.key, offsetS: this.currentTime, volume: this.volume, dur: this.duration });
        this._fire('play'); this._fire('playing'); res(); }); });
    }
    pause() { if (this.paused) return; this._ct = this.currentTime; this.paused = true; rec({ ev: 'pause', src: this.key, offsetS: this._ct, volume: this.volume }); this._fire('pause'); }
    load() {}
    _tick() { if (!this.paused && this._meta && isFinite(this.duration) && this.currentTime >= this.duration) {
      this._ct = this.duration; this.paused = true; rec({ ev: 'ended', src: this.key, offsetS: this._ct, volume: this.volume }); this._fire('ended'); } }
  }
  window.Audio = FakeAudio;
  const ss = { speaking: false, pending: false, paused: false,
    speak(u) { rec({ ev: 'tts', src: 'speechSynthesis', text: u && u.text, lang: u && u.lang }); },
    cancel() {}, pause() {}, resume() {}, getVoices() { return []; }, addEventListener() {}, onvoiceschanged: null };
  try { Object.defineProperty(window, 'speechSynthesis', { value: ss, configurable: true }); } catch (e) {}

  // crowd bed (Web Audio): log gain targets and the buffer start
  const sT = AudioParam.prototype.setTargetAtTime;
  AudioParam.prototype.setTargetAtTime = function (target, t, tc) { rec({ ev: 'gain', src: 'audio/stadium-bed.mp3', target, tc }); return sT.call(this, target, t, tc); };
  const cS = AudioParam.prototype.cancelScheduledValues;
  AudioParam.prototype.cancelScheduledValues = function (t) { rec({ ev: 'gaincancel', src: 'audio/stadium-bed.mp3' }); return cS.call(this, t); };
  const bS = AudioBufferSourceNode.prototype.start;
  AudioBufferSourceNode.prototype.start = function (when, offset, dur) { rec({ ev: 'bedstart', src: 'audio/stadium-bed.mp3', offsetS: offset || 0, loop: this.loop }); return bS.apply(this, arguments); };

  C.enable = () => { C.vnow = realNow(); C.v0 = C.vnow; C.virt = true;
    for (const a of document.getAnimations()) { C.seen.add(a); try { a.pause(); } catch (e) {} } };
  // one frame: advance the clock, run due timers, audio, rAF callbacks, then the CSS animations
  C.advance = (dtMs) => { C.vnow += dtMs; };
  C.step = (dtMs) => {
    for (let guard = 0; guard < 1000; guard++) {
      C.timers.sort((a, b) => a.at - b.at || a.id - b.id);
      const t = C.timers[0]; if (!t || t.at > C.vnow) break; C.timers.shift();
      try { t.fn(...t.a); } catch (e) { console.error('timer', e); }
    }
    C.audios.forEach((a) => a._tick());
    const q = C.rafQ; C.rafQ = [];
    for (const cb of q) { try { cb(C.vnow); } catch (e) { console.error('raf', e); } }
    for (const a of document.getAnimations()) {
      if (!C.seen.has(a)) { C.seen.add(a); try { a.pause(); a.currentTime = 0; } catch (e) {} }
      else { try { a.currentTime = (a.currentTime || 0) + dtMs; } catch (e) {} }
    }
  };
  // finish the transitions that are running now (a take that starts mid-clip should not open on a fade)
  C.settle = () => { for (const a of document.getAnimations()) { if (a instanceof CSSTransition) { try { a.finish(); } catch (e) {} } } };
})();
