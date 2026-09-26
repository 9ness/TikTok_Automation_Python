"""Vaciar una carpeta no puede preguntar por la venta de cada número.

Eran tres idas a Upstash por número y usuario (99 × 3 al vaciar una carpeta
entera): seis minutos para una carpeta vacía. Ahora se mira el índice una vez.
"""

from __future__ import annotations

from src.nicho_pov_bof.repos import product_repo


class _FakeRedis:
    def __init__(self, indice):
        self.indice = set(indice)
        self.llamadas = 0
        self.borradas = []

    def is_available(self):
        return True

    def smembers(self, key):
        self.llamadas += 1
        return list(self.indice)

    def delete(self, key):
        self.llamadas += 1
        self.borradas.append(key)
        return True

    def srem(self, key, member):
        self.llamadas += 1
        self.indice.discard(member)
        return True


def test_solo_toca_las_que_tienen_venta(monkeypatch):
    fake = _FakeRedis({
        "tareas_productos|Tareas Productos 4|3",
        "tareas_productos|Tareas Productos 5|3",
    })
    monkeypatch.setattr(product_repo, "get_nicho_pov_bof_redis", lambda: fake)
    n = product_repo.borrar_ventas(
        "tareas_productos", "Tareas Productos 4", [str(i) for i in range(1, 100)],
    )
    assert n == 1
    assert fake.indice == {"tareas_productos|Tareas Productos 5|3"}
    # Una lectura del índice + borrar la única venta: nada de 99 preguntas.
    assert fake.llamadas == 3
