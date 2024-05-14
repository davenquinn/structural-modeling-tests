#!/usr/bin/env bash

function create-isopach {
    poetry run python create-isopach.py --bounds output/study-bounds.gpkg "$@"
}

create-isopach \
  --lith carbonate \
  --min-age "Early Ordovician" \
  --max-age Cambrian \
  output/cambrian-to-early-ordovician-carbonates.tif

# Isopachs for specific formations
for strat_name in "Potosi" "Knox" "Bonneterre"; do
    create-isopach \
      --strat-name "$strat_name" \
      output/$strat_name.tif
done