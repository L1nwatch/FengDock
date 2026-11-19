import { ARCHIVED_EXERCISES, EXERCISES, GROUPS } from "./config.mjs?v=7";

export const STORAGE_KEY = "fengdock.exercises.v1";
const STORAGE_VERSION = 5;
const HOUR = 3_600_000;
const EXERCISE_BY_ID = Object.fromEntries(EXERCISES.map((exercise) => [exercise.id, exercise]));
export const FEEDBACK_LABELS = { "+": "+ 合适", "0": "0 合适", "-": "− 不合适", good: "没问题", bad: "不舒服" };

function initialState(exercise) {
  return {
    ...exercise.initial,
    level: 1,
    version: 1,
    epoch: 0,
    positiveStreak: 0,
    status: "active",
    lastProgressionDate: null,
    progressionType: null,
    lastChange: null,
    resistanceNote: exercise.resistanceNote,
  };
}

export function migrateStore(previous = {}, now = new Date()) {
  if (previous.version > STORAGE_VERSION) throw new Error("训练记录由较新版本创建");
  const store = {
    ...previous,
    version: STORAGE_VERSION,
    voiceEnabled: previous.voiceEnabled !== false,
    sessions: previous.sessions ?? [],
    changes: previous.changes ?? [],
    undo: previous.undo ?? {},
    archived: {
      ...previous.archived,
      ...Object.fromEntries(Object.entries(ARCHIVED_EXERCISES).map(([id, name]) => [
        id, { name, level: previous.levels?.[id], manualReview: previous.manualReviews?.[id], status: "archived" },
      ])),
    },
    exercises: Object.fromEntries(EXERCISES.map((exercise) => [
      exercise.id,
      { ...initialState(exercise), ...previous.exercises?.[exercise.id] },
    ])),
  };
  if (previous.version < 4 && previous.exercises?.seated_cat_cow?.tempoSeconds === 6) {
    const exercise = EXERCISE_BY_ID.seated_cat_cow;
    const state = store.exercises[exercise.id];
    const before = { ...state };
    const { tempoSeconds } = exercise.initial;
    const undo = store.undo[exercise.id];
    if (undo) {
      store.undo = { ...store.undo, [exercise.id]: { ...undo, before: { ...undo.before, tempoSeconds } } };
    }
    state.tempoSeconds = tempoSeconds;
    store.changes = [...store.changes];
    recordChange(store, exercise, before, "guideTempo", now, ["tempoSeconds"]);
  }
  return store;
}

function matchesDoseVersion(state, version) {
  return state.version === version
    || (state.lastChange?.type === "guideTempo" && state.lastChange.before.version === version);
}

// Use a local calendar date for the daily plan and elapsed time for recovery.
export function dayKey(value) {
  const date = new Date(value);
  return [date.getFullYear(), date.getMonth() + 1, date.getDate()]
    .map((part) => String(part).padStart(2, "0")).join("-");
}

export function addDays(value, days) {
  const date = new Date(value);
  date.setDate(date.getDate() + days);
  return date;
}

function recordsFor(store, id) {
  return store.sessions.flatMap((session) => session.records ?? [])
    .filter((record) => record.exercise_id === id && record.id)
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp));
}

export function latestAttempt(store, id) {
  return recordsFor(store, id).find((record) => record.attempted);
}

export function latestFeedback(store, id) {
  return recordsFor(store, id).find((record) => record.feedback && !record.voidedAt);
}

export function setsForSlot({ weeklySets, daysPerWeek }, slot) {
  return Math.floor(weeklySets / daysPerWeek) + Number(slot < weeklySets % daysPerWeek);
}

export function schedule(store, exercise, now) {
  const state = store.exercises[exercise.id];
  const last = latestAttempt(store, exercise.id);
  const interval = GROUPS[exercise.group].minIntervalHours * HOUR;
  let slot = 0;
  let next = new Date(now);
  if (last && (state.daysPerWeek < 7 || last.prescribed_dose.trial)) {
    const previousSlot = last.prescribed_dose.slot % state.daysPerWeek;
    slot = last.prescribed_dose.trial ? 0 : (previousSlot + 1) % state.daysPerWeek;
    const spacing = (index) => Math.floor(index * 7 / state.daysPerWeek);
    const earliest = Date.parse(last.timestamp) + interval;
    const scheduled = last.prescribed_dose.trial ? earliest
      : +addDays(last.timestamp, spacing(previousSlot + 1) - spacing(previousSlot));
    next = new Date(Math.max(scheduled, earliest));
  } else if (last && (last.day ?? dayKey(last.timestamp)) >= dayKey(now)) {
    next = addDays(last.timestamp, 1);
    next.setHours(0, 0, 0, 0);
  }
  const due = state.status !== "paused" && +next <= +new Date(now);
  const dose = Object.fromEntries(Object.keys(exercise.initial).map((field) => [field, state[field]]));
  if (state.weeklySets != null) dose.sets = setsForSlot(state, slot);
  return {
    due, next, intervalMet: !last || +new Date(now) - Date.parse(last.timestamp) >= interval,
    dose: { ...dose, level: state.level, version: state.version, slot, resistanceNote: state.resistanceNote },
  };
}

