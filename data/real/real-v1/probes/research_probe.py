import asyncio
from pathlib import Path

from omnistream.eval.real.collect import PublicHTTP


async def main():
 h=PublicHTTP(Path('data/real/real-v1/http'))
 for u in ['https://rss.arxiv.org/rss/cs.AI','https://developer.nvidia.com/blog/feed/','https://blog.ml.cmu.edu/feed/']:
  try:
   r=await h.get(u);import feedparser;f=feedparser.parse(r.content)
   print(u,r.status_code,len(f.entries),[(e.get('title','')[:70],e.get('published',''),len(e.get('summary','')),len(e.get('content',[{}])[0].get('value',''))) for e in f.entries[:2]],flush=True)
  except (ValueError,PermissionError,OSError) as e: print(type(e).__name__,str(e)[:150],flush=True)
 await h.close()
asyncio.run(main())
