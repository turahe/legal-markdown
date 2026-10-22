# pdf-markdown

[![pdf-markdown](assets/badge.svg)](https://github.com/turahe/legal-markdown)
[![Python](https://img.shields.io/badge/python-3.14%2B-3776AB?style=flat-square)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-2ea44f?style=flat-square)](LICENSE)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://docs.astral.sh/uv/)
[![MarkItDown](https://img.shields.io/badge/MarkItDown-powered-00ADD8?style=flat-square)](https://github.com/microsoft/markitdown)

Convert Indonesian legal and regulatory PDFs — *peraturan BPK*, keputusan, undang-undang — into clean, structured Markdown.

The tool downloads a regulation from [peraturan.bpk.go.id](https://peraturan.bpk.go.id), converts it with [MarkItDown](https://github.com/microsoft/markitdown) driven by a local Ollama model, then rebuilds the legal document structure: `BAB` and `Pasal` become real headings, clauses and lettered lists keep their own lines, page-number artifacts and broken table rows are removed, and hyphenated line wraps are rejoined. Text is never summarized, edited, or omitted.

> The published package is `pdf-markdown`; the repository is [turahe/legal-markdown](https://github.com/turahe/legal-markdown).

## Features

- **Bundled default document** — downloads a regulation from `peraturan.bpk.go.id` automatically, or converts any local PDF. The URL and default file names live in `PDFMarkdown` (`src/pdf_markdown/__init__.py:18`).
- **Layout-aware conversion** — MarkItDown with an OpenAI-compatible client pointed at a local Ollama model (`qwen2.5`) and a legal-document prompt.
- **Legal structure recovery** — `BAB` → `##`, `Pasal` → `###`, `LAMPIRAN` → `##`, bold `Menimbang:` / `Mengingat:` / `Menetapkan:` labels, one list item per line.
- **Artifact cleanup** — strips page markers (`- 12 -`), collapses whitespace, flattens text rows that MarkItDown misread as tables, rejoins words split across line wraps.
- **Image extraction** — pulls embedded images out of the PDF with Poppler and separates signature-page assets.
- **Single CLI** — `pdf-markdown input.pdf -o out.md`.

## Requirements

| Requirement | Why | Install |
| --- | --- | --- |
| Python 3.14+ | Runtime (`requires-python = ">=3.14"`) | [python.org](https://www.python.org/downloads/) |
| [uv](https://docs.astral.sh/uv/) | Package manager / build backend | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| [Ollama](https://ollama.com) | Local LLM used by MarkItDown | `ollama pull qwen2.5` |
| Poppler (`pdfimages`, `pdftotext`) | Only needed for `--extract-images` | `sudo apt install poppler-utils` |
| Network access | Only for the bundled download | — |

Ollama must be running and the model pulled:

```bash
ollama pull qwen2.5
ollama serve
```

## Installation

From source with uv:

```bash
git clone https://github.com/turahe/legal-markdown.git
cd legal-markdown
uv sync
uv run pdf-markdown --help
```

Or with a plain virtual environment:

```bash
python3.14 -m venv .venv
source .venv/bin/activate
pip install -e .
pdf-markdown --help
```

## Usage

Convert the bundled regulation (downloads it first if it is not present):

```bash
uv run pdf-markdown
```

Convert a local PDF:

```bash
uv run pdf-markdown path/to/peraturan.pdf -o path/to/peraturan.md
```

Extract images without converting:

```bash
uv run pdf-markdown path/to/peraturan.pdf --extract-images assets/
```

## CLI reference

```
pdf-markdown [-h] [-o OUTPUT] [--download-timeout DOWNLOAD_TIMEOUT]
             [--extract-images DIR] [input]
```

| Argument | Default | Description |
| --- | --- | --- |
| `input` | bundled regulation | Local PDF to convert. When omitted, the default PDF (`PDFMarkdown.default_pdf`) is downloaded from `peraturan.bpk.go.id`. |
| `-o`, `--output` | `Salinan_PBPK_1_Tahun_2026.md` | Markdown output path. |
| `--download-timeout` | `60.0` | Download socket timeout, in seconds. |
| `--extract-images DIR` | — | Extract embedded images into `DIR/standard` and signature-page assets into `DIR/signatures`, then exit. |

Exit codes: `0` success, `1` download/convert/extraction error, `2` input PDF not found.

## How it works

```
input.pdf
   │
   ├─ download ──────────► peraturan.bpk.go.id  (browser-like UA, atomic .part → rename)
   │
   ├─ convert ───────────► MarkItDown + Ollama (http://localhost:11434/v1, model qwen2.5)
   │                          with the legal-document prompt
   │
   ├─ post-process ──────► PDFMarkdown.humanize_markdown()
   │                          · drop empty lines and page markers
   │                          · repair text rows misread as tables
   │                          · detect headings (BAB / Pasal / LAMPIRAN / roman)
   │                          · bold Menimbang / Mengingat / Menetapkan
   │                          · keep (1) / 1. / a. items on their own lines
   │                          · rejoin hyphenated line wraps
   │
   └─ write ──────────────► output.md (UTF-8)
```

Relevant code: `PDFMarkdown.download_pdf` (`src/pdf_markdown/__init__.py:113`), `PDFMarkdown.convert_pdf` (`src/pdf_markdown/__init__.py:215`), `PDFMarkdown.humanize_markdown` (`src/pdf_markdown/__init__.py:43`), and the prompt in `PDFMarkdown.prompt_legal` (`src/pdf_markdown/__init__.py:21`).

The Ollama endpoint and model are configured in `convert_pdf` (`src/pdf_markdown/__init__.py:219`) — edit them there to point at a different server or model.

## Formatting rules

| Source pattern | Markdown output |
| --- | --- |
| `BAB I ...` | `## BAB I ...` |
| `Pasal 12` | `### Pasal 12` |
| `LAMPIRAN I` | `## LAMPIRAN I` |
| `I. ...`, `II. ...` | `## I. ...` |
| Short all-caps line (≤ 100 chars, ≤ 12 words) | `## ...` |
| `Menimbang:`, `Mengingat:`, `Menetapkan:` | `**Menimbang:**` |
| `(1)`, `1.`, `a.` items | one item per paragraph, indentation preserved |
| `- 12 -` page marker | removed |
| Text row misread as a table | flattened into one line |

Content is preserved verbatim; only structural markup is applied.

## Image extraction

```bash
uv run pdf-markdown doc.pdf --extract-images out/
```

```
out/
├── standard/    # every embedded image, e.g. page-012-image-034.png
└── signatures/  # images from pages whose text contains "ttd." (signature blocks)
```

Images keep their original format. Alpha masks (`smask` streams) are skipped so they do not appear as black rectangles.

## Example output

```markdown
**Menetapkan:**

UNDANG-UNDANG TENTANG PERUBAHAN ATAS UNDANG-UNDANG

## NOMOR 29 TAHUN 2002 TENTANG ANGGARAN PENDAPATAN DAN

(1) Penerimaan perpajakan sebagaimana dimaksud dalam Pasal 3 ayat (2) terdiri atas :

a. Pajak dalam negeri;

b. Pajak perdagangan internasional.
```

Words are preserved exactly as extracted from the PDF, so spacing artifacts that already exist in the source text layer are carried over as-is.

See [`Salinan_PBPK_1_Tahun_2026.md`](Salinan_PBPK_1_Tahun_2026.md) for the full conversion of the bundled document.

## Project layout

```
src/pdf_markdown/__init__.py       # PDFMarkdown class and CLI entry point
assets/badge.svg                    # project badge
Salinan_PBPK_1_Tahun_2026.pdf      # sample source document
Salinan_PBPK_1_Tahun_2026.md       # converted output
```

## Development

```bash
uv sync           # create the environment
uv run pdf-markdown --help
```

## License

MIT — see [LICENSE](LICENSE). Copyright (c) 2026 Nur Wachid.
