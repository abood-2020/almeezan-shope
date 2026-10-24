import logging
import time
from datetime import date
from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, OperationalError, connection, transaction
from django.db.models import F, Prefetch, Q
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from shop.models import (
    Category,
    Currency,
    ExchangeRate,
    GoogleAccount,
    Invoice,
    Order,
    OrderLine,
    PriceList,
    PriceListCategoryRule,
    PriceListItem,
    PriceListProductRule,
    Product,
    ProductColor,
    ProductImage,
    ProductOption,
    ProductSize,
    SiteSetting,
    Trader,
    TraderCategoryDiscount,
)
from shop.pricing import PriceChangeRequired, compare_expected_price, parse_discount, quantize_money, quote_many


def get_active_trader(user):
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    trader = (
        Trader.objects.select_related("user", "price_list__currency")
        .filter(user=user)
        .first()
    )
    if trader is None or not trader.is_active:
        return None
    return trader


def login_trader(request, username, password):
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Invalid credentials.")
    if not user.is_active:
        raise PermissionDenied("This account is inactive.")
    trader = (
        Trader.objects.select_related("user", "price_list__currency")
        .filter(user=user)
        .first()
    )
    if trader is None:
        raise PermissionDenied("No trader profile is linked to this account.")
    if not trader.is_active:
        raise PermissionDenied("This trader account is inactive.")
    login(request, user)
    return trader


def catalog_products(trader=None):
    queryset = Product.objects.select_related("category", "base_currency", "original_currency").prefetch_related(
        "images",
        "colors",
        "sizes",
        "options",
    )
    if trader is not None:
        queryset = queryset.prefetch_related(
            Prefetch(
                "price_list_items",
                queryset=PriceListItem.objects.filter(price_list=trader.price_list),
            )
        )
    return queryset.order_by("id")


def _line_error(index, message):
    raise ValidationError({"items": [f"Item {index + 1}: {message}"]})


def prepare_order_lines(trader, items, acknowledge_price_changes=False, display_currency=None):
    if not items:
        raise ValidationError({"items": ["Add at least one product."]})
    products = []
    resolved = []
    for index, item in enumerate(items):
        try:
            product = Product.objects.select_related("base_currency", "original_currency", "category").get(pk=item["product_id"])
        except Product.DoesNotExist:
            _line_error(index, "Unknown product.")
        if not product.available:
            _line_error(index, "This product is unavailable.")
        option = ProductOption.objects.filter(product=product, label=item["option"]).first()
        if option is None:
            _line_error(index, "This option does not belong to the product.")
        if not option.is_available:
            _line_error(index, "This option is unavailable.")
        quantity = item["qty"]
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            _line_error(index, "Quantity must be a positive integer.")
        if quantity < product.min_qty:
            _line_error(index, f"Minimum quantity is {product.min_qty}.")
        products.append(product)
        resolved.append((index, item, product, option.label, quantity))
    display = (display_currency or trader.price_list.currency_id).upper()
    quotes = quote_many(trader.price_list, products, display_currency=display, trader=trader)
    if any(not quote.checkout_allowed for quote in quotes.values()):
        raise ValidationError({"display_currency": ["Exchange rates are too old to confirm a new order. Refresh the rates and try again."]})
    prepared = []
    changes = []
    for index, item, product, label, quantity in resolved:
        quote = quotes[product.id]
        if not quote.available or quote.unit_price is None:
            if quote.error == "missing_exchange_rate":
                _line_error(index, "No exchange rate is available for this product.")
            _line_error(index, "No price is set for this product on your price list.")
        expected = item.get("expected_unit_price")
        if not acknowledge_price_changes and not compare_expected_price(expected, quote):
            changes.append({
                "product_id": product.id,
                "option": label,
                "previous": f"{Decimal(str(expected)):.2f}",
                "current": f"{quote.unit_price:.2f}",
                "currency_code": display,
            })
        prepared.append((product, label, quantity, quote))
    if changes:
        raise PriceChangeRequired(changes)
    return prepared


def allocate_order_number(day: date) -> str:
    prefix = f"RW-{day.year}-"
    highest = 1000
    numbers = Order.objects.select_for_update().filter(number__startswith=prefix).values_list("number", flat=True)
    for number in numbers:
        suffix = number.removeprefix(prefix)
        if suffix.isdigit():
            highest = max(highest, int(suffix))
    return f"{prefix}{highest + 1}"


def create_order(trader, note, items, acknowledge_price_changes=False, display_currency=None):
    display = (display_currency or trader.price_list.currency_id).upper()
    prepared = prepare_order_lines(trader, items, acknowledge_price_changes, display)
    currency = Currency.objects.get(pk=display)
    snapshot_id = None
    provider = ""
    provider_date = None
    if any(quote.exchange_rate is not None for _product, _label, _quantity, quote in prepared):
        from shop.fx import current_snapshot

        snapshot = current_snapshot()
        if snapshot is not None:
            snapshot_id = snapshot.pk
            provider = snapshot.provider
            provider_date = snapshot.provider_date
    places = currency.decimal_places
    line_totals = []
    for product, label, quantity, quote in prepared:
        line_total = quantize_money(quote.unit_price * quantity, places)
        line_totals.append((product, label, quantity, quote, line_total))
    total = quantize_money(sum((line_total for *_, line_total in line_totals), Decimal("0")), places)
    today = timezone.localdate()
    for _ in range(3):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    number=allocate_order_number(today),
                    trader=trader,
                    trader_name_ar=trader.name_ar,
                    trader_name_en=trader.name_en,
                    trader_email=trader.user.email or "",
                    price_list_name_ar=trader.price_list.name_ar,
                    price_list_name_en=trader.price_list.name_en,
                    ordered_on=today,
                    status=Order.Status.REVIEW,
                    currency=currency,
                    currency_symbol=currency.symbol,
                    rate_snapshot_id=snapshot_id,
                    rate_provider=provider,
                    rate_provider_date=provider_date,
                    note=note or "",
                    total=total,
                )
                OrderLine.objects.bulk_create([
                    OrderLine(
                        order=order,
                        product=product,
                        product_code=product.code,
                        product_name_ar=product.name_ar,
                        product_name_en=product.name_en,
                        option_label=label,
                        unit_ar=product.unit_ar,
                        unit_en=product.unit_en,
                        category_path_ar=category_snapshot(product.category)[0],
                        category_path_en=category_snapshot(product.category)[1],
                        quantity=quantity,
                        unit_price=quote.unit_price,
                        base_price=quote.base_price,
                        base_currency=quote.base_currency,
                        original_price=quote.original_price,
                        original_currency=quote.original_currency,
                        discount_percent=quote.discount_percent,
                        exchange_rate=quote.exchange_rate,
                        pricing_note=quote.pricing_note,
                        line_total=line_total,
                    )
                    for product, label, quantity, quote, line_total in line_totals
                ])
            return Order.objects.prefetch_related("lines").select_related("currency", "trader").get(pk=order.pk)
        except IntegrityError:
            continue
    raise ValidationError("Could not allocate an order number.")


