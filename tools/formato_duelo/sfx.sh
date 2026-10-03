#!/bin/sh
# sfx.sh <dir> — fabrica los sonidos del duelo con ffmpeg (no hay banco de
# lluvia/viento): calle mojada, lluvia, golpe de viento y «pop» de rótulo.
set -e
mkdir -p "$1" && cd "$1"
ffmpeg -v error -y -f lavfi -i "anoisesrc=color=pink:amplitude=0.6:d=70:r=44100" -af "highpass=f=900,lowpass=f=9000,tremolo=f=11:d=0.25,volume=0.5" lluvia.wav
ffmpeg -v error -y -f lavfi -i "anoisesrc=color=brown:amplitude=0.5:d=70:r=44100" -af "lowpass=f=600,volume=0.6" calle.wav
ffmpeg -v error -y -f lavfi -i "anoisesrc=color=brown:amplitude=0.9:d=2.2:r=44100" -af "bandpass=f=500:width_type=o:w=2,afade=t=in:d=0.5,afade=t=out:st=1.1:d=1.1,volume=2.2" viento.wav
ffmpeg -v error -y -f lavfi -i "aevalsrc='sin(2*PI*(260+700*exp(-t*40))*t)*exp(-t*28)':d=0.25:s=44100" -af "volume=0.9" pop.wav
