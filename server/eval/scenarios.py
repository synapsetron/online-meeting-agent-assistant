"""SYNTHETIC scripted meetings for the offline cost replay (WP3).

Everything in this module is invented for the experiment: no real people, no
real meeting content. Speakers are anonymous labels. The texts are Ukrainian
because the product targets Ukrainian meetings and Cyrillic text has a different
token cost than English.

Pacing follows the one real session we have numbers for (about one final segment
per 8 s, about 11 words per segment): gaps cycle deterministically through
``GAP_PATTERN_S`` (6-10 s) and every utterance has 5-25 words. Ids are long on
purpose, like production: UUID segment ids and ``item-<epoch-ms>-<rand>`` agenda
ids. Nothing here is random; the same import always yields the same data.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

SYNTHETIC = True  # marker: this is not recorded meeting data

GAP_PATTERN_S: tuple[int, ...] = (8, 6, 9, 7, 10, 8, 7, 9)  # mean 8 s
DEFAULT_TRAILING_SILENCE_S = 30.0
MEETING_EPOCH_MS = 1_791_006_900_000  # fixed fake wall-clock start of every scenario

_SEGMENT_ID_NAMESPACE = uuid.UUID("5b0c1f0e-7a41-4c1b-9d55-0c6f3f2a9e10")
_SPEAKERS = ("Спікер А", "Спікер Б", "Спікер В")
_AGENDA_ID_SUFFIXES = ("scy4", "k9qd", "m2xv", "t7hb")


@dataclass(frozen=True)
class AgendaSpec:
    id: str
    title: str
    estimated_minutes: float | None = None


@dataclass(frozen=True)
class SegmentSpec:
    id: str
    t_seconds: float  # simulated seconds from meeting start at which the final segment arrives
    speaker: str
    text: str
    off_agenda: bool = False  # part of a scripted drift away from the agenda


@dataclass(frozen=True)
class Scenario:
    key: str
    title: str  # Ukrainian, for the results document
    description: str  # Ukrainian
    agenda: tuple[AgendaSpec, ...]
    segments: tuple[SegmentSpec, ...]
    trailing_silence_s: float = DEFAULT_TRAILING_SILENCE_S
    # When True the fake LLM answers with one canned topic_drift hint whenever the
    # newest segment it was shown is ``off_agenda`` (exercises the hint path).
    canned_drift_hints: bool = False
    pauses: dict[int, float] = field(default_factory=dict, compare=False)

    @property
    def duration_s(self) -> float:
        """Simulated meeting length: last segment plus the trailing silence."""
        return self.segments[-1].t_seconds + self.trailing_silence_s

    @property
    def total_words(self) -> int:
        return sum(len(s.text.split()) for s in self.segments)


# ---------------------------------------------------------------------------
# Utterance pools (synthetic). The first utterance of a pool opens the topic.
# ---------------------------------------------------------------------------

_SPRINT = (
    "Почнімо зі статусу спринту: що ми встигли закрити за цей тиждень?",
    "У цьому спринті ми закрили дванадцять задач із запланованих п'ятнадцяти.",
    "Три задачі залишилися в роботі, дві з них майже готові до перевірки.",
    "Швидкість команди трохи впала, бо двоє людей були на навчанні.",
    "Задачу з авторизацією перенесли, оскільки змінилися вимоги від замовника.",
    "Я закінчив інтеграцію з платіжним сервісом і передав її на рев'ю.",
    "Рев'ю коду зараз займає приблизно день, і це гальмує закриття задач спринту.",
    "Пропоную домовитися, що кожен переглядає чужі зміни до обіду.",
    "На дошці спринту є дві задачі без виконавця, їх треба розподілити сьогодні.",
    "Я візьму задачу з експортом звітів, вона невелика.",
    "Тоді друга задача про сповіщення залишається мені, зроблю до четверга.",
    "Загалом спринт іде за графіком, критичних відставань я не бачу.",
)

_BLOCKERS = (
    "Перейдемо до наступного пункту: які зараз є блокери розробки?",
    "Головний блокер у мене це нестабільне тестове середовище, воно падає щодня.",
    "Через це автотести проходять лише з третьої спроби, і ми втрачаємо години.",
    "Ще один блокер це доступ до нової бази даних, заявку досі не погодили.",
    "Я вже двічі писав адміністраторам, але відповіді поки немає.",
    "Можу підняти це питання на рівні керівника відділу, якщо потрібно.",
    "Так, будь ласка, бо без доступу розробка модуля звітів стоїть.",
    "У мене блокер інший: бракує макетів для екрана налаштувань.",
    "Дизайнер обіцяв надіслати макети завтра вранці, я нагадаю йому сьогодні.",
    "Тоді тимчасово візьми задачу з рефакторингу, щоб не простоювати.",
    "Добре, а тестове середовище хтось може подивитися вже сьогодні?",
    "Я подивлюся після зустрічі, схоже, що проблема в конфігурації контейнерів.",
)

_RELEASE = (
    "Переходимо до плану релізу: коли ми реально можемо випустити версію?",
    "За планом реліз призначено на наступну середу, але є ризики.",
    "Щоб встигнути, треба заморозити код у п'ятницю ввечері.",
    "Після заморожування залишаться лише виправлення помилок, без нових функцій.",
    "У реліз точно входять платежі, оновлений профіль і експорт звітів.",
    "Сповіщення я б переніс у наступний реліз, вони ще сирі.",
    "Згоден, краще випустити менше, але стабільно, ніж відкочувати реліз.",
    "Хто відповідає за інструкцію з розгортання і сценарій відкату?",
    "Інструкцію з розгортання оновлю я, а сценарій відкату напише наш інженер з інфраструктури.",
    "Ще треба попередити підтримку про дату релізу і нові функції.",
    "Я підготую короткий опис змін для підтримки до понеділка.",
    "Отже, план релізу такий: заморожування в п'ятницю, випуск у середу.",
)

_BUDGET = (
    "Наступне питання це бюджет тестування на наступний квартал.",
    "Зараз у бюджеті закладено години лише на ручне тестування.",
    "Я пропоную частину бюджету перенести на автоматизацію регресійних тестів.",
    "Автоматизація окупиться приблизно за два релізи, якщо рахувати години тестувальників.",
    "Скільки коштуватиме ліцензія на інструмент для навантажувального тестування?",
    "Приблизно стільки, скільки два дні роботи одного тестувальника на місяць.",
    "Тоді це вкладається в бюджет, якщо не розширювати команду тестування.",
    "Ще варто закласти резерв на тестування на реальних пристроях.",
    "Резерв у десять відсотків бюджету виглядає розумним, більше нам не погодять.",
    "Я оформлю запит на бюджет тестування і надішлю його до кінця тижня.",
    "Додай туди порівняння з поточними витратами, так буде легше погодити.",
    "Домовилися, бюджет тестування фіксуємо в такому вигляді.",
)

_OFF_AGENDA = (
    "До речі, хтось уже бачив, який сніг обіцяють на вихідні?",
    "Так, кажуть, що в суботу буде мінус десять і сильний вітер.",
    "Я якраз збирався їхати в гори, тепер думаю, чи брати ланцюги на колеса.",
    "Бери обов'язково, минулого року ми простояли на перевалі чотири години.",
    "А де ви зупиняєтесь, у готелі чи орендуєте будинок?",
    "Орендуємо будинок на шістьох, виходить дешевше і є своя кухня.",
    "Звучить чудово, я б теж поїхав, але в мене ремонт на кухні.",
    "О, ремонт це надовго, ми свій робили майже пів року.",
    "Найгірше було з плиткою, майстер тричі переносив терміни.",
    "А ще нова кав'ярня відкрилася біля офісу, там дуже смачні круасани.",
    "Треба буде сходити туди разом на обід наступного тижня.",
    "Гаразд, ми трохи відволіклися, повертаймося до порядку денного.",
)

# Short lead-ins used to vary repeated utterances deterministically.
_OPENERS = ("", "Дивіться,", "Як на мене,", "Чесно кажучи,", "Додам ще,", "Якщо коротко,", "Підсумовуючи,")

_Block = tuple[tuple[str, ...], int, bool]  # (pool, number of utterances, off_agenda)


def _vary(pool: tuple[str, ...], k: int) -> str:
    """k-th utterance of a block: the pool verbatim on the first pass, then the
    same sentences with a rotating lead-in (deterministic, no randomness)."""
    core = pool[k % len(pool)]
    if k < len(pool):
        return core
    opener = _OPENERS[(k // len(pool) + k) % len(_OPENERS)]
    if not opener:
        return core
    return f"{opener} {core[0].lower()}{core[1:]}"


def _agenda(*items: tuple[str, float | None]) -> tuple[AgendaSpec, ...]:
    return tuple(
        AgendaSpec(
            id=f"item-{1_791_006_808_101 + 4217 * i}-{_AGENDA_ID_SUFFIXES[i % len(_AGENDA_ID_SUFFIXES)]}",
            title=title,
            estimated_minutes=minutes,
        )
        for i, (title, minutes) in enumerate(items)
    )


def _build_segments(
    key: str, blocks: tuple[_Block, ...], pauses: dict[int, float]
) -> tuple[SegmentSpec, ...]:
    segments: list[SegmentSpec] = []
    t = 0.0
    for pool, count, off_agenda in blocks:
        for k in range(count):
            i = len(segments)
            t += GAP_PATTERN_S[i % len(GAP_PATTERN_S)] + pauses.get(i, 0.0)
            segments.append(
                SegmentSpec(
                    id=str(uuid.uuid5(_SEGMENT_ID_NAMESPACE, f"{key}:{i}")),
                    t_seconds=t,
                    speaker=_SPEAKERS[(i + i // 5) % len(_SPEAKERS)],
                    text=_vary(pool, k),
                    off_agenda=off_agenda,
                )
            )
    return tuple(segments)


def _scenario(
    key: str,
    title: str,
    description: str,
    agenda: tuple[AgendaSpec, ...],
    blocks: tuple[_Block, ...],
    *,
    pauses: dict[int, float] | None = None,
    canned_drift_hints: bool = False,
) -> Scenario:
    pauses = dict(pauses or {})
    return Scenario(
        key=key,
        title=title,
        description=description,
        agenda=agenda,
        segments=_build_segments(key, blocks, pauses),
        canned_drift_hints=canned_drift_hints,
        pauses=pauses,
    )


_FULL_AGENDA = (
    ("Статус спринту", 2.0),
    ("Блокери розробки", 2.0),
    ("План релізу", 2.0),
    ("Бюджет тестування", 1.5),
)

NORMAL_FLOW = _scenario(
    "normal_flow",
    "Нормальний перебіг",
    "Чотири пункти порядку денного обговорюються по черзі, без відхилень.",
    _agenda(*_FULL_AGENDA),
    ((_SPRINT, 10, False), (_BLOCKERS, 10, False), (_RELEASE, 10, False), (_BUDGET, 8, False)),
)

DRIFT_AND_RETURN = _scenario(
    "drift_and_return",
    "Відхилення від теми та повернення",
    "Під час другого пункту розмова переходить на сторонні теми, потім після "
    "паузи 35 с учасники повертаються до порядку денного.",
    _agenda(*_FULL_AGENDA[:3]),
    (
        (_SPRINT, 8, False),
        (_BLOCKERS, 5, False),
        (_OFF_AGENDA, 12, True),
        (_BLOCKERS[1:], 5, False),
        (_RELEASE, 8, False),
    ),
    pauses={25: 35.0},  # silence before the first utterance after the drift
    canned_drift_hints=True,
)

SKIPPED_ITEM = _scenario(
    "skipped_item",
    "Пропущений пункт",
    "Третій пункт («План релізу») не обговорюється: після другого пункту одразу "
    "переходять до четвертого.",
    _agenda(*_FULL_AGENDA),
    ((_SPRINT, 10, False), (_BLOCKERS, 10, False), (_BUDGET, 12, False)),
)

ITEM_OVERRUN = _scenario(
    "item_overrun",
    "Перевищення часу пункту",
    "Перший пункт оцінено в 1 хв, але він триває близько 5 хв; далі короткий другий пункт.",
    _agenda(("Статус спринту", 1.0), ("Блокери розробки", 2.0)),
    ((_SPRINT, 36, False), (_BLOCKERS, 8, False)),
)

LONG_MEETING = _scenario(
    "long_meeting",
    "Довга зустріч (~30 хв)",
    "Близько 30 хв: чотири пункти з повторюваними варіаціями реплік і один "
    "епізод відхилення від теми; згенеровано детерміновано з шаблонів.",
    _agenda(("Статус спринту", 7.0), ("Блокери розробки", 8.0), ("План релізу", 7.0), ("Бюджет тестування", 7.0)),
    (
        (_SPRINT, 50, False),
        (_BLOCKERS, 45, False),
        (_OFF_AGENDA, 12, True),
        (_BLOCKERS[1:], 15, False),
        (_RELEASE, 50, False),
        (_BUDGET, 50, False),
    ),
)

SCENARIOS: tuple[Scenario, ...] = (
    NORMAL_FLOW,
    DRIFT_AND_RETURN,
    SKIPPED_ITEM,
    ITEM_OVERRUN,
    LONG_MEETING,
)

SCENARIOS_BY_KEY: dict[str, Scenario] = {s.key: s for s in SCENARIOS}
