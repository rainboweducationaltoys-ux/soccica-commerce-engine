import base64
import hashlib
import hmac
import os
import random
import string
from functools import wraps

import psycopg2.errors
from dotenv import load_dotenv
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import (
    check_password_hash,
    generate_password_hash,
)

from db import get_connection, initialize_database


load_dotenv()


app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "")

ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
SHOPIFY_WEBHOOK_SECRET = os.getenv("SHOPIFY_WEBHOOK_SECRET", "")

STATUS_STAGES = [
    "Order Confirmed",
    "Purchased",
    "Supplier Processing",
    "International Transit",
    "Arrived UAE",
    "Out for Delivery",
    "Delivered",
]

SOC_CODE_ALPHABET = string.ascii_uppercase + string.digits

initialize_database()


def get_order_by_code(soc_code: str):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE soc_tracking_code = %s
                """,
                (soc_code,),
            )

            return cursor.fetchone()


def get_timeline_for_code(soc_code: str):
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT status, public_note, created_at
                FROM shipment_timeline
                WHERE soc_tracking_code = %s
                ORDER BY created_at ASC
                """,
                (soc_code,),
            )

            return cursor.fetchall()


def emails_match(email_a: str, email_b: str) -> bool:
    return bool(
        email_a
        and email_b
        and email_a.strip().lower() == email_b.strip().lower()
    )


@app.route("/")
def index():
    code = request.args.get("code", "").strip().upper()

    order = None
    timeline = None
    authorized = False

    if code:
        order = get_order_by_code(code)

        if order:
            # Timeline is public to anyone with the code — same data EMX
            # shows for any tracking number. Login only gates the extra
            # "Ordered by" detail below, not the timeline itself.
            timeline = get_timeline_for_code(code)

            session_email = session.get("customer_email", "")

            if session_email:
                authorized = emails_match(
                    session_email,
                    order.get("customer_email", ""),
                )

    return render_template(
        "landing.html",
        code=code,
        order=order,
        authorized=authorized,
        timeline=timeline,
        status_stages=STATUS_STAGES,
        customer_email=session.get("customer_email"),
        customer_name=session.get("customer_name"),
    )


@app.route("/track/<soc_code>")
def track_redirect(soc_code: str):
    return redirect(
        url_for(
            "index",
            code=soc_code.strip().upper(),
        )
    )


@app.route(
    "/register",
    methods=["GET", "POST"],
)
def register():
    code = (
        request.values.get("code", "")
        .strip()
        .upper()
    )

    if request.method == "POST":
        email = (
            request.form.get("email", "")
            .strip()
            .lower()
        )
        password = request.form.get("password", "")
        name = request.form.get("name", "").strip()
        code = (
            request.form.get("code", "")
            .strip()
            .upper()
        )

        if "@" not in email:
            flash("Please enter a valid email address.")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.")
        else:
            password_hash = generate_password_hash(
                password
            )

            try:
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            INSERT INTO customers (
                                email,
                                password_hash,
                                name
                            )
                            VALUES (%s, %s, %s)
                            """,
                            (
                                email,
                                password_hash,
                                name,
                            ),
                        )

                session["customer_email"] = email
                session["customer_name"] = name

                return redirect(
                    url_for(
                        "index",
                        code=code or None,
                    )
                )

            except psycopg2.errors.UniqueViolation:
                flash(
                    "An account with this email already exists. "
                    "Try logging in instead."
                )

    return render_template(
        "register.html",
        code=code,
    )


@app.route(
    "/login",
    methods=["GET", "POST"],
)
def login():
    code = (
        request.values.get("code", "")
        .strip()
        .upper()
    )

    if request.method == "POST":
        email = (
            request.form.get("email", "")
            .strip()
            .lower()
        )
        password = request.form.get("password", "")
        code = (
            request.form.get("code", "")
            .strip()
            .upper()
        )

        with get_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT email, password_hash, name
                    FROM customers
                    WHERE email = %s
                    """,
                    (email,),
                )

                customer = cursor.fetchone()

        if customer and check_password_hash(
            customer["password_hash"],
            password,
        ):
            session["customer_email"] = customer["email"]
            session["customer_name"] = customer["name"]

            return redirect(
                url_for(
                    "index",
                    code=code or None,
                )
            )

        flash("Invalid email or password.")

    return render_template(
        "login.html",
        code=code,
    )


@app.route("/logout")
def logout():
    session.pop("customer_email", None)
    session.pop("customer_name", None)
    return redirect(url_for("index"))


def generate_soc_code() -> str:
    suffix = "".join(
        random.choices(SOC_CODE_ALPHABET, k=8)
    )

    return f"SOC{suffix}"


def verify_shopify_webhook(
    raw_body: bytes,
    provided_signature: str,
) -> bool:
    if not SHOPIFY_WEBHOOK_SECRET or not provided_signature:
        return False

    computed_signature = base64.b64encode(
        hmac.new(
            SHOPIFY_WEBHOOK_SECRET.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).digest()
    ).decode("utf-8")

    return hmac.compare_digest(
        provided_signature,
        computed_signature,
    )


