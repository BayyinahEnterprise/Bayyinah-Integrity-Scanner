"""Instruction phrases in languages other than English.

The English families in ``concealed_instruction`` cannot see an attack
written in Chinese or Russian. This module adds the three plainest
shapes, in sixteen languages:

* override:   "ignore / forget the (previous) instructions"
* disclosure: "show / reveal the system prompt"
* steering:   "do not tell the user"

Each pattern is a verb and an object within a short window, in the
order the language uses, so ordinary inflection and filler words still
match. They are deliberately few. A paraphrase, a dialect form or a
language not listed here will pass, and a "not instruction-like"
result never means hidden text is safe.

Scripts without spaces (Chinese, Japanese) and scripts whose letters
are not ``\\w`` word characters to the pattern engine in the same way
are written without word boundaries.
"""

from __future__ import annotations

import re
from typing import Final

_F = re.I | re.S


def _any(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(f"(?:{a})" for a in alts), _F)


_OVERRIDE: Final[re.Pattern[str]] = _any(
    # Chinese (simplified and traditional)
    r"(?:忽略|无视|無視|忽視|忽视|不要理会|不要理會|忘记|忘記|不用管).{0,14}(?:指令|指示|提示|说明|說明|规则|規則|要求)",
    # Japanese
    r"(?:以前|これまで|上記|前述|今まで|すべて|全て).{0,12}(?:指示|命令|プロンプト|ルール|指令).{0,12}(?:無視|忘れ)",
    # Korean
    r"(?:이전|위의|앞의|기존|모든).{0,12}(?:지시|지침|명령|프롬프트|규칙).{0,12}(?:무시|잊)",
    # Arabic
    r"(?:تجاهل|تجاهلي|تجاهلوا|أهمل|اهمل|انس|إنس).{0,40}(?:التعليمات|الأوامر|الاوامر|التوجيهات|الإرشادات|الارشادات)",
    # Persian
    r"(?:دستورالعمل|دستورات|دستور|فرمان).{0,40}(?:نادیده|فراموش)",
    # Urdu
    r"(?:ہدایات|احکامات|احکام).{0,40}(?:نظر\s?انداز|بھول)",
    # Hindi
    r"(?:निर्देश|निर्देशों|आदेश|आदेशों|अनुदेश).{0,40}(?:अनदेखा|अनदेखी|नज़रअंदाज़|नजरअंदाज|भूल)",
    # Russian, Ukrainian
    r"(?:игнорируй|проигнорируй|забудь|не обращай(?:те)? внимания на|ігноруй|проігноруй|забудь).{0,45}"
    r"(?:инструкци|указани|правил|команд|інструкці|вказівк)",
    # Spanish
    r"\b(?:ignora|ignore|ignorad|olvida|olvide|haz caso omiso de|omite)\b.{0,45}\b(?:instrucciones|indicaciones|reglas|órdenes)\b",
    # Portuguese
    r"\b(?:ignore|ignora|desconsidere|esqueça|esqueca)\b.{0,45}\b(?:instruções|instrucoes|orientações|regras|comandos)\b",
    # French
    r"\b(?:ignore[zr]?|oublie[zr]?|ne tiens pas compte d|ne tenez pas compte d)\w*.{0,45}\b(?:instructions|consignes|directives|règles)\b",
    # German
    r"\b(?:ignorier(?:e|en|t)?|vergiss|vergessen sie|missachte)\b.{0,45}\b(?:anweisung(?:en)?|instruktionen|vorgaben|regeln|befehle)\b",
    # Italian
    r"\b(?:ignora|ignorate|dimentica)\b.{0,45}\b(?:istruzioni|indicazioni|regole)\b",
    # Turkish
    r"(?:talimat|yönerge|komut|kural)\w*.{0,35}(?:yok say|görmezden gel|dikkate alma|unut)",
    # Indonesian, Malay
    r"\b(?:abaikan|lupakan)\b.{0,45}\b(?:instruksi|perintah|petunjuk|aturan|arahan)\b",
    # Vietnamese
    r"(?:bỏ qua|phớt lờ|quên).{0,45}(?:hướng dẫn|chỉ dẫn|chỉ thị|lệnh)",
)

_DISCLOSURE: Final[re.Pattern[str]] = _any(
    r"(?:显示|顯示|输出|輸出|透露|泄露|洩露|告诉我|告訴我|打印|列出).{0,16}(?:系统提示|系統提示|提示词|提示詞|系统指令|系統指令)",
    r"(?:系统提示|系統提示|提示词|提示詞).{0,16}(?:显示|顯示|输出|輸出|透露|泄露|洩露)",
    r"システムプロンプト.{0,16}(?:表示|出力|開示|教え|見せ)",
    r"시스템\s?프롬프트.{0,16}(?:공개|출력|보여|알려)",
    r"(?:اكشف|أظهر|اظهر|اعرض|اطبع).{0,35}(?:موجه النظام|تعليمات النظام|رسالة النظام)",
    r"(?:покажи|выведи|раскрой|сообщи|напечатай).{0,35}системн\w+ (?:промпт|подсказк|инструкци|сообщени)",
    r"\b(?:revela|muestra|imprime)\b.{0,35}(?:prompt|instrucciones|mensaje) del sistema",
    r"\b(?:revele|mostre|exiba|imprima)\b.{0,35}(?:prompt|instruções|mensagem) do sistema",
    r"\b(?:révèle|affiche|montre)\w*.{0,35}(?:prompt|instructions?|message|invite) système",
    r"\b(?:zeige?|gib|verrate|offenbare)\b.{0,35}system[- ]?(?:prompt|anweisung|nachricht)",
)

_STEERING: Final[re.Pattern[str]] = _any(
    r"不要(?:告诉|告訴|提及|透露|让|讓).{0,12}(?:用户|用戶|使用者)",
    r"ユーザー.{0,12}(?:伝えない|言わない|知らせない|教えない)",
    r"사용자.{0,12}(?:말하지|알리지|언급하지)",
    r"لا (?:تخبر|تذكر|تبلغ).{0,25}المستخدم",
    r"не (?:говори|сообщай|упоминай)(?:те)?.{0,25}пользовател",
    r"\bno (?:le )?(?:digas|menciones|informes)\b.{0,25}usuario",
    r"\bnão (?:diga|mencione|informe|conte)\b.{0,25}usuário",
    r"\bne (?:dis|dites|mentionne[zs]?|révèle[zs]?) (?:pas|rien)\b.{0,25}utilisateur",
    r"\b(?:sag|sage|erwähne|teile)\b.{0,25}(?:nutzer|benutzer|anwender).{0,25}\bnichts?\b",
)

I18N_FAMILIES: Final[dict[str, tuple[int, re.Pattern[str]]]] = {
    "override_i18n": (3, _OVERRIDE),
    "disclosure_i18n": (3, _DISCLOSURE),
    "steering_i18n": (2, _STEERING),
}

__all__ = ["I18N_FAMILIES"]
