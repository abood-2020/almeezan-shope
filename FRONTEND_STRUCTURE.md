# Frontend structure reference

Contract for a future Django backend. Describes the frontend as it exists. No new business features.

Brand in the UI: رِواق / Riwaq, bilingual Arabic (default, RTL) and English wholesale fashion catalog. Submission is a trade request. There is no online payment.

## 1. Project Overview

Wholesale B2B catalog. Guests browse products. A signed-in trader sees one assigned price list and currency, builds a cart, and submits a request. An administration screen edits products, categories, traders, prices, currencies, order status, invoice files, and a WhatsApp number. All of that state lives in the browser for the current session. Refresh discards it.

### Current frontend stack

| Item | Value |
|---|---|
| Language | TypeScript |
| UI | React 19.2.6 |
| App shell | Next.js 16.3.4, run by vinext 1.0.0-beta.5 on Vite 8.0.13 |
| Package manager | pnpm 11.25.0 (`packageManager` in `package.json`). Use Corepack if `pnpm` is not on PATH |
| Node | `>=22.13.0` |
| CSS | Tailwind CSS 4 plus custom rules in `app/globals.css`. Cairo font in `app/font.css` and `public/assets/Cairo*` |
| Components | shadcn-style files in `components/ui` (Radix, Base UI). Icons: `lucide-react`. Toasts: `sonner` |
| Forms / files | `react-hook-form` is installed. Shop forms are plain React. Excel: `xlsx`. PDF: `jspdf` |
| Routing | Hash routes inside one client page. Not Next.js routes |
| State | `useState` in `app/page.tsx`. No Redux, Zustand, React Query, `localStorage`, or `sessionStorage` |
| Shop API | None |

### How it runs locally

```text
corepack pnpm install --frozen-lockfile
corepack pnpm dev
```

`pnpm dev` runs `node scripts/run-framework.mjs dev`, which starts vinext with `--port 5173`.

- URL: `http://127.0.0.1:5173/`
- Verified: homepage HTTP 200
- `Sites local sign-in: seedy@sites.test` is the Sites preview wrapper (`vite.config.ts` `mockAuth`). It is not the shop login
- Shop login is the in-page dialog. Demo password is the literal string `demo123`

### Main entry files

| File | Role |
|---|---|
| `app/layout.tsx` | HTML shell. `lang="ar"` `dir="rtl"`. Metadata title only |
| `app/page.tsx` | `'use client'`. All shop state, screens, login, cart, orders, admin |
| `app/data.ts` | `Product`, `CartLine`, `Order`, seed products, categories, sample orders, statuses, image helpers |
| `app/pricing.ts` | `PriceList`, `effectivePrice`, `commitPrices` |
| `app/catalog-navigation.ts` | Hash parser and name-based subcategories |
| `app/files.ts` | Excel import/export and order PDF |

`app/chatgpt-auth.ts`, `db/schema.ts`, `db/index.ts`, and `examples/d1/` are not used by the shop.

## 2. Project Structure

| Path | Responsibility |
|---|---|
| `app/page.tsx` | Application. State, screens, dialogs, submit, admin saves |
| `app/layout.tsx` | Document shell |
| `app/globals.css`, `app/font.css` | Visual design. Leave unchanged |
| `app/data.ts` | Seed catalog, orders, image URL rules: `assetSrc`, `productImageSrc`, `productImageForOption` |
| `app/pricing.ts` | Seed price lists and price resolution. `baseCurrency = 'ILS'` |
| `app/catalog-navigation.ts` | `catalogGroups`, `catalogHref`, `readStoreRoute`, `productType` |
| `app/files.ts` | `columns`, `downloadTemplate`, `readImport`, `exportExcel`, `downloadOrder` |
| `app/store-header.tsx` | Header, language, account, cart count, catalog menu |
| `app/product-editor.tsx` | `ProductEditor`. Create/edit product, photos, colors, sizes |
| `app/price-list-manager.tsx` | `PriceListManager`. List index, draft prices, 10 rows per page |
| `app/product-image.tsx` | Image loading/error shell |
| `app/cart-quantity.tsx` | Cart quantity control |
| `app/trade-pages.tsx` | Static Traders and Export marketing pages |
| `app/contact-page.tsx` | Contact form that only prepares text to copy |
| `components/ui/` | Shared UI primitives. No shop data |
| `components.json` | shadcn config |
| `public/assets/` | Product, category, and hero images. Keys such as `men-shirt` map to `/assets/men-shirt.jpg` |
| `public/files/invoice-demo.pdf` | One demo invoice file |
| `public/favicon.svg` | Logo mark |
| `public/assets/fashion-source-manifest.json` | Image source notes. Not read by the app |
| `package.json` | Dependencies and scripts: `dev`, `build`, `start`, `lint`, `db:generate` |
| `pnpm-lock.yaml`, `pnpm-workspace.yaml`, `.npmrc` | Install lock and pnpm policy |
| `vite.config.ts` | vinext + Cloudflare plugin. Shop data is not here |
| `next.config.ts` | Empty Next config |
| `tsconfig.json` | `@/*` maps to the repo root |
| `scripts/`, `build/` | Dev/build wrapper for the Sites runtime. No shop business logic |
| `db/`, `drizzle/`, `drizzle.config.ts`, `examples/d1/` | Empty/example database scaffold. Not connected |
| `.openai/hosting.json` | `"d1": null`, `"r2": null` |
| `README.md` | Demo behavior and the session-only boundary |

