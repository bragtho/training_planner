import 'package:flutter/material.dart';

/// Platzhalter fuer Bereiche, deren Backend-Endpunkte noch folgen.
class PlaceholderPage extends StatelessWidget {
  const PlaceholderPage(
      {super.key, required this.title, required this.icon, required this.text});
  final String title;
  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: Text(title)),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(32),
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Icon(icon, size: 64, color: t.colorScheme.outline),
            const SizedBox(height: 16),
            Text(text, textAlign: TextAlign.center, style: t.textTheme.bodyLarge),
          ]),
        ),
      ),
    );
  }
}
