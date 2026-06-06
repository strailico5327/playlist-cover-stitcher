# Playlist Cover Stitcher

Playlist Cover Stitcher creates one seamless 1000x1000 PNG playlist cover from four album covers.

## Web Version

Open `index.html` in a modern browser. No build step, server, or package install is required.

Features:

- Click a grid tile to choose an image.
- Drag one image file onto a tile to fill that tile.
- Drag multiple image files onto the page to randomly fill empty tiles.
- Right-click a tile to paste from the clipboard or delete only that tile.
- Press `Ctrl+V` while hovering a tile to paste a copied image.
- Drag from one filled tile to another filled tile to swap them.
- Shuffle, clear, and export a 1000x1000 PNG.
- Center-crop non-square images before resizing.

The static web version uses browser-native image decoding, so it supports PNG, JPEG, WebP, and BMP files.

Web icons are stored in `assets/` and referenced by `index.html` and `site.webmanifest`.

## Licence

This project is licensed under the GNU General Public License v3.0.

Copyright (C) 2026 strailico5327.
