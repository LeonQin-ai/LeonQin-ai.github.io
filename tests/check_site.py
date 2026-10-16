"""Check generated documents, internal URLs, feeds and article completeness."""
from html.parser import HTMLParser
import ast
import json
from markdown_it import MarkdownIt
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
SITE=ROOT/'_site'
posts=json.loads((ROOT/'content/posts.json').read_text(encoding='utf-8'))

class Document(HTMLParser):
    def __init__(self,text):
        super().__init__(convert_charrefs=True)
        self.ids=set();self.links=[];self.h1=0;self.canonical=[];self.meta={};self.scripts=[]
        self.feed(text)
    def handle_starttag(self,tag,attrs):
        data=dict(attrs)
        if 'id' in data:
            assert data['id'] not in self.ids,('Duplicate ID',data['id'])
            self.ids.add(data['id'])
        if tag=='h1':self.h1+=1
        for key in ('href','src'):
            if key in data:self.links.append(data[key])
        if tag=='link' and data.get('rel')=='canonical':self.canonical.append(data['href'])
        if tag=='meta':self.meta[data.get('name',data.get('property'))]=data.get('content','')

docs={path:Document(path.read_text(encoding='utf-8')) for path in SITE.rglob('*.html')}
assert len(posts)==8 and len(docs)==len(posts)+2,(len(posts),len(docs))
checked=0
for path,doc in docs.items():
    assert doc.h1==1 and len(doc.canonical)==1,(path,'Missing unique heading/canonical')
    assert doc.meta.get('description') and doc.meta.get('og:image'),path
    for target in doc.links:
        url=urlsplit(target)
        if url.scheme or url.netloc:continue
        rel=unquote(url.path)
        dest=SITE/rel.lstrip('/') if rel.startswith('/') else path.parent/rel
        if not rel:dest=path
        if dest.is_dir():dest=dest/'index.html'
        assert dest.exists(),(path.relative_to(SITE),target)
        if url.fragment:
            assert dest in docs and unquote(url.fragment) in docs[dest].ids,(path,target,'Missing fragment')
        checked+=1
for post in posts:
    html=(SITE/'articles'/post['slug']/'index.html').read_text(encoding='utf-8')
    assert len(html)>7000 and 'article-main' in html and '文章目录' in html,post['slug']
    assert 'href="'+post['file']+'"' not in html,post['slug']
feed=ET.parse(SITE/'feed.xml')
assert len(feed.findall('./channel/item'))==len(posts)
sitemap=ET.parse(SITE/'sitemap.xml')
assert len(sitemap.findall('{*}url'))==len(posts)+1
assert (SITE/'assets/og-cover.png').is_file()
assert (SITE/'.nojekyll').is_file()
print(f'PASS: {len(docs)} HTML documents, {checked} internal links/anchors, 8 complete articles, SEO, RSS and sitemap')

examples=0
for post in posts:
    source=(ROOT/'content'/post['file']).read_text(encoding='utf-8')
    for token in MarkdownIt().parse(source):
        if token.type!='fence':continue
        if token.info.strip()=='python':
            ast.parse(token.content,filename=post['file'])
            examples+=1
        elif token.info.strip()=='json':
            json.loads(token.content)
            examples+=1
print(f'PASS: {examples} Python/JSON article examples parse successfully')
