# AOTR Bespoke 房源筛选工具 — 案例存档

**项目周期**：2026-04-26 ~ 2026-04-27（约 24 小时跨夜+次日迭代）
**最终生产 URL**：https://www.neststudent.com/sales/aotr-bespoke.html

---

## 一句话定位

把房东 Bespoke 的私有 Google Sheet 房源（268 套）变成销售可即时筛选 + 地图 + AI 生成介绍的内部工具，零外包、低代码、可持续。

---

## 业务价值

**销售场景**：客户来咨询新加坡留学生租房，需求维度多（入住时间、预算、学校、区域、户型），现在销售在 Google Sheet 里手动翻 1500 行。

**工具产出**：
- 1 秒内多维筛选（日期 + 学校通勤 + 价格 + 房型 + 区域 + 仅限女性...）
- 地图视图直观看分布
- 一键生成微信/小红书可发的销售文案

---

## 完整功能清单

### 数据层
- Google Sheet（房东私有，Will 个人 hooli 邮箱有查看权）
- Apps Script Web App（跑在 Will 邮箱下，绕开 Sheet 共享权限）
- 地理编码缓存（OneMap，266 个唯一地址）
- 学校通勤矩阵（Google Distance Matrix，10 学校 × 266 房源 = 2660 对公交时间）
- MRT 步行矩阵（Google Distance Matrix，266 套到最近 MRT 步行时间）

### 前端（单文件 HTML + 内联 JS）
- 列表 / 地图双视图切换
- 起租日期 14天/30天协调窗口逻辑
- 学校通勤显示 + 筛选 + 排序
- "更多筛选" 折叠面板（地区/房型/卧室/Auto Close/仅限女性）
- 翻页 100 条/页
- AI 生成介绍弹窗 + 一键复制

### 部署
- 国内主：`www.neststudent.com/sales/aotr-bespoke.html`（nginx 静态托管）
- 海外备：`azureoxe.github.io/aotr-bespoke`
- Apps Script 通过 clasp 自动化部署

---

## 架构决策（带"为什么"）

### 1. 为什么用 Apps Script Web App 而不是直接读 Sheet？
Sheet 是 Bespoke 的私有数据，Will 只有查看权。直接读需要 OAuth 暴露给前端。Apps Script 跑在 Will 账号下，对外暴露匿名 JSON API，干净隔离。

### 2. 为什么用 OneMap 而不是 Google Maps 做地理编码？
新加坡政府服务，**完全免费、无需 API key、本地地址识别准**。268 个地址 90 秒跑完。

### 3. 为什么用 Google Distance Matrix 而不是 OneMap Routing 做通勤？
OneMap PT 路由需要注册 + 3 天换 token，运维负担大。Google Distance Matrix 一个 key 永不过期 + 免费 $200/月额度（实际用 $1-3）。

### 4. 为什么把 Bespoke 数据自己处理而不是同步进明道？
Bespoke 不是 NestLiving 自营房源，是合作房东的临时数据。同步进明道污染主数据。隔离的小工具更合适。

### 5. 为什么用 Apps Script 当 Gemini 代理（不直接前端调）？
前端调 Gemini → key 暴露在 HTML 源码 → 任何访问者能爬走刷免费配额。Apps Script 后台调，key 在 PropertiesService（仅 owner 可见）。

### 6. 为什么用 GitHub Pages + 自建服务器双部署？
GitHub Pages 国内访问被 GFW 偶发干扰（"连接被终止"）。销售在国内办公不能依赖 VPN。自建服务器（已有的 admin 服务器）国内稳定 → 主用。GitHub 留作海外 / 灾备。

### 7. 为什么用 clasp 自动化 Apps Script 部署？
手动操作（编辑器 → 部署 → 管理 → 编辑 → 新版本 → 保存）每次 5 步、容易出错。clasp 一条命令搞定。当用户曾把整个脚本误覆盖成只剩 generateIntro 时，恢复成本巨大 — 自动化能避免这种事故。

---

## 全部踩过的坑（含解决方案）

### 数据层
| 坑 | 现象 | 根因 | 修法 |
|---|---|---|---|
| Apps Script Date 对象 String() 转换 | 日期变 "Sun May 28 2026 00:00:00 GM"（GMT 截断） | 老的 parseDate 用 `split("T")` 误匹配 GMT 里的 T | 加 `instanceof Date` 分支用 `getFullYear/getMonth/getDate` |
| Formula 单元格 getValues() 拿不到值 | 表里显示"28 May" 但 API 返回空 | formula 在某些情况下 getValues() 失败 | 双源兜底：getValues + getDisplayValues |
| 跨区域同号撞车（最严重 bug）| 点 One North 显示 Tanamera | 房源 `no` 字段在每个区域内单独编号，140 对 (region, no) 重复 | 用 DATA 数组 index 作全局唯一 ID |
| MingDao 通勤表表面有数据 | 34894 条通勤记录 | 但只覆盖 MingDao 公寓表，Bespoke 不在 | 必须 sample 验证再用，不能光看表名 |

