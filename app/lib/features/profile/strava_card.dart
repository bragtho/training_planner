import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';

class StravaCard extends ConsumerStatefulWidget {
  const StravaCard({super.key});

  @override
  ConsumerState<StravaCard> createState() => _StravaCardState();
}

class _StravaCardState extends ConsumerState<StravaCard>
    with WidgetsBindingObserver {
  bool _busy = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  /// Nach der Freigabe im Browser zurueck in der App: Status neu laden.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) ref.invalidate(stravaStatusProvider);
  }

  void _toast(String msg) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(msg)));

  Future<void> _run(Future<void> Function() action) async {
    setState(() => _busy = true);
    try {
      await action();
    } catch (e) {
      if (mounted) _toast(errorMessage(e));
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  Future<void> _connect() => _run(() async {
        final r = await ref.read(apiProvider).dio.get('/integrations/strava/authorize-url');
        final ok = await launchUrl(Uri.parse(r.data['url'] as String),
            mode: LaunchMode.externalApplication);
        if (!ok && mounted) _toast('Browser konnte nicht geöffnet werden');
      });

  Future<void> _sync({bool full = false}) => _run(() async {
        final r = await ref.read(apiProvider).dio.post(
              '/integrations/strava/sync',
              queryParameters: {'full': full},
              options: Options(receiveTimeout: const Duration(minutes: 3)),
            );
        ref
          ..invalidate(stravaStatusProvider)
          ..invalidate(pmcProvider)
          ..invalidate(activitiesProvider);
        if (mounted) {
          _toast('${r.data['imported']} neu importiert, ${r.data['updated']} aktualisiert');
        }
      });

  Future<void> _disconnect() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Strava trennen?'),
        content: const Text(
            'Die Verbindung wird gelöscht. Bereits importierte Aktivitäten bleiben erhalten.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Trennen')),
        ],
      ),
    );
    if (ok != true) return;
    await _run(() async {
      await ref.read(apiProvider).dio.delete('/integrations/strava');
      ref.invalidate(stravaStatusProvider);
    });
  }

  @override
  Widget build(BuildContext context) {
    final status = ref.watch(stravaStatusProvider);
    final t = Theme.of(context);
    final muted = t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant);
    return SurfaceCard(
      child: status.when(
        loading: () => const SizedBox(height: 80, child: Center(child: CircularProgressIndicator())),
        error: (e, _) => Text(errorMessage(e)),
        data: (s) {
          final connected = s['connected'] == true;
          return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            Row(children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(color: AppColors.strava, borderRadius: BorderRadius.circular(Radii.md)),
                child: const Icon(Icons.sync_alt_rounded, color: Colors.white, size: 20),
              ),
              const SizedBox(width: Gap.md),
              Expanded(
                child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                  Text('Strava', style: t.textTheme.titleMedium),
                  Text(
                    connected ? '${s['activity_count']} Aktivitäten importiert' : 'Aktivitäten automatisch importieren',
                    style: muted,
                  ),
                ]),
              ),
              Pill(
                label: connected ? 'Verbunden' : 'Getrennt',
                color: connected ? AppColors.completed : t.colorScheme.outline,
                icon: connected ? Icons.check_circle_rounded : Icons.link_off_rounded,
              ),
            ]),
            const SizedBox(height: Gap.lg),
            if (s['configured'] != true) ...[
              const Text('Auf dem Server fehlen STRAVA_CLIENT_ID und STRAVA_CLIENT_SECRET (backend/.env).'),
              const SizedBox(height: Gap.sm),
              Text('Callback-Domain bei Strava: ${Uri.parse(s['redirect_uri'] as String).host}', style: muted),
            ] else if (!connected) ...[
              FilledButton.icon(
                style: FilledButton.styleFrom(backgroundColor: AppColors.strava, foregroundColor: Colors.white),
                onPressed: _busy ? null : _connect,
                icon: const Icon(Icons.link_rounded),
                label: const Text('Mit Strava verbinden'),
              ),
              const SizedBox(height: Gap.sm),
              Text('Der Browser öffnet sich. Danach kehrst Du hierher zurück.', style: muted, textAlign: TextAlign.center),
            ] else ...[
              FilledButton.icon(
                onPressed: _busy ? null : () => _sync(),
                icon: _busy
                    ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                    : const Icon(Icons.refresh_rounded),
                label: const Text('Jetzt synchronisieren'),
              ),
              const SizedBox(height: Gap.sm),
              Row(children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _busy ? null : () => _sync(full: true),
                    child: const Text('Alles neu laden'),
                  ),
                ),
                const SizedBox(width: Gap.sm),
                TextButton(
                  style: TextButton.styleFrom(foregroundColor: t.colorScheme.error),
                  onPressed: _busy ? null : _disconnect,
                  child: const Text('Trennen'),
                ),
              ]),
            ],
          ]);
        },
      ),
    );
  }
}
