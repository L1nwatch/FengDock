import { EXERCISES, GROUPS } from "./config.mjs";
import { buildSteps } from "./guide.mjs";
import {
  STORAGE_KEY, FEEDBACK_LABELS, migrateStore, addDays, dayKey, schedule, saveTraining,
  latestFeedback, recoveryAvailable, confirmRecovery, undoFeedback, resumeExercise, updateResistance,
  confirmedStreak, canReportWorse, canReplaceFeedback, replaceFeedback,
} from "./training.mjs";

const AUDIO_BASE_URL = "/static/exercises/audio";
const AUDIO_MANIFEST_URL = `${AUDIO_BASE_URL}/manifest.json`;

const views = {
  home: document.getElementById("home-view"),
  workout: document.getElementById("workout-view"),
  feedback: document.getElementById("feedback-view"),
  summary: document.getElementById("summary-view"),
};

const elements = {
  voiceToggle: document.getElementById("voice-toggle"),
  historyButton: document.getElementById("history-button"),
  todayLabel: document.getElementById("today-label"),
  planDuration: document.getElementById("plan-duration"),
  planList: document.getElementById("plan-list"),
  startButton: document.getElementById("start-button"),
  lastSessionNote: document.getElementById("last-session-note"),
  exitWorkout: document.getElementById("exit-workout"),
  exercisePosition: document.getElementById("exercise-position"),
  workoutProgress: document.getElementById("workout-progress"),
  phaseBadge: document.getElementById("phase-badge"),
  roundLabel: document.getElementById("round-label"),
  exercisePurpose: document.getElementById("exercise-purpose"),
  exerciseName: document.getElementById("exercise-name"),
  stepInstruction: document.getElementById("step-instruction"),
  timerRing: document.getElementById("timer-ring"),
  countdown: document.getElementById("countdown"),
  nextCue: document.getElementById("next-cue"),
  formCueText: document.getElementById("form-cue-text"),
  pauseButton: document.getElementById("pause-button"),
  pauseLabel: document.getElementById("pause-label"),
  skipStepButton: document.getElementById("skip-step-button"),
  skipExerciseButton: document.getElementById("skip-exercise-button"),
  feedbackForm: document.getElementById("feedback-form"),
  feedbackProgress: document.getElementById("feedback-progress"),
  feedbackExercise: document.getElementById("feedback-exercise"),
  summaryCopy: document.getElementById("summary-copy"),
  adjustmentList: document.getElementById("adjustment-list"),
  doneButton: document.getElementById("done-button"),
  historyDialog: document.getElementById("history-dialog"),
  closeHistory: document.getElementById("close-history"),
  historyContent: document.getElementById("history-content"),
  resetDataButton: document.getElementById("reset-data-button"),
  confirmDialog: document.getElementById("confirm-dialog"),
  confirmCancel: document.getElementById("confirm-cancel"),
  confirmExit: document.getElementById("confirm-exit"),
  toast: document.getElementById("toast"),
  recoveryPanel: document.getElementById("recovery-panel"),
  recoveryList: document.getElementById("recovery-list"),
  feedbackChoices: document.getElementById("feedback-choices"),
  feedbackReasons: document.getElementById("feedback-reasons"),
  feedbackIntro: document.getElementById("feedback-intro"),
  cancelFeedback: document.getElementById("cancel-feedback"),
  measurementForm: document.getElementById("measurement-form"),
  measurementNote: document.getElementById("measurement-note"),
  experimentContent: document.getElementById("experiment-content"),
};

let store = migrateStore();
let workout = null;
let timerId = null;
let wakeLock = null;
let toastTimer = null;
let audioManifest = null;
let activeAudio = null;
const countdownAudio = new Audio();
countdownAudio.preload = "auto";
const audioCache = new Map();

function loadStore() {
  return migrateStore(JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "null") ?? {});
}

async function updateStore(update) {
  const commit = () => {
    const next = loadStore();
    const result = update(next, new Date());
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
    store = next;
    return result;
  };
  if (navigator.locks) return navigator.locks.request(STORAGE_KEY, commit);
  return commit();
}

function displayError(error) {
  const message = error instanceof DOMException ? "浏览器无法保存训练记录，请检查存储空间或隐私设置。" : error.message;
  showToast(message);
}

function node(tag, className, label) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (label) element.textContent = label;
  return element;
}

function button(label, action, className = "secondary-button") {
  const element = node("button", className, label);
  element.type = "button";
  element.addEventListener("click", action);
  return element;
}

async function act(update) {
  try {
    const change = await updateStore(update);
    renderHome();
    if (elements.historyDialog.open) renderHistory();
    if (typeof change === "string") showToast(change);
    else if (change?.type) showToast(changeLabel(change));
  } catch (error) {
    displayError(error);
  }
}