Ignored for backend work: `node_modules/`, `.sites-runtime/`, `dist/`, `.next/`, `.vinext/`, `.wrangler/`.

## 3. Current Screens / Sections

Navigation is `page` state plus `window.location.hash`. Allowed hashes are listed in `readStoreRoute` (`app/catalog-navigation.ts`). Unknown hashes become `home`.

Catalog links use `#products` or `#products?category={n}&subcategory={id}`.

### Home

- Purpose: landing, categories, featured products, how ordering works.
- Source: `page==='home'` in `app/page.tsx`. Header: `app/store-header.tsx`.
- Data: `categories`, `products` (first 8), `lang`. Hero files `/assets/hero-video-poster.jpg`, `/assets/hero-background.mp4`.
- Actions: open catalog, open login or portal, switch language, open WhatsApp, jump to info.
- Backend: product and category content yes. Layout and copy no.

### Products / catalog

- Purpose: filterable grid.
- Source: `page==='products'` in `app/page.tsx`. Cards are `ProductCard` in the same file.
- Data: `products`, `categories`, `groups` from `catalogGroups`, signed-in trader's `effectivePrice`, `currency` symbol.
- Actions: search (`query`), category pills, subcategory, in-stock only, color, size, sort (`featured`, `name`, and if signed in `low` / `high`), open product, add minimum quantity of the selected variant.
- Guest prices are hidden. Add opens login.
- Backend: catalog and prices yes. Filter and sort state no.

### Subcategories

- Purpose: extra catalog links such as shirts or dresses.
- Source: `productTypes` regex in `app/catalog-navigation.ts`. Not a stored entity.
- A child appears only when at least one product name matches.
- Backend: not a separate table unless names stop matching. Today it is derived.

### Product details

- Purpose: dialog over the current page. Not its own route.
- Source: `selected` dialog in `app/page.tsx`. Image: `app/product-image.tsx`.
- Data: one `Product`, color index, size, `option` string, `qty` starting at `min`, price if signed in.
- Actions: pick color and size, change quantity, add to cart or open login. Unavailable variants are disabled.
- Option string built by `variantValue`: `` `${color.ar} / ${color.en} · ${size}` ``.
- If a product has no colors, the dialog uses `product.options` instead.
- Backend: same product payload as the catalog. No separate detail endpoint required.

### Cart

- Purpose: review lines, optional note, then submit.
- Source: `page==='cart'` in `app/page.tsx`. Quantity widget: `app/cart-quantity.tsx`.
- Data: `cart`, `note`, `review`, `simulateError`, `merchant`, `total`, `currency`.
- Actions: change qty (not below `min`), remove line, continue shopping, review, submit, simulate a failed submit.
- Empty cart has no submit.
- Backend: cart can stay in the browser until submit. The submitted order must be stored. `simulateError` is demo-only and should not be a backend feature.

### Login

- Purpose: dialog, not a route.
- Source: `login` dialog in `app/page.tsx`. `signIn(username)`.
- Data: `merchants`, `loginName`, `password`, `user` (username string).
- Rules: form requires `password === 'demo123'`, then `signIn`. Quick buttons call `signIn('trader')` or `signIn('export')` with no password check. `signIn` requires `merchants.find(m => m.username === username && m.active)`.
- Switching username clears `cart`.
- There is no per-trader password field. The merchant editor only displays the text `demo123`.
- Backend: real authentication. The UI currently has one shared password and a bypass on the quick buttons.

### Confirmation

- Purpose: hash `#confirmation` after a successful submit.
- Source: `page==='confirmation'` in `app/page.tsx`.
- Data: `activeOrder` in memory. Refresh shows an empty state even if the hash remains.
- Actions: download PDF, open WhatsApp, go to portal.
- Backend: order must be reloadable by id if this screen should survive refresh. The current UI does not fetch it.

### Trader portal

- Purpose: hash `#portal`.
- Source: `page==='portal'` in `app/page.tsx`. Tabs: `portalTab` = `overview` | `orders` | `invoices` | `cart`.
- Data: current `merchant`, `list`, `currency`, `orders` where `order.merchant === merchant.ar`, `invoices` where `invoice.merchant === merchant.id`, current `cart`.
- Signed-out visitors see a sign-in empty state. No route guard.
- Backend: trader profile, price-list name, orders, invoices.

### Orders (trader)

