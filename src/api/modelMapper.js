function transformKeys(value, transform) {
  if (Array.isArray(value)) return value.map((item) => transformKeys(item, transform));
  if (!value || typeof value !== 'object' || value instanceof File || value instanceof Blob || value instanceof FormData) return value;
  return Object.fromEntries(Object.entries(value).map(([key, item]) => [transform(key), transformKeys(item, transform)]));
}

const camelize = (key) => key.replace(/_([a-z])/g, (_, letter) => letter.toUpperCase());
const snakeize = (key) => key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`);

export const toScreenModel = (wireValue) => transformKeys(wireValue, camelize);
export const toWireModel = (screenValue) => transformKeys(screenValue, snakeize);
