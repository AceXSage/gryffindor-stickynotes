# Gryffindor · 能分页的 Windows 桌面便签

## 需求设计

我要的是一张随手叫得出来的便签：一屏里能切几页、写完自己存、断网也能用。市面上的要么得登录同步，要么根本不支持多页。最后写成这个样子：PyQt5、单文件源码、无边框毛玻璃、贴屏幕边能收起来、全程不联网。

---

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 系统 | Windows 10（1803 及以后）/ Windows 11。毛玻璃用的 Windows Acrylic，热键用的 RegisterHotKey，都是 Windows 专用，macOS 和 Linux 跑不了 |
| Python | 3.8 及以上都能装上 PyQt5（5.15.11 的 wheel 是 cp38-abi3，标着 `requires-python >=3.8`）。我自己用的是 3.11.15。3.9、3.10 已经停止维护，装 3.11 或 3.12 更省事。3.14 我试过能装、能 import，但没在上面长期用过 |
| 依赖 | 只有 PyQt5，装完占 150 MB 左右 |
| 磁盘 | 源码 104 KB；笔记和图片按用得多少长 |
| 权限 | 普通用户就行。设置写 HKCU，不碰系统目录，不需要管理员 |

设置写在注册表 `HKCU\Software\GryffindorSoft\Gryffindor`，这是 `QSettings("GryffindorSoft", "Gryffindor")` 落下来的地址（Gryffindor.py:1387，应用名取的是 `APP_TITLE`，Gryffindor.py:100）。里面这几个值：

| 键 | 是什么 |
|---|---|
| `page_names` | 页名列表 |
| `current_page` | 停在第几页，从 0 数 |
| `hotkey` | 全局热键，默认 `Ctrl+G` |
| `bg_alpha` | 底板透明度，30–215，默认 88 |
| `font_size` | 正文字号 |
| `pos` / `size` | 窗口位置和大小 |
| `auto_start` | 开机自启开关（只对打包后的 exe 有效，见第 5 节） |

---

## 2. 怎么跑起来

**首选：双击 `run.cmd`。** 它按顺序找解释器——目录里的 `.venv\Scripts\python.exe`、`py -3`、`python`——挑第一个能 `import PyQt5` 的来跑。找到了就起程序，找不到会告诉你缺什么。

**注意**：Python 没装、或者 PyQt5 没装这两种情况，run.cmd 打完提示就结束了，双击时窗口一闪而过，你什么也看不到。要看清提示就开一个 cmd，`cd` 到目录，敲 `run.cmd`。

想自己建虚拟环境跑（改代码、或者不想污染系统 Python）：

```bat
git clone https://github.com/AceXSage/gryffindor-stickynotes.git
cd gryffindor-stickynotes

python -m venv .venv
.venv\Scripts\activate
pip install PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple

python Gryffindor.py
```

建好之后 `run.cmd` 会自动优先用它。没有 git 就下载 ZIP、解压，直接双击 `run.cmd`。

**要个 exe（目标机器不装 Python）：**

```bat
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --icon Gryffindor_icon.ico Gryffindor.py
```

