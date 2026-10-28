const list = (value) => Array.isArray(value) ? value.filter(Boolean) : [];

export const INTERNAL_EXPERIENCE_EXTENSION_KEYS = new Set(['experience_unit_v2']);

const hasValue = (value) => value != null && value !== ''
  && (!Array.isArray(value) || value.length > 0)
  && (typeof value !== 'object' || Array.isArray(value) || Object.keys(value).length > 0);

export function sanitizeExperienceContentBlocks(blocks = []) {
  return list(blocks).flatMap((source) => {
    const block = structuredClone(source);
    const type = block.type || block.block_type;
    const data = block.data || {};
    if (type === 'properties') {
      data.value = Object.fromEntries(Object.entries(data.value || {}).filter(([key]) => (
        !INTERNAL_EXPERIENCE_EXTENSION_KEYS.has(key) && !key.startsWith('_')
      )));
      block.data = data;
    }
    const visibleValues = Object.entries(data).filter(([key]) => !['title', 'tone'].includes(key));
    if (block.origin === 'system_projection' && !visibleValues.some(([, value]) => hasValue(value))) return [];
    return [block];
  });
}

export function editableCustomBlocks(blocks = []) {
  return sanitizeExperienceContentBlocks(blocks).filter((block) => block.origin !== 'system_projection');
}

export function periodToText(period) {
  if (typeof period === 'string') return period.trim();
  if (!period || typeof period !== 'object') return '';
  if (period.raw_text) return String(period.raw_text);
  return [period.start, period.end].filter(Boolean).join(' ~ ');
}

export function textToPeriod(value) {
  const raw = String(value || '').trim();
  return raw ? { raw_text: raw } : {};
}

export function metricsToText(metrics = []) {
  return list(metrics).map((metric) => {
    if (typeof metric === 'string') return metric;
    return metric.raw_expression || metric.raw_text || metric.quote
      || [metric.metric_name, metric.value, metric.unit].filter((part) => part != null && part !== '').join(' ');
  }).filter(Boolean).join('\n');
}

export function textToMetrics(value) {
  return String(value || '').split(/\r?\n/).map((item) => item.trim()).filter(Boolean).map((rawExpression) => ({
    raw_expression: rawExpression,
    normalization_status: 'unresolved',
  }));
}
