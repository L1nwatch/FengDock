const AUDIO_FOLDER = "/static/exercises/audio";
const CACHE_NAME = "fengdock-exercise-clips";
const CACHE_STORE = "clips";
const NOTES = { ready: 523, start: 660, cat: 440, cow: 587, switch: 784, rest: 392, done: 880 };
// TTS clips can start or end with silence longer than a countdown beat.
function trimClip(buffer) {
  let first = buffer.length;
  let last = 0;
  for (let channel = 0; channel < buffer.numberOfChannels; channel += 1) {
    const samples = buffer.getChannelData(channel);
    for (let index = 0; index < samples.length; index += 1) {
      if (Math.abs(samples[index]) < 0.008) continue;
      first = Math.min(first, index);
      last = Math.max(last, index);
    }
  }
  const margin = Math.round(0.035 * buffer.sampleRate);
  const start = first <= last ? Math.max(0, first - margin) : 0;
  const end = first <= last ? Math.min(buffer.length, last + margin + 1) : buffer.length;
  return { buffer, offset: start / buffer.sampleRate, duration: (end - start) / buffer.sampleRate };
}

function openClipCache() {
  return new Promise((resolve) => {
    if (!window.indexedDB) {
      resolve(undefined);
      return;
    }
    const request = window.indexedDB.open(CACHE_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(CACHE_STORE);
    request.onsuccess = () => resolve(request.result);
    request.onerror = request.onblocked = () => resolve(undefined);
  }).catch(() => undefined);
}

function accessClipCache(database, mode, operation) {
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(CACHE_STORE, mode);
    const request = operation(transaction.objectStore(CACHE_STORE));
    transaction.oncomplete = () => resolve(request.result);
    transaction.onabort = () => reject(transaction.error);
  }).catch(() => undefined);
}

