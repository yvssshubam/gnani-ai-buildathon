/**
 * Microphone with end-of-speech detection, for the simulated caller phone.
 *
 * Measures the room's noise for a moment, waits for speech, and calls onTurn(wavBlob) once the
 * caller has been quiet for SILENCE_MS. Audio is sent as 16 kHz mono WAV: Chrome's own recording
 * format (WebM) isn't one Prisma accepts.
 */
const TARGET_RATE = 16000;
const SILENCE_MS = 1000;      // this much quiet after speech ends the turn
const MIN_SPEECH_MS = 300;    // shorter sounds (a cough, a click) are ignored
const MAX_TURN_MS = 25000;    // Prisma accepts at most 30 s per clip
const PREROLL_MS = 300;       // keep the audio from just before speech started
const CALIBRATE_MS = 400;     // background noise measured before each turn

export class Recorder {
  constructor({ onTurn, onState, onLevel }) {
    this.onTurn = onTurn;
    this.onState = onState || (() => {});
    this.onLevel = onLevel || (() => {});
    this.mode = "off"; // off | paused | listening | hearing
  }

  async start() {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    });
    this.ctx = new (window.AudioContext || window.webkitAudioContext)();
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.proc = this.ctx.createScriptProcessor(4096, 1, 1);
    this.proc.onaudioprocess = (e) => this.#onAudio(e);
    this.source.connect(this.proc);
    this.proc.connect(this.ctx.destination);
    this.pause();
  }

  stop() {
    this.mode = "off";
    try { this.proc?.disconnect(); this.source?.disconnect(); } catch { /* already closed */ }
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.onLevel(0);
  }

  /** Mic stays open but is ignored (while the agent speaks, so it can't hear itself). */
  pause() { this.#set("paused"); this.onLevel(0); }

  listen() {
    this.chunks = []; this.preroll = [];
    this.speechMs = this.silenceMs = this.turnMs = 0;
    this.calibrating = CALIBRATE_MS; this.calSamples = [];
    this.#set("listening");
  }

  /** "Done speaking" button: send what we have now. */
  finishNow() { if (this.mode === "hearing") this.#emit(); }

  #set(mode) { this.mode = mode; this.onState(mode); }

  #onAudio(e) {
    if (this.mode !== "listening" && this.mode !== "hearing") return;
    const input = e.inputBuffer.getChannelData(0);
    const ms = (input.length / this.ctx.sampleRate) * 1000;
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    const level = Math.sqrt(sum / input.length);
    this.onLevel(Math.min(1, level * 4));
    const copy = new Float32Array(input);

    if (this.calibrating > 0) {
      this.calSamples.push(level);
      this.calibrating -= ms;
      if (this.calibrating <= 0) this.noise = this.calSamples.reduce((a, b) => a + b, 0) / this.calSamples.length;
      return;
    }
    const loud = level > Math.max(0.015, (this.noise || 0.005) * 3);

    if (this.mode === "listening") {
      this.preroll.push(copy);
      while (this.preroll.length * ms > PREROLL_MS) this.preroll.shift();
      if (loud) {
        this.chunks = this.preroll.slice(); this.preroll = [];
        this.speechMs = ms; this.silenceMs = 0; this.turnMs = ms;
        this.#set("hearing");
      }
      return;
    }
    this.chunks.push(copy);
    this.turnMs += ms;
    if (loud) { this.speechMs += ms; this.silenceMs = 0; } else { this.silenceMs += ms; }
    if (this.silenceMs >= SILENCE_MS || this.turnMs >= MAX_TURN_MS) {
      if (this.speechMs < MIN_SPEECH_MS) this.listen();
      else this.#emit();
    }
  }

  #emit() {
    const wav = toWav(this.chunks, this.ctx.sampleRate);
    this.chunks = [];
    this.pause();
    this.onTurn(wav);
  }
}

export function toWav(buffers, inRate) {
  const total = buffers.reduce((n, b) => n + b.length, 0);
  const merged = new Float32Array(total);
  let off = 0;
  for (const b of buffers) { merged.set(b, off); off += b.length; }
  const ratio = inRate / TARGET_RATE;
  const outLen = Math.floor(total / ratio);
  const pcm = new Int16Array(outLen);
  for (let i = 0; i < outLen; i++) {
    const start = Math.floor(i * ratio), end = Math.min(total, Math.floor((i + 1) * ratio));
    let s = 0;
    for (let j = start; j < end; j++) s += merged[j];
    const v = Math.max(-1, Math.min(1, s / Math.max(1, end - start)));
    pcm[i] = v < 0 ? v * 0x8000 : v * 0x7fff;
  }
  const buf = new ArrayBuffer(44 + pcm.length * 2);
  const dv = new DataView(buf);
  const w = (o, s) => { for (let i = 0; i < s.length; i++) dv.setUint8(o + i, s.charCodeAt(i)); };
  w(0, "RIFF"); dv.setUint32(4, 36 + pcm.length * 2, true); w(8, "WAVE"); w(12, "fmt ");
  dv.setUint32(16, 16, true); dv.setUint16(20, 1, true); dv.setUint16(22, 1, true);
  dv.setUint32(24, TARGET_RATE, true); dv.setUint32(28, TARGET_RATE * 2, true);
  dv.setUint16(32, 2, true); dv.setUint16(34, 16, true);
  w(36, "data"); dv.setUint32(40, pcm.length * 2, true);
  new Int16Array(buf, 44).set(pcm);
  return new Blob([buf], { type: "audio/wav" });
}

/** Play the reply parts in order. Resolves when done (or skipped). */
export async function playAll(urls, isCancelled = () => false, onAudio = () => {}) {
  for (const url of urls || []) {
    if (!url || isCancelled()) continue;
    await new Promise((resolve) => {
      const a = new Audio(url);
      onAudio(a);
      a.onended = a.onerror = resolve;
      a.play().catch(resolve);
    });
  }
  onAudio(null);
}
