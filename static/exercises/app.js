const STORAGE_KEY = "fengdock.exercises.v1";
const STORAGE_VERSION = 2;
const AUDIO_BASE_URL = "/static/exercises/audio";
const AUDIO_MANIFEST_URL = `${AUDIO_BASE_URL}/manifest.json`;

const EXERCISES = [
  {
    id: "cat_cow",
    name: "Cat-Cow",
    chineseName: "猫牛式",
    purpose: "温和活动脊柱 · 不做力量进阶",
    cue: "猫式时拱背，牛式时塌腰并抬起胸口；只在舒适范围内缓慢活动，不强迫做到最大屈曲或伸展。",
    fixedDose: { level: 1, reps: 10, secondsPerRep: 12 },
    automaticProgression: false,
    buildSteps(dose) {
      const catPhaseDuration = Math.ceil(dose.secondsPerRep / 2);
      const cowPhaseDuration = dose.secondsPerRep - catPhaseDuration;
      const steps = [prepareStep(
        "cat_cow_prepare",
        "Cat cow. Come onto your hands and knees. Work slowly, and stay within a comfortable range.",
      )];
      for (let rep = 1; rep <= dose.reps; rep += 1) {
        steps.push({
          phase: "work",
          duration: catPhaseDuration,
          instruction: "猫式：缓慢拱背",
          audioCue: `cat_cow_round_${rep}`,
          prompt: `Rep ${rep}. Slowly round your back.`,
          roundLabel: `第 ${rep} 次 / 共 ${dose.reps} 次 · 猫式拱背`,
          next: "接下来：牛式塌腰并抬胸",
          countDown: true,
        });
        steps.push({
          phase: "work",
          duration: cowPhaseDuration,
          instruction: "牛式：缓慢塌腰并抬起胸口",
          audioCue: "cat_cow_arch",
          prompt: "Cow. Gently arch your back and lift your chest.",
          roundLabel: `第 ${rep} 次 / 共 ${dose.reps} 次 · 牛式塌腰`,
          next: rep === dose.reps ? "接下来：动作完成" : `接下来：第 ${rep + 1} 次猫式拱背`,
          countDown: false,
        });
      }
      return steps;
    },
    doseLabel(dose) {
      return `${dose.reps} 次 · 每次约 ${dose.secondsPerRep} 秒`;
    },
  },
  {
    id: "high_incline_push_up",
    name: "High Incline Push-Up",
    chineseName: "高位斜板俯卧撑",
    purpose: "胸肌与肱三头肌力量 · 上肢线条",
    cue: "使用稳定厨房台面；双手约肩宽，脚距台面约 80 厘米；头、肩、髋、脚跟近似一线，腹部轻收并夹紧臀部；肘部与躯干约 30–45°。腰、肩或手腕不适请选“不舒服”。",
    levels: [
      { level: 1, sets: 2, repsPerSet: 8, restSeconds: 22.5, secondsPerRep: 5 },
      { level: 2, sets: 2, repsPerSet: 10, restSeconds: 22.5, secondsPerRep: 5 },
      { level: 3, sets: 2, repsPerSet: 12, restSeconds: 22.5, secondsPerRep: 5 },
      { level: 4, sets: 3, repsPerSet: 8, restSeconds: 22.5, secondsPerRep: 5 },
      { level: 5, sets: 3, repsPerSet: 10, restSeconds: 22.5, secondsPerRep: 5 },
      { level: 6, sets: 3, repsPerSet: 12, restSeconds: 22.5, secondsPerRep: 5 },
    ],
    maxAutoLevel: 6,
    manualReviewAtMax: true,
    buildSteps(dose) {
      const steps = [prepareStep(
        "high_incline_prepare",
        "High incline push-up. Use a stable kitchen counter about ten centimeters below navel height. Place your hands about shoulder-width apart, and start with your feet about eighty centimeters from the counter. Keep your body in one straight line, lightly brace your core, and squeeze your glutes.",
        20,
      )];
      for (let set = 1; set <= dose.sets; set += 1) {
        for (let rep = 1; rep <= dose.repsPerSet; rep += 1) {
          const firstRep = rep === 1;
          const lastRep = rep === dose.repsPerSet;
          const lastSet = set === dose.sets;
          steps.push({
            phase: "work",
            duration: dose.secondsPerRep,
            instruction: "胸部靠近台面，再受控推回",
            audioCue: firstRep ? `high_incline_set_${set}_start` : `high_incline_rep_${rep}`,
            prompt: firstRep
              ? `Set ${set}. Begin. Lower your chest toward the counter, then press back up.`
              : `Rep ${rep}. Lower slowly, then press up.`,
            roundLabel: `第 ${set} 组 · 第 ${rep} 次 / 共 ${dose.repsPerSet} 次`,
            next: lastRep
              ? (lastSet ? "接下来：动作完成" : `接下来：休息 ${dose.restSeconds} 秒`)
              : `接下来：第 ${rep + 1} 次`,
            countDown: false,
          });
        }
        if (set < dose.sets) {
          steps.push(restStep(
            dose.restSeconds,
            `high_incline_rest_${set + 1}`,
            `Set ${set} complete. Rest for twenty-two and a half seconds. Set ${set + 1} is next.`,
            `第 ${set} 组完成 / 共 ${dose.sets} 组`,
          ));
        }
      }
      return steps;
    },
    doseLabel(dose) {
      return `${dose.sets} 组 · 每组 ${dose.repsPerSet} 次 · 休息 ${dose.restSeconds} 秒`;
    },
  },
  {
    id: "bird_dog",
    name: "Bird-Dog",
    chineseName: "鸟狗式",
    purpose: "骨盆与腰椎稳定 · 抗旋转控制",
    cue: "向外延伸，不追求抬高；保持骨盆稳定，不塌腰，正常呼吸。",
    levels: [
      { level: 1, holdSeconds: 10, repsPerSide: 5 },
      { level: 2, holdSeconds: 10, repsPerSide: 6 },
      { level: 3, holdSeconds: 10, repsPerSide: 7 },
      { level: 4, holdSeconds: 10, repsPerSide: 8 },
    ],
    maxAutoLevel: 4,
    buildSteps(dose) {
      const steps = [prepareStep(
        "bird_dog_prepare",
        "Bird dog. Come onto your hands and knees, find a steady position, and get ready.",
      )];
      const totalHolds = dose.repsPerSide * 2;
      let holdIndex = 0;
      for (let round = 1; round <= dose.repsPerSide; round += 1) {
        holdIndex += 1;
        steps.push({
          phase: "work",
          duration: dose.holdSeconds,
          instruction: "左臂向前，右腿向后",
          audioCue: round === 1 ? "bird_dog_left_first" : "bird_dog_left",
          prompt: round === 1
            ? "Begin. Reach your left arm forward and your right leg back. Keep your pelvis steady and breathe."
            : "Left arm forward, right leg back. Stay steady and breathe.",
          roundLabel: `第 ${round} 轮 / 共 ${dose.repsPerSide} 轮`,
          next: "接下来：换边",
          countDown: true,
        });
        if (holdIndex < totalHolds) {
          steps.push(switchStep("switch_sides", "Switch sides and get into position."));
        }

        holdIndex += 1;
        steps.push({
          phase: "work",
          duration: dose.holdSeconds,
          instruction: "右臂向前，左腿向后",
          audioCue: "bird_dog_right",
          prompt: "Right arm forward, left leg back. Stay steady and breathe.",
          roundLabel: `第 ${round} 轮 / 共 ${dose.repsPerSide} 轮`,
          next: round === dose.repsPerSide ? "接下来：动作完成" : "接下来：换边",
          countDown: true,
        });
        if (holdIndex < totalHolds) {
          steps.push(switchStep("switch_sides", "Switch sides and get into position."));
        }
      }
      return steps;
    },
    doseLabel(dose) {
      return `每侧 ${dose.repsPerSide} 次 · 每次 ${dose.holdSeconds} 秒`;
    },
  },
  {
    id: "static_plank",
    name: "Static Plank",
    chineseName: "平板支撑",
    purpose: "躯干前侧耐力 · 抗伸展控制",
    cue: "头、躯干和骨盆大致一线；不塌腰、不抬高臀部，正常呼吸。",
    levels: [
      { level: 1, holdSeconds: 30, sets: 3, restSeconds: 22.5 },
      { level: 2, holdSeconds: 35, sets: 3, restSeconds: 22.5 },
      { level: 3, holdSeconds: 40, sets: 3, restSeconds: 22.5 },
      { level: 4, holdSeconds: 45, sets: 3, restSeconds: 22.5 },
    ],
    maxAutoLevel: 4,
    buildSteps(dose) {
      const steps = [prepareStep("static_plank_prepare", "Static plank. Find a stable position and get ready.")];
      for (let set = 1; set <= dose.sets; set += 1) {
        steps.push({
          phase: "work",
          duration: dose.holdSeconds,
          instruction: "收紧躯干，保持身体一线",
          audioCue: set === 1 ? "static_plank_start" : `static_plank_set_${set}`,
          prompt: set === 1
            ? "Begin the plank. Brace gently, keep your body in one long line, and keep breathing."
            : `Set ${set}. Begin, and keep breathing.`,
          roundLabel: `第 ${set} 组 / 共 ${dose.sets} 组`,
          next: set === dose.sets ? "接下来：动作完成" : `接下来：休息 ${dose.restSeconds} 秒`,
          countDown: true,
        });
        if (set < dose.sets) {
          steps.push(restStep(
            dose.restSeconds,
            `static_plank_rest_${set + 1}`,
            `Rest. Breathe normally. Set ${set + 1} is next.`,
            `第 ${set} 组完成 / 共 ${dose.sets} 组`,
          ));
        }
      }
      return steps;
    },
    doseLabel(dose) {
      return `${dose.sets} 组 · 每组 ${dose.holdSeconds} 秒 · 休息 ${dose.restSeconds} 秒`;
    },
  },
  {
    id: "side_plank",
    name: "Side Plank",
    chineseName: "侧平板支撑",
    purpose: "躯干侧向稳定 · 抗侧屈控制",
    cue: "肩、骨盆和腿大致一线；骨盆不要下沉，身体不要前后旋转。",
    levels: [
      { level: 1, holdSeconds: 20, setsPerSide: 2, restSeconds: 15 },
      { level: 2, holdSeconds: 25, setsPerSide: 2, restSeconds: 15 },
      { level: 3, holdSeconds: 30, setsPerSide: 2, restSeconds: 15 },
      { level: 4, holdSeconds: 35, setsPerSide: 2, restSeconds: 15 },
    ],
    maxAutoLevel: 4,
    buildSteps(dose) {
      const steps = [prepareStep("side_plank_prepare", "Side plank. Find a stable position and get ready.")];
      const total = dose.setsPerSide * 2;
      let current = 0;
      for (let set = 1; set <= dose.setsPerSide; set += 1) {
        current += 1;
        steps.push({
          phase: "work",
          duration: dose.holdSeconds,
          instruction: "左侧支撑，抬起骨盆",
          audioCue: "side_plank_left",
          prompt: "Begin on your left side. Lift your hips, keep your body long, and breathe.",
          roundLabel: `第 ${set} 轮左侧 / 共 ${dose.setsPerSide} 轮`,
          next: `接下来：休息 ${dose.restSeconds} 秒后换边`,
          countDown: true,
        });
        steps.push(restStep(
          dose.restSeconds,
          "side_plank_rest_right",
          "Rest and breathe. Your right side is next.",
          `已完成 ${current} / ${total} 组`,
        ));

        current += 1;
        steps.push({
          phase: "work",
          duration: dose.holdSeconds,
          instruction: "右侧支撑，抬起骨盆",
          audioCue: "side_plank_right",
          prompt: "Begin on your right side. Lift your hips, keep your body long, and breathe.",
          roundLabel: `第 ${set} 轮右侧 / 共 ${dose.setsPerSide} 轮`,
          next: current === total ? "接下来：动作完成" : `接下来：休息 ${dose.restSeconds} 秒`,
          countDown: true,
        });
        if (current < total) {
          steps.push(restStep(
            dose.restSeconds,
            "side_plank_rest_left",
            "Rest and breathe. Your left side is next.",
            `已完成 ${current} / ${total} 组`,
          ));
        }
      }
      return steps;
    },
    doseLabel(dose) {
      return `每侧 ${dose.setsPerSide} 组 · 每组 ${dose.holdSeconds} 秒 · 休息 ${dose.restSeconds} 秒`;
    },
  },
];

