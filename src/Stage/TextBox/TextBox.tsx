import { compileSentence } from '@/Core/parser/compileSentence';
export { compileSentence, splitChars } from '@/Core/parser/compileSentence';
export type { EnhancedNode } from '@/Core/parser/compileSentence';
import { useEffect, useMemo, useState } from 'react';
import { addDialoguePinyin } from './dialoguePinyin';
import { useSelector } from 'react-redux';
import { RootState } from '@/store/store';
import { useFontFamily } from '@/hooks/useFontFamily';
import { useTextAnimationDuration, useTextDelay } from '@/hooks/useTextOptions';
import { getTextSize } from '@/UI/getTextSize';
import { match } from '@/Core/util/match';
import { textSize } from '@/store/userDataInterface';
import IMSSTextbox from '@/Stage/TextBox/IMSSTextbox';
import { SCREEN_CONSTANTS } from '@/Core/util/constants';
import { useStageState } from '@/hooks/useStageState';

const userAgent = navigator.userAgent;
const isFirefox = /firefox/i.test(userAgent);
const isSafari = /^((?!chrome|android).)*safari/i.test(userAgent);


export const TextBox = () => {
  const stageState = useStageState();
  const guiState = useSelector((state: RootState) => state.GUI);
  const userDataState = useSelector((state: RootState) => state.userData);
  const textDelay = useTextDelay(userDataState.optionData.textSpeed);
  const textDuration = useTextAnimationDuration(userDataState.optionData.textSpeed);
  let size = getTextSize(userDataState.optionData.textSize) + '%';
  const font = useFontFamily();
  const isRead = stageState.isRead;
  const isText = stageState.showText !== '' || stageState.showName !== '';
  let textSizeState = userDataState.optionData.textSize;
  if (isText && stageState.showTextSize !== -1) {
    size = getTextSize(stageState.showTextSize) + '%';
    textSizeState = stageState.showTextSize;
  }
  const MaxTextLine = Number(userDataState.globalGameVar.Max_line); // congfig定义字体行数
  const lineLimit = Number.isNaN(MaxTextLine)
    ? match(textSizeState)
        .with(textSize.small, () => 3)
        .with(textSize.medium, () => 2)
        .with(textSize.large, () => 2)
        .default(() => 2)
    : MaxTextLine;
  // 拆字
  const textArray = useMemo(() => {
    const nodes = compileSentence(stageState.showText, lineLimit);
    return userDataState.optionData.dialoguePinyin ? addDialoguePinyin(nodes) : nodes;
  }, [stageState.showText, lineLimit, userDataState.optionData.dialoguePinyin]);
  const isHasName = stageState.showName !== '';
  const showName = compileSentence(stageState.showName, lineLimit);
  const currentConcatDialogPrev = stageState.currentConcatDialogPrev;
  const currentDialogKey = stageState.currentDialogKey;
  const miniAvatar = stageState.miniAvatar;
  const textboxOpacity = userDataState.optionData.textboxOpacity;
  const Textbox = IMSSTextbox;
  const fontOptimization = guiState.fontOptimization;

  const [isShowStroke, setIsShowStroke] = useState(true);

  useEffect(() => {
    if (!fontOptimization) {
      setIsShowStroke(true);
      return;
    }

    const handleResize = () => {
      const targetHeight = SCREEN_CONSTANTS.height;
      const targetWidth = SCREEN_CONSTANTS.width;

      const h = window.innerHeight; // 窗口高度
      const w = window.innerWidth; // 窗口宽度
      const zoomH = h / targetHeight; // 以窗口高度为基准的变换比
      const zoomW = w / targetWidth; // 以窗口宽度为基准的变换比
      const zoomH2 = w / targetHeight; // 竖屏时以窗口高度为基础的变换比
      const zoomW2 = h / targetWidth; // 竖屏时以窗口宽度为基础的变换比
      [zoomH, zoomW, zoomH2, zoomW2].forEach((e) => {
        if (e <= 0.2) {
          setIsShowStroke(false);
        } else {
          setIsShowStroke(true);
        }
      });
    };
    window.addEventListener('resize', handleResize);
    handleResize();
    return () => {
      window.removeEventListener('resize', handleResize);
    };
  }, [fontOptimization]);

  return (
    <Textbox
      textArray={textArray}
      isRead={isRead}
      isText={isText}
      textDelay={textDelay}
      showName={showName}
      isHasName={isHasName}
      currentConcatDialogPrev={currentConcatDialogPrev}
      fontSize={size}
      currentDialogKey={currentDialogKey}
      isSafari={isSafari}
      isFirefox={isFirefox}
      miniAvatar={miniAvatar}
      textDuration={textDuration}
      font={font}
      textSizeState={textSizeState}
      lineLimit={lineLimit}
      isUseStroke={isShowStroke}
      textboxOpacity={textboxOpacity}
    />
  );
};
