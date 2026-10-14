#!/usr/bin/env python3
"""HotPulse scraper — 抓取国内外主流平台热榜，输出 data.json。仅依赖 Python 标准库。"""
import html, json, re, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
from pathlib import Path

OUT = Path(__file__).with_name("data.json")
CST = timezone(timedelta(hours=8))
UA  = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                     "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"}

# ── 分类 ──────────────────────────────────────────────────────────────────────
# 顺序即优先级：先命中的分类生效
CATEGORIES = [
    ("politics", "时政", ["国务院", "总书记", "中央", "外交部", "国台办", "国防部", "人大", "政协", "政府", "部长",
                          "省委", "市委", "书记", "被查", "落马", "双开", "纪委", "监委", "反腐", "党中央", "政策",
                          "两会", "台独", "台办", "国防", "解放军", "election", "president", "minister", "parliament", "congress",
                          "senate", "government", "white house", "policy", "vote", "prime minister"]),
    ("world", "国际", ["中美", "中朝", "中日", "中俄", "中欧", "缅北", "美国", "俄罗斯", "乌克兰", "以色列", "伊朗", "巴勒斯坦", "加沙", "朝鲜", "韩国", "日本",
                       "欧盟", "英国", "法国", "德国", "印度", "联合国", "北约", "特朗普", "普京", "泽连斯基",
                       "外长", "总统", "首相", "大选", "关税", "停火", "空袭", "war", "ukraine", "russia", "israel",
                       "gaza", "iran", "china", "un", "nato", "trump", "putin", "ceasefire", "strike", "troops"]),
    ("sports", "体育", ["足球", "篮球", "nba", "cba", "世界杯", "奥运", "冠军", "比赛", "联赛", "国足", "中超",
                        "网球", "乒乓", "羽毛球", "排球", "马拉松", "全运会", "球队", "球员", "夺冠", "s16",
                        "欧冠", "英超", "西甲", "巴萨", "皇马", "曼联", "斯诺克", "武网", "退赛", "f1", "郑钦文",
                        "英雄联盟", "电竞", "football", "soccer", "olympic", "tennis", "cup", "league", "match"]),
    ("ent", "娱乐", ["明星", "电影", "电视剧", "综艺", "演唱会", "官宣", "恋情", "嘉宾", "歌手",
                     "演员", "导演", "票房", "热播", "剧", "首映", "粉丝", "出道", "爆料", "红毯",
                     "film", "movie", "music", "singer", "actor", "actress", "celebrity", "album"]),
    ("finance", "财经", ["股市", "股价", "股票", "a股", "港股", "美股", "基金", "央行", "降息", "加息", "利率", "汇率", "人民币",
                         "楼市", "房价", "房贷", "gdp", "cpi", "经济", "财报", "营收", "利润", "上市", "ipo",
                         "黄金", "油价", "市值", "亿元", "万亿", "消费", "关税", "market", "stock", "economy",
                         "inflation", "fed", "rate", "bank", "tariff", "dollar", "shares", "investor"]),
    ("tech", "科技", ["ai", "人工智能", "大模型", "芯片", "华为", "苹果", "iphone", "小米", "特斯拉", "手机",
                      "deepseek", "openai", "chatgpt", "机器人", "航天", "卫星", "火箭", "新能源", "电动车",
                      "汽车", "鸿蒙", "5g", "科技", "互联网", "app", "算法", "spacex", "nasa", "tech",
                      "google", "apple", "microsoft", "nvidia", "robot", "chip", "software"]),
    ("society", "社会", []),  # 兜底
]
CAT_NAME = {k: n for k, n, _ in CATEGORIES}

# 英文关键词按单词边界匹配（避免 "ai" 命中 "said"），中文按子串匹配
CAT_RE = [(key, re.compile("|".join(
             rf"\b{re.escape(w.strip())}\b" if w.isascii() else re.escape(w) for w in words)))
          for key, _, words in CATEGORIES if words]

def categorize(title, summary="", default="society"):
    # 先只看标题，标题判断不出来再带上摘要
    for text in (title, title + " " + summary):
        t = text.lower()
        for key, pattern in CAT_RE:
            if pattern.search(t):
                return key
    return default

# ── 工具 ──────────────────────────────────────────────────────────────────────

def fetch(url, headers=None, data=None, timeout=12):
    req = urllib.request.Request(url, headers={**UA, **(headers or {})}, data=data)
    return urllib.request.urlopen(req, timeout=timeout).read()

