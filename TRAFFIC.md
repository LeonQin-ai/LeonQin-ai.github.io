# 博客访问记录

| 查询日期（北京时间） | 数据来源 | 统计范围 | 浏览量 | 独立访客 |
| --- | --- | --- | --- | --- |
| 2026-11-14 | GitHub 仓库 Traffic API | 博客源码仓库，最近 14 天 | 2 | 2 |

这里的仓库数据不统计 GitHub Pages 网页访问。博客网页在接入统计前的访问人数未知。

要开始统计网页访问，在自己的 [GoatCounter](https://www.goatcounter.com/) 账户创建站点后，将形如 `https://站点代号.goatcounter.com/count` 的真实地址写入博客仓库 **Settings → Secrets and variables → Actions → Variables** 下的 `GOATCOUNTER_ENDPOINT`，然后重新运行 Pages 工作流。变量留空时不加载统计脚本。部署后访问博客首页和一篇文章，确认 GoatCounter 后台出现对应路径；报表从接入后起算，不补录历史数据。

本地用 `gh api repos/LeonQin-ai/LeonQin-ai.github.io/traffic/views` 可以复查仓库访问数据。重叠的统计窗口不能累加为累计独立访客。
