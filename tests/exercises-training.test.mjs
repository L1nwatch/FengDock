import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync, existsSync } from "node:fs";
import { EXERCISES, GROUPS, ARCHIVED_EXERCISES } from "../static/exercises/config.mjs";
import {
  addDays, confirmRecovery, latestFeedback, migrateStore, replaceFeedback, resumeExercise,
  saveTraining, schedule, setsForSlot, undoFeedback, updateResistance,
} from "../static/exercises/training.mjs";
import { buildSteps } from "../static/exercises/guide.mjs";

const exercises = Object.fromEntries(EXERCISES.map((exercise) => [exercise.id, exercise]));
const start = new Date(2026, 1, 1, 12);
const hour = 3_600_000;
let serial = 0;

function submit(store, exercise, time, feedback = "+", options = {}) {
  const id = String(++serial);
  const { dose } = schedule(store, exercise, time);
  const result = saveTraining(store, exercise.id, {
    id, sessionId: id, startedAt: time.toISOString(), dose, feedback,
    attempted: true, completed: true, ...options,
  }, time);
  return { id, result };
}

function recover(store, exercise, id, time, outcome = "ok") {
  return confirmRecovery(store, exercise.id, id, outcome, addDays(time, 1));
}

function positiveRun(store, exercise, date) {
  let last;
  for (let count = 0; count < GROUPS[exercise.group].positiveTarget; count += 1) {
    const time = schedule(store, exercise, date).next;
    const entry = submit(store, exercise, time);
    last = recover(store, exercise, entry.id, time);
    date = addDays(time, 1);
  }
  return { date, change: last };
}

test("initial plans have seven independent doses and a limited curl tolerance trial", () => {
  const store = migrateStore();
  assert.deepEqual(EXERCISES.map(({ id, group }) => [id, group]), [
    ["seated_cat_cow", "back"], ["glute_bridge", "back"], ["supine_march", "back"],
    ["shoulder_rolls", "shoulder"], ["serratus_punch", "shoulder"], ["wall_slide", "shoulder"],
    ["band_curl", "muscle"],
  ]);
  assert.deepEqual(EXERCISES.map(({ id }) => {
    const { reps, holdSeconds, sets, daysPerWeek } = store.exercises[id];
    return [reps, holdSeconds, sets, daysPerWeek];
  }), [
    [8, 0, 1, 7], [10, 2, 1, 7], [8, 2, 1, 7], [5, 0, 1, 7],
    [8, 0, 1, 7], [8, 0, 1, 7], [8, 0, 2, 2],
  ]);
  for (const exercise of EXERCISES) assert.equal(schedule(store, exercise, start).due, true);
  const { dose } = schedule(store, exercises.band_curl, start);
  assert.deepEqual([dose.trial, dose.sets, dose.reps], [true, 1, 3]);
});

test("legacy migration retains stored records, feedback, doses, levels and review flags", () => {
  const records = Object.keys(ARCHIVED_EXERCISES).map((exercise_id, index) => ({
    exercise_id, level: index + 1, feedback: index % 2 ? "good" : "bad",
    completed: true, prescribed_dose: { holdSeconds: 22.5, repsPerSide: 5 },
  }));
  const previous = { version: 2, voiceEnabled: false,
    levels: { high_incline_push_up: 6 }, manualReviews: { high_incline_push_up: true },
    sessions: [{ id: "old", timestamp: start.toISOString(), records }],
  };
  const migrated = migrateStore(previous);
  assert.equal(migrated.version, 4);
  assert.equal(migrated.voiceEnabled, false);
  assert.deepEqual(migrated.sessions, previous.sessions);
  assert.deepEqual(migrated.levels, previous.levels);
  assert.deepEqual(migrated.manualReviews, previous.manualReviews);
  assert.equal(migrated.archived.high_incline_push_up.status, "archived");
  assert.equal(migrated.archived.high_incline_push_up.level, 6);
  assert.equal(migrated.exercises.seated_cat_cow.level, 1);
});