const FEEDBACK_LABELS = { good: "没问题", bad: "不舒服" };

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
};

let store = loadStore();
let workout = null;
let timerId = null;
let wakeLock = null;
let toastTimer = null;
let audioManifest = null;
let activeAudio = null;
const countdownAudio = new Audio();
countdownAudio.preload = "auto";
const audioCache = new Map();

const audioManifestPromise = loadAudioManifest();

function prepareStep(audioCue, prompt, duration = 7) {
  return {
    phase: "prepare",
    duration,
    instruction: "找到稳定位置，准备开始",
    audioCue,
    prompt,
    roundLabel: "准备姿势",
    next: "接下来：开始动作",
    countDown: false,
  };
}

function switchStep(audioCue, prompt) {
  return {
    phase: "switch",
    duration: 4,
    instruction: "换边",
    audioCue,
    prompt,
    roundLabel: "调整姿势",
    next: "接下来：保持",
    countDown: false,
  };
}

function restStep(duration, audioCue, prompt, roundLabel) {
  return {
    phase: "rest",
    duration,
    instruction: "休息并正常呼吸",
    audioCue,
    prompt,
    roundLabel,
    next: "接下来：下一组",
    countDown: duration >= 10,
  };
}

function defaultStore() {
  return {
    version: STORAGE_VERSION,
    voiceEnabled: true,
    levels: Object.fromEntries(EXERCISES.map((exercise) => [exercise.id, 1])),
    manualReviews: {},
    sessions: [],
  };
}

