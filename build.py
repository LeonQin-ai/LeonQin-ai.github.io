"""Build a complete, portable static blog from version-controlled Markdown."""
from __future__ import annotations

from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlsplit
from xml.etree import ElementTree as ET

from markdown_it import MarkdownIt

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_site"
SITE = "https://leonqin-ai.github.io"
REPO = "https://github.com/LeonQin-ai/LeonQin-ai.github.io"
PROJECT = "https://github.com/LeonQin-ai/cognitive-os-agent"
BRAND = "Leon Qin · 工程笔记"
DESCRIPTION = "从源码出发，记录 AI 与系统工程。Cognitive OS 的架构、多 Agent 协作、记忆、工具执行与实测。"
POSTS = json.loads((ROOT / "content/posts.json").read_text(encoding="utf-8"))
SLUGS = {post["file"]: post["slug"] for post in POSTS}


def href(post):
    return f'/articles/{post["slug"]}/'


def icon(name):
    paths = {
        "arrow": '<path d="M5 12h14m-6-6 6 6-6 6"/>',
        "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
        "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
        "rss": '<path d="M4 11a9 9 0 0 1 9 9M4 4a16 16 0 0 1 16 16"/><circle cx="5" cy="19" r="1"/>',
        "external": '<path d="M14 4h6v6m0-6L10 14M10 4H4v16h16v-6"/>',
    }
    return f'<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{paths[name]}</svg>'


