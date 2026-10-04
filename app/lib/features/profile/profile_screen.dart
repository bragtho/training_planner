import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import 'strava_card.dart';

final profileProvider =
    FutureProvider.autoDispose<Map<String, dynamic>>((ref) async {
  final r = await ref.watch(apiProvider).dio.get('/profile');
  return Map<String, dynamic>.from(r.data as Map);
});

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(profileProvider);
    return Scaffold(
      appBar: AppBar(title: const Text('Profil'), actions: [
        IconButton(
          tooltip: 'Abmelden',
          icon: const Icon(Icons.logout),
          onPressed: () => ref.read(authProvider.notifier).signOut(),
        ),
      ]),
      body: profile.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            Text(errorMessage(e)),
            TextButton(
                onPressed: () => ref.invalidate(profileProvider),
                child: const Text('Erneut versuchen')),
          ]),
        ),
        data: (p) => _ProfileForm(initial: p),
      ),
    );
  }
}

class _ProfileForm extends ConsumerStatefulWidget {
  const _ProfileForm({required this.initial});
  final Map<String, dynamic> initial;

  @override
  ConsumerState<_ProfileForm> createState() => _ProfileFormState();
}

class _ProfileFormState extends ConsumerState<_ProfileForm> {
  final _form = GlobalKey<FormState>();
  late final Map<String, TextEditingController> _c;
  late List zones = widget.initial['zones'] as List;
  bool _saving = false;

  static const _text = {'name', 'goals'};
  static const _fields = {
    'name': 'Name',
    'ftp': 'FTP (Watt)',
    'weight_kg': 'Gewicht (kg)',
    'hr_max': 'Max. Herzfrequenz',
    'hr_rest': 'Ruhepuls',
    'lthr': 'Schwellenpuls (LTHR)',
    'goals': 'Ziele',
  };

  @override
  void initState() {
    super.initState();
    _c = {
      for (final k in _fields.keys)
        k: TextEditingController(text: widget.initial[k]?.toString() ?? '')
    };
  }

  @override
  void dispose() {
    for (final c in _c.values) {
      c.dispose();
    }
    super.dispose();
  }

  String? _number(String? v) {
    if (v == null || v.trim().isEmpty) return null;
    return double.tryParse(v.replaceAll(',', '.')) == null
        ? 'Zahl eingeben'
        : null;
  }

  Future<void> _save() async {
    if (!_form.currentState!.validate()) return;
    setState(() => _saving = true);
    final body = <String, dynamic>{};
    _c.forEach((k, ctrl) {
      final v = ctrl.text.trim();
      if (v.isEmpty) return;
      if (_text.contains(k)) {
        body[k] = v;
      } else {
        final n = double.parse(v.replaceAll(',', '.'));
        body[k] = (k == 'ftp' || k == 'weight_kg') ? n : n.round();
      }
    });
    final messenger = ScaffoldMessenger.of(context);
    try {
      final r = await ref.read(apiProvider).dio.put('/profile', data: body);
      if (mounted) setState(() => zones = r.data['zones'] as List);
      messenger.showSnackBar(const SnackBar(content: Text('Gespeichert')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessage(e))));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Align(
      alignment: Alignment.topCenter,
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 600),
        child: ListView(padding: const EdgeInsets.all(16), children: [
          const StravaCard(),
          const SizedBox(height: 16),
          Form(
            key: _form,
            child: Column(children: [
              for (final e in _fields.entries)
                Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: TextFormField(
                    controller: _c[e.key],
                    decoration: InputDecoration(labelText: e.value),
                    keyboardType: _text.contains(e.key)
                        ? TextInputType.text
                        : const TextInputType.numberWithOptions(decimal: true),
                    maxLines: e.key == 'goals' ? 3 : 1,
                    validator: _text.contains(e.key) ? null : _number,
                  ),
                ),
            ]),
          ),
          FilledButton(
            onPressed: _saving ? null : _save,
            child: const Text('Speichern'),
          ),
          const SizedBox(height: 24),
          Text('Leistungszonen', style: t.textTheme.titleMedium),
          const SizedBox(height: 8),
          for (final z in zones)
            ListTile(
              dense: true,
              title: Text(z['name'] as String),
              trailing: Text(z['max'] == null
                  ? '> ${z['min']} W'
                  : '${z['min']}-${z['max']} W'),
            ),
        ]),
      ),
    );
  }
}