- Inside portal tab `orders`, plus the latest three on overview.
- Filter: `statusFilter` against `statuses`.
- Actions: filter, open order dialog, download PDF.
- Traders cannot change status.
- Sample orders all use `merchant: 'متجر الأفق'`, so only the local trader sees them.

### Order details dialog

- Source: `activeOrder` dialog in `app/page.tsx`.
- Data: order lines, product lookup by `line.id`, note, total.
- Actions: view, download PDF.

### Invoices (trader)

- Portal tab `invoices`.
- Data: `{id, date, merchant, amount, url, name}`. `merchant` is the trader **id** (`horizon`), not the Arabic name.
- Actions: view file in a new tab, download, if `url` is set. Otherwise the label is "Record only".
- Amount is a stored number. It is not calculated from orders.
- Display currency is the symbol of that trader's price list.

### Traders marketing page

- Hash `#traders`.
- Source: `app/trade-pages.tsx` with `kind: 'traders'`.
- Static copy. Actions: catalog, sign-in, WhatsApp, switch to export page.
- Backend: no.

### Export marketing page

- Hash `#export`.
- Source: `app/trade-pages.tsx` with `kind: 'export'`.
- Same pattern as Traders. Backend: no.

### About / info

- Hash `#info`.
- Source: `page==='info'` in `app/page.tsx`.
- Static story, three steps, four FAQ items. Backend: no.

### Contact

- Hash `#contact`.
- Source: `app/contact-page.tsx`.
- Data: `companyPhone`. Local draft `{name, contact, inquiry, message}` is not stored.
- Inquiry ids: `wholesale`, `export`, `account`, `followup`, `other`.
- Actions: prepare text, copy, optionally open WhatsApp with that text. The form says it does not send or save.
- Backend: only if the WhatsApp number should persist. The inquiry itself is not saved today.

### Admin

- Hash `#admin`. Opened from the footer. **No login and no role check.**
- Source: `page==='admin'` in `app/page.tsx`.
- Tabs via `adminTab`: `overview`, `products`, `categories`, `merchants`, `prices`, `currencies`, `orders`, `invoices`, `settings`.
- Banner says changes last for this session.
- Backend: every mutable entity below, plus an access rule the UI does not have yet.

### Admin overview

- Counts: orders, `status==='review'`, products, available products, active traders, price lists.
- Latest 5 orders. Status bars. Shortcuts to add a product or open Excel import.
- Backend: counts can be derived. No separate model.

### Products management

- Source: admin tab `products` plus `ProductEditor` in `app/product-editor.tsx`.
- Actions: search by Arabic name, English name, or code; add; edit; Excel export of the filtered rows; Excel import.
- Save rejects a duplicate `code` (`onSave` in `app/page.tsx`). New id is `Date.now()` when `id` is falsy.
- No delete-product action.
- `badge` exists on some seed products and is kept if the editor spreads the original product. The editor has no badge field, so new products have no badge.
- Backend: product CRUD that matches the editor. Delete is not in the UI.

### Categories

- Admin tab `categories`. Generic editor `type==='category'`.
- Fields: `ar`, `en`, `img`. Image upload becomes `URL.createObjectURL` (`blob:`).
- Index `0` (`جميع المنتجات` / All products) is not editable and is not a real category. Real categories start at index `1`.
- Duplicate Arabic name is rejected. New category is appended, so its id is the new array index.
- No delete.
- Backend: categories need stable ids. The UI currently uses the array index as `Product.cat` and as Excel `Category_ID`.

### Traders

- Admin tab `merchants`. Editor `type==='merchant'`.
- Fields: `id`, `ar`, `en`, `username`, `email`, `list` (price list id), `active`.
- Duplicate `username` is rejected. New id is `String(Date.now())`.
- Deactivate with `active: false`. Inactive users fail `signIn`. No delete.
- Password is not a field.
- Backend: trader accounts, assigned price list, active flag, and a real password policy.

### Price lists

- Admin tab `prices`. Create dialog `type==='priceList'`. Editor UI: `PriceListManager`.
- Create fields: `ar`, `en`, `currency`. New id `list-` + `Date.now()`, `prices: {}`.
- Detail: search, category, status `all|missing|edited`, 10 products per page, draft `priceDrafts`, save, discard.
- Changing the list currency clears draft price inputs. No automatic conversion.
- Save via `commitPrices` (`app/pricing.ts`): blank cells are omitted; negative or non-numeric values throw. If the currency is not `ILS`, every product must have a price or save is blocked.
- `effectivePrice`: use `list.prices[product.id]` when finite; if missing and currency is `ILS`, use `product.price`; if missing and currency is not `ILS`, return `NaN` ("Price not set").
- No delete list.
- Backend: price list header, per-product prices, ILS fallback rule.

### Currencies

- Admin tab `currencies`. Editor `type==='currency'`.
- Fields: `id` (3 letters `A-Z`), `name`, `symbol`.
- Duplicate code rejected. Existing code can be edited. No delete.
- Renaming a code updates the currency row only. Price lists still store the old code string.
- Seed: `ILS` / `₪`, `USD` / `$`.
- Backend: currency reference data. No exchange rates. The UI states that explicitly.

