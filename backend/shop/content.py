"""Store content defaults, validation, and public payloads.

The storefront keeps working from these defaults until an administrator edits them.
ensure_store_content() creates missing rows once and does not overwrite later edits.
"""

import re
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction

MARKUP = re.compile(r"<\s*/?\s*[a-zA-Z!]|javascript\s*:", re.IGNORECASE)
CTA_TARGETS = {"", "catalog", "portal", "whatsapp", "products", "contact", "traders", "export", "info"}
NAV_LABELS = {
    "home_ar": "الرئيسية",
    "home_en": "Home",
    "catalog_ar": "الكتالوج",
    "catalog_en": "Catalog",
    "traders_ar": "التجار",
    "traders_en": "Traders",
    "export_ar": "التصدير",
    "export_en": "Export",
    "about_ar": "من نحن",
    "about_en": "About us",
    "contact_ar": "تواصل معنا",
    "contact_en": "Contact us",
    "products_ar": "المنتجات والفئات",
    "products_en": "Products & categories",
    "portal_ar": "بوابة التاجر",
    "portal_en": "Trader portal",
    "traders_link_ar": "الغرابلي جلوبال للتجّار",
    "traders_link_en": "Algharabli Global for Traders",
    "export_link_ar": "الغرابلي جلوبال بلا حدود",
    "export_link_en": "Algharabli Global Beyond Borders",
    "cart_ar": "سلة الطلب",
    "cart_en": "Order cart",
    "about_link_ar": "من نحن ومعلومات الطلب",
    "about_link_en": "About us & ordering information",
    "orders_ar": "سجل الطلبات",
    "orders_en": "Order history",
}
TEXT_FIELDS = (
    "name_ar", "name_en", "tagline_ar", "tagline_en", "header_caption_ar", "header_caption_en",
    "logo_alt_ar", "logo_alt_en", "address_ar", "address_en",
    "seo_title_ar", "seo_title_en", "seo_description_ar", "seo_description_en",
    "footer_explore_ar", "footer_explore_en", "footer_account_ar", "footer_account_en",
    "copyright_ar", "copyright_en", "footer_note_ar", "footer_note_en", "footer_place_ar", "footer_place_en",
)
URL_FIELDS = ("instagram_url", "facebook_url")
COPY_FIELDS = (
    "eyebrow_ar", "eyebrow_en", "title_ar", "title_en", "body_ar", "body_en",
    "cta_ar", "cta_en", "cta_target", "secondary_cta_ar", "secondary_cta_en", "secondary_cta_target",
    "aside_title_ar", "aside_title_en", "aside_body_ar", "aside_body_en",
)
PAGE_FIELDS = (
    "eyebrow_ar", "eyebrow_en", "title_ar", "title_en", "body_ar", "body_en",
    "intro_title_ar", "intro_title_en", "intro_body_ar", "intro_body_en",
    "cta_ar", "cta_en", "faq_eyebrow_ar", "faq_eyebrow_en", "faq_title_ar", "faq_title_en",
    "faq_intro_ar", "faq_intro_en",
)

