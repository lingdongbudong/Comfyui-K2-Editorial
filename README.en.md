# Comfyui-K2-Editorial

<p align="right">
  <a href="README.md">中文</a> ｜ <b>English</b>
</p>

> [!CAUTION]
> **⛔ Commercial use prohibited · No repackaging or redistribution** — Copyright © 2026 灵冻不冻 (lingdongbudong). All rights reserved.
> This repository is licensed under the **[PolyForm Strict License 1.0.0](LICENSE)** as of **2026-11-24**.
>
> - **❌ No commercial use** — you may not use this plugin (source, prompt pools, scene / character / outfit libraries, presets, or any derivative) for any commercial purpose: paid distribution, bundling, paid generation services, commercial courses, or as the technical base of a commercial service. Written permission is required.
> - **❌ No repackaging or redistribution** — do not repackage, rename, wrap, re-upload, or include this plugin in third-party bundles, mirror archives, net-disk collections or resource sites, **modified or not**.
> - **❌ Do not remove or alter** this notice, the author attribution, or the source link.
> - **✅ Permitted** — personal non-commercial use (research, study, hobby, generating your own images) and modifying the source for your own use; quoting screenshots / recordings for non-commercial sharing with full attribution and this notice intact.
>
> **Commercial / derivative-work / repost licensing** → [Bilibili DM](https://space.bilibili.com/516891894) for written permission.
> **Legacy versions** published before **2026-11-24** remain under the license they were published with (AGPL-3.0); that grant is not withdrawn.
> Full terms: **[NOTICE.md](NOTICE.md)**.

---

## What it is

A ComfyUI custom node that assembles **long-form Krea2 prompts** (1,500–2,700 words) for the
"white chalk light / futuristic luxury editorial" look. Pick a character, a motif, an aspect
ratio and an outfit — one motif drives the whole image, instead of a random tag pool.

Fully local · zero dependencies · no network access at runtime ·
**generates prompts only, never images**.

## What's inside

| Item | Count |
| --- | --- |
| Motifs | **553** (scene 312 · short-form 226 · poster 15) |
| Layout templates | 8 |
| Characters | **2,432** (snapshot shared with Anima-Wardrobe-V6) |
| Outfit library | SFW only (L0–L1; the `nsfw_outfit` category is excluded) |

## Install

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/lingdongbudong/Comfyui-K2-Editorial.git
```

Restart ComfyUI. No dependencies to install.

## Attribution

- **Motif library** based on reference material from **辞雪沐春** (Bilibili), re-segmented,
  rewritten and expanded into 553 motifs. Redistribution was agreed verbally without a
  specified license text; if the author later states a license, their statement prevails.
- **Character data and artwork snapshots** come from Comfyui-Anima-Wardrobe-V6.
- Character and franchise names belong to their respective rights holders; they are used here
  as descriptive identifiers only.

## Language

Full documentation is in Chinese: **[README.md](README.md)**.

## License

**[PolyForm Strict License 1.0.0](LICENSE)** © 2026 灵冻不冻 (lingdongbudong).

- ❌ **No commercial use** without prior written permission.
- ❌ **No repackaging or redistribution**, modified or not.
- ✅ Personal non-commercial use, and modifying the source for your own use.
- Legacy versions published before 2026-11-24 remain under their original license (AGPL-3.0);
  that grant is not withdrawn.

Commercial / derivative licensing: contact the author via [Bilibili DM](https://space.bilibili.com/516891894).
Full terms: [NOTICE.md](NOTICE.md) · Chinese documentation: [README.md](README.md).
