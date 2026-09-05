# Los personajes

Un fichero por personaje, con la descripción que devolvió ChatGPT al pasarle
su foto de Pinterest por [`../personaje.md`](../personaje.md).

**Aquí no está la imagen**, que es lo que se usa a diario: la imagen se genera
en Flow con este texto y se guarda aparte (`<clave>.jpg`). Esto es lo que
permite REHACERLA sin volver a buscar la foto original.

| Clave | Quién es | Qué productos le tocan |
|---|---|---|
| `belleza_mujer` | rubia ondulada, ~40, verde oliva y lino blanco | cremas, sérums, cuidado facial |
| `belleza_mujer_2` | morena melena, ~45, elegante | colágeno, antiedad, articulaciones |
| `belleza_mujer_3` | morena joven, ~27, aire deportivo | vitaminas, biotina, energía |
| `hogar_mujer` | 30-35, casual de casa | orden, limpieza, cocina, plantas |
| `exterior_hombre` | 30-40, práctico | jardín, terraza, herramientas, bici |
| `tech_hombre` | 22-28, moderno | gaming, escritorios, LED, gadgets |
| `fitness_hombre` | 28-35, atlético | proteína, creatina, entrenamiento |
| `bebe_mujer` | ~30, madre joven | biberones, pañales, crianza |
| `viaje_mujer` | 25-35, viajera | maletas, mochilas de cabina |
| `generico_mujer` | 28-35, neutra | lo que no encaja en ningún nicho |

Al añadir una persona más a un nicho hay que subir su número en
`config.NICHOS[...]["personas"]`, o no entrará en el reparto.
