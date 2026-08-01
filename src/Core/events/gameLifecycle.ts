export const NARRATIVEOS_GAME_ENDED_EVENT = 'narrativeos:game-ended';

export function notifyNarrativeOSGameEnded() {
  window.dispatchEvent(new Event(NARRATIVEOS_GAME_ENDED_EVENT));
}