SECTIONS = [
    {
        "key": "hero", "sort_order": 10,
        "eyebrow_ar": "الغرابلي جلوبال · تجارة الملابس بالجملة", "eyebrow_en": "ALGHARABLI GLOBAL · WHOLESALE FASHION",
        "title_ar": "تشكيلة تليق بمتجرك", "title_en": "A collection for your store",
        "body_ar": "أزياء رجالية ونسائية وأطفال في كتالوج واحد. اختر القطع، الألوان والمقاسات، ثم أرسل طلبك التجاري.",
        "body_en": "Explore men’s, women’s and children’s styles in one catalog. Choose your pieces, colors and sizes, then send your trade request.",
        "cta_ar": "استعرض الكتالوج", "cta_en": "Browse the catalog", "cta_target": "catalog",
        "secondary_cta_ar": "دخول التاجر", "secondary_cta_en": "Trader sign in", "secondary_cta_target": "portal",
        "blocks": [
            {"key": "trust-1", "title_ar": "سعرك مرتبط بحسابك", "title_en": "Your assigned pricing", "body_ar": "قائمة أسعار بعملة واضحة", "body_en": "A clear price list and currency"},
            {"key": "trust-2", "title_ar": "خيارات القطع أمامك", "title_en": "Product options at a glance", "body_ar": "ألوان ومقاسات وحد أدنى للطلب", "body_en": "Colors, sizes and minimums"},
            {"key": "trust-3", "title_ar": "متابعة من الشركة", "title_en": "Company follow-up", "body_ar": "بعد إرسال الطلب برقم مرجعي", "body_en": "After a numbered request is sent"},
        ],
    },
    {
        "key": "categories", "sort_order": 20,
        "eyebrow_ar": "الأقسام", "eyebrow_en": "COLLECTIONS",
        "title_ar": "تسوّق حسب القسم", "title_en": "Shop by category",
        "cta_ar": "جميع المنتجات", "cta_en": "All products", "cta_target": "catalog",
        "blocks": [],
    },
    {
        "key": "benefits", "sort_order": 30,
        "eyebrow_ar": "لتجارتك", "eyebrow_en": "FOR YOUR TRADE",
        "title_ar": "تفاصيل تسهّل طلب الجملة", "title_en": "Wholesale details made clearer",
        "blocks": [
            {"key": "benefit-1", "title_ar": "سعرك مرتبط بحسابك", "title_en": "Your assigned pricing", "body_ar": "قائمة أسعار بعملة واضحة", "body_en": "A clear price list and currency"},
            {"key": "benefit-2", "title_ar": "خيارات القطع أمامك", "title_en": "Product options at a glance", "body_ar": "ألوان ومقاسات وحد أدنى للطلب", "body_en": "Colors, sizes and minimums"},
            {"key": "benefit-3", "title_ar": "سلة لطلب الجملة", "title_en": "Wholesale request cart", "body_ar": "راجع الأصناف والكميات قبل الإرسال", "body_en": "Review items and quantities"},
        ],
    },
    {
        "key": "steps", "sort_order": 40,
        "eyebrow_ar": "طريقة الطلب", "eyebrow_en": "HOW IT WORKS",
        "title_ar": "من التصفح إلى المتابعة", "title_en": "From browsing to follow-up",
        "body_ar": "الطلب يذهب للشركة لمتابعته معك، دون دفع إلكتروني.",
        "body_en": "Your request goes to the company for follow-up, without online payment.",
        "cta_ar": "معلومات وأسئلة شائعة", "cta_en": "Information & FAQ", "cta_target": "info",
        "blocks": [
            {"key": "step-1", "title_ar": "استعرض المنتجات", "title_en": "Explore styles", "body_ar": "ابحث في الأقسام عن القطع المناسبة", "body_en": "Find styles in the catalog"},
            {"key": "step-2", "title_ar": "اختر الخيارات", "title_en": "Select options", "body_ar": "حدد اللون والمقاس والكمية", "body_en": "Choose color, size and quantity"},
            {"key": "step-3", "title_ar": "راجع السلة", "title_en": "Review your cart", "body_ar": "راجع الأصناف والكميات قبل الإرسال", "body_en": "Review items and quantities before submitting"},
            {"key": "step-4", "title_ar": "أرسل طلبك", "title_en": "Send request", "body_ar": "أرسلها للمتابعة واحتفظ برقمك المرجعي", "body_en": "Submit for follow-up and keep your reference"},
        ],
    },
    {
        "key": "trade", "sort_order": 50,
        "eyebrow_ar": "الغرابلي جلوبال للتجارة", "eyebrow_en": "ALGHARABLI GLOBAL TRADE",
        "title_ar": "تشكيلة واحدة لفرص تجارية أوسع", "title_en": "One collection, wider trade possibilities",
        "body_ar": "من فلسطين إلى أسواق أوسع، تصفح تشكيلات الرجال والنساء والأطفال واختر ما يناسب متجرك.",
        "body_en": "From Palestine to wider markets, explore men’s, women’s and children’s collections for your store.",
        "cta_ar": "استعرض الكتالوج", "cta_en": "Browse catalog", "cta_target": "catalog",
        "secondary_cta_ar": "دخول التاجر", "secondary_cta_en": "Trader sign in", "secondary_cta_target": "portal",
        "aside_title_ar": "جهّز طلب متجرك", "aside_title_en": "Prepare your store’s request",
        "aside_body_ar": "استعرض المنتجات، اختر الكميات، ثم راجع السلة قبل إرسال الطلب التجاري.",
        "aside_body_en": "Explore products, choose quantities and review the cart before sending your trade request.",
        "blocks": [
            {"key": "point-1", "title_ar": "الأسعار حسب قائمة حساب التاجر وعملتها", "title_en": "Prices follow each trader’s assigned list and currency", "body_ar": "", "body_en": ""},
            {"key": "point-2", "title_ar": "ألوان ومقاسات وحد أدنى ظاهر لكل منتج", "title_en": "Visible colors, sizes and minimums", "body_ar": "", "body_en": ""},
            {"key": "point-3", "title_ar": "طلب برقم مرجعي للمتابعة مع الشركة", "title_en": "A reference number for company follow-up", "body_ar": "", "body_en": ""},
        ],
    },
    {
        "key": "featured", "sort_order": 60,
        "eyebrow_ar": "كتالوج الغرابلي جلوبال", "eyebrow_en": "THE ALGHARABLI GLOBAL EDIT",
        "title_ar": "منتجات تستحق الاكتشاف", "title_en": "Styles worth discovering",
        "body_ar": "اختر من تشكيلة الرجال والنساء والأطفال.",
        "body_en": "Explore men’s, women’s and children’s styles.",
        "cta_ar": "عرض الكتالوج", "cta_en": "Browse catalog", "cta_target": "catalog",
        "blocks": [],
    },
    {
        "key": "closing", "sort_order": 70,
        "eyebrow_ar": "الغرابلي جلوبال للتجارة", "eyebrow_en": "ALGHARABLI GLOBAL TRADE",
        "title_ar": "جاهز لتجهيز طلب متجرك؟", "title_en": "Ready to prepare your request?",
        "body_ar": "اختر القطع المناسبة، ثم أرسل طلب الجملة للشركة للمتابعة.",
        "body_en": "Choose your pieces and send a wholesale request for company follow-up.",
        "cta_ar": "استعرض المنتجات", "cta_en": "Explore products", "cta_target": "products",
        "secondary_cta_ar": "تواصل عبر واتساب", "secondary_cta_en": "Chat on WhatsApp", "secondary_cta_target": "whatsapp",
        "blocks": [],
    },
]

