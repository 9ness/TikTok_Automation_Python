import json
from pathlib import Path
from playwright.sync_api import sync_playwright

def own_page(browser):
    import os;target=json.loads(Path(os.environ.get('BROWSER_JSON','browser.json')).read_text())['target_id']
    for context in browser.contexts:
        for page in context.pages:
            session=context.new_cdp_session(page)
            info=session.send('Target.getTargetInfo')['targetInfo']
            session.detach()
            if info['targetId']==target:
                return page
    raise RuntimeError('La pestaña propia no existe; no se toca ninguna otra')

if __name__=='__main__':
    import sys
    with sync_playwright() as p:
        browser=p.chromium.connect_over_cdp('http://127.0.0.1:9222')
        page=own_page(browser)
        page.set_default_timeout(10000)
        if len(sys.argv)>1 and sys.argv[1]=='frames':
            page.locator('button').filter(has_text=__import__('re').compile('^Frames$')).click()
            page.locator('button').filter(has_text=__import__('re').compile('^Portrait')).click()
        print(page.locator('body').inner_text()[:1800])
        print('inputs',page.locator('input').evaluate_all('(es)=>es.map(e=>({type:e.type,accept:e.accept}))'))
