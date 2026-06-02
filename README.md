# Offer 捕手

AI 驱动的学生求职智能体 — 批量匹配、深度诊断、简历优化、公司分析。附带浏览器插件实现 JD 一键抓取。

## 快速开始

### 1. 环境准备

```bash
pip install -r requirements.txt
```

### 2. 配置 API Key

```bash
# Windows
set DS_KEY=sk-your-deepseek-key
set DASHSCOPE_KEY=sk-your-dashscope-key

# Mac / Linux
export DS_KEY=sk-your-deepseek-key
export DASHSCOPE_KEY=sk-your-dashscope-key
```

- **DS_KEY**：[DeepSeek API Key](https://platform.deepseek.com/) — 用于简历解析、JD 匹配、深度诊断
- **DASHSCOPE_KEY**：[阿里云 DashScope API Key](https://dashscope.console.aliyun.com/) — 用于浏览器插件视觉 JD 提取（通义千问 VL）

### 3. 启动服务

```bash
python main.py
```

打开 http://localhost:5000

### 4. 安装浏览器插件

1. 打开 Chrome，访问 `chrome://extensions/`
2. 开启「开发者模式」
3. 点击「加载已解压的扩展程序」
4. 选择 `extension/` 目录
5. 默认服务器地址为 `http://localhost:5000`，根据实际情况修改

## 功能模块

| 模块 | 说明 |
|------|------|
| **批量匹配** | 上传简历 + 导入 JD → AI 五维度打分排序 → 可视化结果 |
| **深度诊断** | 针对单个岗位逐项比对（学历/专业/经验/技能）→ pass/warn/fail + 具体建议 |
| **简历优化** | AI 分析 5 个目标 JD → 生成针对性的简历修改方案 |
| **投递管理** | 记录投递进度（待投/已投/面试/offer）→ 看板管理 |
| **策略建议** | AI 生成投递优先顺序 + 风险提示 + 周计划 |
| **权重自定义** | 拖滑块调整五维度权重（经验/学科/技能/公司/适配）|

## 浏览器插件

在 BOSS 直聘搜索结果页：
- **📄 抓取当前**：截取当前可见岗位，VL 识别标题+公司+JD
- **📦 逐个抓取**：自动点击 20 张卡片，每张截图发给 VL 识别
- **📤 发送全部**：将收集的 JD 提交至 Web 控制台

技术原理：Chrome `captureVisibleTab` 截图 → Flask 转发给通义千问 VL → VL 返回结构化 JSON → 存入匹配引擎。长篇 JD 自动多截图拼接。

## 评分公式

```
总分 = 经验匹配 × 40% + 学科兼容 × 25% + 技能覆盖 × 15% + 公司质量 × 10% + 综合适配 × 10%
```

权重可在 Web 控制台实时调整，总和自动归一化。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python Flask + gunicorn |
| 前端 | HTML/CSS/JS（零框架依赖）|
| AI 文本 | DeepSeek API（Chat/JSON 模式）|
| AI 视觉 | 通义千问 VL (qwen-vl-max) |
| 插件 | Chrome Extension Manifest V3 |
| 部署 | Railway / Render 一键部署 |

## 项目结构

```
offer-hunter/
├── main.py              # Flask 服务端（API 路由 + 状态管理）
├── engine/
│   └── matcher.py       # AI 匹配引擎（解析/打分/诊断/优化）
├── templates/
│   └── index.html       # Web 控制台 UI（六标签页）
├── extension/           # Chrome 浏览器插件
│   ├── manifest.json    # 插件配置 (Manifest V3)
│   ├── popup.html       # 弹出窗口 UI
│   ├── popup.js         # 弹出窗口逻辑（截图 + API 调用）
│   └── content.js       # 页面注入脚本（点击/滚动/克隆）
├── requirements.txt     # Python 依赖
├── README.md            # 你在这里
└── 方案说明.md           # 详细设计文档（1000+ 字）
```

## 部署

详见 [方案说明.md](./方案说明.md) 第六章。

简要步骤：GitHub 上传 → Railway 导入 → 设环境变量 → 改插件地址 → 完成。
