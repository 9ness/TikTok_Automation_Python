# «Escucha» con los ojos: espectrogramas antes/después (10/11/2026)

> Anexo de [`2026-11-10_audio_y_estilo_vip.md`](2026-11-10_audio_y_estilo_vip.md). Las rutas relativas (`scripts/`, `log/`, `estilo/`, `muestras_audio/`…) son de la carpeta de pruebas `/mnt/HC_Volume_106974679/agentes/trabajo/fable-audio/` (en el ampliado del VPS, fuera de git).

**Aviso.** Un agente no oye. Esto es lo que SE VE en los espectrogramas (0-8 kHz, 30 s; hojas en
`muestras_audio/espectrogramas/`) y dos medidas sencillas sobre el audio: **voz−suelo** (dB entre el nivel de la voz y
el de los huecos: más = huecos más limpios) y **agudos** (energía de 4-8 kHz frente a 300-4.000 Hz mientras se habla:
si baja mucho, la voz queda apagada). No sustituye al oído: lo que aquí parece limpio puede sonar metálico o
«recortado». Los audios para escucharlo están en `muestras_audio/<caso>/`. DNSMOS = OVRL/SIG/BAK (1-5), de
`log/dnsmos.jsonl`; Demucs aún no estaba medido al escribir esto.

## Por caso

**R_cintiacbc__quiet** (real, grabado a −35 LUFS). Al nivelar («hoy») sube la voz y con ella el siseo: fondo rojo
continuo en todas las frecuencias (voz−suelo 22 dB). RNNoise lo baja unos 7 dB (29 dB) pero queda velo entre frases.
DeepFilterNet deja los huecos en negro (54 dB) y los armónicos de la voz intactos hasta arriba (agudos −14,9 frente a
−15,4 del original). Demucs casi no toca el siseo mientras habla (26 dB). `afftdn` baja el fondo 11 dB pero se lleva
12 dB de agudos. DNSMOS OVRL: hoy 1,44 → afftdn 2,33 · rnnoise 2,25 · DFN 2,79 · DFN suave 2,48.

**R_bugalleitor__1** (real, ruido de ambiente grave y continuo). «Hoy» = igual que el original. RNNoise limpia las
pausas (31 dB) pero la franja grave sigue bajo la voz. DeepFilterNet corta a negro entre palabras (57 dB): se ven
bloques de encendido/apagado muy bruscos, que al oído pueden sonar a puerta de ruido, y pierde ~6 dB de agudos.
Demucs lo deja prácticamente como estaba (17,5 dB frente a 16,5). OVRL: hoy 2,17 → rnnoise 2,48 · rnnoise 70 % 2,63 ·
DFN 2,93 (BAK 4,0) · DFN suave 2,74.

**R_nebulabs__img** (real). Los primeros ~17 s no hay voz, solo un ambiente muy flojo; luego voz a buen nivel y fondo
limpio (BAK 3,76). La nota baja (OVRL 1,62) viene de la señal (SIG 2,06), no del ruido: ningún método la arregla
(mejor: DFN 2,0). DFN y Demucs dejan el arranque en silencio digital. Aquí limpiar no aporta; en el espectrograma no
se ve qué le pasa a la voz (habría que oírla).

**S_patri_musica** (voz + música). La música son las líneas horizontales, también en las pausas. «Hoy» y `afftdn` no
hacen nada (afftdn 1,43, peor que hoy 1,49). RNNoise la quita en las pausas (27 dB) pero las líneas siguen visibles
debajo de la voz: la música «asoma» cada vez que habla. DeepFilterNet y Demucs dejan pausas en negro y casi sin
líneas bajo la voz; Demucs deja algo de resto grave. OVRL: hoy 1,49 → rnnoise 2,72 → DFN 3,07; SI-SDR 2,9 → 3,9 →
10,8 dB.

**S_patri_viento** (voz + rachas de viento). El viento son las manchas brillantes en graves (0-6 s, 10-20 s, 25-30 s).
RNNoise quita la mayor parte pero deja retumbe grave en las rachas; DeepFilterNet lo limpia casi todo; Demucs deja
restos claros (mancha en 13-15 s). OVRL: hoy 2,30 → rnnoise 2,82 → DFN 3,16; SI-SDR 0,8 → 5,4 → 11,5 dB.

**S_patri_eco** (voz + reverberación). Los cinco paneles son casi iguales: el eco (armónicos emborronados en el
tiempo) sigue en todos. Los limpiadores solo oscurecen un poco las pausas. El DNSMOS sube (2,40 → rnnoise 2,85 → DFN
3,27) por el fondo, no porque se vaya el eco; RNNoise incluso se aleja de la voz limpia (SI-SDR 5,1 → 2,4; DFN 6,6).
**Ninguno de los probados quita el eco.**

