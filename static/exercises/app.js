import { EXERCISES, GROUPS, POSITIONS } from "./config.mjs?v=7";
import { buildSteps } from "./guide.mjs?v=7";
import { createGuideAudio } from "./audio.mjs?v=7";
import {
  STORAGE_KEY, FEEDBACK_LABELS, migrateStore, schedule, saveTraining,
  undoFeedback, resumeExercise, updateResistance, eligibleStreak, canReplaceFeedback, replaceFeedback,
} from "./training.mjs?v=7";

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
  feedbackIntro: document.getElementById("feedback-intro"),
  cancelFeedback: document.getElementById("cancel-feedback"),
};

const exerciseOrder = Object.keys(POSITIONS)
  .flatMap((position) => EXERCISES.filter((exercise) => exercise.position === position));

let store = migrateStore();
let workout = null;
let timerId = null;
let wakeLock = null;
let toastTimer = null;
const guideAudio = createGuideAudio();

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
  if (change.type === "paused") return "按反馈暂停";
  if (change.type === "resumed") return "已恢复计划";
  if (change.type === "resistanceReady") return "当前阻力下已达到计划训练量，可以确认更高阻力";
  if (change.type === "maintenance") return "已进入维护";
  if (change.type === "undo") return "已撤销反馈及由此产生的调整";
  if (change.type === "guideTempo") return `猫式和牛式各 ${change.after.tempoSeconds / 2} 秒`;
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
  const plan = exerciseOrder.filter((exercise) => !exerciseId || exercise.id === exerciseId)
    .map((exercise) => planItem(exercise, now)).filter((item) => item.due);
  if (!plan.length) {
    renderHome();
    return;
  }
  startWorkout(plan, manual);
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

function exerciseRow(item) {
  const { exercise, dose, next, due } = item;
  const state = store.exercises[exercise.id];
  const isCurl = exercise.id === "band_curl";
  const row = node("li", "plan-item");
  row.dataset.exercise = exercise.id;
  row.dataset.due = String(due);
  const title = node("div", "plan-item__title");
  const name = node("strong", "plan-item__name", exercise.name);
  const level = node("span", "level-chip", `L${state.level}`);
  title.append(name, level);
  row.append(title, node("span", "plan-item__dose", exercise.chineseName));
  row.append(node("span", "plan-item__target", doseLabel(exercise, dose)));
  const status = [];
  if (state.status === "paused") status.push("已暂停");
  else if (state.status === "maintenance") status.push("维护");
  if (state.resistanceReady) status.push("可确认更高的弹力带阻力");
  if (state.status !== "paused") {
    if (isCurl && due) status.push("已加入今日训练");
    else if (!due) status.push(state.daysPerWeek < 7 ? `下次 ${formatScheduleDate(next)}` : "今天已记录");
    if (state.status !== "maintenance" || isCurl) {
      const goal = GROUPS[exercise.group].positiveTarget;
      status.push(`进阶进度 ${Math.min(eligibleStreak(store, exercise.id), goal)} / ${goal}`);
    }
  }
  if (isCurl && state.resistanceNote) status.push(state.resistanceNote);
  row.append(node("span", "plan-item__dose", status.join(" · ")));
  if (state.lastChange) {
    row.append(node("span", "plan-item__dose", `最近调整 · ${changeLabel(state.lastChange)}`));
  }
  const actions = node("div", "inline-actions");
  if (due && !isCurl) {
    actions.append(button("开始引导", () => startPlan(exercise.id)));
    actions.append(button("已完成", () => startPlan(exercise.id, true)));
  }
  if (state.status === "paused") {
    actions.append(button("恢复动作", () => act((nextStore, time) => resumeExercise(nextStore, exercise.id, time))));
  } else if (isCurl) {
    renderResistance(state, actions);
  }
  if (actions.childElementCount) row.append(actions);
  return row;
}

