const OUTPUT_SIZE = 1000;
const TILE_SIZE = OUTPUT_SIZE / 2;
const SUPPORTED_TYPES = new Set([
  "image/png",
  "image/jpeg",
  "image/webp",
  "image/bmp",
]);
const SUPPORTED_EXTENSIONS = /\.(png|jpe?g|webp|bmp)$/i;

const tiles = Array.from(document.querySelectorAll(".tile"));
const grid = document.querySelector("#cover-grid");
const singleFileInput = document.querySelector("#single-file-input");
const bulkFileInput = document.querySelector("#bulk-file-input");
const exportButton = document.querySelector("#export-button");
const addButton = document.querySelector("#add-button");
const pasteButton = document.querySelector("#paste-button");
const shuffleButton = document.querySelector("#shuffle-button");
const clearButton = document.querySelector("#clear-button");

const state = {
  tiles: [null, null, null, null],
  selectedIndex: null,
  pointerStart: null,
};

function setStatus() {
}

function tileIndexFromEvent(event) {
  const tile = event.target.closest(".tile");
  return tile ? Number(tile.dataset.index) : null;
}

function firstEmptyIndex() {
  return state.tiles.findIndex((tile) => tile === null);
}

function pasteStartIndex() {
  return Number.isInteger(state.selectedIndex) ? state.selectedIndex : 0;
}

function selectTile(index) {
  state.selectedIndex = index;
  tiles.forEach((tile, tileIndex) => {
    tile.classList.toggle("selected-tile", tileIndex === index);
  });
}

function isSupportedFile(file) {
  return SUPPORTED_TYPES.has(file.type) || SUPPORTED_EXTENSIONS.test(file.name);
}

function extensionFromMimeType(mimeType) {
  if (mimeType === "image/jpeg") {
    return "jpg";
  }
  return mimeType.split("/")[1] || "png";
}

async function loadBitmap(file) {
  if ("createImageBitmap" in window) {
    try {
      return await createImageBitmap(file, { imageOrientation: "from-image" });
    } catch {
      return await createImageBitmap(file);
    }
  }

  const image = new Image();
  image.decoding = "async";
  image.src = URL.createObjectURL(file);
  await image.decode();
  return image;
}

async function prepareTile(file) {
  const bitmap = await loadBitmap(file);
  const side = Math.min(bitmap.width, bitmap.height);
  const sourceX = Math.floor((bitmap.width - side) / 2);
  const sourceY = Math.floor((bitmap.height - side) / 2);
  const canvas = document.createElement("canvas");
  canvas.width = TILE_SIZE;
  canvas.height = TILE_SIZE;
  const context = canvas.getContext("2d", { alpha: true });
  context.imageSmoothingQuality = "high";
  context.drawImage(bitmap, sourceX, sourceY, side, side, 0, 0, TILE_SIZE, TILE_SIZE);
  bitmap.close?.();
  return {
    canvas,
    fileName: file.name || "clipboard image",
    previewUrl: canvas.toDataURL("image/png"),
  };
}

async function loadFileIntoTile(file, index, options = {}) {
  if (!file || !isSupportedFile(file)) {
    if (options.showErrors !== false) {
      setStatus("No supported image file was selected.");
    }
    return false;
  }

  try {
    state.tiles[index] = await prepareTile(file);
    renderTile(index);
    setStatus(`Grid ${index + 1} loaded: ${state.tiles[index].fileName}`);
    return true;
  } catch (error) {
    if (options.showErrors !== false) {
      setStatus(`Could not load image: ${error.message}`);
    }
    return false;
  }
}

function renderTile(index) {
  const tile = tiles[index];
  const tileState = state.tiles[index];

  if (!tileState) {
    tile.innerHTML = `<span class="tile-empty"><strong>${index + 1}</strong><span>Click, drop, or paste</span></span>`;
    return;
  }

  const image = document.createElement("img");
  image.alt = `Grid ${index + 1}: ${tileState.fileName}`;
  image.draggable = false;
  image.src = tileState.previewUrl;
  tile.replaceChildren(image);
}

function renderAllTiles() {
  for (let index = 0; index < tiles.length; index += 1) {
    renderTile(index);
  }
}

function shuffle(items) {
  for (let index = items.length - 1; index > 0; index -= 1) {
    const other = Math.floor(Math.random() * (index + 1));
    [items[index], items[other]] = [items[other], items[index]];
  }
  return items;
}

