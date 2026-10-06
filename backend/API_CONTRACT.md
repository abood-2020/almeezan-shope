# Phase 3 API contract

Session authentication for the existing Riwaq frontend. Base URL in local development: `http://127.0.0.1:8000`.

Send cookies on later browser requests (`credentials: "include"`). For `POST`, read `csrfToken` from `GET /api/auth/csrf/` and send it as the `X-CSRFToken` header.

Prices are decimal strings. Guests do not receive trader prices or the ILS base price.

## GET /api/auth/csrf/

- Auth: public
- Response: `{"csrfToken": "<token>"}`
- Also sets the `csrftoken` cookie.

## POST /api/auth/login/

- Auth: public, CSRF required
- Body: `{"username": "trader", "password": "demo123"}`
- Success `200`: `{"authenticated": true, "trader": { ... }}`
- `401` wrong username or password
- `403` inactive user, inactive trader, or no trader profile
- The password is never returned.

`trader` contains `id`, `username`, `name_ar`, `name_en`, `email`, `active`, and `price_list` (`id`, `name_ar`, `name_en`, `currency_code`, `currency_symbol`).

## POST /api/auth/logout/

- Auth: active trader, CSRF required
- Success `200`: `{"authenticated": false}`

## GET /api/auth/me/

- Auth: public
- Guest: `{"authenticated": false, "trader": null}`
- Active trader: `{"authenticated": true, "trader": { ... }}` using the login trader shape.

## GET /api/catalog/categories/

- Auth: public
- Real categories only. There is no "All products" row.
- Example item: `{"id": 1, "name_ar": "رجالي", "name_en": "Men", "image": "men"}`
- `image` is an asset key, or a `/media/...` path when a file has been stored.

## GET /api/catalog/products/

## GET /api/catalog/products/<id>/

- Auth: public. A trader session adds pricing.
- `404` when the product id does not exist.
- Product fields: `id`, `name_ar`, `name_en`, `code`, `category_id`, `unit_ar`, `unit_en`, `min_qty`, `available`, `description_ar`, `description_en`, `badge`, `image`, `gallery`, `colors`, `sizes`, `options`, `unavailable_variants`.
- `colors`: `name_ar`, `name_en`, `hex`, `image`.
- `options`: display strings such as `عاجي / Ivory · M`.
- `unavailable_variants`: option strings that cannot be ordered.
- Trader session also includes `price` (`"82.00"` or `null`), `currency_code`, and `currency_symbol`.
- ILS lists use an explicit row when present, otherwise the product base price.
- Other currencies require an explicit row. `price` is `null` when it is missing.
- No exchange rates.

## GET /api/pricing/current/

- Auth: active trader
- Body of the response:

```json
{
  "id": "local",
  "name_ar": "تجار فلسطين",
  "name_en": "Palestine traders",
  "currency_code": "ILS",
  "currency_symbol": "₪",
  "prices": [{"product_id": 1, "price": "82.00"}]
}
```

Uses the same price rule as the catalog.

## GET /api/orders/

- Auth: active trader
- Only that trader's orders, newest first.
- Each order uses the detail shape below.

## POST /api/orders/

- Auth: active trader, CSRF required
- Body:

```json
{
  "note": "Optional note",
  "items": [{"product_id": 1, "option": "عاجي / Ivory · M", "qty": 12}]
}
```

- Success `201` with the order detail.
- The server sets the trader, status `review`, currency, unit prices, total, and order number (`RW-<year>-<sequence>`).
- Client `price`, `total`, `trader`, `status`, and `currency` values are ignored.
- `400` when the order is empty, a product or option is unknown, a product or option is unavailable, the quantity is not a positive integer, the quantity is below the product minimum, or the trader's list has no price for the product.

## GET /api/orders/<order_number>/

- Auth: active trader
- `200` only for an order owned by the session trader.
- `404` for an unknown number or another trader's order.

Order detail:

