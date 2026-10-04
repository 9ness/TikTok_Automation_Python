"""La lista de usuarios: 2 comandos (SMEMBERS + MGET) y caché en memoria que se
tira al guardar o borrar (Upstash cobra por comando)."""
from __future__ import annotations

import json

from src.editor_auto.models import EditorUser
from src.editor_auto.repos import user_repo
from src.editor_auto.repos.user_repo import UserRepo


class RedisContador:
    prefix = "test:"

    def __init__(self) -> None:
        self.d: dict = {}
        self.sets: dict = {}
        self.comandos = 0

    def is_available(self):
        return True

    def get_json(self, k):
        self.comandos += 1
        v = self.d.get(k)
        return json.loads(v) if v else None

    def mget_json(self, ks):
        self.comandos += 1
        return [json.loads(self.d[k]) if k in self.d else None for k in ks]

    def set_json(self, k, v):
        self.comandos += 1
        self.d[k] = json.dumps(v, default=str)
        return True

    def set_str(self, k, v):
        self.comandos += 1
        self.d[k] = v
        return True

    def get_str(self, k):
        self.comandos += 1
        return self.d.get(k)

    def sadd(self, k, m):
        self.comandos += 1
        self.sets.setdefault(k, set()).add(m)
        return True

    def smembers(self, k):
        self.comandos += 1
        return list(self.sets.get(k, set()))

    def srem(self, k, m):
        self.comandos += 1
        self.sets.get(k, set()).discard(m)
        return True

    def delete(self, k):
        self.comandos += 1
        return self.d.pop(k, None) is not None


def _usuario(nombre: str) -> EditorUser:
    return EditorUser.model_validate({"name": nombre})


def test_lista_en_dos_comandos_y_cacheada():
    user_repo._invalidar_lista()
    r = RedisContador()
    repo = UserRepo(redis=r)
    for n in ("ana", "mauro", "ness"):
        repo.save(_usuario(n))
    r.comandos = 0
    assert {u.name for u in repo.list_all()} == {"ana", "mauro", "ness"}
    assert r.comandos == 2  # SMEMBERS + MGET, no uno por usuario
    repo.list_all(); repo.list_all()
    assert r.comandos == 2  # de memoria


def test_guardar_invalida_y_no_se_comparte_el_objeto():
    user_repo._invalidar_lista()
    r = RedisContador()
    repo = UserRepo(redis=r)
    u = repo.save(_usuario("ana"))
    primera = repo.list_all()
    primera[0].name = "modificado"  # quien la recibe no estropea la caché
    assert repo.list_all()[0].name == "ana"
    u.name = "ana2"
    repo.save(u)
    assert repo.list_all()[0].name == "ana2"