async function fillEmptyTiles(files) {
  const imageFiles = shuffle(files.filter(isSupportedFile));
  const emptySlots = shuffle(state.tiles.map((tile, index) => (tile ? null : index)).filter((index) => index !== null));

  if (!imageFiles.length) {
    setStatus("No supported image files were dropped.");
    return;
  }
  if (!emptySlots.length) {
    setStatus("All four grid tiles are filled. Clear a tile or click Shuffle.");
    return;
  }

  let loaded = 0;
  for (let index = 0; index < emptySlots.length && index < imageFiles.length; index += 1) {
    loaded += (await loadFileIntoTile(imageFiles[index], emptySlots[index], { showErrors: false })) ? 1 : 0;
  }
  setStatus(`Randomly placed ${loaded} image(s) into empty grid tiles.`);
}

async function pasteFilesInOrder(files, startIndex = pasteStartIndex()) {
  const imageFiles = files.filter(isSupportedFile);
  if (!imageFiles.length) {
    setStatus("Clipboard has no image or copied image file.");
    return;
  }

  let loaded = 0;
  for (let offset = 0; offset < imageFiles.length; offset += 1) {
    const targetIndex = startIndex + offset;
    if (targetIndex >= state.tiles.length) {
      break;
    }
    loaded += (await loadFileIntoTile(imageFiles[offset], targetIndex, { showErrors: false })) ? 1 : 0;
  }

  if (loaded) {
    selectTile(startIndex);
    setStatus(`Pasted ${loaded} image(s) starting at Grid ${startIndex + 1}.`);
  }
}

async function filesFromEntry(entry) {
  if (!entry) {
    return [];
  }
  if (entry.isFile) {
    return await new Promise((resolve) => entry.file((file) => resolve([file]), () => resolve([])));
  }
  if (!entry.isDirectory) {
    return [];
  }

  const reader = entry.createReader();
  const entries = [];
  while (true) {
    const batch = await new Promise((resolve) => reader.readEntries(resolve, () => resolve([])));
    if (!batch.length) {
      break;
    }
    entries.push(...batch);
  }

  const nested = await Promise.all(entries.map(filesFromEntry));
  return nested.flat();
}

async function filesFromDataTransfer(dataTransfer) {
  const items = Array.from(dataTransfer.items || []);
  const entries = items.map((item) => item.webkitGetAsEntry?.()).filter(Boolean);
  if (entries.length) {
    return (await Promise.all(entries.map(filesFromEntry))).flat();
  }
  return Array.from(dataTransfer.files || []);
}

function filesFromClipboardData(clipboardData) {
  const files = Array.from(clipboardData?.files || []).filter(isSupportedFile);
  if (files.length) {
    return files;
  }

  return Array.from(clipboardData?.items || [])
    .map((item) => (item.kind === "file" ? item.getAsFile() : null))
    .filter((file) => file && isSupportedFile(file));
}

async function filesFromClipboard() {
  if (!navigator.clipboard?.read) {
    setStatus("Clipboard read is not available. Press Ctrl+V instead.");
    return [];
  }

  const clipboardItems = await navigator.clipboard.read();
  const files = [];
  for (const item of clipboardItems) {
    const type = item.types.find((mimeType) => SUPPORTED_TYPES.has(mimeType) || mimeType.startsWith("image/"));
    if (!type) {
      continue;
    }
    const blob = await item.getType(type);
    files.push(new File([blob], `clipboard-image-${files.length + 1}.${extensionFromMimeType(type)}`, { type }));
  }
  return files;
}

async function pasteFromClipboard() {
  try {
    await pasteFilesInOrder(await filesFromClipboard());
  } catch {
    setStatus("Clipboard read was blocked. Press Ctrl+V to paste instead.");
  }
}

function exportPng() {
  if (state.tiles.some((tile) => tile === null)) {
    setStatus("Upload all four images before exporting.");
    return;
  }

  const canvas = document.createElement("canvas");
  canvas.width = OUTPUT_SIZE;
  canvas.height = OUTPUT_SIZE;
  const context = canvas.getContext("2d", { alpha: true });
  context.fillStyle = "#ffffff";
  context.fillRect(0, 0, OUTPUT_SIZE, OUTPUT_SIZE);

  const positions = [
    [0, 0],
    [TILE_SIZE, 0],
    [0, TILE_SIZE],
    [TILE_SIZE, TILE_SIZE],
  ];
  state.tiles.forEach((tile, index) => {
    context.drawImage(tile.canvas, positions[index][0], positions[index][1]);
  });

  const link = document.createElement("a");
  link.download = "playlist-cover.png";
  link.href = canvas.toDataURL("image/png");
  link.click();
  setStatus("Exported 1000x1000 PNG: playlist-cover.png");
}

