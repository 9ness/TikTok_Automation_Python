"""Zapatillas Vista POV/Sentado 20s: dos clips mudos + voz de Fish.

Son los únicos del multimodo que hablan, y no con la voz del clip: el guion de
punto de dolor del POV BOF Largo, locutado con Fish y montado con su editor.
"""

from __future__ import annotations

from pathlib import Path

from src.nicho_ropa import config

MODOS = ("mm_zapatillas_pov20", "mm_zapatillas_sentado20")


class TestConfig:
    def test_son_de_dos_clips_de_10_mudos_y_con_fish(self):
        for m in MODOS:
            assert config.lleva_fish(m)
            assert config.partes_de_modo(m) == 2
            assert not config.modo_habla(m)  # el audio del clip se tira
            assert m in config.modos_multimodo()
            e = config.prompts_mof10("mujer", False, m)[0]
            assert e["fish"] and e["segundos_clip"] == 10
            # El movimiento termina prohibiendo texto y voz en el clip.
            assert "sin ningún texto" in e["guion"] and "Nadie habla" in e["guion"]

    def test_los_demas_no_llevan_fish(self):
        assert not config.lleva_fish("mm_espejo")
        assert not config.lleva_fish(config.MODO_MULTI)

    def test_la_pantalla_los_marca(self):
        fish = [m["clave"] for m in config.modos_de("mujer", "multimodo") if m["fish"]]
        assert sorted(fish) == sorted(MODOS)


class TestMontaje:
    def _job(self, params):
        class Job:
            id = "j1"
            enqueued_by = "ana"

        j = Job()
        j.params = params
        return j

    def test_escribe_locuta_y_monta_con_el_editor_del_largo(self, monkeypatch, tmp_path):
        from src.queue import runners

        clips = []
        for n in (1, 2):
            c = tmp_path / f"clip{n}.mp4"
            c.write_bytes(b"x")
            clips.append(c)
        prod = {"titulo": "Botines de mujer", "tienda": "Tienda", "precio": "25"}
        llamadas: dict = {}

        monkeypatch.setattr(
            "src.nicho_ropa.repos.product_repo.get_product", lambda *a, **k: prod,
        )
        monkeypatch.setattr(runners, "_fotos_prenda_ropa", lambda *a, **k: {})
        monkeypatch.setattr(runners, "_segundos_de_video", lambda *a, **k: 20.0)

        def escribir(**kw):
            llamadas["prompt"] = kw["prompt"]
            return {"guion": "Si tus pies se cansan, esto te interesa. Ve al carrito naranja.",
                    "subliminal": "Han ajustado el precio de\nBotines", "nombre": "Botines"}

        monkeypatch.setattr("src.nicho_pov_bof_largo.services.guionista.escribir", escribir)
        guardado: dict = {}
        monkeypatch.setattr(
            "src.nicho_ropa.repos.product_repo.guardar_guion",
            lambda carpeta, pid, modo, dice, video, videos=None, **k: guardado.update(
                modo=modo, dice=dice, videos=videos, **k),
        )

        def sintetizar(texto, destino, **kw):
            llamadas["voz"] = kw
            Path(destino).write_bytes(b"a")
            return {"texto": texto, "voz_id": "v", "duracion": 19.5, "tempo": 1.0, "voz_label": "x"}

        monkeypatch.setattr("src.nicho_pov_bof_largo.services.voz.sintetizar", sintetizar)
        monkeypatch.setattr(
            "src.nicho_pov_bof_largo.services.velocidad_voz.apuntar", lambda *a, **k: None,
        )

        def montar(**kw):
            llamadas["montar"] = kw
            Path(kw["output_path"]).write_bytes(b"v")

        monkeypatch.setattr("src.nicho_pov_bof_largo.pipeline.video_editor.montar", montar)
        monkeypatch.setattr("src.nicho_ropa.config.video_dir", lambda: str(tmp_path / "out"))
        videos: list = []
        monkeypatch.setattr(
            "src.nicho_ropa.repos.product_repo.guardar_video",
            lambda carpeta, producto, modo, ruta, at, usuario="": videos.append((modo, ruta, usuario)),
        )
        olvidados: list = []
        monkeypatch.setattr(
            "src.nicho_ropa.repos.product_repo.olvidar_clips",
            lambda *a, **k: olvidados.append(a),
        )

        salida = runners.run_nicho_ropa_video(
            self._job({
                "producto": "3", "carpeta": "mujer_zapatos_web__Carpeta 2",
                "raw_paths": [str(c) for c in clips], "raw_path": str(clips[0]),
                "modo": "mm_zapatillas_pov20", "operator": "ana",
            }),
            lambda *_: None, lambda *_: None,
        )

        # El guion es el de punto de dolor del Largo, para 20 s.
        assert "puntos de dolor" in llamadas["prompt"].lower()
        assert guardado["modo"] == "mm_zapatillas_pov20" and len(guardado["videos"]) == 2
        assert guardado["subliminal"].startswith("Han ajustado")
        # Voz de mujer, a la medida de los dos clips.
        assert llamadas["voz"]["sexo"] == "mujer"
        assert llamadas["voz"]["segundos_ideal"] == 20.0
        # Montado con los textos del Largo: dos clips, subtítulos, acabado blanco.
        m = llamadas["montar"]
        assert len(m["clips"]) == 2 and m["con_subtitulos"] and m["estilo_texto"] == "blanco"
        assert videos == [("mm_zapatillas_pov20", salida, "ana")]
        assert "__mm_zapatillas_pov20" in salida and olvidados
