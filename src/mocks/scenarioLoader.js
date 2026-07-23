import manifest from '../../mocks/manifest.json';
import success from '../../mocks/scenarios/success.json';
import empty from '../../mocks/scenarios/empty.json';
import partialSuccess from '../../mocks/scenarios/partial-success.json';
import error from '../../mocks/scenarios/error.json';

const scenarios = Object.freeze({ success, empty, 'partial-success': partialSuccess, error });
const scenarioAliases = Object.freeze({ partial_success: 'partial-success', partial: 'partial-success' });

function compilePath(path) {
  const escaped = path.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`^${escaped.replace(/\\\{[^}]+\\\}/g, '[^/]+')}$`);
}

export const mockRoutes = Object.freeze(manifest.routes.map((route) => ({
  ...route,
  method: route.method.toUpperCase(),
  pattern: compilePath(route.path),
})));

export const availableMockScenarios = Object.freeze(Object.keys(scenarios));

export function getMockScenario(requestedScenario) {
  const rawName = requestedScenario || import.meta.env.VITE_MOCK_SCENARIO || manifest.default_scenario;
  const name = scenarioAliases[rawName] || rawName;
  if (!scenarios[name]) {
    throw new Error(`Unknown mock scenario "${rawName}". Choose: ${availableMockScenarios.join(', ')}`);
  }
  return scenarios[name];
}
