"""Optional local system-voice narration; no audio is downloaded or bundled."""

from __future__ import annotations


def speak(text: str, language: str) -> None:
    try:
        import pyttsx3
    except ImportError as error:
        raise RuntimeError(
            "الصوت يحتاج تثبيت الإضافة الاختيارية: python -m pip install \"suda-lang[voice]\""
        ) from error

    engine = pyttsx3.init()
    voices = engine.getProperty("voices")
    matching = []
    for voice in voices:
        languages = [
            item.decode("utf-8", errors="ignore").lower()
            if isinstance(item, bytes)
            else str(item).lower()
            for item in getattr(voice, "languages", [])
        ]
        identity = f"{voice.id} {voice.name} {' '.join(languages)}".lower()
        if language.lower() in identity:
            matching.append(voice)
    if not matching:
        engine.stop()
        language_name = "العربية" if language == "ar" else "الإنجليزية"
        raise RuntimeError(
            f"ماكو صوت نظام مثبت للغة {language_name}. ثبّت حزمة صوت مناسبة من إعدادات النظام."
        )
    engine.setProperty("voice", matching[0].id)
    engine.say(text)
    engine.runAndWait()
    engine.stop()