function resetStreak(state) {
  state.epoch += 1;
  state.positiveStreak = 0;
  state.resistanceReady = false;
}

function snapshot(exercise, state) {
  const fields = [...Object.keys(exercise.initial), "level", "version", "status", "resistanceNote"];
  return Object.fromEntries(fields.map((field) => [field, state[field]]));
}

function recordChange(store, exercise, before, type, now, fields = []) {
  const state = store.exercises[exercise.id];
  state.version += 1;
  const change = {
    timestamp: now.toISOString(), exerciseId: exercise.id, type, fields,
    before: snapshot(exercise, before), after: snapshot(exercise, state),
  };
  state.progressionType = type;
  state.lastChange = change;
  store.changes.push(change);
  return change;
}

function changeDose(store, exercise, values, type, now) {
  const state = store.exercises[exercise.id];
  const before = { ...state };
  Object.assign(state, values);
  state.level += 1;
  state.lastProgressionDate = now.toISOString();
  state.status = type === "up" && !exercise.fallback && !nextParameter(exercise, state)
    ? "maintenance" : "active";
  resetStreak(state);
  return recordChange(store, exercise, before, type, now, Object.keys(values));
}

function nextParameter(exercise, state) {
  for (const rule of exercise.progression) {
    const max = rule.before && state[rule.before.field] < rule.before.threshold ? rule.before.max : rule.max;
    if (state[rule.field] < max) return [rule, max];
  }
  return null;
}

function advanceParameter(store, exercise, rule, max, now) {
  const current = store.exercises[exercise.id][rule.field];
  const step = rule.step ?? Math.max(1, Math.round(current * rule.rate));
  return changeDose(store, exercise, { [rule.field]: Math.min(max, current + step) }, "up", now);
}

function maintain(store, exercise, now, ready) {
  const state = store.exercises[exercise.id];
  if (state.status === "maintenance" && state.resistanceReady === ready) return null;
  const before = { ...state };
  state.status = "maintenance";
  state.resistanceReady = ready;
  return recordChange(store, exercise, before, ready ? "resistanceReady" : "maintenance", now);
}

export function eligibleStreak(store, exerciseId) {
  const state = store.exercises[exerciseId];
  const recent = recordsFor(store, exerciseId).filter((record) =>
    !record.voidedAt && record.epoch === state.epoch && record.completed
    && record.feedback === "+" && !record.prescribed_dose.trial,
  );
  const firstIneligible = recent.findIndex((record) => !record.eligible || record.recovery?.outcome === "worse");
  return firstIneligible < 0 ? recent.length : firstIneligible;
}

function progress(store, exercise, now) {
  const state = store.exercises[exercise.id];
  if (state.status === "paused" || eligibleStreak(store, exercise.id) < GROUPS[exercise.group].positiveTarget) return null;

  const candidate = nextParameter(exercise, state);
  if (candidate) return advanceParameter(store, exercise, ...candidate, now);
  if (exercise.fallback) {
    const rule = exercise.fallback;
    if (!state.resistanceUnavailable) return maintain(store, exercise, now, true);
    if (state[rule.field] < rule.max) return advanceParameter(store, exercise, rule, rule.max, now);
    return maintain(store, exercise, now, true);
  }
  return maintain(store, exercise, now, false);
}

function pause(store, exercise, now) {
  const state = store.exercises[exercise.id];
  const before = { ...state };
  state.status = "paused";
  resetStreak(state);
  return recordChange(store, exercise, before, "paused", now);
}