function doseLabel(exercise, dose) {
  if (dose.reps == null) {
    return [
      dose.sets && `${dose.sets} 组`,
      dose.setsPerSide && `每侧 ${dose.setsPerSide} 组`,
      dose.repsPerSet && `每组 ${dose.repsPerSet} 次`,
      dose.repsPerSide && `每侧 ${dose.repsPerSide} 次`,
      dose.holdSeconds && `保持 ${dose.holdSeconds} 秒`,
      dose.secondsPerRep && `每次 ${dose.secondsPerRep} 秒`,
      dose.restSeconds && `休息 ${dose.restSeconds} 秒`,
    ].filter(Boolean).join(" · ");
  }
  if (!dose.tempoSeconds && dose.secondsPerRep) return `${dose.reps} 次 · 每次 ${dose.secondsPerRep} 秒`;
  const scope = exercise?.id === "shoulder_rolls" ? "前后各 " : exercise?.sides ? "每侧 " : "";
  return [
    `${scope}${dose.sets} 组 × ${dose.reps} 次`,
    dose.holdSeconds && `保持 ${dose.holdSeconds} 秒`,
    dose.tempoSeconds && `节奏 ${dose.tempoSeconds} 秒`,
    dose.resistanceLevel && `阻力 R${dose.resistanceLevel}`,
    dose.weeklySets && !dose.trial && `每周 ${dose.daysPerWeek} 天 / 每侧 ${dose.weeklySets} 组`,
  ].filter(Boolean).join(" · ");
}

const PARAMETER_LABELS = {
  reps: "次数", holdSeconds: "保持时间", sets: "每次组数", weeklySets: "每周组数",
  daysPerWeek: "每周训练天数", tempoSeconds: "每次秒数", resistanceLevel: "阻力等级", resistanceNote: "弹力带",
};

function changeLabel(change) {
  if (change.type === "paused") return "因不适暂停，请评估后再恢复动作";
  if (change.type === "resumed") return "已恢复计划";
  if (change.type === "resistanceReady") return "当前阻力下已达到计划训练量，可以确认更高阻力";
  if (change.type === "maintenance") return "已进入维护";
  if (change.type === "undo") return "已撤销反馈及由此产生的调整";
  const values = change.fields.filter((field) => field !== "resistanceNote").map((field) =>
    `${PARAMETER_LABELS[field]} ${change.before[field]} → ${change.after[field]}`,
  );
  return `L${change.after.level} · ${values.join(" · ")}`;
}

function planItem(exercise, now) {
  const entry = schedule(store, exercise, now);
  const steps = entry.due ? buildSteps(exercise, entry.dose) : [];
  return { exercise, ...entry, steps, durationSeconds: steps.reduce((sum, step) => sum + step.duration, 0) };
}

function refreshStore() {
  try {
    store = loadStore();
    return true;
  } catch (error) {
    displayError(error);
    return false;
  }
}

function startPlan(exerciseId, manual = false) {
  if (workout || !refreshStore()) return;
  const now = new Date();
  const plan = EXERCISES.filter((exercise) => exerciseId ? exercise.id === exerciseId : !exercise.trial)
    .map((exercise) => planItem(exercise, now)).filter((item) => item.due);
  if (!plan.length) {
    renderHome();
    return;
  }
  startWorkout(plan, manual);
}

function renderRecovery(now) {
  const pending = EXERCISES.flatMap((exercise) => {
    const record = latestFeedback(store, exercise.id);
    if (store.exercises[exercise.id].status === "paused" || !record?.attempted
        || record.recovery || record.reason === "symptoms" || !recoveryAvailable(record, now)) return [];
    return [{ exercise, record }];
  });
  const rows = pending.map(({ exercise, record }) => {
    const row = node("div", "recovery-row");
    row.append(node("strong", "", exercise.chineseName));
    const actions = node("div", "inline-actions");
    actions.append(
      button("无加重", () => act((next, time) => confirmRecovery(next, exercise.id, record.id, "ok", time))),
      button("有加重", () => act((next, time) => confirmRecovery(next, exercise.id, record.id, "worse", time)), "danger-button"),
    );
    row.append(actions);
    return row;
  });
  if (pending.length > 1) {
    rows.push(button("以上动作均无加重", () => act((next, time) => {
      for (const { exercise, record } of pending) confirmRecovery(next, exercise.id, record.id, "ok", time);
      return "恢复确认已记录";
    }), "secondary-button recovery-batch"));
  }
  elements.recoveryList.replaceChildren(...rows);
  elements.recoveryPanel.hidden = rows.length === 0;
}

function renderResistance(state, actions) {
  if (!state.resistanceReady) return;
  actions.append(button("确认更高阻力", () => {
    const input = window.prompt("已换用更高阻力时，请填写可复现的设置，例如弹力带型号、颜色或握距。");
    if (input?.trim()) act((next, time) => updateResistance(next, input.trim().slice(0, 120), time));
  }));
  if (!state.resistanceUnavailable) {
    actions.append(button("暂无更高阻力", () => act((next, time) => updateResistance(next, null, time))));
  }
}

