# 🔥 HotPulse · 全网热榜

> 聚合国内外主流平台热榜（微博、抖音、头条、百度、知乎、B站、澎湃、央视 + BBC、NYT、Guardian、Al Jazeera、Google News 共 13 个来源），自动识别多平台同时上榜的大事

**🌐 在线访问：[https://climb0516.github.io/hot-news/](https://climb0516.github.io/hot-news/)**

页面风格参考 [TechPulse](https://github.com/climb0516/tech-news)。

---

## 功能特性

- **13 个来源**：8 个国内平台 + 5 个海外媒体，每小时自动抓取
- **三种视图**：
  - 平台榜单：每个平台一张卡片，显示 Top 10（可展开全部），带排名、热度、新 / 热 / 沸标签
  - 大事聚合：把不同平台上的同一事件合并，按「在榜平台数 + 排名权重」排序，看今天真正的大事
  - 信息流：所有平台的条目按相对排名交错排列，带摘要和封面
- **自动分类**：时政 / 国际 / 体育 / 娱乐 / 财经 / 科技 / 社会，按标题关键词归类
- **组合筛选**：分类单选 + 平台多选（选择会被记住），左侧实时显示每项条数
- **全文搜索**：快捷键 `⌘K` / `Ctrl K`，`Esc` 清空
- **右侧挂件**：跨平台大事 Top 10、分类分布、来源抓取状态
- **容错**：某个来源本次抓取失败时沿用上一次数据，并在卡片上标注「旧数据」
- **深色 / 浅色主题**、手机适配、页面每 10 分钟自动刷新数据

---

## 技术架构

```
GitHub Actions（每小时 / 手动 / 修改爬虫后 push）
  ↓ python scraper.py（只用标准库，无需安装依赖）
  ↓ 并发抓取 13 个来源 → 分类 → 跨平台事件聚合
  ↓ 写入 data.json 并 commit
       ↓
GitHub Pages（index.html）
  ↓ 前端读取同目录 data.json 渲染
```

热榜本身是快照数据，所以不用数据库，直接把最新快照存成 `data.json`。

---

## 数据来源

**国内**

| 来源 | 方式 | 条数 | 说明 |
|------|------|------|------|
| 微博热搜 | 游客 Cookie + 解析 s.weibo.com 热搜页 | 50 | 官方 ajax 接口对游客返回 403；自动过滤商业推广位 |
| 抖音热榜 | iesdouyin 热搜接口 | 50 | |
| 今日头条 | hot-board 接口 | 50 | 含封面图 |
| 百度热搜 | top.baidu.com 接口 | 50 | 跳过置顶条 |
| 知乎热榜 | api.zhihu.com | 30 | 含问题摘要 |
| B站热门 | ranking/v2 接口 | 30 | 视频标题不参与事件聚合 |
| 澎湃新闻 | 首页侧栏热闻接口 | 20 | |
| 央视新闻 | 新闻列表 jsonp | 20 | 按时间排序 |

**海外**（RSS）

| 来源 | 条数 |
|------|------|
| BBC World | 20 |
| NYTimes World | 20 |
| The Guardian World | 20 |
| Al Jazeera | 20 |
| Google News（US） | 20 |

**新增 / 删除来源**：编辑 `scraper.py` 里的 `SOURCES` 列表（id、名称、地区、类型、头像缩写、主题色、抓取函数）。RSS 来源直接用 `rss(url)` 生成抓取函数。

**分类规则**：见 `scraper.py` 中的 `CATEGORIES`，按顺序匹配，先命中的生效；英文关键词按单词边界匹配，中文按子串匹配；没命中的国内条目归「社会」，海外条目归「国际」。

**事件聚合**：只对国内平台的中文标题做聚合。标题去掉标点后，两两比较字符二元组的重合度，重合度达到阈值就并成同一事件（见 `similar()`）。

**图片防盗链**：页面统一使用 `referrerpolicy="no-referrer"`。

---

## 本地运行

```
python3 scraper.py              # 抓取一次，生成 data.json
python3 -m http.server 8000     # 浏览器打开 http://localhost:8000
```

直接双击 `index.html`（file:// 协议）无法读取 `data.json`，需要通过 HTTP 服务打开。

---

## 部署到 GitHub Pages

1. 新建仓库并 push 本目录
2. Settings → Pages → Source 选 `main` 分支根目录
3. Settings → Actions → General → Workflow permissions 选 **Read and write**（workflow 需要提交 data.json）
4. Actions 页面手动运行一次 `Hot List Scraper`

> 注意：GitHub Actions 的机器在海外，个别国内平台可能限制海外 IP。如果线上某个来源持续显示「旧数据」，可以改为在本机用 launchd / cron 定时执行 `python3 scraper.py && git commit -am "data" && git push`。
>
> 仓库 60 天没有提交时，GitHub 会自动停用定时任务。本项目每小时都会提交 data.json，正常情况下不会触发。
