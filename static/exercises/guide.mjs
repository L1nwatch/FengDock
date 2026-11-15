function roundFor(set, dose, rep, side) {
  return [`第 ${set}/${dose.sets} 组`, side?.label, `第 ${rep}/${dose.reps} 次`].filter(Boolean).join(" · ");
}

function transition(exercise, side, roundLabel) {
  return {
    phase: "switch", duration: exercise.restSeconds ?? 6, roundLabel,
    instruction: `${exercise.directional ? "换向" : "换边"} · ${side.label}`,
    audioCue: side.restCue ?? side.audioCue,
    tone: "switch", countDown: true,
  };
}

function workSteps(exercise, dose, side, roundLabel, startingSide) {
  const action = (instruction, duration, options) => ({
    phase: "work", duration, instruction: side ? `${side.label} · ${instruction}` : instruction,
    roundLabel, ...options,
  });

  if (exercise.phases) {
    return exercise.phases.map(({ instruction, audioCue, tone }, index) => {
      const end = Math.round((index + 1) * dose.tempoSeconds / exercise.phases.length);
      const start = Math.round(index * dose.tempoSeconds / exercise.phases.length);
      return action(instruction, end - start, { audioCue, tone, countDown: true });
    });
  }

  const sideCue = startingSide ? side?.audioCue : null;
  if (exercise.liftCue) {
    const lift = exercise.liftSeconds ?? Math.ceil(dose.tempoSeconds / 2);
    const steps = [
      action(exercise.movement.split("，")[0], lift, { audioCue: sideCue || exercise.liftCue }),
    ];
    if (dose.holdSeconds) {
      steps.push(action(`保持 ${dose.holdSeconds} 秒`, dose.holdSeconds, { countDown: dose.holdSeconds >= 4 }));
    }
    steps.push(action("缓慢回位", dose.tempoSeconds - lift, { audioCue: "lower" }));
    return steps;
  }

  return [action(exercise.movement, dose.tempoSeconds, {
    audioCue: sideCue, tone: sideCue ? null : "start", countDown: exercise.countDownReps,
  })];
}

export function buildSteps(exercise, dose) {
  const steps = [{
    phase: "prepare", duration: dose.trial ? 12 : 8,
    instruction: dose.trial ? `先用轻阻力试做，每侧 ${dose.reps} 次` : "找到稳定位置，准备开始",
    audioCue: `${exercise.id}_${dose.trial ? "trial" : "prepare"}`,
    roundLabel: "准备姿势", tone: "ready", countDown: true,
  }];
  for (let set = 1; set <= dose.sets; set += 1) {
    const sides = exercise.sides ?? [null];
    const order = exercise.alternate
      ? Array.from({ length: dose.reps }, () => sides).flat()
      : sides.flatMap((side) => Array(dose.reps).fill(side));
    let previousSide;
    for (const [index, side] of order.entries()) {
      const rep = (exercise.alternate ? Math.floor(index / sides.length) : index % dose.reps) + 1;
      const roundLabel = roundFor(set, dose, rep, side);
      const startingSide = index === 0 || side !== previousSide;
      if (index > 0 && startingSide && !exercise.alternate) steps.push(transition(exercise, side, roundLabel));
      steps.push(...workSteps(exercise, dose, side, roundLabel, startingSide));
      previousSide = side;
    }
    if (set < dose.sets) {
      steps.push({
        phase: "rest", duration: exercise.restSeconds ?? 20, instruction: "休息并正常呼吸",
        audioCue: sides[0]?.restCue ?? "rest",
        roundLabel: `第 ${set}/${dose.sets} 组完成`, tone: "rest", countDown: true,
      });
    }
  }
  return steps.map((step, index) => ({
    ...step, next: steps[index + 1] ? `接下来 · ${steps[index + 1].instruction}` : "接下来 · 提交反馈",
  }));
}
