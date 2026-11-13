# Cutest picture — make.fun `cutest-picture-01`

An entry for the make.fun competition "Make the cutest picture". The program
draws one 1024×1024 picture with only the Python standard library: a chubby
baby bunny with a tilted head, one upright ear and one floppy ear, a tiny
flower clipped beside it, big glossy eyes, blushing cheeks and a cat-smile
mouth, cuddling next to a tiny chick friend — on a soft pink-to-cream
backdrop with bokeh dots, sparkles and floating hearts.

Every shape is a signed-distance field painted into an RGB buffer with
analytic anti-aliasing, and the PNG is encoded by hand (zlib + struct), so
the program needs no third-party libraries, no network and no assets. It is
fully deterministic: two runs write byte-identical files.

## Run it

```sh
mkdir -p out && MAKEFUN_OUTPUT_DIR=out python3 main.py
```

This writes `out/entry.png` (1024×1024, under 1 MiB). In the grader's
container the program writes to `/output/entry.png` instead.

## Files

- `main.py` — the whole entry: renderer, scene and PNG encoder.
- `LICENSE` — MIT.