function exerciseRow(item, now) {
  const { exercise, dose, next, waitingForTrial, due } = item;
  const state = store.exercises[exercise.id];
  const row = node("li", "plan-item");
  row.dataset.exercise = exercise.id;
  const title = node("div", "plan-item__title");
  const name = node("strong", "plan-item__name", exercise.name);
  const level = node("span", "level-chip", `L${state.level}`);
  title.append(name, level);
  row.append(title, node("span", "plan-item__dose", exercise.chineseName));
  const formalDose = dose.trial ? { ...state, trial: false } : dose;
  row.append(node("span", "plan-item__target", `${dose.trial ? "正式计划 · " : ""}${doseLabel(exercise, formalDose)}`));
  const status = [];
  const record = latestFeedback(store, exercise.id);
  if (state.status === "paused") status.push("已暂停 · 请评估相关不适");
  else if (state.status === "maintenance") status.push("维护");
  if (state.resistanceReady) status.push("可确认更高的弹力带阻力");
  if (exercise.trial && state.status !== "paused") {
    if (waitingForTrial) status.push("确认试做后的恢复，方可开始正式训练");
    else if (due) status.push(dose.trial ? `首次耐受试做 · 每侧 ${dose.sets} 组 × ${dose.reps} 次` : "今天安排弯举");
    else status.push(`下次 ${formatScheduleDate(next)}`);
    if (state.resistanceNote) status.push(state.resistanceNote);
  } else if (!due && state.status !== "paused") {
    status.push(state.daysPerWeek < 7 ? `下次 ${formatScheduleDate(next)}` : "今天已记录");
  }
  if (state.status !== "paused" && (state.status !== "maintenance" || exercise.trial)) {
    const goal = GROUPS[exercise.group].positiveTarget;
    status.push(`连续 + ${state.positiveStreak} 次 · 已确认 ${Math.min(confirmedStreak(store, exercise.id, true), goal)} / ${goal}`);
  }
  if (record?.attempted && !record.recovery && record.reason !== "symptoms" && state.status !== "paused") {
    status.push("待确认恢复");
  }
  row.append(node("span", "plan-item__dose", status.join(" · ")));
  if (state.lastChange) {
    row.append(node("span", "plan-item__dose", `最近调整 · ${changeLabel(state.lastChange)}`));
  }
  const actions = node("div", "inline-actions");
  if (due) {
    actions.append(button(dose.trial ? "开始试做" : "开始引导", () => startPlan(exercise.id)));
    actions.append(button(dose.trial ? "试做已完成" : "已完成", () => startPlan(exercise.id, true)));
  }
  if (state.status === "paused") {
    actions.append(button("评估后恢复", () => {
      if (window.confirm("确认已评估相关不适，并适合恢复这个动作？")) {
        act((nextStore, time) => resumeExercise(nextStore, exercise.id, time));
      }
    }));
  } else {
    if (canReportWorse(store, exercise.id, record, now) && (record.recovery || !recoveryAvailable(record, now))) {
      actions.append(button("报告症状加重", () => {
        act((nextStore, time) => confirmRecovery(nextStore, exercise.id, record.id, "worse", time));
      }, "danger-button"));
    }
    if (exercise.trial) renderResistance(state, actions);
  }
  if (actions.childElementCount) row.append(actions);
  return row;
}

function renderHome() {
  const now = new Date();
  const plan = EXERCISES.map((exercise) => planItem(exercise, now));
  const rehab = plan.filter((item) => !item.exercise.trial && item.due);
  elements.todayLabel.textContent = new Intl.DateTimeFormat("zh-CN", {
    month: "long", day: "numeric", weekday: "long",
  }).format(now);
  elements.planDuration.textContent = String(Math.ceil(rehab.reduce((sum, item) => sum + item.durationSeconds, 0) / 60));
  elements.startButton.disabled = !rehab.length;
  elements.startButton.firstElementChild.textContent = rehab.length ? "开始今日康复" : "今天的康复计划已结束";
  elements.planList.replaceChildren(...Object.entries(GROUPS).map(([id, group]) => {
    const section = node("section", "plan-group");
    section.append(node("h3", "", group.name));
    const list = node("ul", "plan-list");
    list.append(...plan.filter((item) => item.exercise.group === id).map((item) => exerciseRow(item, now)));
    section.append(list);
    return section;
  }));
  elements.lastSessionNote.textContent = "可以按需跳过动作。康复进阶以完成质量和恢复确认计算。";
  renderRecovery(now);
  renderExperiment(now);
  updateVoiceButton();
}