### Apps Script
| 坑 | 现象 | 修法 |
|---|---|---|
| OAuth 权限作用域 | UrlFetchApp.fetch 被拒 | 在编辑器手动 Run 一次触发授权 |
| 新功能误覆盖整个脚本 | doGet 等函数全没了，list 端点挂 | clasp 自动化 + git 备份 |
| Gemini 503 高并发抽风 | 偶发"This model is currently experiencing high demand" | Apps Script 内置 3 模型降级 + 2 次重试 |

### 前端
| 坑 | 现象 | 修法 |
|---|---|---|
| GitHub Pages 国内不稳 | "连接被意外终止" | 改 nginx 子路径托管 |
| date input 不触发 change | 修改日期不刷新筛选 | 同时监听 change + input |
| 浏览器缓存 | 部署后看到的还是旧版 | 加 Cache-Control 头 + 用户强刷 Cmd+Shift+R |

### LLM 文案生成
| 坑 | 现象 | 修法 |
|---|---|---|
| Gemini 编造 MRT 步行时间 | "Tampines MRT 25 分钟"（实际 8 分钟） | 预算真实步行时间，传给 prompt 强制使用 |
| Gemini 编造商场 / MRT 站名 | 偶尔写错 | prompt 加"不知道的省略，不要编造" |
| 模型 ID 过期 | gemini-2.0-flash 下架 | 改用 gemini-2.5-flash |

---

## 时间和钱

### 投入
- **总工时**：约 6 小时（跨两晚）
- **现金成本**：$0（所有服务都在免费额度内）

### 长期运营成本
- Google Maps：每月 ~$0（远低于免费额度）
- Apps Script：免费
- nest 服务器：你已经有
- 域名：你已经有
- **= 完全无新增成本**

---

## 关键文件清单

```
~/nestliving/aotr-bespoke-site/
├── index.html              # 主 HTML（单文件，内联 CSS/JS）
├── geocodes.json           # 地址 → lat/lng 缓存
├── geocode.py              # 增量地理编码脚本（OneMap）
├── commute.json            # 学校通勤矩阵
├── commute.py              # 增量通勤算法（Google Distance Matrix）
├── mrt_stations.json       # 新加坡 MRT 站列表
├── mrt_walk.json           # 房源 → 最近 MRT 步行时间
├── mrt_walk.py             # 增量 MRT 步行算法
├── .env                    # API keys（chmod 600，不入 git）
└── CASE_STUDY.md           # 本文档

~/nestliving/aotr-apps-script/
├── Code.js                 # Apps Script 代码（clasp 管理）
├── appsscript.json         # Apps Script 配置
└── .clasp.json             # clasp 项目链接
```

---

## 增量更新流程（写给未来的自己）

### 房源数据更新
- 房东自己改 Sheet → 销售刷新即看到
- **零运维**

### 添加新房源（地理编码 + 通勤 + MRT 步行 全套）
```bash
cd ~/nestliving/aotr-bespoke-site
python3 geocode.py    # 增量编码新地址
python3 commute.py    # 增量算新房源到 10 学校的通勤
python3 mrt_walk.py   # 增量算新房源到最近 MRT 步行
scp -i <key> *.json root@146.56.223.89:/opt/web/sales/
```

### 添加新学校
1. `commute.py` 里 `SCHOOLS` 数组加一条（lat/lng 从明道学校库查）
2. `python3 commute.py` 自动只算新学校 × 所有房源
3. scp 同步 `commute.json`

### 改 HTML
```bash
cd ~/nestliving/aotr-bespoke-site
# 改 index.html
git add . && git commit -m "..." && git push
scp -i <key> index.html root@146.56.223.89:/opt/web/sales/aotr-bespoke.html
```

### 改 Apps Script
```bash
cd ~/nestliving/aotr-apps-script
# 改 Code.js
clasp push --force
clasp deploy --deploymentId AKfycbxZiDMWyA9fkpVOAaXuCczGeZXmpid9EYgKHyRRdecsdpkw8pZIhRZNesq5kcYTV_cT --description "..."
```

---

## 这个项目的可复用模式

如果以后做类似项目（B 端 / 内部工具 / 数据展示 + AI 增强），可以套这个模板：

1. **数据源隔离**：用 Apps Script / Cloudflare Workers 做"私有数据 → 公开 JSON" 的代理
2. **地理增强**：地址 → lat/lng → 通勤矩阵 → 真实距离 / 时间
3. **静态前端 + 多托管**：单文件 HTML，自建服务器 + GitHub Pages 双线
4. **AI 文案生成**：固定数据从模板拼，自然语言交给 LLM，关键事实必须传真实数据
5. **clasp / git 自动化**：所有部署脚本化

---

## 可以做但还没做的功能

- 通勤多人需求（情侣不同学校）
- 房源对比（选 2-3 套并排看）
- 销售文案 A/B 测试（保存哪条转化率高）
- 客户偏好保存（销售常用筛选预设）
- 新房源/已下架自动通知销售群
