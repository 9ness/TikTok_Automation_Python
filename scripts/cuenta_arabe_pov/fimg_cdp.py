"""fimg_cdp.py <prompt.txt> <ref.jpg>... — como fimg.py pero por CDP directo. GO=1 envía."""
import json,asyncio,os,sys,re
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
from flowlib import *
ptxt,refs=sys.argv[1],sys.argv[2:]
prompt=open(ptxt,encoding='utf-8').read().strip()
NING="document.querySelectorAll(\"button[aria-label='Ingrediente']\").length"
async def m():
    async with TabEv() as t:
        await t.cmd('Page.bringToFront'); await t.cmd('Page.enable')
        await tecla(t,'Escape',vk=27); await asyncio.sleep(0.5)
        if '/edit/' in await t.js('location.href'):
            await t.js('history.back()'); await asyncio.sleep(3)
        while await t.js("!!document.querySelector(\"button[aria-label='Borrar petición']\")"):
            await clic(t,q("button[aria-label='Borrar petición']")); await asyncio.sleep(0.8)
        for f in refs:
            buscar=os.path.splitext(os.path.basename(f))[0]; nom=buscar+'.jpg'
            antes=await t.js(NING)
            await clic(t,"document.querySelector(\"button[aria-label^='Añadir ingredientes']\")"); await asyncio.sleep(1.5)
            SB="document.querySelector(\"input[placeholder='Buscar recursos']\")"
            async def buscar_item():
                await clic(t,SB); await t.js(f"{SB}.select()"); await t.cmd('Input.insertText',text=buscar); await asyncio.sleep(2)
                return await t.js(f"!!({txt(nom)})")
            if not await buscar_item():
                await t.cmd('Page.setInterceptFileChooserDialog',enabled=True)
                await clic(t,"[...document.querySelectorAll('span')].filter(e=>e.offsetParent&&/^Subir archivo/.test(e.innerText.trim())).pop()")
                ev=await t.evento('Page.fileChooserOpened',15)
                assert ev,'no salió el selector de ficheros'
                await t.cmd('DOM.setFileInputFiles',files=[os.path.abspath(f)],backendNodeId=ev['backendNodeId'])
                await t.cmd('Page.setInterceptFileChooserDialog',enabled=False)
                await asyncio.sleep(12)
                assert await buscar_item(),f'no aparece {nom} tras subirlo'
            await clic(t,txt(nom)); await asyncio.sleep(1.2)
            if await t.js(NING)==antes:
                await clic(t,txt('Añadir a petición')); await asyncio.sleep(1.5)
            await tecla(t,'Escape',vk=27); await asyncio.sleep(0.5)
            if await t.js(NING)!=antes+1:
                await t.shot('/tmp/flowerr.png'); print('ERROR no se adjuntó',nom); sys.exit(4)
        await clic(t,"[...document.querySelectorAll('[contenteditable=true]')].pop()")
        await t.cmd('Input.insertText',text=prompt); await asyncio.sleep(0.8)
        s=await t.js("document.querySelector(\"button[aria-label='Activador de ajustes']\").innerText")
        print('ajustes:',s.replace('\n',' '))
        assert 'Nano Banana' in s,'Flow no está en imagen Nano Banana'
        if os.getenv('GO')=='1':
            # snap AQUÍ: las refs recién subidas también salen por flow-content.google y fwait las cogería
            await asyncio.sleep(3)
            js_ids=r'''JSON.stringify([...document.querySelectorAll('img[src*="flow-content.google/image/"]')].map(i=>(i.src.match(/\/image\/([0-9a-f-]+)/)||[])[1]))'''
            json.dump(json.loads(await t.js(js_ids)),open(os.path.join(os.path.dirname(os.path.abspath(__file__)),'snap.json'),'w'))
            await clic(t,q("button[aria-label='Iniciar generación']")); print('enviado')
        await t.shot('/tmp/flowpre.png')
asyncio.run(m())
