# Models

Buddy's brain depends on several model weights that are **not** included in
this repository. They are large, and they come from Hugging Face and Ollama,
so they are treated as external dependencies to be downloaded during setup
(the planned installer will fetch these automatically). This file lists exactly
what the code expects and where each one goes.

## Chat / vision / embeddings (served by Ollama)

The brain talks to a local [Ollama](https://ollama.com) server for language and
vision. Pull these with `ollama pull <name>`:

| Purpose     | Model name         | Notes                                    |
|-------------|--------------------|------------------------------------------|
| Chat        | `qwen3.5:9b`       | the main conversational model            |
| Vision      | `gemma3:12b`       | used when an image is attached           |
| Embeddings  | `nomic-embed-text` | text embeddings                          |

Ollama stores these under its own models directory. In this setup that is
`G:\Ollama\models` (set via the `OLLAMA_MODELS` environment variable in the
launcher); adjust to taste.

## Image generation (ComfyUI weights, from Hugging Face)

Image generation calls ComfyUI's node classes directly and loads three weight
files by name. These must be placed in the corresponding ComfyUI model folders
so the loaders can find them:

| Role  | File                                    | ComfyUI folder            |
|-------|-----------------------------------------|---------------------------|
| UNet  | `z_image_turbo_int8_convrot.safetensors`| `models/unet/`            |
| CLIP  | `qwen_3_4b_fp8_mixed.safetensors`       | `models/clip/` (lumina2)  |
| VAE   | `ae.safetensors`                        | `models/vae/`             |

These file names are what the brain references in `brain/buddy_ai.py`
(`load_image_model`). If you substitute different weights, update those names
to match.

## Why they aren't in the repo

Model weights are large binaries, are already distributed by Hugging Face and
Ollama, and would bloat the repository enormously. Keeping them out is the norm
for this kind of project; the installer (planned) will download the correct
versions and place them in the right folders, so a fresh install ends up with
working chat, vision, and image generation without anything being committed
here.
