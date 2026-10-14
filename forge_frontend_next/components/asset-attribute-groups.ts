export type AttributeGroup = {key:string;label:string;multiple:boolean;options:string[]};
export const attributeGroups: Record<string,AttributeGroup[]> = {
  "BACKGROUND": [
    {
      "key": "place",
      "label": "场所",
      "multiple": false,
      "options": [
        "庭院",
        "书房",
        "厅堂",
        "卧室",
        "街道",
        "山林",
        "河岸",
        "乡村",
        "农田",
        "教室",
        "牢房",
        "废墟",
        "船舶甲板",
        "城市远景"
      ]
    },
    {
      "key": "style",
      "label": "画面风格",
      "multiple": false,
      "options": [
        "水墨",
        "写实",
        "动漫",
        "油画",
        "像素"
      ]
    },
    {
      "key": "era",
      "label": "时代",
      "multiple": false,
      "options": [
        "古代",
        "近现代",
        "当代",
        "幻想"
      ]
    },
    {
      "key": "time",
      "label": "时间",
      "multiple": false,
      "options": [
        "清晨",
        "白天",
        "黄昏",
        "夜晚"
      ]
    },
    {
      "key": "weather",
      "label": "天气",
      "multiple": true,
      "options": [
        "晴天",
        "阴天",
        "雨",
        "雪",
        "雾"
      ]
    },
    {
      "key": "elements",
      "label": "画面元素",
      "multiple": true,
      "options": [
        "石头",
        "树木",
        "桥",
        "船",
        "人物",
        "建筑",
        "花草"
      ]
    }
  ],
  "FIGURE": [
    {
      "key": "era",
      "label": "时代",
      "multiple": false,
      "options": [
        "古代",
        "近现代",
        "当代",
        "幻想"
      ]
    },
    {
      "key": "style",
      "label": "画面风格",
      "multiple": false,
      "options": [
        "水墨",
        "写实",
        "动漫",
        "油画",
        "像素"
      ]
    },
    {
      "key": "gender",
      "label": "性别",
      "multiple": false,
      "options": [
        "男性",
        "女性"
      ]
    },
    {
      "key": "age",
      "label": "年龄",
      "multiple": false,
      "options": [
        "儿童",
        "少年",
        "青年",
        "中年",
        "老年"
      ]
    },
    {
      "key": "identity",
      "label": "身份",
      "multiple": true,
      "options": [
        "学生",
        "教师",
        "书生",
        "武将",
        "官员",
        "平民"
      ]
    },
    {
      "key": "clothing",
      "label": "服饰",
      "multiple": true,
      "options": [
        "长袍",
        "盔甲",
        "校服",
        "西装",
        "休闲服"
      ]
    },
    {
      "key": "expression",
      "label": "表情",
      "multiple": true,
      "options": [
        "平静",
        "开心",
        "悲伤",
        "愤怒",
        "惊讶"
      ]
    },
    {
      "key": "pose",
      "label": "姿态",
      "multiple": true,
      "options": [
        "站立",
        "坐姿",
        "正面",
        "侧面",
        "背面"
      ]
    }
  ],
  "BGM": [
    {
      "key": "usage",
      "label": "使用场景",
      "multiple": true,
      "options": [
        "开场",
        "对话",
        "探索",
        "行动与冲突",
        "结局"
      ]
    },
    {
      "key": "mood",
      "label": "情绪",
      "multiple": true,
      "options": [
        "平静",
        "欢快",
        "悲伤",
        "紧张",
        "悬疑",
        "温暖"
      ]
    },
    {
      "key": "tempo",
      "label": "节奏",
      "multiple": false,
      "options": [
        "舒缓",
        "中速",
        "快速"
      ]
    },
    {
      "key": "style",
      "label": "音乐风格",
      "multiple": true,
      "options": [
        "古风",
        "古典",
        "流行",
        "电子",
        "管弦乐"
      ]
    },
    {
      "key": "instruments",
      "label": "乐器",
      "multiple": true,
      "options": [
        "钢琴",
        "弦乐",
        "吉他",
        "古筝",
        "笛子",
        "鼓"
      ]
    }
  ]
};
