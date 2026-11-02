# 法律声明与免责条款 ／ Legal Notice & Disclaimer

> 本文件（`DISCLAIMER.md`）是本仓库（`pikayu-jj`，以下简称"本项目"）许可条款之外**独立适用**的使用条件。
> 获取、运行、复制、修改或以任何方式使用本项目任何内容者（"使用者"），视为**已完整阅读、理解并不可撤销地接受**本文件全部条款。
> 部分条款以英文列于各条末，中英文不一致时以中文为准。
>
> This document is independently binding in addition to, and not in substitution of, the license terms of this repository.
> Any person who obtains, runs, copies, modifies or otherwise uses any part of this project ("User") is deemed to have fully read, understood and irrevocably accepted all terms below.

---

## 第一条 项目性质

1.1 本项目是**本机工具的开源实现**，功能为：对使用者自己机器上已打开的第三方象棋程序窗口做**屏幕截取与图像识别**，并把识别结果交给本机运行的**开源象棋引擎**计算着法，再以**模拟鼠标点击**的方式把着法回输到该窗口。本项目**不向目标程序注入代码、不读写其内存、不修改其文件、不挂钩其函数、不破解其通信协议**。

1.2 本项目以**计算机视觉与自动化技术的学习、研究与个人测试**为目的发布。它不是**外挂、破解工具、私服、代练服务或任何形式的有偿对局服务**，亦不提供上述任何功能。

1.3 本项目由个人在业余时间开发并公开，**非商业发行**，不设客服、不承诺维护、不收取任何费用，不受任何第三方委托或控制。

1.4 项目名称、图标、说明文字中出现的任何第三方商标、商品名、服务名、游戏名（包括但不限于"JJ象棋"、微信、Pikafish 及其权利人的名称与标识）**仅用于说明兼容性与技术构成**，其全部权利归各自权利人所有。本项目与上述任何权利人**不存在隶属、代理、合作、授权、赞助或背书关系**，亦不代表其立场。

---

## 第二条 使用条件（强制）

2.1 **仅限自有设备、自有账号、自行控制的窗口。** 使用者只能在其本人拥有或合法控制的计算设备上，对**其本人已合法打开**的窗口运行本项目。

2.2 **禁止对他人。** 不得把本项目的运行结果、执行过程、数据或衍生能力作用于任何他人设备、他人账号、他人对局，或任何**真人对手的线上对局**。

2.3 **禁止违反目标程序规则。** 目标程序（含其用户协议、服务条款、社区规则）可能禁止自动化操作。使用者有义务在运行前自行核实并遵守；**因违反该等规则产生的一切后果（含警告、封禁、扣分、收益清零、账号终止、民事或刑事责任）由使用者自行承担**。

2.4 **禁止商业用途。** 未经权利人书面许可，不得将本项目（含其源码、构建产物、二进制的全部或部分）用于收费、代练、导流、广告、售卖、捆绑、云服务、硬件预装或任何以营利为目的的用途。

2.5 **禁止再分发植入物。** 不得在分发版本中加入广告、挖矿程序、后门、遥测、远程控制、账号凭证收集或其他任何非本项目开源代码明示的功能。

2.6 **遵守当地法律。** 使用者须确保其使用行为符合其所在地及行为发生地的法律、行政法规与部门规章；**合法性与合规性判断由使用者独立完成**。

---

## 第三条 无关联、无授权声明

3.1 本项目**未获得**任何第三方游戏、平台、引擎或商业实体的**许可、授权、认证或同意**。本项目不声称与任何第三方存在上述关系。

3.2 本项目**不包含、不修改、不反向工程**任何目标程序的代码、资源、密钥或凭证。屏幕截图、测试用图像（`fixtures/`、`dbg/`、`logs/` 下的图像）**仅包含公开界面显示内容**，属技术测试样本，其版权（如有）归原权利人，本项目仅作不可替代的兼容性测试与回归验证之用，不构成合理使用以外的主张。

3.3 如任何权利人认为本仓库中的任何内容侵犯其合法权益，请通过仓库 Issues 联系，权利人提供权属证明后，相关文件将在合理期间内**删除或替换**。

---

## 第四条 许可证与第三方组件

4.1 **本项目自身源码**以 **GNU General Public License v3.0** 发布，全文见 [LICENSE](LICENSE)。在 GPLv3 允许的范围内，使用者可自由运行、研究、复制、修改与再分发；再分发时必须保留许可证与版权声明，并**同步公开修改后的完整源代码**。

4.2 **本文件第二条至第八条的条款属于 GPLv3 第 7 条允许的"附加条款"**，仅限制使用范围与责任，不限制 GPLv3 授予的复制、修改、再分发等权利。若本条与 LICENSE 冲突，就自由软件权利而言以 LICENSE 为准；就使用限制与责任承担而言以本文件为准。

4.3 **Pikafish 引擎**（`pikafish/` 目录及打包产物内的引擎与权重）为独立第三方作品，适用其自身许可：

| 组件 | 许可 | 说明 |
| --- | --- | --- |
| Pikafish（GPLv3 衍生自 Stockfish） | GPLv3，见 [pikafish/Copying.txt](pikafish/Copying.txt)、[pikafish/AUTHORS](pikafish/AUTHORS) | 引擎源码与二进制 |
| `pikafish.nnue` 权重 | [NNUE-License.md](pikafish/NNUE-License.md) | **仅限合法用途；未经许可不得商业使用** |

