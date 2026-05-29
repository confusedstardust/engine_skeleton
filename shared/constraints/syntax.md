
## 2. 最重要的硬性规则

1. 每条语句单独占一行。
2. 每条语句必须使用英文分号 `;` 结尾。
3. 命令中的冒号 `:`、分号 `;`、竖线 `|`、参数横线 `-` 必须使用英文字符。
4. 旁白使用空角色名，格式为 `:旁白文本;`。
5. 角色对话格式为 `角色名:台词;`。
6. 变量必须先初始化，再使用。
7. `choose` 中引用的目标文件或 label 必须真实存在。
8. 分支结束后必须明确跳转到下一个场景、结局或汇合 label。
9. `changeScene` 后舞台状态不会自动清空，必要时要手动清理背景、立绘、BGM。
10. 不要输出 Markdown 代码块包裹脚本内容，除非用户明确要求写文档。

## 3. 基础语法

### 3.2 关闭资源 `none`

`none` 用于关闭当前资源或效果。

```webgal
changeBg:none;
changeFigure:none;
bgm:none -enter=3000;
miniAvatar:none;
```

### 3.3 立即继续 `-next`

在演出语句后加 `-next`，表示执行完当前语句后立刻继续下一句。

```webgal
changeBg:bg_school.jpg -next;
changeFigure:hero.png -left -next;
主角:终于到了。;
```

常用于连续切背景、切立绘、播放音效等。

## 4. 对话与旁白

### 4.1 角色对话

格式：

```webgal
角色名:台词;
```

示例：

```webgal
方鸿渐:我以为回来以后，一切都会变得容易。;
苏文纨:你总是这样，把犹豫说成体面。;
```

### 4.2 旁白

格式：

```webgal
:旁白文本;
```

示例：

```webgal
:黄昏压在街角，像一封没有寄出的信。;
```

### 4.3 连续对话

如果连续几句属于同一个角色，可以省略后续行的角色名。但为了让 LLM 输出更稳定，推荐每句都写角色名。

不推荐：

```webgal
雪之下雪乃:你到得真早;
对不起，等很久了吗？;
```

推荐：

```webgal
雪之下雪乃:你到得真早;
雪之下雪乃:对不起，等很久了吗？;
```

### 4.4 黑屏文字 `intro`

用于黑屏独白、章节引子、心理段落。多行内容用 `|` 分隔。

```webgal
intro:记忆不需要合适的剧本，|一旦说出口，|就都成了笑话。;
```

保持黑屏文字停留：

```webgal
intro:第一行|第二行|第三行 -hold;
```

### 4.5 结束游戏 `end`

```webgal
end;
```

结局场景末尾建议写 `end;`。

## 5. 背景与立绘

### 5.1 切换背景 `changeBg`

```webgal
changeBg:bg_classroom.jpg;
```

关闭背景：

```webgal
changeBg:none;
```

连续演出：

```webgal
changeBg:bg_classroom.jpg -next;
```

背景图片通常放在：

```text
public/game/background/
```

### 5.2 切换立绘 `changeFigure`

默认中间位置：

```webgal
changeFigure:hero.png;
```

左侧：

```webgal
changeFigure:alice.png -left;
```

右侧：

```webgal
changeFigure:bob.png -right;
```

关闭立绘：

```webgal
changeFigure:none;
changeFigure:none -left;
changeFigure:none -right;
```

立绘图片通常放在：

```text
public/game/figure/
```

### 5.3 小头像 `miniAvatar`

显示小头像：

```webgal
miniAvatar:minipic_test.png;
```

关闭小头像：

```webgal
miniAvatar:none;
```

### 5.4 立绘变换 `-transform`

可以在 `changeFigure` 后添加 JSON 变换。

```webgal
changeFigure:hero.png -transform={"alpha":1,"position":{"x":0,"y":500},"scale":{"x":1,"y":1},"rotation":0} -next;
```

常用字段：