test("all seven can progress past L100 with no changes to their configured bounds", () => {
  for (const exercise of EXERCISES) {
    const store = migrateStore();
    const state = store.exercises[exercise.id];
    state.level = 100;
    state.trialComplete = true;
    const { change } = positiveRun(store, exercise, start);
    assert.deepEqual(change.fields, ["reps"], exercise.id);
    assert.equal(state.level, 101, exercise.id);
    assert.equal(state.positiveStreak, 0);
    assert.deepEqual(change.before.reps, exercise.initial.reps);
    assert.equal(change.after.reps, exercise.initial.reps + 1);
    for (const other of EXERCISES.filter(({ id }) => id !== exercise.id)) {
      assert.equal(store.exercises[other.id].level, 1);
    }
  }
});

test("missing, early or closely spaced recovery cannot promote an exercise", () => {
  const store = migrateStore();
  const exercise = exercises.seated_cat_cow;
  let date = start;
  for (let day = 0; day < 7; day += 1) {
    const { id } = submit(store, exercise, date);
    assert.throws(() => confirmRecovery(store, exercise.id, id, "ok", date), /次日/);
    if (day !== 2) recover(store, exercise, id, date);
    date = addDays(date, 1);
  }
  assert.equal(store.exercises[exercise.id].level, 1);
  assert.equal(store.exercises[exercise.id].positiveStreak, 7);
  for (let day = 0; day < 3; day += 1) {
    const { id } = submit(store, exercise, date);
    recover(store, exercise, id, date);
    date = addDays(date, 1);
  }
  assert.equal(store.exercises[exercise.id].level, 2);

  const nextStore = migrateStore();
  const yesterdayNight = new Date(2026, 1, 1, 23);
  submit(nextStore, exercise, yesterdayNight);
  const nextMorning = new Date(2026, 1, 2, 7);
  assert.equal(schedule(nextStore, exercise, nextMorning).due, true);
  submit(nextStore, exercise, nextMorning);
  assert.equal(latestFeedback(nextStore, exercise.id).eligible, false);
});

test("neutral resets the streak, true skips preserve it, difficulty reduces one field and symptoms pause", () => {
  const store = migrateStore();
  const exercise = exercises.glute_bridge;
  submit(store, exercise, start);
  const second = addDays(start, 1);
  submit(store, exercise, second, null, { attempted: false, completed: false });
  assert.equal(schedule(store, exercise, second).due, true);
  assert.equal(store.exercises[exercise.id].positiveStreak, 1);
  submit(store, exercise, second, "0");
  assert.equal(store.exercises[exercise.id].positiveStreak, 0);
  const { result } = submit(store, exercise, addDays(start, 4), "-", { reason: "difficulty" });
  assert.deepEqual(result.fields, ["holdSeconds"]);
  assert.equal(result.after.holdSeconds, 1);
  assert.equal(result.before.level, result.after.level);
  const painDay = addDays(start, 5);
  submit(store, exercise, painDay, "-", { reason: "symptoms", completed: false });
  assert.equal(store.exercises[exercise.id].status, "paused");
  assert.equal(schedule(store, exercise, addDays(painDay, 1)).due, false);
  resumeExercise(store, exercise.id, addDays(painDay, 1));
  assert.equal(schedule(store, exercise, addDays(painDay, 1)).due, true);
});

test("bridge and march individually increase hold, then sets, then maintain", () => {
  for (const exercise of [exercises.glute_bridge, exercises.supine_march]) {
    const store = migrateStore();
    const state = store.exercises[exercise.id];
    state.reps = exercise.progression[0].max;
    let date = start;
    for (const expected of [3, 4, 5]) {
      const run = positiveRun(store, exercise, date);
      date = run.date;
      assert.deepEqual(run.change.fields, ["holdSeconds"]);
      assert.equal(state.holdSeconds, expected);
      assert.equal(state.sets, 1);
    }
    const run = positiveRun(store, exercise, date);
    assert.deepEqual(run.change.fields, ["sets"]);
    assert.equal(state.sets, 2);
    assert.equal(state.status, "maintenance");
    const last = positiveRun(store, exercise, run.date);
    assert.equal(last.change, null);
    assert.equal(state.level, 5);
    assert.equal(state.status, "maintenance");
  }
});