function renderExperiment(now) {
  const last = store.measurements[0];
  const next = last && addDays(last.timestamp, 14);
  elements.measurementNote.textContent = !last || dayKey(now) >= dayKey(next)
    ? "可以记录左右上臂围度。建议每两周在相同条件下测量一次。"
    : `下次围度记录 · ${formatSessionDate(next)}`;
  const start = addDays(now, -83);
  start.setHours(0, 0, 0, 0);
  const records = store.sessions.flatMap((session) => session.records ?? []).filter((record) =>
    record.exercise_id === "band_curl" && record.completed && !record.prescribed_dose.trial && new Date(record.timestamp) >= start,
  ).sort((a, b) => b.timestamp.localeCompare(a.timestamp));
  const rows = Array.from({ length: 12 }, (_, index) => {
    const from = addDays(start, (11 - index) * 7);
    const until = addDays(from, 7);
    const inWeek = (entry) => new Date(entry.timestamp) >= from && new Date(entry.timestamp) < until;
    const training = records.filter(inWeek);
    const measurements = store.measurements.filter(inWeek);
    if (!training.length && !measurements.length) return null;
    const row = node("tr");
    const week = node("th", "", new Intl.DateTimeFormat("zh-CN", { month: "numeric", day: "numeric" }).format(from));
    week.scope = "row";
    row.append(week);
    const performance = node("td");
    for (const { prescribed_dose: dose, timestamp } of training) {
      performance.append(node("span", "", `${formatSessionDate(timestamp)} · R${dose.resistanceLevel} · ${dose.sets}×${dose.reps} / 侧 · ${dose.tempoSeconds} 秒/次`));
    }
    const arms = node("td");
    for (const measurement of measurements) {
      arms.append(node("span", "", `${formatSessionDate(measurement.timestamp)} · ${measurement.left} / ${measurement.right}`));
    }
    row.append(performance, arms);
    return row;
  }).filter(Boolean);
  const table = node("table", "trend-table");
  const header = table.createTHead().insertRow();
  for (const title of ["周起始", "完成剂量", "左右围度（cm）"]) header.append(node("th", "", title));
  table.createTBody().append(...rows);
  elements.experimentContent.replaceChildren(rows.length ? table : node("p", "plan-item__dose", "暂无围度或正式弯举记录。"));
}

