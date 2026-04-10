#!/usr/bin/env python3
"""
SRT Subtitle Translator
Translates .srt subtitle files between any two languages using the OpenAI API.

Usage:
    python translate_srt.py input.srt
    python translate_srt.py input.srt -o output.srt
    python translate_srt.py *.srt
    python translate_srt.py /path/to/folder/
    python translate_srt.py input.srt --from Japanese --to Spanish
    python translate_srt.py input.srt --model gpt-4.1
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

try:
    from openai import OpenAI
except ImportError:
    sys.exit("openai package not found.  Run:  pip install openai")

# ── Defaults (override via CLI flags) ────────────────────────────────────────
DEFAULT_MODEL       = "gpt-4.1-mini"
DEFAULT_SOURCE_LANG = "auto"          # "auto" = ask the model to detect
DEFAULT_TARGET_LANG = "English"
DEFAULT_BATCH_SIZE  = 20              # subtitles per API call
DEFAULT_MAX_RETRIES = 3
DEFAULT_RETRY_DELAY = 5               # seconds between retries
# ─────────────────────────────────────────────────────────────────────────────


def parse_srt(text: str) -> list[dict]:
    """Parse SRT text into a list of subtitle dicts."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    blocks = re.split(r"\n\s*\n", text)
    subs = []
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        if "-->" not in lines[1]:
            continue
        subs.append({
            "idx":     lines[0].strip(),
            "timing":  lines[1].strip(),
            "content": "\n".join(lines[2:]).strip(),
        })
    return subs


def build_srt(subs: list[dict]) -> str:
    """Reconstruct SRT text from a list of subtitle dicts."""
    return "\n\n".join(
        f"{s['idx']}\n{s['timing']}\n{s['content']}" for s in subs
    ) + "\n"


def make_prompt(lines: list[str], source_lang: str, target_lang: str) -> str:
    if source_lang.lower() == "auto":
        lang_instruction = (
            f"Detect the language of the following subtitle lines and translate "
            f"them into natural, fluent {target_lang}."
        )
    else:
        lang_instruction = (
            f"Translate the following {source_lang} subtitle lines into "
            f"natural, fluent {target_lang}."
        )

    return (
        f"{lang_instruction} "
        "Preserve any HTML formatting tags such as <i> or <b>.\n\n"
        "Reply ONLY with a JSON array of strings — one translated string per "
        "input line, in the same order. "
        "No explanations, no markdown fences, no extra text.\n\n"
        f"Input:\n{json.dumps(lines, ensure_ascii=False)}"
    )


