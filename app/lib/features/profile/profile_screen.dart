import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'strava_card.dart';

class ProfileScreen extends ConsumerWidget {
  const ProfileScreen({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final profile = ref.watch(profileProvider);
    return Scaffold(
      body: profile.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: StatusMessage.error(errorMessage(e), onRetry: () => ref.invalidate(profileProvider)),
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
    'ftp': 'FTP',
    'weight_kg': 'Gewicht',
    'hr_max': 'Max. Herzfrequenz',
    'hr_rest': 'Ruhepuls',
    'lthr': 'Schwellenpuls (LTHR)',
    'goals': 'Ziele',
  };
  static const _suffix = {'ftp': 'W', 'weight_kg': 'kg', 'hr_max': 'bpm', 'hr_rest': 'bpm', 'lthr': 'bpm'};
  static const _icons = {
    'name': Icons.badge_outlined,
    'ftp': Icons.bolt_rounded,
    'weight_kg': Icons.monitor_weight_outlined,
    'hr_max': Icons.favorite_rounded,
    'hr_rest': Icons.bedtime_outlined,
    'lthr': Icons.monitor_heart_outlined,
    'goals': Icons.flag_outlined,
  };
  static const _sections = [
    ('Persönlich', 'Wie der Coach Dich anspricht', ['name', 'weight_kg']),
    ('Leistung', 'Grundlage für Zonen, IF und TSS', ['ftp']),
    ('Herzfrequenz', 'Für Fahrten ohne Leistungsmesser', ['hr_max', 'hr_rest', 'lthr']),
    ('Ziele', 'Events, Wünsche, verfügbare Zeit', ['goals']),
  ];

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

  double? _value(String k) => double.tryParse(_c[k]!.text.trim().replaceAll(',', '.'));

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
      ref.invalidate(profileProvider);
      messenger.showSnackBar(const SnackBar(content: Text('Gespeichert')));
    } catch (e) {
      messenger.showSnackBar(SnackBar(content: Text(errorMessage(e))));
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  Widget _field(String k) => TextFormField(
        controller: _c[k],
        decoration: InputDecoration(
          labelText: _fields[k],
          prefixIcon: Icon(_icons[k], size: 20),
          suffixText: _suffix[k],
          alignLabelWithHint: k == 'goals',
        ),
        keyboardType: _text.contains(k) ? TextInputType.text : const TextInputType.numberWithOptions(decimal: true),
        maxLines: k == 'goals' ? 4 : 1,
        validator: _text.contains(k) ? null : _number,
        onChanged: (_) => setState(() {}),
      );

  @override
  Widget build(BuildContext context) {
    return PageBody(
      maxWidth: 1000,
      children: [
        PageHeader(
          subtitle: 'Profil',
          title: 'Einstellungen',
          trailing: [
            OutlinedButton.icon(
              onPressed: () => ref.read(authProvider.notifier).signOut(),
              icon: const Icon(Icons.logout_rounded, size: 18),
              label: const Text('Abmelden'),
            ),
          ],
        ),
        _AthleteCard(name: _c['name']!.text, ftp: _value('ftp'), weight: _value('weight_kg')),
        const SizedBox(height: Gap.md),
        LayoutBuilder(builder: (context, c) {
          final form = _buildForm(context);
          final side = Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
            const StravaCard(),
            const SizedBox(height: Gap.md),
            _ZonesCard(zones: zones),
          ]);
          if (c.maxWidth < 820) {
            return Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
              side,
              const SizedBox(height: Gap.md),
              form,
            ]);
          }
          return Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Expanded(flex: 3, child: form),
            const SizedBox(width: Gap.md),
            Expanded(flex: 2, child: side),
          ]);
        }),
      ],
    );
  }

  Widget _buildForm(BuildContext context) {
    final t = Theme.of(context);
    return SurfaceCard(
      padding: const EdgeInsets.all(Gap.xl),
      child: Form(
        key: _form,
        child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
          for (final (i, s) in _sections.indexed) ...[
            if (i > 0) const Padding(padding: EdgeInsets.symmetric(vertical: Gap.lg), child: Divider()),
            Text(s.$1, style: t.textTheme.titleMedium),
            Text(s.$2, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            const SizedBox(height: Gap.md),
            ResponsiveGrid(
              minItemWidth: s.$3.contains('goals') || s.$3.contains('name') ? 240 : 170,
              children: [for (final k in s.$3) _field(k)],
            ),
          ],
          const SizedBox(height: Gap.xl),
          Align(
            alignment: Alignment.centerRight,
            child: FilledButton.icon(
              onPressed: _saving ? null : _save,
              icon: _saving
                  ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.check_rounded),
              label: const Text('Speichern'),
            ),
          ),
        ]),
      ),
    );
  }
}