function newId() {
  return window.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function startWorkout(plan, manual) {
  workout = {
    id: newId(), startedAt: new Date().toISOString(), plan, manual,
    exerciseIndex: 0, stepIndex: 0, paused: false, remainingMs: 0, deadline: 0,
    nextCountdownSecond: 3, adjustments: [],
    results: plan.map((item) => ({
      id: newId(), completedWorkSteps: 0,
      totalWorkSteps: item.steps.filter((step) => step.phase === "work").length,
      skippedWorkSteps: 0, completed: manual,
    })),
  };
  if (manual) {
    renderExerciseFeedback();
  } else {
    showView("workout");
    requestWakeLock();
    enterCurrentStep();
  }
}

function enterCurrentStep() {
  clearTimer();
  if (!workout) return;
  const item = workout.plan[workout.exerciseIndex];
  const step = item.steps[workout.stepIndex];
  if (!step) {
    completeCurrentExercise();
    return;
  }

  workout.paused = false;
  workout.remainingMs = step.duration * 1000;
  workout.deadline = Date.now() + workout.remainingMs;
  workout.nextCountdownSecond = 3;
  renderWorkout();
  speak(step.audioCue, step.prompt);
  preloadNextCue();
  vibrate(step.phase === "work" ? [60] : [35, 40, 35]);
  timerId = window.setInterval(tickTimer, 100);
}

function tickTimer() {
  if (!workout || workout.paused) return;
  const step = currentStep();
  if (!step) return;
  workout.remainingMs = Math.max(0, workout.deadline - Date.now());
  renderTimer(step);

  const countdownSecond = Math.ceil(workout.remainingMs / 1000);
  if (
    step.countDown
    && countdownSecond >= 1
    && countdownSecond <= workout.nextCountdownSecond
  ) {
    workout.nextCountdownSecond = countdownSecond - 1;
    const spokenNumber = ["", "One.", "Two.", "Three."][countdownSecond];
    speakCountdown(`countdown_${countdownSecond}`, spokenNumber);
  }

  if (workout.remainingMs <= 0) {
    finishStep({ skipped: false });
  }
}

function finishStep({ skipped }) {
  if (!workout || workout.saving) return;
  const step = currentStep();
  const result = workout.results[workout.exerciseIndex];
  clearTimer();
  if (step?.phase === "work") {
    if (skipped) result.skippedWorkSteps += 1;
    else result.completedWorkSteps += 1;
  }
  workout.stepIndex += 1;
  const currentItem = workout.plan[workout.exerciseIndex];
  if (workout.stepIndex >= currentItem.steps.length) {
    completeCurrentExercise();
  } else {
    enterCurrentStep();
  }
}

function completeCurrentExercise(manual = false) {
  if (!workout || workout.saving) return;
  const result = workout.results[workout.exerciseIndex];
  result.completed = manual || result.completedWorkSteps === result.totalWorkSteps;
  clearTimer();
  releaseWakeLock();
  speak("exercise_complete", "How did that feel?");
  vibrate([80, 70, 120]);
  renderExerciseFeedback();
}

function skipExercise() {
  submitResult(null);
}

function togglePause() {
  if (!workout || workout.saving) return;
  if (workout.paused) {
    workout.paused = false;
    workout.deadline = Date.now() + workout.remainingMs;
    elements.pauseLabel.textContent = "暂停";
    elements.pauseButton.querySelector(".control-button__icon").textContent = "Ⅱ";
    speak("resumed", "Let's continue.");
    timerId = window.setInterval(tickTimer, 100);
  } else {
    workout.remainingMs = Math.max(0, workout.deadline - Date.now());
    workout.paused = true;
    clearTimer();
    elements.pauseLabel.textContent = "继续";
    elements.pauseButton.querySelector(".control-button__icon").textContent = "▶";
    stopVoice();
    speak("paused", "Paused. Take your time.", { interrupt: false });
  }
  renderWorkout();
}

function renderWorkout() {
  if (!workout) return;
  const item = workout.plan[workout.exerciseIndex];
  const step = currentStep();
  if (!item || !step) return;
  const phaseLabels = { prepare: "准备", work: "动作", switch: "换边", rest: "休息" };

  elements.exercisePosition.textContent = `${workout.exerciseIndex + 1} / ${workout.plan.length}`;
  const totalSteps = workout.plan.reduce((sum, planItem) => sum + planItem.steps.length, 0);
  const priorSteps = workout.plan.slice(0, workout.exerciseIndex).reduce((sum, planItem) => sum + planItem.steps.length, 0);
  const progress = ((priorSteps + workout.stepIndex) / totalSteps) * 100;
  elements.workoutProgress.style.width = `${Math.max(2, progress)}%`;
  elements.phaseBadge.textContent = phaseLabels[step.phase];
  elements.phaseBadge.dataset.phase = step.phase;
  elements.roundLabel.textContent = step.roundLabel;
  elements.exercisePurpose.textContent = item.exercise.purpose;
  elements.exerciseName.textContent = `${item.exercise.name} · ${item.exercise.chineseName}`;
  elements.stepInstruction.textContent = workout.paused ? "已暂停，准备好后继续" : step.instruction;
  elements.nextCue.textContent = step.next;
  elements.formCueText.textContent = item.exercise.cue;
  renderTimer(step);
}

function renderTimer(step) {
  if (!workout || !step) return;
  const seconds = Math.max(0, Math.ceil(workout.remainingMs / 1000));
  const percentage = Math.max(0, Math.min(100, (workout.remainingMs / (step.duration * 1000)) * 100));
  elements.countdown.textContent = String(seconds);
  elements.timerRing.style.setProperty("--timer-progress", `${percentage}%`);
  elements.timerRing.setAttribute("aria-label", `当前步骤剩余 ${seconds} 秒`);
}

function currentStep() {
  return workout?.plan[workout.exerciseIndex]?.steps[workout.stepIndex] || null;
}

function renderExerciseFeedback(negative = false) {
  showView("feedback");
  const item = workout.plan[workout.exerciseIndex];
  const result = workout.results[workout.exerciseIndex];
  elements.feedbackProgress.textContent = `动作 ${workout.exerciseIndex + 1} / ${workout.plan.length}`;
  elements.feedbackExercise.textContent = `${item.exercise.name} · ${item.exercise.chineseName}`;
  elements.feedbackIntro.textContent = result.completed
    ? "训练当天或次日如有症状加重，可在首页报告。"
    : "本次动作未完整完成。仍可报告训练困难或不适。";
  elements.feedbackChoices.hidden = negative || !result.completed;
  elements.feedbackReasons.hidden = !negative && result.completed;
  document.getElementById("feedback-back").hidden = !result.completed;
  elements.cancelFeedback.hidden = !workout.manual && result.completed && !workout.saveFailed;
  elements.cancelFeedback.textContent = workout.manual || workout.saveFailed ? "取消" : "跳过这次反馈";
  for (const control of elements.feedbackForm.querySelectorAll("button")) control.disabled = false;
}

function saveFeedback(event) {
  event.preventDefault();
  const value = event.submitter?.value;
  if (value === "+" || value === "0") submitResult(value);
  else if (value === "difficulty" || value === "symptoms") submitResult("-", value);
}

async function submitResult(feedback, reason) {
  if (!workout || workout.saving) return;
  const current = workout;
  const { exercise, dose } = current.plan[current.exerciseIndex];
  const result = current.results[current.exerciseIndex];
  const attempted = Boolean(feedback || result.completedWorkSteps
    || current.plan[current.exerciseIndex].steps[current.stepIndex]?.phase === "work");
  const input = { id: result.id, sessionId: current.id, startedAt: current.startedAt,
    completed: Boolean(feedback && result.completed), attempted, dose, feedback, reason };
  current.saving = true;
  clearTimer();
  for (const control of elements.feedbackForm.querySelectorAll("button")) control.disabled = true;

  try {
    const change = await updateStore((next, time) => current.correction
      ? replaceFeedback(next, exercise.id, current.correction, feedback, reason, time)
      : saveTraining(next, exercise.id, input, time));
    if (change) current.adjustments.push({ name: exercise.chineseName, change });
    if (current.correction) {
      workout = null;
      showView("home");
      renderHome();
      renderHistory();
      elements.historyDialog.showModal();
      showToast("反馈已更新");
      return;
    }
    if (feedback === "+") speak("feedback_good", "Got it.");
    else if (feedback === "-") speak(reason === "symptoms" ? null : "feedback_bad",
      reason === "symptoms" ? "Movement paused." : "Got it.");
    else speak("exercise_skipped", "Exercise skipped.");
    await advanceToNextExercise(current);
  } catch (error) {
    current.saving = false;
    current.saveFailed = true;
    displayError(error);
    if (workout === current) renderExerciseFeedback();
  }
}

async function advanceToNextExercise(current) {
  if (workout !== current) return;
  current.exerciseIndex += 1;
  current.stepIndex = 0;
  if (current.exerciseIndex >= current.plan.length) {
    await finishWorkout();
    return;
  }
  window.setTimeout(() => {
    if (workout !== current) return;
    current.saving = false;
    const item = current.plan[current.exerciseIndex];
    const next = refreshStore() && schedule(store, item.exercise, new Date());
    if (!next?.due || next.dose.version !== item.dose.version || next.dose.trial !== item.dose.trial) {
      advanceToNextExercise(current);
      return;
    }
    showView("workout");
    requestWakeLock();
    enterCurrentStep();
  }, 850);
}

async function closeSession(status) {
  const current = workout;
  await updateStore((next, now) => {
    if (status === "partial") {
      const { exercise, dose } = current.plan[current.exerciseIndex];
      const result = current.results[current.exerciseIndex];
      if (result.completedWorkSteps || currentStep()?.phase === "work") {
        const nextPlan = schedule(next, exercise, now);
        if (nextPlan.due && nextPlan.dose.version === dose.version && nextPlan.dose.trial === dose.trial) {
          saveTraining(next, exercise.id, {
            id: result.id, sessionId: current.id, startedAt: current.startedAt,
            completed: false, attempted: true, dose, feedback: null,
          }, now);
        }
      }
    }
    const session = next.sessions.find((entry) => entry.id === current.id);
    if (!session) return;
    session.status = status;
    session.completedAt = status === "completed" ? now.toISOString() : null;
  });
}

async function finishWorkout() {
  clearTimer();
  releaseWakeLock();
  try {
    await closeSession("completed");
  } catch (error) {
    displayError(error);
  }
  renderSummary(workout.adjustments);
  workout = null;
  showView("summary");
}

function renderSummary(adjustments) {
  elements.summaryCopy.textContent = adjustments.some(({ change }) => change.type === "paused")
    ? "因不适暂停的动作会从计划中移除，待评估后可在首页恢复。"
    : "训练已保存。训练当天或次日如有症状加重，可在首页报告。";
  elements.adjustmentList.replaceChildren(...adjustments.map(({ name, change }) => {
    const row = node("article", "adjustment-item");
    const copy = node("div");
    copy.append(node("strong", "", name), node("small", "", changeLabel(change)));
    row.append(copy);
    return row;
  }));
}

function renderHistory() {
  const now = new Date();
  const adjustments = node("details", "experiment-trend");
  adjustments.append(node("summary", "", "剂量调整历史"));
  for (const change of store.changes.slice().reverse()) {
    const exercise = EXERCISES.find((item) => item.id === change.exerciseId);
    adjustments.append(node("p", "plan-item__dose",
      `${formatSessionDate(change.timestamp)} · ${exercise?.chineseName} · ${changeLabel(change)}`));
  }
  if (!store.changes.length) adjustments.append(node("p", "plan-item__dose", "暂无调整。"));

  const sessions = store.sessions.map((session) => {
    const article = node("article", "history-session");
    const top = node("div", "history-session__top");
    const stamp = session.timestamp ?? session.startedAt;
    const time = stamp && Number.isFinite(Date.parse(stamp))
      ? new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(stamp)) : "";
    top.append(node("strong", "", formatSessionDate(stamp)), node("span", "", time));
    const list = node("ul", "history-session__exercises");
    for (const record of session.records ?? []) {
      const exercise = EXERCISES.find((item) => item.id === record.exercise_id);
      const name = exercise?.chineseName ?? store.archived[record.exercise_id]?.name ?? record.exercise_id;
      const item = node("li");
      item.dataset.feedback = record.feedback || "skipped";
      const label = record.voidedAt ? "反馈已撤销" : (FEEDBACK_LABELS[record.feedback] ?? record.feedback)
        || (record.completed ? "旧规则记录" : "已跳过");
      const recovery = record.recovery?.outcome === "ok" ? "恢复无加重" : record.recovery ? "恢复有加重" : "";
      const reason = { difficulty: "困难", symptoms: "有症状" }[record.reason];
      item.append(node("span", "", [
        name, !exercise && "已归档", record.level && `L${record.level}`,
        record.prescribed_dose?.trial && "试做", doseLabel(exercise, record.prescribed_dose ?? {}),
        record.prescribed_dose?.resistanceNote, label, reason, recovery,
      ].filter(Boolean).join(" · ")));
      const actions = node("div", "inline-actions");
      if (exercise && !workout) {
        if (store.undo[exercise.id]?.recordId === record.id && !record.voidedAt) {
          actions.append(button("撤销反馈", () => act((next, time) => undoFeedback(next, exercise.id, record.id, time))));
        }
        if (canReplaceFeedback(store, record)) {
          actions.append(button("重新反馈", () => {
            elements.historyDialog.close();
            startWorkout([{ exercise, dose: record.prescribed_dose, steps: [] }], true);
            workout.results[0].completed = record.completed;
            workout.correction = record.id;
            renderExerciseFeedback();
          }));
        }
        if (canReportWorse(store, exercise.id, record, now)) {
          actions.append(button("报告加重", () => act((next, time) =>
            confirmRecovery(next, exercise.id, record.id, "worse", time)), "danger-button"));
        }
      }
      if (actions.childElementCount) item.append(actions);
      list.append(item);
    }
    article.append(top, list);
    return article;
  });
  if (!sessions.length) sessions.push(node("p", "history-empty", "还没有训练记录。"));
  elements.historyContent.replaceChildren(adjustments, ...sessions);
}