### Admin orders

- Tab `orders`. Search by id or `merchant` string. Filter by status.
- Admin can change status with `Choice` among `review`, `confirmed`, `complete`, `cancelled`.
- Open details, export Excel. Export drops `items` and adds `Lines: items.length`.
- No create-order and no delete-order in admin.
- Backend: list orders, update status. Persist lines so details and PDF still work.

### Admin invoices

- Tab `invoices`. Editor `type==='invoice'`.
- Fields: `id`, `date`, `merchant` (trader id), `amount`, optional PDF (`url` blob or path, `name`).
- Duplicate invoice id rejected. Existing id cannot be edited. No delete.
- Amount is entered. It is not tied to an order.
- Backend: invoice record plus file storage.

### Excel import / export

- Source: `app/files.ts`, import dialog in `app/page.tsx`.
- Template columns (`columns`): `Code`, `Name_AR`, `Name_EN`, `Category_ID`, `Unit_AR`, `Unit_EN`, `Min_Qty`, `Base_Price_ILS`, `Available`, `Description_AR`, `Description_EN`.
- `Price_ILS` is accepted as an alias of `Base_Price_ILS`.
- Validation: required text fields, unique `Code` against current products and within the file, `Category_ID` integer from 1 to `categories.length - 1`, `Min_Qty` integer `>= 1`, price `>= 0`, `Available` is `'0'` or `'1'`, at least 1 row, at most 1000.
- Confirm writes new products in memory: `image: 'men-shirt'`, `options: ['افتراضي / Default']`, no colors, sizes, or gallery. Id `Date.now()+i`.
- Export buttons on products, merchants, orders, invoices download an `.xlsx` in the browser. They do not call a server.
- Backend: bulk create if imports must persist. Export can stay in the browser once the rows are loaded.

### PDF

- Source: `downloadOrder` in `app/files.ts`, called as `pdf(order)` from `app/page.tsx`.
- Built in the browser with canvas + jsPDF. Includes trader label, email, date, line photo, code, option, qty, prices, total, note.
- Labeled "Commercial request · not an accounting invoice".
- English trader label is hardcoded: Arabic name `متجر الأفق` becomes `Horizon Store`; every other Arabic name becomes `Atlas Trading`.
- Email passed in is `merchant?.email` or `'trader@example.com'`.
- Backend: no PDF endpoint required. Order and product data must be present so this function can still run.

### WhatsApp / settings

- Admin tab `settings` edits `companyPhone` (default `''`).
- `openWhatsApp` in `app/page.tsx`: if the digits are length 8–15, open `https://wa.me/{digits}`. Otherwise open a phone dialog.
- Floating button and several page buttons use this. They do not attach the cart, order, or PDF.
- Contact page uses the same number when it is already valid.
- Backend: one persisted company phone if the button should work after refresh. No WhatsApp Business API.

### Shared chrome

- Announcement bar and footer: `app/page.tsx`. Footer opens admin and signs out (`setUser('')`, `setCart([])`, go home).
- Language toggle sets `documentElement.lang` and `dir`. Not persisted.
- Toaster: `sonner`.

## 4. Current Data Model

Shapes below are the frontend objects. They are not proposed database tables.

### Product

Source type: `Product` in `app/data.ts`.

| Field | Type | Notes |
|---|---|---|
| `id` | number | Seed 1–8. New: `Date.now()` |
| `ar`, `en` | string | Required in the editor |
| `code` | string | Unique. Example `RW-MN-001` |
| `cat` | number | Index into `categories`. `1` is Men. `0` is not used on products |
| `price` | number | Base price in ILS. Editor label is ₪ |
| `unit`, `unitEn` | string | Example `قطعة` / `piece` |
| `min` | number | Minimum order quantity. Integer `>= 1` |
| `available` | boolean | Product-level availability |
| `image` | string | Asset key, `blob:` URL, `data:` URL, or path starting with `/` |
| `gallery` | string[] optional | Extra photos. Editor allows 8 images including cover |
| `badge` | string optional | Seed values: `جديد`, `الأكثر طلبًا`, `اختيار رِواق`. Not edited |
| `desc`, `descEn` | string | |
| `options` | string[] | Selling options. Rebuilt from colors × sizes when colors exist |
| `colors` | array optional | See Color |
| `sizes` | string[] optional | Example `S`, `M`, `4Y` |
| `unavailableVariants` | string[] optional | Must match an `options` entry or the editor drops it |

### Color

Inline on `Product.colors`. No separate type export.

| Field | Type |
|---|---|
| `ar`, `en` | string, unique per product, case-insensitive |
| `hex` | `#` + 6 hex digits. Editor uppercases it |
| `image` | optional asset key or `blob:` URL |

### Variant / option

Not a separate object.