**S_patri_lluvia** (voz + lluvia fuerte). La lluvia llena todas las frecuencias. RNNoise la baja mucho (voz−suelo 10 →
28 dB) y deja un velo uniforme; DeepFilterNet deja los huecos en negro pero los armónicos por encima de ~3 kHz salen
más finos (agudos −24 dB frente a ≈ −19 de la voz limpia: puede perder brillo en las eses); Demucs limpia menos y
deja manchas graves en los huecos. OVRL: hoy 1,29 → afftdn 1,53 → rnnoise 2,40 → DFN 3,30.

**S_nueve_motor** (voz + motor; la voz empieza en el segundo 5). **Ojo con el nivelado:** en «hoy» el ruido de los
4 primeros segundos sin voz pasa de −12,9 dB a −1,9 dB respecto a la voz: el `loudnorm` de una pasada lo sube casi
al volumen de la voz. Con RNNoise el arranque sigue a −4,8 dB (no limpia el motor ahí y el nivelado lo infla): se ve
un bloque naranja al principio. DeepFilterNet y Demucs lo dejan en silencio (−70 / −60 dB); a DFN le queda una línea
fina del tono del motor. OVRL: hoy 2,10 → rnnoise 2,49 → DFN 3,21 (SI-SDR −2,8 → 3,8 → 9,0 dB). DFN suave pierde casi
toda la ventaja (2,47; SI-SDR 0,1). Nota: ese bombeo es del nivelado de una pasada de las pruebas; `audio_clean`
nivela en dos pasadas con `linear=true`, que no debería hacerlo (por comprobar con este caso).

**S_patri_clics** (hoja extra, con «declick + rnnoise»). Los clics apenas se ven a esta escala. RNNoise y
declick+RNNoise salen idénticos (OVRL 2,98 y 2,99; hoy 3,04): `adeclick` no aporta. `afftdn` empeora (2,48). DFN 3,18 y
SI-SDR 12,0 (hoy 5,9).

## Problema → qué lo arregla y qué lo estropea

| Problema | Lo arregla | No sirve o lo estropea |
|---|---|---|
| Volumen bajo | El nivelado a −16 LUFS (ya se hace). Con limpieza ANTES de nivelar, porque si no sube el siseo con la voz (cintia: OVRL 1,44 sin limpiar → 2,79 con DFN) | Nivelado de una pasada: infla el ruido donde no hay voz (motor: +11 dB en el arranque) |
| Ruido constante (siseo, motor, aspiradora) | DeepFilterNet (OVRL ≈ 2,8-3,2); RNNoise bien y casi gratis (≈ 2,3-2,5) | `afftdn`: quita poco y apaga la voz (−4 a −12 dB de agudos). Demucs: casi no lo toca. RNNoise al 70 %: peor que al 100 % casi siempre |
| Viento | DeepFilterNet (SI-SDR 0,8 → 11,5 dB) | RNNoise a medias (queda retumbe grave); Demucs deja rachas; `afftdn` casi nada |
| Eco / reverberación | Nada de lo probado | Todos lo dejan igual; RNNoise se aleja algo de la voz limpia. Haría falta un «dereverb» (Resemble Enhance, Adobe, Auphonic: sin probar) |
| Música de fondo | DeepFilterNet y Demucs (parecidos a la vista; DFN ~1 s por 30 s, Demucs 25-55 s) | RNNoise solo en las pausas (asoma bajo la voz); `afftdn` nada (empeora) |
| Clics | Nada claro; DeepFilterNet mejora algo | `adeclick` no aporta; `afftdn` empeora |
| Lluvia | DeepFilterNet (OVRL 1,29 → 3,30), con posible pérdida de brillo; RNNoise aceptable (2,40) | `afftdn` casi nada (1,53); Demucs a medias |

## Lo que hay que comprobar con el oído

1. DeepFilterNet deja silencio digital entre frases (voz−suelo > 55 dB): puede sonar recortado o artificial en vídeos
   sin música. La versión suave (tope 12 dB) conserva ambiente pero pierde buena parte de la mejora.
2. Si DeepFilterNet apaga las eses en lluvia y en `bugalleitor` (−5 / −6 dB de agudos en la medida).
3. Si la música que deja RNNoise bajo la voz molesta más que la música entera.
4. Si el arranque inflado del caso del motor se oye tan mal como se ve.
