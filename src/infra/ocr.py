"""Local OCR configuration, without a document-classification dependency."""
def default_ocr():
    import pytesseract
    from src.infra.runtime_config import configure_tesseract,load_config
    configure_tesseract(load_config())
    return pytesseract.image_to_string
