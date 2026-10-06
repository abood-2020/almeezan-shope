from datetime import date
from decimal import Decimal

from django.contrib.auth import login
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from shop.models import (
    Category,
    Currency,
    Invoice,
    Order,
    OrderLine,
    PriceList,
    PriceListItem,
    Product,
    ProductColor,
    ProductImage,
    ProductOption,
    ProductSize,
    SiteSetting,
    Trader,
)


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
    queryset = Product.objects.select_related("category").prefetch_related(
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


def prepare_order_lines(trader, items):
    if not items:
        raise ValidationError({"items": ["Add at least one product."]})
    prepared = []
    for index, item in enumerate(items):
        try:
            product = Product.objects.get(pk=item["product_id"])
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
        unit_price = trader.price_list.price_for(product)
        if unit_price is None:
            _line_error(index, "No price is set for this product on your price list.")
        prepared.append((product, option.label, quantity, unit_price))
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


def create_order(trader, note, items):
    prepared = prepare_order_lines(trader, items)
    total = sum((unit_price * quantity for _, _, quantity, unit_price in prepared), Decimal("0"))
    today = timezone.localdate()
    currency = trader.price_list.currency
    for _ in range(3):
        try:
            with transaction.atomic():
                order = Order.objects.create(
                    number=allocate_order_number(today),
                    trader=trader,
                    trader_name_ar=trader.name_ar,
                    ordered_on=today,
                    status=Order.Status.REVIEW,
                    currency=currency,
                    currency_symbol=currency.symbol,
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
                        quantity=quantity,
                        unit_price=unit_price,
                    )
                    for product, label, quantity, unit_price in prepared
                ])
            return Order.objects.prefetch_related("lines").select_related("currency", "trader").get(pk=order.pk)
        except IntegrityError:
            continue
    raise ValidationError("Could not allocate an order number.")


def get_site_settings():
    setting = SiteSetting.objects.filter(pk=1).first()
    if setting is None:
        setting = SiteSetting(company_whatsapp_number="")
        setting.save()
    return setting


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
        if "image_key" in data:
            _reject_blob(category.image_key, "image_key")
        duplicate = Category.objects.filter(name_ar=category.name_ar)
        if category.pk:
            duplicate = duplicate.exclude(pk=category.pk)
        if category.name_ar and duplicate.exists():
            raise ValidationError({"name_ar": ["A category with this Arabic name already exists."]})
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
        for field in ("name_ar", "name_en", "price_list"):
            if field in data:
                setattr(trader, field, data[field])
        if "active" in data:
            trader.is_active = data["active"]
        trader.full_clean()
        trader.save()
        return Trader.objects.select_related("user", "price_list__currency").get(pk=trader.pk)


def set_trader_password(trader, password):
    trader.user.set_password(password)
    trader.user.save(update_fields=["password"])


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
        for field in ("name_ar", "name_en", "currency", "is_active"):
            if field in data:
                setattr(price_list, field, data[field])
        if not creating and "currency" in data and data["currency"].code != "ILS":
            _require_complete_prices(price_list, set(price_list.items.values_list("product_id", flat=True)))
        price_list.full_clean()
        price_list.save()
        return PriceList.objects.select_related("currency").get(pk=price_list.pk)


def _require_complete_prices(price_list, product_ids):
    if price_list.currency_id == "ILS" or (getattr(price_list, "currency", None) and price_list.currency.code == "ILS"):
        return
    required = set(Product.objects.values_list("id", flat=True))
    if set(product_ids) != required:
        raise ValidationError({"prices": ["Enter a price for every product before saving a non-ILS list."]})


def replace_price_list_prices(price_list, rows):
    product_ids = [row["product_id"] for row in rows]
    if len(product_ids) != len(set(product_ids)):
        raise ValidationError({"prices": ["Each product can appear only once."]})
    known = set(Product.objects.filter(id__in=product_ids).values_list("id", flat=True))
    unknown = [product_id for product_id in product_ids if product_id not in known]
    if unknown:
        raise ValidationError({"prices": ["Unknown product."]})
    currency_code = price_list.currency_id
    if currency_code != "ILS":
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
    return PriceList.objects.select_related("currency").prefetch_related("items").get(pk=price_list.pk)


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