`--onefile` 不能省。少了它出来的是 `dist\Gryffindor\` 一整个文件夹，不是单个 exe。加了之后产物是 `dist\Gryffindor.exe`，可以拷到别的 Win10/11 机器上直接双击。

**exe 从哪儿读写笔记**：启动时先在 exe 所在目录找 `Gryffindor_note_p1.md`，找不到就往上一层层找（最多 5 层，Gryffindor.py:111-124），都没找到才在当前目录新建。所以最好单独开一个文件夹放 exe，别扔在桌面或者下载目录里。

---

## 3. 第一次启动会有什么

程序自己建，不用手动准备：

```
Gryffindor_note_p1.md     第 I 页
Gryffindor_note_p2.md     第 II 页
images/                   拖进来的图片复制到这里，正文写相对路径
```

- 一页一个文件，文件名按下标走：`p1`、`p2`、`p3`……跟页签顺序一一对应。
- 文件内容第一行是 `<!--GRYFFINDOR_RICH_V1-->`，后面是 HTML。没有这个标记的老文件（纯 Markdown 文本）也能打开，按纯文本加载。
- 打字停手 500 ms 才写盘（Gryffindor.py:1403-1406、2481-2483），切页、关窗、退出时会再强制存一次。
- 删掉中间某页，后面的文件整体前移一位。别在资源管理器里手动改名——页签是按文件名读内容的，改完就对不上了。
- 备份就把整个文件夹拷走。换机器连 `images/` 一起搬，正文里的相对路径才不会断。
- 日志不在程序目录：`%LOCALAPPDATA%\Gryffindor\` 下，`error.log` 记被吞掉的异常，`fatal.log` 记原生崩溃。

---

## 4. 功能介绍

### 页签

| 操作 | 效果 |
|---|---|
| 页签条右边的 `+` | 新增一页。名字取当前没被占用的最小罗马数字，所以删过 `II` 再加一页还是 `II`（Gryffindor.py:1785） |
| 双击页签 或 `F2` | 改名 |
| 右键页签 | Rename / Copy Page Text / Delete；只剩一页时 Delete 是灰的 |
| 按住页签左右拖 | 换顺序，文件跟着搬，内容不会串 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 下一页 / 上一页 |
| `Del` | 删当前页，会弹确认框 |

`Del` 有个上下文：启动后、切过页、点过页签，都算“在页签上”，这时 `Del` 是删页；在正文里打过字、点过、滚过滚轮之后，`Del` 就还给正文删字符。想再删页就点一下页签。

### 编辑

- 打空格触发转换：`# ` 到 `###### ` 变标题；`- ` 或 `* ` 变无序列表；`1. ` 或 `1) ` 变有序列表；`> ` 变引用；`--- `、`*** `、`___ ` 变分割线。
- 回车时把上一行的行内标记渲染掉：`**粗体**`、`*斜体*`、`~~删除线~~`、`==高亮==`、行内代码（反引号包起来的那段）。
- `Ctrl+B` 粗体、`Ctrl+I` 斜体、`Ctrl+Shift+H` 高亮。没选中文字就作用在光标所在的那个词上。
- `Ctrl+滚轮` 或者标题栏的 `+` / `-` 调字号，范围 8–72 pt，标题按层级倍数跟着变（1 级 1.8 倍、2 级 1.5、3 级 1.3、4 级 1.15、5 级 1.05、6 级 1.0）。
- 页面右下角两行统计：`Chars` 是去掉空白字符后的字符数，`Words` 是英文单词数加上每个汉字算一个。停手 150 ms 才刷新一次。

### 搜索

`Ctrl+F` 开搜索条，边打边搜。当前页读的是编辑器里还没落盘的内容，其他页读文件（按修改时间缓存）。结果是一行一条「页名 · 那行内容」，单行超过 90 字截断，最多 200 条（Gryffindor.py:2011-2023）。点一条就跳过去，并选中第一个命中的词。`Esc` 关掉。

### 窗口

- 拖到屏幕上、左、右、下四条边（20 px 以内），松手后鼠标一离开，窗口就收到只剩 2 px 的一条缝；鼠标移到那条缝上滑出来，动画 180 ms。
- 自动收有个前提：鼠标先进过窗口。不然程序把窗口叫出来的一瞬间它就自己缩回去了。
- 标题栏的关闭按钮（×）= 收到托盘，不是退出。`Alt+F4` 是存盘真退出。
- 圆点按钮切置顶，默认就是置顶（红点=置顶，灰点=不置顶）。
- 重复启动不开第二个窗口：新进程给老进程发个 `show`，老进程被提到前台，新进程打印两行中文提示，以退出码 2 退出。`run.cmd` 看到 2 会停住，打一行英文再 `pause`。
- 托盘菜单五项：`Auto Start`（默认勾着，只对 exe 生效）、`Global Hotkey`（点一下重录组合键）、`Opacity` 滑块（30–215）、`Show`、`Quit`。菜单里没有“隐藏”项，隐藏走关闭按钮或者热键。
- 默认热键 `Ctrl+G`：藏在托盘就弹出来，贴边只剩缝就滑出来，在别的窗口后面就提到前面，已经在前台就收进托盘。如果 `Ctrl+G` 被别的程序占了，启动时会自动退到 `Ctrl+Alt+G` 并写回设置；两个都不行，托盘那行显示 `Global Hotkey: unavailable`。

