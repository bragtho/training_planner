import 'package:flutter/foundation.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../features/activity/activity_screen.dart';
import '../features/auth/login_screen.dart';
import '../features/bests/bests_screen.dart';
import '../features/calendar/calendar_screen.dart';
import '../features/calendar/workout_detail.dart';
import '../features/calendar/workout_editor.dart';
import '../features/coach/coach_screen.dart';
import '../features/dashboard/dashboard_screen.dart';
import '../features/profile/profile_screen.dart';
import '../features/season/season_screen.dart';
import '../features/shell/app_shell.dart';
import 'auth.dart';

final routerProvider = Provider<GoRouter>((ref) {
  // Router wird nur bei Auth-Aenderung neu bewertet, nicht neu gebaut.
  final refresh = ValueNotifier<int>(0);
  ref.listen(authProvider, (_, _) => refresh.value++);
  ref.onDispose(refresh.dispose);

  return GoRouter(
    initialLocation: '/',
    refreshListenable: refresh,
    redirect: (context, state) {
      final status = ref.read(authProvider);
      if (status == AuthStatus.unknown) return null;
      final onLogin = state.matchedLocation == '/login';
      if (status == AuthStatus.signedOut) return onLogin ? null : '/login';
      return onLogin ? '/' : null;
    },
    routes: [
      GoRoute(path: '/login', builder: (_, _) => const LoginScreen()),
      GoRoute(path: '/season', builder: (_, _) => const SeasonScreen()),
      GoRoute(path: '/bests', builder: (_, _) => const BestsScreen()),
      GoRoute(
        path: '/workout/new',
        builder: (_, state) => WorkoutEditorScreen(
          initialDate: DateTime.tryParse(state.uri.queryParameters['date'] ?? ''),
        ),
      ),
      GoRoute(
        path: '/workout/:id',
        builder: (_, state) => WorkoutDetailScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/workout/:id/edit',
        builder: (_, state) => WorkoutEditorScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      GoRoute(
        path: '/activity/:id',
        builder: (_, state) =>
            ActivityScreen(id: int.parse(state.pathParameters['id']!)),
      ),
      StatefulShellRoute.indexedStack(
        builder: (_, _, shell) => AppShell(shell: shell),
        branches: [
          StatefulShellBranch(routes: [
            GoRoute(path: '/', builder: (_, _) => const DashboardScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/calendar', builder: (_, _) => const CalendarScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/coach', builder: (_, _) => const CoachScreen()),
          ]),
          StatefulShellBranch(routes: [
            GoRoute(path: '/profile', builder: (_, _) => const ProfileScreen()),
          ]),
        ],
      ),
    ],
  );
});
