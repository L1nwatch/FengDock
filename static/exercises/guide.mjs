export function buildSteps(exercise, dose) {
  const steps = [];
  steps.push({
    phase: "prepare", duration: dose.trial ? 12 : 8,
    instruction: dose.trial ? `先用轻阻力试做，每侧 ${dose.reps} 次` : "找到稳定位置，准备开始",
    prompt: `${exercise.name}. ${exercise.setup}${dose.trial ? ` Try only ${dose.reps} reps on each side.` : ""}`,
    roundLabel: "准备姿势",
  });
  for (let set = 1; set <= dose.sets; set += 1) {
    const sides = exercise.sides ?? [null];
    const order = exercise.alternate
      ? Array.from({ length: dose.reps }, () => sides).flat()
      : sides.flatMap((side) => Array(dose.reps).fill(side));
    let previousSide;
    for (const [index, side] of order.entries()) {
      const rep = (exercise.alternate ? Math.floor(index / sides.length) : index % dose.reps) + 1;
      const roundLabel = [`第 ${set}/${dose.sets} 组`, side?.label, `第 ${rep}/${dose.reps} 次`]
        .filter(Boolean).join(" · ");
      if (side && side !== previousSide && index > 0 && !exercise.alternate) {
        steps.push({ phase: "switch", duration: exercise.restSeconds ?? 4,
          instruction: `换到${side.label}`, prompt: `Rest. ${side.prompt} next.`, roundLabel });
      }
      previousSide = side;
      const firstDuration = Math.ceil(dose.tempoSeconds / 2);
      if (dose.holdSeconds) {
        steps.push({
          phase: "work", duration: firstDuration, instruction: exercise.movement.split("，")[0],
          prompt: side ? `${side.prompt}. Lift.` : "Lift.", roundLabel,
        }, {
          phase: "work", duration: dose.holdSeconds, instruction: `保持 ${dose.holdSeconds} 秒`,
          prompt: "Hold.", roundLabel, countDown: dose.holdSeconds >= 4,
        }, {
          phase: "work", duration: dose.tempoSeconds - firstDuration, instruction: "缓慢回位",
          prompt: "Lower.", roundLabel,
        });
      } else if (exercise.liftSeconds) {
        steps.push({
          phase: "work", duration: exercise.liftSeconds, instruction: `${side.label} · 弯举`,
          prompt: `${side.prompt}. Curl.`, roundLabel,
        }, {
          phase: "work", duration: dose.tempoSeconds - exercise.liftSeconds, instruction: "缓慢放下",
          prompt: "Lower.", roundLabel,
        });
      } else {
        steps.push({
          phase: "work", duration: dose.tempoSeconds,
          instruction: [side?.label, exercise.movement].filter(Boolean).join(" · "),
          prompt: [side?.prompt, exercise.prompt].filter(Boolean).join(". "), roundLabel,
        });
      }
    }
    if (set < dose.sets) {
      steps.push({
        phase: "rest", duration: exercise.restSeconds ?? 20, instruction: "休息并正常呼吸",
        prompt: "Rest. Another set is next.", roundLabel: `第 ${set}/${dose.sets} 组完成`, countDown: true,
      });
    }
  }
  return steps.map((step, index) => ({
    ...step, next: steps[index + 1] ? `接下来 · ${steps[index + 1].instruction}` : "接下来 · 提交反馈",
  }));
}
