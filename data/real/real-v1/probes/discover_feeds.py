import asyncio
from pathlib import Path

from bs4 import BeautifulSoup

from omnistream.eval.real.collect import PublicHTTP


async def main():
 h=PublicHTTP(Path('data/real/real-v1/http'))
 for u in ['https://home.treasury.gov/news/press-releases','https://www.fdic.gov/news/press-releases','https://www.nasa.gov/nasa-brand-center/images-and-media/']:
  try:
   r=await h.get(u);s=BeautifulSoup(r.content,'html.parser');print(u,[(a.get('href'),a.get_text(' ',strip=True)[:50]) for a in s.find_all(['link','a'],href=True) if any(x in a['href'].lower() for x in ['rss','feed','xml'])],flush=True)
  except (ValueError,PermissionError,OSError) as e:print(u,type(e).__name__,str(e)[:150],flush=True)
 await h.close()
asyncio.run(main())
