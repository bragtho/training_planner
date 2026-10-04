import 'dart:math' as math;

import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../core/api.dart';
import '../../core/auth.dart';
import '../../core/data.dart';
import '../../core/theme.dart';
import '../../core/ui.dart';
import 'rich_text.dart';

class CoachScreen extends ConsumerStatefulWidget {
  const CoachScreen({super.key});

  @override
  ConsumerState<CoachScreen> createState() => _CoachScreenState();
}

class _CoachScreenState extends ConsumerState<CoachScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();
  final _messages = <Json>[];
  bool _loading = true;
  bool _sending = false;
  bool _configured = true;
  String? _error;
  String? _lastFailed; // fuer "Erneut senden"

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final dio = ref.read(apiProvider).dio;
      final status = await dio.get('/coach/status');
      final r = await dio.get('/coach/messages');
      _configured = status.data['configured'] == true;
      _messages
        ..clear()
        ..addAll([for (final m in r.data as List) Json.from(m as Map)]);
    } catch (e) {
      _error = errorMessage(e);
    } finally {
      if (mounted) setState(() => _loading = false);
      _toBottom();
    }
  }

  void _toBottom() => WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.animateTo(_scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 200), curve: Curves.easeOut);
        }
      });

  /// Sendet eine Nachricht oder startet eine Schnellaktion; die Antwort kann bis zu einigen Minuten dauern.
  Future<void> _send({String? text, String? quick}) async {
    if (_sending) return;
    final shown = text ?? (quick == 'plan_week' ? 'Woche planen' : 'Letztes Training auswerten');
    setState(() {
      _sending = true;
      _error = null;
      _lastFailed = null;
      _messages.add({'id': -1, 'role': 'user', 'text': shown, 'actions': <String>[]});
    });
    _toBottom();
    try {
      final dio = ref.read(apiProvider).dio;
      final r = await (quick != null
          ? dio.post('/coach/quick', data: {'action': quick}, options: Options(receiveTimeout: const Duration(minutes: 6)))
          : dio.post('/coach/chat', data: {'message': text}, options: Options(receiveTimeout: const Duration(minutes: 6))));
      final out = [for (final m in r.data as List) Json.from(m as Map)];
      if (!mounted) return;
      setState(() {
        _messages.removeLast(); // vorlaeufige Nachricht durch gespeicherte ersetzen
        _messages.addAll(out);
      });
      if ((out.last['actions'] as List).isNotEmpty) {
        ref
          ..invalidate(calendarProvider)
          ..invalidate(pmcProvider);
      }
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _messages.removeLast();
        _error = errorMessage(e);
        _lastFailed = text;
        if (quick == null && text != null) _input.text = text;
      });
    } finally {
      if (mounted) setState(() => _sending = false);
      _toBottom();
    }
  }

  Future<void> _clear() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (c) => AlertDialog(
        title: const Text('Verlauf löschen?'),
        content: const Text('Das Gespräch mit dem Coach wird gelöscht. Geplante Trainings bleiben bestehen.'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(c, false), child: const Text('Abbrechen')),
          FilledButton(onPressed: () => Navigator.pop(c, true), child: const Text('Löschen')),
        ],
      ),
    );
    if (ok != true) return;
    try {
      await ref.read(apiProvider).dio.delete('/coach/messages');
      if (mounted) setState(_messages.clear);
    } catch (e) {
      if (mounted) setState(() => _error = errorMessage(e));
    }
  }

  void _submit() {
    final t = _input.text.trim();
    if (t.isEmpty || _sending) return;
    _input.clear();
    _send(text: t);
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final canSend = !_sending && _configured;
    return Scaffold(
      body: SafeArea(
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : Align(
                alignment: Alignment.topCenter,
                child: ConstrainedBox(
                  constraints: const BoxConstraints(maxWidth: 860),
                  child: Column(children: [
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: Gap.lg),
                      child: PageHeader(
                        subtitle: 'KI-Coach',
                        title: 'Dein Trainer',
                        trailing: [
                          IconButton(
                              tooltip: 'Verlauf löschen',
                              onPressed: _messages.isEmpty || _sending ? null : _clear,
                              icon: const Icon(Icons.delete_sweep_outlined)),
                        ],
                      ),
                    ),
                    if (!_configured)
                      const _Banner(
                        icon: Icons.key_off_rounded,
                        text: 'Der Coach ist noch nicht eingerichtet: ANTHROPIC_API_KEY fehlt in backend/.env.',
                      ),
                    Expanded(
                      child: _messages.isEmpty
                          ? _Intro(
                              enabled: canSend,
                              onQuick: (q) => _send(quick: q),
                              onAsk: (text) => _send(text: text),
                            )
                          : ListView.builder(
                              controller: _scroll,
                              padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.lg),
                              itemCount: _messages.length + (_sending ? 1 : 0),
                              itemBuilder: (_, i) => i == _messages.length ? const _Thinking() : _Bubble(m: _messages[i]),
                            ),
                    ),
                    if (_error != null)
                      _Banner(
                        icon: Icons.error_outline_rounded,
                        text: _error!,
                        action: _lastFailed == null
                            ? null
                            : TextButton(
                                onPressed: () {
                                  _input.clear();
                                  _send(text: _lastFailed);
                                },
                                child: const Text('Erneut senden')),
                      ),
                    if (_messages.isNotEmpty)
                      SizedBox(
                        height: 44,
                        child: ListView(
                          scrollDirection: Axis.horizontal,
                          padding: const EdgeInsets.symmetric(horizontal: Gap.lg),
                          children: [
                            ActionChip(
                              avatar: const Icon(Icons.edit_calendar_rounded, size: 18),
                              label: const Text('Woche planen'),
                              onPressed: canSend ? () => _send(quick: 'plan_week') : null,
                            ),
                            const SizedBox(width: Gap.sm),
                            ActionChip(
                              avatar: const Icon(Icons.fact_check_outlined, size: 18),
                              label: const Text('Letztes Training auswerten'),
                              onPressed: canSend ? () => _send(quick: 'review_last') : null,
                            ),
                          ],
                        ),
                      ),
                    Padding(
                      padding: const EdgeInsets.fromLTRB(Gap.lg, Gap.sm, Gap.lg, Gap.md),
                      child: Container(
                        padding: const EdgeInsets.only(left: Gap.lg, right: 6),
                        decoration: BoxDecoration(
                          color: t.colorScheme.surfaceContainerLow,
                          borderRadius: BorderRadius.circular(28),
                          border: Border.all(color: t.colorScheme.outlineVariant),
                          boxShadow: [
                            BoxShadow(color: Colors.black.withValues(alpha: 0.04), blurRadius: 12, offset: const Offset(0, 4)),
                          ],
                        ),
                        child: Row(crossAxisAlignment: CrossAxisAlignment.end, children: [
                          Expanded(
                            child: TextField(
                              controller: _input,
                              enabled: _configured,
                              minLines: 1,
                              maxLines: 5,
                              maxLength: 4000,
                              buildCounter: (_, {required currentLength, required isFocused, maxLength}) => null,
                              textInputAction: TextInputAction.send,
                              onSubmitted: (_) => _submit(),
                              decoration: const InputDecoration(
                                hintText: 'Frag Deinen Coach …',
                                filled: false,
                                border: InputBorder.none,
                                enabledBorder: InputBorder.none,
                                focusedBorder: InputBorder.none,
                                disabledBorder: InputBorder.none,
                                contentPadding: EdgeInsets.symmetric(vertical: 16),
                              ),
                            ),
                          ),
                          Padding(
                            padding: const EdgeInsets.only(bottom: 6),
                            child: IconButton.filled(
                              tooltip: 'Senden',
                              onPressed: canSend ? _submit : null,
                              icon: const Icon(Icons.arrow_upward_rounded),
                            ),
                          ),
                        ]),
                      ),
                    ),
                  ]),
                ),
              ),
      ),
    );
  }
}

