import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/core/sport.dart';
import 'package:training_planner/features/activity/activity_analysis.dart';
import 'package:training_planner/features/activity/activity_map.dart';
import 'package:training_planner/features/activity/activity_screen.dart';
import 'package:training_planner/features/activity/highlight.dart';
import 'package:training_planner/features/activity/zoom.dart';

Json _streams({bool gps = true}) => {
  'time': [for (var i = 0; i < 20; i++) i * 30],
  'watts': [for (var i = 0; i < 20; i++) i < 10 ? 150 : 320],
  'heartrate': [for (var i = 0; i < 20; i++) 120 + i],
  'cadence': [for (var i = 0; i < 20; i++) i == 0 ? 0 : 88],
  'altitude': [for (var i = 0; i < 20; i++) 400 + i],
  'latlng': gps ? [for (var i = 0; i < 20; i++) [46.0 + i * 0.001, 7.0 + i * 0.001]] : [],
};

final _curve = [
  {'duration_s': 5, 'watts': 400, 'start_s': 330},
  {'duration_s': 60, 'watts': 330, 'start_s': 320},
  {'duration_s': 300, 'watts': 320, 'start_s': 300},
  {'duration_s': 1200, 'watts': 250, 'start_s': 0},
];

final _laps = [
  {'index': 1, 'start_s': 0, 'duration_s': 300, 'distance_m': 2500.0, 'avg_watts': 150.0, 'avg_heartrate': 125.0},
  {'index': 2, 'start_s': 300, 'duration_s': 270, 'distance_m': 2500.0, 'avg_watts': 320.0, 'avg_heartrate': 135.0},
];

Widget _screen({bool gps = true, List<Json>? laps, String? sport, num? tss}) => ProviderScope(
  overrides: [
    activityProvider(1).overrideWith(
      (ref) async => {
        'id': 1,
        'name': 'Testfahrt',
        'start_time': '2026-09-01T08:00:00',
        'duration_s': 600,
        'distance_m': 5000,
        'sport': ?sport,
        'tss': ?tss,
      },
    ),
    streamsProvider(1).overrideWith((ref) async => _streams(gps: gps)),
    powerCurveProvider(1).overrideWith((ref) async => _curve),
    lapsProvider(1).overrideWith((ref) async => laps ?? _laps),
    // gezoomter Ausschnitt in Sekundenaufloesung: ein Punkt je Sekunde
    streamsWindowProvider.overrideWith((ref, key) async {
      final (_, from, to) = key;
      final t = [for (var i = from; i <= to && i <= 570; i++) i];
      return {'time': t, 'watts': [for (final x in t) x == 400 ? 900 : 320]};
    }),
    profileProvider.overrideWith((ref) async => {'ftp': 300}),
    activityAnalysisProvider(1).overrideWith((ref) async => {'coach_configured': false}), // Feedback gehoert nicht zu diesem Test
  ],
  child: const MaterialApp(home: ActivityScreen(id: 1)),
);

Future<void> _load(WidgetTester tester, Widget w) async {
  tester.view.physicalSize = const Size(1000, 5000);
  tester.view.devicePixelRatio = 1;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(w);
  for (var i = 0; i < 5; i++) {
    await tester.pump(const Duration(milliseconds: 100));
  }
}

/// Alle Diagramme der Fahrt ausser der Leistungskurve (die steht ganz unten).
List<LineChart> _charts(WidgetTester tester) => tester.widgetList<LineChart>(find.byType(LineChart)).toList()..removeLast();

/// Standardansicht ist "Kombiniert"; hier auf die einzelnen Diagramme wechseln.
Future<void> _single(WidgetTester tester) async {
  await tester.tap(find.text('Einzeln'));
  await tester.pump(const Duration(milliseconds: 100));
}

/// Tippt in der Leistungskurve auf den Punkt mit dem gegebenen Index (wie ein Tipp auf den Graphen).
Future<void> _pickDuration(WidgetTester tester, int index) async {
  final data = tester.widget<LineChart>(find.byType(LineChart).last).data; // Leistungskurve steht ganz unten
  final bar = data.lineBarsData.first;
  data.lineTouchData.touchCallback!(
    FlTapUpEvent(TapUpDetails(kind: PointerDeviceKind.touch)),
    LineTouchResponse(
      touchLocation: Offset.zero,
      touchChartCoordinate: Offset.zero,
      lineBarSpots: [TouchLineBarSpot(bar, 0, bar.spots[index], 0)],
    ),
  );
}