def update_site_settings(number):
    setting = get_site_settings()
    setting.company_whatsapp_number = number
    setting.save()
    return setting


def import_products(rows):
    if len(rows) > 1000:
        raise ValidationError({"rows": ["Maximum 1000 rows."]})
    if not rows:
        raise ValidationError({"rows": ["Add at least one row."]})

    errors = []
    prepared = []
    seen = set(Product.objects.values_list("code", flat=True))
    categories = set(Category.objects.values_list("id", flat=True))
    for index, row in enumerate(rows):
        problems = _import_problems(row, seen, categories)
        if problems:
            errors.append(f"Row {index + 2}: " + " · ".join(problems))
            continue
        code = str(_import_cell(row, "Code", "code")).strip()
        seen.add(code)
        prepared.append(_normalized_import_row(row, code))
    if errors:
        raise ValidationError({"rows": errors})
    created = []
    with transaction.atomic():
        for row in prepared:
            product = Product.objects.create(
                category_id=row["category_id"],
                name_ar=row["name_ar"],
                name_en=row["name_en"],
                code=row["code"],
                base_price_ils=row["base_price_ils"],
                unit_ar=row["unit_ar"],
                unit_en=row["unit_en"],
                min_qty=row["min_qty"],
                available=row["available"],
                description_ar=row["description_ar"],
                description_en=row["description_en"],
            )
            ProductImage.objects.create(product=product, image_key="men-shirt", is_primary=True, sort_order=0)
            ProductOption.objects.create(product=product, label="افتراضي / Default", is_available=True, sort_order=0)
            created.append(product.pk)
    return list(_product_queryset().filter(pk__in=created))


def _import_cell(row, *names):
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return None


def _import_problems(row, seen, categories):
    from decimal import InvalidOperation

    problems = []
    code = _import_cell(row, "Code", "code")
    name_ar = _import_cell(row, "Name_AR", "name_ar")
    name_en = _import_cell(row, "Name_EN", "name_en")
    unit_ar = _import_cell(row, "Unit_AR", "unit_ar")
    unit_en = _import_cell(row, "Unit_EN", "unit_en")
    if not all(str(value).strip() for value in (code, name_ar, name_en, unit_ar, unit_en)):
        problems.append("required fields")
    code_text = "" if code is None else str(code).strip()
    if code_text and code_text in seen:
        problems.append("duplicate code")
    category_raw = _import_cell(row, "Category_ID", "category_id")
    category_id = _import_int(category_raw)
    if category_id is None or category_id not in categories:
        problems.append("invalid category")
    if _import_int(_import_cell(row, "Min_Qty", "min_qty")) is None:
        problems.append("invalid minimum")
    else:
        minimum = _import_int(_import_cell(row, "Min_Qty", "min_qty"))
        if minimum < 1:
            problems.append("invalid minimum")
    price_raw = _import_cell(row, "Base_Price_ILS", "Price_ILS", "base_price_ils")
    try:
        price = Decimal(str(price_raw))
        if price < 0:
            problems.append("invalid price")
    except (InvalidOperation, TypeError):
        problems.append("invalid price")
    available = _import_cell(row, "Available", "available")
    if str(available) not in {"0", "1"}:
        problems.append("Available must be 0 or 1")
    return problems


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
        "base_price_ils": Decimal(str(_import_cell(row, "Base_Price_ILS", "Price_ILS", "base_price_ils"))),
        "available": str(_import_cell(row, "Available", "available")) == "1",
        "description_ar": str(row.get("Description_AR") or row.get("description_ar") or "").strip(),
        "description_en": str(row.get("Description_EN") or row.get("description_en") or "").strip(),
    }
