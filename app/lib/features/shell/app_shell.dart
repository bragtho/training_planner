import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';

/// Navigation: Bottom-Bar auf schmalen Displays, Rail ab Tablet/Desktop-Breite.
class AppShell extends StatelessWidget {
  const AppShell({super.key, required this.shell});
  final StatefulNavigationShell shell;

  static const _items = [
    (Icons.dashboard_outlined, Icons.dashboard, 'Dashboard'),
    (Icons.calendar_month_outlined, Icons.calendar_month, 'Kalender'),
    (Icons.psychology_outlined, Icons.psychology, 'Coach'),
    (Icons.person_outline, Icons.person, 'Profil'),
  ];

  void _go(int i) => shell.goBranch(i, initialLocation: i == shell.currentIndex);

  @override
  Widget build(BuildContext context) {
    final wide = MediaQuery.sizeOf(context).width >= 720;
    if (wide) {
      return Scaffold(
        body: Row(children: [
          NavigationRail(
            selectedIndex: shell.currentIndex,
            onDestinationSelected: _go,
            labelType: NavigationRailLabelType.all,
            destinations: [
              for (final i in _items)
                NavigationRailDestination(
                    icon: Icon(i.$1), selectedIcon: Icon(i.$2), label: Text(i.$3)),
            ],
          ),
          const VerticalDivider(width: 1),
          Expanded(child: shell),
        ]),
      );
    }
    return Scaffold(
      body: shell,
      bottomNavigationBar: NavigationBar(
        selectedIndex: shell.currentIndex,
        onDestinationSelected: _go,
        destinations: [
          for (final i in _items)
            NavigationDestination(
                icon: Icon(i.$1), selectedIcon: Icon(i.$2), label: i.$3),
        ],
      ),
    );
  }
}