```json
{
  "number": "RW-2026-1043",
  "date": "2026-10-06",
  "status": "review",
  "trader_name_ar": "متجر الأفق",
  "note": "",
  "currency_code": "ILS",
  "currency_symbol": "₪",
  "total": "984.00",
  "items": [
    {
      "product_id": 1,
      "code": "RW-MN-001",
      "name_ar": "قميص رجالي كتان بقصّة مريحة",
      "name_en": "Relaxed linen shirt",
      "option": "عاجي / Ivory · M",
      "qty": 12,
      "unit_price": "82.00",
      "line_total": "984.00"
    }
  ]
}
```

`unit_price` is the price at submission and does not change when the price list changes later.

# Phase 4 API contract

Admin routes require an authenticated Django user with `is_staff`. Traders are rejected. Reuse `GET /api/auth/csrf/` and send `X-CSRFToken` on every `POST`, `PATCH`, `PUT`, and `DELETE`.

The seeded development staff user is `admin` / `demo123`. Reseeding does not reset that password. New traders created through the API do not receive this password.

Passwords and password hashes are never returned.

## POST /api/admin/auth/login/

- Auth: public, CSRF required
- Body: `{"username": "admin", "password": "demo123"}`
- `200`: `{"authenticated": true, "user": {"id": 1, "username": "admin", "email": "admin@example.com", "is_staff": true}}`
- `401` wrong username or password
- `403` inactive user, or a user who is not staff

## POST /api/admin/auth/logout/

- Auth: staff, CSRF required
- `200`: `{"authenticated": false}`

## GET /api/admin/auth/me/

- Auth: staff
- `200`: `{"authenticated": true, "user": { ... }}`

## Products

- `GET /api/admin/products/`
- `POST /api/admin/products/`
- `GET /api/admin/products/<id>/`
- `PATCH /api/admin/products/<id>/`

Staff only. No delete. Money is a decimal string. `category_id` must exist. `code` must be unique. `min_qty` is an integer `>= 1`. `base_price_ils` is `>= 0`.

Create body includes names, code, category, price, units, minimum, `available`, and either `options` or `colors` plus `sizes`. Colors use `name_ar`, `name_en`, and `hex`. `unavailable_variants` lists option labels that cannot be ordered. When colors and sizes are sent, options are rebuilt as `Arabic / English · size`.

`image_key` and `gallery` store asset keys only. Values starting with `blob:` are rejected. Uploaded files use the image routes below.

The admin product adds `base_price_ils` and image records (`id`, `url`, `image_key`, `sort_order`, `is_primary`) to the catalog product shape. Colors include `id`.

## Product images

- `POST /api/admin/products/<id>/images/`
- `PATCH /api/admin/products/<id>/images/<image_id>/`
- `DELETE /api/admin/products/<id>/images/<image_id>/`
- `POST /api/admin/products/<id>/colors/<color_id>/image/`

Multipart field `file`. JPEG, PNG, WEBP, and GIF only. Optional `is_primary` and `sort_order`. The stored file is served from `/media/...` while `DEBUG` is on. `blob:` URLs are not stored.

## Categories

- `GET /api/admin/categories/`
- `POST /api/admin/categories/`
- `GET /api/admin/categories/<id>/`
- `PATCH /api/admin/categories/<id>/`

Fields: `name_ar`, `name_en`, `image_key`. Optional multipart `image`. No "All products" row and no delete. Duplicate Arabic names are rejected. Response matches the public category shape.

## Traders

- `GET /api/admin/traders/`
- `POST /api/admin/traders/`
- `GET /api/admin/traders/<id>/`
- `PATCH /api/admin/traders/<id>/`
- `POST /api/admin/traders/<id>/set-password/`

Body: `id`, `name_ar`, `name_en`, `username`, `email`, `price_list_id`, `active`. Username must be unique. `id` cannot change. `active` updates both the trader and the Django user. A create request without `password` stores an unusable password. Password changes use:

