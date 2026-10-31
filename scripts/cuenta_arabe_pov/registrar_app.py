"""Registro privado por el MCP documentado del admin; nunca publica.
Se usa /subir porque el conector no admite adjuntar un fichero local.
Las credenciales se leen en memoria y nunca se guardan ni se imprimen.
"""
import json,re,sys,time,hashlib
from pathlib import Path
from urllib.parse import urlparse
import requests
ROOT=Path.cwd()  # se ejecuta desde la carpeta de la ronda
REPO=Path.home()/'proyectos/TikTok_Automation_Python'

def endpoint():
 text=(REPO/'MCP_URLS.local.md').read_text()
 values=re.findall(r'https?://[^\s`<>]+?/api/mcp/ness\.[a-f0-9]{32}',text)
 values=[v for v in values if urlparse(v).hostname=='factory.nebulabsmedia.com']
 assert values,'No hay un acceso documentado del admin para esta app'
 return values[-1]

def decode(response):
 if response.status_code not in (200,202):raise RuntimeError(f'MCP HTTP {response.status_code}; URL y credencial omitidas')
 try:return response.json()
 except ValueError:
  for line in response.text.splitlines():
   if line.startswith('data: '):
    try:return json.loads(line[6:])
    except ValueError:pass
 raise RuntimeError('Respuesta MCP no interpretable; contenido omitido')

class Client:
 def __init__(self):
  self.base=endpoint();self.session=requests.Session();self.headers={'Accept':'application/json, text/event-stream','Content-Type':'application/json'}
  r=self.post({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'agente-hmizat-pov','version':'1.0'}}})
  if r.headers.get('Mcp-Session-Id'):self.headers['Mcp-Session-Id']=r.headers['Mcp-Session-Id']
  decode(r)
 def post(self,body):
  try:return self.session.post(self.base+'/',headers=self.headers,json=body,timeout=240)
  except requests.RequestException:raise RuntimeError('Fallo de transporte MCP; URL y credencial omitidas') from None
 def call(self,name,args):
  payload=decode(self.post({'jsonrpc':'2.0','id':int(time.time()*1000),'method':'tools/call','params':{'name':name,'arguments':args}}))
  if 'error' in payload:raise RuntimeError('Error de protocolo MCP; detalle omitido')
  result=payload.get('result',{})
  if result.get('isError'):raise RuntimeError('La herramienta MCP rechazó el registro; no se imprime la respuesta')
  text='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
  return json.loads(text)
 def upload(self,path):
  try:
   with path.open('rb') as f:r=self.session.post(self.base+'/subir',files={'file':(path.name,f,'video/mp4')},timeout=180)
  except requests.RequestException:raise RuntimeError('Fallo de transporte al adjuntar; URL y credencial omitidas') from None
  data=decode(r);assert data.get('archivo_id'),'No se recibió archivo_id';return data['archivo_id']

def register(number,replace=''):
 plan=next(r for r in json.loads((ROOT/'PLAN.json').read_text()) if r['numero']==number)
 path=ROOT/plan['archivo'];assert path.is_file()
 receipt=ROOT/'MIS_TANDAS.json';saved=json.loads(receipt.read_text()) if receipt.exists() else {'usuario':'nes_bugallo','registros':[]}
 if not replace and any(r['numero']==number for r in saved['registros']):print(f'Vídeo {number:02d} ya registrado.');return
 client=Client()
 attaches=ROOT/'ARCHIVOS_APP.json';uploads=json.loads(attaches.read_text()) if attaches.exists() else {}
 if replace or str(number) not in uploads:
  aid=client.upload(path);uploads[str(number)]={'archivo_id':aid,'reemplaza':replace,'archivo':plan['archivo'],'usuario':'ness'};attaches.write_text(json.dumps(uploads,ensure_ascii=False,indent=2))
 else:aid=uploads[str(number)]['archivo_id']
 marker=ROOT/'REGISTRO_EN_CURSO.json'
 assert not marker.exists(),'Hay un registro ambiguo: comprobar la app antes de repetir'
 marker.write_text(json.dumps({'numero':number,'archivo':plan['archivo'],'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'inicio':time.time()}))
 ve=lambda k:(ROOT/'veo'/f'{number:02d}_{k}.txt').read_text().strip()
 audio='Voz darija de Fish con subtítulos' if (ROOT/'audio'/f'{number:02d}_fish.mp3').exists() else 'Sonido comercial al subir (SUBIDA.json)'
 notes=f"Hmizat {ROOT.name} · pieza {number:02d}. Imágenes Flow Nano Banana 2 + clips GenAI Pro Veo (Frames, 1 cr). Texto en pantalla {plan['idioma_pantalla']} igual que el viral; caption y hashtags del original. {audio}. Sin publicar."
 result=client.call('registrar_replica_video',{'modo':'con_ia','titulo':plan['nombre_enlace'],'archivo_id':aid,'product_id':plan['product_id'],'url_viral':plan['referencia'],'caption':plan['caption'],'hashtags':[],'prompts':[ve(1),ve(2)],'notas':notes,'para':'nes_bugallo',**({'replica_id':replace} if replace else {})})
 rid=result.get('id');assert rid,'Registro sin identificador'
 item={'numero':number,'id':rid,'id_tandas':result.get('id_tandas') or 'rv|'+rid,'usuario':'nes_bugallo','archivo':plan['archivo'],'product_id':plan['product_id'],'semaforo':None}
 if replace:
  old=[r for r in saved['registros'] if r['id']==replace];saved['registros']=[r for r in saved['registros'] if r['id']!=replace]
  saved.setdefault('reemplazos',[]).append({'numero':number,'reemplazado':replace,'nuevo':rid,'fecha':time.strftime('%Y-%m-%d %H:%M')});item['reemplaza']=replace
 saved['registros'].append(item);receipt.write_text(json.dumps(saved,ensure_ascii=False,indent=2));marker.unlink()
 print(f"Vídeo {number:02d} registrado como {item['id_tandas']} para nes_bugallo, sin publicar.")
if __name__=='__main__':register(int(sys.argv[1]),*(sys.argv[2:3]))