- Display and cart value: `` `${ar} / ${en} · ${size}` `` from `variantValue` in `app/page.tsx`.
- `variantAvailable`: `product.available && !unavailableVariants.includes(option)`.
- `productImageForOption` (`app/data.ts`) finds the color whose `` `${ar} / ${en} · ` `` prefixes the option string.
- Products with no colors keep free-text `options` (Excel import uses `افتراضي / Default`).

### Category

Not a named type. Array in `categories`.

| Position | Fields |
|---|---|
| Index `0` | `{ar, en}` only. All-products filter. Not a stored category |
| Index `1+` | `{ar, en, img?}`. `img` is an asset key or `blob:` URL |

`Product.cat` and Excel `Category_ID` are this index.

### Subcategory

Derived. `{id, ar, en, count}` from `productTypes` in `app/catalog-navigation.ts`.

Ids: `tees`, `shirts`, `trousers`, `blazers`, `dresses`, `sets`, `cardigans`.

### Trader (`merchants` state)

No exported type. Initial values in `app/page.tsx`.

| Field | Seed examples |
|---|---|
| `id` | `horizon`, `atlas` |
| `ar` | `متجر الأفق`, `أطلس للتجارة` |
| `en` | `Horizon Store`, `Atlas Trading` |
| `username` | `trader`, `export` |
| `email` | `trader@example.com`, `export@example.com` |
| `list` | `local`, `export` |
| `active` | `true` |

No password field. Session identity is `user` (the username string).

### Price list

`PriceList` in `app/pricing.ts`.

| Field | Type | Notes |
|---|---|---|
| `id` | string | `local`, `export`, or `list-{timestamp}` |
| `ar`, `en` | string | |
| `currency` | string | Currency **code** (`ILS`, `USD`), not the symbol |
| `prices` | `Record<number, number>` | Key is `Product.id` |

`PriceDraft`: `{currency: string, values: Record<number, string>}` while editing. Not persisted even in the session until save.

Seed:

- `local`: Arabic `تجار فلسطين`, currency `ILS`, price copied from each product's `price`.
- `export`: Arabic `تجار التصدير`, currency `USD`, explicit map `{1:25, 2:14, 3:47, 4:34, 5:23, 6:30, 7:27, 8:22}`.

### Currency

No exported type.

| Field | Notes |
|---|---|
| `id` | 3-letter code |
| `name` | Bilingual label in one string, e.g. `شيكل / Shekel` |
| `symbol` | `₪` or `$`. This symbol is what orders store as `Order.currency` |

### Cart line

`CartLine` in `app/data.ts`.

| Field | Notes |
|---|---|
| `key` | `` `${product.id}-${option}` `` |
| `id` | Product id |
| `qty` | Integer, at least `product.min` |
| `option` | Variant string |
| `price` | Unit price captured from the active list |

### Order

`Order` in `app/data.ts`.

| Field | Notes |
|---|---|
| `id` | Seed `RW-2026-1042` and similar. New id: `` `RW-2026-${1043 + orders.length - 3}` `` |
| `date` | `YYYY-MM-DD` |
| `status` | `review` \| `confirmed` \| `complete` \| `cancelled` |
| `items` | `CartLine[]` |
| `total` | Sum of `price * qty` at submit time |
| `currency` | **Symbol** (`₪`, `$`), not the code |
| `note` | Optional |
| `merchant` | Trader **Arabic name** (`merchant.ar`), not trader id |

`statuses` in `app/data.ts` maps those four keys to Arabic and English labels. The set is fixed in the UI.

### Invoice

No exported type. Seed in `app/page.tsx`.

| Field | Seed |
|---|---|
| `id` | `INV-2026-087` |
| `date` | `2026-09-12` |
| `merchant` | `horizon` (trader id) |
| `amount` | `456` |
| `url` | `/files/invoice-demo.pdf` or a `blob:` URL |
| `name` | `INV-2026-087.pdf` |

### Settings

| Field | Notes |
|---|---|
| `companyPhone` | String. Compared after stripping non-digits. Valid length 8–15 |
| `lang` | `'ar'` \| `'en'`. UI only |

### Contact draft

Local to `app/contact-page.tsx`: `name` (max 120), `contact` (max 160), `inquiry` (one of five ids), `message` (max 3000). Discarded after copy. Not app state.

## 5. Current Data Sources

