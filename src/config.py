from pathlib import Path


# Projenin ana klasörü
BASE_DIR = Path(__file__).resolve().parent.parent

# Girdi ve çıktı klasörleri
INPUT_DIR = BASE_DIR / "input"
OUTPUT_DIR = BASE_DIR / "output"
IMAGES_DIR = BASE_DIR / "images"
LOGS_DIR = BASE_DIR / "logs"

# Dosya konumları
PRODUCTS_FILE = INPUT_DIR / "products.csv"
AMAZON_OUTPUT_FILE = OUTPUT_DIR / "amazon_products.csv"
SHOPIFY_OUTPUT_FILE = OUTPUT_DIR / "shopify_products.csv"
ERROR_OUTPUT_FILE = OUTPUT_DIR / "errors.csv"
PROGRESS_FILE = OUTPUT_DIR / "progress.csv"

# Tarayıcı ayarları
HEADLESS = True
PAGE_TIMEOUT = 90_000
PRODUCT_TITLE_TIMEOUT = 30_000

VIEWPORT_WIDTH = 1440
VIEWPORT_HEIGHT = 1000

LOCALE = "en-AE"

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/149.0.0.0 Safari/537.36"
)

# Scraper ayarları
WAIT_BETWEEN_PRODUCTS_MIN = 2
WAIT_BETWEEN_PRODUCTS_MAX = 5
MAX_RETRIES = 3