def fetch_json(url, **kw):
    return json.loads(fetch(url, **kw))

def clean(text, n=160):
    text = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()
    return (text[:n] + "…") if len(text) > n else text

def to_int(v):
    try:
        return int(float(re.sub(r"[^\d.]", "", str(v)) or 0))
    except ValueError:
        return 0

def fmt_hot(n):
    if not n:
        return ""
    if n >= 1e8:
        return f"{n / 1e8:.1f}亿"
    if n >= 1e4:
        return f"{n / 1e4:.1f}万"
    return str(n)

def item(rank, title, url, hot=0, hot_text=None, label="", image=None, summary="", region="cn"):
    title = clean(title, 120)
    return {
        "rank":     rank,
        "title":    title,
        "url":      url or "",
        "hot":      hot,
        "hot_text": hot_text if hot_text is not None else fmt_hot(hot),
        "label":    label,          # 新 / 热 / 沸 / 爆 …
        "image":    image or None,
        "summary":  clean(summary),
        "category": categorize(title, clean(summary), "world" if region == "intl" else "society"),
    }

# ── 国内平台 ──────────────────────────────────────────────────────────────────

WEIBO_LABEL = {"新": "新", "热": "热", "沸": "沸", "爆": "爆", "暖": "暖", "商": None, "荐": None}

def weibo(limit=50):
    # 官方 ajax 接口对游客 403，改为：拿游客 SUB Cookie → 解析 s.weibo.com 热搜页
    raw = fetch("https://passport.weibo.com/visitor/genvisitor2",
                data=b"cb=visitor_gray_callback&tid=&from=weibo").decode()
    sub = re.search(r'"sub":"([^"]+)"', raw).group(1)
    page = fetch("https://s.weibo.com/top/summary", headers={"Cookie": f"SUB={sub}"}).decode()
    rows = re.findall(r'<td class="td-01 ranktop[^"]*">(\d+)</td>\s*<td class="td-02">\s*'
                      r'<a href="([^"]+)"[^>]*>([^<]+)</a>\s*(?:<span>([^<]*)</span>)?\s*</td>\s*'
                      r'<td class="td-03">(.*?)</td>', page, re.S)
    out = []
    for rank, href, title, hot, tag in rows[:limit]:
        label = WEIBO_LABEL.get(clean(tag), "") if clean(tag) else ""
        if label is None:  # 商业推广
            continue
        out.append(item(int(rank), title, "https://s.weibo.com" + href, to_int(hot), label=label))
    return out

def douyin(limit=50):
    data = fetch_json("https://www.iesdouyin.com/web/api/v2/hotsearch/billboard/word/")
    label_map = {1: "新", 3: "热", 4: "首发", 5: "首发", 8: "独家", 16: "辟谣"}
    return [item(i + 1, w["word"], "https://www.douyin.com/search/" + urllib.parse.quote(w["word"]),
                 w.get("hot_value", 0), label=label_map.get(w.get("label"), ""))
            for i, w in enumerate(data.get("word_list", [])[:limit])]

def toutiao(limit=50):
    data = fetch_json("https://www.toutiao.com/hot-event/hot-board/?origin=toutiao_pc")
    label_map = {"hot": "热", "new": "新", "refuteRumors": "辟谣", "interpretation": "解读", "boom": "爆"}
    return [item(i + 1, x["Title"], x["Url"].split("?")[0], to_int(x.get("HotValue")),
                 label=label_map.get(x.get("Label"), ""), image=(x.get("Image") or {}).get("url"))
            for i, x in enumerate(data.get("data", [])[:limit])]

def baidu(limit=50):
    data = fetch_json("https://top.baidu.com/api/board?platform=wise&tab=realtime")
    words = data["data"]["cards"][0]["content"][0]["content"]
    tag_map = {"1": "新", "3": "热", "5": "沸"}
    out = []
    for x in words:
        if x.get("isTop"):
            continue
        out.append(item(len(out) + 1, x["word"],
                        "https://www.baidu.com/s?wd=" + urllib.parse.quote(x["word"]),
                        label=tag_map.get(str(x.get("hotTag", "")), ""), hot_text=""))
        if len(out) >= limit:
            break
    return out

