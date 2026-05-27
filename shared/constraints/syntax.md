# WebGAL Script Syntax Constraints

Hard rules for WebGAL `.txt` scene files. Every sub-agent that generates or validates scripts MUST respect these.

---

## Complete Syntax Reference

```
; comment line
// inline comment

; Variables (use 0/1 for flags, never true/false)
setVar:name=value;
setVar:name=value -when=condition;

; Branching choices (option text : label to jump to)
choose:Option A:labelA|Option B:labelB|Option C:labelC;

; Choices with conditional visibility
choose:(cond)->VisibleOption:labelA|[cond]->DisabledOption:labelB;

; Labels and jumps
label:labelName;
jumpLabel:labelName;
jumpLabel:labelName -when=condition;

; Scene management
callScene:filename.txt;       ; calls sub-scene, RETURNS to next line after
intro:line1|line2|line3;       ; title screen subtitle
end;                            ; ends the game (main scene only)

; Dialogue and narration
SpeakerName:dialogue text;
:narration text (no speaker);

; Music and visuals
bgm:file.mp3 -volume=80;
changeBg:image.webp -next;
changeFigure:image.webp -left/-right -next;
miniAvatar:avatar.webp;          ; dialogue avatar
```

---

## Critical Rules

### 1. `callScene` returns to the caller

After the sub-scene finishes, execution continues from the line after `callScene`. Always put a `;` (empty comment) on the next line as a guard against fall-through.

```
callScene:some_scene.txt;
;
; safe — the ; stops fall-through into whatever follows
```

### 2. `end;` only works in the main scene

Sub-scenes must reach end-of-file naturally. The return chain unwinds back to the main scene's `end;`. Never put `end;` in a sub-scene.

### 3. `jumpLabel` is file-local only

You cannot jump to a label in another file. Use `callScene` for cross-file transitions. Every `jumpLabel:XXX` must have a matching `label:XXX` in the SAME file.

### 4. Variables are global

Set in one scene, readable in all scenes. Initialize all variables to 0 in `start.txt`.

### 5. Use 0/1 for boolean flags, never `true`/`false`

```
; CORRECT
setVar:flag=1;
jumpLabel:somewhere -when=flag==1;

; WRONG
setVar:flag=true;
jumpLabel:somewhere -when=flag==true;
```

### 6. `-when=` only supports single conditions

No AND/OR in condition expressions. Use accumulator variables to simulate AND logic.

```
; WRONG
jumpLabel:ending -when=respect>=50 AND empathy>=50;

; CORRECT
setVar:bestCheck=0;
setVar:bestCheck=bestCheck+1 -when=respect>=50;
setVar:bestCheck=bestCheck+1 -when=empathy>=50;
jumpLabel:ending -when=bestCheck>=2;
```

### 7. After every `callScene`, guard with `;` or `jumpLabel`

```
callScene:sub.txt;
;                        ← guard against fall-through

callScene:sub2.txt;
jumpLabel:next_section;  ← or explicit jump
```

### 8. `choose` target labels must exist in the same file

Every `choose:Option:labelName` must have a corresponding `label:labelName` in that file.

---

## Dialogue Avatar Rules (MANDATORY)

Every character that has a sprite AND a mini avatar MUST display their avatar before their first line of dialogue, and again after any scene where the speaker changes.

```
miniAvatar:miniavatar_<name>.webp;
CharacterName:dialogue text...
```

Rules:
- Each named speaker's **first line in a scene** must be preceded by `miniAvatar:`
- When the speaker changes, insert `miniAvatar:` for the new speaker
- Narration (`:text`) and unnamed speakers can skip the avatar
- After a `changeFigure` call, re-issue `miniAvatar:` for the next speaker
- Avatar file names must match: `miniavatar_<name>.webp` corresponds to `figure_<name>.webp`

Example — correct flow:
```
changeBg:bg_home_gate.webp -next;
changeFigure:figure_wife.webp -right -next;

miniAvatar:miniavatar_wife.webp;
妻子:渊明……？真的是你！

miniAvatar:miniavatar_tao_yuanming.webp;
陶渊明:我……我辞官了。

:没有人说话。只有冷月静静地映在院中。
```

---

## Common Pitfalls & Fixes

| Symptom | Root Cause | Fix |
|---------|-----------|-----|
| Game loops back to start after ending | `callScene` return falls into a `jumpLabel:game_start` | Add `;` after every `callScene` line to stop fall-through |
| Ending shows wrong scene | Cross-file `jumpLabel` silently fails | Use `callScene` instead of cross-file `jumpLabel` |
| Conditional jump never fires | `=true` as string doesn't match `==1` check | Use `setVar:flag=1;` and `-when=flag==1` |
| Game crashes on branching choice | `choose` target label missing in file | Verify all choose labels exist in the same file |
| AND condition always false | `-when=a>=50 AND b>=50` not supported | Use accumulator: `setVar:chk=chk+1 -when=a>=50;` × N |
| Sub-scene ends game prematurely | `end;` in a sub-scene terminates everything | Remove `end;` from sub-scenes, let them return naturally |
| Variable not updating | `setVar:x=y -when=cond` fails if cond uses strings | Use numeric comparisons in `-when=` conditions |