def head(title, description, path, schema):
    canonical = SITE + path
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><meta name="description" content="{escape(description, quote=True)}">
<link rel="canonical" href="{canonical}"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml">
<link rel="alternate" type="application/rss+xml" title="{BRAND}" href="/feed.xml">
<meta name="color-scheme" content="light dark"><meta name="theme-color" content="#f5f4ef">
<meta property="og:site_name" content="{BRAND}"><meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{escape(title, quote=True)}"><meta property="og:description" content="{escape(description, quote=True)}">
<meta property="og:url" content="{canonical}"><meta property="og:type" content="{'article' if path.startswith('/articles/') else 'website'}">
<meta property="og:image" content="{SITE}/assets/og-cover.png"><meta name="twitter:card" content="summary_large_image">
<script>try{{const t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme: dark)').matches))document.documentElement.dataset.theme='dark';}}catch(e){{}}</script>
<link rel="stylesheet" href="/assets/site.css"><script src="/assets/site.js" defer></script>
<script type="application/ld+json">{json.dumps(schema, ensure_ascii=False).replace('</', '<\\/')}</script>
</head><body><a class="skip-link" href="#main">跳到正文</a>'''


def header(article=False):
    return f'''<header class="site-header"><div class="header-inner">
<a class="brand" href="/" aria-label="Leon Qin 工程笔记首页"><span class="brand-mark" aria-hidden="true">lq<span>·</span></span><span>Leon Qin<small>工程笔记</small></span></a>
<nav aria-label="主导航"><a href="/#writing"{' aria-current="page"' if article else ''}>文章</a><a href="/#about">关于</a><a class="rss-link" href="/feed.xml">RSS {icon('rss')}</a><button class="theme-toggle" type="button" aria-label="切换深浅主题" title="切换深浅主题">{icon('sun')}</button><a class="nav-github" href="{REPO}">GitHub {icon('external')}</a></nav>
</div></header>'''


def footer():
    return f'''<footer class="site-footer"><div><a class="footer-brand" href="/">Leon Qin · 工程笔记</a><p>记录实现，也记录边界。让每一个结论都有出处。</p></div><div class="footer-links"><a href="{PROJECT}">Cognitive OS {icon('external')}</a><a href="{REPO}">网站源码 {icon('external')}</a><a href="/feed.xml">RSS 订阅 {icon('rss')}</a><span>© 2026 Leon Qin</span></div></footer><button class="back-top" aria-label="回到顶部" hidden>↑</button></body></html>'''


def write(path, text):
    dest = OUT / path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")


def load_posts():
    for index, post in enumerate(POSTS, 1):
        text = (ROOT / "content" / post["file"]).read_text(encoding="utf-8")
        lines = text.splitlines()
        if not lines or not lines[0].startswith("# "):
            raise ValueError(f'Missing article title: {post["file"]}')
        post["full_title"] = lines[0][2:].strip()
        post["body"] = "\n".join(lines[1:]).strip()
        post["minutes"] = max(3, round((len(re.findall(r'[\u4e00-\u9fff]', text)) / 340) + len(re.findall(r'\b[a-zA-Z]{3,}\b', text)) / 200))
        post["number"] = f"{index:02d}"


def card(post):
    tags = ''.join(f'<span>{escape(tag)}</span>' for tag in post['tags'])
    search = ' '.join([post['title'], post['summary'], post['category'], *post['tags']])
    return f'''<article class="post-card" data-post data-category="{post['category']}" data-search="{escape(search, quote=True)}">
<div class="card-top"><span class="post-number">{post['number']}</span><span class="category">{post['category']}</span></div>
<a class="card-title" href="{href(post)}"><h3>{escape(post['title'])}</h3></a><p>{escape(post['summary'])}</p>
<div class="card-bottom"><div class="tags">{tags}</div><span class="read-time">{post['minutes']} 分钟 {icon('arrow')}</span></div></article>'''


def build_home():
    categories = list(dict.fromkeys(post['category'] for post in POSTS))
    filters = '<button class="filter is-active" data-filter="全部" aria-pressed="true">全部文章 <span>08</span></button>'
    filters += ''.join(f'<button class="filter" data-filter="{category}" aria-pressed="false">{category}</button>' for category in categories)
    schema = {"@context":"https://schema.org", "@type":"Blog", "name":BRAND, "url":SITE + "/", "description":DESCRIPTION, "author":{"@type":"Person","name":"Leon Qin","url":"https://github.com/LeonQin-ai"}}
    html = head(BRAND + "｜AI 与系统工程", DESCRIPTION, "/", schema) + header()
    html += f'''<main id="main"><section class="hero page-width"><div class="hero-copy">
<p class="eyebrow"><span class="status-dot"></span> AI × SYSTEMS × SOURCE CODE</p>
<h1>从源码出发，<br>把 Agent 做成<span class="accent-word">系统<span class="accent-dot">。</span></span></h1>
<p class="hero-description">你好，我是 Leon。这里记录 Cognitive OS 的构建过程：<br class="desktop-break">架构怎么拆、代码怎么写、结果怎么验证。</p>
<div class="hero-actions"><a class="button button-primary" href="{href(POSTS[0])}">从第一篇读起 {icon('arrow')}</a><a class="text-link" href="{PROJECT}">探索 Cognitive OS {icon('external')}</a></div>
<div class="hero-note"><span>08 篇工程笔记</span><span>源码 · 架构 · 实测</span><span>开源，持续记录</span></div>
</div><div class="hero-visual"><div class="diagram-header"><span><i></i><i></i><i></i></span><span>cognitive-os / runtime</span><span class="diagram-badge">C11</span></div><img src="/assets/runtime-map.svg" width="540" height="395" alt="Cognitive OS 示意：请求进入调度器，由 Agent 联结记忆与上下文，执行工具并核对证据。"><div class="diagram-footer"><span class="status-dot"></span><code>reason → act → verify</code><span>把想法落实到执行。</span></div></div></section>
<section class="series-strip page-width" aria-label="系列介绍"><span class="series-label">正在连载</span><div><h2>Cognitive OS：一个 Agent Runtime 的工程实践</h2><p>从系统边界到百万任务，一起走过设计、实现与验证。</p></div><a href="#writing" aria-label="查看全部八篇文章">8 篇完整文章 {icon('arrow')}</a></section>
<section class="writing page-width" id="writing" aria-labelledby="writing-title"><div class="section-heading"><div><p class="eyebrow">THE ENGINEERING JOURNAL</p><h2 id="writing-title">工程笔记<span class="heading-dot"> / </span><span class="heading-count">08</span></h2></div><label class="search-box">{icon('search')}<input type="search" id="article-search" placeholder="搜索标题、主题…" aria-label="搜索文章" autocomplete="off"><kbd>/</kbd></label></div>
<div class="filter-bar" role="group" aria-label="按主题筛选">{filters}</div><p class="search-status" role="status" aria-live="polite"></p><div class="post-grid">{''.join(card(post) for post in POSTS)}</div><div class="empty-state" hidden><span>∅</span><h3>暂时没有找到这篇笔记</h3><p>换一个关键词，或查看全部文章。</p><button class="button button-secondary" id="clear-search">清除筛选</button></div></section>
<section class="about page-width" id="about" aria-labelledby="about-title"><div class="about-intro"><p class="eyebrow">BEHIND THE NOTES</p><h2 id="about-title">写代码，<br>也把过程写下来。</h2></div><div class="about-copy"><p>我是 Leon Qin，关注 AI 基础设施与系统工程。我在开发 <a href="{PROJECT}">Cognitive OS</a>：一个用 C11 实现的 Agent Runtime，把调度、状态、记忆、上下文与工具执行放回系统中。</p><p>这里分享源码里的设计取舍、真实问题和可复现的实验。测试数字会标明工作负载，完成记录会对应实际证据。希望这些笔记，也能成为你构建系统时的一点参考。</p><div class="about-links"><a class="text-link" href="https://github.com/LeonQin-ai">GitHub 主页 {icon('external')}</a><a class="text-link" href="/feed.xml">用 RSS 订阅 {icon('rss')}</a></div></div></section></main>'''
    write('index.html', html + footer())


def render_article(post):
    md = MarkdownIt('commonmark', {'html':False}).enable('table')
    toc = []
    tokens = md.parse(post['body'])
    for index, token in enumerate(tokens):
        if token.type == 'heading_open':
            label = tokens[index+1].content
            anchor = 'h-' + re.sub(r'[^\w-]+', '-', label).strip('-')
            if any(item[0] == anchor for item in toc): anchor += '-' + str(index)
            token.attrSet('id', anchor)
            toc.append((anchor, label, int(token.tag[1])))
    default_link = md.renderer.rules.get('link_open')

    def link_open(items, index, options, env):
        token = items[index]
        target = token.attrGet('href') or ''
        if target == 'README.md':
            token.attrSet('href', '/#writing')
        elif target.split('#')[0] in SLUGS:
            name, _, fragment = target.partition('#')
            token.attrSet('href', f'/articles/{SLUGS[name]}/' + ('#' + fragment if fragment else ''))
        elif target.startswith(('http://', 'https://')):
            token.attrSet('rel', 'noopener')
        return default_link(items, index, options, env) if default_link else md.renderer.renderToken(items, index, options, env)

    default_fence = md.renderer.rules['fence']

    def fence(items, index, options, env):
        token = items[index]
        if token.info.strip() == 'mermaid':
            dependency = 'A[阅读' in token.content
            asset = 'flow-dependency.svg' if dependency else 'flow-runtime.svg'
            alt = '先阅读，再实现与验证；独立文档核对分支与验证结果汇入最终整理。' if dependency else '请求经调度、推理、规划、工具执行与校验形成闭环，并记录执行结果。'
            return f'<figure class="article-diagram"><img src="/assets/{asset}" alt="{alt}" loading="lazy"><figcaption>{alt}</figcaption><details><summary>查看图示源码</summary><pre><code>{escape(token.content)}</code></pre></details></figure>'
        return default_fence(items, index, options, env)

    md.renderer.rules['link_open'] = link_open
    md.renderer.rules['fence'] = fence
    body = md.renderer.render(tokens, md.options, {})
    # Tables remain real tables; the wrapper contains horizontal scrolling.
    body = body.replace('<table>', '<div class="table-scroll"><table>').replace('</table>', '</table></div>')
    toc_html = ''.join(f'<a class="toc-level-{level}" href="#{escape(anchor, quote=True)}">{escape(label)}</a>' for anchor, label, level in toc)
    schema = {"@context":"https://schema.org", "@type":"BlogPosting", "headline":post['full_title'], "description":post['summary'], "datePublished":post['date'], "author":{"@type":"Person","name":"Leon Qin","url":"https://github.com/LeonQin-ai"}, "mainEntityOfPage":SITE + href(post), "image":SITE+'/assets/og-cover.png', "inLanguage":"zh-CN"}
    html = head(post['title'] + '｜' + BRAND, post['summary'], href(post), schema) + header(True)
    html += f'''<div class="reading-progress" aria-hidden="true"><span></span></div><main id="main" class="article-page page-width"><div class="article-top"><a class="breadcrumb" href="/#writing">← 全部工程笔记</a><span>Cognitive OS 系列 / {post['number']}</span></div><header class="article-header"><div class="article-eyebrow"><span class="category">{post['category']}</span><span>第 {post['number']} / 08 篇</span></div><h1>{escape(post['full_title'])}</h1><p class="article-deck">{escape(post['summary'])}</p><div class="article-meta"><span class="author-avatar">LQ</span><span>Leon Qin</span><span class="meta-divider">·</span><time datetime="{post['date']}">{post['date'].replace('-', '.')}</time><span class="meta-divider">·</span><span>约 {post['minutes']} 分钟</span></div></header>
<div class="article-layout"><div class="article-main"><details class="mobile-toc"><summary>文章目录</summary><nav aria-label="移动端文章目录">{toc_html}</nav></details><article class="prose">{body}</article><aside class="project-callout"><span class="callout-symbol">↗</span><div><h2>把阅读变成一次实验。</h2><p>Cognitive OS 的源码、测试和原始数据都在 GitHub，欢迎复现、提问与贡献。</p><a class="text-link" href="{PROJECT}">前往开源项目 {icon('external')}</a></div></aside>'''
    index = POSTS.index(post)
    previous = POSTS[index-1] if index else None
    following = POSTS[index+1] if index+1 < len(POSTS) else None
    html += '<nav class="post-navigation" aria-label="上一篇与下一篇">'
    html += f'<a href="{href(previous)}"><span>← 上一篇</span><strong>{escape(previous["title"])}</strong></a>' if previous else '<a href="/#writing"><span>回到起点</span><strong>查看全部工程笔记</strong></a>'
    html += f'<a href="{href(following)}"><span>下一篇 →</span><strong>{escape(following["title"])}</strong></a>' if following else f'<a href="{PROJECT}"><span>接下来，动手试试 ↗</span><strong>探索 Cognitive OS 源码</strong></a>'
    html += f'''</nav><div class="article-source"><a href="{REPO}/blob/main/content/{post['file']}">在 GitHub 阅读 Markdown 源文</a><a href="{REPO}/issues/new?title=文章反馈：{post['slug']}">反馈与交流 ↗</a></div></div><aside class="desktop-toc"><span class="eyebrow">IN THIS ARTICLE</span><p>本文目录</p><nav aria-label="文章目录">{toc_html}</nav><a class="toc-back" href="/#writing">← 返回系列目录</a></aside></div></main>'''
    write(f'articles/{post["slug"]}/index.html', html + footer())


def build_feeds():
    rss = ET.Element('rss', version='2.0')
    channel = ET.SubElement(rss, 'channel')
    for key, value in [('title', BRAND), ('link', SITE+'/'), ('description', DESCRIPTION), ('language', 'zh-CN')]:
        ET.SubElement(channel, key).text = value
    for post in POSTS:
        item = ET.SubElement(channel, 'item')
        for key, value in [('title',post['full_title']),('link',SITE+href(post)),('guid',SITE+href(post)),('description',post['summary']),('pubDate',format_datetime(datetime.fromisoformat(post['date']).replace(tzinfo=timezone.utc)))]:
            ET.SubElement(item,key).text=value
    write('feed.xml', '<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(rss, encoding='unicode'))
    sitemap = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')
    for path in ['/', *[href(post) for post in POSTS]]:
        node=ET.SubElement(sitemap,'url'); ET.SubElement(node,'loc').text=SITE+path
    write('sitemap.xml', '<?xml version="1.0" encoding="utf-8"?>\n'+ET.tostring(sitemap,encoding='unicode'))
    write('robots.txt', f'User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n')


def main():
    OUT.mkdir(exist_ok=True)
    shutil.copytree(ROOT/'assets', OUT/'assets', dirs_exist_ok=True)
    load_posts(); build_home()
    for post in POSTS: render_article(post)
    build_feeds()
    write('.nojekyll','')
    schema={"@context":"https://schema.org","@type":"WebPage","name":"页面未找到"}
    write('404.html',head('页面未找到｜'+BRAND,'这个链接没有对应的文章。','/404.html',schema)+header()+f'<main id="main" class="not-found page-width"><p class="eyebrow">404 / PAGE NOT FOUND</p><h1>这页笔记还没写。</h1><p>或许链接发生了变化，从文章目录重新出发吧。</p><a class="button button-primary" href="/#writing">返回文章目录 {icon("arrow")}</a></main>'+footer())
    print(f'Built homepage, {len(POSTS)} articles, 404, RSS and sitemap in {OUT}')


if __name__ == '__main__':
    main()