/// Kopfkarte mit Initialen und den wichtigsten Leistungswerten.
class _AthleteCard extends StatelessWidget {
  const _AthleteCard({required this.name, required this.ftp, required this.weight});
  final String name;
  final double? ftp;
  final double? weight;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final initials = name.trim().isEmpty
        ? '?'
        : name.trim().split(RegExp(r'\s+')).take(2).map((p) => p[0].toUpperCase()).join();
    final wkg = (ftp != null && weight != null && weight! > 0) ? ftp! / weight! : null;

    Widget stat(String label, String value, String unit) => Padding(
          padding: const EdgeInsets.only(right: Gap.xl),
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Text(label, style: t.textTheme.labelSmall?.copyWith(color: Colors.white.withValues(alpha: 0.8))),
            Row(crossAxisAlignment: CrossAxisAlignment.baseline, textBaseline: TextBaseline.alphabetic, children: [
              Text(value, style: t.textTheme.headlineSmall?.copyWith(color: Colors.white)),
              const SizedBox(width: 3),
              Text(unit, style: t.textTheme.labelMedium?.copyWith(color: Colors.white.withValues(alpha: 0.8))),
            ]),
          ]),
        );

    return Card(
      clipBehavior: Clip.antiAlias,
      child: Container(
        decoration: const BoxDecoration(
          gradient: LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [AppColors.brandDeep, Color(0xFF1E3A8A)],
          ),
        ),
        padding: const EdgeInsets.all(Gap.xl),
        child: Wrap(
          spacing: Gap.xl,
          runSpacing: Gap.lg,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Row(mainAxisSize: MainAxisSize.min, children: [
              CircleAvatar(
                radius: 30,
                backgroundColor: Colors.white.withValues(alpha: 0.18),
                child: Text(initials, style: t.textTheme.titleLarge?.copyWith(color: Colors.white)),
              ),
              const SizedBox(width: Gap.lg),
              Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                Text(name.trim().isEmpty ? 'Dein Profil' : name.trim(),
                    style: t.textTheme.titleLarge?.copyWith(color: Colors.white)),
                Text('Athletenprofil', style: t.textTheme.bodySmall?.copyWith(color: Colors.white.withValues(alpha: 0.8))),
              ]),
            ]),
            Row(mainAxisSize: MainAxisSize.min, children: [
              stat('FTP', ftp?.round().toString() ?? '–', 'W'),
              stat('Leistungsgewicht', wkg?.toStringAsFixed(2).replaceAll('.', ',') ?? '–', 'W/kg'),
              stat('Gewicht', weight?.toStringAsFixed(1).replaceAll('.', ',') ?? '–', 'kg'),
            ]),
          ],
        ),
      ),
    );
  }
}

/// Leistungszonen als farbige Balken mit Wattbereichen.
class _ZonesCard extends StatelessWidget {
  const _ZonesCard({required this.zones});
  final List zones;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return SurfaceCard(
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        const SectionHeader(title: 'Leistungszonen', subtitle: 'Nach Coggan, berechnet aus Deiner FTP'),
        for (final (i, z) in zones.indexed)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 3),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: Gap.md, vertical: 10),
              decoration: BoxDecoration(
                color: AppColors.zones[i % 7].withValues(alpha: 0.1),
                borderRadius: BorderRadius.circular(Radii.md),
              ),
              child: Row(children: [
                Container(
                  width: 4,
                  height: 18,
                  margin: const EdgeInsets.only(right: Gap.md),
                  decoration: BoxDecoration(color: AppColors.zones[i % 7], borderRadius: BorderRadius.circular(2)),
                ),
                Expanded(child: Text(z['name'] as String, style: t.textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600))),
                Text(
                  z['max'] == null ? '> ${z['min']} W' : '${z['min']}–${z['max']} W',
                  style: t.textTheme.labelLarge?.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
                ),
              ]),
            ),
          ),
      ]),
    );
  }
}