function renderHome() {
  const now = new Date();
  const plan = exerciseOrder.map((exercise) => planItem(exercise, now));
  const due = plan.filter((item) => item.due);
  elements.todayLabel.textContent = new Intl.DateTimeFormat("zh-CN", {
    month: "long", day: "numeric", weekday: "long",
  }).format(now);
  elements.planDuration.textContent = String(Math.ceil(due.reduce((sum, item) => sum + item.durationSeconds, 0) / 60));
  elements.startButton.disabled = !due.length;
  elements.startButton.firstElementChild.textContent = due.length ? `开始今日训练 · ${due.length} 个动作` : "今天没有待练动作";
  elements.planList.replaceChildren(...Object.entries(POSITIONS).map(([id, name]) => {
    const section = node("section", "plan-group");
    section.append(node("h3", "", name));
    const list = node("ul", "plan-list");
    list.append(...plan.filter((item) => item.exercise.position === id).map(exerciseRow));
    section.append(list);
    return section;
  }));
  elements.lastSessionNote.textContent = "可以按需跳过动作。";
  updateVoiceButton();
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
    if (store.voiceEnabled) {
      guideAudio.unlock();
      guideAudio.preload();
    }
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
  const cueWindow = step.countDown
    ? Math.min(step.duration, step.duration + (step.countDownAfter ?? 0) - 3) : step.duration;
  if (cueWindow > 0) speak(step.audioCue, { tone: step.tone, windowSeconds: cueWindow });
  else guideAudio.stop();
  vibrate(step.phase === "work" ? [60] : [35, 40, 35]);
  timerId = window.setInterval(tickTimer, 100);
}

