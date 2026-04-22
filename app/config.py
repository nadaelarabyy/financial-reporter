import os
from dotenv import load_dotenv

load_dotenv()

AZURE_DI_ENDPOINT = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_ENDPOINT")
AZURE_DI_KEY = os.getenv("AZURE_DOCUMENT_INTELLIGENCE_KEY")

# Clustering tolerances
Y_CLUSTER_TOLERANCE = 0.015
X_CLUSTER_TOLERANCE = 0.020

# Table detection heuristics
MIN_LINES_FOR_TABLE_REGION = 4
MIN_NUMERIC_LINE_RATIO = 0.35

# Region expansion (important for clipped headers/labels)
TABLE_REGION_EXPAND_X = 0.03
TABLE_REGION_EXPAND_Y = 0.015

# Header/footer detection
TOP_PAGE_BAND_RATIO = 0.12
BOTTOM_PAGE_BAND_RATIO = 0.10
REPEATED_TEXT_MIN_PAGES = 2

# Routing thresholds
HIGH_CONFIDENCE_THRESHOLD = 0.85
MEDIUM_CONFIDENCE_THRESHOLD = 0.65

OUTPUT_DIR = "outputs"