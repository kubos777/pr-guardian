#!/usr/bin/env bash
# Genera la narración del video con la voz TTS integrada de macOS (`say`).
#
# Uso:
#   ./scripts/make_narration.sh                 # voz Paulina (es_MX), 175 wpm
#   VOICE=Mónica RATE=165 ./scripts/make_narration.sh
#
# Salida: scripts/narration/audio/NN_*.aiff  (un archivo por bloque)
#         scripts/narration/audio/full.aiff  (todo seguido, con pausas)
# Al final imprime la duración de cada bloque para que cuadres la edición.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)/narration"
OUT="$DIR/audio"
VOICE="${VOICE:-Paulina}"
RATE="${RATE:-175}"

mkdir -p "$OUT"
rm -f "$OUT"/*.aiff

echo "Voz: $VOICE   Velocidad: $RATE wpm"
echo ""

TOTAL=0
for f in "$DIR"/*.txt; do
  name="$(basename "$f" .txt)"
  say -v "$VOICE" -r "$RATE" -f "$f" -o "$OUT/$name.aiff"
  dur="$(afinfo "$OUT/$name.aiff" | awk -F': ' '/estimated duration/{print $2}' | awk '{print $1}')"
  printf "  %-22s %6.1f s\n" "$name" "$dur"
  TOTAL=$(echo "$TOTAL + $dur" | bc)
done

echo ""
printf "TOTAL narración: %.1f s (~%.1f min)\n" "$TOTAL" "$(echo "$TOTAL/60" | bc -l)"
echo ""
echo "Archivos en: $OUT"
echo "Impórtalos a tu editor y alinéalos con cada escena del video."
