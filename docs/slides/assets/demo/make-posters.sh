#!/usr/bin/env bash
#
# Generate poster frames for the demo-journey videos used by the slide deck.
# A <video> needs a poster so the print-to-PDF path in deck-stage.js has a
# still to render (it swaps each <video> for its poster image). Re-run this
# after re-recording either journey, then commit the regenerated PNGs.
#
# Requires ffmpeg on PATH:  brew install ffmpeg
#
# The timestamps below were chosen by hand to land on a representative,
# non-blank screen (the journeys have white loading/transition frames).

set -euo pipefail
cd "$(dirname "$0")"

# poster <video> <timestamp-seconds> <output.png>
poster() {
  local src="$1" ts="$2" out="$3"
  # -ss after -i = frame-accurate seek (decodes up to ts); fine for short clips.
  ffmpeg -y -i "$src" -ss "$ts" -frames:v 1 -update 1 "$out"
  echo "wrote $out  <-  $src @ ${ts}s"
}

poster holder-journey.webm  19 holder-journey-poster.png
poster manager-journey.webm 40 manager-journey-poster.png
