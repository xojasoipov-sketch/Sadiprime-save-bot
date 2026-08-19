"""English strings — not the default, but kept in parity for future i18n."""

MESSAGES: dict[str, str] = {
    "start": (
        "👋 Hi! I'm a media downloader bot.\n\n"
        "Send an Instagram, TikTok, YouTube or Pinterest link and I'll "
        "download it for you.\n\n"
        "Or just type a song name — pick from the results list and I'll "
        "send it as mp3 🎵\n\n"
        "Commands: /help /settings /status /stats"
    ),
    "help": (
        "ℹ️ Supported platforms:\n"
        "• Instagram (reels, posts, images, carousels)\n"
        "• TikTok\n"
        "• YouTube (videos and Shorts)\n"
        "• Pinterest (pins)\n\n"
        "Just send a link — the platform is detected automatically.\n"
        "🎵 Or type a song/artist name (no link needed) — I'll show up to "
        "10 results, pick one and I'll send it as audio (mp3).\n\n"
        "Use /settings for quality options, /status for bot status."
    ),
    "settings_title": "⚙️ Quality setting:",
    "settings_saved": "✅ Setting saved: {quality}",
    "settings_audio_only_on": "🎵 Audio only: ON",
    "settings_audio_only_off": "🎬 Audio only: OFF",
    "status_header": "📊 Bot status",
    "stats_header": "📈 Statistics",
    "stats_top_platforms": "By platform:",
    "link_detected": "🔎 Link detected",
    "music_search_detected": "🎵 Searching…",
    "error_no_query": "❌ That's too short to search. Type a song or artist name.",
    "error_no_search_results": "❌ Nothing found. Try a different name.",
    "error_search_expired": "⏳ This search has expired. Please search again.",
    "search_picked": "✅ Selected: {title}",
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