function showView(name) {
  for (const [viewName, view] of Object.entries(views)) view.hidden = viewName !== name;
  document.body.dataset.view = name;
  window.scrollTo({ top: 0, behavior: "instant" });
}

async function toggleVoice() {
  try {
    await updateStore((next) => { next.voiceEnabled = !next.voiceEnabled; });
  } catch (error) {
    displayError(error);
    return;
  }
  if (!store.voiceEnabled) stopVoice();
  else speak("voice_enabled", "Audio guidance is on.");
  updateVoiceButton();
}

function updateVoiceButton() {
  elements.voiceToggle.setAttribute("aria-pressed", String(store.voiceEnabled));
  elements.voiceToggle.setAttribute("aria-label", store.voiceEnabled ? "关闭语音播报" : "开启语音播报");
  elements.voiceToggle.querySelector(".icon-button__label").textContent = store.voiceEnabled ? "语音开" : "语音关";
}

function speak(cueId, fallbackText, { interrupt = true } = {}) {
  if (!store.voiceEnabled || !fallbackText) return;
  if (interrupt) stopVoice();

  const audio = getCueAudio(cueId);
  if (!audio) {
    speakFallback(fallbackText, { interrupt: false });
    return;
  }

  activeAudio = audio;
  audio.currentTime = 0;
  audio.play().catch(() => {
    if (activeAudio === audio) activeAudio = null;
    speakFallback(fallbackText, { interrupt: false });
  });
}

