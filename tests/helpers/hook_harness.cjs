function hookHarness() {
  const slots = [];
  let index = 0;
  let effects = [];
  const changed = (before, after) => !before || !after || before.length !== after.length || before.some((value, i) => !Object.is(value, after[i]));
  const react = {
    useState(initial) {
      const key = index++;
      slots[key] ??= { value: typeof initial === 'function' ? initial() : initial };
      return [slots[key].value, value => { slots[key].value = typeof value === 'function' ? value(slots[key].value) : value; }];
    },
    useRef(initial) { const key = index++; return slots[key] ??= { current: initial }; },
    useCallback(callback, deps) {
      const key = index++;
      if (!slots[key] || changed(slots[key].deps, deps)) slots[key] = { deps, callback };
      return slots[key].callback;
    },
    useEffect(callback, deps) {
      const key = index++;
      if (!slots[key] || changed(slots[key].deps, deps)) effects.push(() => {
        slots[key]?.cleanup?.(); slots[key] = { deps, cleanup: callback() };
      });
    },
  };
  return {
    react,
    render(callback) { index = 0; effects = []; const result = callback(); effects.forEach(effect => effect()); return result; },
    unmount() { slots.forEach(slot => slot?.cleanup?.()); },
  };
}
module.exports = { hookHarness };