class _Banner extends StatelessWidget {
  const _Banner({required this.icon, required this.text, this.action});
  final IconData icon;
  final String text;
  final Widget? action;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.xs),
      padding: const EdgeInsets.symmetric(horizontal: Gap.md, vertical: Gap.sm),
      decoration: BoxDecoration(
        color: t.colorScheme.errorContainer,
        borderRadius: BorderRadius.circular(Radii.md),
      ),
      child: Row(children: [
        Icon(icon, color: t.colorScheme.onErrorContainer, size: 20),
        const SizedBox(width: Gap.sm),
        Expanded(child: Text(text, style: TextStyle(color: t.colorScheme.onErrorContainer))),
        ?action,
      ]),
    );
  }
}

/// Avatar des Coaches: Verlaufskreis mit Funkeln.
class _CoachAvatar extends StatelessWidget {
  const _CoachAvatar({this.size = 32});
  final double size;

  @override
  Widget build(BuildContext context) => Container(
        width: size,
        height: size,
        decoration: const BoxDecoration(
          shape: BoxShape.circle,
          gradient: LinearGradient(colors: [AppColors.brand, AppColors.accent]),
        ),
        child: Icon(Icons.auto_awesome, color: Colors.white, size: size * 0.5),
      );
}

/// Startbildschirm des Chats mit Vorschlaegen zum Antippen.
class _Intro extends StatelessWidget {
  const _Intro({required this.enabled, required this.onQuick, required this.onAsk});
  final bool enabled;
  final void Function(String) onQuick;
  final void Function(String) onAsk;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final suggestions = <(IconData, String, String, VoidCallback)>[
      (Icons.edit_calendar_rounded, 'Woche planen', 'Trainings für die nächsten 7 Tage in den Kalender',
          () => onQuick('plan_week')),
      (Icons.fact_check_outlined, 'Letztes Training auswerten', 'Was lief gut, was kann besser werden?',
          () => onQuick('review_last')),
      (Icons.battery_charging_full_rounded, 'Brauche ich Erholung?', 'Einschätzung anhand Deiner Form',
          () => onAsk('Brauche ich gerade einen Ruhetag?')),
      (Icons.emoji_events_outlined, 'Auf ein Event vorbereiten', 'Aufbau bis zum Wettkampf',
          () => onAsk('Wie bereite ich mich am besten auf mein nächstes Event vor?')),
    ];
    return SingleChildScrollView(
      padding: const EdgeInsets.all(Gap.lg),
      child: Column(children: [
        const SizedBox(height: Gap.lg),
        const _CoachAvatar(size: 64),
        const SizedBox(height: Gap.lg),
        Text('Wie kann ich helfen?', style: t.textTheme.headlineSmall, textAlign: TextAlign.center),
        const SizedBox(height: Gap.sm),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520),
          child: Text(
            'Ich kenne Dein Profil, Deine Fitness und Deinen Kalender. Frag mich nach Training, Erholung oder Ziel-Events. '
            'Geplante Trainings landen direkt im Kalender.',
            textAlign: TextAlign.center,
            style: t.textTheme.bodyMedium?.copyWith(color: t.colorScheme.onSurfaceVariant),
          ),
        ),
        const SizedBox(height: Gap.xl),
        ResponsiveGrid(minItemWidth: 300, children: [
          for (final s in suggestions)
            SurfaceCard(
              onTap: enabled ? s.$4 : null,
              child: Row(children: [
                Container(
                  padding: const EdgeInsets.all(Gap.sm),
                  decoration: BoxDecoration(
                    color: t.colorScheme.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(Radii.md),
                  ),
                  child: Icon(s.$1, color: t.colorScheme.primary, size: 20),
                ),
                const SizedBox(width: Gap.md),
                Expanded(
                  child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                    Text(s.$2, style: t.textTheme.titleSmall),
                    Text(s.$3, style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
                  ]),
                ),
              ]),
            ),
        ]),
      ]),
    );
  }
}