def category_snapshot(category):
    """Category names at order time. Stored on the line so later moves do not rewrite history."""
    arabic = []
    english = []
    seen = set()
    current = category
    while current is not None and current.pk not in seen:
        seen.add(current.pk)
        arabic.append(current.name_ar)
        english.append(current.name_en)
        if not current.parent_id:
            break
        current = Category.objects.filter(pk=current.parent_id).first()
    return " / ".join(reversed(arabic)), " / ".join(reversed(english))


def get_site_settings():
    setting = SiteSetting.objects.filter(pk=1).first()
    if setting is None:
        setting = SiteSetting(company_whatsapp_number="")
        setting.save()
    return setting


def google_profile_required(trader):
    account = GoogleAccount.objects.filter(user_id=trader.user_id).only("profile_completed").first()
    return bool(account and not account.profile_completed)


def authenticate_google(request, credential):
    from django.conf import settings

    from shop.google_auth import GoogleAuthError, verify_google_id_token

    client_id = settings.GOOGLE_CLIENT_ID
    if not client_id:
        raise GoogleAuthError("not_configured", 503)
    identity = verify_google_id_token(credential, client_id)
    account = GoogleAccount.objects.select_related("user").filter(sub=identity["sub"]).first()
    if account is not None:
        return _login_google_account(request, account, identity["email"])
    if User.objects.filter(email__iexact=identity["email"]).exists():
        raise GoogleAuthError("email_exists", 409)
    price_list = default_price_list()
    if price_list is None:
        raise GoogleAuthError("no_default_price_list", 503)
    try:
        trader = _create_google_trader(identity, price_list)
    except IntegrityError:
        account = GoogleAccount.objects.select_related("user").filter(sub=identity["sub"]).first()
        if account is None:
            raise GoogleAuthError("invalid", 409) from None
        return _login_google_account(request, account, identity["email"])
    login(request, trader.user)
    return trader, True


def _login_google_account(request, account, email):
    from shop.google_auth import GoogleAuthError

    user = account.user
    trader = (
        Trader.objects.select_related("user", "price_list__currency")
        .filter(user=user)
        .first()
    )
    if not user.is_active or trader is None or not trader.is_active:
        raise GoogleAuthError("inactive", 403)
    if email and email != account.email and not User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
        account.email = email
        account.save(update_fields=["email"])
        user.email = email
        user.save(update_fields=["email"])
    login(request, user)
    return trader, not account.profile_completed


def _create_google_trader(identity, price_list):
    import hashlib

    from shop.content import has_markup

    digest = hashlib.sha256(identity["sub"].encode()).hexdigest()
    username = f"g{digest[:20]}"
    trader_id = f"g{digest[:31]}"
    name = identity["name"]
    if not name or has_markup(name):
        name = identity["email"].split("@", 1)[0]
    name = name[:160]
    with transaction.atomic():
        user = User(username=username, email=identity["email"], is_staff=False, is_superuser=False, is_active=True)
        user.set_unusable_password()
        user.save()
        trader = Trader.objects.create(
            id=trader_id,
            user=user,
            name_ar=name,
            name_en=name,
            price_list=price_list,
        )
        GoogleAccount.objects.create(sub=identity["sub"], user=user, email=identity["email"])
    return Trader.objects.select_related("user", "price_list__currency").get(pk=trader.pk)


def complete_google_profile(trader, data):
    from shop.content import has_markup, normalize_phone, plain

    account = GoogleAccount.objects.filter(user_id=trader.user_id).first()
    if account is None or account.profile_completed:
        raise ValidationError({"profile": ["This account does not need a Google profile."]})
    name = plain(data.get("business_name"), "business_name", 160).strip()
    if has_markup(name) or len(name) < 2:
        raise ValidationError({"business_name": ["Enter the business name."]})
    phone = normalize_phone(str(data.get("phone") or ""), "phone")
    if not phone:
        raise ValidationError({"phone": ["Enter a phone number."]})
    country = plain(data.get("country"), "country", 80).strip()
    city = plain(data.get("city"), "city", 80).strip()
    if len(country) < 2 or len(city) < 2:
        raise ValidationError({"country": ["Enter the country and city."]})
    trader.name_ar = name
    trader.name_en = name
    trader.phone = phone
    trader.country = country
    trader.city = city
    trader.full_clean()
    trader.save()
    account.profile_completed = True
    account.save(update_fields=["profile_completed"])
    return Trader.objects.select_related("user", "price_list__currency").get(pk=trader.pk)


def login_staff(request, username, password):
    user = User.objects.filter(username=username).first()
    if user is None or not user.check_password(password):
        raise AuthenticationFailed("Invalid credentials.")
    if not user.is_active:
        raise PermissionDenied("This account is inactive.")
    if not user.is_staff:
        raise PermissionDenied("Staff access is required.")
    login(request, user)
    return user


