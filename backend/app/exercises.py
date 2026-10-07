"""Katalog der Kraftuebungen mit Kurzanleitung. Die Strichfiguren dazu zeichnet die App anhand der Kennung (id).

Der Coach waehlt Uebungen ueber `exercise_id`; so bleiben Name, Anleitung und Bild immer zusammen.
`hold` = Haltuebung (eine Position statt Bewegung, Haltezeit statt Wiederholungen).
"""

from __future__ import annotations

EXERCISES: dict[str, dict] = {
    "squat": {
        "name": "Kniebeuge",
        "muscles": ["Oberschenkel vorn", "Gesäß"],
        "steps": [
            "Füße etwa schulterbreit, Zehen leicht nach außen.",
            "Gesäß nach hinten und unten schieben, als würdest Du Dich setzen.",
            "Rücken gerade, Knie folgen den Zehen, Fersen bleiben am Boden.",
            "Mit Druck durch die ganze Fußsohle wieder aufrichten.",
        ],
        "mistakes": ["Knie fallen nach innen", "Fersen heben ab", "Rücken wird rund"],
    },
    "goblet_squat": {
        "name": "Goblet-Kniebeuge",
        "muscles": ["Oberschenkel vorn", "Gesäß", "Rumpf"],
        "steps": [
            "Eine Kurzhantel senkrecht mit beiden Händen vor die Brust halten.",
            "Ellbogen zeigen nach unten, Brust bleibt aufrecht.",
            "Tief in die Kniebeuge sinken, die Ellbogen passen zwischen die Knie.",
            "Aufrichten, ohne dass die Hantel von der Brust wegkippt.",
        ],
        "mistakes": ["Oberkörper kippt nach vorn", "Hantel driftet vom Körper weg"],
    },
    "deadlift": {
        "name": "Kreuzheben",
        "muscles": ["Rückenstrecker", "Gesäß", "Beinbeuger"],
        "steps": [
            "Füße hüftbreit, Hantel oder Stange über der Fußmitte.",
            "Hüfte nach hinten schieben, Rücken lang, Griff etwas außerhalb der Knie.",
            "Mit gestrecktem Rücken aufrichten und die Last nah am Körper führen.",
            "Oben Hüfte und Knie strecken, ohne ins Hohlkreuz zu fallen.",
        ],
        "mistakes": ["Rücken wird rund", "Last driftet vom Körper weg", "Hüfte steigt vor den Schultern"],
    },
    "rdl": {
        "name": "Rumänisches Kreuzheben",
        "muscles": ["Beinbeuger", "Gesäß", "unterer Rücken"],
        "steps": [
            "Aufrecht stehen, Knie leicht gebeugt, Kurzhanteln vor den Oberschenkeln.",
            "Hüfte weit nach hinten schieben, Last gleitet nah an den Beinen nach unten.",
            "Rücken bleibt gerade, bis Du die Dehnung hinten am Oberschenkel spürst.",
            "Hüfte nach vorn schieben und aufrichten.",
        ],
        "mistakes": ["Rücken wird rund", "Knie beugen sich zu stark (wird zur Kniebeuge)"],
    },
    "single_leg_rdl": {
        "name": "Einbeiniges Kreuzheben",
        "muscles": ["Beinbeuger", "Gesäß", "Gleichgewicht"],
        "steps": [
            "Auf einem Bein stehen, das Standknie leicht gebeugt.",
            "Oberkörper nach vorn kippen und das freie Bein gestreckt nach hinten heben.",
            "Hüften bleiben parallel zum Boden, Rücken gerade.",
            "Zurück in den Stand, dann Seite wechseln.",
        ],
        "mistakes": ["Hüfte dreht auf", "Rücken wird rund"],
    },
    "lunge": {
        "name": "Ausfallschritt",
        "muscles": ["Oberschenkel vorn", "Gesäß"],
        "steps": [
            "Großen Schritt nach vorn machen.",
            "Hinteres Knie senkrecht Richtung Boden senken, Oberkörper bleibt aufrecht.",
            "Das vordere Knie bleibt über dem Fuß.",
            "Mit dem vorderen Bein zurück in den Stand drücken.",
        ],
        "mistakes": ["Vorderes Knie schiebt weit über die Zehen", "Oberkörper kippt nach vorn"],
    },
    "split_squat": {
        "name": "Bulgarische Kniebeuge",
        "muscles": ["Oberschenkel vorn", "Gesäß", "Gleichgewicht"],
        "steps": [
            "Hinteren Fuß auf einer Bank oder einem Stuhl ablegen, vorderen Fuß etwa einen großen Schritt davor.",
            "Senkrecht nach unten sinken, bis der vordere Oberschenkel etwa waagerecht ist.",
            "Gewicht liegt auf dem vorderen Bein, der Oberkörper bleibt aufrecht.",
            "Aufrichten, nach den Wiederholungen die Seite wechseln.",
        ],
        "mistakes": ["Fuß zu nah an der Bank", "Gewicht liegt auf dem hinteren Bein"],
    },
    "step_up": {
        "name": "Step-up",
        "muscles": ["Oberschenkel vorn", "Gesäß"],
        "steps": [
            "Einen Fuß komplett auf eine Bank oder Kiste stellen (Knie etwa 90 Grad).",
            "Mit dem Bein auf der Kiste hochdrücken, das andere Bein nur kurz antippen.",
            "Oben gerade stehen, dann kontrolliert absteigen.",
            "Seite wechseln.",
        ],
        "mistakes": ["Das hintere Bein stößt mit ab", "Knie fällt nach innen"],
    },
    "glute_bridge": {
        "name": "Beckenheben",
        "muscles": ["Gesäß", "Beinbeuger"],
        "steps": [
            "Auf dem Rücken liegen, Füße hüftbreit aufgestellt, Arme neben dem Körper.",
            "Hüfte anheben, bis Schultern, Hüfte und Knie eine Linie bilden.",
            "Oben das Gesäß kurz fest anspannen.",
            "Kontrolliert wieder absenken.",
        ],
        "mistakes": ["Hohlkreuz beim Anheben", "Druck nur über die Zehen"],
    },
    "hip_thrust": {
        "name": "Hip Thrust",
        "muscles": ["Gesäß", "Beinbeuger"],
        "steps": [
            "Oberen Rücken an eine Bank lehnen, Füße hüftbreit aufgestellt.",
            "Hüfte hochdrücken, bis der Oberkörper waagerecht ist.",
            "Oben Kinn leicht zur Brust, Gesäß fest anspannen.",
            "Hüfte kontrolliert absenken, Gewicht (falls vorhanden) liegt auf der Hüfte.",
        ],
        "mistakes": ["Überstreckter unterer Rücken", "Füße zu nah oder zu weit vom Körper"],
    },
    "calf_raise": {
        "name": "Wadenheben",
        "muscles": ["Waden"],
        "steps": [
            "Aufrecht stehen, Vorderfüße auf einer Stufenkante (oder flach am Boden).",
            "Langsam so hoch wie möglich auf die Zehenspitzen drücken.",
            "Oben kurz halten, dann tief absenken, bis die Wade gedehnt ist.",
        ],
        "mistakes": ["Wippen mit Schwung", "Fußgelenke knicken nach außen"],
    },
    "plank": {
        "name": "Unterarmstütz",
        "hold": True,
        "muscles": ["Rumpf", "Schultern"],
        "steps": [
            "Auf Unterarme und Zehenspitzen stützen, Ellbogen unter den Schultern.",
            "Körper bildet eine gerade Linie von Kopf bis Ferse.",
            "Bauch und Gesäß anspannen, normal weiteratmen.",
        ],
        "mistakes": ["Hüfte hängt durch", "Hüfte ragt nach oben", "Atem anhalten"],
    },
    "side_plank": {
        "name": "Seitstütz",
        "hold": True,
        "muscles": ["seitlicher Rumpf", "Gesäß", "Schultern"],
        "steps": [
            "Auf die Seite legen, Unterarm unter der Schulter, Beine übereinander.",
            "Hüfte anheben, bis der Körper eine gerade Linie bildet.",
            "Position halten, danach die Seite wechseln.",
        ],
        "mistakes": ["Hüfte sinkt ab", "Oberkörper dreht nach vorn oder hinten"],
    },
    "dead_bug": {
        "name": "Dead Bug",
        "muscles": ["tiefer Rumpf", "Hüftbeuger"],
        "steps": [
            "Auf dem Rücken liegen, Arme senkrecht nach oben, Hüfte und Knie 90 Grad gebeugt.",
            "Gegenüberliegenden Arm und Bein langsam strecken, ohne Hohlkreuz.",
            "Unterer Rücken bleibt am Boden.",
            "Zurück in die Ausgangsposition, Seite wechseln.",
        ],
        "mistakes": ["Hohlkreuz", "Zu schnelle Bewegung"],
    },
    "bird_dog": {
        "name": "Vierfüßlerstand mit Armheben (Bird Dog)",
        "muscles": ["Rumpf", "Gesäß", "unterer Rücken"],
        "steps": [
            "Auf Hände und Knie, Hände unter den Schultern, Knie unter den Hüften.",
            "Gegenüberliegenden Arm und Bein gleichzeitig lang ausstrecken.",
            "Rücken bleibt ruhig, Hüfte kippt nicht zur Seite.",
            "Zurück zur Mitte, Seite wechseln.",
        ],
        "mistakes": ["Hohlkreuz", "Becken dreht auf"],
    },
    "push_up": {
        "name": "Liegestütz",
        "muscles": ["Brust", "Trizeps", "Schultern", "Rumpf"],
        "steps": [
            "Hände etwas mehr als schulterbreit, Körper gerade von Kopf bis Ferse.",
            "Brust kontrolliert Richtung Boden senken, Ellbogen etwa 45 Grad vom Körper.",
            "Kräftig zurück nach oben drücken.",
            "Zu schwer: Knie ablegen oder Hände auf eine erhöhte Fläche.",
        ],
        "mistakes": ["Hüfte hängt durch", "Ellbogen weit nach außen"],
    },
    "row": {
        "name": "Rudern vorgebeugt",
        "muscles": ["oberer Rücken", "Bizeps"],
        "steps": [
            "Hüfte nach hinten, Oberkörper fast waagerecht, Rücken gerade, Kurzhantel hängt unter der Schulter.",
            "Ellbogen nah am Körper nach hinten ziehen, bis die Hantel an die Rippen kommt.",
            "Schulterblatt kurz zusammenziehen.",
            "Kontrolliert wieder absenken.",
        ],
        "mistakes": ["Oberkörper dreht mit", "Mit Schwung aus dem Rücken ziehen"],
    },
    "hip_flexor_stretch": {
        "name": "Hüftbeuger-Dehnung",
        "hold": True,
        "muscles": ["Hüftbeuger"],
        "steps": [
            "Ins Ausfallschritt-Knien gehen: hinteres Knie am Boden, vorderer Fuß flach davor.",
            "Becken leicht nach hinten kippen und Hüfte nach vorn schieben.",
            "Oberkörper aufrecht, Arm der hinteren Seite nach oben strecken.",
            "Ruhig atmen und halten, danach die Seite wechseln.",
        ],
        "mistakes": ["Hohlkreuz statt Beckenkippung", "Vorderes Knie schiebt weit über die Zehen"],
    },
    "superman": {
        "name": "Rückenstrecker (Superman)",
        "muscles": ["Rückenstrecker", "Gesäß"],
        "steps": [
            "Auf den Bauch legen, Arme nach vorn ausgestreckt, Blick zum Boden.",
            "Arme, Brust und Beine gleichzeitig wenige Zentimeter anheben.",
            "Kurz halten, ohne den Nacken zu überstrecken.",
            "Kontrolliert ablegen.",
        ],
        "mistakes": ["Kopf in den Nacken", "Mit Schwung hochreißen"],
    },
}


