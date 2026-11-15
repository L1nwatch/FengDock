function roundFor(set, dose, rep, side) {
  return [`第 ${set}/${dose.sets} 组`, side?.label, `第 ${rep}/${dose.reps} 次`].filter(Boolean).join(" · ");
}

function transition(exercise, side, roundLabel) {
  const duration = exercise.restSeconds ?? (exercise.alternate ? 4 : 6);
  return {
    phase: "switch", duration, roundLabel,
    instruction: `${exercise.directional ? "换向" : "换边"} · ${side.label}`,
    audioCue: exercise.alternate ? "switch_sides" : side.restCue,
    prompt: exercise.alternate ? "Switch sides." : `${side.prompt} next.`,
    tone: "switch", countDown: duration >= 6,
  };
}

function workSteps(exercise, dose, side, roundLabel, tone) {
  const movement = (instruction) => side ? `${side.label} · ${instruction}` : instruction;
  const action = (instruction, duration, prompt, options) => ({
    phase: "work", duration, instruction: movement(instruction), prompt, roundLabel, ...options,
  });

  if (exercise.phases) {
    return exercise.phases.map(({ instruction, prompt, audioCue, tone }, index) => {
      const end = Math.round((index + 1) * dose.tempoSeconds / exercise.phases.length);
      const start = Math.round(index * dose.tempoSeconds / exercise.phases.length);
      return action(instruction, end - start, prompt, { audioCue, tone, countDown: true });
    });
  }

  if (dose.holdSeconds) {
    const lift = Math.ceil(dose.tempoSeconds / 2);
    return [
      action(exercise.movement.split("，")[0], lift, side ? `${side.prompt}. Lift.` : "Lift.", { tone }),
      action(`保持 ${dose.holdSeconds} 秒`, dose.holdSeconds, "Hold.", { countDown: dose.holdSeconds >= 4 }),
      action("缓慢回位", dose.tempoSeconds - lift, "Lower."),
    ];
  }

  if (exercise.liftSeconds) {
    return [
      action("弯举", exercise.liftSeconds, tone ? `${side.prompt}. Curl.` : "Curl.", { tone }),
      action("缓慢放下", dose.tempoSeconds - exercise.liftSeconds, "Lower."),
    ];
  }

  const prompt = side && tone ? `${side.prompt}. ${exercise.prompt}` : exercise.prompt;
  return [action(exercise.movement, dose.tempoSeconds, prompt, { tone })];
}

export function buildSteps(exercise, dose) {
  const steps = [{
    phase: "prepare", duration: dose.trial ? 12 : 8,
    instruction: dose.trial ? `先用轻阻力试做，每侧 ${dose.reps} 次` : "找到稳定位置，准备开始",
    prompt: `${exercise.name}. ${exercise.setup}${dose.trial ? ` Try only ${dose.reps} reps on each side.` : ""}`,
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
      if (index > 0 && startingSide) steps.push(transition(exercise, side, roundLabel));
      steps.push(...workSteps(exercise, dose, side, roundLabel, startingSide ? "start" : null));
      previousSide = side;
    }
    if (set < dose.sets) {
      steps.push({
        phase: "rest", duration: exercise.restSeconds ?? 20, instruction: "休息并正常呼吸",
        audioCue: sides[0]?.restCue,
        prompt: sides[0] ? `Rest. ${sides[0].prompt} next.` : "Rest. Another set is next.",
        roundLabel: `第 ${set}/${dose.sets} 组完成`, tone: "rest", countDown: true,
      });
    }
  }
  return steps.map((step, index) => ({
    ...step, next: steps[index + 1] ? `接下来 · ${steps[index + 1].instruction}` : "接下来 · 提交反馈",
  }));
}