function loadStore() {
  const fallback = defaultStore();
  try {
    const parsed = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!parsed) return fallback;
    const sessions = Array.isArray(parsed.sessions)
      ? parsed.sessions.map((session) => ({
          id: session.id,
          timestamp: session.timestamp || session.startedAt,
          startedAt: session.startedAt || session.timestamp,
          completedAt: session.completedAt || null,
          status: session.status || ((session.records || []).length >= EXERCISES.length ? "completed" : "partial"),
          records: (session.records || []).map((record) => ({
            timestamp: record.timestamp || session.timestamp,
            exercise_id: record.exercise_id,
            level: record.level,
            prescribed_dose: record.prescribed_dose,
            completed: Boolean(record.completed),
            feedback: record.feedback === "good" || record.feedback === "bad" ? record.feedback : null,
            legacy: Boolean(record.legacy || (parsed.version !== STORAGE_VERSION && !record.feedback)),
          })),
        }))
      : [];
    return {
      ...fallback,
      voiceEnabled: parsed.voiceEnabled !== false,
      levels: { ...fallback.levels, ...(parsed.levels || {}) },
      manualReviews: { ...fallback.manualReviews, ...(parsed.manualReviews || {}) },
      sessions,
    };
  } catch (_error) {
    return fallback;
  }
}