| Entity | Source | File / symbol |
|---|---|---|
| Products | Hardcoded seed, then React state | `initialProducts` → `products` in `app/page.tsx` |
| Categories | Hardcoded seed, then React state | `categories` in `app/data.ts` → `categories` state |
| Colors, sizes, variants | Fields on the product seed / editor | `app/data.ts`, `app/product-editor.tsx` |
| Subcategories | Generated by regex | `productTypes`, `catalogGroups` |
| Traders | Hardcoded in `useState` initializer | `merchants` in `app/page.tsx` |
| Session user | React state | `user` username. Empty means guest |
| Price lists | Hardcoded, then React state | `initialPriceLists` in `app/pricing.ts` → `priceLists` |
| Unsaved price edits | React state | `priceDrafts` |
| Currencies | Hardcoded in `useState` | `currencies` in `app/page.tsx` |
| Cart | React state. Cleared on refresh, sign-out, and account switch | `cart` |
| Orders | Seed plus generated on submit | `sampleOrders` → `orders`. New objects in `submit` |
| Invoices | Seed plus admin editor | `invoices` |
| Invoice / product image files | Static `public/` or temporary `blob:` | `public/assets`, `public/files`, `URL.createObjectURL` |
| WhatsApp number | React state, default empty | `companyPhone` |
| Language | React state | `lang` |
| Contact message | Component state, then clipboard | `app/contact-page.tsx` |
| PDF / Excel files | Generated in the browser | `app/files.ts` |
| External shop API | None | |
| Cloudflare D1 / Drizzle | Present as empty scaffold, unused | `db/schema.ts` |

Image rule (`assetSrc` in `app/data.ts`): if the value starts with `blob:`, `data:`, or `/`, use it as the URL. Otherwise request `/assets/{value}.jpg`.

`PriceListManager` does not use `assetSrc`. It treats `blob:` as a URL and everything else as `/assets/{image}.jpg`.

## 6. User Flows

### Guest browsing

1. Open `/`. Hash empty or `#home`. Language Arabic, RTL.
2. Prices show "Sign in to see your price". Sort by price is hidden.
3. Open a category (`#products?category=1`) or all products (`#products`).
4. Search and filters run on the in-memory array.
5. Open a product dialog. Choose color and size. Add prompts the login dialog.
6. Cart page is reachable but stays empty until sign-in and add.
7. Portal asks for sign-in. Admin is still reachable from the footer with no login.

### Trader login

1. Account button or "Trader sign in" opens the dialog.
2. Either submit `trader` or `export` with password `demo123`, or click "Local trader" / "Export trader".
3. `signIn` checks `active`. On success `user` is the username. A different username clears the cart.
4. Prices come from `effectivePrice(product, list)` and the currency symbol.
5. Sign out from the footer clears `user` and `cart`.

### Product selection and add to cart

1. Signed-in user picks color and size on the card or in the dialog.
2. `add` rejects unavailable variants, non-finite prices, and qty below `min` or non-integers.
3. Default add from the card uses `product.min` and the selected variant.
4. Line key is `id + '-' + option`. Same key increases qty. Price stored on the line is the list price at add time.
5. A later `useEffect` drops lines whose product no longer has a finite price and rewrites line prices from the current list.

### Submit order

1. Cart → "Review request" sets `review` and locks qty edits.
2. "Send request" runs `submit`.
3. It rechecks availability, price, and minimums.
4. Waits 750ms. If `simulateError` is checked, it stops, keeps the cart, and shows an error. The checkbox resets.
5. Otherwise it creates an order with status `review`, prepends it to `orders`, clears cart and note, and opens `#confirmation`.
6. Refresh loses `activeOrder`, `orders` changes, and the cart.

### View trader orders

1. `#portal`, tab "My orders".
2. Rows are `orders` whose `merchant` equals the trader's **Arabic** name.
3. Status filter is local. Eye opens the detail dialog. PDF downloads in the browser.
4. The export trader sees none of the three sample orders.

### View / download invoice

1. Portal tab "Invoices & files".
2. Rows where `invoice.merchant === merchant.id`.
3. View and download use `invoice.url` when present. The demo file is `public/files/invoice-demo.pdf`.
4. Admin can attach a new PDF for a chosen trader id. That `blob:` URL dies on refresh.

### Admin product management

1. Footer → `#admin` → Products.
2. Add/edit in `ProductEditor`. At least one photo. Colors need unique names, valid HEX, and at least one size. Options are regenerated from colors and sizes.
3. Save updates `products` in memory. Duplicate code is rejected.
4. Import validates the workbook, then appends simplified products.
5. Export downloads the current filtered array.

### Admin trader management

1. Admin → Traders. Add or edit name, username, email, price list, active flag.
2. Duplicate username is rejected.
3. Assigned list changes which prices that username sees after the next render. `signIn` does not store the list id; it looks up `merchants` by username.

### Admin price management

1. Admin → Price lists. Open a list or create one.
2. Edit prices in a draft. ILS lists may omit a product and fall back to `product.price`. Other currencies must price every product before save.
3. Save replaces that list's `prices` and `currency`. Assigned traders see the new numbers. Cart lines reprice or disappear if a price becomes NaN.

### Other flows

- Admin changes order status in the orders table. The trader portal shows the new label immediately because it is the same array.
- Admin adds a currency or invoice the same way: dialog submit, in-memory array.
- Admin types a WhatsApp number. Storefront buttons then open `wa.me`. Nothing is sent automatically.
- Contact: fill form → prepare → copy and/or open WhatsApp. Nothing is stored.

## 7. Backend Integration Points

