# InvoiceProcessingApp/shared_code/pdf_utils.py
"""
This module provides utility functions for processing PDF documents,
primarily for converting PDF pages into image formats.
"""
import fitz
import base64
import logging

def convert_pdf_bytes_to_images_base64(pdf_bytes: bytes, dpi=200) -> list[str] | None:
    """
    Converts each page of a PDF, provided as byte content, into a list of base64 encoded PNG image strings.

    Args:
        pdf_bytes: The byte content of the PDF file.
        dpi: The resolution (dots per inch) for rendering the PDF pages to images.

    Returns:
        A list of base64 encoded PNG image strings, one for each page of the PDF.
        Returns None if an error occurs during conversion.
    """
    base64_images = []
    try:
        pdf_document = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page_num in range(len(pdf_document)):
            page = pdf_document.load_page(page_num)
            pix = page.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            base64_encoded_image = base64.b64encode(img_bytes).decode('utf-8')
            base64_images.append(base64_encoded_image)
        
        pdf_document.close()
        logging.info(f"Successfully converted PDF to {len(base64_images)} base64 PNG images.")
        return base64_images
    except Exception as e:
        logging.error(f"Error converting PDF to images: {e}", exc_info=True)
        return None