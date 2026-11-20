import type { Step } from '@/api/types';

/**
 * Plain-language description of one step, for the polite live region
 * (spec 10.4: announce each stage in words, not every event).
 */
export function describeStep(step: Step, bubbleName: (id: string) => string | null, position?: number): string {
  const name = step.bubble ? bubbleName(step.bubble) : null;
  const where = name ? `${name} bubble` : 'bubbles';
  let text: string;
  switch (step.kind) {
    case 'route':
      text = 'Understanding your question';
      break;
    case 'seed':
      text = 'Choosing starting points';
      break;
    case 'retrieve':
      text = `Searching ${where}`;
      break;
    case 'score':
      text = `Scoring evidence from ${where}`;
      break;
    case 'subagent':
      text = `Working on ${where}`;
      break;
    case 'join':
      text = 'Joining global entities';
      break;
    case 'merge':
      text = 'Merging results';
      break;
    case 'answer':
      text = 'Writing answer';
      break;
    default:
      text = 'Working';
  }
  if (step.status === 'error') {
    text = step.kind === 'subagent' && name ? `${name} bubble could not answer` : `${text}: could not finish`;
  }
  return position !== undefined ? `${text}, step ${position}` : text;
}

/** The step that is currently running, else the last one that started. */
export function currentStep(steps: readonly Step[]): Step | undefined {
  const running = [...steps].reverse().find((s) => s.status === 'running');
  return running ?? steps[steps.length - 1];
}
