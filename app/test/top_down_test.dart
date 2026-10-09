import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/core/ui.dart';

Widget _app(List<bool> ready) => MaterialApp(
  home: Scaffold(
    body: TopDown(sections: [for (var i = 0; i < ready.length; i++) TopDownSection(ready: ready[i], child: Text('A$i'))]),
  ),
);

void main() {
  testWidgets('TopDown zeigt Abschnitte nur bis zum ersten ungeladenen, darunter nichts', (tester) async {
    await tester.pumpWidget(_app([true, false, true]));
    expect(find.text('A0'), findsOneWidget);
    expect(find.text('A1'), findsNothing);
    expect(find.text('A2'), findsNothing); // fertig, aber ein Abschnitt darueber fehlt noch
    expect(find.byType(LoadingBlock), findsOneWidget);
    await tester.pumpWidget(_app([true, true, true]));
    expect([for (final t in ['A0', 'A1', 'A2']) find.text(t).evaluate().length], [1, 1, 1]);
    expect(find.byType(LoadingBlock), findsNothing);
  });
}
