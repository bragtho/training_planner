import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

import '../../core/theme.dart';
import '../../core/ui.dart';

/// Navigation: Bottom-Bar auf schmalen Displays, Rail ab Tablet, ausgeklappte Seitenleiste auf Desktop.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  static const _items = [
    (Icons.space_dashboard_outlined, Icons.space_dashboard_rounded, 'Übersicht'),
    (Icons.calendar_month_outlined, Icons.calendar_month_rounded, 'Kalender'),
    (Icons.auto_awesome_outlined, Icons.auto_awesome, 'Coach'),
    (Icons.person_outline_rounded, Icons.person_rounded, 'Profil'),
  ];

  void _go(int i) => shell.goBranch(i, initialLocation: i == shell.currentIndex);

  @override
  Widget build(BuildContext context) {
    final width = MediaQuery.sizeOf(context).width;
    final t = Theme.of(context);
    if (width >= 720) {
      final extended = width >= 1200;
      return Scaffold(
        body: Row(children: [
          NavigationRail(
            extended: extended,
            minExtendedWidth: 220,
            selectedIndex: shell.currentIndex,
            onDestinationSelected: _go,
            labelType: extended ? NavigationRailLabelType.none : NavigationRailLabelType.all,
            leading: Padding(
              padding: const EdgeInsets.only(top: Gap.md, bottom: Gap.xl),
              child: AppLogo(showName: extended),
            ),
            destinations: [
              for (final i in _items)
                NavigationRailDestination(icon: Icon(i.$1), selectedIcon: Icon(i.$2), label: Text(i.$3)),
            ],
          ),
          VerticalDivider(width: 1, color: t.colorScheme.outlineVariant),
          Expanded(child: shell),
        ]),
      );
    }
    return Scaffold(
      body: shell,
      bottomNavigationBar: DecoratedBox(
        decoration: BoxDecoration(border: Border(top: BorderSide(color: t.colorScheme.outlineVariant))),
        child: NavigationBar(
          selectedIndex: shell.currentIndex,
          onDestinationSelected: _go,
          destinations: [
            for (final i in _items) NavigationDestination(icon: Icon(i.$1), selectedIcon: Icon(i.$2), label: i.$3),
          ],
        ),
      ),
    );
  }
}