/// Drei pulsierende Punkte, solange der Coach antwortet.
class _Thinking extends StatefulWidget {
  const _Thinking();

  @override
  State<_Thinking> createState() => _ThinkingState();
}

class _ThinkingState extends State<_Thinking> with SingleTickerProviderStateMixin {
  late final _c = AnimationController(vsync: this, duration: const Duration(milliseconds: 1200))..repeat();

  @override
  void dispose() {
    _c.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: Gap.sm),
      child: Row(children: [
        const _CoachAvatar(),
        const SizedBox(width: Gap.sm),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: 14),
          decoration: BoxDecoration(
            color: t.colorScheme.surfaceContainerLow,
            border: Border.all(color: t.colorScheme.outlineVariant),
            borderRadius: BorderRadius.circular(Radii.lg),
          ),
          child: AnimatedBuilder(
            animation: _c,
            builder: (_, _) => Row(mainAxisSize: MainAxisSize.min, children: [
              for (var i = 0; i < 3; i++)
                Container(
                  margin: const EdgeInsets.symmetric(horizontal: 2),
                  width: 7,
                  height: 7,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: t.colorScheme.primary
                        .withValues(alpha: 0.25 + 0.75 * (0.5 + 0.5 * math.sin((_c.value - i * 0.2) * 2 * math.pi))),
                  ),
                ),
              const SizedBox(width: Gap.sm),
              Text('Coach denkt nach', style: t.textTheme.bodySmall?.copyWith(color: t.colorScheme.onSurfaceVariant)),
            ]),
          ),
        ),
      ]),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.m});
  final Json m;

  @override
  Widget build(BuildContext context) {
    final t = Theme.of(context);
    final mine = m['role'] == 'user';
    final actions = [for (final a in (m['actions'] as List? ?? const [])) a as String];
    final maxW = math.min(640.0, MediaQuery.sizeOf(context).width * 0.8);
    final base = t.textTheme.bodyMedium!.copyWith(height: 1.45, color: mine ? t.colorScheme.onPrimary : null);
    final bubble = Container(
      constraints: BoxConstraints(maxWidth: maxW),
      padding: const EdgeInsets.symmetric(horizontal: Gap.lg, vertical: Gap.md),
      decoration: BoxDecoration(
        color: mine ? t.colorScheme.primary : t.colorScheme.surfaceContainerLow,
        border: mine ? null : Border.all(color: t.colorScheme.outlineVariant),
        borderRadius: BorderRadius.only(
          topLeft: const Radius.circular(Radii.lg),
          topRight: const Radius.circular(Radii.lg),
          bottomLeft: Radius.circular(mine ? Radii.lg : 4),
          bottomRight: Radius.circular(mine ? 4 : Radii.lg),
        ),
      ),
      child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
        SelectableText.rich(simpleMarkdown(m['text'] as String, base)),
        if (actions.isNotEmpty) ...[
          const SizedBox(height: Gap.md),
          Container(
            padding: const EdgeInsets.all(Gap.sm),
            decoration: BoxDecoration(
              color: AppColors.completed.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(Radii.md),
            ),
            child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
              for (final a in actions)
                InkWell(
                  borderRadius: BorderRadius.circular(Radii.sm),
                  onTap: () => context.go('/calendar'),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 3, horizontal: 4),
                    child: Row(mainAxisSize: MainAxisSize.min, children: [
                      const Icon(Icons.event_available_rounded, size: 16, color: AppColors.completed),
                      const SizedBox(width: 6),
                      Flexible(
                        child: Text(a,
                            style: t.textTheme.labelMedium
                                ?.copyWith(color: AppColors.completed, fontWeight: FontWeight.w600)),
                      ),
                    ]),
                  ),
                ),
            ]),
          ),
        ],
      ]),
    );
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Row(
        mainAxisAlignment: mine ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!mine) ...[const _CoachAvatar(), const SizedBox(width: Gap.sm)],
          Flexible(child: bubble),
        ],
      ),
    );
  }
}
