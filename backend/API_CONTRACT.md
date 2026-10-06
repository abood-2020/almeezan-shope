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