export function createGuideAudio() {
  const clips = new Map();
  const playing = new Set();
  let context;
  let enabled = false;
  let resuming;
  let manifestRequest;
  let cacheRequest;
  let cues;
  let playback = 0;

  async function readClips() {
    const result = await fetch(`${AUDIO_FOLDER}/manifest.json`, { cache: "no-cache" });
    if (!result.ok) throw new Error("Exercise cue manifest unavailable");
    cues = (await result.json()).cues;
  }

  async function readClip(file) {
    const url = `${AUDIO_FOLDER}/${file}`;
    const cache = await (cacheRequest ??= openClipCache());
    const saved = cache && await accessClipCache(cache, "readonly", (store) => store.get(file));
    if (saved) return saved;

    const response = await fetch(url, { cache: "force-cache" });
    if (!response.ok || !response.headers.get("content-type")?.startsWith("audio/")) {
      throw new Error("Exercise audio clip unavailable");
    }
    const bytes = await response.arrayBuffer();
    // Filenames include a content hash so a release never overwrites cached audio.
    if (cache) await accessClipCache(cache, "readwrite", (store) => store.put(bytes, file));
    return bytes;
  }

  function decode(clip) {
    if (!context) return;
    const decoder = context;
    return clip.decoding ??= clip.bytes.then((bytes) => decoder.decodeAudioData(bytes.slice(0)))
      .then((buffer) => { clip.audio = trimClip(buffer); })
      .catch(() => { clip.decoding = null; });
  }

  function clipFor(id) {
    return clips.get(cues?.[id]?.file)?.audio;
  }

  async function preload(ids) {
    await (manifestRequest ??= readClips().catch(() => { manifestRequest = undefined; }));
    const files = new Set((ids ?? Object.keys(cues ?? {})).map((id) => cues?.[id]?.file).filter(Boolean));
    await Promise.all([...files].map(async (file) => {
      if (!clips.has(file)) {
        const clip = { bytes: readClip(file) };
        clips.set(file, clip);
        clip.bytes.catch(() => { clips.delete(file); });
      }
      const clip = clips.get(file);
      await (decode(clip) ?? clip.bytes.catch(() => {}));
    }));
  }

  function setSessionType(type) {
    try {
      if (window.navigator.audioSession) window.navigator.audioSession.type = type;
    } catch {
      // Browsers without Audio Session support still recover the AudioContext.
    }
  }

  function resumeContext(userGesture = false) {
    const target = context;
    if (target.state === "running") return Promise.resolve(true);
    if (resuming?.context === target && !userGesture) return resuming.promise;
    // A mobile interruption can leave resume() pending until another user gesture.
    const request = { context: target };
    request.promise = new Promise((resolve) => {
      const timeout = window.setTimeout(() => resolve(false), 500);
      try {
        target.resume().then(() => {
          window.clearTimeout(timeout);
          resolve(enabled && context === target && target.state === "running");
        }, () => {
          window.clearTimeout(timeout);
          resolve(false);
        });
      } catch {
        window.clearTimeout(timeout);
        resolve(false);
      }
    }).finally(() => {
      if (resuming === request) resuming = null;
    });
    resuming = request;
    return request.promise;
  }

  function unlock({ reset = false } = {}) {
    const AudioContext = window.AudioContext ?? window.webkitAudioContext;
    if (!AudioContext) return Promise.resolve(false);
    enabled = true;
    // Short coaching cues can share the output with background media.
    setSessionType("transient");
    try {
      if (reset || !context || context.state === "closed") {
        const previous = context;
        stop();
        resuming = null;
        context = new AudioContext();
        const target = context;
        target.addEventListener("statechange", () => {
          if (context !== target || !enabled || target.state === "running") return;
          stop();
          if (!document.hidden) recover();
        });
        if (previous && previous.state !== "closed") previous.close().catch(() => {});
      }
      for (const clip of clips.values()) decode(clip);
      return resumeContext(true);
    } catch {
      return Promise.resolve(false);
    }
  }

  function recover({ userGesture = false } = {}) {
    if (!enabled || !context) return Promise.resolve(false);
    if (context.state === "closed") return unlock();
    return resumeContext(userGesture);
  }

  function disable() {
    enabled = false;
    stop();
    setSessionType("auto");
  }

  function stop() {
    playback += 1;
    for (const source of playing) source.stop();
    playing.clear();
  }

  function start(source, time, ...range) {
    source.addEventListener("ended", () => playing.delete(source), { once: true });
    playing.add(source);
    source.start(time, ...range);
  }

  function beep(frequency) {
    const time = context.currentTime;
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    oscillator.frequency.value = frequency;
    gain.gain.setValueAtTime(0.09, time);
    gain.gain.exponentialRampToValueAtTime(0.001, time + 0.1);
    oscillator.connect(gain);
    gain.connect(context.destination);
    start(oscillator, time);
    oscillator.stop(time + 0.11);
  }

  function playClip(clip, delay, windowSeconds) {
    const source = context.createBufferSource();
    source.buffer = clip.buffer;
    if (windowSeconds > delay + 0.1) {
      source.playbackRate.value = Math.max(1, clip.duration / (windowSeconds - delay - 0.1));
    }
    source.connect(context.destination);
    start(source, context.currentTime + delay, clip.offset, clip.duration);
  }

  function play(id, { tone, windowSeconds, countdown } = {}) {
    stop();
    if (!enabled || !context) return;
    const thisPlayback = playback;
    const requestedAt = performance.now();
    const playReady = () => {
      const elapsed = (performance.now() - requestedAt) / 1000;
      if (!enabled || thisPlayback !== playback || context.state !== "running" || elapsed > 0.6) return;
      if (tone) beep(NOTES[tone]);
      const clip = clipFor(id);
      if (clip) {
        playClip(clip, tone ? 0.1 : 0, windowSeconds - elapsed);
      } else if (countdown) {
        beep(880 - countdown * 80);
        preload([id]);
      }
    };
    if (context.state === "running" && (!id || clipFor(id) || countdown)) {
      playReady();
      return;
    }
    // Wait for recovery and loading, then discard a cue that has become stale.
    Promise.all([recover(), id ? preload([id]) : undefined]).then(playReady);
  }

  return {
    preload, unlock, recover, disable, play, stop,
    countdown: (second) => play(`countdown_${second}`, { countdown: second, windowSeconds: 1 }),
  };
}
