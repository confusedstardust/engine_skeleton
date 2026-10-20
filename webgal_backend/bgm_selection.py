"""Deterministic mood matching for the public music catalog."""

MOODS = {
    'ordinary': {'日常', '平静', '中性'}, 'peace': {'平静', '宁静'},
    'slow': {'低沉', '悲伤'}, 'soft': {'柔和', '温柔'},
    'tense': {'紧张', '悬疑'}, 'warm': {'温暖', '治愈'},
    'happy': {'欢快', '快乐'}, 'normal': {'平静', '日常', '中性'},
    'sad': {'悲伤', '低沉'}, 'bad': {'负面', '紧张'},
    'terrible': {'绝望', '恐怖'},
}


def select_bgm(catalog, mood, usage):
    expected = MOODS.get(mood, {mood}) | {mood}
    matched = [item for item in catalog if expected.intersection(item.get('moods') or [])]
    neutral = [item for item in catalog if {'平静', '日常', '中性', 'ordinary', 'normal'}.intersection(item.get('moods') or [])]
    candidates = matched or neutral or catalog
    if not candidates:
        return None, True
    selected = min(candidates, key=lambda item: (usage.get(item['filename'], 0), item['filename']))
    return selected, not bool(matched)
