import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/core/theme.dart';
import 'package:training_planner/core/ui.dart';

void main() {
  test('Zonen entsprechen den Coggan-Grenzen des Backends', () {
    expect(AppColors.zoneIndex(40), 0);
    expect(AppColors.zoneIndex(55), 1);
    expect(AppColors.zoneIndex(89.9), 2);
    expect(AppColors.zoneIndex(90), 3);
    expect(AppColors.zoneIndex(110), 4);
    expect(AppColors.zoneIndex(130), 5);
    expect(AppColors.zoneIndex(200), 6);
  });

  test('Form wird in verstaendliche Bereiche eingeordnet', () {
    expect(FormStatus.of(30).label, 'Erholt, Fitness sinkt');
    expect(FormStatus.of(10).label, 'Frisch');
    expect(FormStatus.of(0).label, 'Ausgeglichen');
    expect(FormStatus.of(-20).label, 'Produktives Training');
    expect(FormStatus.of(-35).label, 'Überlastet');
  });

  testWidgets('Kennzahl zeigt Wert auch in sehr schmaler Kachel', (tester) async {
    await tester.pumpWidget(MaterialApp(
      theme: buildTheme(Brightness.light),
      home: const Scaffold(
        body: Center(
          child: SizedBox(
            width: 110,
            child: MetricTile(label: 'Ermüdung', value: '20', unit: 'ATL', delta: -16, icon: Icons.bolt),
          ),
        ),
      ),
    ));
    expect(find.text('20'), findsOneWidget);
    expect(find.byIcon(Icons.bolt), findsNothing); // Symbol entfaellt bei wenig Platz
    expect(tester.takeException(), isNull);
  });
}