test("trial requires confirmed recovery before the first formal curl and preserves 48 hours", () => {
  const store = migrateStore();
  const exercise = exercises.band_curl;
  const { id } = submit(store, exercise, start, "0");
  const twoDays = new Date(+start + 48 * hour);
  assert.equal(schedule(store, exercise, twoDays).waitingForTrial, true);
  recover(store, exercise, id, start);
  assert.equal(schedule(store, exercise, new Date(+twoDays - 1)).due, false);
  const { due, dose } = schedule(store, exercise, twoDays);
  assert.equal(due, true);
  assert.deepEqual([dose.trial, dose.sets, dose.reps, dose.resistanceLevel], [false, 2, 8, 1]);
});

test("curl allocates weekly sets across training days, honors delays and increases resistance only on confirmation", () => {
  const store = migrateStore();
  const exercise = exercises.band_curl;
  const state = store.exercises[exercise.id];
  Object.assign(state, { trialComplete: true, reps: 14 });
  let date = start;
  for (const expected of [5, 6]) {
    const run = positiveRun(store, exercise, date);
    date = run.date;
    assert.deepEqual(run.change.fields, ["weeklySets"]);
    assert.equal(state.weeklySets, expected);
  }
  const frequency = positiveRun(store, exercise, date);
  assert.deepEqual(frequency.change.fields, ["daysPerWeek"]);
  assert.equal(state.daysPerWeek, 3);
  assert.equal(state.weeklySets, 6);
  assert.deepEqual([0, 1, 2].map((slot) => setsForSlot(state, slot)), [2, 2, 2]);
  date = frequency.date;

  for (const expected of [7, 8, 9, 10]) {
    const run = positiveRun(store, exercise, date);
    date = run.date;
    assert.equal(state.weeklySets, expected);
  }
  assert.deepEqual([0, 1, 2].map((slot) => setsForSlot(state, slot)), [4, 3, 3]);
  const lastRecord = latestFeedback(store, exercise.id);
  const next = schedule(store, exercise, date);
  assert.ok(+next.next - Date.parse(lastRecord.timestamp) >= 48 * hour);
  const delayed = addDays(next.next, 8);
  assert.equal(schedule(store, exercise, delayed).due, true);
  const run = positiveRun(store, exercise, delayed);
  assert.equal(run.change.type, "resistanceReady");
  assert.equal(state.resistanceLevel, 1);
  assert.equal(state.reps, 14);
  const increased = updateResistance(store, "蓝色型号 B · 短握距", run.date);
  assert.equal(increased.type, "resistance");
  assert.equal(state.resistanceLevel, 2);
  assert.equal(state.reps, 8);
  assert.equal(state.daysPerWeek, 3);
  assert.equal(state.weeklySets, 10);
});

test("no higher resistance uses bounded eccentric tempo and maintains the existing resistance", () => {
  const store = migrateStore();
  const exercise = exercises.band_curl;
  const state = store.exercises[exercise.id];
  Object.assign(state, { trialComplete: true, reps: 14, daysPerWeek: 3, weeklySets: 10, level: 8 });
  assert.throws(() => updateResistance(store, "蓝色", start), /完成进阶/);
  const eligible = positiveRun(store, exercise, start);
  const fallback = updateResistance(store, null, eligible.date);
  assert.deepEqual(fallback.fields, ["tempoSeconds"]);
  assert.equal(state.tempoSeconds, 5);
  const next = positiveRun(store, exercise, eligible.date);
  assert.deepEqual(next.change.fields, ["tempoSeconds"]);
  const cap = positiveRun(store, exercise, next.date);
  assert.equal(state.status, "maintenance");
  assert.equal(state.resistanceLevel, 1);
  assert.equal(state.tempoSeconds, 6);
  assert.equal(state.reps, 14);
  assert.ok(cap.change);
});