PAGES = [
    {
        "key": "about",
        "eyebrow_ar": "عن الغرابلي جلوبال", "eyebrow_en": "ABOUT ALGHARABLI GLOBAL",
        "title_ar": "تجربة جملة واضحة، من التصفح إلى إرسال الطلب.",
        "title_en": "A clear wholesale journey, from browsing to request.",
        "body_ar": "الغرابلي جلوبال واجهة للتجار لاستعراض المنتجات والخيارات والأسعار المرتبطة بحساباتهم، ثم إرسال طلب للشركة لمتابعته تجاريًا.",
        "body_en": "Algharabli Global lets traders explore products, options and account-specific prices, then send a request for the company to follow up.",
        "intro_title_ar": "كيف ترسل طلبك؟", "intro_title_en": "How to send a request",
        "cta_ar": "استعرض المنتجات", "cta_en": "Explore products",
        "faq_eyebrow_ar": "إجابات سريعة", "faq_eyebrow_en": "QUICK ANSWERS",
        "faq_title_ar": "الأسئلة الشائعة", "faq_title_en": "Frequently asked questions",
        "faq_intro_ar": "هذه المعلومات تشرح طريقة عمل واجهة الغرابلي جلوبال الحالية.",
        "faq_intro_en": "How the current Algharabli Global experience works.",
        "blocks": [
            {"key": "step-1", "title_ar": "تصفح التشكيلة", "title_en": "Browse the collection", "body_ar": "اختر القسم أو ابحث بالكود أو اسم المنتج.", "body_en": "Choose a category or search by product name or code."},
            {"key": "step-2", "title_ar": "حدد الخيارات والكميات", "title_en": "Choose options and quantities", "body_ar": "راجع اللون والمقاس والحد الأدنى قبل الإضافة للسلة.", "body_en": "Check color, size and minimum quantity before adding to cart."},
            {"key": "step-3", "title_ar": "راجع وأرسل", "title_en": "Review and submit", "body_ar": "أرسل الطلب واحفظ رقمه المرجعي وملف PDF.", "body_en": "Submit your request and keep its reference and PDF."},
        ],
    },
    {
        "key": "traders",
        "eyebrow_ar": "شراكة تبدأ من متجرك", "eyebrow_en": "A PARTNERSHIP FOR YOUR STORE",
        "title_ar": "الغرابلي جلوبال للتجّار", "title_en": "Algharabli Global for Traders",
        "body_ar": "مساحة مصممة لتاجر الملابس الذي يبحث عن خيارات واضحة وخطوات طلب سهلة. من اختيار القطع إلى متابعة طلب الجملة، كل التفاصيل في مكان واحد.",
        "body_en": "A space for fashion traders who value clear choices and a simple request journey. From selecting pieces to following up on your wholesale request, everything is in one place.",
        "intro_title_ar": "كل خطوة محسوبة لمتجرك", "intro_title_en": "Every step shaped for your store",
        "intro_body_ar": "اعرف تفاصيل المنتج قبل إضافته، وابنِ سلتك بالكميات المناسبة، ثم احتفظ برقم الطلب لتسهيل متابعته.",
        "intro_body_en": "See product details before adding them, build your cart with suitable quantities and keep the reference number for follow-up.",
        "cta_ar": "استكشف الكتالوج", "cta_en": "Explore the catalog",
        "blocks": [],
    },
    {
        "key": "export",
        "eyebrow_ar": "من الغرابلي جلوبال إلى آفاق أوسع", "eyebrow_en": "FROM ALGHARABLI GLOBAL TO WIDER MARKETS",
        "title_ar": "الغرابلي جلوبال بلا حدود", "title_en": "Algharabli Global Beyond Borders",
        "body_ar": "تشكيلة أزياء جملة لعلاقات تجارية تتجاوز الحدود. استكشف الكتالوج، واطّلع على سعرك بعملة حسابك، وجهّز طلبًا واضحًا تتابعه الشركة معك.",
        "body_en": "Wholesale fashion for trade beyond borders. Explore the catalog, view pricing in your account currency and prepare a clear request for company follow-up.",
        "intro_title_ar": "من أول قطعة إلى فرصة جديدة", "intro_title_en": "From the first piece to a new opportunity",
        "intro_body_ar": "الغرابلي جلوبال يجمع عرض المنتجات وخياراتها وطلبات الجملة في تجربة واحدة. يحدد حسابك قائمة الأسعار وعملتها، وتتم متابعة التفاصيل التجارية بعد إرسال الطلب.",
        "intro_body_en": "Algharabli Global brings products, options and wholesale requests into one experience. Your account sets the price list and currency, while commercial details are followed up after submission.",
        "cta_ar": "استكشف الكتالوج", "cta_en": "Explore the catalog",
        "blocks": [],
    },
]

