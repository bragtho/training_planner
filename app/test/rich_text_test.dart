import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:training_planner/features/coach/rich_text.dart';

void main() {
  const base = TextStyle(fontSize: 14);

  test('Listen werden zu Aufzaehlungspunkten, fett wird hervorgehoben', () {
    final span = simpleMarkdown('Plan:\n- **Di** Sweetspot\n* Fr Ruhetag', base);
    expect(span.toPlainText(), 'Plan:\n•  Di Sweetspot\n•  Fr Ruhetag');
    final bold = <String>[];
    span.visitChildren((s) {
      if (s is TextSpan && s.style?.fontWeight == FontWeight.bold) bold.add(s.text ?? '');
      return true;
    });
    expect(bold, ['Di']);
  });

  test('Ueberschriften verlieren die Rauten, HTML bleibt Text', () {
    final span = simpleMarkdown('## Woche\n<b>nicht fett</b>', base);
    expect(span.toPlainText(), 'Woche\n<b>nicht fett</b>');
  });
}
