import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:intl/date_symbol_data_local.dart';
import 'package:training_planner/core/data.dart';
import 'package:training_planner/features/profile/memory_card.dart';

Widget _app(List<CoachMemory> list) => ProviderScope(
  overrides: [coachMemoriesProvider.overrideWith((ref) async => list)],
  child: const MaterialApp(
    home: Scaffold(body: SingleChildScrollView(child: CoachMemoryCard())),
  ),
);

void main() {
  setUpAll(() => initializeDateFormatting('de'));

  testWidgets('Zeigt Eintraege mit Gueltigkeit und Loeschknopf', (tester) async {
    await tester.pumpWidget(
      _app([
        CoachMemory(id: 1, text: 'Offseason, strukturiertes Training ab November.', validUntil: DateTime(2026, 11, 1)),
        const CoachMemory(id: 2, text: 'Trainiert am liebsten morgens.'),
      ]),
    );
    await tester.pumpAndSettle();
    expect(find.text('Coach-Notizen (2)'), findsOneWidget);
    expect(find.text('Offseason, strukturiertes Training ab November.'), findsNothing);
    await tester.tap(find.text('Coach-Notizen (2)'));
    await tester.pumpAndSettle();
    expect(find.text('Offseason, strukturiertes Training ab November.'), findsOneWidget);
    expect(find.text('gilt bis 1. November 2026'), findsOneWidget);
    expect(find.text('Trainiert am liebsten morgens.'), findsOneWidget);
    expect(find.byTooltip('Vergessen'), findsNWidgets(2));
  });

  testWidgets('Leerer Zustand erklaert, dass sich der Coach Dinge selbst merkt', (tester) async {
    await tester.pumpWidget(_app(const []));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Coach-Notizen'));
    await tester.pumpAndSettle();
    expect(find.textContaining('merkt sich das Wichtige von allein'), findsOneWidget);
    expect(find.byTooltip('Vergessen'), findsNothing);
  });
}
