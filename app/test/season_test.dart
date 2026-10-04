import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/core/theme.dart';
import 'package:training_planner/features/season/season_screen.dart';

Json _plan({bool withPlan = true}) {
  final monday = mondayOf(DateTime.now());
  final weeks = <Json>[];
  for (var i = -1; i < 5; i++) {
    final d = DateTime(monday.year, monday.month, monday.day + i * 7);
    final planned = withPlan && i >= 0;
    weeks.add({
      'week_start': isoDay(d),
      'phase': planned ? (i < 3 ? 'base' : 'build') : null,
      'tss_target': planned ? 300.0 + i * 40 : null,
      'hours_target': null,
      'recovery': i == 2,
      'note': i == 0 ? 'Start Struktur' : null,
      'planned_tss': 0,
      'actual_tss': i < 0 ? 210 : 0,
      'ctl': 40.0 + i,
      'tsb': 3.0,
      'projected': i >= 0,
    });
  }
  final eventDay = DateTime(monday.year, monday.month, monday.day + 30);
  return {
    'weeks': weeks,
    'events': [
      {
        'id': 1,
        'date': isoDay(eventDay),
        'name': 'Landesmeisterschaft',
        'priority': 'A',
        'notes': null,
        'days_to_go': 30,
        'form_tsb': 12.0,
      },
    ],
  };
}

Widget _app(Json data) => ProviderScope(
  overrides: [atpProvider.overrideWith((ref, range) async => data)],
  child: MaterialApp(theme: buildTheme(Brightness.light), home: const SeasonScreen()),
);

void main() {
  setUpAll(() => initializeDateFormatting('de'));

  testWidgets('Zeigt Kennzahlen, Event und Wochenliste des Saisonplans', (tester) async {
    tester.view.physicalSize = const Size(1100, 2400);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);
    await tester.pumpWidget(_app(_plan()));
    await tester.pumpAndSettle();

    expect(find.text('Saison im Überblick'), findsOneWidget);
    expect(find.text('Nächstes A-Event'), findsOneWidget);
    expect(find.text('30'), findsOneWidget); // Tage bis zum Event
    expect(find.text('+12'), findsOneWidget); // Form am Event laut Prognose
    expect(find.text('Landesmeisterschaft'), findsWidgets);
    expect(find.text('Start Struktur'), findsWidgets); // in den Details der aktuellen Woche und in der Liste
    expect(find.textContaining('Entlastung'), findsWidgets);
    expect(tester.takeException(), isNull);
  });

  testWidgets('Ohne Plan und Events erklaert die Seite, wie der Plan entsteht', (tester) async {
    await tester.pumpWidget(_app({'weeks': _plan(withPlan: false)['weeks'], 'events': <Json>[]}));
    await tester.pumpAndSettle();
    expect(find.text('Noch kein Saisonplan'), findsOneWidget);
    expect(find.text('Mit dem Coach erstellen'), findsOneWidget);
  });

  test('ISO-Kalenderwoche und Phasen', () {
    expect(isoWeek(DateTime(2026, 10, 4)), 40);
    expect(isoWeek(DateTime(2027, 1, 1)), 53); // 2026 hat 53 Wochen
    expect(isoWeek(DateTime(2027, 1, 4)), 1);
    expect(Phases.label('peak'), 'Spitze');
    expect(Phases.all.keys, ['preparation', 'base', 'build', 'peak', 'race', 'transition']);
    expect(mondayOf(DateTime(2026, 10, 4)), DateTime(2026, 9, 28));
  });
}
