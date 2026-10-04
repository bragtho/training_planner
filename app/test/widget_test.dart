import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/features/shell/placeholder_page.dart';

void main() {
  testWidgets('Platzhalter zeigt Titel und Text', (tester) async {
    await tester.pumpWidget(const MaterialApp(
      home: PlaceholderPage(
          title: 'Kalender', icon: Icons.calendar_month, text: 'Bald'),
    ));
    expect(find.text('Kalender'), findsOneWidget);
    expect(find.text('Bald'), findsOneWidget);
  });
}
