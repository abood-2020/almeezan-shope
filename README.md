# Riwaq wholesale frontend

Bilingual Arabic / English interactive B2B theme. Arabic RTL is the default.

## Demo journeys
- Browse and filter the catalog; inspect products, options, and minimum quantities.
- Use Trader sign-in. Local account: `trader` / `demo123`; export account: `export` / `demo123`. Quick-entry buttons are also provided.
- Each trader is assigned an independently priced list and currency. There is no currency conversion.
- Add products, change quantities, review, and submit a demo request. The optional error simulation demonstrates retry without losing the cart.
- Download a PDF containing trader details, item photos, codes, options, prices, quantities, and totals.
- Explore the trader portal for orders and administrator-provided invoice files.
- Open Administration from the footer: edit products, categories, traders, price lists, currencies, statuses, and uploaded invoice records. Import Excel using the supplied fixed-column template with validation; export filtered records to XLSX.

## Boundaries
All business state is held in browser memory for the current session. Refreshing resets it. Demo sign-in is a UI simulation, not secure authentication. No database, backend business logic, payment, taxes, delivery, warehouse, accounting invoice creation, exchange service, or WhatsApp API is implemented.

The company WhatsApp number was not supplied. The confirmation action asks for a real international phone number before opening wa.me without a pre-filled message or attachments. Replace this with the company's approved number when provided.

Photos and categories demonstrate a broad general-merchandise selection and are replaceable. The store name is a replaceable demo identity. Image source references are in public/assets/asset-manifest.json. Hero is generated original artwork. Cairo is hosted locally.

## Development
Run the project's existing dev/build scripts. The Sites wrapper serves the frontend but contains no application business backend.

## Validation
TypeScript checking and production build are required for this version. Cloud-browser visual QA is unavailable in this environment because the required control-browser skill is not exposed. The optional feature-detected WebMCP catalog-search tool could not be exercised in a supported browser context.

## Administration refinement
The administration workspace has its own compact header, with no storefront search, categories, cart, or marketing footer. Price lists open from a compact index showing product count, assigned traders and currency. List details support name/code search, category filters, ten products per page, draft retention across admin tabs, save and discard. Product editing contains only the base price in ILS; independent list prices are stored per list and product. No currency conversion occurs. New products use their base price for ILS lists and require an explicit price for foreign-currency lists. The Excel product template uses Base_Price_ILS and accepts the former Price_ILS column for compatibility.

The storefront has a prominent fixed WhatsApp button. A company number is still required to open a real company conversation.
