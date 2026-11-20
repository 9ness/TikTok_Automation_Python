from PIL import Image, ImageDraw

from src.editor_auto.tools.photo_insert import _fondo_cuadros


def _tablero(path):
    t = Image.new("RGB", (400, 400), "white")
    d = ImageDraw.Draw(t)
    for i in range(0, 400, 20):
        for j in range(0, 400, 20):
            if (i // 20 + j // 20) % 2:
                d.rectangle([i, j, i + 19, j + 19], fill=(204, 204, 204))
    d.ellipse([100, 100, 300, 300], fill=(200, 0, 0))
    t.save(path)


def test_tablero_falso_se_descarta(tmp_path):
    p = tmp_path / "t.png"
    _tablero(p)
    assert _fondo_cuadros(str(p)) is True


def test_fondo_blanco_y_transparencia_real_valen(tmp_path):
    b = Image.new("RGB", (400, 400), "white")
    ImageDraw.Draw(b).ellipse([100, 100, 300, 300], fill=(0, 0, 200))
    b.save(tmp_path / "b.png")
    a = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    ImageDraw.Draw(a).ellipse([100, 100, 300, 300], fill=(0, 200, 0, 255))
    a.save(tmp_path / "a.png")
    assert _fondo_cuadros(str(tmp_path / "b.png")) is False
    assert _fondo_cuadros(str(tmp_path / "a.png")) is False


def test_plataformas_sin_foto():
    from src.editor_auto.tools.photo_insert import _es_plataforma
    assert _es_plataforma("TikTok") and _es_plataforma("logo TikTok") and _es_plataforma("Instagram")
    assert not _es_plataforma("Nike") and not _es_plataforma("logo Nike")
