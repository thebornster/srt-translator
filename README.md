# srt-translator

A command-line tool that translates `.srt` subtitle files between any two languages using the OpenAI API.

## Features

- Translate a single file, multiple files, or an entire folder in one command
- Works with any language pair
- Auto-detects the source language if you don't specify it
- Preserves subtitle timing, index numbers, and HTML formatting tags (`<i>`, `<b>`, etc.)
- Batches subtitles into efficient API calls with automatic retry on failure
- Output files are saved alongside the originals — nothing gets overwritten

## Requirements

- Python 3.10+
- An [OpenAI API key](https://platform.openai.com/api-keys)

## Installation

```bash
git clone https://github.com/thebornster/srt-translator.git
cd srt-translator
pip install openai
```

## Setup

Set your OpenAI API key as an environment variable:

```bash
# macOS / Linux
export OPENAI_API_KEY=sk-...

# Windows (Command Prompt)
set OPENAI_API_KEY=sk-...

# Windows (PowerShell)
$env:OPENAI_API_KEY="sk-..."
```

Alternatively, pass it directly with `--api-key` on each run.

## Usage

```bash
# Translate a single file (auto-detects source language, outputs to English)
python translate_srt.py movie.srt

# Specify a custom output path
python translate_srt.py movie.srt -o movie_english.srt

# Translate multiple files at once
python translate_srt.py ep01.srt ep02.srt ep03.srt

# Translate every .srt in a folder
python translate_srt.py /path/to/subtitles/

# Specify source and target languages explicitly
python translate_srt.py movie.srt --from Japanese --to Spanish

# Use a different model
python translate_srt.py movie.srt --model gpt-4.1

# Combine options
python translate_srt.py /subtitles/ --from Arabic --to French --model gpt-4.1-mini --batch-size 30
```

### Output naming

When no `-o` path is given, the translated file is saved next to the original with the target language appended to the filename:

```
movie.srt           →  movie_english.srt
episode01.srt       →  episode01_spanish.srt
```

## Options

| Flag | Default | Description |
|------|---------|-------------|
| `--from LANG` | `auto` | Source language. `auto` = model detects it automatically |
| `--to LANG` | `English` | Target language |
| `--model MODEL` | `gpt-4.1-mini` | OpenAI model to use |
| `--batch-size N` | `20` | Number of subtitles per API call |
| `--retries N` | `3` | Max retries on API failure |
| `--retry-delay N` | `5` | Seconds to wait between retries |
| `-o, --output PATH` | — | Output file path (single-file mode only) |
| `--api-key KEY` | — | OpenAI API key (overrides environment variable) |

## Choosing a model

The default `gpt-4.1-mini` is recommended for most use cases — it produces high-quality translations at low cost. If you need higher accuracy for complex or literary dialogue, use `gpt-4.1` or `gpt-4o`.

### Estimated cost with `gpt-4.1-mini`

| Files | Episode length | Estimated cost |
|-------|---------------|----------------|
| 1 | 1 hour | ~$0.02 |
| 10 | 1 hour | ~$0.20 |
| 30 | 1 hour | ~$0.60–$0.80 |

Prices are based on ~1,000 subtitle lines per hour-long episode at $0.40/1M input tokens and $1.60/1M output tokens.

## Example output

```
Files to translate: 3

→ episode01.srt
  847 subtitles | 43 batches | auto-detect → English | model: gpt-4.1-mini
  batch 1/43  (1–20) … done
  batch 2/43  (21–40) … done
  ...
  saved → episode01_english.srt

→ episode02.srt
  ...
```

## License

MIT