function saveStore() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
  } catch (_error) {
    showToast("浏览器无法保存记录，请检查隐私设置");
  }
}

function getPrescription(exercise) {
  if (exercise.fixedDose) return { ...exercise.fixedDose };
  const requestedLevel = Number(store.levels[exercise.id] || 1);
  const index = Math.min(Math.max(requestedLevel, 1), exercise.levels.length) - 1;
  return { ...exercise.levels[index] };
}

function buildPlan() {
  return EXERCISES.map((exercise) => {
    const dose = getPrescription(exercise);
    const steps = exercise.buildSteps(dose);
    return {
      exercise,
      dose,
      steps,
      durationSeconds: steps.reduce((total, step) => total + step.duration, 0),
    };
  });
}

function renderHome() {
  const plan = buildPlan();
  const today = new Intl.DateTimeFormat("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "long",
  }).format(new Date());
  elements.todayLabel.textContent = today;
  elements.planDuration.textContent = String(Math.ceil(plan.reduce((sum, item) => sum + item.durationSeconds, 0) / 60));
  elements.planList.replaceChildren(
    ...plan.map(({ exercise, dose }, index) => {
      const item = document.createElement("li");
      item.className = "plan-item";

      const number = document.createElement("span");
      number.className = "plan-item__number";
      number.textContent = String(index + 1).padStart(2, "0");

      const copy = document.createElement("div");
      const name = document.createElement("span");
      name.className = "plan-item__name";
      name.textContent = `${exercise.name} · ${exercise.chineseName}`;
      const doseText = document.createElement("span");
      doseText.className = "plan-item__dose";
      doseText.textContent = exercise.doseLabel(dose);
      copy.append(name, doseText);

      const level = document.createElement("span");
      level.className = "level-chip";
      if (store.manualReviews[exercise.id]) {
        level.textContent = "需评估";
        level.dataset.review = "true";
      } else if (exercise.automaticProgression === false) {
        level.textContent = "固定";
      } else {
        level.textContent = `LV.${dose.level}`;
      }

      item.append(number, copy, level);
      return item;
    }),
  );

  const latest = store.sessions[0];
  if (latest) {
    const date = formatSessionDate(latest.timestamp);
    const completedRecords = (latest.records || []).filter((record) => record.completed && record.feedback);
    const goodCount = completedRecords.filter((record) => record.feedback === "good").length;
    const badCount = completedRecords.filter((record) => record.feedback === "bad").length;
    elements.lastSessionNote.textContent = `上次训练：${date} · ${goodCount} 个没问题${badCount ? ` · ${badCount} 个不舒服` : ""}`;
  } else {
    elements.lastSessionNote.textContent = "第一次训练会从基础剂量开始。记录只保存在这台设备。";
  }
  updateVoiceButton();
}