def translate_batch(
    client: OpenAI,
    lines: list[str],
    source_lang: str,
    target_lang: str,
    model: str,
    max_retries: int,
    retry_delay: int,
) -> list[str]:
    """Send one batch to the API and return translated lines."""
    prompt = make_prompt(lines, source_lang, target_lang)

    for attempt in range(1, max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            raw = response.choices[0].message.content.strip()
            raw = re.sub(r"^```json\s*", "", raw)
            raw = re.sub(r"^```\s*",     "", raw)
            raw = re.sub(r"\s*```$",     "", raw).strip()
            result = json.loads(raw)
            if isinstance(result, list) and len(result) == len(lines):
                return result
            print(
                f"  [warn] Response had {len(result)} items for {len(lines)} "
                "inputs — keeping originals for this batch."
            )
            return lines
        except json.JSONDecodeError as e:
            print(f"  [warn] JSON parse error (attempt {attempt}/{max_retries}): {e}")
        except Exception as e:
            print(f"  [warn] API error (attempt {attempt}/{max_retries}): {e}")
        if attempt < max_retries:
            time.sleep(retry_delay)

    print("  [error] All retries failed — keeping originals for this batch.")
    return lines


def translate_srt(
    client: OpenAI,
    src_path: Path,
    dst_path: Path,
    source_lang: str,
    target_lang: str,
    model: str,
    batch_size: int,
    max_retries: int,
    retry_delay: int,
) -> None:
    """Translate one SRT file and write the result to dst_path."""
    print(f"\n→ {src_path.name}")

    try:
        text = src_path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        text = src_path.read_text(encoding="latin-1")

    subs = parse_srt(text)
    if not subs:
        print("  [skip] No subtitle blocks found.")
        return

    total   = len(subs)
    batches = (total + batch_size - 1) // batch_size
    src_label = "auto-detect" if source_lang.lower() == "auto" else source_lang
    print(f"  {total} subtitles | {batches} batches | {src_label} → {target_lang} | model: {model}")

    for b in range(batches):
        start = b * batch_size
        end   = min(start + batch_size, total)
        lines = [subs[i]["content"] for i in range(start, end)]

        print(f"  batch {b+1}/{batches}  ({start+1}–{end}) …", end=" ", flush=True)
        translated = translate_batch(
            client, lines, source_lang, target_lang,
            model, max_retries, retry_delay,
        )
        for i, t in enumerate(translated):
            subs[start + i]["content"] = t
        print("done")

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path.write_text(build_srt(subs), encoding="utf-8")
    print(f"  saved → {dst_path}")


def collect_inputs(paths: list[str]) -> list[Path]:
    """Expand a mix of files and directories into a flat list of .srt paths."""
    collected = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            found = sorted(path.glob("*.srt"))
            if not found:
                print(f"[warn] No .srt files found in directory: {p}")
            collected.extend(found)
        elif path.suffix.lower() == ".srt":
            if path.exists():
                collected.append(path)
            else:
                print(f"[warn] File not found: {p}")
        else:
            print(f"[skip] Not an .srt file: {p}")
    return collected


def make_output_path(src: Path, output_arg: str | None, target_lang: str, multiple: bool) -> Path:
    """Determine the output path for a translated file."""
    if output_arg and not multiple:
        return Path(output_arg)
    suffix = f"_{target_lang.lower().replace(' ', '_')}"
    stem = src.stem
    if not stem.endswith(suffix):
        stem += suffix
    return src.with_name(stem + src.suffix)


def main():
    parser = argparse.ArgumentParser(
        description="Translate .srt subtitle files using the OpenAI API.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python translate_srt.py movie.srt
  python translate_srt.py movie.srt -o movie_english.srt
  python translate_srt.py *.srt
  python translate_srt.py /folder/with/subtitles/
  python translate_srt.py movie.srt --from Japanese --to Spanish
  python translate_srt.py movie.srt --model gpt-4.1 --batch-size 30
        """,
    )
    parser.add_argument(
        "inputs", nargs="+",
        help=".srt file(s) or folder(s) containing .srt files",
    )
    parser.add_argument(
        "-o", "--output",
        help="Output file path (single-file mode only)",
    )
    parser.add_argument(
        "--from", dest="source_lang", default=DEFAULT_SOURCE_LANG,
        metavar="LANG",
        help=f'Source language (default: "{DEFAULT_SOURCE_LANG}" = auto-detect)',
    )
    parser.add_argument(
        "--to", dest="target_lang", default=DEFAULT_TARGET_LANG,
        metavar="LANG",
        help=f'Target language (default: "{DEFAULT_TARGET_LANG}")',
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL,
        help=f"OpenAI model to use (default: {DEFAULT_MODEL})",
    )
    parser.add_argument(
        "--batch-size", type=int, default=DEFAULT_BATCH_SIZE,
        help=f"Subtitles per API call (default: {DEFAULT_BATCH_SIZE})",
    )
    parser.add_argument(
        "--retries", type=int, default=DEFAULT_MAX_RETRIES,
        help=f"Max retries on API failure (default: {DEFAULT_MAX_RETRIES})",
    )
    parser.add_argument(
        "--retry-delay", type=int, default=DEFAULT_RETRY_DELAY,
        help=f"Seconds between retries (default: {DEFAULT_RETRY_DELAY})",
    )
    parser.add_argument(
        "--api-key",
        help="OpenAI API key (overrides OPENAI_API_KEY environment variable)",
    )
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        sys.exit(
            "No API key found.\n"
            "Set it with:    export OPENAI_API_KEY=sk-...\n"
            "Or pass it via: --api-key sk-..."
        )

    client = OpenAI(api_key=api_key)
    files  = collect_inputs(args.inputs)

    if not files:
        sys.exit("No .srt files to translate.")

    multiple = len(files) > 1
    if multiple and args.output:
        print("[warn] --output is ignored when translating multiple files.")

    print(f"Files to translate: {len(files)}")

    for src in files:
        dst = make_output_path(src, args.output, args.target_lang, multiple)
        translate_srt(
            client       = client,
            src_path     = src,
            dst_path     = dst,
            source_lang  = args.source_lang,
            target_lang  = args.target_lang,
            model        = args.model,
            batch_size   = args.batch_size,
            max_retries  = args.retries,
            retry_delay  = args.retry_delay,
        )

    print("\nAll done.")


if __name__ == "__main__":
    main()
