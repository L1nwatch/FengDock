// Dose bounds, increments and recovery settings are application policy.
export const GROUPS = {
  back: { name: "Back Exercise", positiveTarget: 7, minIntervalHours: 18, recoveryCheckHours: 18 },
  shoulder: { name: "Shoulder Rehab", positiveTarget: 10, minIntervalHours: 18, recoveryCheckHours: 18 },
  muscle: { name: "Muscle Building", positiveTarget: 3, minIntervalHours: 48, recoveryCheckHours: 18 },
};

export const ARCHIVED_EXERCISES = {
  cat_cow: "Cat-Cow · 跪姿猫牛式",
  static_plank: "Static Plank · 平板支撑",
  side_plank: "Side Plank · 侧平板支撑",
  bird_dog: "Bird-Dog · 鸟狗式",
  high_incline_push_up: "High Incline Push-Up · 高位斜板俯卧撑",
};

const daily = { sets: 1, holdSeconds: 0, daysPerWeek: 7, resistanceLevel: 0, tempoSeconds: 4 };
const increaseReps = (max) => ({ field: "reps", max, rate: 0.1 });
const increase = (field, max) => ({ field, max, step: 1 });
const sides = [
  { label: "左侧", prompt: "Left side", restCue: "side_plank_rest_left" },
  { label: "右侧", prompt: "Right side", restCue: "side_plank_rest_right" },
];

export const EXERCISES = [
  {
    id: "seated_cat_cow", group: "back", name: "Seated Cat-Cow", chineseName: "坐姿猫牛式",
    purpose: "腰背活动", cue: "坐稳，双脚踩地。在舒适范围内缓慢拱背，再轻抬胸口。",
    setup: "Sit with both feet on the floor.",
    phases: [
      { instruction: "猫式 · 缓慢拱背", prompt: "Cat. Slowly round your back.", audioCue: "cat_cow_cat", tone: "cat" },
      { instruction: "牛式 · 轻抬胸口", prompt: "Cow. Gently lift your chest.", audioCue: "cat_cow_arch", tone: "cow" },
    ],
    initial: { ...daily, reps: 8, tempoSeconds: 12 }, minimum: { reps: 5 },
    progression: [increaseReps(14)],
  },
  {
    id: "glute_bridge", group: "back", name: "Glute Bridge", chineseName: "臀桥",
    purpose: "臀肌与骨盆稳定", cue: "仰卧屈膝，脚踩地。臀部抬起时保持腰背舒适，正常呼吸。",
    setup: "Lie on your back, knees bent and feet flat.",
    movement: "抬起臀部，再缓慢放下", prompt: "Lift your hips. Lower slowly.",
    initial: { ...daily, reps: 10, holdSeconds: 2 }, minimum: { reps: 6, holdSeconds: 0 },
    progression: [increaseReps(15), increase("holdSeconds", 5), increase("sets", 2)],
  },
  {
    id: "supine_march", group: "back", name: "Supine March", chineseName: "仰卧交替抬腿",
    purpose: "腹部核心稳定", cue: "仰卧屈膝，左右交替轻抬一脚。保持骨盆稳定和正常呼吸。",
    setup: "Lie on your back with knees bent. Alternate feet.",
    movement: "轻抬一脚，再受控放下", prompt: "Lift and lower.",
    sides, alternate: true,
    initial: { ...daily, reps: 8, holdSeconds: 2 }, minimum: { reps: 5, holdSeconds: 0 },
    progression: [increaseReps(12), increase("holdSeconds", 5), increase("sets", 2)],
  },
  {
    id: "shoulder_rolls", group: "shoulder", name: "Shoulder Rolls", chineseName: "肩部绕环",
    purpose: "肩部活动与放松", cue: "放松双臂，在舒适的小幅度内轻轻绕环。",
    setup: "Relax your arms by your sides.",
    movement: "轻轻绕环", prompt: "Roll gently.", directional: true,
    sides: [{ label: "向前", prompt: "Forward" }, { label: "向后", prompt: "Backward" }],
    initial: { ...daily, reps: 5 }, minimum: { reps: 3 },
    progression: [increase("reps", 10)],
  },
  {
    id: "serratus_punch", group: "shoulder", name: "Supine Serratus Punch", chineseName: "仰卧肩胛前伸",
    purpose: "前锯肌与肩胛控制", cue: "空手仰卧，手轻轻向上够，再让肩胛回到起始位置。",
    setup: "Lie on your back. Reach toward the ceiling with an empty hand.",
    movement: "手向上够，再受控回位", prompt: "Reach and release.",
    sides,
    initial: { ...daily, reps: 8 }, minimum: { reps: 5 },
    progression: [increaseReps(14), increase("holdSeconds", 2)],
  },
  {
    id: "wall_slide", group: "shoulder", name: "Wall Slide", chineseName: "靠墙上滑",
    purpose: "肩胛与肩关节协调", cue: "在无痛、可控的幅度内缓慢上滑，再慢慢回位。",
    setup: "Face the wall. Keep the movement comfortable.",
    movement: "手沿墙上滑，再缓慢回位", prompt: "Slide up and down slowly.",
    sides,
    initial: { ...daily, reps: 8, tempoSeconds: 5 }, minimum: { reps: 5 },
    progression: [increaseReps(14)],
  },
  {
    id: "band_curl", group: "muscle", name: "Seated Resistance Band Biceps Curl", chineseName: "坐姿弹力带弯举",
    purpose: "肱二头肌增肌", cue: "坐稳，用轻阻力，肘部靠近身体。每组结束保留约 2–3 次余力。",
    setup: "Sit upright. Keep your elbow near your side.",
    movement: "弯举，再缓慢放下", prompt: "Curl and lower.",
    sides,
    liftSeconds: 2,
    resistanceNote: "8 字形弹力带 · 轻阻力",
    initial: { ...daily, sets: 2, reps: 8, daysPerWeek: 2, weeklySets: 4, resistanceLevel: 1 },
    minimum: { reps: 8, weeklySets: 4 },
    repeatAfterTrialDays: 2,
    trial: { sets: 1, reps: 3 },
    progression: [
      increaseReps(14),
      { ...increase("weeklySets", 10), before: { field: "daysPerWeek", threshold: 3, max: 6 } },
      increase("daysPerWeek", 3),
    ],
    fallback: increase("tempoSeconds", 6),
    decrease: ["tempoSeconds", "reps", "weeklySets", "daysPerWeek"],
    restSeconds: 60,
  },
];
