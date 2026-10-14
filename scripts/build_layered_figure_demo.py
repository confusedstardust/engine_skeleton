"""Create reusable expression demo scenes without changing the game's start scene."""
from __future__ import annotations

import argparse
from pathlib import Path


PRESETS = {
    'demo': ('综合演示', '每四秒切换表情，呼吸、眨眼、视线、头部和头发动作同时运行。'),
    'normal': ('自然', '自动眨眼与轻微视线移动。'),
    'happy': ('开心', '微笑、眯眼和轻微歪头。'),
    'joy': ('大笑', '笑眼和张嘴。'),
    'sad': ('难过', '眉毛、嘴角与头部动作组合。'),
    'angry': ('生气', '压眉、收眼和嘴角变化。'),
    'surprised': ('惊讶', '抬眉、睁大眼睛和张嘴。'),
    'curious': ('疑惑', '一侧抬眉、歪头和不对称眼神。'),
    'sleepy': ('困倦', '半闭眼和头部轻动。'),
    'wink': ('眨眼示意', '单眼闭合、微笑和歪头。'),
    'talk': ('说话演示', '循环嘴型，尚未连接真实语音。'),
}
PAIRS = {'happyjoy': ('开心与大笑', ['happy', 'joy']),
         'sadangry': ('难过与生气', ['sad', 'angry']),
         'surprisecurious': ('惊讶与疑惑', ['surprised', 'curious']),
         'sleepywink': ('困倦与眨眼', ['sleepy', 'wink']),
         'normaltalk': ('自然与说话', ['normal', 'talk'])}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_dir', type=Path, help='The job public/game directory')
    parser.add_argument('figure', help='Path under game/figure to a .layered.json manifest')
    parser.add_argument('--background', default='bg_courtyard_night.webp')
    parser.add_argument('--return-scene', default='start_before_psd_preview.txt')
    args = parser.parse_args()
    for value in (args.figure, args.background, args.return_scene):
        if any(char in value for char in '\n\r;|'):
            parser.error('Scene asset names must not contain command delimiters.')
    root = args.game_dir/'scene'
    if not (args.game_dir/'figure'/args.figure).is_file() or not (root/args.return_scene).is_file():
        parser.error('The figure manifest and return scene must already exist.')
    generated = [root/f'psd_face_{key}.txt' for key in PRESETS] + [root/f'psd_menu_{key}.txt' for key in PAIRS] + [root/'psd_expression_menu.txt']
    if any(path.exists() for path in generated):
        parser.error('Demo scenes already exist. Use a fresh game directory to preserve existing scenes.')
    main_menu = 'choose:综合演示:psd_face_demo.txt|' + '|'.join(f'{label}:psd_menu_{key}.txt' for key, (label, _) in PAIRS.items()) + ';\n'
    for key, (label, description) in PRESETS.items():
        query = 'expression=normal&talk=true' if key == 'talk' else f'expression={key}'
        text = 'changeFigure:none -left -next;\nchangeFigure:none -right -next;\n'
        text += f'changeBg:{args.background} -next;\nchangeFigure:{args.figure}?motion=combo&{query} -next;\n'
        text += f'表情预览:{label}：{description} 点击切换。;\n' + main_menu
        (root/f'psd_face_{key}.txt').write_text(text, encoding='utf-8')
    (root/'psd_expression_menu.txt').write_text(main_menu, encoding='utf-8')
    for key, (_, modes) in PAIRS.items():
        text = 'choose:' + '|'.join(f'{PRESETS[mode][0]}:psd_face_{mode}.txt' for mode in modes)
        text += f'|返回表情列表:psd_expression_menu.txt|进入原剧情:{args.return_scene};\n'
        (root/f'psd_menu_{key}.txt').write_text(text, encoding='utf-8')
    print('Created 17 scenes. To enter the demo, use changeScene:psd_face_demo.txt;')


if __name__ == '__main__':
    main()
