"""Uzbek (default) user-facing strings."""

MESSAGES: dict[str, str] = {
    "start": (
        "👋 Salom! Men media yuklab beruvchi botman.\n\n"
        "Instagram, TikTok, YouTube yoki Pinterest havolasini yuboring — "
        "men uni siz uchun yuklab beraman.\n\n"
        "Yoki shunchaki qo'shiq nomini yozing — natijalar ro'yxatidan tanlang, "
        "men mp3 qilib yuboraman 🎵\n\n"
        "Buyruqlar: /help /settings /status"
    ),
    "help": (
        "ℹ️ Qo'llab-quvvatlanadigan platformalar:\n"
        "• Instagram (reels, post, rasm, karusel)\n"
        "• TikTok\n"
        "• YouTube (video va Shorts)\n"
        "• Pinterest (pin)\n\n"
        "Shunchaki havolani yuboring — platforma avtomatik aniqlanadi.\n"
        "🎵 Yoki qo'shiq/ijrochi nomini yozing (havolasiz) — 10 tagacha natija "
        "ro'yxatini ko'rsataman, birini tanlasangiz audio (mp3) qilib yuboraman.\n\n"
        "Sozlamalar uchun /settings, holat uchun /status buyrug'ini ishlating."
    ),
    "settings_title": "⚙️ Sifat sozlamasi:",
    "settings_saved": "✅ Sozlama saqlandi: {quality}",
    "settings_audio_only_on": "🎵 Faqat audio: YOQILGAN",
    "settings_audio_only_off": "🎬 Faqat audio: O'CHIRILGAN",
    "status_header": "📊 Bot holati",
    "link_detected": "🔎 Havola aniqlandi",
    "music_search_detected": "🎵 Qidirilmoqda…",
    "error_no_query": "❌ Qidiruv uchun matn juda qisqa. Qo'shiq yoki ijrochi nomini yozing.",
    "error_no_search_results": "❌ Hech narsa topilmadi. Boshqacha nom bilan urinib ko'ring.",
    "error_search_expired": "⏳ Qidiruv muddati tugadi. Qaytadan qidiring.",
    "search_picked": "✅ Tanlandi: {title}",
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