tiles.forEach((tile) => {
  tile.addEventListener("click", (event) => {
    const index = tileIndexFromEvent(event);
    if (index === null) {
      return;
    }
    selectTile(index);
    singleFileInput.click();
  });

  tile.addEventListener("pointerdown", (event) => {
    const index = tileIndexFromEvent(event);
    if (index === null || !state.tiles[index] || event.button !== 0) {
      return;
    }
    state.pointerStart = {
      index,
      x: event.clientX,
      y: event.clientY,
    };
  });

  tile.addEventListener("pointerup", (event) => {
    const start = state.pointerStart;
    state.pointerStart = null;
    tiles.forEach((item) => item.classList.remove("swap-target"));
    if (!start) {
      return;
    }

    const endIndex = tileIndexFromEvent(event);
    const distance = Math.abs(event.clientX - start.x) + Math.abs(event.clientY - start.y);
    if (distance >= 16 && endIndex !== null && endIndex !== start.index) {
      if (!state.tiles[endIndex]) {
        setStatus("Drag between two filled grid tiles to swap them.");
        return;
      }
      [state.tiles[start.index], state.tiles[endIndex]] = [state.tiles[endIndex], state.tiles[start.index]];
      renderAllTiles();
      setStatus(`Swapped Grid ${start.index + 1} and Grid ${endIndex + 1}.`);
    }
  });

  tile.addEventListener("pointerenter", (event) => {
    const index = tileIndexFromEvent(event);
    if (state.pointerStart && index !== null && index !== state.pointerStart.index) {
      tile.classList.add("swap-target");
    }
  });

  tile.addEventListener("pointerleave", () => {
    tile.classList.remove("swap-target");
  });

  tile.addEventListener("dragover", (event) => {
    event.preventDefault();
    tile.classList.add("drag-over");
  });

  tile.addEventListener("dragleave", () => {
    tile.classList.remove("drag-over");
  });

  tile.addEventListener("drop", async (event) => {
    event.preventDefault();
    tile.classList.remove("drag-over");
    const index = tileIndexFromEvent(event);
    const files = await filesFromDataTransfer(event.dataTransfer);

    if (files.length > 1) {
      await fillEmptyTiles(files);
      return;
    }
    if (!files.length) {
      setStatus("No supported image files were dropped.");
      return;
    }
    await loadFileIntoTile(files[0], index ?? firstEmptyIndex());
  });
});

grid.addEventListener("dragover", (event) => {
  event.preventDefault();
});

window.addEventListener("dragover", (event) => {
  event.preventDefault();
});

window.addEventListener("drop", async (event) => {
  if (event.target.closest(".tile")) {
    return;
  }
  event.preventDefault();
  await fillEmptyTiles(await filesFromDataTransfer(event.dataTransfer));
});

window.addEventListener("paste", async (event) => {
  const files = filesFromClipboardData(event.clipboardData);
  if (!files.length) {
    setStatus("Clipboard has no image or copied image file.");
    return;
  }
  event.preventDefault();
  await pasteFilesInOrder(files);
});

singleFileInput.addEventListener("change", async () => {
  await loadFileIntoTile(singleFileInput.files[0], pasteStartIndex());
  singleFileInput.value = "";
});

bulkFileInput.addEventListener("change", async () => {
  await fillEmptyTiles(Array.from(bulkFileInput.files));
  bulkFileInput.value = "";
});

addButton.addEventListener("click", () => bulkFileInput.click());
pasteButton.addEventListener("click", pasteFromClipboard);
exportButton.addEventListener("click", exportPng);
shuffleButton.addEventListener("click", () => {
  if (state.tiles.some((tile) => tile === null)) {
    setStatus("Load all four grid images before shuffling.");
    return;
  }

  const before = state.tiles.map((tile) => tile.fileName).join("\n");
  shuffle(state.tiles);
  if (state.tiles.map((tile) => tile.fileName).join("\n") === before) {
    state.tiles.push(state.tiles.shift());
  }
  renderAllTiles();
  setStatus("Shuffled all four grid images.");
});

clearButton.addEventListener("click", () => {
  state.tiles = [null, null, null, null];
  state.selectedIndex = null;
  tiles.forEach((tile) => tile.classList.remove("selected-tile"));
  renderAllTiles();
  setStatus("Cleared. Click a tile, drag images in, or press Ctrl+V.");
});