export function saveTraining(store, exerciseId, input, now) {
  const exercise = EXERCISE_BY_ID[exerciseId];
  const state = store.exercises[exerciseId];
  let session = store.sessions.find((entry) => entry.id === input.sessionId);
  if (session?.records.some((entry) => entry.id === input.id)) return null;
  const { due, dose, intervalMet } = schedule(store, exercise, now);
  if (!due || dose.version !== input.dose.version || input.dose.trial) {
    throw new Error("训练计划已更新，请返回首页查看。");
  }
  const record = {
    id: input.id, timestamp: now.toISOString(), day: dayKey(now), exercise_id: exerciseId,
    level: input.dose.level, prescribed_dose: input.dose, completed: input.completed,
    attempted: input.attempted, feedback: input.feedback, intervalMet,
    eligible: input.completed && !input.dose.trial && input.feedback === "+" && intervalMet,
    epoch: state.epoch,
  };
  if (!session) {
    session = { id: input.sessionId, timestamp: input.startedAt, startedAt: input.startedAt,
      status: "in_progress", completedAt: null, records: [] };
    store.sessions.unshift(session);
  }
  session.records.push(record);
  return applyFeedback(store, exercise, record, now);
}

function applyFeedback(store, exercise, record, now) {
  if (!record.feedback) return null;
  const id = exercise.id;
  const state = store.exercises[id];
  store.undo[id] = { recordId: record.id, before: { ...state } };
  if (record.feedback === "-") return pause(store, exercise, now);
  if (record.feedback === "+") {
    if (record.completed && !record.prescribed_dose.trial) state.positiveStreak += 1;
    return record.eligible ? progress(store, exercise, now) : null;
  }
  resetStreak(state);
  return null;
}

export function undoFeedback(store, exerciseId, recordId, now) {
  const exercise = EXERCISE_BY_ID[exerciseId];
  const undo = store.undo[exerciseId];
  const record = latestFeedback(store, exerciseId);
  if (undo?.recordId !== recordId || record?.id !== recordId) throw new Error("只能撤销该动作最近一次可撤销的反馈。");
  const before = store.exercises[exerciseId];
  // Keep the actual training and its recovery interval when undoing its rating.
  record.voidedAt = now.toISOString();
  const fields = Object.keys(exercise.initial).filter((field) => before[field] !== undo.before[field]);
  store.exercises[exerciseId] = { ...undo.before, version: before.version };
  delete store.undo[exerciseId];
  const change = recordChange(store, exercise, before, "undo", now, fields);
  record.undoVersion = change.after.version;
  return change;
}

export function canReplaceFeedback(store, record) {
  const state = store.exercises[record.exercise_id];
  return record.voidedAt && state && matchesDoseVersion(state, record.undoVersion)
    && latestAttempt(store, record.exercise_id)?.id === record.id;
}

export function replaceFeedback(store, exerciseId, recordId, feedback, now) {
  const record = recordsFor(store, exerciseId).find((entry) => entry.id === recordId);
  if (!record || !canReplaceFeedback(store, record)) throw new Error("这条记录已无法重新反馈。");
  const exercise = EXERCISE_BY_ID[exerciseId];
  const state = store.exercises[exerciseId];
  record.feedbackRevisions ??= [];
  record.feedbackRevisions.push({
    feedback: record.feedback, reason: record.reason, recovery: record.recovery, voidedAt: record.voidedAt,
  });
  record.feedback = feedback;
  delete record.reason;
  record.eligible = record.completed && feedback === "+" && record.intervalMet && !record.prescribed_dose.trial;
  record.epoch = state.epoch;
  delete record.voidedAt;
  delete record.undoVersion;
  delete record.recovery;
  return applyFeedback(store, exercise, record, now);
}

export function resumeExercise(store, exerciseId, now) {
  const exercise = EXERCISE_BY_ID[exerciseId];
  const state = store.exercises[exerciseId];
  if (state.status !== "paused") return null;
  const before = { ...state };
  state.status = "active";
  delete store.undo[exerciseId];
  return recordChange(store, exercise, before, "resumed", now);
}

export function updateResistance(store, note, now) {
  const exercise = EXERCISE_BY_ID.band_curl;
  const state = store.exercises[exercise.id];
  if (state.status === "paused") throw new Error("动作已暂停。");
  if (!state.resistanceReady) throw new Error("请先完成进阶所需的训练。");
  if (note && note === state.resistanceNote) throw new Error("请描述可复现的更高阻力设置。");
  delete store.undo[exercise.id];
  if (note) {
    state.resistanceUnavailable = false;
    return changeDose(store, exercise, {
      resistanceLevel: state.resistanceLevel + 1,
      resistanceNote: note,
      reps: exercise.initial.reps,
    }, "resistance", now);
  }
  state.resistanceUnavailable = true;
  state.resistanceReady = false;
  return progress(store, exercise, now) ?? maintain(store, exercise, now, false);
}
