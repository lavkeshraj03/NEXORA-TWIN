"""Optional operator-hosted OCR contract; no automatic third-party selection."""
import httpx

from app.core.config import get_settings


def pdf_pages(raw: bytes) -> dict[int, str]:
    settings = get_settings()
    if not settings.ocr_url:
        raise ValueError("Scanned/empty PDF page requires OCR; OCR is not configured")
    key = settings.ocr_api_key.get_secret_value()
    headers = {"Content-Type": "application/pdf"}
    if key:
        headers["Authorization"] = "Bearer " + key
    try:
        with httpx.Client(timeout=45, follow_redirects=False) as client:
            with client.stream("POST", settings.ocr_url, headers=headers, content=raw) as response:
                if response.status_code != 200:
                    raise ValueError("Configured OCR service rejected the document")
                content = bytearray()
                for chunk in response.iter_bytes():
                    if len(content) + len(chunk) > 1024 * 1024:
                        raise ValueError("OCR response exceeds the processing limit")
                    content.extend(chunk)
        import json
        pages = json.loads(content)["pages"]
        if not isinstance(pages, list) or not 1 <= len(pages) <= 100:
            raise ValueError()
        result = {}
        for page in pages:
            number, text = page["number"], page["text"]
            if type(number) is not int or not 1 <= number <= 100 or not isinstance(text, str) or number in result:
                raise ValueError()
            result[number] = text
        if sum(len(text) for text in result.values()) > 200000:
            raise ValueError()
        return result
    except Exception as error:
        if isinstance(error, ValueError) and str(error).startswith(("Configured OCR", "OCR response")):
            raise
        raise ValueError("Configured OCR service is unavailable or returned invalid page text") from None
