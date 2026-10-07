/// Abschnitt einer Fahrt (Sekunden seit Start), der in allen Diagrammen und auf der Karte hervorgehoben wird.
class Highlight {
  const Highlight({required this.startS, required this.durationS, required this.watts, this.label});
  final int startS;
  final int durationS;
  final double watts;
  final String? label; // gesetzt bei einer Runde, z. B. "Runde 3"; null bei der besten Dauer der Leistungskurve

  int get endS => startS + durationS;
  double get startMin => startS / 60;
  double get endMin => endS / 60;

  @override
  bool operator ==(Object other) => other is Highlight && other.startS == startS && other.durationS == durationS;

  @override
  int get hashCode => Object.hash(startS, durationS);
}