- `alpha`：透明度，0 到 1。
- `position`：位置偏移，例如 `{"x":0,"y":500}`。
- `scale`：缩放，例如 `{"x":1,"y":1}`。
- `rotation`：旋转，单位为弧度。
- `blur`：模糊。
- `brightness`、`contrast`、`saturation`、`gamma`：画面滤镜参数。

### 5.5 修改已有对象 `setTransform`

```webgal
setTransform:{"position":{"x":100,"y":0}} -target=fig-center -duration=0;
```

常见 target：

```text
fig-left
fig-center
fig-right
bg-main
```


## 7. 场景与分支

### 7.1 场景跳转 `changeScene`

切换到另一个场景文件。

```webgal
changeScene:chapter_02.txt;
```

示例：

```webgal
主角:我们该离开这里了。;
changeScene:ending_default.txt;
```

`changeScene` 适合章节推进、进入分支文件、进入结局。

### 7.2 分支选择 `choose`

基础格式：

```webgal
choose:选项文本A:目标A|选项文本B:目标B;
```

跳到场景文件：

```webgal
choose:坦白自己的不安:branch_honest.txt|维持表面的体面:branch_polite.txt|转移话题:branch_avoid.txt;
```

跳到当前文件中的 label：

```webgal
choose:留下:stay|离开:leave;
```

生成 `choose` 时必须满足：

- 每个选项文本要体现不同立场，不要只是换个说法。
- 每个选项目标必须存在。
- 每个选项对应的分支内容必须不同。
- 每个分支至少影响一个变量，或最终导向不同的剧情后果。

### 7.3 条件选项

条件展示与条件可点击格式：

```webgal
choose:(showConditionVar>1)[enableConditionVar>2]->叫住她:chapter_02.txt|回家:chapter_03.txt;
```

含义：

- `(showConditionVar>1)`：满足时才显示选项。
- `[enableConditionVar>2]`：满足时才允许点击选项。
- `->` 后面是正常的 `选项文本:目标`。

如果没有必要，不建议 LLM 主动生成复杂条件选项。

### 7.4 标签 `label`

创建当前文件内的跳转点：

```webgal
label:stay;
```

跳转到标签：

```webgal
jumpLabel:stay;
```

同文件分支示例：

```webgal
主角:现在该怎么办？;
choose:留下:stay|离开:leave;

label:stay;
setVar:courage=courage+1;
主角:我决定再等等。;
jumpLabel:after_choice;

label:leave;
setVar:distance=distance+1;
主角:我不能再停留了。;
jumpLabel:after_choice;

label:after_choice;
主角:无论如何，夜色已经沉了下来。;
```

重要：同一个文件里的脚本会向下顺序执行。每个 label 分支结束后，必须用 `jumpLabel` 跳到汇合点，否则会继续执行下面的其他分支。

## 8. 变量

### 8.1 设置变量 `setVar`

格式：

```webgal
setVar:变量名=值;
```

初始化：

```webgal
setVar:trust=0;
setVar:distance=0;
setVar:courage=0;
```

修改：

```webgal
setVar:trust=trust+1;
setVar:distance=distance+1;
setVar:courage=courage-1;
```

布尔值：

```webgal
setVar:has_key=false;
setVar:met_heroine=true;
```

字符串：

```webgal
setVar:hero_name=方鸿渐;
```

### 8.2 条件执行 `-when`

任意语句后都可以添加 `-when=条件`。条件满足时才执行该语句。

```webgal
changeScene:ending_best.txt -when=trust>=2;
changeScene:ending_failure.txt -when=distance>=2;
changeScene:ending_default.txt;
```

常见比较：

```text
a>1
a>=1
a<1
a<=1
a==1
a!=1
```
### 8.3 推荐结局判断写法

在最终场景或汇合点使用多行 `changeScene` 判断结局：

```webgal
changeScene:ending_best.txt -when=trust>=2;
changeScene:ending_failure.txt -when=distance>=2;
changeScene:ending_default.txt;
```

最后一行不加 `-when`，作为默认结局兜底。

