import argparse
import hashlib
import json
import logging
import os
import subprocess
import csv
import yaml
from pathlib import Path
import tempfile
import torch

def setup_logging():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def hash_file(filepath: Path) -> str:
    """Records SHA-256 of the original file; never alters it."""
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return hasher.hexdigest()

def run_ocr(input_pdf: Path, output_pdf: Path):
    """Runs OCRmyPDF with Tesseract Dutch (-l nld), skipping pages that already have good text."""
    cmd = [
        "ocrmypdf",
        "-l", "nld",
        "--skip-text",
        str(input_pdf),
        str(output_pdf)
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.CalledProcessError as e:
        logging.error(f"OCR failed for {input_pdf}: {e}")
        raise

def extract_text_per_page(pdf_path: Path):
    """Extracts text page by page, keeping page numbers."""
    import fitz # pymupdf
    doc = fitz.open(pdf_path)
    pages_text = []
    for page_num in range(len(doc)):
        page = doc.load_page(page_num)
        text = page.get_text("text")
        pages_text.append({
            "page": page_num + 1,
            "dutch_text": text
        })
    return pages_text

def translate_dutch_to_english(pages_text, translator):
    """Translates Dutch to English, sentence-chunked and reassembled in original line order."""
    import nltk

    try:
        nltk.data.find('tokenizers/punkt')
        nltk.data.find('tokenizers/punkt_tab')
    except LookupError:
        nltk.download('punkt', quiet=True)
        nltk.download('punkt_tab', quiet=True)

    for page in pages_text:
        dutch_text = page.get("dutch_text", "")
        if not dutch_text.strip():
            page["english_text"] = ""
            continue

        # Keep original line order by splitting by lines first
        lines = dutch_text.splitlines()
        english_lines = []

        for line in lines:
            if not line.strip():
                english_lines.append(line)
                continue

            sentences = nltk.sent_tokenize(line)
            english_sentences = []
            for sentence in sentences:
                if not sentence.strip():
                    english_sentences.append(sentence)
                    continue
                try:
                    result = translator(sentence)
                    english_sentences.append(result[0]['translation_text'])
                except Exception as e:
                    logging.warning(f"Translation failed for sentence, keeping original: {e}")
                    english_sentences.append(sentence)

            english_lines.append(" ".join(english_sentences))

        page["english_text"] = "\n".join(english_lines)

    return pages_text

def do_litellm_tagging(text: str) -> dict:
    try:
        from litellm import completion

        with open("config/tagging_fields.yaml", "r") as f:
            config = yaml.safe_load(f)

        prompt = f"Extract the following fields from the provided text based on this configuration:\n{yaml.dump(config)}\n\nText:\n{text[:8000]}"

        response = completion(
            model="gpt-3.5-turbo", # or any default litellm model configured in environment
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        logging.error(f"LiteLLM tagging failed: {e}")
        return {}

def main():
    parser = argparse.ArgumentParser(description="Corpus processing pipeline")
    parser.add_argument("--input_dir", type=str, required=True, help="Input directory containing PDFs")
    parser.add_argument("--output_dir", type=str, required=True, help="Output directory for text and JSON")
    parser.add_argument("--log_file", type=str, required=True, help="CSV file for results log")
    parser.add_argument("--do_tagging", action="store_true", help="Run LiteLLM tagging")
    parser.add_argument("--batch", type=int, help="Batch index for parallel runs")
    parser.add_argument("--num_batches", type=int, help="Total number of batches")
    args = parser.parse_args()

    setup_logging()
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log_file_path = Path(args.log_file)
    log_file_path.parent.mkdir(parents=True, exist_ok=True)
    processed_files = set()

    log_exists = log_file_path.exists()
    if log_exists:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get('status') == 'success':
                    processed_files.add(row['document_name'])

    pdf_files = list(input_dir.glob('**/*.pdf'))
    pdf_files.sort()

    if args.batch is not None and args.num_batches is not None:
        batch_size = max(1, len(pdf_files) // args.num_batches)
        start_idx = args.batch * batch_size
        end_idx = start_idx + batch_size if args.batch < args.num_batches - 1 else len(pdf_files)
        pdf_files = pdf_files[start_idx:end_idx]

    if not pdf_files:
        logging.info("No files to process.")
        return

    device = 0 if torch.cuda.is_available() else -1
    logging.info(f"Loading translation model on device {device}...")
    from transformers import pipeline
    translator = pipeline("translation", model="Helsinki-NLP/opus-mt-nl-en", device=device)

    with open(log_file_path, 'a', newline='', encoding='utf-8') as f:
        fieldnames = ['document_name', 'hash', 'pages', 'status']
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not log_exists:
            writer.writeheader()

        for pdf_file in pdf_files:
            doc_name = pdf_file.name
            if doc_name in processed_files:
                logging.info(f"Skipping {doc_name}, already processed.")
                continue

            logging.info(f"Processing {doc_name}...")
            try:
                doc_hash = hash_file(pdf_file)

                with tempfile.TemporaryDirectory() as temp_dir:
                    ocr_pdf = Path(temp_dir) / "ocr.pdf"
                    run_ocr(pdf_file, ocr_pdf)

                    pages_data = extract_text_per_page(ocr_pdf)

                pages_data = translate_dutch_to_english(pages_data, translator)

                output_data = {
                    "document_name": doc_name,
                    "hash": doc_hash,
                    "pages": pages_data
                }

                if args.do_tagging:
                    full_english_text = " ".join([p.get("english_text", "") for p in pages_data])
                    tags = do_litellm_tagging(full_english_text)
                    output_data["tags"] = tags

                out_json = output_dir / f"{pdf_file.stem}.json"
                with open(out_json, "w", encoding="utf-8") as out_f:
                    json.dump(output_data, out_f, ensure_ascii=False, indent=2)

                writer.writerow({
                    'document_name': doc_name,
                    'hash': doc_hash,
                    'pages': len(pages_data),
                    'status': 'success'
                })
                f.flush()
                logging.info(f"Successfully processed {doc_name}")

            except Exception as e:
                logging.error(f"Failed to process {doc_name}: {e}")
                writer.writerow({
                    'document_name': doc_name,
                    'hash': hash_file(pdf_file) if pdf_file.exists() else '',
                    'pages': 0,
                    'status': f'failed: {str(e)}'
                })
                f.flush()

if __name__ == "__main__":
    main()