Do not add these calls yet. When integration happens, replace the data behind these symbols. Do not redesign the screens.

| Current file | Symbol | Backend responsibility | Likely operation |
|---|---|---|---|
| `app/page.tsx` | `products` / `setProducts`, seed `initialProducts` | Durable catalog | Read catalog. Create/update product |
| `app/page.tsx` | `categories` / `setCategories` | Durable categories and images | Read, create, update |
| `app/page.tsx` | `merchants` / `setMerchants` | Trader accounts and assigned list | Read, create, update, set active |
| `app/page.tsx` | `user`, `signIn`, login form | Authenticate username. Stop trusting a shared password | Login, logout, current user |
| `app/pricing.ts`, `app/page.tsx` | `priceLists`, `effectivePrice`, `priceDrafts` | Store list currency and per-product prices. Keep the ILS fallback | Read lists. Update one list |
| `app/page.tsx` | `currencies` | Store code, name, symbol | Read, create, update |
| `app/page.tsx` | `cart` | Optional. Today it is not stored | None until submit, unless cart must survive refresh |
| `app/page.tsx` | `submit`, `orders`, `sampleOrders` | Persist the request and return it after reload | Create order. List mine. List all. Update status |
| `app/page.tsx` | `invoices` | Persist record and file | List mine. List all. Create/update with file upload |
| `app/page.tsx` | `companyPhone` | Persist the company number | Read and update one setting |
| `app/page.tsx` | import confirm handler | Persist imported rows, including the simplified image/option defaults | Bulk create products |
| `app/files.ts` | `exportExcel`, `downloadOrder` | No server file required if the client already has the rows | — |
| `app/product-editor.tsx` | photo and color `URL.createObjectURL` | Store image files and return a URL `assetSrc` can use | Upload image |
| `app/page.tsx` | category and invoice file inputs | Same for category images and invoice PDFs | Upload file |
| `app/contact-page.tsx` | contact draft | None. It is not saved today | — |

Guest catalog read can omit prices or return them only with a trader session. The UI hides prices when `merchant` is missing.

Admin has no identity. A backend must not leave write APIs public just because the footer link is public. How admin is authenticated is not defined in this frontend.

## 8. Files That Django Should NOT Affect

Leave these as client behavior unless a later task explicitly wires data into them:

- `app/globals.css`, `app/font.css`, `components/ui/**`, `public/favicon.svg`
- Hash routing: `readStoreRoute`, `catalogHref`, `go`, `openCatalog` in `app/page.tsx` and `app/catalog-navigation.ts`
- Language toggle and RTL/LTR
- Catalog search, filters, sort, pills, and price-list table filters/pagination
- `ProductCard` layout, dialogs, empty states, toasts
- `app/trade-pages.tsx`, about/FAQ copy in `app/page.tsx`
- `app/contact-page.tsx` compose/copy behavior
- `app/cart-quantity.tsx` and in-memory cart editing before submit
- `simulateError` checkbox (demo only; do not implement)
- `downloadOrder` and `exportExcel` generation
- `productTypes` regex subcategories, as long as product names stay the source
- `app/chatgpt-auth.ts` (unused)
- `db/**`, `examples/d1/**`, Cloudflare/vinext config, for shop features
- WhatsApp link opening. Only the stored phone number needs a backend

Do not restyle pages or split this UI into a new design to fit Django.

## 9. Backend Requirements Derived From Frontend

### Required for MVP

Enough for a guest to browse and a trader to sign in and still see an order after refresh.

- Categories with Arabic and English names and an image.
- Products with the fields in section 4, including colors, sizes, options, and unavailable variants.
- Product and color images reachable at a URL the current `assetSrc` rule accepts.
- Two concepts already in the UI: base ILS price on the product, and a price list of per-product prices.
- Trader: names, username, email, active flag, one price list.
- Login that selects that trader. Prices hidden for guests.
- `effectivePrice` rules, including "not set" for a non-ILS list with no price.
- Create order from cart lines: product, option string, qty, unit price, symbol or code, note, status `review`, trader.
- List that trader's orders and one order's lines.
- Seed or equivalent of the current 8 products, 4 categories, 2 lists, and 2 traders so the existing screens have data.
- No payment, tax, shipping, or stock quantity. Availability is a boolean plus unavailable option strings.

### Required for full current frontend functionality

- Admin create/update for products, categories, traders, price lists, currencies, invoices, and order status. Match the validations in section 3. The UI has no deletes.
- Invoice file attached to a trader id, with a manually entered amount.
- Excel import of up to 1000 rows with the columns and checks in `readImport`.
- Company WhatsApp number, digits only, length 8–15.
- Sample orders are optional data. If they are seeded, portal filtering uses the Arabic trader name today.
- Currency list with code, display name, and symbol. No FX conversion.
- New non-ILS price lists cannot be saved until every product has a price.
- ILS lists fall back to `product.price` when a cell is empty.

### Optional / later