def zhihu(limit=50):
    data = fetch_json("https://api.zhihu.com/topstory/hot-lists/total?limit=50")
    out = []
    for i, x in enumerate(data.get("data", [])[:limit]):
        t = x["target"]
        qid = t.get("id") or t["url"].rsplit("/", 1)[-1]
        detail = x.get("detail_text", "")
        hot = to_int(detail) * (10000 if "万" in detail else 1)
        thumb = next((c.get("thumbnail") for c in x.get("children", []) if c.get("thumbnail")), None)
        out.append(item(i + 1, t["title"], f"https://www.zhihu.com/question/{qid}", hot,
                        summary=t.get("excerpt", ""), image=thumb))
    return out

def bilibili(limit=30):
    data = fetch_json("https://api.bilibili.com/x/web-interface/ranking/v2?rid=0&type=all")
    if data.get("code") != 0:
        raise RuntimeError(f"[Bilibili] ranking code={data.get('code')} message={data.get('message')}")
    return [item(i + 1, x["title"], f"https://www.bilibili.com/video/{x['bvid']}",
                 x["stat"]["view"], hot_text=fmt_hot(x["stat"]["view"]) + "播放",
                 image=x.get("pic", "").replace("http://", "https://"), summary=x.get("desc", ""))
            for i, x in enumerate(data["data"]["list"][:limit])]

def thepaper(limit=20):
    data = fetch_json("https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar")
    return [item(i + 1, x["name"], f"https://www.thepaper.cn/newsDetail_forward_{x['contId']}",
                 to_int(x.get("interactionNum")), hot_text=(x.get("interactionNum") or "") + " 评论",
                 image=x.get("pic"))
            for i, x in enumerate(data["data"].get("hotNews", [])[:limit])]

def cctv(limit=20):
    raw = fetch("https://news.cctv.com/2019/07/gaiban/cmsdatainterface/page/news_1.jsonp").decode()
    data = json.loads(raw[raw.index("(") + 1: raw.rindex(")")])
    return [item(i + 1, x["title"], x["url"], hot_text=x.get("focus_date", "")[5:16],
                 image=x.get("image"), summary=x.get("brief", ""))
            for i, x in enumerate(data["data"]["list"][:limit])]

# ── 海外媒体（RSS） ───────────────────────────────────────────────────────────

MEDIA_NS = "{http://search.yahoo.com/mrss/}"

def rss(url, limit=20):
    def run():
        root = ET.fromstring(fetch(url))
        out = []
        for i, it in enumerate(root.iter("item")):
            if i >= limit:
                break
            img = None
            for tag in ("thumbnail", "content"):
                el = it.find(MEDIA_NS + tag)
                if el is not None and el.get("url"):
                    img = el.get("url")
                    break
            title = it.findtext("title", "")
            pub = it.findtext("pubDate", "")
            out.append(item(i + 1, title, it.findtext("link", ""), hot_text=pub[5:22] if pub else "",
                            image=img, summary=it.findtext("description", ""), region="intl"))
        return out
    return run

# id, 名称, 地区, 类型, 头像缩写, 主题色, 抓取函数
SOURCES = [
    ("weibo",    "微博热搜",   "cn",   "social", "微", "#ff8200", weibo),
    ("douyin",   "抖音热榜",   "cn",   "social", "抖", "#fe2c55", douyin),
    ("toutiao",  "今日头条",   "cn",   "news",   "头", "#f04142", toutiao),
    ("baidu",    "百度热搜",   "cn",   "social", "百", "#2932e1", baidu),
    ("zhihu",    "知乎热榜",   "cn",   "social", "知", "#0066ff", zhihu),
    ("bilibili", "B站热门",    "cn",   "social", "B",  "#fb7299", bilibili),
    ("thepaper", "澎湃新闻",   "cn",   "news",   "澎", "#00a0e9", thepaper),
    ("cctv",     "央视新闻",   "cn",   "news",   "央", "#c4161c", cctv),
    ("bbc",      "BBC World",  "intl", "news",   "BBC", "#bb1919", rss("https://feeds.bbci.co.uk/news/world/rss.xml")),
    ("nyt",      "NYTimes",    "intl", "news",   "NYT", "#5a5a5a", rss("https://rss.nytimes.com/services/xml/rss/nyt/World.xml")),
    ("guardian", "The Guardian", "intl", "news", "G",  "#052962", rss("https://www.theguardian.com/world/rss")),
    ("aljazeera", "Al Jazeera", "intl", "news",  "AJ", "#fa9000", rss("https://www.aljazeera.com/xml/rss/all.xml")),
    ("gnews",    "Google News", "intl", "news",  "GN", "#4285f4", rss("https://news.google.com/rss?hl=en-US&gl=US&ceid=US:en")),
]

# ── 跨平台事件聚合 ─────────────────────────────────────────────────────────────

