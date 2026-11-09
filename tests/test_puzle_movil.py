import importlib.util
import pathlib

_p = pathlib.Path(__file__).resolve().parents[1] / "scripts" / "movil" / "puzle.py"
_s = importlib.util.spec_from_file_location("puzle_movil", _p)
puzle = importlib.util.module_from_spec(_s)
_s.loader.exec_module(puzle)

H = '<?xml version="1.0" encoding="UTF-8"?><hierarchy rotation="0">{}</hierarchy>'

PUZLE = H.format(
    '<node index="0" text="" resource-id="" class="android.widget.FrameLayout" bounds="[0,0][1080,2248]">'
    '<node text="Verifica para continuar" resource-id="" class="android.widget.TextView" clickable="false" bounds="[100,800][980,900]"/>'
    '<node text="" content-desc="Cerrar" resource-id="com.zhiliaoapp.musically:id/close_btn" class="android.widget.ImageView" clickable="true" bounds="[870,667][960,767]"/>'
    '<node text="" resource-id="captcha_container" class="android.webkit.WebView" bounds="[60,700][1020,1700]"/>'
    '</node>')

PERFIL = H.format(
    '<node text="" bounds="[0,0][1080,2248]">' +
    "".join(f'<node text="@pisadaviva{i}" resource-id="com.zhiliaoapp.musically:id/title" bounds="[0,{i*50}][500,{i*50+40}]"/>' for i in range(8)) +
    '<node text="Cerrar sesion" bounds="[0,2000][300,2100]"/></node>')


def test_detecta_por_texto():
    assert puzle.detectar_puzle(PUZLE)


def test_detecta_por_id_sin_texto():
    x = H.format('<node resource-id="com.x:id/secsdk_captcha_view" bounds="[0,0][10,10]"/>')
    assert puzle.detectar_puzle(x)


def test_perfil_normal_no_es_puzle():
    assert not puzle.detectar_puzle(PERFIL)
    assert puzle.boton_cerrar(PERFIL) is None


def test_boton_cerrar_centro():
    assert puzle.boton_cerrar(PUZLE) == (915, 717)


def test_puzle_sin_boton():
    x = H.format('<node text="Verify to continue" bounds="[0,0][10,10]"/>')
    assert puzle.detectar_puzle(x) and puzle.boton_cerrar(x) is None


def test_xml_invalido():
    assert not puzle.detectar_puzle("no es xml") and puzle.boton_cerrar("") is None
    assert puzle.dump_sospechoso("no es xml")


def test_dump_sospechoso():
    assert puzle.dump_sospechoso(H.format('<node text="" bounds="[0,0][1080,2248]"/>'))
    assert not puzle.dump_sospechoso(PERFIL)