def catalog() -> list[dict]:
    """Katalog als Liste fuer die API (id, Name, Haltuebung, Muskeln, Schritte, typische Fehler)."""
    return [{"id": k, "hold": bool(v.get("hold")), **{f: v[f] for f in ("name", "muscles", "steps", "mistakes")}} for k, v in EXERCISES.items()]


# Schreibweisen, damit auch frei benannte Uebungen ("Hip Bridge", "Rumaenisches Kreuzheben") eine Anleitung bekommen.
# Reihenfolge zaehlt: spezielle Namen vor allgemeinen.
_ALIASES: list[tuple[str, str]] = [
    ("goblet", "goblet_squat"), ("bulgar", "split_squat"), ("split squat", "split_squat"), ("split-squat", "split_squat"),
    ("einbein", "single_leg_rdl"), ("single leg", "single_leg_rdl"), ("single-leg", "single_leg_rdl"),
    ("rumän", "rdl"), ("rumaen", "rdl"), ("romanian", "rdl"), ("rdl", "rdl"),
    ("kreuzheben", "deadlift"), ("deadlift", "deadlift"),
    ("kniebeuge", "squat"), ("squat", "squat"),
    ("ausfallschritt", "lunge"), ("lunge", "lunge"),
    ("step-up", "step_up"), ("step up", "step_up"), ("stepup", "step_up"),
    ("hip thrust", "hip_thrust"), ("hip-thrust", "hip_thrust"),
    ("hip bridge", "glute_bridge"), ("glute bridge", "glute_bridge"), ("brücke", "glute_bridge"), ("bruecke", "glute_bridge"),
    ("beckenheben", "glute_bridge"),
    ("waden", "calf_raise"), ("calf", "calf_raise"),
    ("seitstütz", "side_plank"), ("seitstuetz", "side_plank"), ("side plank", "side_plank"),
    ("plank", "plank"), ("unterarmstütz", "plank"), ("unterarmstuetz", "plank"),
    ("dead bug", "dead_bug"), ("bird dog", "bird_dog"), ("bird-dog", "bird_dog"), ("vierfüßler", "bird_dog"),
    ("liegestütz", "push_up"), ("liegestuetz", "push_up"), ("push-up", "push_up"), ("push up", "push_up"), ("pushup", "push_up"),
    ("rudern vorgebeugt", "row"), ("bent over row", "row"), ("bent-over row", "row"),
    ("hüftbeuger", "hip_flexor_stretch"), ("hueftbeuger", "hip_flexor_stretch"), ("hip flexor", "hip_flexor_stretch"),
    ("superman", "superman"), ("rückenstrecker", "superman"), ("rueckenstrecker", "superman"),
]


def match_id(name: str | None) -> str | None:
    """Katalog-Kennung zu einem freien Uebungsnamen, sonst None."""
    n = (name or "").lower()
    return next((eid for alias, eid in _ALIASES if alias in n), None)
