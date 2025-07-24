#!/bin/bash
# Create 3 rotated versions of each jpg in the current directory using ImageMagick
for img in *.jpg; do
  base="${img%.*}"
  ext="${img##*.}"
  convert "$img" -rotate 90  "${base}_rot90.${ext}"
  convert "$img" -rotate 180 "${base}_rot180.${ext}"
  convert "$img" -rotate 270 "${base}_rot270.${ext}"
done