function tickTimer() {
  if (!workout || workout.paused) return;
  const step = currentStep();
  if (!step) return;
  workout.remainingMs = Math.max(0, workout.deadline - Date.now());
  if (workout.remainingMs <= 0) {
    finishStep({ skipped: false });
    return;
  }
  renderTimer(step);

  const countdownSecond = Math.ceil(secondsLeft(step));
  if (
    step.countDown
    && countdownSecond >= 1
    && countdownSecond <= workout.nextCountdownSecond
  ) {
    workout.nextCountdownSecond = countdownSecond - 1;
    if (store.voiceEnabled) guideAudio.countdown(countdownSecond);
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
  speak("exercise_complete", { tone: "done" });
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
    if (store.voiceEnabled) guideAudio.unlock();
    speak("resumed");
    timerId = window.setInterval(tickTimer, 100);
  } else {
    workout.remainingMs = Math.max(0, workout.deadline - Date.now());
    workout.paused = true;
    clearTimer();
    elements.pauseLabel.textContent = "继续";
    elements.pauseButton.querySelector(".control-button__icon").textContent = "▶";
    speak("paused");
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

function secondsLeft(step) {
  return workout.remainingMs / 1000 + (step.countDownAfter ?? 0);
}

function renderTimer(step) {
  if (!workout || !step) return;
  const seconds = Math.ceil(secondsLeft(step));
  const percentage = Math.min(100, (secondsLeft(step) / (step.countDownTotal ?? step.duration)) * 100);
  elements.countdown.textContent = String(seconds);
  elements.timerRing.style.setProperty("--timer-progress", `${percentage}%`);
  elements.timerRing.setAttribute("aria-label", `当前步骤剩余 ${seconds} 秒`);
}

function currentStep() {
  return workout?.plan[workout.exerciseIndex]?.steps[workout.stepIndex] || null;
}

function renderExerciseFeedback() {
  showView("feedback");
  const item = workout.plan[workout.exerciseIndex];
  const result = workout.results[workout.exerciseIndex];
  elements.feedbackProgress.textContent = `动作 ${workout.exerciseIndex + 1} / ${workout.plan.length}`;
  elements.feedbackExercise.textContent = `${item.exercise.name} · ${item.exercise.chineseName}`;
  elements.feedbackIntro.textContent = result.completed ? "选择这次的感受。" : "这次动作提前结束，可以记录感受。";
  elements.cancelFeedback.hidden = !workout.manual && !workout.saveFailed;
  elements.cancelFeedback.textContent = "取消";
  for (const control of elements.feedbackForm.querySelectorAll("button")) control.disabled = false;
}

function saveFeedback(event) {
  event.preventDefault();
  const value = event.submitter?.value;
  if (value === "+" || value === "-") submitResult(value);
}

async function submitResult(feedback) {
  if (!workout || workout.saving) return;
  const current = workout;
  const { exercise, dose } = current.plan[current.exerciseIndex];
  const result = current.results[current.exerciseIndex];
  const attempted = Boolean(feedback || result.completedWorkSteps
    || current.plan[current.exerciseIndex].steps[current.stepIndex]?.phase === "work");
  const input = { id: result.id, sessionId: current.id, startedAt: current.startedAt,
    completed: Boolean(feedback && result.completed), attempted, dose, feedback };
  current.saving = true;
  clearTimer();
  guideAudio.stop();
  for (const control of elements.feedbackForm.querySelectorAll("button")) control.disabled = true;

  try {
    const change = await updateStore((next, time) => current.correction
      ? replaceFeedback(next, exercise.id, current.correction, feedback, time)
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
    if (feedback === "+") speak("feedback_good");
    else if (feedback === "-") speak("symptom_stop");
    else speak("exercise_skipped");
    await advanceToNextExercise(current, feedback === "-" ? 1800 : 850);
  } catch (error) {
    current.saving = false;
    current.saveFailed = true;
    displayError(error);
    if (workout === current) renderExerciseFeedback();
  }
}

async function advanceToNextExercise(current, delay = 850) {
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
    if (!next?.due || next.dose.version !== item.dose.version) {
      advanceToNextExercise(current);
      return;
    }
    showView("workout");
    requestWakeLock();
    enterCurrentStep();
  }, delay);
}

async function closeSession(status) {
  const current = workout;
  await updateStore((next, now) => {
    if (status === "partial") {
      const { exercise, dose } = current.plan[current.exerciseIndex];
      const result = current.results[current.exerciseIndex];
      if (result.completedWorkSteps || currentStep()?.phase === "work") {
        const nextPlan = schedule(next, exercise, now);
        if (nextPlan.due && nextPlan.dose.version === dose.version) {
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
    ? "标为不合适的动作已暂停，可在首页恢复。"
    : "训练已保存。";
  elements.adjustmentList.replaceChildren(...adjustments.map(({ name, change }) => {
    const row = node("article", "adjustment-item");
    const copy = node("div");
    copy.append(node("strong", "", name), node("small", "", changeLabel(change)));
    row.append(copy);
    return row;
  }));
}

function renderHistory() {
  const adjustments = node("details", "dose-history");
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
      item.append(node("span", "", [
        name, !exercise && "已归档", record.level && `L${record.level}`,
        record.prescribed_dose?.trial && "试做", doseLabel(exercise, record.prescribed_dose ?? {}),
        record.prescribed_dose?.resistanceNote, label,
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
  if (!store.voiceEnabled) guideAudio.unlock({ reset: true });
  try {
    await updateStore((next) => { next.voiceEnabled = !next.voiceEnabled; });
  } catch (error) {
    displayError(error);
    return;
  }
  if (store.voiceEnabled) {
    guideAudio.preload();
    speak("voice_enabled");
  } else {
    guideAudio.disable();
  }
  updateVoiceButton();
}

function updateVoiceButton() {
  elements.voiceToggle.setAttribute("aria-pressed", String(store.voiceEnabled));
  elements.voiceToggle.setAttribute("aria-label", store.voiceEnabled ? "关闭语音播报" : "开启语音播报");
  elements.voiceToggle.querySelector(".icon-button__label").textContent = store.voiceEnabled ? "语音开" : "语音关";
}

function speak(cueId, options) {
  if (store.voiceEnabled) guideAudio.play(cueId, options);
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
elements.cancelFeedback.addEventListener("click", () => {
  if (workout.saving) return;
  const returnToHistory = workout.correction;
  workout = null;
  showView("home");
  renderHome();
  if (returnToHistory) {
    renderHistory();
    elements.historyDialog.showModal();
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
  guideAudio.stop();
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
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  if (store.voiceEnabled) guideAudio.recover();
  if (workout && !views.workout.hidden && !wakeLock) requestWakeLock();
  if (!views.home.hidden && refreshStore()) renderHome();
});
for (const event of ["focus", "pageshow"]) {
  window.addEventListener(event, () => {
    if (store.voiceEnabled) guideAudio.recover();
  });
}
document.addEventListener("pointerdown", () => {
  if (store.voiceEnabled) guideAudio.recover({ userGesture: true });
}, { passive: true });
document.addEventListener("keydown", () => {
  if (store.voiceEnabled) guideAudio.recover({ userGesture: true });
});
window.addEventListener("storage", (event) => {
  if (event.key !== STORAGE_KEY || !refreshStore()) return;
  if (!store.voiceEnabled) guideAudio.disable();
  const active = workout?.plan[workout.exerciseIndex];
  if (active && !workout.saving && !workout.correction && store.exercises[active.exercise.id].status === "paused") {
    clearTimer();
    releaseWakeLock();
    guideAudio.stop();
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
  guideAudio.disable();
});

if (refreshStore()) {
  const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
  if (saved && saved.version !== store.version && localStorage.getItem(STORAGE_KEY)) {
    updateStore(() => {}).catch(displayError);
  }
}
showView("home");
renderHome();
if (store.voiceEnabled) guideAudio.preload();
