import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';

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
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: status.when(
          loading: () => const Center(child: CircularProgressIndicator()),
          error: (e, _) => Text(errorMessage(e)),
          data: (s) {
            final connected = s['connected'] == true;
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              Row(children: [
                const Icon(Icons.sync_alt),
                const SizedBox(width: 8),
                Text('Strava', style: t.textTheme.titleMedium),
                const Spacer(),
                if (connected)
                  Chip(
                    label: Text('${s['activity_count']} Aktivitäten'),
                    visualDensity: VisualDensity.compact,
                  ),
              ]),
              const SizedBox(height: 8),
              if (s['configured'] != true) ...[
                const Text(
                    'Auf dem Server fehlen STRAVA_CLIENT_ID und STRAVA_CLIENT_SECRET (backend/.env).'),
                const SizedBox(height: 8),
                Text('Callback-Domain bei Strava: ${Uri.parse(s['redirect_uri'] as String).host}',
                    style: t.textTheme.bodySmall),
              ] else if (!connected) ...[
                const Text(
                    'Verbinde Strava, um deine bisherigen Fahrten automatisch zu importieren.'),
                const SizedBox(height: 12),
                FilledButton.icon(
                  onPressed: _busy ? null : _connect,
                  icon: const Icon(Icons.link),
                  label: const Text('Mit Strava verbinden'),
                ),
                const SizedBox(height: 4),
                Text('Der Browser öffnet sich. Danach kehrst du hierher zurück.',
                    style: t.textTheme.bodySmall),
              ] else ...[
                Wrap(spacing: 8, runSpacing: 8, children: [
                  FilledButton.icon(
                    onPressed: _busy ? null : () => _sync(),
                    icon: _busy
                        ? const SizedBox(
                            width: 16, height: 16,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.refresh),
                    label: const Text('Jetzt synchronisieren'),
                  ),
                  OutlinedButton(
                    onPressed: _busy ? null : () => _sync(full: true),
                    child: const Text('Alles neu laden'),
                  ),
                  TextButton(
                    onPressed: _busy ? null : _disconnect,
                    child: const Text('Trennen'),
                  ),
                ]),
              ],
            ]);
          },
        ),
      ),
    );
  }
}