### 拖放

- 拖 `.md` / `.markdown` / `.txt` 进窗口：整篇变成新的一页，页名取文件名，重名自动加 `(2)`。
- 拖 `.png` / `.jpg` / `.jpeg` / `.bmp` / `.gif` / `.webp`：复制进 `images/`，正文插入相对路径，宽度 340。
- 其他后缀不管，只在 `error.log` 里记一笔。

---

## 5. 常见问题

**双击 `run.cmd`，窗口一闪就没了**
它进的是出错分支：没找到 Python，或者找到的 Python 里没有 PyQt5。提示打在那一下闪掉的窗口里。开个 cmd，`cd` 到目录，敲 `run.cmd`，就能看到它试了哪个解释器、缺什么。

**报 `Could not load the Qt platform plugin "windows"`**
这句话的意思是 Qt 的 `qwindows.dll` 没加载起来。最常见两种：一是 run.cmd 挑中的 Python 和你装 PyQt5 的不是同一个（比如系统里有个 3.14，PyQt5 装在 3.11 的 `.venv` 里）；二是 PyQt5 装了一半断掉，或者被清理软件删过文件。先看 run.cmd 用的是哪个解释器，再跑 `python -c "import PyQt5; print(PyQt5.__file__)"` 看装在哪，对不上就删掉 `.venv` 重装。VC++ 运行库缺失也可能造成这个错，但不是唯一原因，上面两条排掉再看它。

**全局热键按了没反应**
`Ctrl+G` 被别的程序占了。程序启动时注册失败会自动换 `Ctrl+Alt+G`；两个都注册不上，托盘菜单那行会变成 `Global Hotkey: unavailable`。进托盘菜单 → `Global Hotkey` 重录一个，还失败会弹窗告诉你。

**毛玻璃不生效，窗口是纯色底**
Acrylic 是 Win10 1803 之后才有的效果。系统设置里关掉“透明效果”、走远程桌面、部分虚拟机里都会退回纯色。功能不受影响。这一步代码是 `try/except` 吞掉的（Gryffindor.py:1490-1491），失败也不报错，所以只能看现象。

**杀毒软件报毒**
PyInstaller 用 `--onefile` 打的 exe 经常被误报。源码里没有任何网络请求。不放心就直接跑源码。

**多显示器下窗口位置跑到主屏去了**
位置是存下来的，但恢复时会拿主屏的可用区域做边界判断（Gryffindor.py:2159-2172）：算出来落在主屏可见范围外就回主屏居中。副屏在主屏右边或下边、窗口位置又偏出主屏范围，就会这样。拖回去一次，程序会重新存。

**托盘里勾了 Auto Start，重启没自启**
这个开关只在打包成 exe 后生效（Gryffindor.py:2526-2530 先判断 `sys.frozen`）。源码方式跑的时候，勾了也不会写注册表，属于正常现象。要源码方式自启，自己往 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 加一个指向 `run.cmd` 的值。

**笔记在哪？怎么卸干净**
笔记：程序目录（exe 方式见第 2 节末尾）里的 `Gryffindor_note_p*.md` 和 `images/`。
设置：注册表 `HKCU\Software\GryffindorSoft\Gryffindor`，整个删掉。
自启：`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 `Gryffindor` 值。
日志：`%LOCALAPPDATA%\Gryffindor`，直接删。
这四样清掉就干净了。

---

## 6. 许可

个人自用工具，没附开源许可证。要二次分发或者商用，先联系我。
