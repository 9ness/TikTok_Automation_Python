"""«Mis tandas»: los vídeos ya montados de un usuario, de todos sus nichos,
en tandas de diez para publicarlos.

Es una VISTA, no un nicho: no guarda vídeos ni estados propios. Lee los
documentos de cada nicho (POV BOF, POV BOF Largo, Moda Mujer Multimodo) y los
botones escriben en esos mismos documentos, así que marcar algo aquí es
marcarlo en su pantalla y al revés. Lo único suyo es el ORDEN de publicación
(`mis_tandas:orden:<usuario>`), que no se mueve una vez fijado.
"""
