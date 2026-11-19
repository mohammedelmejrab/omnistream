import asyncio

import feedparser
import httpx

URLS = [
'https://blogs.nvidia.com/feed/', 'https://blogs.microsoft.com/feed/',
'https://blog.google/rss/', 'https://newsroom.intel.com/feed/',
'https://nvidianews.nvidia.com/releases.xml', 'https://ir.amd.com/news-events/press-releases/rss',
'https://www.intc.com/news-events/press-releases/rss', 'https://feeds.feedburner.com/microsoft/presspass',
'https://research.google/blog/rss/', 'https://www.microsoft.com/en-us/research/feed/',
'https://huggingface.co/blog/feed.xml','https://export.arxiv.org/api/query?search_query=cat:cs.AI&start=0&max_results=5&sortBy=submittedDate&sortOrder=descending',
]
async def main():
 async with httpx.AsyncClient(headers={'User-Agent':'omnistream-research/0.1 (local academic project)'},follow_redirects=True) as c:
  for u in URLS:
   try:
    r=await c.get(u,timeout=30); f=feedparser.parse(r.content)
    print(r.status_code,u,len(f.entries),[(e.get('title','')[:70],e.get('published',e.get('updated','')),len(e.get('summary','')),len(e.get('content',[{}])[0].get('value',''))) for e in f.entries[:2]],flush=True)
   except Exception as e: print(type(e).__name__,u,flush=True)
   await asyncio.sleep(3)
asyncio.run(main())
