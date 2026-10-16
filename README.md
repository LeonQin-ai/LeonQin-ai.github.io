# Leon Qin · 工程笔记

个人技术博客，关注 AI 与系统工程，首个专题为 **Cognitive OS 的源码、架构与实测**。

- 网站：**https://leonqin-ai.github.io/**
- 项目：[Cognitive OS](https://github.com/LeonQin-ai/cognitive-os-agent)
- [文章目录与项目分享文案](content/README.md)
- 本仓库只管理博客内容与网站，不包含 Runtime 源码或运行配置。

## 内容

8 篇文章保存在 [`content/`](content/)，包括 C11 Runtime、多轮 Agent 讨论、Flow DAG、Memory/Context、工具协议、可靠性、百万任务实测和上手实验。文章引用原项目的源码和原始证据；历史基准不是每次构建重新测量的生产模型性能。

正文已扩展为源码深读系列：二叉堆与任务回收、讨论接管时序、Kahn 分层与失败传播、MMU 预算和缓存、真实 DSML 故障复盘、幂等与中断恢复、原始数据复算，以及可运行验收脚本和故障分析。源码解读链接固定到核对的提交 `cca98b6`；当前限制与后续改进方向在正文中分别说明。

## 本地预览

需要 Python 3.12 或更高版本：

```bash
python -m pip install -r requirements.txt
python build.py
python tests/check_site.py
python -m http.server 4173 --directory _site
```

打开 `http://localhost:4173`。`_site/` 是生成产物，不提交到仓库。

## 写文章

1. 在 `content/` 添加 Markdown 正文，第一行为一级标题。
2. 在 `content/posts.json` 添加文件名、永久 slug、标题、主题、摘要、标签和发布日期。
3. 运行构建和检查，通过后推送 `main`。

文章链接形如 `/articles/agent-runtime-in-c/`，不包含文件日期。内部 `.md` 链接在构建时转换为阅读页链接。两张 Mermaid 架构图在站点内使用静态 SVG 呈现，保留可展开的图示源码。

## 发布

GitHub Pages 使用 GitHub Actions 部署。工作流安装固定版本的 Markdown 解析器、生成完整静态 HTML、检查内部链接与 SEO/RSS，并执行浏览器回归，再上传 Pages 产物。仓库 Pages 设置的发布源为 **GitHub Actions**。

网站不依赖在线字体、外部 JavaScript CDN 或服务端数据库，文章正文直接包含在生成的 HTML 中；深浅主题、搜索和代码复制使用本地 JavaScript。

## 浏览器验证

```bash
npm ci
npx playwright install chromium
npm test
```

Windows 如果已有 Edge，可设置环境变量 `PLAYWRIGHT_BROWSER_CHANNEL=msedge`，直接使用本机浏览器。回归覆盖首页、8 个文章链接、主题筛选、搜索/无结果、键盘快捷键、主题持久化、文章目录/代码复制，以及手机布局。截图为测试产物，不随网站源码发布。
