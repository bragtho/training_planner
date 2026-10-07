/// Abschnitt einer Fahrt (Sekunden seit Start), der in allen Diagrammen und auf der Karte hervorgehoben wird.
class Highlight {
  const Highlight({required this.startS, required this.durationS, required this.watts});
  final int startS;
  final int durationS;
  final double watts;

  int get endS => startS + durationS;
  double get startMin => startS / 60;
  double get endMin => endS / 60;

  @override
  bool operator ==(Object other) => other is Highlight && other.startS == startS && other.durationS == durationS;

  @override
  int get hashCode => Object.hash(startS, durationS);
}
