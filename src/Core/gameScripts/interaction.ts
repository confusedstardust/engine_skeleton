import { interactionManager } from '@/Core/Modules/interaction/InteractionManager';
import type { IPerform } from '@/Core/Modules/perform/performInterface';
import type { ISentence } from '@/Core/controller/scene/sceneInterface';
import { getStringArgByKey } from '@/Core/util/getSentenceArg';
import { WebGAL } from '@/Core/WebGAL';

export const interaction = (sentence: ISentence): IPerform => {
  const nodeId = sentence.content.trim(); const configPath = getStringArgByKey(sentence, 'config');
  // getStringArgByKey returns null (rather than undefined) when an argument is absent.
  // Treating null as present made every valid interaction command fail before activation.
  if (!nodeId || !configPath || getStringArgByKey(sentence, 'next') !== null) {
    throw new Error('interaction 指令需要稳定节点 ID 和 -config，且不允许 -next。');
  }
  const instanceName = `interaction#${nodeId}`;
  return { performName: instanceName, duration: 0, autoRemove: false, isHoldOn: false,
    startFunction: () => { void interactionManager.activate(nodeId, configPath, WebGAL.sceneManager.sceneData.currentScene.sceneUrl, WebGAL.sceneManager.sceneData.currentSentenceId - 1); },
    // Completion removes the Perform through the manager; cancellation never grants a result.
    stopFunction: () => { if (interactionManager.getViewModel().lifecycle !== 'completed') interactionManager.cancel(); },
    blockingNext: () => true, blockingAuto: () => true, blockingStateCalculation: () => true };
};
