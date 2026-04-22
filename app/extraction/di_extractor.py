from azure.core.credentials import AzureKeyCredential
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeDocumentRequest

from app.config import AZURE_DI_ENDPOINT, AZURE_DI_KEY
from app.schemas import DIExtractionBundle, PageLines, LineItem
from app.utils.bbox_utils import polygon_to_bbox


def get_client() -> DocumentIntelligenceClient:
    return DocumentIntelligenceClient(
        endpoint=AZURE_DI_ENDPOINT,
        credential=AzureKeyCredential(AZURE_DI_KEY)
    )


def run_layout_analysis(pdf_path: str) -> DIExtractionBundle:
    client = get_client()

    with open(pdf_path, "rb") as f:
        poller = client.begin_analyze_document(
            model_id="prebuilt-layout",
            body=AnalyzeDocumentRequest(bytes_source=f.read())
        )
        result = poller.result()

    pages = []

    for page_idx, page in enumerate(result.pages, start=1):
        page_lines = PageLines(
            page_number=page_idx,
            width=page.width,
            height=page.height,
            lines=[]
        )

        for line in page.lines:
            polygon = list(line.polygon) if line.polygon else None
            bbox = polygon_to_bbox(polygon) if polygon else (0, 0, 0, 0)

            page_lines.lines.append(
                LineItem(
                    text=line.content.strip(),
                    page_number=page_idx,
                    bbox=bbox,
                    polygon=polygon
                )
            )

        pages.append(page_lines)

    return DIExtractionBundle(
        raw_result=result,
        content=result.content or "",
        pages=pages
    )