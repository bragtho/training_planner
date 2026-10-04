import 'package:flutter/material.dart';

/// Minimaler Markdown-Ersatz fuer Coach-Antworten: **fett**, Listen mit "- " oder "* ", Absaetze.
/// Alles andere wird als Text angezeigt (kein HTML, keine Links).
TextSpan simpleMarkdown(String text, TextStyle base) {
  final spans = <InlineSpan>[];
  final lines = text.split('\n');
  for (var i = 0; i < lines.length; i++) {
    var line = lines[i];
    final bullet = RegExp(r'^\s*[-*•]\s+').firstMatch(line);
    if (bullet != null) {
      line = '•  ${line.substring(bullet.end)}';
    } else {
      line = line.replaceFirst(RegExp(r'^#{1,6}\s+'), ''); // Ueberschriften als normaler Text
    }
    spans.addAll(_bold(line, base, headline: RegExp(r'^#{1,6}\s+').hasMatch(lines[i])));
    if (i < lines.length - 1) spans.add(const TextSpan(text: '\n'));
  }
  return TextSpan(style: base, children: spans);
}

List<InlineSpan> _bold(String line, TextStyle base, {bool headline = false}) {
  final out = <InlineSpan>[];
  final re = RegExp(r'\*\*(.+?)\*\*');
  var pos = 0;
  for (final m in re.allMatches(line)) {
    if (m.start > pos) out.add(TextSpan(text: line.substring(pos, m.start)));
    out.add(TextSpan(text: m.group(1), style: const TextStyle(fontWeight: FontWeight.bold)));
    pos = m.end;
  }
  if (pos < line.length) out.add(TextSpan(text: line.substring(pos)));
  return headline ? [TextSpan(style: const TextStyle(fontWeight: FontWeight.bold), children: out)] : out;
}
