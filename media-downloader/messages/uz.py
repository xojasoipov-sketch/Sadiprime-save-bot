"""Uzbek (default) user-facing strings."""

MESSAGES: dict[str, str] = {
    "start": (
        "👋 Salom! Men media yuklab beruvchi botman.\n\n"
        "Instagram, TikTok, YouTube yoki Pinterest havolasini yuboring — "
        "men uni siz uchun yuklab beraman.\n\n"
        "Buyruqlar: /help /settings /status"
    ),
    "help": (
        "ℹ️ Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (reels, post, rasm, karusel)\n"
        "• TikTok\n"
        "• YouTube (video va Shorts)\n"
        "• Pinterest (pin)\n\n"
        "Shunchaki havolani yuboring — platforma avtomatik aniqlanadi.\n"
        "Sozlamalar uchun /settings, holat uchun /status buyrug'ini ishlating."
    ),
    "settings_title": "⚙️ Sifat sozlamasi:",
    "settings_saved": "✅ Sozlama saqlandi: {quality}",
    "status_header": "📊 Bot holati",
    "link_detected": "🔎 Havola aniqlandi",
    "downloading": "⬇️ Yuklab olinmoqda…",
    "processing": "📦 Qayta ishlanmoqda…",
    "uploading": "📤 Yuborilmoqda…",
    "complete": "✅ Tayyor",
    "error_unsupported_link": "❌ Qo'llab-quvvatlanmaydigan havola.",
    "error_invalid_url": "❌ Havola noto'g'ri yoki xavfsiz emas.",
    "error_download_failed": "❌ Mediani yuklab bo'lmadi.",
    "error_private": "❌ Bu kontent yopiq yoki mavjud emas.",
    "error_too_large": "❌ Media Telegram uchun juda katta.",
    "error_timeout": "❌ Yuklash vaqti tugadi. Birozdan so'ng qayta urinib ko'ring.",
    "error_rate_limited": "⏳ Juda ko'p so'rov. Birozdan so'ng qayta urinib ko'ring.",
    "error_queue_full": "⏳ Navbat to'lgan. Birozdan so'ng qayta urinib ko'ring.",
    "error_active_job": "⏳ Sizda hozir yuklanayotgan media bor. Iltimos, tugashini kuting.",
    "error_generic": "❌ Xatolik yuz berdi. Birozdan so'ng qayta urinib ko'ring.",
    "not_admin": "⛔ Bu buyruq faqat administratorlar uchun.",
}