- Persisting the cart before submit.
- Persisting UI language.
- Saving contact-form inquiries.
- Sending WhatsApp, email, or the PDF automatically.
- Server-side PDF or Excel. The browser already builds them.
- Payment, accounting invoices, warehouse stock, delivery, taxes.
- Admin audit log, delete actions, or per-button permissions beyond what the screens show.
- Turning regex subcategories into managed records.
- Using the unused Drizzle/D1 scaffold.

## 10. Risks / Data Inconsistencies

Django must absorb these. Do not "fix" them by changing the frontend in this phase.

- **Refresh clears everything.** There is no browser storage. A backend only helps after the page loads data from it.
- **Category ids are array indexes.** Index `0` is the fake All row. `Product.cat` and `Category_ID` point at `categories[n]`. Inserting or reordering categories would change product assignment if this stays index-based.
- **Several id styles.** Products are numbers. Traders, price lists, and currencies are strings. New ids are `Date.now()` or `` `list-${Date.now()}` ``. They are only unique within one browser session.
- **Order trader vs invoice trader.** `Order.merchant` is the Arabic name. `Invoice.merchant` is the trader id. Portal order filter compares Arabic names. Portal invoice filter compares ids. Renaming a trader would hide that trader's old orders in the current UI.
- **Order currency is the symbol.** Price lists store `ILS` / `USD`. Submitted `Order.currency` stores `₪` / `$`. Sample orders use `₪`.
- **Variant identity is a display string.** Cart and order lines do not store color id or size id. Image lookup depends on the prefix `` `${ar} / ${en} · ` ``. Renaming a color breaks that match.
- **Options are duplicated.** They are stored both as `options[]` and as `colors` × `sizes`. The product editor regenerates `options` on save. Excel import sets only `options`.
- **`badge` is display-only** and easy to drop because the editor never shows it.
- **Images are keys or blob URLs.** `blob:` and `data:` URLs cannot be sent to a server as durable files. Seed images are keys like `men-shirt`, not full paths. `PriceListManager` assumes every non-blob image is `/assets/{key}.jpg`.
- **Imported products are incomplete** versus the editor: fixed image `men-shirt`, one default option, no colors or sizes.
- **One shared password, plus a bypass.** Any active username works with `demo123`. The two quick buttons sign in with no password. Merchants do not store a password.
- **Admin is unauthenticated.** `#admin` is a public hash.
- **No deletes** for products, categories, traders, lists, currencies, orders, or invoices. Inactive is the only trader removal.
- **Currency code edits do not cascade** to `PriceList.currency`.
- **English PDF trader name is hardcoded** inside `downloadOrder` to Horizon Store or Atlas Trading. Other traders will be mislabeled in English PDFs until that client function is changed later. Do not change it as part of backend setup.
- **New order ids** use `1043 + orders.length - 3`, which only lines up while the three sample orders exist.
- **Cart reprices from the list** and drops lines with no price. A saved order must keep the unit price from submit time, which the current `Order.items` already copies.
- **Subcategories depend on names.** A product without a matching Arabic or English word has no subcategory.
- **Contact and WhatsApp do not create business records.**

## 11. Backend Planning Summary

| Area | Frontend status | Backend needed | Priority |
|---|---|---|---|
| Home, info, traders, export pages | Static UI over the catalog | Catalog read only where products/categories show | MVP for catalog blocks; copy stays client |
| Catalog and product dialog | Works from memory | Products, categories, images, variants | MVP |
| Guest vs trader prices | Works | Auth and price lists; hide prices when logged out | MVP |
| Login | Demo password and quick entry | Real trader login | MVP |
| Cart | Works until refresh | Keep client-side until submit | MVP client; persist later |
| Submit order | Memory only | Create order + lines | MVP |
| Confirmation | Lost on refresh | Read the saved order if the screen should reload | MVP if refresh must work |
| Trader orders | Filtered by Arabic name | List orders for the logged-in trader | MVP |
| Invoices | One static PDF plus memory uploads | Invoice row, trader id, file | Full UI |
| Admin access | Public hash, no user | Access rule not specified by the UI | Decide before admin APIs |
| Product admin | Full editor, session only | Create/update product and images | Full UI |
| Category admin | Create/update, index ids | Categories with stable ids | Full UI |
| Trader admin | Create/update, no password field | Trader record and active flag | Full UI |
| Price lists | Full editor, ILS fallback | Lists and per-product prices | MVP for the two seed lists; editor is full UI |
| Currencies | Create/update, no FX | Code, name, symbol | Full UI |
| Order status | Admin dropdown | Update status | Full UI |
| Excel | Client parse and download | Bulk create for import; export can stay client | Full UI |
| PDF | Client `jspdf` | Order payload only | No server PDF |
| WhatsApp setting | Session phone, `wa.me` only | One phone setting | Full UI |
| Contact form | Copy only | None | Later only if a new feature is requested |
| Payment, stock qty, shipping, tax | Not in the UI | Do not add | Out of scope |
