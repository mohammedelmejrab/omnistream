import { describe, expect, it } from 'vitest';
import { AGENTIC_STEPS, NORMAL_STEPS } from './fixtures/stored-runs';
import { announceStep, dedupeAnnouncement, failureLabel, startLabel } from './announce';

describe('startLabel', () => {
  it('names the bubble being searched, in plain words', () => {
    expect(startLabel(AGENTIC_STEPS[2]!)).toBe('Searching Energy bubble');
  });

  it('stays silent for scoring steps', () => {
    expect(startLabel(NORMAL_STEPS[3]!)).toBeNull();
  });
});

describe('announceStep', () => {
  it('adds the position, and the total only when it is known', () => {
    expect(announceStep(AGENTIC_STEPS[2]!, 3, 7)).toBe('Searching Energy bubble, step 3 of 7');
    expect(announceStep(AGENTIC_STEPS[2]!, 3, null)).toBe('Searching Energy bubble, step 3');
  });
});

describe('dedupeAnnouncement', () => {
  it('reads a bubble once when retrieve and subagent steps follow each other', () => {
    const first = dedupeAnnouncement(null, 'Searching Energy bubble, step 3');
    expect(first.announce).toBe('Searching Energy bubble, step 3');
    const second = dedupeAnnouncement(first.last, 'Searching Energy bubble, step 4');
    expect(second.announce).toBeNull();
  });

  it('announces a different bubble', () => {
    const next = dedupeAnnouncement('Searching Energy bubble', 'Searching Policy bubble, step 5');
    expect(next.announce).toBe('Searching Policy bubble, step 5');
  });
});

describe('failureLabel', () => {
  it('uses the "could not answer" wording for a bubble', () => {
    expect(failureLabel(AGENTIC_STEPS[3]!)).toBe('Policy bubble could not answer');
  });
});