def norm(title):
    t = re.sub(r"[#【】\[\]「」『』“”\"'‘’《》（）()：:，,。.！!？?、\s·|_\-—…]", "", title.lower())
    return t

def bigrams(s):
    return {s[i:i + 2] for i in range(len(s) - 1)} if len(s) > 1 else {s}

def similar(a, b):
    if not a or not b:
        return False
    if len(a) >= 4 and len(b) >= 4 and (a in b or b in a):
        return True
    ga, gb = bigrams(a), bigrams(b)
    inter = len(ga & gb)
    ratio = inter / min(len(ga), len(gb))
    return (inter >= 3 and ratio >= 0.6) or (inter >= 5 and ratio >= 0.4)

def build_events(sources):
    """把不同平台上标题相近的条目合并成一个事件（仅国内平台，中文标题）。"""
    entries = []
    for s in sources:
        if s["region"] != "cn" or s["id"] == "bilibili":  # B站视频标题不适合做事件合并
            continue
        n = max(len(s["items"]), 1)
        for it in s["items"]:
            entries.append((s["id"], it, norm(it["title"]), 1 - (it["rank"] - 1) / n))
    parent = list(range(len(entries)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            if entries[i][0] != entries[j][0] and similar(entries[i][2], entries[j][2]):
                parent[find(i)] = find(j)

    groups = {}
    for i, e in enumerate(entries):
        groups.setdefault(find(i), []).append(e)

    events = []
    for members in groups.values():
        platforms = {}
        for sid, it, _, w in members:  # 同一平台只保留排名最高的那条
            if sid not in platforms or it["rank"] < platforms[sid]["rank"]:
                platforms[sid] = {"source": sid, "rank": it["rank"], "url": it["url"],
                                  "title": it["title"], "weight": w}
        refs = sorted(platforms.values(), key=lambda r: r["rank"])
        lead = max(members, key=lambda m: m[3])[1]  # 用权重最高的条目作代表
        score = sum(r["weight"] for r in refs) + 0.6 * (len(refs) - 1)
        events.append({
            "title":     lead["title"],
            "category":  lead["category"],
            "image":     next((m[1]["image"] for m in members if m[1]["image"]), None),
            "summary":   next((m[1]["summary"] for m in members if m[1]["summary"]), ""),
            "score":     round(score, 3),
            "platforms": [{k: r[k] for k in ("source", "rank", "url", "title")} for r in refs],
        })
    events.sort(key=lambda e: (-len(e["platforms"]), -e["score"]))
    return events

# ── 主流程 ────────────────────────────────────────────────────────────────────

def run_source(spec):
    sid, name, region, kind, abbr, color, fn = spec
    src = {"id": sid, "name": name, "region": region, "kind": kind, "abbr": abbr, "color": color,
           "ok": True, "error": "", "items": []}
    try:
        src["items"] = fn()
    except Exception as e:
        src["ok"], src["error"] = False, f"{type(e).__name__}: {e}"[:200]
    print(f"  {'✓' if src['ok'] else '✗'} {name:<12} {len(src['items']):>3} {src['error']}")
    return src

def main():
    print("→ 抓取热榜")
    with ThreadPoolExecutor(max_workers=8) as pool:
        sources = list(pool.map(run_source, SOURCES))

    # 某个来源本次失败时，沿用上一次的数据，避免页面上出现空卡片
    if OUT.exists():
        try:
            prev = {s["id"]: s for s in json.loads(OUT.read_text())["sources"]}
            for s in sources:
                if not s["items"] and prev.get(s["id"], {}).get("items"):
                    s["items"] = prev[s["id"]]["items"]
                    s["stale"] = True
                    s["updated"] = prev[s["id"]].get("updated")
        except Exception:
            pass

    now = datetime.now(CST)
    for s in sources:
        s.setdefault("updated", now.isoformat(timespec="seconds"))
    events = build_events(sources)
    data = {
        "updated":    now.isoformat(timespec="seconds"),
        "categories": [{"id": k, "name": n} for k, n, _ in CATEGORIES],
        "sources":    sources,
        "events":     events[:200],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    ok = sum(s["ok"] for s in sources)
    multi = sum(len(e["platforms"]) > 1 for e in events)
    print(f"→ 完成：{ok}/{len(sources)} 个来源成功，{sum(len(s['items']) for s in sources)} 条，"
          f"{multi} 个跨平台事件 → {OUT.name}")

if __name__ == "__main__":
    main()
