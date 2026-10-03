#!/bin/sh
# hoja.sh <clip.mp4> <salida.png> — 16 fotogramas (cada 0,5 s) en una hoja 8x2
ffmpeg -v error -y -i "$1" -vf "fps=2,scale=240:-2,tile=8x2" -frames:v 1 "$2"