def staff_payload(user):
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "is_staff": user.is_staff,
    }


def _reject_blob(value, field):
    if isinstance(value, str) and value.startswith("blob:"):
        raise ValidationError({field: ["Browser blob URLs are not stored."]})


def _product_queryset():
    return catalog_products()


PRODUCT_FIELDS = (
    "name_ar",
    "name_en",
    "code",
    "category",
    "base_price_ils",
    "base_price_usd",
    "base_currency",
    "original_price",
    "original_currency",
    "unit_ar",
    "unit_en",
    "min_qty",
    "available",
    "description_ar",
    "description_en",
    "badge",
)


def save_product(data, product=None):
    creating = product is None
    with transaction.atomic():
        if creating:
            product = Product()
        for field in PRODUCT_FIELDS:
            if field in data:
                setattr(product, field, data[field])
        _align_original_price(product, data)
        if "code" in data:
            product.code = data["code"].strip()
        try:
            product.full_clean()
            product.save()
        except IntegrityError as exc:
            raise ValidationError({"code": ["This code is already in use."]}) from exc
        _sync_choices(product, data, creating)
        _sync_image_keys(product, data)
        return _product_queryset().get(pk=product.pk)


def _align_original_price(product, data):
    """Keep the fixed original price authoritative without erasing a second legacy amount."""
    if product.original_price is not None and product.original_currency_id:
        product.price_review_required = False
        if product.original_currency_id == "ILS":
            product.base_price_ils = product.original_price
            product.base_currency_id = product.base_currency_id or "ILS"
        elif product.original_currency_id == "USD":
            product.base_price_usd = product.original_price
        elif product.original_currency_id not in {"CNY", "USD", "ILS"}:
            raise ValidationError({"original_currency": ["Choose CNY, USD or ILS."]})
        return
    if "base_price_ils" in data and product.original_currency_id == "ILS":
        product.original_price = product.base_price_ils
    if "base_price_usd" in data and product.original_currency_id == "USD" and product.base_price_usd is not None:
        product.original_price = product.base_price_usd
    if product.original_price is None and product.base_price_usd is not None:
        product.price_review_required = True
    if product.base_price_ils is None:
        product.base_price_ils = product.original_price if product.original_currency_id == "ILS" else Decimal("0")


def _sync_choices(product, data, creating):
    relevant = {"colors", "sizes", "options", "unavailable_variants"} & set(data)
    if not relevant:
        if creating:
            raise ValidationError({"options": ["Add at least one selling option."]})
        return
    unavailable = set(data.get("unavailable_variants") or [])
    if relevant == {"unavailable_variants"}:
        for option in product.options.all():
            option.is_available = option.label not in unavailable
            option.save(update_fields=["is_available"])
        return

    if "colors" in data:
        colors = []
        seen_ar = set()
        seen_en = set()
        for index, row in enumerate(data["colors"]):
            name_ar = row["name_ar"].strip()
            name_en = row["name_en"].strip()
            if not name_ar or not name_en:
                raise ValidationError({"colors": ["Each color needs an Arabic and English name."]})
            if name_ar.casefold() in seen_ar or name_en.casefold() in seen_en:
                raise ValidationError({"colors": ["Color names must be unique."]})
            seen_ar.add(name_ar.casefold())
            seen_en.add(name_en.casefold())
            _reject_blob(row.get("image_key", ""), "colors")
            colors.append((index, name_ar, name_en, row["hex"].upper(), row.get("image_key") or ""))
    else:
        colors = [
            (color.sort_order, color.name_ar, color.name_en, color.hex_code, color.image_key)
            for color in product.colors.all()
        ]

    if "sizes" in data:
        sizes = []
        seen = set()
        for index, value in enumerate(data["sizes"]):
            value = value.strip()
            if not value or value in seen:
                continue
            seen.add(value)
            sizes.append((index, value))
    else:
        sizes = [(size.sort_order, size.value) for size in product.sizes.all()]

    if colors and not sizes:
        raise ValidationError({"sizes": ["Add at least one size when colors are set."]})

    if colors:
        labels = [
            ProductOption.label_for(name_ar, name_en, size)
            for _, name_ar, name_en, _, _ in colors
            for _, size in sizes
        ]
    elif "options" in data:
        labels = []
        for label in data["options"]:
            label = label.strip()
            if label and label not in labels:
                labels.append(label)
    else:
        labels = [option.label for option in product.options.all()]

    if not labels:
        raise ValidationError({"options": ["Add at least one selling option."]})

    previous_color_files = {
        (color.name_ar, color.name_en): color.image.name
        for color in product.colors.all()
        if color.image
    }
    product.options.all().delete()
    product.colors.all().delete()
    product.sizes.all().delete()
    color_rows = [
        ProductColor.objects.create(
            product=product,
            name_ar=name_ar,
            name_en=name_en,
            hex_code=hex_code,
            image_key=image_key,
            sort_order=index,
        )
        for index, name_ar, name_en, hex_code, image_key in colors
    ]
    for row in color_rows:
        previous = previous_color_files.get((row.name_ar, row.name_en))
        if previous and not row.image:
            row.image.name = previous
            row.save(update_fields=["image"])
    size_rows = [
        ProductSize.objects.create(product=product, value=value, sort_order=index)
        for index, value in sizes
    ]
    links = {
        ProductOption.label_for(color.name_ar, color.name_en, size.value): (color, size)
        for color in color_rows
        for size in size_rows
    }
    for index, label in enumerate(labels):
        color, size = links.get(label, (None, None))
        ProductOption.objects.create(
            product=product,
            label=label,
            color=color,
            size=size,
            is_available=label not in unavailable,
            sort_order=index,
        )