void main() {
  setUpAll(() => initializeDateFormatting('de'));

  testWidgets('Zeigt Leistungskurve, Karte, Herzfrequenz und Trittfrequenz', (tester) async {
    await _load(tester, _screen());
    expect(find.text('Leistungskurve'), findsOneWidget);
    expect(find.text('Karte'), findsOneWidget);
    expect(find.text('Herzfrequenz'), findsOneWidget);
    expect(find.text('Trittfrequenz'), findsOneWidget);
    expect(find.text('Auswahl aufheben'), findsNothing);
  });

  testWidgets('Andere Sportarten: Sportart und hrTSS statt Radauswertung', (tester) async {
    await _load(tester, _screen(sport: 'Run', tss: 55));
    expect(find.byType(CoachFeedbackCard), findsNothing);
    expect(find.text('Laufen'), findsOneWidget);
    expect(find.text('hrTSS'), findsOneWidget);
    expect(find.text('TSS'), findsNothing);
    await tester.pumpWidget(const SizedBox()); // neue ProviderScope statt Wiederverwendung
    await _load(tester, _screen(sport: 'Ride', tss: 55));
    expect(find.byType(CoachFeedbackCard), findsOneWidget);
    expect(find.text('Laufen'), findsNothing);
  });

  test('Sportarten: Namen, Symbole, Rad als Standard', () {
    expect(isCyclingSport(null) && isCyclingSport('GravelRide') && isCyclingSport('VirtualRide'), isTrue);
    expect(isCyclingSport('Run'), isFalse);
    expect(sportInfo('Hike').label, 'Wandern');
    expect(sportInfo('WeightTraining').label, 'Krafttraining');
    expect(sportInfo('Run').icon, Icons.directions_run_rounded);
    expect(sportInfo('Irgendwas').label, 'Irgendwas');
  });

  testWidgets('Dauer waehlen hebt den Abschnitt in den Graphen und auf der Karte hervor', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    await _pickDuration(tester, 2); // 5 min
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Beste 5 min: 320 W, von 5:00 bis 10:00'), findsOneWidget);
    expect(find.text('Hervorgehoben: beste 5 min'), findsOneWidget);
    expect(find.text('Ø Abschnitt'), findsNWidgets(3)); // Leistung, Herzfrequenz, Trittfrequenz
    await tester.tap(find.text('Auswahl aufheben'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Ø Abschnitt'), findsNothing);
    expect(find.text('Hervorgehoben: beste 5 min'), findsNothing);
  });

  testWidgets('Runden: Tabelle, Auswahl hebt die Runde hervor und zoomt', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    expect(find.text('Runden'), findsOneWidget);
    expect(find.text('2500 m'), findsNothing);
    expect(find.text('2,50 km'), findsNWidgets(2));
    expect(find.text('320 W'), findsWidgets);
    await tester.tap(find.text('4:30'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Runde 2: 320 W, von 5:00 bis 9:30'), findsOneWidget);
    expect(find.text('Hervorgehoben: Runde 2'), findsOneWidget);
    expect(find.text('Ø Abschnitt'), findsNWidgets(3));
    expect(find.textContaining('Beste '), findsNothing); // die Leistungskurve zeigt keine Auswahl an
    await tester.ensureVisible(find.text('Auf Runde zoomen'));
    await tester.tap(find.text('Auf Runde zoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Ganze Fahrt zeigen'), findsOneWidget);
    await tester.tap(find.text('4:30')); // erneut tippen hebt die Auswahl auf
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Ø Abschnitt'), findsNothing);
  });

  testWidgets('Ohne oder mit nur einer Runde gibt es keine Rundenkarte', (tester) async {
    await _load(tester, _screen(laps: [_laps.first]));
    expect(find.text('Runden'), findsNothing);
    await _load(tester, _screen(laps: const []));
    expect(find.text('Runden'), findsNothing);
  });

  testWidgets('Zoom zeigt in den Diagrammen nur den Abschnitt und laesst sich zuruecknehmen', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    expect(find.text('Auf Abschnitt zoomen'), findsNothing); // ohne Auswahl kein Zoom
    await _pickDuration(tester, 2); // 5 min
    await tester.pump(const Duration(milliseconds: 100));
    List<LineChartData> datas() => _charts(tester).map((c) => c.data).toList(); // ohne Leistungskurve
    expect(datas().where((d) => d.minX == 3.0), isEmpty);
    await tester.tap(find.text('Auf Abschnitt zoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    // Leistung, Herzfrequenz, Trittfrequenz, Hoehe zoomen (die Leistungskurve selbst nicht)
    expect(datas().where((d) => d.minX == 3.0 && d.maxX == 9.5).length, 4);
    await tester.tap(find.text('Ganze Fahrt zeigen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(datas().where((d) => d.minX == 3.0), isEmpty);
    await tester.tap(find.text('Auf Abschnitt zoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Auswahl aufheben')); // Auswahl weg -> Zoom auch
    await tester.pump(const Duration(milliseconds: 100));
    expect(datas().where((d) => d.minX == 3.0), isEmpty);
  });

  testWidgets('Gezoomt werden die Daten des Ausschnitts in hoher Aufloesung nachgeladen', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    int points() => _charts(tester).first.data.lineBarsData.first.spots.length;
    expect(points(), 20); // ganze Fahrt: grob
    await _pickDuration(tester, 2);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.text('Auf Abschnitt zoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    final coarse = points();
    expect(coarse, lessThan(20)); // nur der sichtbare Teil, noch grob (Nachladen mit kurzer Verzoegerung)
    await tester.pump(const Duration(milliseconds: 400));
    await tester.pump(const Duration(milliseconds: 100));
    expect(points(), greaterThan(coarse * 5));
    final spots = _charts(tester).first.data.lineBarsData.first.spots;
    expect(spots.any((p) => p.y == 900), isTrue); // die Spitze ist jetzt sichtbar
    await tester.tap(find.text('Ganze Fahrt zeigen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(points(), lessThanOrEqualTo(20)); // ganze Fahrt wieder grob
    expect(find.text('Auf Abschnitt zoomen'), findsOneWidget);
  });

  testWidgets('Allgemeiner Zoom: Hineinzoomen, Verschieben und Zuruecksetzen wirken auf alle Diagramme', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    List<LineChartData> datas() => _charts(tester).map((c) => c.data).toList(); // ohne Leistungskurve
    expect(find.text('Zoom: ganze Fahrt'), findsOneWidget);
    await tester.tap(find.byTooltip('Hineinzoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Ausschnitt 2:23 bis 7:08'), findsOneWidget);
    expect(datas().where((d) => (d.minX - 2.375).abs() < 1e-6).length, 4);
    await tester.tap(find.byTooltip('Nach rechts'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Ausschnitt 3:34 bis 8:19'), findsOneWidget);
    await tester.tap(find.text('Ganze Fahrt'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Zoom: ganze Fahrt'), findsOneWidget);
    expect(datas().where((d) => !d.minX.isNaN), isEmpty);
  });

  String? viewText(WidgetTester tester) {
    final f = find.textContaining('Ausschnitt ');
    return f.evaluate().isEmpty ? null : tester.widget<Text>(f).data;
  }

  testWidgets('Mausrad zoomt zum Mauszeiger', (tester) async {
    await _load(tester, _screen());
    await _single(tester);
    final rect = tester.getRect(find.byType(LineChart).first);
    final mouse = TestPointer(1, PointerDeviceKind.mouse);
    await tester.sendEventToBinding(mouse.hover(Offset(rect.left + 42, rect.center.dy))); // ganz links in der Zeichenflaeche
    await tester.sendEventToBinding(mouse.scroll(const Offset(0, -100)));
    await tester.pump(const Duration(milliseconds: 100));
    expect(viewText(tester), startsWith('Ausschnitt 0:00 bis')); // Anfang bleibt stehen
    await tester.sendEventToBinding(mouse.scroll(const Offset(0, 100)));
    await tester.pump(const Duration(milliseconds: 100));
    expect(viewText(tester), isNull); // wieder ganze Fahrt
  });

  testWidgets('Zwei Finger zoomen, Ziehen mit der Maus verschiebt', (tester) async {
    await _load(tester, _screen());
    final c = tester.getCenter(find.byType(LineChart).first);
    final g1 = await tester.startGesture(c + const Offset(-80, 0), pointer: 1);
    final g2 = await tester.startGesture(c + const Offset(80, 0), pointer: 2);
    await g1.moveBy(const Offset(-30, 0)); // Finger spreizen = hineinzoomen
    await g2.moveBy(const Offset(30, 0));
    await g1.up();
    await g2.up();
    await tester.pump(const Duration(milliseconds: 100));
    final zoomed = viewText(tester);
    expect(zoomed, isNotNull);

    final drag = await tester.startGesture(c, kind: PointerDeviceKind.mouse, buttons: kPrimaryMouseButton);
    await drag.moveBy(const Offset(120, 0)); // Inhalt nach rechts ziehen -> Ausschnitt rutscht nach links
    await drag.up();
    await tester.pump(const Duration(milliseconds: 100));
    expect(viewText(tester), isNot(zoomed));
  });

  testWidgets('Kombinierte Ansicht: Reihen waehlbar, Zoom gilt weiter, Einzelansicht bleibt moeglich', (tester) async {
    await _load(tester, _screen());
    expect(find.text('Alle Daten in einem Diagramm'), findsOneWidget); // Standardansicht
    expect(find.byType(LineChart), findsNWidgets(2));
    await _single(tester);
    expect(find.text('Alle Daten in einem Diagramm'), findsNothing);
    await tester.tap(find.text('Kombiniert'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.text('Alle Daten in einem Diagramm'), findsOneWidget);
    expect(find.byType(LineChart), findsNWidgets(2)); // Leistungskurve + ein kombiniertes Diagramm, keine Einzeldiagramme
    LineChartData combined() => tester.widgetList<LineChart>(find.byType(LineChart)).first.data;
    expect(combined().lineBarsData.length, 4);
    expect(find.textContaining('Berühre oder fahre mit der Maus'), findsOneWidget);
    final mouse = await tester.createGesture(kind: PointerDeviceKind.mouse);
    await mouse.addPointer(location: Offset.zero);
    addTearDown(mouse.removePointer);
    final c = tester.getCenter(find.byType(LineChart).first);
    await mouse.moveTo(c);
    await tester.pump(const Duration(milliseconds: 100));
    await mouse.moveTo(c + const Offset(6, 0));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.textContaining('Berühre oder fahre mit der Maus'), findsNothing); // Werte stehen ausserhalb des Diagramms
    expect(find.textContaining(' W'), findsWidgets); // Werte der Reihen stehen in der Anzeige
    await tester.tap(find.text('Trittfrequenz'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(combined().lineBarsData.length, 3);
    await tester.tap(find.byTooltip('Hineinzoomen'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(combined().minX, isNot(isNaN));
    await tester.tap(find.text('Einzeln'));
    await tester.pump(const Duration(milliseconds: 100));
    expect(find.byType(LineChart), findsNWidgets(5)); // Leistungskurve + vier Einzeldiagramme
    expect(find.text('Alle Daten in einem Diagramm'), findsNothing);
  });

  test('Zoom-Rechnung bleibt im Bereich', () {
    expect(zoomView(null, 0.5, 100), const ViewRange(25, 75));
    expect(zoomView(const ViewRange(25, 75), 2, 100), isNull); // wieder alles sichtbar
    expect(panView(const ViewRange(25, 75), 1, 100), const ViewRange(50, 100)); // am Ende angehalten
    expect(panView(null, 0.5, 100), isNull);
    expect(clampView(-10, 5, 100)!.min, 0);
    final tiny = clampView(50, 50.01, 100)!;
    expect(tiny.span, 0.5); // nicht weiter als etwa 30 s
  });

  testWidgets('Ohne GPS-Daten gibt es keine Karte', (tester) async {
    await _load(tester, _screen(gps: false));
    expect(find.text('Karte'), findsNothing);
    expect(find.text('Leistungskurve'), findsOneWidget);
  });

  test('Strecke und Highlight', () {
    expect(ActivityMapCard.route(_streams()).length, 20);
    expect(ActivityMapCard.route(_streams(gps: false)), isEmpty);
    const h = Highlight(startS: 300, durationS: 300, watts: 320);
    expect(h.endMin, 10);
  });
}
