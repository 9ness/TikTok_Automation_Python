"""El modo de guion (precio / punto de dolor) viaja DENTRO del trabajo.

El documento de Redis lleva el modo en la clave, así que quien guarda tiene que
saber con cuál se pidió el trabajo. Resolverlo al guardar —minutos después, con
la cola por medio— escribía en el documento del modo que estuviera activo en
ese momento: guiones de precio dentro de "punto de dolor" y el documento de
precio vacío. Es lo que hizo que al operador le pareciera que se machacaban.
"""

from __future__ import annotations

from src.nicho_pov_bof_largo.repos import product_repo


class TestLaClaveSeparaLosModos:
    def test_cada_modo_tiene_su_documento(self, monkeypatch):
        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.progress_repo.get_modo",
            lambda *a, **k: "precio",
        )
        precio = product_repo._key("mis_productos", "Carpeta 1", "ness", "precio")
        dolor = product_repo._key("mis_productos", "Carpeta 1", "ness", "dolor")
        assert precio != dolor
        # El modo por defecto se queda en la clave de siempre: el histórico no
        # se mueve de sitio.
        assert not precio.endswith(":m:precio")
        assert dolor.endswith(":m:dolor")

    def test_leer_un_producto_respeta_el_modo_que_se_pide(self, monkeypatch):
        """`get_product` aceptaba `estilo` y no lo usaba: leía siempre el del
        modo activo, así que el montaje comparaba con el guion del otro."""
        vistas: list[str] = []

        def espia(source, folder, usuario="", estilo=""):
            vistas.append(estilo)
            return {}

        monkeypatch.setattr(product_repo, "load_folder", espia)
        product_repo.get_product("mis_productos", "Carpeta 1", "3", "ness", "dolor")
        assert vistas == ["dolor"]


class TestElTrabajoSeLlevaElModo:
    def _job(self, params):
        class Job:
            id = "j1"
            enqueued_by = "ness"

        j = Job()
        j.params = params
        return j

    def test_los_guiones_en_lote_escriben_en_el_modo_con_el_que_se_pidieron(
        self, monkeypatch,
    ):
        """Se encola en 'dolor', el operador cambia el catálogo a 'precio'
        mientras la cola trabaja: los guiones tienen que acabar en 'dolor'."""
        from src.queue import runners

        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.progress_repo.get_modo",
            lambda *a, **k: "precio",  # el modo ACTIVO ya es otro
        )
        monkeypatch.setattr(
            "src.nicho_pov_bof.services.drive_client.list_product_folders",
            lambda source: [{"name": "Carpeta 1"}],
        )
        monkeypatch.setattr(
            "src.nicho_pov_bof.repos.product_repo.load_folder_para",
            lambda *a, **k: {"productos": {"1": {"titulo": "Aspiradora", "precio": "39"}}},
        )
        leidos: list[str] = []
        escritos: list[str] = []

        def load_folder(source, folder, usuario="", estilo=""):
            leidos.append(estilo)
            return {}

        def update_product(source, folder, producto, usuario="", estilo="", **campos):
            escritos.append(estilo)
            return {}

        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.product_repo.load_folder", load_folder)
        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.product_repo.update_product", update_product)
        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.services.guionista.escribir",
            lambda **kw: {"guion": "Si tu casa está sucia, esta aspiradora.",
                          "subliminal": "a", "nombre": "Aspiradora"},
        )
        monkeypatch.setattr(runners, "_foto_limpia", lambda *a, **k: None)

        runners.run_nicho_pov_bof_largo_guiones(
            self._job({"source": "mis_productos", "folder": "Carpeta 1",
                       "usuario": "ness", "estilo": "dolor"}),
            lambda _m: None, lambda _p, _m: None,
        )
        assert escritos and set(escritos) == {"dolor"}, escritos
        assert set(leidos) == {"dolor"}, leidos

    def test_sin_modo_en_el_trabajo_se_usa_el_activo(self, monkeypatch):
        """Los trabajos encolados antes de este arreglo no lo llevan."""
        from src.queue import runners

        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.progress_repo.get_modo",
            lambda *a, **k: "dolor",
        )
        monkeypatch.setattr(
            "src.nicho_pov_bof.repos.product_repo.load_folder_para",
            lambda *a, **k: {"productos": {"1": {"titulo": "Aspiradora"}}},
        )
        leidos: list[str] = []
        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.repos.product_repo.load_folder",
            lambda s, f, u="", e="": leidos.append(e) or {},
        )
        try:
            runners.run_nicho_pov_bof_largo_guiones(
                self._job({"source": "mis_productos", "folder": "Carpeta 1",
                           "usuario": "ness"}),
                lambda _m: None, lambda _p, _m: None,
            )
        except RuntimeError:
            pass  # sin textos: da igual, lo que se mira es con qué modo leyó
        assert leidos and set(leidos) == {"dolor"}, leidos
