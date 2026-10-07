import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/features/calendar/exercise_figure.dart';
import 'package:training_planner/features/calendar/strength_plan.dart';
import 'package:training_planner/features/dashboard/today_card.dart';

final _exercises = <Json>[
  {'type': 'exercise', 'exercise_id': 'squat', 'name': 'Kniebeuge', 'sets': 3, 'reps': 8, 'rest_s': 120, 'load': 'RPE 7', 'note': 'Rücken gerade'},
  {'type': 'exercise', 'name': 'Plank', 'sets': 3, 'duration_s': 45, 'rest_s': 30},
];

final _catalog = <String, Json>{
  'squat': {
    'id': 'squat',
    'name': 'Kniebeuge',
    'hold': false,
    'muscles': ['Gesäß'],
    'steps': ['Füße schulterbreit.', 'Gesäß nach hinten schieben.'],
    'mistakes': ['Knie fallen nach innen'],
  },
};

Widget _wrap(Widget child) => ProviderScope(
      overrides: [exerciseCatalogProvider.overrideWith((ref) async => _catalog)],
      child: MaterialApp(home: Scaffold(body: SingleChildScrollView(child: child))),
    );

void main() {
  test('Texte fuer Saetze und Pause', () {
    expect(setsText(_exercises[0]), '3 × 8 Wiederholungen');
    expect(setsText(_exercises[1]), '3 × 45 s halten');
    expect(restText(30), '30 s');
    expect(restText(120), '2:00 min');
    expect(restText(90), '1:30 min');
  });

  testWidgets('Zeigt Uebungen mit Saetzen, Pause, Last und Hinweis', (tester) async {
    await tester.pumpWidget(_wrap(StrengthPlan(exercises: _exercises, durationS: 597)));
    expect(find.text('Krafttraining'), findsOneWidget);
    expect(find.text('2 Übungen · ca. 9 min'), findsOneWidget);
    expect(find.text('Kniebeuge'), findsOneWidget);
    expect(find.text('3 × 8 Wiederholungen'), findsOneWidget);
    expect(find.text('Pause 2:00 min'), findsOneWidget);
    expect(find.text('RPE 7'), findsOneWidget);
    expect(find.text('Rücken gerade'), findsOneWidget);
    expect(find.text('3 × 45 s halten'), findsOneWidget);
    expect(find.text('Pause 30 s'), findsOneWidget);
  });

  test('Leistungsprofil ignoriert Kraftuebungen', () {
    expect(WorkoutProfile.flatten(_exercises), isEmpty);
    final mixed = [
      {'type': 'steady', 'duration_s': 600, 'power_pct': [60, 60]},
      ..._exercises,
    ];
    expect(WorkoutProfile.flatten(mixed).length, 1);
  });

  testWidgets('Antippen klappt Bilder, Anleitung und typische Fehler auf', (tester) async {
    await tester.pumpWidget(_wrap(StrengthPlan(exercises: _exercises, durationS: 597)));
    await tester.pump();
    expect(find.text("So geht's"), findsNothing);
    await tester.tap(find.text('Kniebeuge'));
    await tester.pump();
    expect(find.text("So geht's"), findsOneWidget);
    expect(find.text('Füße schulterbreit.'), findsOneWidget);
    expect(find.text('Gesäß'), findsOneWidget);
    expect(find.text('Häufige Fehler'), findsOneWidget);
    expect(find.text('Start'), findsOneWidget);
    expect(find.text('Ende'), findsOneWidget);
    await tester.tap(find.text('Kniebeuge'));
    await tester.pump();
    expect(find.text("So geht's"), findsNothing);
    // Uebung ohne Katalog-Kennung: Hinweis statt Anleitung
    await tester.tap(find.text('Plank'));
    await tester.pump();
    expect(find.textContaining('noch keine Anleitung'), findsOneWidget);
    expect(find.text("So geht's"), findsNothing);
  });

  testWidgets('Alle Posen lassen sich zeichnen, Haltuebungen zeigen eine Position', (tester) async {
    for (final id in exercisePoses.keys) {
      await tester.pumpWidget(MaterialApp(home: Scaffold(body: SizedBox(width: 400, child: ExerciseFigures(exerciseId: id)))));
      expect(find.byType(PoseImage), findsNWidgets(exercisePoses[id]!.$2 == null ? 1 : 2), reason: id);
    }
    expect(exercisePoses.length, 19);
    expect(ExerciseFigures.has('squat'), isTrue);
    expect(ExerciseFigures.has('gibt_es_nicht'), isFalse);
  });
}
