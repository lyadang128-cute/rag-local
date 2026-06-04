from app.processors.base import BaseProcessor
from app.processors.text import TextProcessor
from app.processors.pdf import PDFProcessor
from app.processors.docx import DocxProcessor
from app.processors.excel import ExcelProcessor
from app.processors.ppt import PPTProcessor
from app.processors.web import WebProcessor
from app.processors.ocr import OCRProcessor

__all__ = [
    "BaseProcessor",
    "TextProcessor",
    "PDFProcessor",
    "DocxProcessor",
    "ExcelProcessor",
    "PPTProcessor",
    "WebProcessor",
    "OCRProcessor",
]