function speakCountdown(cueId, fallbackText) {
  if (!store.voiceEnabled || !fallbackText) return;
  const cue = audioManifest?.cues?.[cueId];
  if (!cue?.file) {
    speakFallback(fallbackText, { interrupt: false });
    return;
  }

  countdownAudio.pause();
  countdownAudio.src = `${AUDIO_BASE_URL}/${cue.file}`;
  countdownAudio.currentTime = 0;
  countdownAudio.play().catch(() => {
    speakFallback(fallbackText, { interrupt: false });
  });
}

function speakFallback(text, { interrupt = true } = {}) {
  if (!("speechSynthesis" in window) || !("SpeechSynthesisUtterance" in window)) return;
  if (interrupt) window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = "en-US";
  utterance.rate = 0.92;
  utterance.pitch = 1;
  const voices = window.speechSynthesis.getVoices();
  const englishVoice = voices.find((voice) => /^en[-_]US/i.test(voice.lang))
    || voices.find((voice) => /^en[-_]/i.test(voice.lang));
  if (englishVoice) utterance.voice = englishVoice;
  window.speechSynthesis.speak(utterance);
}

async function loadAudioManifest() {
  try {
    const response = await fetch(AUDIO_MANIFEST_URL, { cache: "no-store" });
    if (!response.ok) return null;
    audioManifest = await response.json();
    ["countdown_3", "countdown_2", "countdown_1"].forEach(preloadCue);
    return audioManifest;
  } catch (_error) {
    return null;
  }
}

function getCueAudio(cueId) {
  const cue = audioManifest?.cues?.[cueId];
  if (!cue?.file) return null;
  if (!audioCache.has(cueId)) {
    const audio = new Audio(`${AUDIO_BASE_URL}/${cue.file}`);
    audio.preload = "auto";
    audio.addEventListener("ended", () => {
      if (activeAudio === audio) activeAudio = null;
    });
    audioCache.set(cueId, audio);
  }
  return audioCache.get(cueId);
}

function preloadCue(cueId) {
  const audio = getCueAudio(cueId);
  if (audio) audio.load();
}

function preloadNextCue() {
  if (!workout) return;
  const currentItem = workout.plan[workout.exerciseIndex];
  const nextStep = currentItem.steps[workout.stepIndex + 1];
  const nextExercise = workout.plan[workout.exerciseIndex + 1];
  const cueId = nextStep?.audioCue || nextExercise?.steps[0]?.audioCue;
  if (cueId) preloadCue(cueId);
}

function stopVoice() {
  if (activeAudio) {
    activeAudio.pause();
    activeAudio.currentTime = 0;
    activeAudio = null;
  }
  countdownAudio.pause();
  countdownAudio.currentTime = 0;
  window.speechSynthesis?.cancel();
}

function vibrate(pattern) {
  if (navigator.vibrate) navigator.vibrate(pattern);
}

async function requestWakeLock() {
  if (!("wakeLock" in navigator)) return;
  try {
    const lock = await navigator.wakeLock.request("screen");
    if (!workout || views.workout.hidden || wakeLock) {
      await lock.release();
      return;
    }
    wakeLock = lock;
    lock.addEventListener("release", () => { if (wakeLock === lock) wakeLock = null; });
  } catch (_error) {
    wakeLock = null;
  }
}

function releaseWakeLock() {
  if (wakeLock) wakeLock.release().catch(() => {});
  wakeLock = null;
}