def _sync_image_keys(product, data):
    if "gallery" not in data and "image_key" not in data:
        return
    if "gallery" in data:
        keys = data["gallery"]
    else:
        key = data.get("image_key") or ""
        keys = [key] if key else []
    for key in keys:
        _reject_blob(key, "gallery")
    product.images.filter(image="").delete()
    has_primary = product.images.filter(is_primary=True).exists()
    for index, key in enumerate(keys):
        ProductImage.objects.create(
            product=product,
            image_key=key,
            sort_order=index,
            is_primary=not has_primary and index == 0,
        )


def validate_image_upload(upload):
    allowed = {"image/jpeg", "image/png", "image/webp", "image/gif"}
    extension = upload.name.rsplit(".", 1)[-1].lower() if "." in upload.name else ""
    if upload.content_type not in allowed or extension not in {"jpg", "jpeg", "png", "webp", "gif"}:
        raise ValidationError({"file": ["Upload a JPEG, PNG, WEBP, or GIF image."]})


def validate_pdf_upload(upload):
    if not upload.name.lower().endswith(".pdf"):
        raise ValidationError({"file": ["Upload a PDF file."]})
    header = upload.read(5)
    upload.seek(0)
    if header != b"%PDF-":
        raise ValidationError({"file": ["The file is not a valid PDF."]})


def add_product_image(product, upload, is_primary=False, sort_order=0):
    validate_image_upload(upload)
    with transaction.atomic():
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)
        elif not product.images.filter(is_primary=True).exists():
            is_primary = True
        return ProductImage.objects.create(
            product=product,
            image=upload,
            sort_order=sort_order,
            is_primary=is_primary,
        )


def update_product_image(image, upload=None, is_primary=None, sort_order=None):
    validate_image_upload(upload) if upload is not None else None
    with transaction.atomic():
        if upload is not None:
            image.image.delete(save=False)
            image.image = upload
        if sort_order is not None:
            image.sort_order = sort_order
        if is_primary:
            ProductImage.objects.filter(product=image.product, is_primary=True).exclude(pk=image.pk).update(is_primary=False)
            image.is_primary = True
        elif is_primary is False:
            image.is_primary = False
        image.save()
        if not ProductImage.objects.filter(product=image.product, is_primary=True).exists():
            fallback = ProductImage.objects.filter(product=image.product).order_by("sort_order", "id").first()
            if fallback is not None:
                fallback.is_primary = True
                fallback.save(update_fields=["is_primary"])
        return image


def delete_product_image(image):
    product = image.product
    was_primary = image.is_primary
    if image.image:
        image.image.delete(save=False)
    image.delete()
    if was_primary:
        fallback = ProductImage.objects.filter(product=product).order_by("sort_order", "id").first()
        if fallback is not None:
            fallback.is_primary = True
            fallback.save(update_fields=["is_primary"])


def set_color_image(color, upload):
    validate_image_upload(upload)
    if color.image:
        color.image.delete(save=False)
    color.image = upload
    color.save(update_fields=["image"])
    return color


def save_category(data, category=None, image=None):
    creating = category is None
    with transaction.atomic():
        if creating:
            category = Category()
        for field in ("name_ar", "name_en", "image_key"):
            if field in data:
                setattr(category, field, data[field].strip() if isinstance(data[field], str) else data[field])
        if "parent_id" in data:
            category.parent_id = data["parent_id"]
        if "sort_order" in data:
            category.sort_order = data["sort_order"]
        if "image_key" in data:
            _reject_blob(category.image_key, "image_key")
        if image is not None:
            validate_image_upload(image)
            if category.image:
                category.image.delete(save=False)
            category.image = image
        category.full_clean()
        category.save()
        return category


def save_trader(data, trader=None):
    creating = trader is None
    password = data.get("password")
    with transaction.atomic():
        if creating:
            if Trader.objects.filter(pk=data["id"]).exists():
                raise ValidationError({"id": ["This trader id is already in use."]})
            user = User(username=data["username"], email=data.get("email") or "")
            if password:
                user.set_password(password)
            else:
                user.set_unusable_password()
        else:
            user = trader.user
            if "username" in data:
                user.username = data["username"]
            if "email" in data:
                user.email = data["email"]
        username = user.username
        taken = User.objects.filter(username=username)
        if user.pk:
            taken = taken.exclude(pk=user.pk)
        if taken.exists():
            raise ValidationError({"username": ["This username is already in use."]})
        if "active" in data:
            user.is_active = data["active"]
        user.full_clean()
        user.save()
        if creating:
            trader = Trader(id=data["id"], user=user)
        for field in ("name_ar", "name_en", "price_list", "phone", "country", "city"):
            if field in data:
                setattr(trader, field, data[field])
        if "active" in data:
            trader.is_active = data["active"]
        trader.full_clean()
        trader.save()
        if "category_discounts" in data:
            _replace_trader_discounts(trader, data["category_discounts"])
        return Trader.objects.select_related("user", "price_list__currency").get(pk=trader.pk)


def _replace_trader_discounts(trader, rows):
    seen = set()
    cleaned = []
    for row in rows:
        category = row["category"]
        if category.id in seen:
            raise ValidationError({"category_discounts": ["Each category can have only one discount."]})
        seen.add(category.id)
        percent = parse_discount(row["discount_percent"])
        cleaned.append((category, percent))
    TraderCategoryDiscount.objects.filter(trader=trader).delete()
    TraderCategoryDiscount.objects.bulk_create([
        TraderCategoryDiscount(trader=trader, category=category, discount_percent=percent)
        for category, percent in cleaned
    ])


def set_trader_password(trader, password):
    trader.user.set_password(password)
    trader.user.save(update_fields=["password"])


LAST_ADMIN_MESSAGE = (
    "Cannot revoke the last active administrator. At least one active administrator must remain."
)
access_log = logging.getLogger("shop.access")


class AdminAccessError(Exception):
    def __init__(self, code, detail):
        self.code = code
        self.detail = detail


def _lock_admin_rows(user_id):
    """Serialize administrator changes. PostgreSQL locks the relevant users; SQLite locks on write."""
    if connection.features.has_select_for_update:
        list(
            User.objects.select_for_update()
            .filter(Q(pk=user_id) | Q(is_staff=True, is_active=True))
            .order_by("pk")
        )
        return
    User.objects.filter(pk=user_id).update(is_staff=F("is_staff"))