4.4 使用者以任何方式使用 Pikafish 权重，即视为同意 [NNUE-License.md](pikafish/NNUE-License.md) 的全部条件，包括但不限于"仅限合法用途、超出合法范围的后果（如线上作弊）由使用者自行承担"。**本文件第二条与本条共同构成使用本项目时对第三方许可的遵守义务。**

4.5 本项目可能包含的其他第三方代码、库、字体、图标，其权利与许可归各自权利人，使用者应自行遵守。

---

## 第五条 免责声明：按"现状"提供

5.1 本项目**按"现状"（AS IS）与"现有"（AS AVAILABLE）提供**。在适用法律允许的最大范围内，作者与贡献者**不对本项目作出任何明示或默示的担保**，包括但不限于：适销性担保、特定用途适用性担保、不侵权担保、无缺陷担保、准确性与完整性担保、持续性可用性担保。

5.2 作者与贡献者**不保证**：本项目能够运行、无错误、不中断、与任何目标程序版本兼容、识别结果正确、着法合法或构成"最佳着法"。任何一次运行的结果均可能因窗口尺寸、皮肤、分辨率、渲染时序、系统负载、目标程序更新而变化，**由此产生的任何结果（含输棋、错判、误点、超时判负）均不构成作者的责任**。

5.3 作者与贡献者**不对使用者的任何作为或不作为负责**，包括对局结果、账号状态、游戏内资产、第三方投诉或平台处罚。

---

## 第六条 责任限制

6.1 在适用法律允许的最大范围内，**无论基于合同、侵权（含过失）、严格责任、保证或其他任何法律依据**，作者、维护者、贡献者、版权持有人**均不对任何间接、附带、特殊、惩罚性、示范性或后果性损害承担赔偿责任**，包括但不限于：利润损失、数据丢失或损坏、设备损坏、账号封禁、收益损失、商誉损失、第三方索赔、业务中断、替代服务采购费用。

6.2 在适用法律不允许上述全面排除的司法管辖区，**作者与贡献者的全部累积赔偿责任以其在提出索赔前十二（12）个月内因本项目实际收到的款项总额为上限；本项目免费分发，故该上限为零（0）**。

6.3 使用者**使用本项目的全部风险由其自身承担**。使用者在做出是否使用的判断时，**已完整评估**目标程序规则、当地法律、设备与数据安全风险；作者与贡献者**不承担任何形式的风险分担义务**。

6.4 本条第 6.1 至 6.3 款**在项目停止维护、仓库关闭、文件删除后继续有效**。

---

## 第七条 赔偿与免责（Indemnification）

7.1 使用者**不可撤销地承诺**：因其使用本项目、或因违反本文件任何条款、或因其行为侵犯任何第三方（含游戏平台、其他玩家、权利人）的权利而引发的一切主张、诉讼、仲裁、行政查处、索赔、损失、费用（含合理律师费、仲裁费、差旅费、调查费），**一律由使用者自行承担并负责抗辩，使作者、维护者与贡献者免受任何损害与支出**。

7.2 使用者不得以任何理由要求作者、维护者或贡献者**参与抗辩、出具证明、承担责任或进行赔偿**。

---

## 第八条 其他

8.1 **可分割性**：本文件任一条款被认定无效或不可执行，不影响其余条款的效力；该条款应在**最大限度**内解释为有效，以最接近其原意。

8.2 **不弃权**：作者未行使或延迟行使本文件任何权利，不构成对该权利的放弃。

8.3 **完整协议**：本文件与 [LICENSE](LICENSE)、[pikafish/NNUE-License.md](pikafish/NNUE-License.md) 共同构成使用者与作者之间就本项目**使用**的完整约定，取代此前所有口头或书面的相关表示。

8.4 **准据法与管辖**：本文件适用**中华人民共和国大陆地区法律**（不含港澳台地区法律及冲突规范）。因本文件引起的争议，**以作者所在地有管辖权的人民法院为一审管辖法院**；使用者不同意该管辖的，应**立即停止使用并删除本项目全部副本**。

8.5 **条款修订**：作者可随时更新本文件，更新自提交至本仓库之日起对**此后**的使用行为生效。使用者**每次运行前应自行查阅**最新版本。

8.6 **生效**：本文件自随代码提交至本仓库之时起生效，适用于此前、当前及此后的全部使用行为。

---

## English Summary (non-authoritative)

- **Scope.** This is an open-source local automation tool: screen capture + image recognition + a locally run open-source chess engine + simulated mouse clicks. It does **not** inject into, read memory of, patch, hook or reverse-engineer the target application.
- **You may** use it only on your **own devices, own accounts and your own windows**, for study and personal testing.
- **You may not** use it against real human opponents or third parties, in violation of any platform's terms of service, for any commercial purpose, or in distribution with ads, malware, telemetry or credential collection.
- **No affiliation.** This project is not authorized, endorsed by, or affiliated with any game, platform or engine rights holder.
- **License.** Project source is GPLv3 (see `LICENSE`). Pikafish and its NNUE weights are governed by their own licenses (`pikafish/Copying.txt`, `pikafish/NNUE-License.md`), including **no commercial use without permission**.
- **No warranty.** Provided **AS IS**, without any warranty of any kind.
- **No liability.** In no event shall the authors be liable for any indirect, incidental, special, exemplary or consequential damages; aggregate liability is capped at the total amount received by the authors for this project, which is **zero**.
- **Indemnity.** You agree to defend and fully indemnify the authors against all third-party claims arising from your use.
- **Governing law.** Laws of mainland China; exclusive jurisdiction at the court where the author resides. If you do not accept these terms, stop using and delete all copies immediately.

---

© 2026 z416946520 · 本项目源码以 GPLv3 发布，本声明独立适用。
