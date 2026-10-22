"""Download and convert an Indonesian legal PDF to Markdown."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.request import Request, urlopen


class PDFMarkdown:
    """Download legal PDFs, convert them, and format the Markdown output."""

    pdf_url = "https://peraturan.bpk.go.id/Download/32336/UU%20Nomor%2026%20Tahun%202003.pdf"
    default_pdf = "1.pdf"
    default_markdown = "2.md"
    prompt_legal = """
You are an expert assistant specializing in converting Indonesian legal and regulatory documents (laws, regulations, decrees) into Markdown.
Your goal is to format the output so that its structure and layout match the original PDF as closely and precisely as possible.

Strict Rules:
1. PRESERVE LEGAL STRUCTURE:
   - Header/Title/Preamble: Keep centered or bolded at the top.
   - CHAPTERS: Use Heading 2 (`## BAB ...`).
   - ARTICLES: Use Heading 3 (`### Pasal ...`).
2. DO NOT MODIFY CONTENT:
   - Do NOT summarize, edit, omit, or alter any words or clauses within the text.
3. PRESERVE CLAUSES AND LISTS:
   - Clauses starting with numbers in parentheses e.g., `(1)`, `(2)` must be placed on new lines.
   - Lettered lists e.g., `a.`, `b.`, `c.` or numbered lists e.g., `1.`, `2.` must maintain clean and accurate line breaks and indentation.
4. CLOSING AND SIGNATURES:
   - Preserve the closing sections (enactment date, signatory details, and annexes) neatly structured at the end of the document.