def change_trader_admin(actor, trader, grant):
    """Grant or remove application administration. is_staff is the only privilege this changes."""
    if not getattr(actor, "is_authenticated", False) or not actor.is_active or not actor.is_staff:
        raise PermissionDenied("Staff access is required.")
    attempts = 3 if connection.vendor == "sqlite" else 2
    for attempt in range(attempts):
        try:
            return _change_trader_admin(actor, trader, grant)
        except OperationalError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))
    raise OperationalError("Could not update administrator access.")


def _change_trader_admin(actor, trader, grant):
    with transaction.atomic():
        _lock_admin_rows(trader.user_id)
        user = User.objects.get(pk=trader.user_id)
        trader = Trader.objects.select_related("user", "price_list__currency").get(pk=trader.pk)
        previous = bool(user.is_staff)
        if grant:
            if not user.is_active or not trader.is_active:
                raise AdminAccessError("inactive_account", "This account is inactive.")
            if previous:
                return trader, False
            user.is_staff = True
            user.save(update_fields=["is_staff"])
        else:
            if not previous:
                return trader, False
            others = User.objects.filter(is_staff=True, is_active=True).exclude(pk=user.pk).exists()
            if user.is_active and not others:
                raise AdminAccessError("last_admin", LAST_ADMIN_MESSAGE)
            user.is_staff = False
            user.save(update_fields=["is_staff"])
        access_log.info(
            "admin_access actor_id=%s actor=%s target_user_id=%s target=%s action=%s previous_is_staff=%s new_is_staff=%s",
            actor.pk,
            actor.get_username(),
            user.pk,
            user.get_username(),
            "promote" if grant else "revoke",
            previous,
            user.is_staff,
        )
        trader.user = user
        return trader, True


def save_currency(data, currency=None):
    code = data["code"].upper() if "code" in data else None
    if currency is None:
        if Currency.objects.filter(pk=code).exists():
            raise ValidationError({"code": ["This currency code already exists."]})
        currency = Currency(code=code, name=data["name"].strip(), symbol=data["symbol"].strip())
    else:
        if code and code != currency.code:
            raise ValidationError({"code": ["Currency code cannot be changed."]})
        if "name" in data:
            currency.name = data["name"].strip()
        if "symbol" in data:
            currency.symbol = data["symbol"].strip()
    currency.full_clean()
    currency.save()
    return currency


def save_price_list(data, price_list=None):
    creating = price_list is None
    with transaction.atomic():
        if creating:
            if PriceList.objects.filter(pk=data["id"]).exists():
                raise ValidationError({"id": ["This price list id is already in use."]})
            price_list = PriceList(id=data["id"])
        for field in ("name_ar", "name_en", "currency", "is_active", "pricing_mode", "default_discount_percent", "discount_scope", "is_default"):
            if field in data:
                setattr(price_list, field, data[field])
        legacy = price_list.pricing_mode != PriceList.PricingMode.RULE_BASED
        if legacy and not creating and "currency" in data and data["currency"].code != "ILS":
            _require_complete_prices(price_list, set(price_list.items.values_list("product_id", flat=True)))
        if price_list.is_default:
            PriceList.objects.exclude(pk=price_list.pk).filter(is_default=True).update(is_default=False)
        price_list.full_clean()
        price_list.save()
        if "scope_categories" in data:
            price_list.scope_categories.set(data["scope_categories"])
        return _priced_list(price_list.pk)


def _require_complete_prices(price_list, product_ids):
    if price_list.currency_id == "ILS" or (getattr(price_list, "currency", None) and price_list.currency.code == "ILS"):
        return
    required = set(Product.objects.values_list("id", flat=True))
    if set(product_ids) != required:
        raise ValidationError({"prices": ["Enter a price for every product before saving a non-ILS list."]})


def _priced_list(price_list_id):
    return PriceList.objects.select_related("currency").prefetch_related(
        "items", "scope_categories", "category_rules", "product_rules"
    ).get(pk=price_list_id)


def replace_price_list_prices(price_list, rows):
    product_ids = [row["product_id"] for row in rows]
    if len(product_ids) != len(set(product_ids)):
        raise ValidationError({"prices": ["Each product can appear only once."]})
    known = set(Product.objects.filter(id__in=product_ids).values_list("id", flat=True))
    unknown = [product_id for product_id in product_ids if product_id not in known]
    if unknown:
        raise ValidationError({"prices": ["Unknown product."]})
    if price_list.pricing_mode != PriceList.PricingMode.RULE_BASED and price_list.currency_id != "ILS":
        _require_complete_prices(price_list, product_ids)
    with transaction.atomic():
        kept = []
        for row in rows:
            item, _ = PriceListItem.objects.update_or_create(
                price_list=price_list,
                product_id=row["product_id"],
                defaults={"price": row["price"]},
            )
            kept.append(item.pk)
        PriceListItem.objects.filter(price_list=price_list).exclude(pk__in=kept).delete()
    return _priced_list(price_list.pk)


def default_price_list():
    """The list future trader registration should assign. Existing traders are left unchanged."""
    return (
        PriceList.objects.select_related("currency")
        .filter(is_default=True, is_active=True, pricing_mode=PriceList.PricingMode.RULE_BASED)
        .first()
    )


def pricing_mode_preview(price_list, pricing_mode):
    products = list(Product.objects.select_related("category", "base_currency").order_by("id"))
    current = quote_many(price_list, products)
    proposed = quote_many(price_list, products, mode=pricing_mode)
    rows = []
    for product in products:
        before = current[product.id]
        after = proposed[product.id]
        rows.append({
            "product_id": product.id,
            "code": product.code,
            "before": None if before.unit_price is None else f"{before.unit_price:.2f}",
            "after": None if after.unit_price is None else f"{after.unit_price:.2f}",
            "after_available": after.available,
            "after_error": after.error,
            "changed": before.unit_price != after.unit_price,
        })
    return rows


