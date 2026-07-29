import { describe, expect, it } from 'vitest';
import { aiRecommendedExperienceIds } from './jobMatchViewModel.js';

describe('aiRecommendedExperienceIds', () => {
  it('keeps AI suggestions separate from user-created links', () => {
    const ids = aiRecommendedExperienceIds({
      experiences: [
        { experienceId: 'EXP-AI', linkSource: 'ai' },
        { experienceId: 'EXP-USER', linkSource: 'user' },
      ],
    });

    expect([...ids]).toEqual(['EXP-AI']);
  });

  it('supports legacy responses as AI suggestions', () => {
    const ids = aiRecommendedExperienceIds({
      experiences: [{ experienceId: 'EXP-LEGACY' }],
    });

    expect([...ids]).toEqual(['EXP-LEGACY']);
  });
});
