"""Screenshots of v2 panels at several sizes for a visual check."""
import asyncio, sys
from playwright.async_api import async_playwright
from harness import *

async def main():
    async with async_playwright() as p:
        br = await launch(p)
        for (w, h, mob) in ((1280, 720, False), (915, 412, True), (412, 915, True), (1920, 1080, False)):
            ctx, page = await open_game(br, Net(), w, h, mobile=mob, dpr=1)
            await page.click('#btn-pointer')
            await page.evaluate("__FS.manual(true)")
            await page.evaluate("__FS.tick(1/60, 30)")
            await page.screenshot(path=f'{OUT}/shot_{w}x{h}_menu.png')
            await page.click('#btn-settings')
            await page.screenshot(path=f'{OUT}/shot_{w}x{h}_settings.png')
            await page.click('#settings-done')
            await page.click('#btn-progress')
            await page.screenshot(path=f'{OUT}/shot_{w}x{h}_progress.png')
            await page.click('#progress-done')
            await page.evaluate("__FS.start('arcade'); __FS.tick(1/60, 120); __FS.power('freeze'); __FS.power('double'); __FS.tick(1/60, 60); __FS.pause()")
            await page.screenshot(path=f'{OUT}/shot_{w}x{h}_pause.png')
            await page.evaluate("__FS.resume(); __FS.tick(1/60, 30)")
            await page.screenshot(path=f'{OUT}/shot_{w}x{h}_arcade.png')
            await ctx.close()
        await br.close()
asyncio.run(main())
