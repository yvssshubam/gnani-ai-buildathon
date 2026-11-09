/**
 * Make a simulated caller's line sound like a bad phone line, in the browser, before it is played
 * and sent to speech-to-text. The same steps as backend/scripts/replay_calls.py (crack) and
 * stress_test.py (phone quality, rain and crowd noise), so a test call sounds the same in both.
 */

/** A small seeded random generator, so a cracked line breaks up the same way every run. */
function seeded(seed) {
  let a = (seed * 2654435761) >>> 0 || 1;
  const next = () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
  const gauss = () => Math.sqrt(-2 * Math.log(next() || 1e-9)) * Math.cos(2 * Math.PI * next());
  return { next, gauss };
}

/** 16-bit PCM WAV -> samples. Reads the data to the end of the file, since a streamed WAV header
 *  can carry a wrong data length. Returns null for anything else. */
function readWav(buf) {
  const v = new DataView(buf);
  const tag = (o) => String.fromCharCode(v.getUint8(o), v.getUint8(o + 1), v.getUint8(o + 2), v.getUint8(o + 3));
  if (buf.byteLength < 44 || tag(0) !== "RIFF" || tag(8) !== "WAVE") return null;
  let o = 12, rate = 0, bits = 0, channels = 1, format = 0;
  while (o + 8 <= buf.byteLength) {
    const id = tag(o), size = v.getUint32(o + 4, true);
    if (id === "fmt ") {
      format = v.getUint16(o + 8, true);
      channels = v.getUint16(o + 10, true);
      rate = v.getUint32(o + 12, true);
      bits = v.getUint16(o + 22, true);
    } else if (id === "data") {
      if (format !== 1 || bits !== 16 || !rate) return null;
      const start = o + 8, frames = Math.floor((buf.byteLength - start) / (2 * channels));
      const out = new Float64Array(frames);
      for (let i = 0; i < frames; i++) out[i] = v.getInt16(start + i * 2 * channels, true);   // first channel
      return { samples: out, rate };
    }
    o += 8 + size + (size % 2);
  }
  return null;
}

function writeWav(samples, rate) {
  const buf = new ArrayBuffer(44 + samples.length * 2), v = new DataView(buf);
  const put = (o, s) => { for (let i = 0; i < 4; i++) v.setUint8(o + i, s.charCodeAt(i)); };
  put(0, "RIFF"); v.setUint32(4, 36 + samples.length * 2, true); put(8, "WAVE");
  put(12, "fmt "); v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
  v.setUint32(24, rate, true); v.setUint32(28, rate * 2, true); v.setUint16(32, 2, true); v.setUint16(34, 16, true);
  put(36, "data"); v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) v.setInt16(44 + i * 2, Math.max(-32768, Math.min(32767, Math.round(samples[i]))), true);
  return new Blob([buf], { type: "audio/wav" });
}

const rms = (s) => Math.sqrt(s.reduce((a, x) => a + x * x, 0) / Math.max(1, s.length)) || 1;

/** Rain-like noise plus a murmur of reversed speech, at the given signal-to-noise ratio. */
function addNoise(samples, snrDb, rng) {
  const n = samples.length, speech = rms(samples);
  const shift = Math.floor(n / 3);
  const noise = new Float64Array(n);
  let lp = 0;
  for (let i = 0; i < n; i++) {
    lp = 0.85 * lp + 0.15 * rng.gauss();
    const drop = rng.next() < 0.002 ? rng.gauss() * 6 : 0;
    const babble = samples[(n - 1 - ((i + shift) % n))];
    noise[i] = (lp + drop) * 0.7 + (babble / speech) * 0.6;
  }
  const scale = speech / 10 ** (snrDb / 20) / rms(noise);
  return samples.map((s, i) => s + noise[i] * scale);
}

/** A line breaking up: bursts of dropped audio, clipping, noise. 1 = mostly understandable, 3 = mostly gone. */
function crack(samples, rate, level, rng) {
  const [dropShare, clip, snr] = { 1: [0.12, 0.7, 15], 2: [0.35, 0.4, 8], 3: [0.6, 0.25, 3] }[Math.max(1, Math.min(3, level))];
  const keepDropping = 0.6;
  const startDrop = ((1 - keepDropping) * dropShare) / (1 - dropShare);
  const noisy = addNoise(samples, snr, rng);
  let peak = 1;
  for (const s of noisy) peak = Math.max(peak, Math.abs(s));
  peak *= clip;
  const frame = Math.max(1, Math.floor(rate / 25));   // 40 ms
  let dropping = false;
  for (let i = 0; i < noisy.length; i += frame) {
    dropping = rng.next() < (dropping ? keepDropping : startDrop);
    for (let j = i; j < Math.min(i + frame, noisy.length); j++) noisy[j] = dropping ? 0 : Math.max(-peak, Math.min(peak, noisy[j]));
  }
  return noisy;
}

/** Down to 8 kHz like a phone call (averaging, then dropping samples). */
function phoneQuality(samples, rate) {
  const step = Math.max(1, Math.round(rate / 8000));
  const out = new Float64Array(Math.floor(samples.length / step));
  for (let i = 0; i < out.length; i++) {
    let sum = 0;
    for (let j = 0; j < step; j++) sum += samples[i * step + j];
    out[i] = sum / step;
  }
  return { samples: out, rate: Math.floor(rate / step) };
}

/** The caller's line as a bad phone line would carry it. Returns the original if it can't be read. */
export async function roughen(blob, { crack: level = 0, phone = false, seed = 1 } = {}) {
  if (!level && !phone) return blob;
  const wav = readWav(await blob.arrayBuffer());
  if (!wav) return blob;
  let { samples, rate } = wav;
  if (level) samples = crack(samples, rate, level, seeded(seed));
  ({ samples, rate } = phoneQuality(samples, rate));
  return writeWav(samples, rate);
}