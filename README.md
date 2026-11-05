# Gryffindor · Windows 桌面多页签笔记



## 需求设计

市面上的便签要么太重（带账号、带同步），要么不支持多页。我要的是：随手叫出来、一屏内切几页、写完自动存、断网也能用。遂设计一个PyQt5 写的轻量笔记工具，单文件源码，毛玻璃无边框窗口，常驻屏幕边缘，不联网。

---

## 1. 环境要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 1803 及以上 / Windows 11（毛玻璃依赖 DWM Acrylic，Win7 不支持） |
| Python | 3.9 – 3.12（推荐 3.10 或 3.11） |
| 依赖 | 只有 PyQt5（约 50 MB） |
| 磁盘 | 源码 120 KB；笔记与图片按实际使用增长 |

不需要数据库、不需要联网、不需要管理员权限。设置写在注册表 `HKCU\Software\GryffindorSoft\Gryffindor`，不写系统目录。
键名：`page_names` 页签名称、`current_page` 当前页、`hotkey` 全局热键、`opacity` 透明度、窗口几何单独保存。

---

## 2. 拉取与运行

```bat
git clone https://github.com/AceXSage/gryffindor-stickynotes.git
cd gryffindor-stickynotes

python -m venv .venv
.venv\Scripts\activate
pip install PyQt5 -i https://pypi.tuna.tsinghua.edu.cn/simple

python Gryffindor.py
```

装完之后，以后直接**双击 `run.cmd`** 就能启动（它优先用目录里的 `.venv`，没有就找系统 Python，PyQt5 没装会直接把安装命令打出来）。

没有 git 也行：下载 ZIP → 解压 → 从第 2 步开始。

**直接要 exe（不装 Python）：**

```bat
pip install pyinstaller
pyinstaller --noconfirm --windowed --icon Gryffindor_icon.ico Gryffindor.py
```

产物在 `dist\Gryffindor.exe`，单文件，可拷到任意 Win10/11 机器。注意：**笔记生成在 exe 所在目录**，建议单独放一个文件夹再用。

---

## 3. 初建问题

启动后程序自己创建，不用手动建：

```
Gryffindor_note_p1.md     第 I 页内容（富文本 HTML，兼容旧版纯 Markdown 文本）
Gryffindor_note_p2.md     第 II 页，按页签顺序编号
images/                   拖进来的图片复制到这里，正文写相对路径
```

- 内容 500 ms 防抖后自动落盘，切页、关窗、退出都会再 flush 一次。
- 文件按页签顺序编号：删掉中间页，后面的文件整体前移一位，不要在资源管理器里手动改名。
- 备份：整个文件夹拷走。迁移：连 `images/` 一起搬，相对路径不会断。

---

## 4. 功能介绍

### 页签

| 操作 | 效果 |
|---|---|
| 点标题栏 `+` | 新增一页，自动编号 I / II / III… |
| 双击页签 或 `F2` | 重命名当前页 |
| 右键页签 | 重命名 / 复制本页纯文本 / 删除 |
| 按住页签左右拖 | 调整页序，内容跟着走 |
| `Ctrl+Tab` / `Ctrl+Shift+Tab` | 下一页 / 上一页 |
| `Del` | 只在刚点过页签时删当前页（弹确认）；碰过正文后就是删字符 |

### 编辑

- 输入 `# ` `## ` … `###### ` 自动变标题；`- ` / `* ` 变无序列表；`1. ` 变有序列表；`> ` 变引用；`--- ` 变分割线。
- 回车时自动渲染行内格式：粗体、斜体、删除线、高亮、行内代码。
- `Ctrl+B` 加粗、`Ctrl+I` 斜体、`Ctrl+Shift+H` 高亮；没选中文字时自动选中光标所在词。
- `Ctrl+滚轮` 或标题栏 `+` / `-` 缩放字号（8–72 pt），已有标题按层级同比例缩放。
- 右下角实时统计：`Chars`（不含空白字符数）· `Words`（英文单词数 + 中文字符数）。

### 搜索

`Ctrl+F` 打开搜索条，输入即在所有页里搜：当前页取编辑器实时内容，其他页读文件。结果显示为「页名 · 命中行」，点一下跳过去并选中命中的词，`Esc` 关闭，最多 200 条。

### 窗口

- 拖到屏幕四边自动隐藏，鼠标悬停弹出（鼠标进过窗口才允许吸附，避免叫出来就被推走）。
- 关闭按钮 = 最小化到托盘，不是退出；退出走托盘菜单。
- 标题栏圆点按钮切换窗口置顶。
- 重复启动不会开第二个窗口，会把已在跑的那个叫到前台。
- 托盘菜单：显示/隐藏、透明度滑块（30–215）、全局热键改键、开机自启开关、退出。
- 默认全局热键 `Ctrl+G`：藏着时叫出来，已在眼前时收回托盘，不在前台时只叫到前面。

### 拖放

- 拖 `.md` / `.txt` 进来 → 导入为新页，页名取文件名。
- 拖图片（png/jpg/jpeg/bmp/gif/webp）进来 → 复制到 `images/`，正文插入相对路径。

---

## 5. 常见问题

**启动报 could not find or load the Qt platform plugin "windows"**
缺微软 VC++ 运行库，或误用了系统里残缺的 Qt。装 VC++ 2015–2022 x64 运行库，并确认跑的是 venv 里的 python。

**全局热键按了没反应**
`Ctrl+G` 被别的程序占用。托盘菜单 → 热键设置里换组合键；注册失败时程序会提示。

**毛玻璃不生效，窗口是纯色**
需要 Win10 1803+ 且系统「透明效果」开着。远程桌面和部分虚拟机不支持 Acrylic，会退回纯色底，功能不受影响。

**杀毒软件报毒**
PyInstaller 单文件 exe 的常见误报。不放心就直接跑源码 `python Gryffindor.py`，功能一致。

**多显示器下窗口位置乱**
窗口位置按屏幕保存；换显示器或改缩放比例后第一次会回落到主屏，重新拖一次即可。

**笔记在哪？怎么彻底卸载？**
笔记：程序目录下 `Gryffindor_note_p*.md` 与 `images/`。设置：注册表 `HKCU\Software\GryffindorSoft\Gryffindor`。
卸载：删程序目录 → 删注册表项 → 托盘菜单关掉「开机自启」（或删 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` 下的 Gryffindor 项）。

---

## 6. 许可

个人自用工具，未附开源许可证。二次分发或商用请联系作者。
