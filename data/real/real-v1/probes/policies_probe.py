import asyncio

import httpx

HOSTS=['https://blogs.nvidia.com','https://blogs.microsoft.com','https://blog.google','https://nvidianews.nvidia.com','https://ir.amd.com','https://www.intc.com','https://research.google','https://www.microsoft.com','https://huggingface.co','https://export.arxiv.org','https://aws.amazon.com','https://newsroom.ibm.com','https://news.mit.edu']
async def main():
 async with httpx.AsyncClient(headers={'User-Agent':'omnistream-research/0.1 (local academic project)'},follow_redirects=True) as c:
  for h in HOSTS:
   try:
    r=await c.get(h+'/robots.txt',timeout=20)
    print(h,r.status_code,r.text[:10000],flush=True)
   except Exception as e: print(h,type(e).__name__,flush=True)
asyncio.run(main())
