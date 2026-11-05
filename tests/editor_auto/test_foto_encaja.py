"""Las fotos de apoyo se comprueban antes de usarlas (vip_overlays / photo_insert)."""
from src.editor_auto.tools import photo_insert as pi


def _preparar(monkeypatch, veredictos):
    import src.tiktok_shop.utils.image_search as isrch
    monkeypatch.setattr(isrch, "search_product_images",
                        lambda q, num, prefer_google: ("x", [{"link": f"u{i}"} for i in range(6)]), raising=False)
    monkeypatch.setattr(pi, "_download_and_normalize", lambda url, dest: open(dest, "w").close() or True)
    it = iter(veredictos)
    monkeypatch.setattr(pi, "_foto_encaja", lambda path, q: next(it))


def test_salta_la_que_no_encaja(monkeypatch, tmp_path):
    _preparar(monkeypatch, [False, True])
    log = []
    assert pi._search_and_download(query="q", dest=str(tmp_path / "f.png"), prefer_google=False, log=log.append)
    assert any("no encaja" in m for m in log)


def test_ninguna_encaja_va_sin_foto(monkeypatch, tmp_path):
    _preparar(monkeypatch, [False] * 10)
    dest = tmp_path / "f.png"
    assert pi._search_and_download(query="q", dest=str(dest), prefer_google=False, log=lambda m: None) is None
    assert not dest.exists()


def test_sin_comprobacion_se_acepta(monkeypatch, tmp_path):
    _preparar(monkeypatch, [None])
    assert pi._search_and_download(query="q", dest=str(tmp_path / "f.png"), prefer_google=False, log=lambda m: None)