function clearTimer() {
  if (timerId !== null) window.clearInterval(timerId);
  timerId = null;
}

function formatSessionDate(value) {
  const date = new Date(value);
  if (!value || Number.isNaN(+date)) return "日期未知";
  const today = new Date();
  if (date.toDateString() === today.toDateString()) return "今天";
  return new Intl.DateTimeFormat("zh-CN", { year: "numeric", month: "short", day: "numeric" }).format(date);
}

function showToast(message) {
  window.clearTimeout(toastTimer);
  elements.toast.textContent = message;
  elements.toast.hidden = false;
  toastTimer = window.setTimeout(() => { elements.toast.hidden = true; }, 2800);
}

function formatScheduleDate(date) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hourCycle: "h23",
  }).format(date);
}

elements.startButton.addEventListener("click", () => startPlan());
elements.voiceToggle.addEventListener("click", toggleVoice);
elements.pauseButton.addEventListener("click", togglePause);
elements.skipStepButton.addEventListener("click", () => finishStep({ skipped: true }));
elements.skipExerciseButton.addEventListener("click", skipExercise);
document.getElementById("complete-exercise").addEventListener("click", () => completeCurrentExercise(true));
document.getElementById("report-symptom").addEventListener("click", () => submitResult("-", "symptoms"));
document.getElementById("negative-feedback").addEventListener("click", () => renderExerciseFeedback(true));
document.getElementById("feedback-back").addEventListener("click", () => renderExerciseFeedback());
elements.cancelFeedback.addEventListener("click", () => {
  if (workout.saving) return;
  if (workout.manual || workout.saveFailed) {
    const returnToHistory = workout.correction;
    workout = null;
    showView("home");
    renderHome();
    if (returnToHistory) {
      renderHistory();
      elements.historyDialog.showModal();
    }
  } else {
    skipExercise();
  }
});
elements.exitWorkout.addEventListener("click", () => {
  if (!workout || workout.saving) return;
  if (!workout.paused) togglePause();
  elements.confirmDialog.showModal();
});
elements.confirmCancel.addEventListener("click", () => elements.confirmDialog.close());
elements.confirmDialog.addEventListener("close", () => {
  if (workout?.paused) togglePause();
});
elements.confirmExit.addEventListener("click", async () => {
  if (!workout || workout.saving) return;
  workout.saving = true;
  clearTimer();
  releaseWakeLock();
  stopVoice();
  try {
    await closeSession("partial");
  } catch (error) {
    displayError(error);
  }
  workout = null;
  elements.confirmDialog.close();
  showView("home");
  renderHome();
});
elements.feedbackForm.addEventListener("submit", saveFeedback);
elements.doneButton.addEventListener("click", () => {
  renderHome();
  showView("home");
});
elements.historyButton.addEventListener("click", () => {
  refreshStore();
  renderHistory();
  elements.historyDialog.showModal();
});
elements.closeHistory.addEventListener("click", () => elements.historyDialog.close());
elements.historyDialog.addEventListener("click", (event) => {
  if (event.target === elements.historyDialog) elements.historyDialog.close();
});
elements.resetDataButton.addEventListener("click", async () => {
  if (!window.confirm("确定清除全部训练记录与等级？此操作无法撤销。")) return;
  try {
    await updateStore((next) => {
      for (const key of Object.keys(next)) delete next[key];
      Object.assign(next, migrateStore());
    });
    renderHistory();
    renderHome();
    showToast("训练数据已清除");
  } catch (error) {
    displayError(error);
  }
});
elements.measurementForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = new FormData(elements.measurementForm);
  try {
    await updateStore((next, now) => {
      const values = { timestamp: now.toISOString(), left: Number(data.get("left")), right: Number(data.get("right")) };
      next.measurements.unshift(values);
    });
    elements.measurementForm.reset();
    renderExperiment(new Date());
    showToast("围度已保存");
  } catch (error) {
    displayError(error);
  }
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  if (workout && !views.workout.hidden && !wakeLock) requestWakeLock();
  if (!views.home.hidden && refreshStore()) renderHome();
});
window.addEventListener("storage", (event) => {
  if (event.key !== STORAGE_KEY || !refreshStore()) return;
  const active = workout?.plan[workout.exerciseIndex];
  if (active && !workout.saving && !workout.correction && store.exercises[active.exercise.id].status === "paused") {
    clearTimer();
    releaseWakeLock();
    stopVoice();
    workout = null;
    if (elements.confirmDialog.open) elements.confirmDialog.close();
    showView("home");
    showToast("该动作已暂停，请查看今日计划。");
  }
  if (!views.home.hidden) renderHome();
  if (elements.historyDialog.open) renderHistory();
});
window.setInterval(() => {
  if (!views.home.hidden && !document.hidden) renderHome();
}, 60_000);
window.addEventListener("beforeunload", () => {
  clearTimer();
  releaseWakeLock();
});

if (refreshStore()) {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  if (saved && saved.version !== store.version && localStorage.getItem(STORAGE_KEY)) {
    updateStore(() => {}).catch(displayError);
  }
}
showView("home");
renderHome();
loadAudioManifest();