""".strip()

    def __init__(self, download_timeout: float = 60.0) -> None:
        self.download_timeout = download_timeout

    @staticmethod
    def humanize_markdown(markdown: str) -> str:
        """Clean PDF extraction artifacts and format legal structure as Markdown."""
        paragraphs: list[str] = []
        current = ""

        def flush() -> None:
            nonlocal current
            if current:
                paragraphs.append(current)
                current = ""

        for raw_line in markdown.splitlines():
            line = raw_line.strip()
            if not line or re.fullmatch(r"-\s*\d+\s*-", line):
                flush()
                continue

            # MarkItDown can misread line fragments as tables. These are text
            # rows, so retain their words and discard only table syntax.
            if line.startswith("|") and line.endswith("|"):
                cells = [cell.strip() for cell in line[1:-1].split("|")]
                if all(not cell or re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
                    continue
                line = " ".join(cell for cell in cells if cell)
                line = re.sub(r"\s+", " ", line).strip()
                if not line:
                    continue

            line = re.sub(r"\s{2,}", " ", line)

            heading_level = None
            if re.fullmatch(r"BAB\s+.+", line, re.IGNORECASE):
                heading_level = 2
            elif re.fullmatch(r"Pasal\s+\d+", line, re.IGNORECASE):
                heading_level = 3
            elif re.fullmatch(r"LAMPIRAN\s+(?:[IVX]+|[0-9]+)", line, re.IGNORECASE):
                heading_level = 2
            elif re.fullmatch(r"(?:I|II)\.\s+.+", line):
                heading_level = 2
            elif line.isupper() and len(line) <= 100 and len(line.split()) <= 12:
                heading_level = 2

            if heading_level:
                flush()
                paragraphs.append(f"{'#' * heading_level} {line}")
                continue

            if re.match(r"^(Menimbang|Mengingat|Menetapkan)\s*:", line, re.IGNORECASE):
                flush()
                label, remainder = line.split(":", 1)
                paragraphs.append(f"**{label.strip()}:**")
                line = remainder.strip()
                if not line:
                    continue

            is_list_item = bool(re.match(r"^(?:\(\d+\)|\d+\.|[a-z]\.)\s+", line))
            if is_list_item:
                flush()
                current = line
                continue

            if current:
                # Preserve a lexical hyphen split across a PDF line wrap.
                current += line if current.endswith("-") and line[:1].islower() else " " + line
            else:
                current = line

        flush()
        return re.sub(r"\n{3,}", "\n\n", "\n\n".join(paragraphs)).strip() + "\n"

    def download_pdf(self, destination: Path) -> None:
        request = Request(
            self.pdf_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urlopen(request, timeout=self.download_timeout) as response:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_suffix(destination.suffix + ".part")
            try:
                with temporary.open("wb") as output:
                    while chunk := response.read(1024 * 64):
                        output.write(chunk)
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)

    def extract_images(self, source: Path, destination: Path) -> tuple[int, int]:
        """Extract embedded images and copy signature-page assets separately.

        Poppler's ``pdfimages`` extracts the embedded image streams. Images on
        pages whose text contains ``ttd.`` are also copied to ``signatures``;
        this keeps the original image files intact while making likely
        signature assets easy to find.
        """
        pdfimages = shutil.which("pdfimages")
        pdftotext = shutil.which("pdftotext")
        if not pdfimages or not pdftotext:
            raise RuntimeError(
                "Image extraction requires Poppler tools (pdfimages and pdftotext). "
                "Install Poppler, for example with `sudo apt install poppler-utils`."
            )

        listing = subprocess.run(
            [pdfimages, "-list", str(source)],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
        image_pages: dict[int, int] = {}
        mask_numbers: set[int] = set()
        for row in listing.splitlines():
            match = re.match(r"\s*(\d+)\s+(\d+)\s+(image|smask)\s", row)
            if match:
                page_number, image_number = map(int, match.groups()[:2])
                image_pages[image_number] = page_number
                if match.group(3) == "smask":
                    mask_numbers.add(image_number)

        destination.mkdir(parents=True, exist_ok=True)
        standard_dir = destination / "standard"
        signature_dir = destination / "signatures"
        standard_dir.mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="pdf-markdown-images-") as temp_dir:
            prefix = Path(temp_dir) / "image"
            subprocess.run(
                [pdfimages, "-all", str(source), str(prefix)],
                check=True,
                capture_output=True,
                text=True,
            )

            signature_pages: set[int] = set()
            for page_number in set(image_pages.values()):
                page_text = subprocess.run(
                    [pdftotext, "-f", str(page_number), "-l", str(page_number), str(source), "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout
                if re.search(r"\bttd\.", page_text, re.IGNORECASE):
                    signature_pages.add(page_number)

            extracted = sorted(Path(temp_dir).glob("image-*"))
            signature_dir.mkdir(exist_ok=True)
            signature_count = 0
            extracted_count = 0
            for image_path in extracted:
                match = re.search(r"image-(\d+)$", image_path.stem)
                if not match:
                    continue
                image_number = int(match.group(1))
                if image_number in mask_numbers:
                    continue
                page_number = image_pages.get(image_number)
                if page_number is None:
                    continue
                filename = f"page-{page_number:03d}-image-{image_number:03d}{image_path.suffix}"
                standard_path = standard_dir / filename
                shutil.copy2(image_path, standard_path)
                extracted_count += 1
                if page_number in signature_pages:
                    shutil.copy2(image_path, signature_dir / filename)
                    signature_count += 1

        return extracted_count, signature_count

    def convert_pdf(self, source: Path, output: Path) -> None:
        from openai import OpenAI
        from markitdown import MarkItDown

        client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")
        converter = MarkItDown(llm_client=client, llm_model="qwen2.5")
        result = converter.convert(str(source), prompt=self.prompt_legal)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(self.humanize_markdown(result.markdown), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="local PDF to convert (downloads the default PDF if omitted)")
    parser.add_argument("-o", "--output", type=Path, default=Path(PDFMarkdown.default_markdown), help="Markdown output path")
    parser.add_argument("--download-timeout", type=float, default=60.0, help="download socket timeout in seconds")
    parser.add_argument(
        "--extract-images",
        type=Path,
        metavar="DIR",
        help="extract embedded images into DIR/standard and signature-page assets into DIR/signatures, then exit",
    )
    args = parser.parse_args(argv)

    app = PDFMarkdown(download_timeout=args.download_timeout)
    source = args.input or Path(PDFMarkdown.default_pdf)
    if args.input is None:
        try:
            print(f"Downloading PDF to {source}...", flush=True)
            app.download_pdf(source)
        except Exception as exc:
            print(f"Error downloading PDF: {exc}", file=sys.stderr)
            return 1
    elif not source.is_file():
        print(f"Input PDF not found: {source}", file=sys.stderr)
        return 2

    if args.extract_images is not None:
        try:
            standard_count, signature_count = app.extract_images(source, args.extract_images)
        except Exception as exc:
            print(f"Error extracting images: {exc}", file=sys.stderr)
            return 1
        print(
            f"Extracted {standard_count} image(s) to {args.extract_images / 'standard'} "
            f"and {signature_count} signature-page image(s) to {args.extract_images / 'signatures'}."
        )
        return 0

    try:
        print(f"Converting {source} to {args.output}...", flush=True)
        app.convert_pdf(source, args.output)
    except Exception as exc:
        print(f"Error converting PDF: {exc}", file=sys.stderr)
        return 1

    print(f"Conversion complete: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