test("daily crossover, delayed symptom reports, reload and correction retain the historical prescription", () => {
  let store = migrateStore();
  const exercise = exercises.seated_cat_cow;
  let date = start;
  for (let index = 0; index < 6; index += 1) {
    const { id } = submit(store, exercise, date);
    recover(store, exercise, id, date);
    date = addDays(date, 1);
  }
  const { id } = submit(store, exercise, date);
  assert.equal(schedule(store, exercise, date).due, false);
  store = migrateStore(JSON.parse(JSON.stringify(store)));
  assert.equal(store.exercises[exercise.id].positiveStreak, 7);
  const tomorrow = addDays(date, 1);
  assert.equal(schedule(store, exercise, tomorrow).due, true);
  assert.equal(recover(store, exercise, id, date).after.reps, 9);
  assert.equal(schedule(store, exercise, tomorrow).due, true);
  confirmRecovery(store, exercise.id, id, "worse", new Date(+tomorrow + hour));
  assert.equal(store.exercises[exercise.id].status, "paused");
  assert.equal(store.exercises[exercise.id].reps, 8);
  undoFeedback(store, exercise.id, id, new Date(+tomorrow + 2 * hour));
  assert.equal(store.exercises[exercise.id].positiveStreak, 6);
  assert.equal(store.exercises[exercise.id].status, "active");
  replaceFeedback(store, exercise.id, id, "0", null, new Date(+tomorrow + 2 * hour));
  const record = latestFeedback(store, exercise.id);
  assert.equal(record.prescribed_dose.reps, 8);
  assert.equal(record.feedbackRevisions[0].feedback, "+");
  assert.equal(record.feedbackRevisions[0].recovery.outcome, "worse");
  assert.equal(record.feedback, "0");
  assert.equal(store.exercises[exercise.id].positiveStreak, 0);
  assert.deepEqual(store.changes.map(({ type }) => type), ["up", "paused", "undo"]);
});

test("timed steps honor bilateral totals, holds and eccentric tempo", () => {
  const store = migrateStore();
  const march = exercises.supine_march;
  const steps = buildSteps(march, schedule(store, march, start).dose);
  assert.equal(steps.filter(({ instruction }) => instruction.endsWith("保持 2 秒")).length, 16);
  assert.deepEqual(steps.slice(1, 5).map(({ audioCue }) => audioCue), ["left", undefined, "lower", "right"]);
  assert.equal(steps.filter(({ phase }) => phase === "switch").length, 0);
  const curl = exercises.band_curl;
  const trial = schedule(store, curl, start).dose;
  const curlSteps = buildSteps(curl, { ...trial, tempoSeconds: 6 });
  assert.equal(curlSteps.filter(({ audioCue, duration }) => audioCue === "lower" && duration === 4).length, 6);
});

test("a retried write is idempotent and a stale plan cannot create a second rating", () => {
  const store = migrateStore();
  const exercise = exercises.wall_slide;
  const input = {
    id: "same", sessionId: "session", startedAt: start.toISOString(),
    dose: schedule(store, exercise, start).dose, completed: true, attempted: true, feedback: "+",
  };
  saveTraining(store, exercise.id, input, start);
  saveTraining(store, exercise.id, input, start);
  assert.throws(() => saveTraining(store, exercise.id, { ...input, id: "stale" }, start), /计划已更新/);
  assert.equal(store.sessions[0].records.length, 1);
  assert.equal(store.exercises[exercise.id].positiveStreak, 1);
});


test("cat and cow are separate six-second phases, each with a reusable recording and countdown", () => {
  const store = migrateStore();
  const exercise = exercises.seated_cat_cow;
  const steps = buildSteps(exercise, schedule(store, exercise, start).dose);
  assert.equal(steps.length, 17);
  assert.equal(steps[0].countDown, true);
  for (let rep = 1; rep <= 8; rep += 1) {
    const phasePair = steps.slice(2 * rep - 1, 2 * rep + 1);
    assert.deepEqual(phasePair.map(({ duration, countDown, audioCue }) => [duration, countDown, audioCue]), [
      [6, true, "cat_cow_cat"], [6, true, "cat_cow_arch"],
    ]);
    for (const phase of phasePair) assert.match(phase.roundLabel, new RegExp(`第 ${rep}/8 次`));
  }
});