FAQS = [
    ("كيف أرى أسعار الجملة؟", "How do I see wholesale prices?", "أنشئ الإدارة حساب التاجر وتربطه بقائمة أسعار وعملة محددتين. تظهر الأسعار بعد تسجيل الدخول.", "The administrator creates a trader account and assigns a price list and currency. Prices appear after sign-in."),
    ("هل إرسال الطلب يعني الدفع؟", "Does submitting a request mean paying?", "لا. ترسل السلة إلى الشركة لمراجعتها ومتابعتها معك، ولا يوجد دفع إلكتروني في الواجهة.", "No. Your cart is sent to the company for review and follow-up. There is no online payment in this interface."),
    ("أين أجد طلباتي وفواتيري؟", "Where are my requests and invoices?", "بعد الدخول، تعرض بوابة التاجر سجل الطلبات وحالاتها وملفات الفواتير التي أتاحتها الإدارة.", "After sign-in, the trader portal shows request history and status, plus invoice files made available by the administrator."),
    ("هل يصل الطلب تلقائيًا عبر واتساب؟", "Is my request sent automatically on WhatsApp?", "لا. زر واتساب يفتح محادثة مباشرة فقط، ولا يرسل الطلب أو ملفه تلقائيًا.", "No. The WhatsApp button only opens a direct chat. It does not send the request or its PDF automatically."),
]


def has_markup(value):
    return bool(MARKUP.search(value or ""))


def plain(value, field, max_length=None):
    text = "" if value is None else str(value)
    if has_markup(text):
        raise ValidationError({field: "HTML is not allowed."})
    if max_length and len(text) > max_length:
        raise ValidationError({field: f"Use at most {max_length} characters."})
    return text


def normalize_phone(value, field):
    digits = re.sub(r"\D", "", value or "")
    if digits and not 8 <= len(digits) <= 15:
        raise ValidationError({field: "Use 8 to 15 digits, or leave the number empty."})
    return digits


