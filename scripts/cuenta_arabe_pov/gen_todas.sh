#!/bin/bash
cd "${1:-.}"  # carpeta de la ronda
P=/home/nebulabsai/nav-venv/bin/python
for n in 01 02 03 04 05 06 07 08 09 10; do
  R=$(python3 -c "import json;print(' '.join('refs/'+r+'.jpg' for r in json.load(open('refs_por_video.json'))[str(int('$n'))]))")
  for e in 1 2; do
    out=gen/${n}_$e.jpg; [ -s $out ] && continue
    refs="$R"; [ $e = 2 ] && { cp gen/${n}_1.jpg refs/g${n}_1.jpg; refs="refs/g${n}_1.jpg $R"; }
    $P fwait2.py snap >/dev/null && GO=1 timeout 240 $P fimg.py cand/${n}_$e.txt $refs >/dev/null 2>&1
    timeout 330 $P fwait2.py $out 300 || echo "FALLO $out"
    echo "$(date +%T) $out"
  done
done
echo FIN