def set_pricing_mode(price_list, pricing_mode, confirm):
    if pricing_mode not in PriceList.PricingMode.values:
        raise ValidationError({"pricing_mode": ["Unsupported pricing mode."]})
    preview = pricing_mode_preview(price_list, pricing_mode)
    if not confirm:
        return {"confirm_required": True, "pricing_mode": pricing_mode, "changes": preview}
    if price_list.pricing_mode != pricing_mode:
        price_list.pricing_mode = pricing_mode
        price_list.full_clean()
        price_list.save(update_fields=["pricing_mode", "updated_at"])
    return price_list


def _require_rule_list(price_list):
    if price_list.pricing_mode != PriceList.PricingMode.RULE_BASED:
        raise ValidationError({"pricing_mode": ["Switch this list to discount rules before adding rules."]})


def save_category_rule(price_list, data, rule=None):
    _require_rule_list(price_list)
    discount = parse_discount(data["discount_percent"]) if "discount_percent" in data else None
    with transaction.atomic():
        if rule is None:
            category = data["category"]
            if PriceListCategoryRule.objects.filter(price_list=price_list, category=category).exists():
                raise ValidationError({"category_id": ["This category already has a rule on the list."]})
            rule = PriceListCategoryRule(price_list=price_list, category=category, discount_percent=discount)
        else:
            if "category" in data and data["category"].pk != rule.category_id:
                category = data["category"]
                if PriceListCategoryRule.objects.filter(price_list=price_list, category=category).exclude(pk=rule.pk).exists():
                    raise ValidationError({"category_id": ["This category already has a rule on the list."]})
                rule.category = category
            if discount is not None:
                rule.discount_percent = discount
        if "is_active" in data:
            rule.is_active = data["is_active"]
        rule.full_clean()
        rule.save()
    return rule


def save_product_rule(price_list, data, rule=None):
    _require_rule_list(price_list)
    discount = parse_discount(data["discount_percent"]) if "discount_percent" in data else None
    with transaction.atomic():
        if rule is None:
            product = data["product"]
            if PriceListProductRule.objects.filter(price_list=price_list, product=product).exists():
                raise ValidationError({"product_id": ["This product already has a rule on the list."]})
            rule = PriceListProductRule(price_list=price_list, product=product, discount_percent=discount)
        else:
            if "product" in data and data["product"].pk != rule.product_id:
                product = data["product"]
                if PriceListProductRule.objects.filter(price_list=price_list, product=product).exclude(pk=rule.pk).exists():
                    raise ValidationError({"product_id": ["This product already has a rule on the list."]})
                rule.product = product
            if discount is not None:
                rule.discount_percent = discount
        if "is_active" in data:
            rule.is_active = data["is_active"]
        rule.full_clean()
        rule.save()
    return rule


def save_exchange_rate(data, rate=None):
    source = data.get("source", getattr(rate, "source", None))
    target = data.get("target", getattr(rate, "target", None))
    with transaction.atomic():
        if rate is None:
            existing = ExchangeRate.objects.filter(source=source, target=target).first()
            if existing is not None:
                raise ValidationError({"target": ["An exchange rate for this currency pair already exists. Update it instead."]})
            rate = ExchangeRate(source=source, target=target, rate=data["rate"])
        else:
            if "source" in data:
                rate.source = data["source"]
            if "target" in data:
                rate.target = data["target"]
            if "rate" in data:
                rate.rate = data["rate"]
            duplicate = ExchangeRate.objects.filter(source=rate.source, target=rate.target).exclude(pk=rate.pk)
            if duplicate.exists():
                raise ValidationError({"target": ["An exchange rate for this currency pair already exists."]})
        if "is_active" in data:
            rate.is_active = data["is_active"]
        rate.full_clean()
        rate.save()
    return rate


def update_order_status(order, status):
    if status not in Order.Status.values:
        raise ValidationError({"status": ["Unsupported status."]})
    order.status = status
    order.save(update_fields=["status", "updated_at"])
    return order


def save_invoice(data, invoice=None, upload=None):
    creating = invoice is None
    with transaction.atomic():
        if creating:
            if Invoice.objects.filter(number=data["number"]).exists():
                raise ValidationError({"number": ["This invoice number already exists."]})
            invoice = Invoice(number=data["number"].strip())
        elif "number" in data and data["number"].strip() != invoice.number:
            raise ValidationError({"number": ["Invoice number cannot be changed."]})
        for field in ("trader", "issued_on", "amount"):
            if field in data:
                setattr(invoice, field, data[field])
        if upload is not None:
            validate_pdf_upload(upload)
            if invoice.file:
                invoice.file.delete(save=False)
            invoice.file = upload
            invoice.file_name = upload.name
            invoice.file_ref = ""
        invoice.full_clean()
        invoice.save()
        return invoice


def update_site_settings(data, files=None):
    from shop.content import replace_social_links
    from shop.uploads import UPLOAD_FIELDS, validate_public_upload

    data = dict(data)
    social_links = data.pop("social_links", None)
    setting = get_site_settings()
    for key, value in data.items():
        setattr(setting, key, value)
    for key, upload in (files or {}).items():
        if key not in UPLOAD_FIELDS or upload is None:
            continue
        validate_public_upload(upload, UPLOAD_FIELDS[key])
        current = getattr(setting, key)
        if current:
            current.delete(save=False)
        setattr(setting, key, upload)
    setting.save()
    if social_links is not None:
        replace_social_links(setting, social_links)
    return setting


