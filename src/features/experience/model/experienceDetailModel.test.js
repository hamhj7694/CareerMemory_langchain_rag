import { describe, expect, it } from 'vitest';
import {
  editableCustomBlocks,
  metricsToText,
  periodToText,
  sanitizeExperienceContentBlocks,
  textToMetrics,
  textToPeriod,
} from './experienceDetailModel.js';

describe('experience detail view model', () => {
  it('hides internal lineage properties and stale empty system cards', () => {
    const blocks = sanitizeExperienceContentBlocks([
      { type: 'summary', origin: 'system_projection', data: { title: '요약', text: '' } },
      { type: 'properties', origin: 'system_projection', data: { title: '추가 정보', value: { experience_unit_v2: { unit_id: 'UNIT-1' } } } },
      { type: 'paragraph', origin: 'user', data: { title: '메모', text: '보존할 내용' } },
    ]);

    expect(blocks).toHaveLength(1);
    expect(editableCustomBlocks(blocks)[0].data.text).toBe('보존할 내용');
  });

  it('maps period and metric editor text without exposing structured JSON', () => {
    expect(periodToText({ start: '2026-01', end: '2026-06' })).toBe('2026-01 ~ 2026-06');
    expect(textToPeriod('2026년 상반기')).toEqual({ raw_text: '2026년 상반기' });
    expect(metricsToText([{ raw_expression: '호출 7회에서 2회' }])).toBe('호출 7회에서 2회');
    expect(textToMetrics('호출 7회에서 2회')).toEqual([{ raw_expression: '호출 7회에서 2회', normalization_status: 'unresolved' }]);
  });
});
