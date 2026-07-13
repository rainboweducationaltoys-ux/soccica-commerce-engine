import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv


load_dotenv()


DATABASE_URL = os.getenv("DATABASE_URL", "")


@contextmanager
def get_connection():
    if not DATABASE_URL:
        raise RuntimeError(
            "DATABASE_URL ortam değişkeni ayarlanmamış."
        )

    connection = psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )

    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def initialize_database() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS orders (
                    id SERIAL PRIMARY KEY,
                    shopify_order_id TEXT UNIQUE NOT NULL,
                    shopify_order_number TEXT,
                    customer_name TEXT,
                    customer_email TEXT,
                    soc_tracking_code TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Order Confirmed',
                    internal_notes TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS shipment_timeline (
                    id SERIAL PRIMARY KEY,
                    soc_tracking_code TEXT NOT NULL,
                    status TEXT NOT NULL,
                    public_note TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )

            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_timeline_soc_code
                ON shipment_timeline(soc_tracking_code)
                """
            )
