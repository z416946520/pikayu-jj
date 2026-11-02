# JJ象棋（微信小程序）非视觉取棋盘：可行性调查

目标：让 pikafishjj 不依赖截屏识别，直接从运行中的程序里拿到棋盘。下面是这次调查的**实测结论**、证据位置、被堵死的路线，以及推荐的下一步。所有脚本在 `tools/jj-mem/`，可直接重跑。

## 1. 目标身份（实测）

| 项 | 值 |
| --- | --- |
| 形态 | 微信**小程序**（不是原生 PC 程序），窗口标题「JJ象棋」 |
| appid / 版本 | `wx0c852640e4324692` / v151 |
| 宿主进程 | `WeChatAppEx.exe`（WeChat 4.x `xwechat`，RadiumWMPF 25560），命令行带 `--enable-applet-v3` 与 `--wechat-files-path=D:\WeChat\Document\xwechat_files` |
| 进程结构 | 1 个浏览器/主进程（实测 PID 1164）+ 9~10 个 renderer + 2 个 utility；小程序逻辑跑在其中一个 renderer（实测 5604，工作集约 710 MB，含象棋 FEN 数据） |
| 磁盘包 | `%APPDATA%\Tencent\xwechat\radium\users\<user>\applet\packages\wx0c852640e4324692\151\`：`_data-package_.wxapkg` 5.03 MB、`_wasmcode_.wxapkg` 5.94 MB、`_wasmcode1_.wxapkg` 8.11 MB、`__WITHOUT_MULTI_PLUGINCODE__.wxapkg` 0.75 MB，全部以 `V1MMWX` 开头（加密容器） |
| 本地存储 | `...\applet\local\wx0c852640e4324692\`（若干 3~256 KB 文件，小程序 storage/MMKV） |

## 2. 逐条路线的实测结论

| 路线 | 结果 | 证据 |
| --- | --- | --- |
| UI Automation | ✗ 无用：窗口 UIA 树只有 44 个元素，全是微信自己的胶囊菜单（微信游戏／全部／朋友／加到桌面…），没有任何棋盘内容 | 现场 UIA 枚举 |
| 读进程内存 | ✓ 可读，无需提权：`ReadProcessMemory` 对全部 11~13 个 `WeChatAppEx` 进程成功 | `tools/jj-mem/proc_recon.py` |
| 内存里的明文数据 | △ 有，但不是**实时**棋盘：renderer 堆里能读到象棋 FEN/课程数据（`courseName`/`move`/`fen` 字段）、协议名（`match_wireless`、`points_conf`…）、引擎日志（`fen … localmove <moves>`）；但把当前盘面（识别出的 `3k5/6R1C/…`）按整串、子串、UTF-16 在全部进程里搜都搜不到 → 实时盘面不是 FEN 字符串 | `mem_fen.py`、`mem_known.py` |
| 90 格数组结构扫描 | ✗ 未命中：按「90 格里恰好 10 格与多数值不同」在全部进程扫（stride 1/2/4 × 行/列主序 × 8 种翻转 × 7 种空格标记）零命中 → 不是朴素的 90 格小整数数组 | `mem_board2.py` |
| 页面哈希差分 | △ 噪声太大：一次落子后 1272~3726 页变化，全是 V8 GC／计时器／分配器噪声，需要去噪 | `memdiff.py`、`memexp2.py` |
| Frida 注入 renderer | ✗ 被沙箱拒绝：能 attach 浏览器/utility 进程（1164、13288、24520 ✓），**全部 renderer 报 refused to load frida-agent**（Chromium 沙箱）→ 无法在小程序 JS 层下钩子 | `frida_recon.py`（Frida 17 装在 `.venv-re`） |
| 内存里找解密后的小程序包 | ✗ 未找到：全进程搜 `app-service.js`／`app-config.json`／`page-frame.html`／`.wxml` 等索引文件名，只命中微信运行时自己的字符串 | `mem_bundle.py` |
| `V1MMWX` 解密 | ✗ 未破解：候选矩阵（PBKDF2-SHA1(appid, saltiest, 1000, 16/24/32)、MD5(appid/user)、AES CBC/CFB/OFB/CTR/ECB、key/iv 取 key16/keyHi/固定文本/全零）全部失败；且密文长度 766066 mod 16 = 2，不是块对齐 → 方案不同（另有 KDF，或流加密/额外头部） | `wxdec.ps1`、`wxdec2.ps1`、`wxdec3.ps1` |

## 3. 结论与推荐路线

1. **可行但未完成：内存里的实时盘面**（推荐）。它确实存在（内存可读、应用自己的数据在堆里），只是编码既不是 FEN、也不是 90 格小整数数组。下一步用**可逆差分**定位：A 快照 → 落一手 → B 快照 → 悔棋 → C 快照，只保留「A 与 C 完全相同、而 B 不同」的地址段（这一步把 GC/计时器噪声全部滤掉），并把扫描范围收敛到「大块、私有、可读写、大部分为 0」的 wasm 线性内存候选区；再用已知盘面反推编码。工具已就绪：`tools/jj-mem/memdiff.py`、`memexp2.py`。
2. **协议拦截**（备选）：Frida 能进浏览器/utility 进程，可钩 `ws2_32!send/recv` 或 mojo IPC；风险是小程序网络可能走主 `Weixin.exe` 的 MMTLS 栈，且 renderer 进不去。
3. **拿真正的 `V1MMWX` 解密算法**（最彻底）：解出包就能静态看小程序的 JS/wasm，直接得到「盘面编码 + 走子协议」，甚至可能做到协议级自动化（不点屏幕）。可以直接分析 `WeChatAppEx.exe` 里的解密例程（该进程 Frida 可 attach ✓）。

## 4. 副作用与注意

- 调查期间为了制造「盘面变化」，在残局里点了一手棋（源→目标），盘面已改变；可用界面上的【悔棋】或【重来】恢复。
- `.venv-re/`（141 MB）是这次装的 Frida 工具环境，只为调查用，可以随时删。
- 抓到的夹具：`fixtures/jj_puzzle1.png`（残局第 1 关窗口截图，标定 cpitch 66.50 / rpitch 63.68，10 子）。