def https_url(value, field, video=False):
    text = (value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme != "https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValidationError({field: "Enter an https URL, or leave it empty."})
    if video and not parsed.path.lower().endswith((".mp4", ".webm")):
        raise ValidationError({field: "Use a direct https link to an mp4 or webm file."})
    return text


def clean_site_setting(setting):
    setting.company_whatsapp_number = normalize_phone(setting.company_whatsapp_number, "company_whatsapp_number")
    setting.phone = normalize_phone(setting.phone, "phone")
    if setting.email:
        try:
            validate_email(setting.email)
        except ValidationError:
            raise ValidationError({"email": "Enter a valid email address, or leave it empty."})
    for field in URL_FIELDS:
        setattr(setting, field, https_url(getattr(setting, field), field))
    setting.hero_video_url = https_url(setting.hero_video_url, "hero_video_url", video=True)
    for field in TEXT_FIELDS:
        setattr(setting, field, plain(getattr(setting, field) or "", field))
    if not setting.name_ar.strip() or not setting.name_en.strip():
        raise ValidationError({"name_ar": "Arabic and English store names are required."})
    labels = setting.nav_labels or {}
    if not isinstance(labels, dict):
        raise ValidationError({"nav_labels": "Labels must be a map of known keys."})
    cleaned = {}
    for key, value in labels.items():
        if key not in NAV_LABELS:
            raise ValidationError({"nav_labels": "Unknown navigation label."})
        cleaned[key] = plain(value, "nav_labels", 80).strip()
    setting.nav_labels = cleaned


def _block_defaults(spec):
    return {
        "sort_order": spec.get("sort_order", 0),
        "title_ar": spec.get("title_ar", ""),
        "title_en": spec.get("title_en", ""),
        "body_ar": spec.get("body_ar", ""),
        "body_en": spec.get("body_en", ""),
    }


def ensure_store_content():
    from shop.models import ContentBlock, ContentPage, FaqItem, HomepageBlock, HomepageSection
    from shop.services import get_site_settings

    setting = get_site_settings()
    if setting.content_initialized:
        return setting
    with transaction.atomic():
        setting = get_site_settings()
        if setting.content_initialized:
            return setting
        for spec in SECTIONS:
            fields = {name: spec.get(name, "") for name in COPY_FIELDS}
            fields["sort_order"] = spec["sort_order"]
            section, _created = HomepageSection.objects.get_or_create(key=spec["key"], defaults=fields)
            for index, block in enumerate(spec["blocks"], start=1):
                HomepageBlock.objects.get_or_create(
                    section=section,
                    key=block["key"],
                    defaults={**_block_defaults(block), "sort_order": index},
                )
        for spec in PAGES:
            fields = {name: spec.get(name, "") for name in PAGE_FIELDS}
            page, _created = ContentPage.objects.get_or_create(key=spec["key"], defaults=fields)
            for index, block in enumerate(spec["blocks"], start=1):
                ContentBlock.objects.get_or_create(
                    page=page,
                    key=block["key"],
                    defaults={**_block_defaults(block), "sort_order": index},
                )
        if not FaqItem.objects.exists():
            FaqItem.objects.bulk_create([
                FaqItem(question_ar=ar_q, question_en=en_q, answer_ar=ar_a, answer_en=en_a, sort_order=index, is_active=True)
                for index, (ar_q, en_q, ar_a, en_a) in enumerate(FAQS, start=1)
            ])
        setting.content_initialized = True
        setting.save(update_fields=["content_initialized"])
    return setting


def _file_url(field):
    if not field:
        return ""
    return field.url


def _block_payload(block):
    return {
        "key": block.key,
        "sort_order": block.sort_order,
        "title_ar": block.title_ar,
        "title_en": block.title_en,
        "body_ar": block.body_ar,
        "body_en": block.body_en,
    }


def link_url(value, field="url"):
    text = plain(value, field, 500).strip()
    if not text:
        raise ValidationError({field: "Enter a link URL."})
    parsed = urlparse(text)
    host = (parsed.hostname or "").strip().lower()
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ValidationError({field: "Enter an http or https URL."})
    if parsed.scheme == "javascript" or text.lower().startswith(("javascript:", "data:")):
        raise ValidationError({field: "Enter an http or https URL."})
    return text


def ensure_social_links(setting):
    from shop.models import SiteSetting, StoreSocialLink

    if setting.social_links_migrated:
        return setting
    with transaction.atomic():
        locked = SiteSetting.objects.select_for_update().get(pk=setting.pk)
        if locked.social_links_migrated:
            return locked
        order = 0
        for name, url in (("Facebook", locked.facebook_url), ("Instagram", locked.instagram_url)):
            if not url:
                continue
            if not locked.social_links.filter(name=name, url=url).exists():
                StoreSocialLink.objects.create(site=locked, name=name, url=url, sort_order=order, is_active=True)
            order += 1
        SiteSetting.objects.filter(pk=locked.pk).update(social_links_migrated=True)
        locked.social_links_migrated = True
        return locked


def replace_social_links(setting, rows):
    from shop.models import SiteSetting, StoreSocialLink

    if not isinstance(rows, list):
        raise ValidationError({"social_links": "Expected a list of links."})
    if len(rows) > 100:
        raise ValidationError({"social_links": "Use at most 100 links."})
    cleaned = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValidationError({"social_links": "Each link needs a name and URL."})
        name = plain(row.get("name"), "name", 80).strip()
        url = link_url(row.get("url"), "url")
        if not name:
            raise ValidationError({"name": "Enter a display name."})
        active = row.get("is_active", True)
        if isinstance(active, str):
            active = active.lower() not in {"0", "false", "no", "off"}
        cleaned.append((name, url, index, bool(active)))
    with transaction.atomic():
        setting.social_links.all().delete()
        StoreSocialLink.objects.bulk_create([
            StoreSocialLink(site=setting, name=name, url=url, sort_order=order, is_active=active)
            for name, url, order, active in cleaned
        ])
        SiteSetting.objects.filter(pk=setting.pk).update(social_links_migrated=True)
    setting.social_links_migrated = True
    return setting


def _social_payload(setting, include_inactive):
    links = setting.social_links.all()
    if not include_inactive:
        links = links.filter(is_active=True)
    return [
        {"id": link.id, "name": link.name, "url": link.url, "sort_order": link.sort_order, "is_active": link.is_active}
        for link in links
    ]


def content_payload(include_inactive_faqs=False):
    from shop.models import ContentPage, FaqItem, HomepageSection

    setting = ensure_social_links(ensure_store_content())
    labels = {**NAV_LABELS, **(setting.nav_labels or {})}
    sections = []
    for section in HomepageSection.objects.prefetch_related("blocks").order_by("sort_order", "id"):
        sections.append({
            "key": section.key,
            "visible": section.is_visible,
            "sort_order": section.sort_order,
            **{name: getattr(section, name) for name in COPY_FIELDS},
            "blocks": [_block_payload(block) for block in section.blocks.all()],
        })
    pages = []
    for page in ContentPage.objects.prefetch_related("blocks"):
        pages.append({
            "key": page.key,
            **{name: getattr(page, name) for name in PAGE_FIELDS},
            "blocks": [_block_payload(block) for block in page.blocks.all()],
        })
    faqs = FaqItem.objects.all() if include_inactive_faqs else FaqItem.objects.filter(is_active=True)
    return {
        "company_whatsapp_number": setting.company_whatsapp_number,
        "brand": {
            "name_ar": setting.name_ar,
            "name_en": setting.name_en,
            "tagline_ar": setting.tagline_ar,
            "tagline_en": setting.tagline_en,
            "header_caption_ar": setting.header_caption_ar,
            "header_caption_en": setting.header_caption_en,
            "logo": _file_url(setting.logo),
            "logo_alt_ar": setting.logo_alt_ar,
            "logo_alt_en": setting.logo_alt_en,
            "favicon": _file_url(setting.favicon),
        },
        "contact": {
            "phone": setting.phone,
            "whatsapp": setting.company_whatsapp_number,
            "email": setting.email,
            "address_ar": setting.address_ar,
            "address_en": setting.address_en,
            "instagram_url": setting.instagram_url,
            "facebook_url": setting.facebook_url,
        },
        "social_links": _social_payload(setting, include_inactive_faqs),
        "seo": {
            "title_ar": setting.seo_title_ar,
            "title_en": setting.seo_title_en,
            "description_ar": setting.seo_description_ar,
            "description_en": setting.seo_description_en,
            "image": _file_url(setting.og_image),
        },
        "hero": {
            "video": _file_url(setting.hero_video),
            "video_url": setting.hero_video_url,
            "poster": _file_url(setting.hero_poster),
        },
        "footer": {
            "explore_ar": setting.footer_explore_ar,
            "explore_en": setting.footer_explore_en,
            "account_ar": setting.footer_account_ar,
            "account_en": setting.footer_account_en,
            "copyright_ar": setting.copyright_ar,
            "copyright_en": setting.copyright_en,
            "note_ar": setting.footer_note_ar,
            "note_en": setting.footer_note_en,
            "place_ar": setting.footer_place_ar,
            "place_en": setting.footer_place_en,
        },
        "nav": labels,
        "sections": sections,
        "pages": pages,
        "faqs": [
            {
                "id": item.id,
                "question_ar": item.question_ar,
                "question_en": item.question_en,
                "answer_ar": item.answer_ar,
                "answer_en": item.answer_en,
                "sort_order": item.sort_order,
                "is_active": item.is_active,
            }
            for item in faqs.order_by("sort_order", "id")
            if item.question_ar.strip() and item.question_en.strip() and item.answer_ar.strip() and item.answer_en.strip()
        ],
    }


def _apply_copy(instance, data, fields):
    for name in fields:
        if name in data:
            value = data[name]
            if name.endswith("_target"):
                if value not in CTA_TARGETS:
                    raise ValidationError({name: "Choose one of the existing destinations."})
            else:
                value = plain(value, name)
            setattr(instance, name, value)


def update_sections(rows):
    from shop.models import HomepageBlock, HomepageSection

    ensure_store_content()
    if not isinstance(rows, list):
        raise ValidationError({"sections": "Expected a list of sections."})
    with transaction.atomic():
        for row in rows:
            key = row.get("key")
            section = HomepageSection.objects.filter(key=key).first()
            if section is None:
                raise ValidationError({"key": "Unknown homepage section."})
            if "visible" in row:
                section.is_visible = bool(row["visible"])
            _apply_copy(section, row, COPY_FIELDS)
            section.save()
            for block_row in row.get("blocks") or []:
                block = HomepageBlock.objects.filter(section=section, key=block_row.get("key")).first()
                if block is None:
                    continue
                for name in ("title_ar", "title_en", "body_ar", "body_en"):
                    if name in block_row:
                        setattr(block, name, plain(block_row[name], name))
                block.save()
    return content_payload(include_inactive_faqs=True)


def update_pages(rows):
    from shop.models import ContentBlock, ContentPage

    ensure_store_content()
    if not isinstance(rows, list):
        raise ValidationError({"pages": "Expected a list of pages."})
    with transaction.atomic():
        for row in rows:
            page = ContentPage.objects.filter(key=row.get("key")).first()
            if page is None:
                raise ValidationError({"key": "Unknown page."})
            _apply_copy(page, row, PAGE_FIELDS)
            page.save()
            for block_row in row.get("blocks") or []:
                block = ContentBlock.objects.filter(page=page, key=block_row.get("key")).first()
                if block is None:
                    continue
                for name in ("title_ar", "title_en", "body_ar", "body_en"):
                    if name in block_row:
                        setattr(block, name, plain(block_row[name], name))
                block.save()
    return content_payload(include_inactive_faqs=True)


def save_faq(data, item=None):
    from shop.models import FaqItem

    for name in ("question_ar", "question_en", "answer_ar", "answer_en"):
        if name in data:
            data[name] = plain(data[name], name).strip()
            if not data[name]:
                raise ValidationError({name: "This field is required."})
    if item is None:
        missing = [name for name in ("question_ar", "question_en", "answer_ar", "answer_en") if not data.get(name)]
        if missing:
            raise ValidationError({missing[0]: "This field is required."})
        item = FaqItem(sort_order=FaqItem.objects.count() + 1, is_active=True)
    for name in ("question_ar", "question_en", "answer_ar", "answer_en", "is_active", "sort_order"):
        if name in data:
            setattr(item, name, data[name])
    item.save()
    return item


def reorder_faqs(ids):
    from shop.models import FaqItem

    if not isinstance(ids, list) or not all(isinstance(value, int) for value in ids):
        raise ValidationError({"ids": "Expected a list of FAQ ids."})
    with transaction.atomic():
        rest = list(FaqItem.objects.exclude(pk__in=ids).order_by("sort_order", "id").values_list("id", flat=True))
        for index, faq_id in enumerate([*ids, *rest], start=1):
            FaqItem.objects.filter(pk=faq_id).update(sort_order=index)
    return content_payload(include_inactive_faqs=True)