test("bilateral and directional work is separated by a timed transition", () => {
  const store = migrateStore();
  for (const id of ["serratus_punch", "wall_slide", "shoulder_rolls", "band_curl"]) {
    const exercise = exercises[id];
    const { dose } = schedule(store, exercise, start);
    const steps = buildSteps(exercise, dose);
    const transition = steps.findIndex(({ phase }) => phase === "switch");
    const [left, right] = exercise.sides;
    assert.ok(transition > 1);
    assert.ok(steps.slice(1, transition).every(({ instruction }) => instruction.startsWith(left.label)));
    assert.ok(steps.slice(transition + 1).every(({ instruction }) => instruction.startsWith(right.label)));
    assert.equal(steps[transition].instruction, `${exercise.directional ? "换向" : "换边"} · ${right.label}`);
    assert.equal(steps[transition].countDown, true);
  }
});

test("guide timing migration updates the planned cat-cow without rewriting past doses or streaks", () => {
  const previous = migrateStore();
  previous.version = 3;
  const exercise = exercises.seated_cat_cow;
  previous.exercises[exercise.id].tempoSeconds = 6;
  const { id } = submit(previous, exercise, start);
  const next = migrateStore(previous, addDays(start, 1));
  assert.equal(next.exercises[exercise.id].tempoSeconds, 12);
  assert.equal(next.exercises[exercise.id].positiveStreak, 1);
  assert.equal(next.exercises[exercise.id].level, 1);
  assert.equal(latestFeedback(next, exercise.id).id, id);
  assert.equal(latestFeedback(next, exercise.id).prescribed_dose.tempoSeconds, 6);
  assert.equal(latestFeedback(next, exercise.id).feedback, "+");
  assert.equal(next.changes.at(-1).type, "guideTempo");
  assert.equal(migrateStore(next).changes.length, 1);
  undoFeedback(next, exercise.id, id, addDays(start, 1));
  assert.equal(next.exercises[exercise.id].tempoSeconds, 12);
});


test("wall slides count down each rep and hold steps omit spoken prompts", () => {
  const wall = exercises.wall_slide;
  const reps = buildSteps(wall, wall.initial).filter(({ phase }) => phase === "work");
  assert.equal(reps.length, 16);
  assert.ok(reps.every(({ countDown, duration }) => countDown && duration === 5));
  for (const id of ["glute_bridge", "supine_march", "serratus_punch"]) {
    const exercise = exercises[id];
    const steps = buildSteps(exercise, { ...exercise.initial, holdSeconds: 4 });
    const holds = steps.filter(({ instruction }) => instruction.endsWith("保持 4 秒"));
    assert.ok(holds.length);
    assert.ok(holds.every(({ audioCue, countDown }) => !audioCue && countDown));
  }
});

test("every guided step references a generated clip or intentionally uses only a tone", () => {
  const audio = new URL("../static/exercises/audio/", import.meta.url);
  const manifest = JSON.parse(readFileSync(new URL("manifest.json", audio)));
  const promptPack = JSON.parse(readFileSync(new URL("prompts.json", audio)));
  assert.equal(manifest.model, "gpt-4o-mini-tts");
  assert.deepEqual(Object.keys(manifest.cues), Object.keys(promptPack.cues));
  for (const [id, cue] of Object.entries(manifest.cues)) {
    assert.equal(cue.text, promptPack.cues[id]);
    assert.ok(existsSync(new URL(cue.file, audio)), id);
  }
  for (const exercise of EXERCISES) {
    for (const dose of [{ ...exercise.initial, sets: 2 }, ...(exercise.trial ? [{ ...exercise.initial, ...exercise.trial, trial: true }] : [])]) {
      for (const step of buildSteps(exercise, dose)) {
        if (step.audioCue) assert.ok(manifest.cues[step.audioCue], step.audioCue);
      }
    }
  }
});
