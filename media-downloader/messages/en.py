"""English strings — not the default, but kept in parity for future i18n."""

MESSAGES: dict[str, str] = {
    "start": (
        "👋 Hi! I'm a media downloader bot.\n\n"
        "Send an Instagram, TikTok, YouTube or Pinterest link and I'll "
        "download it for you.\n\n"
        "Commands: /help /settings /status"
    ),
    "help": (
        "ℹ️ Supported platforms:\n"
        "• Instagram (reels, posts, images, carousels)\n"
        "• TikTok\n"
        "• YouTube (videos and Shorts)\n"
        "• Pinterest (pins)\n\n"
        "Just send a link — the platform is detected automatically.\n"
        "Use /settings for quality options, /status for bot status."
    ),
    "settings_title": "⚙️ Quality setting:",
    "settings_saved": "✅ Setting saved: {quality}",
    "status_header": "📊 Bot status",
    "link_detected": "🔎 Link detected",
    "downloading": "⬇️ Downloading…",
    "processing": "📦 Processing…",
    "uploading": "📤 Uploading…",
    "complete": "✅ Done",
    "error_unsupported_link": "❌ Unsupported link.",
    "error_invalid_url": "❌ The link is invalid or unsafe.",
    "error_download_failed": "❌ The media could not be downloaded.",
    "error_private": "❌ This content is private or unavailable.",
    "error_too_large": "❌ The media is too large for Telegram.",
    "error_timeout": "❌ Download timed out. Please try again later.",
    "error_rate_limited": "⏳ Too many requests. Please try again later.",
    "error_queue_full": "⏳ The queue is full. Please try again later.",
    "error_active_job": "⏳ You already have a download in progress. Please wait for it to finish.",
    "error_generic": "❌ Something went wrong. Please try again later.",
    "not_admin": "⛔ This command is for administrators only.",
}
