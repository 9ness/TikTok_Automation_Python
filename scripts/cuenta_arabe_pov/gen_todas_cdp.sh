#!/bin/bash
# Imágenes de Flow (Nano Banana, 0 puntos) por CDP: cand/NN_e.txt + refs_por_video.json → gen/NN_e.jpg
cd "$(dirname "$0")"
P=/home/nebulabsai/nav-venv/bin/python
for n in ${@:-01 02 03 04 05 06 07 08 09 10}; do
  R=$(python3 -c "import json;print(' '.join('refs/'+r+'.jpg' for r in json.load(open('refs_por_video.json'))[str(int('$n'))]))")
  for e in 1 2; do
    out=gen/${n}_$e.jpg; [ -s $out ] && continue
    refs="$R"; [ $e = 2 ] && { cp gen/${n}_1.jpg refs/g9_${n}_1.jpg; refs="refs/g9_${n}_1.jpg $R"; }
    GO=1 timeout 240 $P fimg_cdp.py cand/${n}_$e.txt $refs || { echo "FALLO envío $out"; continue; }
    timeout 330 $P fwait_cdp.py $out 300 || echo "FALLO $out"
    echo "$(date +%T) $out"
  done
done
echo FIN
