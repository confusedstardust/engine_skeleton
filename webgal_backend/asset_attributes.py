import json
from pathlib import Path
from fastapi import HTTPException

GROUPS=json.loads(Path(__file__).with_name('asset_attributes.json').read_text(encoding='utf-8'))

def validate_attributes(kind, raw):
    try:
        data=json.loads(raw)
        if not isinstance(data,dict):raise ValueError()
        schema={g['key']:g for g in GROUPS.get(kind,[])}
        result={}
        for key,values in data.items():
            if key not in schema or not isinstance(values,list) or len(values)>(12 if schema[key]['multiple'] else 1):raise ValueError()
            if any(not isinstance(v,str) or not v.strip() or len(v)>40 for v in values):raise ValueError()
            if values:result[key]=list(dict.fromkeys(v.strip() for v in values))
        return result
    except (ValueError,TypeError):
        raise HTTPException(422,'素材属性格式无效，请按属性组填写')

CATEGORY_IDS={'古代人物': 'ancient', '近现代人物': 'modern', '动物角色': 'animal', '幻想人物': 'fantasy', '庭院': 'courtyard', '河岸与水域': 'waterside', '园林': 'garden', '乡村与田园': 'rural', '厅堂': 'hall', '书房': 'study', '卧室': 'bedroom', '山地与山路': 'mountain', '街道': 'street', '起居空间': 'living_room', '农田': 'farmland', '建筑门口': 'gate', '废墟': 'ruins', '森林与竹林': 'forest', '沙漠': 'desert', '牢房': 'prison', '公署与办公室': 'office', '酒馆': 'tavern', '琴房': 'music_room', '走廊': 'corridor', '现代室内': 'modern_interior', '船舶甲板': 'ship', '教室': 'school', '亭阁水榭': 'pavilion', '静物特写': 'still_life', '人物与事件': 'character_event', '意象场景': 'symbolic', '城市远景': 'cityscape'}
