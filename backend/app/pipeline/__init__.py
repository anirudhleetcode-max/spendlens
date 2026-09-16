"""Receipt understanding pipeline.

    image bytes
      -> preprocess.py   decode, resize, paper crop, denoise, deskew, threshold
      -> ocr.py          Tesseract (words, boxes, confidences) on two image variants
      -> normalise.py    amounts, dates, merchant keys
      -> extract.py      merchant / date / total / tax / payment / items + evidence
      -> validate.py     receipt arithmetic, missing fields, digit repair
      -> confidence.py   documented field-confidence formula, review threshold
      -> receipt.py      parse_lines(): the above as one pure function
    category suggestion: app/services/classifier.py (overrides -> TF-IDF + LogReg -> abstain)
"""
