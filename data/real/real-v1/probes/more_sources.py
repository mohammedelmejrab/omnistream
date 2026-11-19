import asyncio
import re
import sys
from pathlib import Path

import feedparser
import httpx
from bs4 import BeautifulSoup

sys.stdout.reconfigure(encoding='utf8')
URLS=['https://www.amd.com/en/corporate/copyright','https://blogs.microsoft.com/terms-of-use/','https://aws.amazon.com/terms/','https://newsroom.ibm.com/terms','https://ir.amd.com/news-events/press-releases/rss','https://nvidianews.nvidia.com/rss','https://blogs.microsoft.com/blog/tag/earnings/feed/','https://newsroom.ibm.com/announcements?pagetemplate=rss&item_count=100','https://bair.berkeley.edu/blog/feed.xml','https://research.google/blog/rss/']
async def main():
 async with httpx.AsyncClient(headers={'User-Agent':'omnistream-research/0.1 (local academic project)'},follow_redirects=True) as c:
  for u in URLS:
   try:
    r=await c.get(u,timeout=20);f=feedparser.parse(r.content)
    p=Path('data/real/real-v1/policy-review');import hashlib
    (p/(hashlib.sha256(u.encode()).hexdigest()[:12]+'.txt')).write_text(u+'\n'+BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True),encoding='utf8')
    print(u,r.status_code,len(f.entries),flush=True)
    if f.entries: print(str(f.entries[0])[:2500],flush=True)
    else:
     t=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
     print([t[max(0,m.start()-70):m.end()+400] for m in list(re.finditer(r'non-commercial|noncommercial|scrap|robot|automated|permission to use',t,re.IGNORECASE))[-8:]],flush=True)
   except Exception as e: print(type(e).__name__,str(e)[:50],flush=True)
   await asyncio.sleep(3)
asyncio.run(main())