```json
{"password": "new-password"}
```

`user.set_password` stores the hash. The response is `{"detail": "Password updated."}`.

## Currencies

- `GET /api/admin/currencies/`
- `POST /api/admin/currencies/`
- `GET /api/admin/currencies/<code>/`
- `PATCH /api/admin/currencies/<code>/`

Body: `code`, `name`, `symbol`. Code is three letters and stored uppercase. The code cannot be changed later. No exchange rates and no delete.

## Price lists

- `GET /api/admin/price-lists/`
- `POST /api/admin/price-lists/`
- `GET /api/admin/price-lists/<id>/`
- `PATCH /api/admin/price-lists/<id>/`
- `PUT /api/admin/price-lists/<id>/prices/`

List body: `id`, `name_ar`, `name_en`, `currency_code`, optional `is_active`. Price body:

```json
{"prices": [{"product_id": 1, "price": "82.00"}]}
```

The price update replaces the explicit rows inside a transaction. Each price must be `>= 0`. Omitted products lose their explicit row. ILS lists then fall back to `base_price_ils`. A non-ILS list is rejected unless every product has an explicit price. `complete` is true for ILS lists and for non-ILS lists that cover every product. No exchange conversion.

## Admin orders

- `GET /api/admin/orders/`
- `GET /api/admin/orders/<order_number>/`
- `PATCH /api/admin/orders/<order_number>/status/`

Optional query `q` matches order number or trader name. Optional `status` is one of `review`, `confirmed`, `complete`, `cancelled`.

Status body: `{"status": "confirmed"}`. Any other status is `400`. Trader, currency, totals, and line prices are not writable. Trader order routes from Phase 3 are unchanged.

## Invoices

Admin:

- `GET /api/admin/invoices/`
- `POST /api/admin/invoices/`
- `GET /api/admin/invoices/<invoice_id>/`
- `PATCH /api/admin/invoices/<invoice_id>/`

`invoice_id` is the invoice number. Create fields: `number`, `trader_id`, `date`, `amount`, optional multipart `file`. The number cannot change. Duplicate numbers are rejected. A file must be a PDF whose content starts with `%PDF-`. It is stored under `media/invoices/`.

Trader, own records only:

- `GET /api/invoices/`
- `GET /api/invoices/<invoice_id>/`

Another trader's invoice is `404`.

```json
{
  "id": "INV-2026-087",
  "number": "INV-2026-087",
  "trader_id": "horizon",
  "date": "2026-09-12",
  "amount": "456.00",
  "file_url": "/files/invoice-demo.pdf",
  "file_name": "INV-2026-087.pdf"
}
```

`file_url` is the media URL when a file was uploaded.

## Settings

- `GET /api/settings/` public
- `GET /api/admin/settings/` staff
- `PATCH /api/admin/settings/` staff

```json
{"company_whatsapp_number": "05991234567"}
```

The value is stored as digits. Empty is allowed. A non-empty value must be 8–15 digits. There is no WhatsApp Business API.

## POST /api/admin/products/bulk-import/

Staff only. Body: `{"rows": [ ... ]}` using the spreadsheet columns `Code`, `Name_AR`, `Name_EN`, `Category_ID`, `Unit_AR`, `Unit_EN`, `Min_Qty`, `Base_Price_ILS`, `Available`, `Description_AR`, `Description_EN`. `Price_ILS` is an alias of `Base_Price_ILS`.

The server checks the workbook again. Required names, code, and units. Unique code against current products and inside the file. `Category_ID` must be a real category. `Min_Qty` is an integer `>= 1`. Price is `>= 0`. `Available` is `0` or `1`. At most 1000 rows. One failure returns `400` and writes nothing.

```json
{"rows": ["Row 2: duplicate code"]}
```

Row numbers count the header as row 1. Created products use image key `men-shirt` and option `افتراضي / Default`. Success `201`: `{"created": 1, "products": [ ... ]}`.