def import_products(rows, lang="ar", category_map=None, embedded=None):
    english = str(lang or "").lower().startswith("en")

    def say(en, ar):
        return en if english else ar

    if len(rows) > 1000:
        raise ValidationError({"rows": [say("Maximum 1000 rows.", "الحد الأقصى 1000 صف.")]})
    if not rows:
        raise ValidationError({"rows": [say("Add at least one row.", "أضف صفًا واحدًا على الأقل.")]})

    errors = []
    prepared = []
    seen = set(Product.objects.values_list("code", flat=True))
    categories = set(Category.objects.values_list("id", flat=True))
    embedded = embedded or {}
    for index, raw in enumerate(rows):
        row, duplicates = _canonicalize_import_row(raw)
        prefix = say(f"Row {index + 2}", f"صف {index + 2}")
        if duplicates:
            errors.append(say(f"{prefix}: duplicate columns", f"{prefix}: أعمدة مكررة"))
            continue
        row = _apply_category_map(row, categories, category_map)
        problems = _import_problems(row, seen, categories, english)
        image_problem, image = _import_image(row, embedded.get(index), say, fetch=not problems)
        if image_problem:
            problems.append(image_problem)
        if problems:
            errors.append(f"{prefix}: " + " · ".join(problems))
            continue
        code = str(_import_cell(row, "Code", "code")).strip()
        seen.add(code)
        prepared.append((_normalized_import_row(row, code), image))
    if errors:
        raise ValidationError({"rows": errors})
    created = []
    stored_names = []
    from django.core.files.base import ContentFile
    from django.core.files.storage import default_storage
    from shop.fx import ensure_store_currencies

    ensure_store_currencies()
    try:
        with transaction.atomic():
            for row, image in prepared:
                product = Product.objects.create(
                    category_id=row["category_id"],
                    name_ar=row["name_ar"],
                    name_en=row["name_en"],
                    code=row["code"],
                    base_price_ils=row["base_price_ils"],
                    original_price=row["original_price"],
                    original_currency_id=row["original_currency_code"],
                    unit_ar=row["unit_ar"],
                    unit_en=row["unit_en"],
                    min_qty=row["min_qty"],
                    available=row["available"],
                    description_ar=row["description_ar"],
                    description_en=row["description_en"],
                )
                if image:
                    picture = ProductImage(product=product, is_primary=True, sort_order=0)
                    filename = _import_image_name(product.code, image[1])
                    picture.image.save(filename, ContentFile(image[0]), save=True)
                    stored_names.append(picture.image.name)
                else:
                    ProductImage.objects.create(product=product, image_key="men-shirt", is_primary=True, sort_order=0)
                ProductOption.objects.create(product=product, label="افتراضي / Default", is_available=True, sort_order=0)
                created.append(product.pk)
    except Exception:
        for name in stored_names:
            default_storage.delete(name)
        raise
    return list(_product_queryset().filter(pk__in=created))


_IMPORT_LABELS = {
    "code": "Code",
    "كود المنتج": "Code",
    "name_ar": "Name_AR",
    "اسم المنتج (عربي)": "Name_AR",
    "name_en": "Name_EN",
    "اسم المنتج (إنجليزي)": "Name_EN",
    "category_id": "Category_ID",
    "معرّف التصنيف": "Category_ID",
    "unit_ar": "Unit_AR",
    "وحدة البيع (عربي)": "Unit_AR",
    "unit_en": "Unit_EN",
    "وحدة البيع (إنجليزي)": "Unit_EN",
    "min_qty": "Min_Qty",
    "الحد الأدنى للكمية": "Min_Qty",
    "base_price_ils": "Base_Price_ILS",
    "price_ils": "Base_Price_ILS",
    "السعر الأساسي (ils)": "Base_Price_ILS",
    "original_currency": "Original_Currency",
    "العملة الأصلية": "Original_Currency",
    "original_price": "Original_Price",
    "السعر الأصلي": "Original_Price",
    "available": "Available",
    "متاح": "Available",
    "description_ar": "Description_AR",
    "الوصف (عربي)": "Description_AR",
    "description_en": "Description_EN",
    "الوصف (إنجليزي)": "Description_EN",
    "product_image": "Product_Image",
    "صورة المنتج": "Product_Image",
}


def _import_field(label):
    text = " ".join(str(label).strip().split())
    if not text:
        return None
    if text in _IMPORT_LABELS:
        return _IMPORT_LABELS[text]
    return _IMPORT_LABELS.get(text.lower())


def _canonicalize_import_row(row):
    if not isinstance(row, dict):
        return {}, ["invalid row"]
    normalized = {}
    duplicates = []
    for raw_key, value in row.items():
        field = _import_field(raw_key)
        if field is None:
            continue
        if field in normalized:
            duplicates.append(field)
            continue
        normalized[field] = value
    return normalized, duplicates


