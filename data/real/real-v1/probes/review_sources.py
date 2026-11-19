import asyncio
from pathlib import Path

import feedparser
import httpx
from bs4 import BeautifulSoup

URLS=[
'https://www.nvidia.com/en-us/about-nvidia/legal-info/','https://www.amd.com/en/legal/terms-and-conditions.html','https://www.intel.com/content/www/us/en/legal/terms-of-use.html','https://www.microsoft.com/en-us/legal/intellectualproperty/copyright','https://huggingface.co/terms-of-service','https://info.arxiv.org/help/api/tou.html',
'https://blogs.nvidia.com/feed/?paged=2','https://blogs.microsoft.com/feed/?paged=2','https://aws.amazon.com/blogs/aws/feed/', 'https://newsroom.ibm.com/announcements?pagetemplate=rss',
'https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending']
async def main():
 async with httpx.AsyncClient(headers={'User-Agent':'omnistream-research/0.1 (local academic project)'},follow_redirects=True) as c:
  for u in URLS:
   try:
    r=await c.get(u,timeout=25); f=feedparser.parse(r.content)
    t=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
    p=Path('data/real/real-v1/policy-review');p.mkdir(exist_ok=True)
    import hashlib
    (p/(hashlib.sha256(u.encode()).hexdigest()[:12]+'.txt')).write_text(u+'\n'+t,encoding='utf8')
    if f.entries: print(u,r.status_code,len(f.entries),[(e.get('title','')[:65],e.get('published',''),len(e.get('summary','')),len(e.get('content',[{}])[0].get('value',''))) for e in f.entries[:2]],flush=True)
    else:
     import re
     print(u,r.status_code, [t[max(0,m.start()-100):m.end()+300] for m in list(re.finditer('non-commercial|noncommercial|automated|scrap|robot|personal|Creative Commons|CC0',t,re.IGNORECASE))[:12]],flush=True)
   except Exception as e: print(u,type(e).__name__,flush=True)
   await asyncio.sleep(3)
asyncio.run(main())
