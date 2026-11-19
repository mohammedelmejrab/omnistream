import asyncio
import sys

import feedparser
import httpx

sys.stdout.reconfigure(encoding='utf8')
URLS=['https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100003114','https://finance.yahoo.com/rss/headline?s=NVDA,MSFT,GOOG,AMD,INTC,IBM','https://research.google/blog/using-wearables-to-enable-cardiovascular-kidney-metabolic-ckm-risk-profiling-for-personalized-coaching/','https://news.samsung.com/global/feed','https://www.ibm.com/legal','https://www.microsoft.com/en-us/legal/terms-of-use','https://bair.berkeley.edu/robots.txt']
async def main():
 async with httpx.AsyncClient(headers={'User-Agent':'omnistream-research/0.1 (local academic project)'},follow_redirects=True) as c:
  for u in URLS:
   try:
    r=await c.get(u,timeout=25);f=feedparser.parse(r.content)
    import hashlib
    import re
    from pathlib import Path

    from bs4 import BeautifulSoup
    t=BeautifulSoup(r.text,'html.parser').get_text(' ',strip=True)
    (Path('data/real/real-v1/policy-review')/(hashlib.sha256(u.encode()).hexdigest()[:12]+'.txt')).write_text(u+'\n'+t,encoding='utf8')
    print(u,r.status_code,len(f.entries),flush=True)
    if f.entries: print([(e.get('title','')[:90],e.get('published',''),len(e.get('summary','')),len(e.get('content',[{}])[0].get('value',''))) for e in f.entries[:2]],flush=True)
    else: print([t[max(0,m.start()-70):m.end()+250] for m in list(re.finditer(r'non-commercial|noncommercial|scraping|robot|automated|Creative Commons|CC BY',t,re.IGNORECASE))[-8:]],flush=True)
   except Exception as e: print(type(e).__name__,flush=True)
   await asyncio.sleep(3)
asyncio.run(main())