def _import_cell(row, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _import_problems(row, seen, categories, english=True):
    from decimal import InvalidOperation

    def say(en, ar):
        return en if english else ar

    problems = []
    code = _import_cell(row, "Code", "code")
    name_ar = _import_cell(row, "Name_AR", "name_ar")
    name_en = _import_cell(row, "Name_EN", "name_en")
    unit_ar = _import_cell(row, "Unit_AR", "unit_ar")
    unit_en = _import_cell(row, "Unit_EN", "unit_en")
    if not all(value is not None and str(value).strip() for value in (code, name_ar, name_en, unit_ar, unit_en)):
        problems.append(say("required fields", "حقول مطلوبة"))
    code_text = "" if code is None else str(code).strip()
    if code_text and code_text in seen:
        problems.append(say("duplicate code", "كود مكرر"))
    category_raw = _import_cell(row, "Category_ID", "category_id")
    category_id = _import_int(category_raw)
    if category_id is None or category_id not in categories:
        shown = "" if category_raw is None else str(category_raw).strip()
        problems.append(say(f"invalid category: {shown or '—'}", f"معرّف التصنيف غير موجود: {shown or '—'}"))
    if _import_int(_import_cell(row, "Min_Qty", "min_qty")) is None:
        problems.append(say("invalid minimum", "الحد الأدنى غير صالح"))
    else:
        minimum = _import_int(_import_cell(row, "Min_Qty", "min_qty"))
        if minimum < 1:
            problems.append(say("invalid minimum", "الحد الأدنى غير صالح"))
    price_problems = _import_price_problems(row, say)
    problems.extend(price_problems)
    available = _import_cell(row, "Available", "available")
    if str(available) not in {"0", "1"}:
        problems.append(say("Available must be 0 or 1", "متاح يجب أن يكون 0 أو 1"))
    return problems


def _import_price_problems(row, say):
    from decimal import InvalidOperation

    original_currency = _import_cell(row, "Original_Currency")
    original_price = _import_cell(row, "Original_Price")
    legacy = _import_cell(row, "Base_Price_ILS", "Price_ILS", "base_price_ils")
    has_original = original_currency not in (None, "") or original_price not in (None, "")
    has_legacy = legacy not in (None, "")
    if not has_original and not has_legacy:
        return [say("invalid price", "سعر غير صالح")]
    problems = []
    legacy_amount = None
    if has_legacy:
        try:
            legacy_amount = Decimal(str(legacy))
            if legacy_amount < 0:
                problems.append(say("invalid price", "سعر غير صالح"))
        except (InvalidOperation, TypeError):
            problems.append(say("invalid price", "سعر غير صالح"))
    if has_original:
        code = str(original_currency or "").strip().upper()
        if code not in {"CNY", "USD", "ILS"} or original_price in (None, ""):
            problems.append(say("invalid original price", "السعر الأصلي أو عملته غير صالحة"))
        else:
            try:
                amount = Decimal(str(original_price))
                if amount < 0:
                    problems.append(say("invalid original price", "السعر الأصلي أو عملته غير صالحة"))
            except (InvalidOperation, TypeError):
                problems.append(say("invalid original price", "السعر الأصلي أو عملته غير صالحة"))
                amount = None
            if amount is not None and has_legacy and legacy_amount is not None and code != "ILS":
                problems.append(say(
                    "ambiguous price columns",
                    "لا تجمع السعر الأصلي بعملة غير الشيكل مع السعر الأساسي بالشيكل",
                ))
            if amount is not None and has_legacy and legacy_amount is not None and code == "ILS" and amount != legacy_amount:
                problems.append(say(
                    "ambiguous price columns",
                    "السعر الأصلي لا يطابق السعر الأساسي بالشيكل",
                ))
    return problems


def _resolved_import_price(row):
    original_currency = _import_cell(row, "Original_Currency")
    original_price = _import_cell(row, "Original_Price")
    legacy = _import_cell(row, "Base_Price_ILS", "Price_ILS", "base_price_ils")
    if original_currency not in (None, "") and original_price not in (None, ""):
        code = str(original_currency).strip().upper()
        amount = Decimal(str(original_price))
        base = amount if code == "ILS" else (Decimal(str(legacy)) if legacy not in (None, "") else Decimal("0"))
        return code, amount, base
    amount = Decimal(str(legacy))
    return "ILS", amount, amount


def _apply_category_map(row, categories, category_map):
    if not category_map:
        return row
    cell = _import_cell(row, "Category_ID", "category_id")
    current = _import_int(cell)
    if current in categories:
        return row
    text = "" if cell is None else str(cell).strip()
    keys = []
    if current is not None:
        keys.append(str(current))
    if text not in keys:
        keys.append(text)
    raw = None
    for key in keys:
        if key in category_map:
            raw = category_map[key]
            break
    mapped = _import_int(raw)
    if mapped is None:
        return row
    updated = dict(row)
    updated["Category_ID"] = mapped
    return updated


def _import_image(row, embedded, say, fetch):
    from shop.remote_images import ImageFetchError, assert_public_http_url, download_product_image, sniff_image

    url = str(_import_cell(row, "Product_Image") or "").strip()
    pictures = list(embedded or [])
    if url and pictures:
        return say("row has both an image URL and an embedded image", "الصف يحتوي على رابط صورة وصورة مدمجة معًا"), None
    if len(pictures) > 1:
        return say("multiple images are anchored to this row", "أكثر من صورة مرتبطة بهذا الصف"), None
    if pictures:
        kind = sniff_image(pictures[0])
        if not kind:
            return say("unsupported or corrupted image", "صورة غير مدعومة أو تالفة"), None
        return None, (pictures[0], kind)
    if not url:
        return None, None
    try:
        assert_public_http_url(url)
    except ImageFetchError as exc:
        return say(exc.english, exc.arabic), None
    if not fetch:
        return None, None
    try:
        data, kind = download_product_image(url)
    except ImageFetchError as exc:
        return say(exc.english, exc.arabic), None
    return None, (data, kind)


def _import_image_name(code, kind):
    import re
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", str(code)).strip("-.")[:40] or "product"
    return f"{stem}.{kind}"


def _import_int(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value) if value.is_integer() else None
    text = str(value).strip()
    if text.isdigit() or (text.startswith("-") and text[1:].isdigit()):
        return int(text)
    return None


def _normalized_import_row(row, code):
    return {
        "code": code,
        "name_ar": str(_import_cell(row, "Name_AR", "name_ar")).strip(),
        "name_en": str(_import_cell(row, "Name_EN", "name_en")).strip(),
        "category_id": _import_int(_import_cell(row, "Category_ID", "category_id")),
        "unit_ar": str(_import_cell(row, "Unit_AR", "unit_ar")).strip(),
        "unit_en": str(_import_cell(row, "Unit_EN", "unit_en")).strip(),
        "min_qty": _import_int(_import_cell(row, "Min_Qty", "min_qty")),
        "original_currency_code": _resolved_import_price(row)[0],
        "original_price": _resolved_import_price(row)[1],
        "base_price_ils": _resolved_import_price(row)[2],
        "available": str(_import_cell(row, "Available", "available")) == "1",
        "description_ar": str(row.get("Description_AR") or row.get("description_ar") or "").strip(),
        "description_en": str(row.get("Description_EN") or row.get("description_en") or "").strip(),
    }
