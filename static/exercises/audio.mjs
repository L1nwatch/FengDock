const AUDIO_FOLDER = "/static/exercises/audio";
const CACHE_NAME = "fengdock-exercise-clips";
const CACHE_STORE = "clips";
const NOTES = { ready: 523, start: 660, cat: 440, cow: 587, switch: 784, rest: 392, done: 880 };
const COUNTDOWN = ["", "One.", "Two.", "Three."];
const COMMON_CUES = [
  "countdown_3", "countdown_2", "countdown_1", "switch_sides",
  "paused", "resumed", "exercise_complete", "exercise_skipped", "feedback_good", "feedback_bad",
  "voice_enabled",
];

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

function speakOnDevice(text) {
  if (!text || !window.speechSynthesis || !window.SpeechSynthesisUtterance) return;
  const utterance = new window.SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  const voices = window.speechSynthesis.getVoices();
  const local = voices.find((voice) => voice.localService && /^en[-_]US/i.test(voice.lang))
    ?? voices.find((voice) => voice.localService && /^en[-_]/i.test(voice.lang));
  if (local) utterance.voice = local;
  window.speechSynthesis.speak(utterance);
}

export function createGuideAudio() {
  const clips = new Map();
  const playing = new Set();
  let context;
  let manifestRequest;
  let cacheRequest;
  let cues;

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
    if (!context || clip.decoding) return;
    clip.decoding = clip.bytes.then((bytes) => context.decodeAudioData(bytes))
      .then((buffer) => { clip.buffer = buffer; })
      .catch(() => {});
  }

  async function preload(ids = COMMON_CUES) {
    await (manifestRequest ??= readClips().catch(() => { manifestRequest = undefined; }));
    for (const id of new Set(ids)) {
      const file = cues?.[id]?.file;
      if (!file) continue;
      if (!clips.has(file)) {
        const clip = { bytes: readClip(file) };
        clips.set(file, clip);
        clip.bytes.catch(() => { clips.delete(file); });
      }
      decode(clips.get(file));
    }
  }

  function unlock() {
    const AudioContext = window.AudioContext ?? window.webkitAudioContext;
    if (!AudioContext) return;
    try {
      context ??= new AudioContext();
      if (context.state !== "running") context.resume().catch(() => {});
      for (const clip of clips.values()) decode(clip);
    } catch {
      // Device speech remains available when Web Audio is unavailable.
    }
  }

  function stop() {
    for (const source of playing) source.stop();
    playing.clear();
    window.speechSynthesis?.cancel();
  }

  function start(source, time, end) {
    source.addEventListener("ended", () => playing.delete(source), { once: true });
    playing.add(source);
    source.start(time);
    if (end !== undefined) source.stop(end);
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
    start(oscillator, time, time + 0.11);
  }

  function play(id, text, { tone, windowSeconds, countdown } = {}) {
    stop();
    if (tone && context) beep(NOTES[tone]);
    const buffer = clips.get(cues?.[id]?.file)?.buffer;
    if (buffer && context?.state === "running") {
      const source = context.createBufferSource();
      source.buffer = buffer;
      const delay = tone ? 0.1 : 0;
      if (windowSeconds > delay + 0.1) {
        source.playbackRate.value = Math.max(1, buffer.duration / (windowSeconds - delay - 0.1));
      }
      source.connect(context.destination);
      start(source, context.currentTime + delay);
    } else {
      if (id) preload([id]);
      if (countdown && context?.state === "running") beep(880 - countdown * 80);
      else speakOnDevice(text);
    }
  }

  return {
    preload, unlock, play, stop,
    countdown: (second) => play(`countdown_${second}`, COUNTDOWN[second], { countdown: second }),
  };
}