function startWorkout() {
  const plan = buildPlan();
  workout = {
    id: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`,
    startedAt: new Date().toISOString(),
    plan,
    exerciseIndex: 0,
    stepIndex: 0,
    paused: false,
    remainingMs: 0,
    deadline: 0,
    nextCountdownSecond: 3,
    records: [],
    adjustments: [],
    results: plan.map((item) => ({
      exerciseId: item.exercise.id,
      level: item.dose.level,
      prescribedDose: { ...item.dose },
      completedWorkSteps: 0,
      totalWorkSteps: item.steps.filter((step) => step.phase === "work").length,
      skippedWorkSteps: 0,
      completed: false,
    })),
  };
  showView("workout");
  requestWakeLock();
  enterCurrentStep();
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
  if (!workout) return;
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

function completeCurrentExercise() {
  if (!workout) return;
  const result = workout.results[workout.exerciseIndex];
  result.completed = result.completedWorkSteps === result.totalWorkSteps && result.skippedWorkSteps === 0;
  clearTimer();
  speak("exercise_complete", "Exercise complete. How did that feel?", { interrupt: true });
  vibrate([80, 70, 120]);
  renderExerciseFeedback();
  showView("feedback");
}

function skipExercise() {
  if (!workout) return;
  clearTimer();
  const item = workout.plan[workout.exerciseIndex];
  const result = workout.results[workout.exerciseIndex];
  const remainingWork = item.steps.slice(workout.stepIndex).filter((step) => step.phase === "work").length;
  result.skippedWorkSteps += remainingWork;
  result.completed = false;
  const record = createRecord(result, null);
  workout.records.push(record);
  workout.adjustments.push(applyProgression(record));
  persistWorkoutSession("in_progress");
  speak("exercise_skipped", "Exercise skipped. Get ready for the next movement.");
  window.setTimeout(advanceToNextExercise, 1200);
}

function togglePause() {
  if (!workout) return;
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

function renderExerciseFeedback() {
  if (!workout) return;
  const item = workout.plan[workout.exerciseIndex];
  elements.feedbackProgress.textContent = `EXERCISE ${workout.exerciseIndex + 1} OF ${workout.plan.length}`;
  elements.feedbackExercise.textContent = `${item.exercise.name} · ${item.exercise.chineseName}`;
  for (const button of elements.feedbackForm.querySelectorAll("button")) button.disabled = false;
}

function saveFeedback(event) {
  event.preventDefault();
  if (!workout) return;
  const feedback = event.submitter?.value;
  if (feedback !== "good" && feedback !== "bad") return;
  for (const button of elements.feedbackForm.querySelectorAll("button")) button.disabled = true;

  const result = workout.results[workout.exerciseIndex];
  const record = createRecord(result, feedback);
  workout.records.push(record);
  workout.adjustments.push(applyProgression(record));
  persistWorkoutSession("in_progress");
  speak(
    feedback === "good" ? "feedback_good" : "feedback_bad",
    feedback === "good" ? "Got it. That felt good." : "Got it. We'll keep that in mind.",
  );
  window.setTimeout(advanceToNextExercise, 1200);
}

function createRecord(result, feedback) {
  return {
    timestamp: new Date().toISOString(),
    exercise_id: result.exerciseId,
    level: result.level,
    prescribed_dose: result.prescribedDose,
    completed: result.completed,
    feedback,
  };
}

function advanceToNextExercise() {
  if (!workout) return;
  workout.exerciseIndex += 1;
  workout.stepIndex = 0;
  if (workout.exerciseIndex >= workout.plan.length) {
    finishWorkout();
    return;
  }
  showView("workout");
  window.setTimeout(() => enterCurrentStep(), 550);
}

function persistWorkoutSession(status) {
  if (!workout) return;
  const session = {
    id: workout.id,
    timestamp: workout.startedAt,
    startedAt: workout.startedAt,
    completedAt: status === "completed" ? new Date().toISOString() : null,
    status,
    records: workout.records.map((record) => ({ ...record })),
  };
  store.sessions = [session, ...store.sessions.filter((item) => item.id !== workout.id)].slice(0, 180);
  saveStore();
}

function finishWorkout() {
  if (!workout) return;
  clearTimer();
  releaseWakeLock();
  persistWorkoutSession("completed");
  stopVoice();
  speak("workout_complete", "Today's session is complete. Nice work.", { interrupt: false });
  renderSummary(workout.adjustments);
  workout = null;
  showView("summary");
}

function applyProgression(record) {
  const exercise = EXERCISES.find((item) => item.id === record.exercise_id);
  if (!exercise) return { name: record.exercise_id, status: "保持", kind: "hold", detail: "没有剂量变化" };
  if (!record.completed) {
    return { name: exercise.name, status: "未计入", kind: "hold", detail: "本次未完整完成，不改变等级或连续记录" };
  }
  if (exercise.automaticProgression === false) {
    return { name: exercise.name, status: "固定剂量", kind: "hold", detail: "活动度动作不自动增加" };
  }

  const currentLevel = Number(store.levels[exercise.id] || 1);
  const priorRecords = store.sessions
    .flatMap((session) => session.records || [])
    .filter((item) => item.exercise_id === exercise.id && item.completed && FEEDBACK_LABELS[item.feedback]);
  const evidence = [record, ...priorRecords];
  const goodStreak = countConsecutiveFeedback(evidence, "good", currentLevel);
  const badStreak = countConsecutiveFeedback(evidence, "bad", currentLevel);

  if (record.feedback === "bad") store.manualReviews[exercise.id] = false;

  if (record.feedback === "bad" && badStreak >= 2) {
    const nextLevel = Math.max(1, currentLevel - 1);
    store.levels[exercise.id] = nextLevel;
    store.manualReviews[exercise.id] = false;
    return {
      name: exercise.name,
      status: nextLevel < currentLevel ? `降至 LV.${nextLevel}` : "保持 LV.1",
      kind: nextLevel < currentLevel ? "down" : "hold",
      detail: nextLevel < currentLevel ? "连续 2 次不舒服，下一次降低一级" : "连续 2 次不舒服，但已在最低等级",
    };
  }

  if (record.feedback === "good" && goodStreak >= 3 && currentLevel < exercise.levels.length) {
    const nextLevel = currentLevel + 1;
    store.levels[exercise.id] = nextLevel;
    store.manualReviews[exercise.id] = false;
    return { name: exercise.name, status: `升至 LV.${nextLevel}`, kind: "up", detail: "连续 3 次没问题，下一次提高一级" };
  }

  if (record.feedback === "good" && goodStreak >= 3 && currentLevel >= exercise.levels.length) {
    if (exercise.manualReviewAtMax) {
      store.manualReviews[exercise.id] = true;
      return {
        name: exercise.name,
        status: "需要人工评估",
        kind: "review",
        detail: "LV.6 已连续 3 次没问题；保持当前剂量，请手动评估台面高度、脚距或阻力",
      };
    }
    return { name: exercise.name, status: `保持 LV.${currentLevel}`, kind: "hold", detail: "已达到自动调整上限" };
  }

  const streak = record.feedback === "good" ? goodStreak : badStreak;
  const target = record.feedback === "good" ? 3 : 2;
  return {
    name: exercise.name,
    status: `保持 LV.${currentLevel}`,
    kind: "hold",
    detail: `连续「${FEEDBACK_LABELS[record.feedback]}」${streak} / ${target} 次`,
  };
}

function countConsecutiveFeedback(records, feedback, level) {
  let count = 0;
  for (const item of records) {
    if (Number(item.level) !== level || item.feedback !== feedback) break;
    count += 1;
  }
  return count;
}

function renderSummary(adjustments) {
  if (adjustments.some((item) => item.kind === "review")) {
    elements.summaryCopy.textContent = "有动作已达到自动进阶上限。系统会保持当前剂量，并在首页标记需要人工评估。";
  } else if (adjustments.some((item) => item.kind === "up")) {
    elements.summaryCopy.textContent = "你的反馈已满足进阶条件。下面的动作会在下一次训练中增加一级，且不会超过预设上限。";
  } else if (adjustments.some((item) => item.kind === "down")) {
    elements.summaryCopy.textContent = "连续两次不舒服的动作已降低一级。下一次会自动使用更轻的剂量。";
  } else {
    elements.summaryCopy.textContent = "每个动作的反馈都已保存。还没有满足升降级条件的动作，下一次维持当前计划。";
  }

  elements.adjustmentList.replaceChildren(
    ...adjustments.map((item) => {
      const row = document.createElement("article");
      row.className = "adjustment-item";
      const copy = document.createElement("div");
      const title = document.createElement("strong");
      title.textContent = item.name;
      const detail = document.createElement("small");
      detail.textContent = item.detail;
      copy.append(title, detail);
      const result = document.createElement("span");
      result.className = `adjustment-result adjustment-result--${item.kind}`;
      result.textContent = item.status;
      row.append(copy, result);
      return row;
    }),
  );
}

function renderHistory() {
  if (!store.sessions.length) {
    elements.historyContent.innerHTML = '<div class="history-empty">还没有训练记录。完成第一次训练后会显示在这里。</div>';
    return;
  }

  elements.historyContent.replaceChildren(
    ...store.sessions.map((session) => {
      const article = document.createElement("article");
      article.className = "history-session";
      const top = document.createElement("div");
      top.className = "history-session__top";
      const date = document.createElement("strong");
      date.textContent = formatSessionDate(session.timestamp);
      const time = document.createElement("span");
      time.textContent = new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit" }).format(new Date(session.timestamp));
      top.append(date, time);

      const feedback = document.createElement("p");
      feedback.className = "history-session__feedback";
      const completedRecords = (session.records || []).filter((record) => record.completed && record.feedback);
      const goodCount = completedRecords.filter((record) => record.feedback === "good").length;
      const badCount = completedRecords.filter((record) => record.feedback === "bad").length;
      const sessionLabel = session.status === "completed" ? "已完成" : "未完成";
      feedback.textContent = `${sessionLabel} · ${goodCount} 个没问题 · ${badCount} 个不舒服`;

      const list = document.createElement("ul");
      list.className = "history-session__exercises";
      for (const record of session.records || []) {
        const exercise = EXERCISES.find((item) => item.id === record.exercise_id);
        const item = document.createElement("li");
        item.dataset.completed = String(Boolean(record.completed));
        item.dataset.feedback = record.feedback || "skipped";
        const feedbackLabel = record.feedback ? FEEDBACK_LABELS[record.feedback] : record.legacy ? "旧规则记录" : "已跳过";
        item.textContent = `${exercise?.name || record.exercise_id} ${exercise?.automaticProgression === false ? "" : `LV.${record.level}`} · ${feedbackLabel}`.trim();
        list.appendChild(item);
      }
      article.append(top, feedback, list);
      return article;
    }),
  );
}

function showView(name) {
  for (const [viewName, view] of Object.entries(views)) view.hidden = viewName !== name;
  document.body.dataset.view = name;
  window.scrollTo({ top: 0, behavior: "instant" });
}

function toggleVoice() {
  store.voiceEnabled = !store.voiceEnabled;
  saveStore();
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
    const firstCue = buildPlan()[0]?.steps[0]?.audioCue;
    if (firstCue) preloadCue(firstCue);
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
    wakeLock = await navigator.wakeLock.request("screen");
    wakeLock.addEventListener("release", () => { wakeLock = null; });
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

elements.startButton.addEventListener("click", startWorkout);
elements.voiceToggle.addEventListener("click", toggleVoice);
elements.pauseButton.addEventListener("click", togglePause);
elements.skipStepButton.addEventListener("click", () => finishStep({ skipped: true }));
elements.skipExerciseButton.addEventListener("click", skipExercise);
elements.exitWorkout.addEventListener("click", () => {
  if (workout && !workout.paused) togglePause();
  elements.confirmDialog.showModal();
});
elements.confirmCancel.addEventListener("click", () => {
  elements.confirmDialog.close();
  if (workout?.paused) togglePause();
});
elements.confirmExit.addEventListener("click", () => {
  clearTimer();
  releaseWakeLock();
  stopVoice();
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
  renderHistory();
  elements.historyDialog.showModal();
});
elements.closeHistory.addEventListener("click", () => elements.historyDialog.close());
elements.historyDialog.addEventListener("click", (event) => {
  if (event.target === elements.historyDialog) elements.historyDialog.close();
});
elements.resetDataButton.addEventListener("click", () => {
  if (!window.confirm("确定清除全部训练记录和自动调整等级吗？此操作无法撤销。")) return;
  store = defaultStore();
  saveStore();
  renderHistory();
  renderHome();
  showToast("训练数据已清除");
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible" && workout && !wakeLock) requestWakeLock();
});
window.addEventListener("beforeunload", () => {
  clearTimer();
  releaseWakeLock();
});

showView("home");
renderHome();
audioManifestPromise.catch(() => {});