def create_order_with_soc_code(
    shopify_order_id: str,
    shopify_order_number: str,
    customer_name: str,
    customer_email: str,
    max_attempts: int = 5,
) -> str:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT soc_tracking_code
                FROM orders
                WHERE shopify_order_id = %s
                """,
                (shopify_order_id,),
            )

            existing = cursor.fetchone()

            if existing:
                return existing["soc_tracking_code"]

    for _ in range(max_attempts):
        soc_code = generate_soc_code()

        try:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO orders (
                            shopify_order_id,
                            shopify_order_number,
                            customer_name,
                            customer_email,
                            soc_tracking_code,
                            status
                        )
                        VALUES (%s, %s, %s, %s, %s, 'Order Confirmed')
                        """,
                        (
                            shopify_order_id,
                            shopify_order_number,
                            customer_name,
                            customer_email,
                            soc_code,
                        ),
                    )

                    cursor.execute(
                        """
                        INSERT INTO shipment_timeline (
                            soc_tracking_code,
                            status,
                            public_note
                        )
                        VALUES (%s, 'Order Confirmed', %s)
                        """,
                        (
                            soc_code,
                            "Your order has been confirmed.",
                        ),
                    )

            return soc_code

        except psycopg2.errors.UniqueViolation as error:
            if "shopify_order_id" in str(error):
                with get_connection() as connection:
                    with connection.cursor() as cursor:
                        cursor.execute(
                            """
                            SELECT soc_tracking_code
                            FROM orders
                            WHERE shopify_order_id = %s
                            """,
                            (shopify_order_id,),
                        )

                        row = cursor.fetchone()

                        if row:
                            return row["soc_tracking_code"]

            continue

    raise RuntimeError(
        "SOC kodu oluşturulamadı (çok fazla çakışma)."
    )


@app.route(
    "/webhooks/orders-create",
    methods=["POST"],
)
def webhook_orders_create():
    raw_body = request.get_data()

    provided_signature = request.headers.get(
        "X-Shopify-Hmac-SHA256",
        "",
    )

    if not verify_shopify_webhook(
        raw_body,
        provided_signature,
    ):
        return "", 401

    payload = (
        request.get_json(
            force=True,
            silent=True,
        )
        or {}
    )

    shopify_order_id = str(payload.get("id", "")).strip()

    if not shopify_order_id:
        return "", 400

    shopify_order_number = str(
        payload.get("order_number")
        or payload.get("name")
        or ""
    )

    customer = payload.get("customer") or {}

    customer_name = " ".join(
        part
        for part in [
            customer.get("first_name", ""),
            customer.get("last_name", ""),
        ]
        if part
    ).strip()

    customer_email = (
        payload.get("email")
        or customer.get("email")
        or ""
    )

    try:
        create_order_with_soc_code(
            shopify_order_id=shopify_order_id,
            shopify_order_number=shopify_order_number,
            customer_name=customer_name,
            customer_email=customer_email,
        )
    except Exception:
        app.logger.exception(
            "orders-create webhook işlenirken hata."
        )

        return "", 500

    return "", 200


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            return redirect(
                url_for(
                    "admin_login",
                    next=request.path,
                )
            )

        return view(*args, **kwargs)

    return wrapped


@app.route(
    "/admin/login",
    methods=["GET", "POST"],
)
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        username_ok = hmac.compare_digest(
            username,
            ADMIN_USERNAME,
        )

        password_ok = hmac.compare_digest(
            password,
            ADMIN_PASSWORD,
        )

        if username_ok and password_ok:
            session["is_admin"] = True

            next_url = (
                request.args.get("next")
                or url_for("admin_orders")
            )

            return redirect(next_url)

        flash("Geçersiz kullanıcı adı veya şifre.")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@login_required
def admin_orders():
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    soc_tracking_code,
                    customer_name,
                    status,
                    updated_at
                FROM orders
                ORDER BY updated_at DESC
                """
            )

            orders = cursor.fetchall()

    return render_template(
        "admin_orders.html",
        orders=orders,
    )


@app.route(
    "/admin/orders/<soc_code>",
    methods=["GET", "POST"],
)
@login_required
def admin_order_detail(soc_code: str):
    soc_code = soc_code.strip().upper()

    if request.method == "POST":
        new_status = request.form.get("status", "")
        public_note = request.form.get(
            "public_note",
            "",
        ).strip()

        internal_notes = request.form.get(
            "internal_notes",
            "",
        ).strip()

        if new_status not in STATUS_STAGES:
            flash("Geçersiz durum seçimi.")
        else:
            with get_connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        UPDATE orders
                        SET
                            status = %s,
                            internal_notes = %s,
                            updated_at = now()
                        WHERE soc_tracking_code = %s
                        """,
                        (
                            new_status,
                            internal_notes,
                            soc_code,
                        ),
                    )

                    cursor.execute(
                        """
                        INSERT INTO shipment_timeline (
                            soc_tracking_code,
                            status,
                            public_note
                        )
                        VALUES (%s, %s, %s)
                        """,
                        (
                            soc_code,
                            new_status,
                            public_note or None,
                        ),
                    )

            flash("Durum güncellendi.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT *
                FROM orders
                WHERE soc_tracking_code = %s
                """,
                (soc_code,),
            )

            order = cursor.fetchone()

            if not order:
                abort(404)

            cursor.execute(
                """
                SELECT status, public_note, created_at
                FROM shipment_timeline
                WHERE soc_tracking_code = %s
                ORDER BY created_at ASC
                """,
                (soc_code,),
            )

            timeline = cursor.fetchall()

    return render_template(
        "admin_order_detail.html",
        order=order,
        timeline=timeline,
        status_stages=STATUS_STAGES,
    )




if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        debug=False,
    )
